#!/usr/bin/env python3
"""Isolated, non-performance characterization of the pinned vhost-net UAPI."""

import argparse
import ctypes
import fcntl
import json
import mmap
import os
from pathlib import Path
import resource
import select
import socket
import struct
import subprocess
import sys
import time


SIZE = 2 * 1024 * 1024
NUM = 256
VERSION_1 = 1 << 32
IFACE = "hn2s1tap0"
HOST_MAC = bytes.fromhex("020000000001")
GUEST_MAC = bytes.fromhex("020000000002")
ETHERTYPE = 0x88B5
HEADER = bytes(12)


def ioctl_code(direction, number, size):
    return (direction << 30) | (size << 16) | (0xAF << 8) | number


def transact(fd, direction, number, payload):
    buffer = bytearray(payload)
    fcntl.ioctl(fd, ioctl_code(direction, number, len(buffer)), buffer, True)
    return bytes(buffer)


def status(pid, tid=None):
    base = Path(f"/proc/{pid}")
    if tid is not None:
        base /= f"task/{tid}"
    text = (base / "status").read_text()
    keys = {"Name", "State", "Tgid", "Pid", "PPid", "Uid", "Gid", "Groups",
            "CapEff", "NoNewPrivs", "Seccomp", "Cpus_allowed_list", "Kthread"}
    fields = {key: value.strip() for line in text.splitlines()
              if ":" in line for key, value in [line.split(":", 1)] if key in keys}
    fields["cgroup"] = (base / "cgroup").read_text().strip()
    return fields


def event_count(fd):
    total = 0
    while True:
        try:
            total += os.eventfd_read(fd)
        except BlockingIOError:
            return total


