#!/usr/bin/env python3
"""Enforced 4/8-sandbox mixed-device correctness, never performance gates."""

import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time

import control
import matrix
import run as bench
import tap_probe


def interrupted(*_):
    raise RuntimeError("bounded owned mixed-scale phase interrupted")


class Backlogged(matrix.Outstanding):
    def __init__(self, connection):
        self.connection = connection
        self.payloads = [bench.native_payload(index, 65536) for index in range(128)]
        self.errors = []
        self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 16384)
        self.writer = threading.Thread(target=self.send)
        self.writer.start()


def worker(args):
    if os.geteuid() == 0:
        raise ValueError("traffic worker must be nonroot")
    out, phase = bench.artifact_path(args.out), bench.artifact_path(args.phase)
    bench.save_json(out / "worker.json", {
        "pid": os.getpid(), "start_ticks": control.support.start_ticks(os.getpid()),
        "namespace": os.readlink("/proc/self/ns/net"),
    })
    result = {"status": "failed", "errors": [], "mode": args.mode,
              "classification": "mixed-scale integrity; not performance or true idle",
              "agent_poll_ms": 50, "heartbeat_ms": 0, "performance_merge_eligible": False}
    guest, tcp, producers = None, None, []
    try:
        guest = control.Guest.__new__(control.Guest)
        guest.__init__(out, bench.artifact_path(args.binary), args.mode,
                       bench.artifact_path(args.fixture), disk=True, tap="hef3tap0")
        tcp = socket.create_connection(("192.0.2.2", 11000), timeout=10)
        tcp.settimeout(120)
        guest.native_connection.settimeout(120)
        result["initial_agent"] = control.agent(guest, True)
        if matrix.rpc_exec(guest, "/bin/busybox touch /bench/run-disk; /bin/sh /disk-load >/dev/null 2>&1 & printf STARTED") != b"STARTED":
            raise RuntimeError("disk fixture did not start")
        deadline = time.monotonic() + 10
        with (guest.path / "disk").open("rb", buffering=0) as disk:
            while True:
                disk.seek(8192)
                if disk.read(6) == b"ACTIVE":
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError("no actual disk completion before barrier")
                time.sleep(.001)
        producers = [Backlogged(guest.native_connection), Backlogged(tcp)]
        for producer in producers:
            producer.barrier()
        bench.save_json(out / "ready.json", {
            "guest_pid": guest.pid, "guest_start_ticks": guest.pid_start_ticks,
            "outstanding_sources": ["synchronous-block", "userspace-TAP", "native-vsock"],
            "ready_monotonic": time.monotonic(),
        })
        deadline = time.monotonic() + 100
        while not (phase / "go").exists():
            if (phase / "abort").exists() or time.monotonic() > deadline:
                raise RuntimeError("shared mixed-scale barrier aborted or expired")
            time.sleep(.02)
        for producer in producers:
            producer.barrier()
        result["release_monotonic"] = time.monotonic()
        result["loaded_exec"] = matrix.rpc_exec(guest, "printf MIXED-EXEC").decode()
        if result["loaded_exec"] != "MIXED-EXEC":
            raise ValueError("loaded exec integrity")
        result["loaded_interactive"] = bench.interactive(guest.connection, "printf MIXED-PTY", "MIXED-PTY")
        result["vsock"] = producers[0].finish()
        result["tap"] = producers[1].finish()
        if matrix.rpc_exec(guest, "/bin/busybox rm /bench/run-disk; while [ ! -f /bench/disk-done ]; do /bin/busybox sleep 0.01; done; /bin/busybox cat /bench/disk-done", 25) != b"DISK-DONE":
            raise RuntimeError("disk fixture did not finish")
        guest.api("PATCH", "/vm", {"state": "Paused"})
        if json.loads(guest.api("GET", "/vm"))["state"] != "Paused":
            raise ValueError("pause not acknowledged")
        before = bench.thread_roster(guest.pid)
        time.sleep(.2)
        result["paused_all_task_cpu_seconds"] = bench.cpu_delta(before, bench.thread_roster(guest.pid))
        if result["paused_all_task_cpu_seconds"] != 0:
            raise RuntimeError("backend execution during acknowledged pause")
        guest.api("PATCH", "/vm", {"state": "Resumed"})
        result["resume_vsock"] = bench.native_echo(guest.native_connection, 500, 64)
        result["resume_tap"] = bench.native_echo(tcp, 500, 64)
        checksum = matrix.rpc_exec(guest, "/bin/busybox sha256sum /dev/vda", 25).decode().split()[0]
        if checksum != bench.digest(guest.path / "disk"):
            raise ValueError("guest/host whole-disk checksum mismatch")
        with (guest.path / "disk").open("rb") as disk:
            disk.seek(65536)
            if disk.read(14 * 1024 * 1024) != bytes(14 * 1024 * 1024):
                raise ValueError("disk load payload mismatch")
        result["whole_disk_sha256"] = checksum
        result["shutdown_exit_code"] = guest.shutdown()
        result["status"] = "passed"
    except (OSError, ValueError, RuntimeError, EOFError, subprocess.SubprocessError) as error:
        result["errors"].append(f"{type(error).__name__}: {error}")
    finally:
        for producer in producers:
            producer.close()
        if tcp is not None:
            tcp.close()
        if guest is not None:
            guest.close()
        bench.save_json(out / "result.json", result)
    return 0 if result["status"] == "passed" else 1


