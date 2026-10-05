#!/usr/bin/env python3
"""Bounded real-KVM repeated-PTY correctness, never a performance matrix."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import control
import custody
import hosted
import performance
import run as bench


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
        "performance_merge_eligible": False,
    }
    topology = hosted.actual_topology()
    vm_cpu, client_cpu = hosted.independent_cpus(topology)
    result["vm_cpu"], result["client_cpu"] = vm_cpu, client_cpu
    os.sched_setaffinity(0, {client_cpu})
    guest, progress = None, None
    try:
        guest = control.Guest.__new__(control.Guest)
        guest.__init__(out, Path(args.binary), args.mode, Path(args.fixture), disk=True, vm_cpu=vm_cpu)
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
        result["shutdown_exit_code"] = guest.shutdown()
        result["status"] = "passed"
    except (OSError, ValueError, RuntimeError, EOFError, subprocess.SubprocessError) as error:
        result["failure_type"] = type(error).__name__
        result["failure_message_sha256"] = hashlib.sha256(str(error).encode()).hexdigest()
        if progress is not None:
            result["active_workload"] = progress.snapshot()
    finally:
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
    args = parser.parse_args()
    if args.phase == "child":
        return child(args)
    if os.geteuid() != 0:
        raise RuntimeError("owned supervision requires sudo from a nonroot caller")
    uid, gid = int(os.environ["SUDO_UID"]), int(os.environ["SUDO_GID"])
    if uid <= 0 or gid <= 0:
        raise RuntimeError("PTY supervisor must originate from nonroot")
    out = bench.artifact_path(args.out)
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chown(out, uid, gid)

    def demote():
        os.setgroups([])
        os.setgid(gid)
        os.setuid(uid)

    supervisor = custody.Supervisor()
    try:
        code, receipt = supervisor.run([
            sys.executable, str(Path(__file__)), "child", "--out", str(out),
            "--binary", args.binary, "--fixture", args.fixture, "--mode", args.mode,
        ], work_seconds=180, cleanup_seconds=30, cwd=bench.ROOT, preexec_fn=demote)
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