class Device:
    def __init__(self, tap, backing, private_ring=False):
        self.fd = -1
        self.events = []
        backing_fd = os.open(backing, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.ftruncate(backing_fd, SIZE)
            self.ram = mmap.mmap(backing_fd, SIZE, flags=mmap.MAP_PRIVATE)
        finally:
            os.close(backing_fd)
        self.private_ring = private_ring
        self.ring = (mmap.mmap(-1, 0x10000, flags=mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS)
                     if private_ring else self.ram)
        self.address = ctypes.addressof(ctypes.c_char.from_buffer(self.ram))
        self.ring_address = ctypes.addressof(ctypes.c_char.from_buffer(self.ring))
        self.indices = [0, 0]
        self.initial_tasks = set(os.listdir("/proc/self/task"))
        try:
            self.fd = os.open("/dev/vhost-net", os.O_RDWR | os.O_CLOEXEC)
            self.features = struct.unpack("<Q", transact(self.fd, 2, 0, bytes(8)))[0]
            try:
                self.fork_owner = transact(self.fd, 2, 0x85, bytes(1))[0]
            except OSError as error:
                self.fork_owner = {"errno": error.errno}
            fcntl.ioctl(self.fd, ioctl_code(0, 1, 0))
            transact(self.fd, 1, 0, struct.pack("<Q", VERSION_1))
            # The ioctl size is the fixed header, not the flexible array payload.
            memory = struct.pack("<IIQQQQ", 1, 0, 0, SIZE, self.address, 0)
            fcntl.ioctl(self.fd, ioctl_code(1, 3, 8), memory)
            for queue in range(2):
                offset = queue * 0x3000
                transact(self.fd, 1, 0x10, struct.pack("<II", queue, NUM))
                transact(self.fd, 1, 0x11, struct.pack(
                    "<IIQQQQ", queue, 0, self.ring_address + offset,
                    self.ring_address + offset + 0x2000, self.ring_address + offset + 0x1000, 0))
                transact(self.fd, 1, 0x12, struct.pack("<II", queue, 0))
                eventfds = []
                self.events.append(eventfds)
                for _ in range(3):
                    eventfds.append(os.eventfd(0, os.EFD_NONBLOCK | os.EFD_CLOEXEC))
                for number, event in zip((0x20, 0x21, 0x22), eventfds):
                    transact(self.fd, 1, number, struct.pack("<Ii", queue, event))
                transact(self.fd, 1, 0x30, struct.pack("<Ii", queue, tap))
        except BaseException:
            self.close()
            raise

    def post(self, queue, payload=None, flags=None, length=None, descriptor_address=None):
        index = self.indices[queue]
        head = index % NUM
        offset = queue * 0x3000
        address = 0x10000 + queue * 0x80000 + head * 2048
        if flags is None:
            flags = 2 if queue == 0 else 0
        if self.private_ring and flags & ~3:
            raise ValueError("UnadvertisedDescriptorFlags")
        if payload is not None:
            self.ram[address:address + len(payload)] = payload
        if length is None:
            length = 2048 if queue == 0 else len(payload)
        struct.pack_into("<QIHH", self.ring, offset + head * 16,
                         address if descriptor_address is None else descriptor_address,
                         length, flags, 0)
        struct.pack_into("<H", self.ring, offset + 0x1004 + head * 2, head)
        self.indices[queue] += 1
        struct.pack_into("<H", self.ring, offset + 0x1002, self.indices[queue])
        os.eventfd_write(self.events[queue][0], 1)
        return address

    def used(self, queue):
        return struct.unpack_from("<H", self.ring, queue * 0x3000 + 0x2002)[0]

    def observe(self, queue, timeout=3):
        ready, _, _ = select.select(self.events[queue][1:], [], [], timeout)
        return {"ready": bool(ready), "call": event_count(self.events[queue][1]),
                "error": event_count(self.events[queue][2]), "used": self.used(queue)}

    def detach(self):
        for queue in range(2):
            transact(self.fd, 1, 0x20, struct.pack("<Ii", queue, -1))
            transact(self.fd, 1, 0x30, struct.pack("<Ii", queue, -1))
        return [struct.unpack("<II", transact(
            self.fd, 3, 0x12, struct.pack("<II", queue, 0)))[1]
                for queue in range(2)]

    def reattach(self, tap):
        for queue in range(2):
            transact(self.fd, 1, 0x20,
                     struct.pack("<Ii", queue, self.events[queue][0]))
            transact(self.fd, 1, 0x30, struct.pack("<Ii", queue, tap))

    def close(self):
        # release() stops/flushes/joins kernel work before guest RAM is unmapped.
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1
        for events in self.events:
            for fd in events:
                os.close(fd)
        self.events.clear()
        if self.private_ring:
            self.ring.close()
        self.ram.close()


def send(control, message):
    control.sendall((json.dumps(message) + "\n").encode())


def receive(control):
    data = bytearray()
    while not data.endswith(b"\n"):
        chunk = control.recv(1)
        if not chunk:
            raise EOFError("supervisor control closed")
        data.extend(chunk)
    return json.loads(data)


def worker(control_fd, output, private_ring=False):
    os.setgroups([])
    os.setgid(1000)
    os.setuid(1000)
    if ctypes.CDLL(None, use_errno=True).prctl(38, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "PR_SET_NO_NEW_PRIVS")
    os.sched_setaffinity(0, {8})
    control = socket.socket(fileno=control_fd)
    control.settimeout(15)
    fd_before = len(os.listdir("/proc/self/fd"))
    tap = -1
    backing = output.with_name("ram-base.bin")
    results = {"pid": os.getpid(), "owner": status(os.getpid()),
               "kernel": os.uname().release, "map": "file-backed MAP_PRIVATE",
               "cases": [], "framing": {"header_bytes": 12, "offloads": 0,
                                        "socket_owns_header": True}}
    results["host_private_rings"] = private_ring
    dev = None
    try:
        tap = os.open("/dev/net/tun", os.O_RDWR | os.O_CLOEXEC)
        fcntl.ioctl(tap, 0x400454CA,
                    struct.pack("16sH22x", IFACE.encode(), 0x0002 | 0x1000 | 0x4000))
        fcntl.ioctl(tap, 0x400454D8, struct.pack("<i", 12))
        fcntl.ioctl(tap, 0x400454D0, 0)
        dev = Device(tap, backing, private_ring)
        results["private_ring_hva_outside_memory_table"] = (
            dev.ring_address + 0x10000 <= dev.address
            or dev.ring_address >= dev.address + SIZE) if private_ring else None
        results["features"] = hex(dev.features)
        results["fork_owner"] = dev.fork_owner
        results["tasks_during"] = [
            status(os.getpid(), tid) for tid in sorted(os.listdir("/proc/self/task"))]
        frame_tx = HOST_MAC + GUEST_MAC + struct.pack("!H", ETHERTYPE) + b"HN2-S1-TX" * 8
        frame_rx = GUEST_MAC + HOST_MAC + struct.pack("!H", ETHERTYPE) + b"HN2-S1-RX" * 8
        for sequence in range(2):
            if sequence == 1:
                struct.pack_into("<H", dev.ram, 0x5002, 0x7711)
            dev.post(1, HEADER + frame_tx)
            tx = dev.observe(1)
            send(control, {"action": "receive", "payload": frame_tx.hex()})
            tx["payload_valid"] = receive(control)["valid"]
            tx["name"] = "valid-tx" if sequence == 0 else "guest-used-index-mutation"
            results["cases"].append(tx)
        address = dev.post(0)
        send(control, {"action": "send", "payload": frame_rx.hex()})
        receive(control)
        rx = dev.observe(0)
        rx["header"] = dev.ram[address:address + 12].hex()
        rx["payload_valid"] = dev.ram[address + 12:address + 12 + len(frame_rx)] == frame_rx
        rx["name"] = "valid-rx-12-byte-header"
        results["cases"].append(rx)
        # Deliberately demonstrate why guest used.idx cannot seed a naive resume.
        struct.pack_into("<H", dev.ram, 0x5002, 0x7711)
        results["poisoned_pause_avail"] = dev.detach()
        dev.reattach(tap)
        dev.post(1, HEADER + frame_tx)
        naive = dev.observe(1)
        naive["name"] = "naive-guest-index-resume"
        naive["trusted_expected_used"] = 3
        results["cases"].append(naive)
        send(control, {"action": "receive", "payload": frame_tx.hex()})
        naive["payload_valid"] = receive(control)["valid"]
        results["seeded_pause_avail"] = dev.detach()
        struct.pack_into("<H", dev.ring, 0x5002, 3)
        dev.reattach(tap)
        dev.post(1, HEADER + frame_tx)
        seeded = dev.observe(1)
        seeded["name"] = "trusted-counter-seeded-resume"
        results["cases"].append(seeded)
        send(control, {"action": "receive", "payload": frame_tx.hex()})
        seeded["payload_valid"] = receive(control)["valid"]
        indirect_address = 0x1A0000
        dev.ram[indirect_address:indirect_address + len(HEADER + frame_tx)] = HEADER + frame_tx
        indirect_table = struct.pack("<QIHH", indirect_address, len(HEADER + frame_tx), 0, 0)
        if private_ring:
            try:
                dev.post(1, indirect_table, flags=4)
            except ValueError as error:
                indirect = dev.observe(1, 0.1)
                indirect["diagnostic"] = str(error)
            else:
                raise RuntimeError("private-ring publisher accepted INDIRECT")
        else:
            dev.post(1, indirect_table, flags=4)
            indirect = dev.observe(1)
        indirect["name"] = ("unadvertised-indirect-rejected" if private_ring
                            else "unadvertised-indirect-descriptor")
        indirect["negotiated_indirect"] = False
        results["cases"].append(indirect)
        if not private_ring:
            send(control, {"action": "receive", "payload": frame_tx.hex()})
            indirect["payload_valid"] = receive(control)["valid"]
        dev.post(1, HEADER + frame_tx, flags=2)
        malformed = dev.observe(1)
        malformed["name"] = "malformed-tx-direction"
        results["cases"].append(malformed)
        address = dev.post(1, HEADER + frame_tx, descriptor_address=SIZE + 4096)
        outside = dev.observe(1)
        outside["name"] = "out-of-range-tx-gpa"
        results["cases"].append(outside)
        # Repair only the rejected descriptor into a cycle, without advancing avail.
        head = (dev.indices[1] - 1) % NUM
        struct.pack_into("<QIHH", dev.ring, 0x3000 + head * 16,
                         address, len(HEADER + frame_tx), 1, head)
        os.eventfd_write(dev.events[1][0], 1)
        cycle = dev.observe(1)
        cycle["name"] = "cyclic-tx-chain"
        results["cases"].append(cycle)
        results["detach_avail"] = dev.detach()
        results["detach_used"] = [dev.used(queue) for queue in range(2)]
        results["post_detach_signals"] = [
            {"call": event_count(events[1]), "error": event_count(events[2])}
            for events in dev.events]
        dev.post(0)
        # Exclude the driver's explicit descriptor/avail publication from comparison.
        before = bytes(dev.ram)
        send(control, {"action": "send", "payload": frame_rx.hex()})
        receive(control)
        results["detached_observation"] = dev.observe(0, 0.1)
        results["detached_ram_unchanged"] = before == bytes(dev.ram)
    finally:
        if dev is not None:
            dev.close()
        if tap >= 0:
            os.close(tap)
        results["tasks_after_close"] = sorted(os.listdir("/proc/self/task"))
        results["fd_before"] = fd_before
        results["fd_after"] = len(os.listdir("/proc/self/fd"))
        results["backing_file_unchanged"] = backing.exists() and not any(backing.read_bytes())
        expected = ([1, 2, 1, 3, 4, 4, 4, 4, 4] if private_ring
                    else [1, 2, 1, 0x7712, 4, 5, 5, 5, 5])
        results["checks"] = {
            "nine_case_indices": [case["used"] for case in results["cases"]] == expected,
            "valid_payloads": all(case.get("payload_valid", False)
                                  for case in results["cases"][:5 + (not private_ring)]),
            "three_malformed_errors_not_completions": (
                len(results["cases"]) == 9
                and all(case["error"] == 1 and case["call"] == 0
                        for case in results["cases"][-3:])),
            "avail_is_not_used": results.get("detach_avail") == [1, 5 if private_ring else 6]
            and results.get("detach_used") == [1, 4 if private_ring else 5],
            "detach_fences_writes": results.get("detached_ram_unchanged", False),
            "private_backing_unchanged": results["backing_file_unchanged"],
            "fds_released": results["fd_before"] == results["fd_after"],
            "worker_joined": results["tasks_after_close"] == [str(os.getpid())],
        }
        output.write_text(json.dumps(results, indent=2) + "\n")
        send(control, {"action": "done"})
        control.close()
    if not all(results["checks"].values()):
        raise RuntimeError("one or more kernel characterization checks failed")


def supervise(output, private_ring=False):
    if os.geteuid() != 0:
        raise RuntimeError("supervisor requires root in an ephemeral network namespace")
    tap = os.open("/dev/net/tun", os.O_RDWR | os.O_CLOEXEC)
    child = None
    left = right = peer = None
    try:
        fcntl.ioctl(tap, 0x400454CA,
                    struct.pack("16sH22x", IFACE.encode(), 0x0002 | 0x1000 | 0x4000))
        fcntl.ioctl(tap, 0x400454CC, 1000)
        fcntl.ioctl(tap, 0x400454CB, 1)
        subprocess.run(["ip", "link", "set", "dev", IFACE,
                        "address", HOST_MAC.hex(":"), "mtu", "1500", "up"], check=True)
        os.close(tap)
        tap = -1
        peer = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETHERTYPE))
        peer.bind((IFACE, 0))
        peer.settimeout(3)
        left, right = socket.socketpair()
        left.settimeout(15)
        child = subprocess.Popen(
            [sys.executable, __file__, "--worker-fd", str(right.fileno()),
             "--output", str(output)] + (["--private-rings"] if private_ring else []),
            pass_fds=[right.fileno()])
        right.close()
        right = None
        while True:
            message = receive(left)
            if message["action"] == "done":
                break
            payload = bytes.fromhex(message["payload"])
            if message["action"] == "receive":
                send(left, {"valid": peer.recv(65536) == payload})
            elif message["action"] == "send":
                send(left, {"sent": peer.send(payload)})
            else:
                raise RuntimeError("unknown worker request")
        if child.wait(timeout=15) != 0:
            raise RuntimeError("probe worker failed")
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        for endpoint in (left, right, peer):
            if endpoint is not None:
                endpoint.close()
        if tap >= 0:
            os.close(tap)
        subprocess.run(["ip", "link", "del", "dev", IFACE],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def main():
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker-fd", type=int)
    parser.add_argument("--private-rings", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite evidence: {args.output}")
    if args.worker_fd is None:
        supervise(args.output, args.private_rings)
    else:
        worker(args.worker_fd, args.output, args.private_rings)


if __name__ == "__main__":
    main()
