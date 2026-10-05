#!/usr/bin/env python3
"""Real jailed setup faults, including second queue and shadow-map allocations."""

import argparse
import array
import ctypes
import json
import os
import select
import signal
import socket
import subprocess
import time
from pathlib import Path

import ioctl_fault
import runner


class Data(ctypes.Structure):
    _fields_ = [("nr", ctypes.c_int), ("arch", ctypes.c_uint),
                ("ip", ctypes.c_ulonglong), ("args", ctypes.c_ulonglong * 6)]


class Notification(ctypes.Structure):
    _fields_ = [("id", ctypes.c_ulonglong), ("pid", ctypes.c_uint),
                ("flags", ctypes.c_uint), ("data", Data)]


class Response(ctypes.Structure):
    _fields_ = [("id", ctypes.c_ulonglong), ("value", ctypes.c_longlong),
                ("error", ctypes.c_int), ("flags", ctypes.c_uint)]


def ioctl(fd, request, value):
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.ioctl(fd, ctypes.c_ulong(request), ctypes.byref(value)) < 0:
        raise OSError(ctypes.get_errno(), "owned fault notification ioctl")


def run_case(directory, operation, backend, queue=None, occurrence=1):
    before_fds = len(list(Path("/proc/self/fd").iterdir()))
    runner.private_directory(directory)
    layout = runner.JailedLayout(directory, fixture=runner.ROOT / ".perf/vhost-net/20261004/fixture")
    binary = runner.ROOT / "vmm/zig-out/bin/flint"
    argv = layout.argv(binary)
    parent, channel = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
    parent.settimeout(10)
    launcher = runner.ROOT / "benchmarks/vhost-net/ioctl_fault.py"
    argv = [*argv[:6], "python3", str(launcher), "--operation", operation,
            "--metadata", str(directory / "filter.json"), "--notify-fd", str(channel.fileno()),
            "--", *argv[6:], "bzImage", "initrd.cpio.gz", "console=ttyS0 reboot=k panic=1 pci=off",
            "--net-backend", backend]
    process, listener = None, None
    result = {"operation": operation, "backend": backend, "queue": queue,
              "target_occurrence": occurrence, "injected": False, "notifications": [],
              "classification": "restrictive owned fault; correctness only, not performance"}
    try:
        with (directory / "serial.log").open("wb") as output:
            process = subprocess.Popen(argv, cwd=directory, stdout=output, stderr=subprocess.STDOUT,
                                       pass_fds=(channel.fileno(),))
        channel.close()
        _, ancillary, _, _ = parent.recvmsg(64, socket.CMSG_SPACE(array.array("i").itemsize))
        descriptors = []
        for level, kind, data in ancillary:
            if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                values = array.array("i")
                values.frombytes(data[:len(data) - len(data) % values.itemsize])
                descriptors.extend(values)
        if len(descriptors) != 1:
            for fd in descriptors:
                os.close(fd)
            raise RuntimeError("expected one owned fault-listener FD")
        listener = descriptors[0]
        poller = select.poll()
        poller.register(listener, select.POLLIN)
        matches = 0
        vhost_table = False
        deadline = time.monotonic() + 30
        while process.poll() is None:
            if time.monotonic() > deadline:
                raise TimeoutError("owned fault did not terminate")
            events = poller.poll(100)
            if not any(flags & select.POLLIN for _, flags in events):
                continue
            notification = Notification()
            ioctl(listener, 0xc0502100, notification)
            members = (layout.cgroup / "cgroup.threads").read_text().split()
            if notification.pid != process.pid and str(notification.pid) not in members:
                raise RuntimeError("fault notification is not from an owned task")
            selected_queue = None
            if queue is not None:
                fd = os.open(f"/proc/{notification.pid}/mem", os.O_RDONLY | os.O_CLOEXEC)
                try:
                    selected_queue = int.from_bytes(os.pread(fd, 4, notification.data.args[2]), "little")
                finally:
                    os.close(fd)
            is_flint = Path(f"/proc/{notification.pid}/exe").resolve() == binary
            table_operation = operation == "SHADOW_MMAP" and notification.data.nr == 16
            if table_operation:
                device = os.stat(f"/proc/{notification.pid}/fd/{notification.data.args[0]}")
                if not is_flint or (os.major(device.st_rdev), os.minor(device.st_rdev)) != (10, 238):
                    raise RuntimeError("shadow phase marker is not this Flint's vhost memory table")
                vhost_table = True
            shadow_map = operation != "SHADOW_MMAP" or (
                notification.data.nr == 9 and vhost_table
                and
                notification.data.args[3] & 0x22 == 0x22
                and notification.data.args[4] & 0xffffffff == 0xffffffff
            )
            target = is_flint and shadow_map and (queue is None or selected_queue == queue)
            matches += int(target)
            inject = target and matches == occurrence and not result["injected"]
            error = 12 if operation == "SHADOW_MMAP" else 24 if operation == "EVENTFD" else 5
            response = Response(notification.id, 0, -error if inject else 0, 0 if inject else 1)
            ioctl(listener, 0xc0182101, response)
            result["notifications"].append({
                "owned_tid": notification.pid, "queue": selected_queue,
                "flint_exec": is_flint, "injected": inject, "errno": error if inject else None,
                "vhost_table_registered": vhost_table if operation == "SHADOW_MMAP" else None,
                "table_operation": table_operation,
                "shadow_map": shadow_map if operation == "SHADOW_MMAP" else None,
                "mmap_flags": notification.data.args[3] if operation == "SHADOW_MMAP" and not table_operation else None,
                "mmap_fd": notification.data.args[4] & 0xffffffff if operation == "SHADOW_MMAP" and not table_operation else None,
            })
            result["injected"] = result["injected"] or inject
        process.wait(timeout=5)
        text = (directory / "serial.log").read_text(errors="replace")
        expected = "OutOfMemory" if operation == "SHADOW_MMAP" else (
            "NetEventfdFailed" if operation == "EVENTFD" else "VhostIoctlFailed")
        result.update({
            "argv": argv, "pid": process.pid, "actual_join_status": process.returncode,
            "expected_error": expected,
            "passed": result["injected"] and process.returncode == 1 and expected in text
                      and "effective=userspace reason=" not in text,
            "owned_pid_absent_after_join": not Path("/proc", str(process.pid)).exists(),
        })
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if listener is not None:
            os.close(listener)
        parent.close()
        channel.close()
        layout.close()
        after_fds = len(list(Path("/proc/self/fd").iterdir()))
        result["supervisor_fds_before_after"] = [before_fds, after_fds]
        result["passed"] = result.get("passed", False) and before_fds == after_fds
        runner.owned_file(directory / "result.json", json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--single", choices=(*ioctl_fault.OPERATIONS, "SHADOW_MMAP", "EVENTFD"))
    args = parser.parse_args()
    if args.single == "GET_VRING_BASE":
        parser.error("GET_VRING_BASE is a lifecycle operation, not a setup fault")
    os.umask(0o077)
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    def terminate(_number, _frame):
        raise SystemExit("owned fault supervisor terminated; joining child")
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    directory = args.output.resolve()
    directory.relative_to(runner.ROOT / ".perf")
    if directory.exists():
        raise ValueError("refusing to overwrite fault evidence")
    runner.private_directory(directory)
    for name in ("fault_probe.py", "ioctl_fault.py"):
        runner.owned_file(directory / f"source-{name}", (runner.ROOT / "benchmarks/vhost-net" / name).read_text())
    runner.setup_tap(directory)
    results = []
    for operation in args.single and [args.single] or [
        *[name for name in ioctl_fault.OPERATIONS if name != "GET_VRING_BASE"],
        "SHADOW_MMAP", "EVENTFD",
    ]:
        queues = (0, 1) if operation.startswith("SET_VRING") or operation == "SET_BACKEND" else (None,)
        occurrences = (1, 2) if operation == "SHADOW_MMAP" else (
            tuple(range(1, 8)) if operation == "EVENTFD" else (1,))
        for backend in ("vhost", "auto"):
            for queue in queues:
                for occurrence in occurrences:
                    name = f"{operation.lower().replace('_','-')}-{backend}-{queue}-{occurrence}"
                    results.append(run_case(directory / name, operation, backend, queue, occurrence))
    runner.owned_file(directory / "results.json", json.dumps(results, indent=2) + "\n")
    if not all(row["passed"] for row in results):
        raise RuntimeError("owned setup-fault matrix failed")


if __name__ == "__main__":
    main()
