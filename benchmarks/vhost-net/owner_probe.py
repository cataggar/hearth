#!/usr/bin/env python3
"""Actual owner-worker inheritance using the prototype's exact enforced filter."""

import argparse
import ctypes
import fcntl
import json
import os
import resource
import signal
import time
from pathlib import Path


def ioctl_code(direction, number, size):
    return direction << 30 | size << 16 | 0xaf << 8 | number


def task_status(pid):
    fields = {"Name", "Pid", "Tgid", "Uid", "Gid", "Groups", "CapEff",
              "NoNewPrivs", "Seccomp", "Seccomp_filters", "Kthread", "Cpus_allowed_list"}
    tasks = {}
    for task in Path("/proc", str(pid), "task").iterdir():
        values = {}
        for line in (task / "status").read_text().splitlines():
            key, _, value = line.partition(":")
            if key in fields:
                values[key] = value.strip()
        values["cgroup"] = (task / "cgroup").read_text().strip()
        tasks[task.name] = values
    return tasks


def probe(args, cgroup, result):
    fd_before = len(list(Path("/proc/self/fd").iterdir()))
    cgroup.joinpath("memory.max").write_text(str(1024 * 1024 * 1024))
    cgroup.joinpath("pids.max").write_text("16")
    result["limits"] = {name: (cgroup / name).read_text().strip()
                        for name in ("memory.max", "pids.max", "cpu.stat")}
    result["cpu_max_available"] = (cgroup / "cpu.max").exists()
    raw = args.filter.read_bytes()
    array = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)

    class FilterProgram(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ushort), ("filter", ctypes.c_void_p)]

    program = FilterProgram(len(raw) // 8, ctypes.addressof(array))
    libc = ctypes.CDLL(None, use_errno=True)
    ready_read, ready_write = os.pipe()
    release_read, release_write = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(ready_read)
        os.close(release_write)
        cgroup.joinpath("cgroup.procs").write_text(str(os.getpid()))
        os.setgroups([])
        os.setgid(1000)
        os.setuid(1000)
        os.sched_setaffinity(0, {8})
        fd = os.open("/dev/vhost-net", os.O_RDWR | os.O_CLOEXEC)
        if libc.prctl(38, 1, 0, 0, 0) or libc.prctl(4, 0, 0, 0, 0):
            os._exit(90)
        if libc.syscall(317, 1, 0, ctypes.byref(program)):
            os._exit(91)
        fcntl.ioctl(fd, ioctl_code(1, 0x84, 1), b"\x01")
        mode = bytearray(1)
        fcntl.ioctl(fd, ioctl_code(2, 0x85, 1), mode)
        if mode[0] != 1:
            os._exit(92)
        fcntl.ioctl(fd, ioctl_code(0, 1, 0))
        os.write(ready_write, b"R")
        os.read(release_read, 1)
        os.close(fd)
        os.write(ready_write, b"C")
        os.read(release_read, 1)
        os._exit(0)
    os.close(ready_write)
    os.close(release_read)
    try:
        os.set_blocking(ready_read, False)
        deadline = time.monotonic() + 10
        while True:
            try:
                ready = os.read(ready_read, 1)
                break
            except BlockingIOError:
                if time.monotonic() > deadline:
                    raise TimeoutError("owner worker did not become ready")
                time.sleep(0.01)
        if ready != b"R":
            raise RuntimeError("enforced owner child failed before ready")
        result["active_tasks"] = task_status(pid)
        workers = [row for row in result["active_tasks"].values() if row["Name"].startswith("vhost-")]
        result["worker_inherits"] = len(workers) == 1 and all(
            row["Uid"].split() == ["1000"] * 4 and row["Gid"].split() == ["1000"] * 4
            and row["Groups"] == "" and int(row["CapEff"], 16) == 0
            and row["NoNewPrivs"] == "1" and row["Seccomp"] == "2"
            and row["Cpus_allowed_list"] == "8"
            and row["cgroup"] == f"0::/{cgroup.name}" for row in workers)
        result["pids_current_active"] = (cgroup / "pids.current").read_text().strip()
        os.write(release_write, b"C")
        while True:
            try:
                closed = os.read(ready_read, 1)
                break
            except BlockingIOError:
                if time.monotonic() > deadline:
                    raise TimeoutError("owner worker did not close")
                time.sleep(0.01)
        if closed != b"C":
            raise RuntimeError("owner close failed")
        result["closed_tasks"] = task_status(pid)
        result["worker_joined_before_ack"] = len(result["closed_tasks"]) == 1
        result["pids_current_closed"] = (cgroup / "pids.current").read_text().strip()
        result["cpu_stat_after"] = (cgroup / "cpu.stat").read_text().strip()
        os.write(release_write, b"E")
        _, status = os.waitpid(pid, 0)
        pid = None
        result["child_status"] = status
        result["passed"] = result["worker_inherits"] and result["worker_joined_before_ack"] and status == 0
    finally:
        if pid is not None:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            _, status = os.waitpid(pid, 0)
            result["failed_child_status"] = status
        os.close(ready_read)
        os.close(release_write)
        result["fd_count_before"] = fd_before
        result["fd_count_after"] = len(list(Path("/proc/self/fd").iterdir()))
    return not result.get("passed", False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--filter", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--id", required=True)
    args = parser.parse_args()
    if os.getuid() != 0 or not args.id.replace("-", "").isalnum():
        raise ValueError("root supervisor and unique alphanumeric/hyphen probe ID required")
    if args.output.exists():
        raise ValueError("refusing to overwrite retained owner evidence")
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    cgroup = Path("/sys/fs/cgroup", f"hearth-vhost-net-{args.id}")
    cgroup.mkdir(mode=0o700)
    result = {"classification": "enforced owner-worker inheritance, not full VMM jail acceptance"}
    try:
        return probe(args, cgroup, result)
    except Exception as error:
        result["failure"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        result["cgroup_empty"] = (cgroup / "cgroup.procs").read_text().strip() == ""
        cgroup.rmdir()
        args.output.write_text(json.dumps(result, indent=2) + "\n")
        os.chmod(args.output, 0o600)
        os.chown(args.output, 1000, 1000)


if __name__ == "__main__":
    raise SystemExit(main())
