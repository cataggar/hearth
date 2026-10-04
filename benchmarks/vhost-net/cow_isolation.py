#!/usr/bin/env python3
"""Two real KVM restores of one backing file, each in its owned namespace."""

import argparse
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
import runner


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            result.update(chunk)
    return result.hexdigest()


def worker(args):
    directory = args.output.resolve()
    runner.private_directory(directory)
    runner.freeze_tools(directory)
    runner.setup_tap(directory)
    runner.owned_file(directory / "variant.json", json.dumps({
        "requested_backend": "vhost", "effective_backend": "vhost",
        "notification": "common blocked-poll/direct IRQ", "classification": "correctness only",
        "binary_sha256": digest(runner.ROOT / "vmm/zig-out/bin/flint"),
    }, indent=2) + "\n")
    channel = socket.socket(fileno=args.control_fd)
    sock = directory / "flint.sock"
    argv = [
        "taskset", "-c", "8", str(runner.ROOT / "vmm/zig-out/bin/flint"), "--restore",
        "--vmstate-path", str(args.source / "baseline.vmstate"),
        "--mem-path", str(args.source / "baseline.mem"), "--tap", "hn2tap0",
        "--net-backend", "vhost", "--api-sock", str(sock),
    ]
    with (directory / "restore.log").open("wb") as output:
        child = subprocess.Popen(argv, cwd=directory, stdout=output, stderr=subprocess.STDOUT,
                                 preexec_fn=runner.demote)
    try:
        runner.owned_file(directory / "flint-pid.txt", str(child.pid) + "\n")
        deadline = time.monotonic() + 15
        while not sock.exists():
            if child.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("independent restored API unavailable")
            time.sleep(0.01)
        channel.sendall(b"R")
        while True:
            action = channel.recv(1)
            if action == b"T":
                variant = {"effective_backend": "vhost", "notification": "common blocked-poll/direct IRQ"}
                status = runner.workload(directory, "h2g", "mutating-upload", 1, 0,
                                         variant_override=variant)
                channel.sendall(b"P" if status == 0 else b"F")
            elif action == b"E" or not action:
                return
            else:
                raise RuntimeError("invalid owned isolation control")
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        channel.close()
        runner.owned_file(directory / "closed.json", json.dumps({
            "pid": child.pid, "status": child.returncode,
            "owned_pid_absent_after_join": not Path("/proc", str(child.pid)).exists(),
        }, indent=2) + "\n")


def supervisor(args):
    directory = args.output.resolve()
    if directory.exists():
        raise ValueError("refusing to overwrite independent restore evidence")
    directory.relative_to(runner.ROOT / ".perf")
    runner.private_directory(directory)
    children = []
    channels = []
    result = {"classification": "unjailed real KVM simultaneous private-restore isolation, not performance"}
    try:
        before = digest(args.source / "baseline.mem")
        for name in ("a", "b"):
            parent, child = socket.socketpair()
            parent.settimeout(30)
            path = directory / name
            with (directory / f"{name}.supervisor.log").open("wb") as output:
                process = subprocess.Popen(
                    ["unshare", "--mount", "--net", "--", sys.executable, __file__,
                     "--source", str(args.source), "--output", str(path),
                     "--control-fd", str(child.fileno())],
                    cwd=runner.ROOT, stdout=output, stderr=subprocess.STDOUT,
                    pass_fds=(child.fileno(),))
            children.append(process)
            channels.append(parent)
            child.close()
            if parent.recv(1) != b"R":
                raise RuntimeError("independent restore supervisor failed")
        a = directory / "a"
        b = directory / "b"
        runner.request(b / "flint.sock", "PATCH", "/vm", {"state": "Paused"})
        runner.inventory(b, "paused-before-other-guest", int((b / "flint-pid.txt").read_text()))
        runner.request(b / "flint.sock", "PUT", "/snapshot/create",
                       {"snapshot_path": "before.vmstate", "mem_file_path": "before.mem"})
        paused_before = digest(b / "before.mem")
        channels[0].sendall(b"T")
        if channels[0].recv(1) != b"P":
            raise RuntimeError("mutating guest payload check failed")
        runner.request(a / "flint.sock", "PATCH", "/vm", {"state": "Paused"})
        runner.request(a / "flint.sock", "PUT", "/snapshot/create",
                       {"snapshot_path": "mutated.vmstate", "mem_file_path": "mutated.mem"})
        mutated = digest(a / "mutated.mem")
        runner.request(b / "flint.sock", "PUT", "/snapshot/create",
                       {"snapshot_path": "after.vmstate", "mem_file_path": "after.mem"})
        paused_after = digest(b / "after.mem")
        after = digest(args.source / "baseline.mem")
        payload = json.loads((a / "mutating-upload.json").read_text())
        result.update({
            "source_before_sha256": before, "source_after_sha256": after,
            "paused_b_before_sha256": paused_before, "paused_b_after_sha256": paused_after,
            "mutated_a_sha256": mutated, "checked_mutating_bytes": payload["payload_bytes_one_direction"],
            "payload_errors": payload["errors"],
            "independent_b_unchanged": paused_before == paused_after,
            "shared_backing_unchanged": before == after,
            "a_and_b_ram_different": mutated != paused_after,
        })
        result["passed"] = (result["independent_b_unchanged"] and result["shared_backing_unchanged"]
                            and result["a_and_b_ram_different"] and not payload["errors"]
                            and payload["payload_bytes_one_direction"] >= 8 * 1024 * 1024)
        if not result["passed"]:
            raise RuntimeError("simultaneous private restores shared guest writes")
    finally:
        for channel in channels:
            try:
                channel.sendall(b"E")
            except OSError:
                pass
            channel.close()
        for child in children:
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.terminate()
                child.wait(timeout=5)
        result["supervisor_statuses"] = [child.returncode for child in children]
        runner.owned_file(directory / "results.json", json.dumps(result, indent=2) + "\n")
        for path in (directory, *directory.rglob("*")):
            if not path.is_symlink():
                os.chown(path, 1000, 1000)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--control-fd", type=int)
    args = parser.parse_args()
    os.umask(0o077)
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    def terminate(_number, _frame):
        raise SystemExit("owned isolation supervisor terminated")
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    args.source = args.source.resolve()
    args.source.relative_to(runner.ROOT / ".perf")
    if args.control_fd is None:
        supervisor(args)
    else:
        worker(args)


if __name__ == "__main__":
    main()
