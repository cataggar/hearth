#!/usr/bin/env python3
"""Ephemeral PID-scoped BPF observer for actual on-CPU irqfd work, not wall time."""

import argparse
import ctypes as c
import ctypes.util
import fcntl
import json
import os
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
libc = c.CDLL(None, use_errno=True)


def syscall(number, *args):
    result = libc.syscall(number, *args)
    if result < 0:
        raise OSError(c.get_errno(), os.strerror(c.get_errno()))
    return result


def pointer(value):
    return c.cast(c.byref(value), c.c_void_p).value


def map_operation(command, fd, key, value):
    attr = (c.c_uint64 * 4)(fd, pointer(key), pointer(value), 0)
    return syscall(321, command, c.byref(attr), c.sizeof(attr))


def topology():
    cpus = []
    for part in Path("/sys/devices/system/cpu/online").read_text().strip().split(","):
        first, *last = part.split("-")
        cpus += range(int(first), int(last[0] if last else first) + 1)
    return cpus


def trace_format(event, expected):
    directory = Path("/sys/kernel/tracing/events") / event
    text = (directory / "format").read_text()
    for field, offset, size in expected:
        match = re.search(rf"field:[^;]*\b{field}(?:\[[^\]]*\])?;\s*offset:(\d+);\s*size:(\d+);", text)
        if not match or tuple(map(int, match.groups())) != (offset, size):
            raise RuntimeError(f"unsupported tracepoint ABI: {event}.{field}")
    return int((directory / "id").read_text())


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--start-ticks", type=int, required=True)
    parser.add_argument("--object", required=True)
    args = parser.parse_args()
    if os.geteuid() != 0 or os.uname().machine != "x86_64":
        raise RuntimeError("scoped privileged x86_64 observer required, never a root VMM")
    stat = Path(f"/proc/{args.pid}/stat").read_text()
    if int(stat[stat.rfind(")") + 2:].split()[19]) != args.start_ticks:
        raise RuntimeError("owned PID generation changed")
    status = Path(f"/proc/{args.pid}/status").read_text()
    if int(re.search(r"^Uid:\s+(\d+)", status, re.M).group(1)) <= 0:
        raise RuntimeError("refusing root-running workload")
    obj_path = Path(args.object).resolve()
    obj_path.relative_to(ROOT)
    symbols = {}
    for line in Path("/proc/kallsyms").read_text().splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[2] in ("irqfd_inject", "irqfd_shutdown"):
            symbols[fields[2]] = int(fields[0], 16)
    if len(symbols) != 2 or not all(symbols.values()):
        raise RuntimeError("actual host irqfd symbols unavailable")
    lib = c.CDLL(ctypes.util.find_library("bpf"), use_errno=True)
    lib.bpf_object__open_file.argtypes = [c.c_char_p, c.c_void_p]
    lib.bpf_object__open_file.restype = c.c_void_p
    lib.libbpf_get_error.argtypes = [c.c_void_p]
    lib.libbpf_get_error.restype = c.c_long
    lib.bpf_object__load.argtypes = [c.c_void_p]
    lib.bpf_object__find_map_fd_by_name.argtypes = [c.c_void_p, c.c_char_p]
    lib.bpf_object__find_program_by_name.argtypes = [c.c_void_p, c.c_char_p]
    lib.bpf_object__find_program_by_name.restype = c.c_void_p
    lib.bpf_program__fd.argtypes = [c.c_void_p]
    lib.bpf_object__close.argtypes = [c.c_void_p]
    obj = lib.bpf_object__open_file(str(obj_path).encode(), None)
    if not obj or lib.libbpf_get_error(obj):
        raise RuntimeError("cannot open owned BPF object")
    fds = []
    try:
        if lib.bpf_object__load(obj) != 0:
            raise RuntimeError("scoped BPF program load denied; preserve verifier diagnostics")
        cfg_fd = lib.bpf_object__find_map_fd_by_name(obj, b"config")
        totals_fd = lib.bpf_object__find_map_fd_by_name(obj, b"totals")
        active_fd = lib.bpf_object__find_map_fd_by_name(obj, b"active")
        class Config(c.Structure):
            _fields_ = [("inject", c.c_uint64), ("shutdown", c.c_uint64), ("tgid", c.c_uint32)]
        cfg = Config(symbols["irqfd_inject"], symbols["irqfd_shutdown"], args.pid)
        map_operation(2, cfg_fd, c.c_uint32(0), cfg)
        events = {
            "queued": ("workqueue/workqueue_queue_work", [("work", 8, 8), ("function", 16, 8)]),
            "started": ("workqueue/workqueue_execute_start", [("work", 8, 8), ("function", 16, 8)]),
            "ended": ("workqueue/workqueue_execute_end", [("work", 8, 8), ("function", 16, 8)]),
            "switched": ("sched/sched_switch", [("prev_pid", 24, 4), ("next_pid", 56, 4)]),
        }
        for name, (event, layout) in events.items():
            event_id = trace_format(event, layout)
            program = lib.bpf_object__find_program_by_name(obj, name.encode())
            prog_fd = lib.bpf_program__fd(program)
            if prog_fd < 0:
                raise RuntimeError(f"missing loaded program: {name}")
            # TRACEPOINT BPF programs attach to the trace-event call globally,
            # not once per CPU (a second attachment is EEXIST). This one private
            # perf fd is the libbpf-style lifetime anchor; the programs themselves
            # filter owned work on every CPU. No ring/raw events are allocated.
            attr = (c.c_uint64 * 16)(2 | (128 << 32), event_id, 1, 1 << 10, 0, 1)
            fd = syscall(298, c.byref(attr), -1, topology()[0], -1, 8)
            fds.append(fd)
            fcntl.ioctl(fd, 0x40042408, prog_fd)
            fcntl.ioctl(fd, 0x2400, 0)
        started = time.monotonic()
        print(json.dumps({"ready": True, "pid": args.pid, "scope": "only work queued by owned TGID and exact irqfd functions; scheduler subtracts off-CPU time",
                          "pinned_maps": False, "raw_task_data_emitted": False}), flush=True)
        while True:
            operation = sys.stdin.readline().strip()
            if operation not in ("READ", "STOP"):
                raise RuntimeError("observer protocol interrupted")
            if operation == "STOP":
                for fd in fds:
                    fcntl.ioctl(fd, 0x2401, 0)
            values = {}
            for kind, name in ((0, "anomalies"), (1, "inject"), (2, "shutdown")):
                value = (c.c_uint64 * 2)()
                map_operation(1, totals_fd, c.c_uint32(kind), value)
                values[name] = {"cpu_ns": value[0], "jobs": value[1]}
            next_key = c.c_uint32()
            empty_attr = (c.c_uint64 * 3)(active_fd, 0, pointer(next_key))
            found = libc.syscall(321, 4, c.byref(empty_attr), c.sizeof(empty_attr))
            incomplete = found >= 0
            result = {"status": "passed" if values["anomalies"]["jobs"] == 0 and not incomplete else "failed",
                      "kernel_work": values, "incomplete_work_at_boundary": incomplete,
                      "kernel_irqfd_cpu_seconds": (values["inject"]["cpu_ns"] + values["shutdown"]["cpu_ns"]) / 1e9,
                      "observer_seconds": time.monotonic() - started,
                      "accounting": "on-CPU intervals inside owned work; not workqueue wall duration; observer overhead retained conservatively"}
            print(json.dumps(result), flush=True)
            if operation == "STOP":
                return 0 if result["status"] == "passed" else 1
    finally:
        for fd in fds:
            os.close(fd)
        lib.bpf_object__close(obj)


if __name__ == "__main__":
    raise SystemExit(main())