def namespace(args):
    tap_probe.require_private_namespace()
    if (args.uid, args.gid) != (int(os.environ.get("SUDO_UID", "0")), int(os.environ.get("SUDO_GID", "0"))):
        raise ValueError("UID/GID must match invoking nonroot sudo account")
    receipt = bench.artifact_path(args.out) / "namespace-supervisor.json"
    bench.save_json(receipt, {
        "pid": os.getpid(), "start_ticks": control.support.start_ticks(os.getpid()),
        "namespace": os.readlink("/proc/self/ns/net"),
    })
    os.chown(receipt, args.uid, args.gid)
    tap_probe.setup_tap(args.uid)

    def demote():
        os.setgroups([])
        os.setgid(args.gid)
        os.setuid(args.uid)
        os.sched_setaffinity(0, {1})

    argv = [sys.executable, str(Path(__file__)), "--worker",
            "--out", args.out, "--phase", args.phase, "--binary", args.binary,
            "--fixture", args.fixture, "--mode", args.mode]
    process = subprocess.Popen(argv, cwd=bench.ROOT, preexec_fn=demote)
    try:
        return process.wait(timeout=220)
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def launch(args):
    if os.geteuid() == 0:
        raise ValueError("orchestrator must be nonroot")
    out = bench.artifact_path(args.out)
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    result = {"status": "failed", "errors": [], "count": args.count, "mode": args.mode,
              "classification": "mixed-device correctness; fixed shared VMM CPU8, controller CPU1",
              "runner_sha256": bench.digest(Path(__file__)),
              "binary_sha256": bench.digest(bench.artifact_path(args.binary)),
              "fixture": json.loads((bench.artifact_path(args.fixture) / "fixture.json").read_text()),
              "performance_merge_eligible": False}
    processes, handles = [], []
    try:
        for index in range(args.count):
            directory = out / f"g{index}"
            directory.mkdir(mode=0o700)
            handle = (directory / "supervisor.log").open("wb")
            handles.append(handle)
            argv = ["sudo", "-n", "unshare", "--net", sys.executable, str(Path(__file__)),
                    "--namespace", "--out", str(directory), "--phase", str(out),
                    "--binary", args.binary, "--fixture", args.fixture, "--mode", args.mode,
                    "--uid", str(os.getuid()), "--gid", str(os.getgid())]
            process = subprocess.Popen(argv, cwd=bench.ROOT, stdout=handle, stderr=subprocess.STDOUT)
            processes.append(process)
            bench.save_json(directory / "supervisor.json", {
                "argv": argv, "pid": process.pid, "start_ticks": control.support.start_ticks(process.pid),
            })
            deadline = time.monotonic() + 30
            while not (directory / "ready.json").exists():
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError(f"sandbox {index} failed before common barrier")
                time.sleep(.02)
        result["all_sandboxes_outstanding_at_release"] = args.count
        (out / "go").touch(mode=0o600)
        result["controller_exit_codes"] = [process.wait(timeout=60) for process in processes]
        result["sandboxes"] = [json.loads((out / f"g{i}" / "result.json").read_text()) for i in range(args.count)]
        if any(code != 0 for code in result["controller_exit_codes"]) or any(row["status"] != "passed" for row in result["sandboxes"]):
            raise RuntimeError("one or more actual mixed sandboxes failed; inspect preserved receipts")
        result["status"] = "passed"
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        result["errors"].append(f"{type(error).__name__}: {error}")
    finally:
        (out / "abort").touch(mode=0o600)
        for process in processes:
            if process.poll() is None:
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    process.wait(timeout=20)
        for handle in handles:
            handle.close()
        bench.save_json(out / "result.json", result)
    print(json.dumps({"status": result["status"], "mode": args.mode, "count": args.count,
                      "errors": result["errors"]}))
    return 0 if result["status"] == "passed" else 1


def main():
    os.umask(0o077)
    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--binary", required=True)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--mode", choices=["C00", "C10", "C01", "C11"], required=True)
    parser.add_argument("--count", choices=[4, 8], type=int, default=4)
    parser.add_argument("--phase")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--namespace", action="store_true")
    parser.add_argument("--uid", type=int, default=1000)
    parser.add_argument("--gid", type=int, default=1000)
    args = parser.parse_args()
    if args.namespace:
        return namespace(args)
    if args.worker:
        return worker(args)
    return launch(args)


if __name__ == "__main__":
    raise SystemExit(main())
