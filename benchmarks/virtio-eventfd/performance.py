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


def workload(guest, tcp, name, progress=None):
    def point(stage, error_point, operation=0):
        if progress is not None:
            progress(name, stage, error_point, operation)

    latency, bytes_done = [], 0
    point("workload", "begin")
    rpc_progress = ({"progress": lambda stage, error_point: point(stage, error_point)}
                    if progress is not None else {})
    if name.startswith("disk-"):
        _, operation, size = name.split("-")
        block = int(size)
        data = json.loads(matrix.rpc_exec(
            guest, f"/disk-probe {operation} {block} {128 if block == 4096 else 16}", 25,
            **rpc_progress))
        latency = [value / 1e6 for value in data["latency_ns"]]
        bytes_done = data["operations"] * block
        return latency, bytes_done, data
    if name.startswith(("vsock-", "tap-")):
        transport, size = name.split("-")
        connection = guest.native_connection if transport == "vsock" else tcp
        for index in range(128 if int(size) < 65536 else 64):
            point("native-echo", "exchange", index)
            started = time.monotonic()
            bench.native_echo(connection, index, int(size))
            latency.append((time.monotonic() - started) * 1000)
            bytes_done += int(size) * 2
        return latency, bytes_done, {"integrity": "all payloads+FNV+sequence verified", "messages": len(latency)}
    if name == "slow-reader":
        point("native-backpressure", "exchange")
        started = time.monotonic()
        checked = bench.native_backpressure(guest.native_connection, 200, 65536)
        return [(time.monotonic() - started) * 1000], 2 * 8 * 65536, checked
    if name == "exec":
        for index in range(64):
            rpc_progress = ({"progress": lambda stage, error_point: point(stage, error_point, index)}
                            if progress is not None else {})
            started = time.monotonic()
            if matrix.rpc_exec(guest, "printf EXEC", **rpc_progress) != b"EXEC":
                raise ValueError("exec integrity failure")
            latency.append((time.monotonic() - started) * 1000)
        return latency, 0, {"commands": 64, "agent_unchanged": True}
    if name == "interactive":
        details = []
        for index in range(32):
            rpc_progress = ({"progress": lambda stage, error_point: point(stage, error_point, index)}
                            if progress is not None else {})
            details.append(bench.interactive(
                guest.connection, "printf PTY", "PTY", **rpc_progress))
        return [row["first_byte_ms"] for row in details], 0, {"samples": details, "agent_poll_ms": 50}
    if name == "idle":
        point("idle", "wait")
        time.sleep(60)
        return [60000], 0, {"silence_seconds": 60, "agent_connected": True, "agent_poll_ms": 50,
                           "native_readers_blocking": True, "host_heartbeat": False}
    if name == "concurrent":
        results, errors = {}, []
        def execute(key):
            try:
                results[key] = workload(guest, tcp, key, progress)
            except Exception as error:
                errors.append(f"{key}: {error}")
        workers = [threading.Thread(target=execute, args=(key,)) for key in ("tap-65536", "vsock-65536")]
        for worker in workers:
            worker.start()
        results["disk-flush-4096"] = workload(guest, tcp, "disk-flush-4096", progress)
        results["interactive"] = workload(guest, tcp, "interactive", progress)
        for worker in workers:
            worker.join(timeout=30)
        if errors or any(worker.is_alive() for worker in workers):
            raise RuntimeError(f"concurrent workload failed: {errors}")
        return results["interactive"][0], sum(row[1] for row in results.values()), {
            key: {"latency_ms": row[0], "verified": row[2]} for key, row in results.items()}
    if name == "lifecycle":
        values = []
        for index in range(20):
            point("lifecycle", "pause", index)
            started = time.monotonic()
            guest.api("PATCH", "/vm", {"state": "Paused"})
            values.append((time.monotonic() - started) * 1000)
            point("lifecycle", "resume", index)
            guest.api("PATCH", "/vm", {"state": "Resumed"})
            point("lifecycle", "wake", index)
            bench.native_echo(guest.native_connection, 500, 64)
        return values, 0, {"pause_resume_transitions": 20}
    raise ValueError(f"unknown workload {name}")


WORKLOADS = ["disk-read-4096", "disk-write-4096", "disk-flush-4096", "disk-read-1048576",
             "disk-write-1048576", "tap-64", "tap-1400", "tap-65536", "vsock-64",
             "vsock-4096", "vsock-65536", "slow-reader", "exec", "interactive", "concurrent",
             "idle", "lifecycle"]


