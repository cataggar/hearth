#!/usr/bin/env python3
"""Restrictive owned-child fault filter; never changes Flint's allow policy."""

import argparse
import array
import ctypes
import json
import os
import platform
import socket
from pathlib import Path


def code(direction, number, size):
    return (direction << 30) | (size << 16) | (0xaf << 8) | number


OPERATIONS = {
    "GET_FEATURES": code(2, 0, 8),
    "SET_FORK_FROM_OWNER": code(1, 0x84, 1),
    "GET_FORK_FROM_OWNER": code(2, 0x85, 1),
    "SET_OWNER": code(0, 1, 0),
    "SET_FEATURES": code(1, 0, 8),
    "SET_MEM_TABLE": code(1, 3, 8),
    "SET_VRING_NUM": code(1, 0x10, 8),
    "SET_VRING_ADDR": code(1, 0x11, 40),
    "SET_VRING_BASE": code(1, 0x12, 8),
    "SET_VRING_KICK": code(1, 0x20, 8),
    "SET_VRING_CALL": code(1, 0x21, 8),
    "SET_VRING_ERR": code(1, 0x22, 8),
    "SET_BACKEND": code(1, 0x30, 8),
    "GET_VRING_BASE": code(3, 0x12, 8),
}


class Filter(ctypes.Structure):
    _fields_ = [("code", ctypes.c_ushort), ("jt", ctypes.c_ubyte),
                ("jf", ctypes.c_ubyte), ("k", ctypes.c_uint)]


class Program(ctypes.Structure):
    _fields_ = [("length", ctypes.c_ushort), ("instructions", ctypes.POINTER(Filter))]


def install(operation, listener=False):
    if platform.machine() != "x86_64":
        raise RuntimeError("the frozen fault fixture is x86_64 Linux only")
    syscall, argument, error = 16, OPERATIONS.get(operation), 5
    if operation == "SHADOW_MMAP":
        syscall, argument, error = 9, 3 * 4096, 12
    elif operation == "EVENTFD":
        syscall, argument, error = 290, 0x80800, 24
    if argument is None:
        raise ValueError("unknown owned fault")
    instructions = (Filter * 6)(
        Filter(0x20, 0, 0, 0), Filter(0x15, 0, 3, syscall),
        Filter(0x20, 0, 0, 24), Filter(0x15, 0, 1, argument),
        Filter(0x06, 0, 0, 0x7fc00000 if listener else 0x50000 | error),
        Filter(0x06, 0, 0, 0x7fff0000),
    )
    if operation == "SHADOW_MMAP" and listener:
        instructions = (Filter * 11)(
            Filter(0x20, 0, 0, 0), Filter(0x15, 0, 3, 9),
            Filter(0x20, 0, 0, 24), Filter(0x15, 0, 1, argument),
            Filter(0x06, 0, 0, 0x7fc00000),
            Filter(0x20, 0, 0, 0), Filter(0x15, 0, 3, 16),
            Filter(0x20, 0, 0, 24), Filter(0x15, 0, 1, OPERATIONS["SET_MEM_TABLE"]),
            Filter(0x06, 0, 0, 0x7fc00000),
            Filter(0x06, 0, 0, 0x7fff0000),
        )
    program = Program(len(instructions), instructions)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, ctypes.c_ulong(1), 0, 0, 0):
        raise OSError(ctypes.get_errno(), "owned NNP")
    fd = None
    if listener:
        fd = libc.syscall(317, 1, 8, ctypes.byref(program))
        if fd < 0:
            raise OSError(ctypes.get_errno(), "owned fault listener")
    elif libc.prctl(22, ctypes.c_ulong(2), ctypes.byref(program), 0, 0):
        raise OSError(ctypes.get_errno(), "restrictive owned fault filter")
    return {"syscall": syscall, "argument1": argument, "errno": error,
            "policy": "additional restrictive fault filter; existing Flint restrictions retained"}, fd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--operation", choices=(*OPERATIONS, "SHADOW_MMAP", "EVENTFD"), required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--notify-fd", type=int)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    argv = args.command[1:] if args.command[:1] == ["--"] else args.command
    binary = Path(__file__).resolve().parents[2] / "vmm/zig-out/bin/flint"
    if not argv or Path(argv[0]).resolve() != binary:
        parser.error("fault launcher may execute only this worktree's Flint")
    os.umask(0o077)
    metadata, listener = install(args.operation, listener=args.notify_fd is not None)
    if listener is not None:
        with socket.socket(fileno=args.notify_fd) as channel:
            channel.sendmsg([b"owned-fault-listener"], [
                (socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [listener])),
            ])
        os.close(listener)
    metadata.update({"operation": args.operation, "pid": os.getpid(), "argv": argv})
    args.metadata.write_text(json.dumps(metadata, indent=2) + "\n")
    args.metadata.chmod(0o600)
    os.execv(str(binary), argv)


if __name__ == "__main__":
    main()
