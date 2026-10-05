#!/usr/bin/env python3
"""Characterize KVM completion-before-interruption; not net/API acceptance."""

import argparse
import ctypes
import errno
import json
import mmap
import os
from pathlib import Path
import platform
import struct


class Segment(ctypes.Structure):
    _fields_ = [("base", ctypes.c_uint64), ("limit", ctypes.c_uint32),
                ("selector", ctypes.c_uint16), *[
                    (name, ctypes.c_uint8) for name in
                    ("type", "present", "dpl", "db", "s", "l", "g", "avl", "unusable", "padding")
                ]]


class Table(ctypes.Structure):
    _fields_ = [("base", ctypes.c_uint64), ("limit", ctypes.c_uint16),
                ("padding", ctypes.c_uint16 * 3)]


class Sregs(ctypes.Structure):
    _fields_ = [*[(name, Segment) for name in ("cs", "ds", "es", "fs", "gs", "ss", "tr", "ldt")],
                ("gdt", Table), ("idt", Table), *[
                    (name, ctypes.c_uint64) for name in ("cr0", "cr2", "cr3", "cr4", "cr8", "efer", "apic_base")
                ], ("interrupt_bitmap", ctypes.c_uint64 * 4)]


class Regs(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in
               ("rax", "rbx", "rcx", "rdx", "rsi", "rdi", "rsp", "rbp",
                "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15", "rip", "rflags")]


LIBC = ctypes.CDLL(None, use_errno=True)
LIBC.ioctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_void_p]
LIBC.ioctl.restype = ctypes.c_int


def ioctl(fd, operation, data=0):
    result = LIBC.ioctl(fd, operation, data)
    if result < 0:
        raise OSError(ctypes.get_errno(), f"owned KVM ioctl {operation:#x}")
    return result


def case(system, run_size, mode):
    vm = vcpu = None
    ram = run = None
    try:
        vm = ioctl(system, 0xAE01)
        ram = mmap.mmap(-1, 2 * 1024 * 1024)
        address = ctypes.addressof(ctypes.c_char.from_buffer(ram))
        # Leave DS:8000 unmapped without exceeding a real-mode segment limit.
        region = ctypes.create_string_buffer(struct.pack("<IIQQQ", 0, 0, 0, 0x4000, address))
        ioctl(vm, 0x4020AE46, ctypes.addressof(region))
        vcpu = ioctl(vm, 0xAE41)
        run = mmap.mmap(vcpu, run_size, flags=mmap.MAP_SHARED,
                        prot=mmap.PROT_READ | mmap.PROT_WRITE)
        registers, special = Regs(), Sregs()
        ioctl(vcpu, 0x8138AE83, ctypes.addressof(special))
        special.cs.base = special.cs.selector = 0
        special.ds.base = special.ds.selector = 0
        special.es.base = special.es.selector = 0
        special.ss.base = special.ss.selector = 0
        ioctl(vcpu, 0x4138AE84, ctypes.addressof(special))
        registers.rip, registers.rflags, registers.rsp = 0x1000, 2, 0x3000
        ioctl(vcpu, 0x4090AE82, ctypes.addressof(registers))
        prefix = b"\xba\x70\x00\xec" if mode == "pio-in" else b"\xa0\x00\x80"
        program = prefix + b"\xa2\x00\x20\xf4"
        ram[0x1000:0x1000 + len(program)] = program
        print(f"{mode}: enter first KVM_RUN; owned PID {os.getpid()}", flush=True)
        ioctl(vcpu, 0xAE80)
        reason = struct.unpack_from("<I", run, 8)[0]
        expected_reason = 2 if mode == "pio-in" else 6
        if reason != expected_reason:
            raise RuntimeError(f"unexpected first owned exit {reason}, wanted {expected_reason}")
        if mode == "pio-in":
            offset = struct.unpack_from("<Q", run, 40)[0]
            if not (run[32] == 0 and run[33] == 1 and offset < run_size
                    and struct.unpack_from("<HI", run, 34) == (0x70, 1)):
                raise RuntimeError("unexpected owned PIO input geometry")
            run[offset] = 0x5A
        else:
            if (struct.unpack_from("<Q", run, 32)[0] != 0x8000
                    or struct.unpack_from("<I", run, 48)[0] != 1 or run[52] != 0):
                raise RuntimeError("unexpected owned MMIO read geometry")
            run[40] = 0x5A
        ioctl(vcpu, 0x8090AE81, ctypes.addressof(registers))
        before = {"rax": registers.rax, "rip": registers.rip, "next_instruction_marker": ram[0x2000]}
        run[1] = 1
        print(f"{mode}: reenter to complete pending exit with immediate_exit=1", flush=True)
        try:
            ioctl(vcpu, 0xAE80)
        except OSError as error:
            if error.errno != errno.EINTR:
                raise
        else:
            raise RuntimeError("immediate-exit completion did not return EINTR")
        ioctl(vcpu, 0x8090AE81, ctypes.addressof(registers))
        after = {"rax": registers.rax, "rip": registers.rip, "next_instruction_marker": ram[0x2000]}
        if before["rax"] != 0 or after["rax"] != 0x5A or after["rip"] != 0x1000 + len(prefix):
            raise RuntimeError(f"pending completion inconsistent: {before} -> {after}")
        if before["next_instruction_marker"] or after["next_instruction_marker"]:
            raise RuntimeError("another guest instruction ran before the interruption barrier")
        run[1] = 0
        print(f"{mode}: resume to following marker/HLT", flush=True)
        ioctl(vcpu, 0xAE80)
        final_reason = struct.unpack_from("<I", run, 8)[0]
        if final_reason != 5 or ram[0x2000] != 0x5A:
            raise RuntimeError("resume did not execute precisely the following marker/HLT")
        return {"mode": mode, "passed": True, "before": before, "after_barrier": after,
                "resumed_exit": final_reason, "resumed_marker": ram[0x2000],
                "classification": "actual KVM model; not Flint API pause/race or TAP acceptance"}
    finally:
        if run is not None:
            run.close()
        if vcpu is not None:
            os.close(vcpu)
        if ram is not None:
            ram.close()
        if vm is not None:
            os.close(vm)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    output.relative_to(root / ".perf")
    if output.exists() or platform.machine() != "x86_64":
        raise RuntimeError("fresh owned x86_64 output required")
    os.umask(0o077)
    output.mkdir(mode=0o700)
    (output / "source.py").write_text(Path(__file__).read_text())
    assert ctypes.sizeof(Regs) == 144 and ctypes.sizeof(Sregs) == 312
    before = len(os.listdir("/proc/self/fd"))
    system = os.open("/dev/kvm", os.O_RDWR | os.O_CLOEXEC)
    try:
        if ioctl(system, 0xAE00) != 12:
            raise RuntimeError("unexpected KVM API")
        run_size = ioctl(system, 0xAE04)
        rows = [case(system, run_size, mode) for mode in ("pio-in", "mmio-read")]
    finally:
        os.close(system)
    after = len(os.listdir("/proc/self/fd"))
    if before != after:
        raise RuntimeError("owned KVM FD leak")
    result = {"rows": rows, "fd_before_after": [before, after], "host_kernel": platform.release(),
              "owned_pid": os.getpid(), "uid": os.getuid(), "no_jail_or_tap": True,
              "runtime_source_reference": os.environ["FLINT_PROBE_REVISION"]}
    (output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
