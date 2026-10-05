#!/usr/bin/env python3
"""Bounded real-KVM repeated-PTY correctness, never a performance matrix."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys

import control
import custody
import hosted
import matrix
import performance
import run as bench
import tap_probe


def child(args):
    if os.geteuid() == 0:
        raise RuntimeError("PTY backend/controller must run nonroot")
    out = bench.artifact_path(args.out)
    result = {
        "status": "failed", "mode": args.mode, "heartbeat_ms": 0,
        "classification": "targeted actual PTY correctness, not qualification",
        "source": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "binary_sha256": bench.digest(args.binary),
        "fixture": json.loads((Path(args.fixture) / "fixture.json").read_text()),
        "exec_completed": 0, "slow_reader_completed": 0, "pty_completed": 0,
        "prelude_completed": [], "closed_pty_completed": 0,
        "devices": "synchronous block+userspace TAP+vsock" if args.all_devices else "synchronous block+vsock; no TAP",
        "operation_accounting": "completed validated whole batches; failed-batch partial operations not counted",
        "performance_merge_eligible": False,
    }
    topology = hosted.actual_topology()
    vm_cpu, client_cpu = hosted.independent_cpus(topology)
    result["vm_cpu"], result["client_cpu"] = vm_cpu, client_cpu
    os.sched_setaffinity(0, {client_cpu})
    guest, tcp, progress = None, None, None
    try:
        guest = control.Guest.__new__(control.Guest)
        guest.__init__(out, Path(args.binary), args.mode, Path(args.fixture), disk=True,
                       tap="hef3tap0" if args.all_devices else None, vm_cpu=vm_cpu)
        if args.all_devices:
            tcp = socket.create_connection(("192.0.2.2", 11000), timeout=8)
            tcp.settimeout(10)
            for name in performance.WORKLOADS[:11]:
                performance.workload(guest, tcp, name)
                result["prelude_completed"].append(name)
        for _ in range(124):
            performance.workload(guest, None, "exec")
            result["exec_completed"] += 64
        for _ in range(15):
            performance.workload(guest, None, "slow-reader")
            result["slow_reader_completed"] += 1
        progress = hosted.WorkloadProgress("interactive")
        for batch in range(128):
            progress.batch = batch
            performance.workload(guest, None, "interactive", progress.point)
            result["pty_completed"] += 32
        if args.closed_pty:
            result["phase"] = "closed-pty-completion"
            progress = hosted.WorkloadProgress("interactive")
            for operation in range(4):
                bench.interactive(
                    guest.connection, "printf PTY; exec 0<&- 1>&- 2>&-; /bin/busybox sleep 0.1", "PTY",
                    lambda stage, point: progress.point("interactive", stage, point, operation))
                result["closed_pty_completed"] += 1
            result["phase"] = "post-closed-pty-connection"
            if matrix.rpc_exec(guest, "printf EXEC") != b"EXEC":
                raise ValueError("post-PTY original connection exec integrity failed")
            result["post_closed_pty_exec_verified"] = True
        result["shutdown_exit_code"] = guest.shutdown()
        result["status"] = "passed"
    except (OSError, ValueError, RuntimeError, EOFError, subprocess.SubprocessError) as error:
        result["failure_type"] = type(error).__name__
        result["failure_message_sha256"] = hashlib.sha256(str(error).encode()).hexdigest()
        if progress is not None:
            result["active_workload"] = progress.snapshot()
        (out / "failure.private.txt").write_text(str(error))
    finally:
        if tcp is not None:
            tcp.close()
        if guest is not None:
            try:
                guest.close()
            except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                result["cleanup_failed"] = True
                result["cleanup_error_type"] = type(error).__name__
                result["status"] = "failed"
        serial = (out / "serial.txt").read_text(errors="replace") if (out / "serial.txt").exists() else ""
        backend = (out / "vmm.stderr").read_text(errors="replace") if (out / "vmm.stderr").exists() else ""
        result["agent_connected_markers"] = serial.count("hearth-agent: connected to host\n")
        result["control_connection_requests"] = len(re.findall(
            r"vsock connect: guest_port=\d+ -> host_port=1024\b", backend))
        bench.save_json(out / "result.json", result)
    return 0 if result["status"] == "passed" else 1


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("supervise", "child"))
    parser.add_argument("--out", required=True)
    parser.add_argument("--binary", required=True)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--mode", choices=("L0", "C00"), required=True)
    parser.add_argument("--all-devices", action="store_true")
    parser.add_argument("--closed-pty", action="store_true")
    args = parser.parse_args()
    if args.phase == "child":
        return child(args)
    if os.geteuid() != 0:
        raise RuntimeError("owned supervision requires sudo from a nonroot caller")
    uid, gid = int(os.environ["SUDO_UID"]), int(os.environ["SUDO_GID"])
    if uid <= 0 or gid <= 0:
        raise RuntimeError("PTY supervisor must originate from nonroot")
    if args.all_devices:
        tap_probe.require_private_namespace()
        tap_probe.setup_tap(uid)
    out = bench.artifact_path(args.out)
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chown(out, uid, gid)

    def demote():
        os.setgroups([])
        os.setgid(gid)
        os.setuid(uid)

    supervisor = custody.Supervisor()
    try:
        argv = [
            sys.executable, str(Path(__file__)), "child", "--out", str(out),
            "--binary", args.binary, "--fixture", args.fixture, "--mode", args.mode,
        ]
        if args.all_devices:
            argv.append("--all-devices")
        if args.closed_pty:
            argv.append("--closed-pty")
        code, receipt = supervisor.run(
            argv, work_seconds=180, cleanup_seconds=30, cwd=bench.ROOT, preexec_fn=demote)
        bench.save_json(out / "custody.json", receipt)
        os.chown(out / "custody.json", uid, gid)
        result = json.loads((out / "result.json").read_text()) if (out / "result.json").exists() else {
            "status": "failed", "failure_type": "NoControllerReceipt",
        }
        result["supervision"] = {key: receipt[key] for key in (
            "status", "controller_returncode", "termination_reason", "cleanup_seconds",
            "surviving_generations", "cleanup_errors", "unsafe_registrations")}
        if code or receipt["status"] != "passed":
            result["status"] = "failed"
        public = out.parent / f"pty-proof-{args.mode}.json"
        bench.save_json(public, result)
        os.chown(public, uid, gid)
        print(json.dumps(result))
        return code or (0 if result["status"] == "passed" else 1)
    finally:
        supervisor.close()


if __name__ == "__main__":
    raise SystemExit(main())
