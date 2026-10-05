#!/usr/bin/env python3
"""Paired, private jailed runtime diagnostics; never infer qualification from exit zero."""

import base64
from concurrent.futures import ThreadPoolExecutor
import fcntl
import gzip
import importlib.util
import json
import os
from pathlib import Path
import resource
import shutil
import statistics
import subprocess
import time


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    specification = importlib.util.spec_from_file_location(
        name.replace("-", "_"), Path(__file__).with_name(f"{name}.py"),
    )
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


vm = load("perf-zig-native-vm")
accounting = load("perf-zig-native")


def usage():
    return [
        resource.getrusage(kind).ru_utime + resource.getrusage(kind).ru_stime
        for kind in (resource.RUSAGE_SELF, resource.RUSAGE_CHILDREN)
    ]


def distribution(values):
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    return {
        "n": len(values), "median": statistics.median(values),
        "mean": statistics.mean(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0,
        "p95": ordered[int((len(ordered) - 1) * .95)],
        "p99": ordered[int((len(ordered) - 1) * .99)], "max": max(values),
        "tail_scope": "empirical within-session order statistics, not independent-tail confidence",
    }


def pty_samples(machine, count):
    control = machine.control
    vm.send(control, {
        "method": "spawn", "interactive": True,
        "cmd": "stty -echo; while IFS= read -r line; do if test $line = quit; then break; fi; echo ack:$line; done",
    })
    samples = []
    for number in range(count + 1):
        token = f"{number:08d}"
        started = time.perf_counter()
        vm.send(control, {"type": "stdin", "data": base64.b64encode(f"{token}\n".encode()).decode()})
        output = bytearray()
        expected = f"ack:{token}".encode()
        while expected not in output:
            result = vm.receive(control)
            if result.get("type") == "exit":
                raise RuntimeError("PTY exited before its numbered ACK")
            if result.get("type") == "stdout":
                output.extend(base64.b64decode(result["data"]))
        if number:
            samples.append((time.perf_counter() - started) * 1000)
    vm.send(control, {"type": "stdin", "data": base64.b64encode(b"quit\n").decode()})
    while True:
        result = vm.receive(control)
        if result.get("type") == "exit":
            if result["code"] != 0:
                raise RuntimeError(f"PTY exit failed: {result}")
            return samples


def perform(machine, workload, specification, folder, binary=None, fixtures=None):
    result = {}
    samples = []
    control = machine.control
    count = specification["operations"]
    if workload == "boot-restore":
        marker = b"restored-owned-runtime"
        vm.request(control, {
            "method": "write_file", "path": "/work/runtime-marker",
            "data": base64.b64encode(marker).decode(),
        })
        control.close()
        machine.control = None
        time.sleep(.3)
        vm.api(machine.api_path, "PATCH", "/vm", {"state": "Paused"})
        started = time.perf_counter()
        vm.api(machine.api_path, "PUT", "/snapshot/create", {
            "snapshot_path": "state.snap", "mem_file_path": "memory.snap",
        })
        result["snapshot_ms"] = (time.perf_counter() - started) * 1000
        result["expected_restored_marker"] = marker.decode()
    elif workload == "pty":
        samples = pty_samples(machine, count)
    elif workload in ("exec", "disk", "vsock"):
        for number in range(count):
            started = time.perf_counter()
            if workload == "exec":
                expected = f"owned-{number}".encode()
                if vm.execute(control, f"printf owned-{number}") != expected:
                    raise RuntimeError("exec content mismatch")
            elif workload == "disk":
                expected = f"disk-{number}".encode()
                if vm.execute(
                    control,
                    "dd if=/dev/zero of=/mnt/runtime-io bs=4096 count=64 conv=fsync 2>/dev/null && "
                    "test $(wc -c </mnt/runtime-io) -eq 262144 && cat /mnt/runtime-io >/dev/null && "
                    f"printf disk-{number}",
                ) != expected:
                    raise RuntimeError("disk completion mismatch")
            else:
                vm.request(control, {"method": "ping"})
            samples.append((time.perf_counter() - started) * 1000)
    elif workload == "idle":
        result["meaning"] = "no client traffic; heartbeat fixture still active; not whole-host or production idle"
        started = time.perf_counter()
        time.sleep(specification["idle_seconds"])
        result["idle_elapsed_seconds"] = time.perf_counter() - started
        control.settimeout(2)
        if vm.execute(control, "printf post-idle") != b"post-idle":
            raise RuntimeError("post-idle guest execution failed")
    elif workload == "concurrency":
        result["levels"] = []
        for level in specification["concurrency"]:
            machines = [machine]
            extras = []
            try:
                for number in range(1, level):
                    extra_folder = folder / f"concurrency-{level}-{number}"
                    extra_folder.mkdir()
                    extra = vm.Vm(binary, extra_folder, **fixtures,
                                  cpu=specification["concurrency_cpus"][number - 1], jailed=True)
                    extras.append(extra)
                    machines.append(extra)
                started = time.perf_counter()
                with ThreadPoolExecutor(max_workers=level) as threads:
                    for number in range(count):
                        expected = f"concurrent-{number}".encode()
                        answers = list(threads.map(
                            lambda current: vm.execute(current.control, f"printf concurrent-{number}"),
                            machines,
                        ))
                        if any(answer != expected for answer in answers):
                            raise RuntimeError("concurrent guest content mismatch")
                elapsed = time.perf_counter() - started
                result["levels"].append({
                    "concurrency": level, "completed_operations": count * level,
                    "wall_seconds": elapsed, "operations_per_second": count * level / elapsed,
                    "jail_rosters": [current.jail_status for current in machines],
                    "driver_affinity": specification["observer_affinity"],
                    "limitation": "host client threads may bottleneck; not an automatic throughput gate",
                })
            finally:
                cleanup_errors = []
                for extra in extras:
                    try:
                        extra.close()
                    except Exception as error:
                        cleanup_errors.append(repr(error))
                if cleanup_errors:
                    raise RuntimeError(f"owned concurrent cleanup failed: {cleanup_errors}")
    else:
        raise ValueError(f"unsupported workload: {workload}; do not silently omit it")
    if samples:
        result["samples_ms"] = samples
        result["distribution_ms"] = distribution(samples)
        result["completed_operations"] = len(samples)
    return result


def compact_snapshots(folder):
    archive = []
    for name in ("disk.ext4", "state.snap", "memory.snap"):
        source = folder / name
        if not source.exists():
            continue
        digest = vm.digest(source)
        target = folder / f"{name}.gz"
        with source.open("rb") as input_stream, target.open("xb") as output_stream:
            with gzip.GzipFile(filename="", mode="wb", fileobj=output_stream, compresslevel=1, mtime=0) as compressed:
                shutil.copyfileobj(input_stream, compressed)
        with gzip.open(target, "rb") as stream:
            import hashlib
            if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                raise RuntimeError("snapshot archive byte verification failed")
        archive.append({"original": name, "sha256": digest, "archive": target.name, "bytes": target.stat().st_size})
        source.unlink()
    (folder / "snapshot-archives.json").write_text(json.dumps(archive, indent=2) + "\n")


def runtime(manifest, output, lock_path):
    raw = manifest.read_bytes()
    specification = json.loads(raw)
    variants = specification["variants"]
    if len(variants) != 2:
        raise ValueError("runtime comparison requires exactly two frozen variants")
    workloads = specification["workloads"]
    allowed = ("boot-restore", "exec", "pty", "disk", "vsock", "idle", "concurrency")
    if not workloads or any(workload not in allowed for workload in workloads):
        raise ValueError("unsupported workload must have a separate explicit diagnostic recipe")
    if specification["operations"] < 1 or specification["repeats"] < 1:
        raise ValueError("nonempty independent samples required")
    if "concurrency" in workloads and (
            specification["collector"] != "none"
            or specification["concurrency"] != [1, 2, 4, 8]
            or len(specification["concurrency_cpus"]) < 7):
        raise ValueError("concurrency requires frozen 1/2/4/8 CPU topology and unprofiled driver controls")
    output.mkdir(parents=True, exist_ok=False)
    (output / "manifest.json").write_bytes(raw)
    (output / "runtime.py").write_bytes(Path(__file__).read_bytes())
    (output / "vm.py").write_bytes(Path(__file__).with_name("perf-zig-native-vm.py").read_bytes())
    rows = []
    original_affinity = os.sched_getaffinity(0)
    fixtures = {key: accounting.project_path(specification[key]) for key in ("kernel", "initrd", "disk")}
    try:
        os.sched_setaffinity(0, specification["observer_affinity"])
        for workload in workloads:
            for repeat in range(specification["repeats"]):
                order = range(2) if repeat % 2 == 0 else reversed(range(2))
                for index in order:
                    variant = variants[index]
                    folder = output / f"{workload}-r{repeat:02d}-v{index}"
                    folder.mkdir()
                    row = {
                        "workload": workload, "repeat": repeat, "variant": variant["id"],
                        "heartbeat_ms": specification["heartbeat_ms"],
                        "qualification": "diagnostic; complete counters/tails/native hardware gates remain separate",
                    }
                    machine = None
                    with Path(lock_path).open("a") as lock:
                        fcntl.flock(lock, fcntl.LOCK_EX)
                        for name, digest in specification["hashes"].items():
                            if accounting.sha256(accounting.project_path(name)) != digest:
                                raise ValueError(f"runtime source/binary/fixture identity changed: {name}")
                        if shutil.disk_usage(ROOT).free < specification["minimum_free_bytes"]:
                            raise OSError("insufficient artifact capacity; retained evidence not deleted")
                        before_cpu, before_host = usage(), accounting.host_cpu_snapshot()
                        started = time.monotonic()
                        try:
                            collector = None
                            if specification["collector"] == "stat":
                                collector = [
                                    "stat", "-x,", "-e", specification["events"],
                                    "-o", str(folder / "boot.perf-stat.csv"),
                                ]
                            elif specification["collector"] == "record":
                                collector = [
                                    "record", "-e", "cpu-clock", "-F", "49",
                                    "--call-graph", "dwarf,4096", "--no-buildid-cache",
                                    "-o", str(folder / "boot.perf.data"),
                                ]
                            elif specification["collector"] != "none":
                                raise ValueError("unknown collector")
                            binary = accounting.project_path(variant["binary"])
                            machine = vm.Vm(binary, folder, **fixtures, cpu=specification["cpu"],
                                            jailed=True, collector=collector)
                            row["boot_ready_ms"] = machine.ready_ms
                            row["creator_argv"] = machine.process.args
                            row["creator_jail_status"] = machine.jail_status
                            row.update(perform(machine, workload, specification, folder, binary, fixtures))
                            machine.close()
                            row["creator_cleanup_verified"] = machine.cleanup_verified
                            machine = None
                            if workload == "boot-restore":
                                if collector:
                                    collector = [argument.replace("boot.perf", "restore.perf") for argument in collector]
                                machine = vm.Vm(binary, folder, **fixtures, cpu=specification["cpu"],
                                                restore=True, jailed=True, collector=collector)
                                row["restore_ready_ms"] = machine.ready_ms
                                row["restorer_argv"] = machine.process.args
                                row["restorer_jail_status"] = machine.jail_status
                                if vm.execute(machine.control, "cat /work/runtime-marker") != row["expected_restored_marker"].encode():
                                    raise RuntimeError("restored guest marker mismatch")
                                row["restored_guest_execution"] = "passed"
                                machine.close()
                                row["restorer_cleanup_verified"] = machine.cleanup_verified
                                machine = None
                            row["status"] = "passed"
                        except Exception as error:
                            row["status"] = "failed"
                            row["error"] = repr(error)
                        finally:
                            if machine:
                                try:
                                    machine.close()
                                    row["cleanup_verified"] = machine.cleanup_verified
                                except Exception as error:
                                    row["status"] = "failed"
                                    row["cleanup_error"] = repr(error)
                            after_cpu = usage()
                            row["lifecycle_wall_seconds"] = time.monotonic() - started
                            row["driver_cpu_seconds"] = after_cpu[0] - before_cpu[0]
                            row["reaped_child_tree_cpu_seconds"] = after_cpu[1] - before_cpu[1]
                            row["cpu_scope"] = "driver plus reaped descendants; detached/unreaped/asynchronous kernel workers not complete"
                            row["whole_host_control"] = accounting.host_cpu_delta(before_host, accounting.host_cpu_snapshot())
                            (folder / "results.json").write_text(json.dumps(row, indent=2) + "\n")
                        if specification["collector"] == "stat":
                            captures = list(folder.glob("*.perf-stat.csv"))
                            row["counter_captures"] = []
                            for capture in captures:
                                contents = subprocess.check_output(
                                    ["sudo", "-n", "--", "cat", "--", str(capture)],
                                    cwd=ROOT, text=True, timeout=10,
                                )
                                row["counter_captures"].append({
                                    "path": capture.name, "csv": contents,
                                    "scope": "inherited owned VMM/threads/taskset, including startup and shutdown",
                                })
                            row["collector_verified"] = bool(captures) and all(
                                capture["csv"].strip() for capture in row["counter_captures"]
                            )
                            if not row["collector_verified"]:
                                row["status"] = "failed"
                                row["counter_error"] = "collector produced no counters; guest correctness alone is not profile coverage"
                            (folder / "results.json").write_text(json.dumps(row, indent=2) + "\n")
                        if specification["collector"] == "record":
                            prerequisite = importlib.util.spec_from_file_location(
                                "private_native_perf", ROOT / "tools/perf/blk-io.py",
                            )
                            support = importlib.util.module_from_spec(prerequisite)
                            prerequisite.loader.exec_module(support)
                            row["reports"] = []
                            for capture in folder.glob("*.perf.data"):
                                argv = support.privileged_perf([
                                    "report", "--stdio", "--force", "-i", str(capture),
                                ])
                                with (folder / f"{capture.name}.report").open("wb") as stdout:
                                    status = subprocess.run(
                                        argv, cwd=ROOT, stdout=stdout, stderr=subprocess.STDOUT,
                                        timeout=30, check=False,
                                    ).returncode
                                row["reports"].append({"capture": capture.name, "exit_code": status, "argv": argv})
                            row["collector_verified"] = bool(row["reports"]) and all(
                                report["exit_code"] == 0 and (folder / report["capture"]).stat().st_size > 0
                                for report in row["reports"]
                            )
                            if not row["collector_verified"]:
                                row["status"] = "failed"
                                row["counter_error"] = "missing or failed stack capture/report"
                            (folder / "results.json").write_text(json.dumps(row, indent=2) + "\n")
                        for extra_folder in folder.glob("concurrency-*"):
                            if extra_folder.is_dir():
                                compact_snapshots(extra_folder)
                        compact_snapshots(folder)
                    rows.append(row)
                    (output / "results.json").write_text(json.dumps(rows, indent=2) + "\n")
                    if row.get("cleanup_error"):
                        raise RuntimeError("owned cleanup failed; stop experiment")
    finally:
        os.sched_setaffinity(0, original_affinity)
    return {
        "rows": len(rows), "passed": sum(row["status"] == "passed" for row in rows),
        "failed": sum(row["status"] != "passed" for row in rows),
        "adoption_qualified": False,
    }
