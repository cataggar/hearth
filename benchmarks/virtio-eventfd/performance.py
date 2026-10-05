#!/usr/bin/env python3
"""Matched functioning-C00 matrix; candidates require an immutable gate file."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import random
import signal
import socket
import statistics
import subprocess
import sys
import threading
import time

import control
import matrix
import run as bench
import tap_probe


def percentile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    first = int(position)
    return ordered[first] + (ordered[min(first + 1, len(ordered) - 1)] - ordered[first]) * (position - first)


def summary(values):
    return {"n": len(values), "mean": statistics.mean(values),
            "p50": percentile(values, .5), "p95": percentile(values, .95), "p99": percentile(values, .99),
            "cv": statistics.stdev(values) / statistics.mean(values) if len(values) > 1 and statistics.mean(values) else 0}


def workload(guest, tcp, name):
    latency, bytes_done = [], 0
    if name.startswith("disk-"):
        _, operation, size = name.split("-")
        block = int(size)
        data = json.loads(matrix.rpc_exec(guest, f"/disk-probe {operation} {block} {128 if block == 4096 else 16}", 25))
        latency = [value / 1e6 for value in data["latency_ns"]]
        bytes_done = data["operations"] * block
        return latency, bytes_done, data
    if name.startswith(("vsock-", "tap-")):
        transport, size = name.split("-")
        connection = guest.native_connection if transport == "vsock" else tcp
        for index in range(128 if int(size) < 65536 else 64):
            started = time.monotonic()
            bench.native_echo(connection, index, int(size))
            latency.append((time.monotonic() - started) * 1000)
            bytes_done += int(size) * 2
        return latency, bytes_done, {"integrity": "all payloads+FNV+sequence verified", "messages": len(latency)}
    if name == "slow-reader":
        started = time.monotonic()
        checked = bench.native_backpressure(guest.native_connection, 200, 65536)
        return [(time.monotonic() - started) * 1000], 2 * 8 * 65536, checked
    if name == "exec":
        for _ in range(64):
            started = time.monotonic()
            if matrix.rpc_exec(guest, "printf EXEC") != b"EXEC":
                raise ValueError("exec integrity failure")
            latency.append((time.monotonic() - started) * 1000)
        return latency, 0, {"commands": 64, "agent_unchanged": True}
    if name == "interactive":
        details = []
        for _ in range(32):
            details.append(bench.interactive(guest.connection, "printf PTY", "PTY"))
        return [row["first_byte_ms"] for row in details], 0, {"samples": details, "agent_poll_ms": 50}
    if name == "idle":
        time.sleep(60)
        return [60000], 0, {"silence_seconds": 60, "agent_connected": True, "agent_poll_ms": 50,
                           "native_readers_blocking": True, "host_heartbeat": False}
    if name == "concurrent":
        results, errors = {}, []
        def execute(key):
            try:
                results[key] = workload(guest, tcp, key)
            except Exception as error:
                errors.append(f"{key}: {error}")
        workers = [threading.Thread(target=execute, args=(key,)) for key in ("tap-65536", "vsock-65536")]
        for worker in workers:
            worker.start()
        results["disk-flush-4096"] = workload(guest, tcp, "disk-flush-4096")
        results["interactive"] = workload(guest, tcp, "interactive")
        for worker in workers:
            worker.join(timeout=30)
        if errors or any(worker.is_alive() for worker in workers):
            raise RuntimeError(f"concurrent workload failed: {errors}")
        return results["interactive"][0], sum(row[1] for row in results.values()), {
            key: {"latency_ms": row[0], "verified": row[2]} for key, row in results.items()}
    if name == "lifecycle":
        values = []
        for _ in range(20):
            started = time.monotonic()
            guest.api("PATCH", "/vm", {"state": "Paused"})
            values.append((time.monotonic() - started) * 1000)
            guest.api("PATCH", "/vm", {"state": "Resumed"})
            bench.native_echo(guest.native_connection, 500, 64)
        return values, 0, {"pause_resume_transitions": 20}
    raise ValueError(f"unknown workload {name}")


WORKLOADS = ["disk-read-4096", "disk-write-4096", "disk-flush-4096", "disk-read-1048576",
             "disk-write-1048576", "tap-64", "tap-1400", "tap-65536", "vsock-64",
             "vsock-4096", "vsock-65536", "slow-reader", "exec", "interactive", "concurrent",
             "idle", "lifecycle"]


def child(args):
    if os.geteuid() == 0:
        raise RuntimeError("nonroot controller required")
    out = bench.artifact_path(args.out)
    os.sched_setaffinity(0, {1})
    result = {"status": "failed", "errors": [], "mode": args.mode, "rows": [],
              "performance_merge_eligible": False, "classification": "C00 A/A" if args.mode == "C00" else "gated exploratory candidate; not automatic adoption"}
    guest, tcp, observer = None, None, None
    try:
        binary, fixture = bench.artifact_path(args.binary), bench.artifact_path(args.fixture)
        bench.save_json(out / "manifest.json", {
            "binary_sha256": bench.digest(binary), "fixture": json.loads((fixture / "fixture.json").read_text()),
            "mode": args.mode, "cpus": [8], "client_cpus": [1], "vcpus": 1, "ram_mib": 512,
            "host_kernel": os.uname().release, "host_arch": os.uname().machine,
            "host_provenance": "W0-verified nested Microsoft/Azure vm31e Standard_D16ds_v5 Xeon8370C 16logical/8core/SMT2",
            "non_nested_host": "unavailable; optional comparison not executed",
            "pmu": "W0 root and user cycles/instructions unsupported; software/KVM trace fallback",
            "guest_pmu": "hidden by unchanged normalizeCpuid",
            "compiler": "Zig0.17 static x86_64-linux-musl ReleaseSafe; immutable binary hash is authoritative",
            "backends": "synchronous block, userspace TAP, native guest-initiated vsock; no async/vhost",
            "storage": "fresh16MiB raw0xA5 disk; guest O_DIRECT QD1, host buffered pread/pwrite+fdatasync; no global cache manipulation",
            "network": "private namespace,192.0.2.0/30,MTU1500,offloads0,no uplink/NAT",
            "warmup": "checked agent/PTY plus64B TCP/vsock then1s silence",
            "samples": "five10s primary windows" if args.long_primary else "17 sustained workload cells; every count in result",
            "minimum_nonidle_seconds": args.minimum_seconds,
            "cpu_accounting": "sum of owned task schedstat execution nanoseconds; ticks retained; generation/roster checked",
            "agent_poll_ms": 50, "heartbeat_ms": 0, "disk_seed": "0x31415926 LCG, raw offsets1MiB..9MiB",
            "runner_sha256": bench.digest(Path(__file__)), "control_sha256": bench.digest(Path(control.__file__)),
            "observer_sha256": bench.digest(bench.ROOT / "tools/perf/irqfd_cpu.py"),
            "observer_object_sha256": bench.digest(bench.ROOT / ".perf/eventfd/w2/irqfd_cpu.bpf.o"),
            "source_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=bench.ROOT, capture_output=True, check=True).stdout.decode().strip(),
            "source_files_sha256": {str(path.relative_to(bench.ROOT)): bench.digest(path) for path in (bench.ROOT / "vmm/src").rglob("*.zig")},
            "started_unix": time.time(), "long_primary": args.long_primary,
            "accounting": "all live VMM task CPU plus exact owned irqfd-work CPU; client separate; BPF observer overhead conservatively retained",
        })
        if args.mode != "C00":
            gates = json.loads(bench.artifact_path(args.gates).read_text())
            if gates["binary_sha256"] != bench.digest(binary) or gates["fixture_sha256"] != bench.digest(fixture / "fixture.json"):
                raise ValueError("gates/source fixtures changed")
            if gates["status"] != "noise-provisionally-acceptable":
                raise ValueError("fresh C00 A/A noise gates have not passed")
            manifest = json.loads((out / "manifest.json").read_text())
            if any(manifest.get(key) != value for key, value in gates["baseline_conditions"].items()):
                raise ValueError("candidate conditions differ from frozen current baseline")
            result["frozen_gates_sha256"] = bench.digest(bench.artifact_path(args.gates))
        started = time.monotonic()
        guest = control.Guest.__new__(control.Guest)
        guest.__init__(out, binary, args.mode, fixture, disk=True, tap="hef3tap0")
        result["boot_guest_connect_ms"] = (time.monotonic() - started) * 1000
        tcp = socket.create_connection(("192.0.2.2", 11000), timeout=8)
        tcp.settimeout(10)
        observer = matrix.Observer(guest)
        control.agent(guest, False)
        for connection in (tcp, guest.native_connection):
            bench.native_echo(connection, 600, 64)
        time.sleep(1)
        for name in (["disk-flush-4096"] * 5 if args.long_primary else WORKLOADS):
            time.sleep(.1)
            old_kernel = observer.read()
            before = bench.thread_roster(guest.pid)
            host_before = Path("/proc/stat").read_text()
            client_before = time.process_time()
            started = time.monotonic()
            latency, byte_count, checked = workload(guest, tcp, name)
            minimum = 10 if args.long_primary else args.minimum_seconds
            batches = 1
            if name != "idle":
                while time.monotonic() - started < minimum:
                    more, size, _ = workload(guest, tcp, name)
                    latency.extend(more)
                    byte_count += size
                    batches += 1
            checked["verified_batches"] = batches
            checked["window_minimum_seconds"] = minimum
            operation_seconds = time.monotonic() - started
            time.sleep(.1)
            seconds = time.monotonic() - started
            after = bench.thread_roster(guest.pid)
            new_kernel = observer.read()
            vm_cpu = bench.cpu_delta(before, after)
            kernel_cpu = new_kernel["kernel_irqfd_cpu_seconds"] - old_kernel["kernel_irqfd_cpu_seconds"]
            count = len(latency)
            row = {"name": name, "status": "passed", "latency_ms": latency, "latency": summary(latency),
                   "operations": count, "bytes": byte_count, "seconds_including_100ms_tail": seconds,
                   "operation_seconds": operation_seconds,
                   "owned_all_task_cpu_seconds": vm_cpu, "owned_irqfd_kernel_work_cpu_seconds": kernel_cpu,
                   "total_backend_cpu_seconds": vm_cpu + kernel_cpu, "cpu_per_operation": (vm_cpu + kernel_cpu) / count,
                   "client_cpu_seconds": time.process_time() - client_before,
                   "bytes_per_second": byte_count / operation_seconds, "threads_before": before, "threads_after": after,
                   "kernel_work_before": old_kernel, "kernel_work_after": new_kernel, "integrity": checked,
                   "host_noise": bench.host_cpu_delta(host_before, Path("/proc/stat").read_text(), seconds)}
            if name == "idle":
                wake = {}
                for kind, connection in (("vsock", guest.native_connection), ("tap", tcp)):
                    wake_started = time.monotonic()
                    bench.native_echo(connection, 700, 64)
                    wake[kind] = (time.monotonic() - wake_started) * 1000
                    if wake[kind] > 1000:
                        raise RuntimeError("timer-free idle wake exceeded one second")
                row["idle_wake_ms_outside_cpu_window"] = wake
            result["rows"].append(row)
            bench.save_json(out / "result.json", result)
        checksum = matrix.rpc_exec(guest, "/bin/busybox sha256sum /dev/vda", 20).decode().split()[0]
        if checksum != bench.digest(guest.path / "disk"):
            raise ValueError("whole guest disk read checksum differs from real host backing")
        result["guest_host_whole_disk_sha256"] = checksum
        result["shutdown_exit_code"] = guest.shutdown()
        result["final_kernel_work"] = observer.finish()
        observer = None
        result["status"] = "passed"
    except (OSError, ValueError, RuntimeError, EOFError, subprocess.SubprocessError) as error:
        result["errors"].append(f"{type(error).__name__}: {error}")
    finally:
        if observer is not None:
            try:
                result["failed_window_kernel_work"] = observer.finish()
            except Exception as error:
                result["errors"].append(f"observer cleanup: {error}")
        if tcp is not None:
            tcp.close()
        if guest is not None:
            guest.close()
    bench.save_json(out / "result.json", result)
    print(json.dumps({"mode": args.mode, "status": result["status"], "rows": len(result["rows"]), "errors": result["errors"]}))
    return 0 if result["status"] == "passed" else 1


def freeze(args):
    source = bench.artifact_path(args.baselines)
    paths = sorted(source.glob("aa-*/result.json"))
    samples = [json.loads(path.read_text()) for path in paths]
    if len(samples) < 5 or any(sample["status"] != "passed" or sample["mode"] != "C00" for sample in samples):
        raise ValueError("at least five actually passing untouched functioning-control repetitions required")
    manifests = [json.loads(path.with_name("manifest.json").read_text()) for path in paths]
    expected_binary = bench.digest(bench.artifact_path(args.binary))
    expected_fixture = json.loads((bench.artifact_path(args.fixture) / "fixture.json").read_text())
    conditions = ("minimum_nonidle_seconds", "cpu_accounting", "runner_sha256",
                  "control_sha256", "observer_sha256", "observer_object_sha256",
                  "source_files_sha256", "cpus", "client_cpus", "vcpus", "ram_mib")
    if any(manifest["binary_sha256"] != expected_binary or manifest["fixture"] != expected_fixture
           or any(manifest.get(key) != manifests[0].get(key) for key in conditions)
           for manifest in manifests):
        raise ValueError("baseline conditions changed; do not freeze mixed A/A")
    if any(manifest.get("minimum_nonidle_seconds", 0) < 5 or not manifest.get("cpu_accounting")
           for manifest in manifests):
        raise ValueError("fresh sustained nanosecond-accounted baselines required")
    noise = {}
    for name in WORKLOADS:
        rows = [next(row for row in sample["rows"] if row["name"] == name) for sample in samples]
        noise[name] = {
            "cpu_per_operation": summary([row["cpu_per_operation"] for row in rows]),
            "p95_ms": summary([row["latency"]["p95"] for row in rows]),
            "throughput": summary([row["bytes_per_second"] for row in rows]) if rows[0]["bytes"] else None,
        }
    exceeds = [name for name, value in noise.items() if name != "idle" and
               (value["cpu_per_operation"]["cv"] > .1 or value["p95_ms"]["cv"] > .1 or
                (value["throughput"] and value["throughput"]["cv"] > .05))]
    result = {
        "status": "noise-inconclusive" if exceeds else "noise-provisionally-acceptable",
        "frozen_unix": time.time(), "candidate_performance_observed": False,
        "binary_sha256": bench.digest(bench.artifact_path(args.binary)),
        "fixture_sha256": bench.digest(bench.artifact_path(args.fixture) / "fixture.json"),
        "baseline_result_sha256": {str(path.relative_to(bench.ROOT)): bench.digest(path) for path in sorted(source.glob("aa-*/result.json"))},
        "primary": "disk-flush-4096", "samples": len(samples), "noise": noise, "exceeds_noise_caps": exceeds,
        "baseline_conditions": {key: manifests[0][key] for key in conditions},
        "candidate_order": [["C10", "C01", "C11"], ["C01", "C11", "C10"], ["C11", "C10", "C01"],
                            ["C01", "C10", "C11"], ["C11", "C01", "C10"]],
        "gates": {"benefit_percent": 10, "paired_confidence": .95, "mechanism_reduction_percent": 90,
                  "max_throughput_regression_percent": 3, "max_cpu_latency_lifecycle_regression_percent": 5,
                  "max_noise_cpu_latency_cv_percent": 10, "max_noise_throughput_cv_percent": 5,
                  "idle_extra_core_percentage_points_per_sandbox": .1},
        "unfulfilled_qualification": ["100 reset transitions", "20 active cross-mode snapshots per mode/device mix",
                                     "10 failure-teardown cycles", "4/8-sandbox active+idle", "64-connection credit stress",
                                     "CLI/API save-on-halt and old/new cross-mode lifecycle", "full mechanism profiles"],
        "decision": "no adoption while noise or any mandatory correctness/performance coverage is incomplete",
    }
    out = bench.artifact_path(args.out)
    if out.exists():
        raise ValueError("refusing to overwrite frozen gates")
    bench.save_json(out, result)
    print(json.dumps({"status": result["status"], "exceeds_noise_caps": exceeds}))


def namespace(args):
    tap_probe.require_private_namespace()
    uid, gid = int(os.environ["SUDO_UID"]), int(os.environ["SUDO_GID"])
    out = bench.artifact_path(args.out)
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chown(out, uid, gid)
    tap_probe.setup_tap(uid)
    def demote():
        os.setgroups([])
        os.setgid(gid)
        os.setuid(uid)
    argv = [sys.executable, str(Path(__file__)), "--child", "--out", str(out),
            "--binary", args.binary, "--fixture", args.fixture, "--mode", args.mode]
    if args.gates:
        argv += ["--gates", args.gates]
    if args.long_primary:
        argv += ["--long-primary"]
    argv += ["--minimum-seconds", str(args.minimum_seconds)]
    child_process = subprocess.Popen(argv, cwd=bench.ROOT, preexec_fn=demote)
    try:
        return child_process.wait(timeout=330)
    except BaseException:
        child_process.send_signal(signal.SIGTERM)
        try:
            child_process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            child_process.kill()
            child_process.wait(timeout=5)
        raise


def main():
    os.umask(0o077)
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(RuntimeError("bounded performance phase interrupted")))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--binary", required=True)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--mode", choices=["C00", "C10", "C01", "C11"], default="C00")
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--baselines")
    parser.add_argument("--gates")
    parser.add_argument("--long-primary", action="store_true")
    parser.add_argument("--minimum-seconds", type=bench.positive_float, default=5)
    args = parser.parse_args()
    if args.freeze:
        freeze(args)
        return 0
    if args.mode != "C00" and not args.gates:
        parser.error("candidate performance requires previously frozen C00 gates")
    return child(args) if args.child else namespace(args)


if __name__ == "__main__":
    raise SystemExit(main())