def execution_identity(manifest):
    if not isinstance(manifest, dict):
        raise ValueError("missing recorded execution provenance: manifest")
    # These are the fixed fields emitted by this runner, not today's build args.
    fields = (
        "binary_sha256", "fixture", "cpus", "client_cpus", "vcpus", "ram_mib",
        "host_kernel", "host_arch", "host_provenance", "non_nested_host", "pmu", "guest_pmu",
        "compiler", "backends", "storage", "network", "warmup", "samples",
        "agent_poll_ms", "heartbeat_ms", "disk_seed", "runner_sha256", "control_sha256",
        "observer_sha256", "observer_object_sha256", "source_commit", "source_files_sha256",
        "long_primary", "accounting", "minimum_nonidle_seconds", "cpu_accounting",
    )
    missing = [field for field in fields if manifest.get(field) in (None, "")]
    if missing:
        raise ValueError(f"missing recorded execution provenance: {', '.join(missing)}")
    minimum = manifest["minimum_nonidle_seconds"]
    if isinstance(minimum, bool) or not isinstance(minimum, (int, float)) or minimum < 5:
        raise ValueError("fresh sustained nanosecond-accounted baselines required")
    identity = {key: value for key, value in manifest.items() if key not in (
        "mode", "started_unix", "argv", "cwd", "out", "pid", "connected_marker_seconds_since_launch",
    )}
    if any(not isinstance(identity[field], list) or not identity[field] for field in ("cpus", "client_cpus")):
        raise ValueError("missing recorded execution provenance: CPU affinity")
    fixture = identity["fixture"]
    if not isinstance(fixture, dict) or any(
        fixture.get(field) in (None, "") for field in (
            "kernel_sha256", "initrd_sha256", "init_sha256", "disk_script_sha256",
            "sources_sha256", "diagnostic_heartbeat_ms", "guest_agent_interactive_poll_ms",
            "native_probe", "combined", "transport", "unsupported",
        )
    ):
        raise ValueError("missing recorded fixture provenance")
    for hashes in (identity["source_files_sha256"], fixture["sources_sha256"]):
        if not isinstance(hashes, dict) or not hashes or any(not value for value in hashes.values()):
            raise ValueError("missing recorded source/fixture hashes")
    # A relocated pinned kernel is the same fixture; timestamps, mode and run
    # paths likewise do not enter fixed execution identity.
    identity["fixture"] = {key: value for key, value in fixture.items() if key != "kernel"}
    return identity


def fixture_identity_sha256(identity):
    return hashlib.sha256(json.dumps(identity["fixture"], sort_keys=True).encode()).hexdigest()


def verify_artifacts(identity, binary, fixture):
    if bench.digest(binary) != identity["binary_sha256"]:
        raise ValueError("supplied binary differs from recorded execution")
    metadata = json.loads((fixture / "fixture.json").read_text())
    if not isinstance(metadata, dict) or not metadata.get("kernel"):
        raise ValueError("supplied fixture lacks its kernel artifact path")
    if {key: value for key, value in metadata.items() if key != "kernel"} != identity["fixture"]:
        raise ValueError("supplied fixture differs from recorded execution")
    if (bench.digest(fixture / "initrd.cpio.gz") != identity["fixture"]["initrd_sha256"]
            or bench.digest(bench.artifact_path(metadata["kernel"])) != identity["fixture"]["kernel_sha256"]):
        raise ValueError("supplied fixture artifacts changed")


def validate_candidate_gates(gates, manifest, binary, fixture):
    frozen = gates.get("execution_identity")
    if not isinstance(frozen, dict):
        raise ValueError("frozen gates lack recorded execution provenance; historical gates are unqualified")
    if gates.get("status") != "noise-provisionally-acceptable":
        raise ValueError("fresh C00 A/A noise gates have not passed")
    frozen = execution_identity(frozen)
    if (gates.get("binary_sha256") != frozen["binary_sha256"]
            or gates.get("fixture_sha256") != fixture_identity_sha256(frozen)):
        raise ValueError("frozen gate artifact identity is inconsistent")
    current = execution_identity(manifest)
    verify_artifacts(current, binary, fixture)
    if current != frozen:
        raise ValueError("candidate differs from frozen recorded execution conditions")


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
        manifest = {
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
        }
        bench.save_json(out / "manifest.json", manifest)
        if args.mode != "C00":
            gates = json.loads(bench.artifact_path(args.gates).read_text())
            validate_candidate_gates(gates, manifest, binary, fixture)
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
    identities = []
    manifests = [path.with_name("manifest.json") for path in paths]
    for path in manifests:
        if not path.is_file():
            raise ValueError(f"missing recorded control manifest: {path.relative_to(bench.ROOT)}")
        manifest = json.loads(path.read_text())
        if manifest.get("mode") != "C00":
            raise ValueError("recorded control manifest is not C00")
        identities.append(execution_identity(manifest))
    identity = identities[0]
    if any(recorded != identity for recorded in identities[1:]):
        raise ValueError("mixed recorded control execution conditions")
    verify_artifacts(identity, bench.artifact_path(args.binary), bench.artifact_path(args.fixture))
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
        "binary_sha256": identity["binary_sha256"],
        "fixture_sha256": fixture_identity_sha256(identity),
        "execution_identity": identity,
        "baseline_manifest_sha256": {str(path.relative_to(bench.ROOT)): bench.digest(path) for path in manifests},
        "baseline_result_sha256": {str(path.relative_to(bench.ROOT)): bench.digest(path) for path in paths},
        "primary": "disk-flush-4096", "samples": len(samples), "noise": noise, "exceeds_noise_caps": exceeds,
        "baseline_conditions": {key: identity[key] for key in (
            "minimum_nonidle_seconds", "cpu_accounting", "runner_sha256",
            "control_sha256", "observer_sha256", "observer_object_sha256",
            "source_files_sha256", "cpus", "client_cpus", "vcpus", "ram_mib")},
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
