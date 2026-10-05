#!/usr/bin/env python3
"""Owned-task C00/candidate software profiles, separate from unprofiled gates."""

import argparse
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import time

import control
import matrix
import performance
import run as bench


def main():
    os.umask(0o077)
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(RuntimeError("bounded profile interrupted")))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--binary", required=True)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--mode", choices=["C00", "C10", "C01", "C11"], default="C00")
    parser.add_argument("--profile", choices=["stat", "stacks", "trace"], required=True)
    parser.add_argument("--gates")
    parser.add_argument("--buffer-pages", type=int)
    args = parser.parse_args()
    if args.mode != "C00":
        if not args.gates:
            parser.error("candidate profiles require frozen gates")
        gates = json.loads(bench.artifact_path(args.gates).read_text())
        if gates["binary_sha256"] != bench.digest(bench.artifact_path(args.binary)):
            raise ValueError("candidate binary differs from frozen common control")
    out = bench.artifact_path(args.out)
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.sched_setaffinity(0, {1})
    guest, collector, handle, observer = None, None, None, None
    result = {"status": "failed", "errors": [], "mode": args.mode, "profile": args.profile,
              "classification": "profiled mechanism attribution, never latency/benefit gates",
              "performance_merge_eligible": False}
    try:
        guest = control.Guest.__new__(control.Guest)
        guest.__init__(out, bench.artifact_path(args.binary), args.mode, bench.artifact_path(args.fixture), disk=True)
        # Agent fixture needs no TAP; native combined fixtures use private
        # namespace runners instead. These disk/exec profiles retain exact
        # synchronous backend semantics and real direct readback verification.
        observer = matrix.Observer(guest)
        matrix.rpc_exec(guest, "/disk-probe flush 4096 16", 15)
        collector, handle = bench.perf_collect(guest.pid, out, args.profile, 12, True, [
            "kvm:kvm_userspace_exit", "kvm:kvm_mmio", "kvm:kvm_set_irq",
            "syscalls:sys_enter_read", "syscalls:sys_exit_read",
            "syscalls:sys_enter_write", "syscalls:sys_exit_write",
            "syscalls:sys_enter_epoll_pwait", "syscalls:sys_exit_epoll_pwait",
            "sched:sched_switch",
        ], args.buffer_pages)
        time.sleep(.3)
        started = time.monotonic()
        operations = 0
        while time.monotonic() - started < 12:
            value = json.loads(matrix.rpc_exec(guest, "/disk-probe flush 4096 128", 20))
            if value["operations"] != 128:
                raise ValueError("profile workload count changed")
            operations += 128
        result["operations"] = operations
        result["perf_exit_code"] = collector.wait(timeout=15)
        handle.close()
        collector, handle = None, None
        if result["perf_exit_code"] != 0:
            raise RuntimeError("actual scoped perf collection failed")
        if args.profile == "stacks":
            report = bench.command(["sudo", "-n", "env", f"PERF_BUILDID_DIR={bench.ROOT / '.perf/eventfd/perf-buildids'}",
                                    "perf", "report", "-f", "--stdio", "-i", str(out / "cpu.data")], out, "cpu-report")
            if report["returncode"] != 0:
                raise RuntimeError("owned stack report failed")
        if args.profile == "trace":
            decoded = bench.command(["sudo", "-n", "env", f"PERF_BUILDID_DIR={bench.ROOT / '.perf/eventfd/perf-buildids'}",
                                     "perf", "script", "-f", "-i", str(out / "kvm-ioctl.data")], out, "kvm-ioctl")
            if decoded["returncode"] != 0:
                raise RuntimeError("owned trace decode failed")
            attribution = bench.command([
                sys.executable, str(bench.ROOT / "benchmarks/virtio-eventfd/analyze_trace.py"),
                "--run", str(out), "--out", str(out / "attribution.json")], out, "attribution")
            if attribution["returncode"] != 0:
                raise RuntimeError("owned mechanism attribution failed")
            result["trace_loss_detected"] = bool(re.search(
                r"lost [1-9][0-9]* chunks", (out / "perf.stderr").read_text()))
            if result["trace_loss_detected"]:
                result["errors"].append("trace event loss: counters are diagnostic, not qualifying attribution")
        result["shutdown_exit_code"] = guest.shutdown()
        result["kernel_work"] = observer.finish()
        observer = None
        result["status"] = "passed" if not result["errors"] else "failed"
    except (OSError, ValueError, RuntimeError, EOFError, subprocess.SubprocessError) as error:
        result["errors"].append(f"{type(error).__name__}: {error}")
    finally:
        if collector is not None:
            collector.wait(timeout=20)
        if handle is not None:
            handle.close()
        if observer is not None:
            try:
                result["failed_window_kernel_work"] = observer.finish()
            except Exception as error:
                result["errors"].append(f"observer: {error}")
        if guest is not None:
            guest.close()
    bench.save_json(out / "result.json", result)
    print(json.dumps(result))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
