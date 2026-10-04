#!/usr/bin/env python3
"""Real enforced-jail controlled-mode correctness and lifecycle fixtures."""

import argparse
import base64
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import struct
import subprocess
import threading
import time

import run as bench
import probe_jail

ROOT = bench.ROOT
spec = importlib.util.spec_from_file_location("jail_support", ROOT / "tools/perf/jail_support.py")
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)


class Guest(support.OwnedVm):
    def __init__(self, out, binary, mode, fixture, restore=None, disk=False, tap=None, restore_api=False, cli_only=False, accept_native=True):
        super().__init__(out / "j")
        self.listener = None
        self.connection = None
        self.socket_path = None
        self.native_listener = None
        self.native_connection = None
        self.out = out
        self.mode = mode
        self.fixture = json.loads((fixture / "fixture.json").read_text())
        if self.fixture.get("diagnostic_heartbeat_ms") != 0:
            raise ValueError("controlled correctness requires a no-heartbeat fixture")
        self.native = self.fixture["native_probe"]
        self.path.mkdir(mode=0o700)
        self.path_created = True
        port = 11000 if self.native else 1024
        self.socket_path = self.path / f"vsock_{port}"
        if len(str(self.socket_path).encode()) >= 108:
            raise ValueError("private UDS path exceeds sockaddr_un")
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(str(self.socket_path))
        self.listener.listen(8)
        self.listener.settimeout(8)
        if self.fixture.get("combined"):
            self.native_listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.native_listener.bind(str(self.path / "vsock_11000"))
            self.native_listener.listen(8)
            self.native_listener.settimeout(8)
        kernel = bench.artifact_path(self.fixture["kernel"])
        initrd = fixture / "initrd.cpio.gz"
        if bench.digest(kernel) != self.fixture["kernel_sha256"] or bench.digest(initrd) != self.fixture["initrd_sha256"]:
            raise ValueError("fixture changed")
        for source, name in ((kernel, "bzImage"), (initrd, "initrd.cpio.gz")):
            shutil.copyfile(source, self.path / name)
        argv = [
            "sudo", "-n", "taskset", "-c", "8", str(binary),
            "--jail", str(self.path), "--jail-uid", str(os.getuid()), "--jail-gid", str(os.getgid()),
            "--virtio-mode", mode,
        ]
        if not cli_only:
            argv += ["--api-sock", "/api.sock"]
        if tap:
            # Jail device admission precedes API network configuration.
            argv += ["--tap", tap]
        if restore:
            for name in ("state", "memory"):
                shutil.copyfile(restore / name, self.path / name)
            argv += ["--vsock-cid", "43", "--vsock-uds", "/vsock"]
            if not restore_api:
                argv += ["--restore", "--vmstate-path", "/state", "--mem-path", "/memory"]
            if disk:
                shutil.copyfile(restore / "disk", self.path / "disk")
                argv += ["--disk", "/disk"]
        elif disk:
            with (self.path / "disk").open("wb") as file:
                block = bytes([0xA5]) * (1024 * 1024)
                for _ in range(16):
                    file.write(block)
        if cli_only and not restore:
            argv += ["/bzImage", "/initrd.cpio.gz", "console=ttyS0 nokaslr reboot=t panic=1 pci=off nomodules",
                     "--vsock-cid", "43", "--vsock-uds", "/vsock"]
            if disk:
                argv += ["--disk", "/disk"]
        self.stdout = (out / "serial.txt").open("wb")
        self.stderr = (out / "vmm.stderr").open("wb")
        bench.save_json(out / "command.json", {"argv": argv, "cwd": str(ROOT), "mode": mode})
        self.process = subprocess.Popen(argv, cwd=ROOT, stdout=self.stdout, stderr=self.stderr, start_new_session=True)
        deadline = time.monotonic() + 10
        while not cli_only and not (self.path / "api.sock").exists():
            if self.process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("actual API did not become ready")
            time.sleep(0.02)
        deadline = time.monotonic() + 5
        while True:
            try:
                self.pid = self.find_vm_pid()
                break
            except RuntimeError:
                if self.process.poll() is not None or time.monotonic() > deadline:
                    raise
                time.sleep(.01)
        self.pid_start_ticks = support.start_ticks(self.pid)
        if not cli_only and (not restore or restore_api):
            if not restore_api:
                self.api("PUT", "/machine-config", {"mem_size_mib": 512, "vcpu_count": 1})
                self.api("PUT", "/boot-source", {
                    "kernel_image_path": "/bzImage", "initrd_path": "/initrd.cpio.gz",
                    "boot_args": self.fixture.get("boot_args", "console=ttyS0 nokaslr reboot=k panic=1 pci=off nomodules"),
                })
            if disk:
                self.api("PUT", "/drives/root", {"drive_id": "root", "path_on_host": "/disk", "is_root_device": False, "is_read_only": False})
            if tap:
                self.api("PUT", "/network-interfaces/eth0", {"iface_id": "eth0", "host_dev_name": tap})
            self.api("PUT", "/vsock", {"guest_cid": 43, "uds_path": "/vsock"})
            if restore_api:
                self.api("PUT", "/snapshot/load", {"snapshot_path": "state", "mem_file_path": "memory"})
            self.api("PUT", "/actions", {"action_type": "InstanceStart"})
        try:
            self.connection, _ = self.listener.accept()
        except TimeoutError as error:
            raise RuntimeError(f"guest connect timed out; owned supervisor status={self.process.poll()}") from error
        self.connection.settimeout(5)
        if self.native_listener is not None and accept_native:
            self.native_connection, _ = self.native_listener.accept()
            self.native_connection.settimeout(10)
        inspected = subprocess.run(
            ["sudo", "-n", "python3", "-c", probe_jail.INSPECT, str(self.process.pid)],
            cwd=ROOT, capture_output=True, check=True, timeout=5,
        )
        roster = json.loads(inspected.stdout)
        bench.save_json(out / "isolation.json", roster)
        if not probe_jail.enforced_roster(roster, os.getuid(), os.getgid()):
            raise RuntimeError("a real VMM task escaped the enforced non-root jail")

    def shutdown(self):
        self.api("PUT", "/actions", {"action_type": "SendCtrlAltDel"})
        code = self.process.wait(timeout=10)
        if code != 0:
            raise RuntimeError(f"API shutdown did not join owners cleanly: {code}")
        return code

    def snapshot(self):
        self.api("PUT", "/snapshot/create", {"snapshot_path": "state", "mem_file_path": "memory"})
        header = (self.path / "state").read_bytes()[:32]
        if struct.unpack_from("<I", header, 16)[0] != 2:
            raise ValueError("snapshot compatibility version changed")
        result = {"version": 2, "memory_bytes": (self.path / "memory").stat().st_size}
        for name in ("state", "memory", "disk"):
            if (self.path / name).exists():
                shutil.copyfile(self.path / name, self.out / name)
        return result

    def close(self):
        for connection in (self.connection, self.listener, self.native_connection, self.native_listener):
            if connection is not None:
                connection.close()
        super().close()
        if self.path_created:
            exit_record = self.path / "exit.json"
            if exit_record.exists():
                shutil.copyfile(exit_record, self.out / "teardown.json")
            if self.socket_path is not None:
                self.socket_path.unlink(missing_ok=True)
            subprocess.run(["sudo", "-n", "rm", "-rf", "--", str(self.path)], cwd=ROOT, check=True, timeout=10)


def agent(guest, disk):
    ping = bench.rpc(guest.connection, {"method": "ping"})
    if not ping.get("ok"):
        raise ValueError(f"agent ping failed: {ping}")
    command = "printf EVENTFD"
    if disk:
        command = "printf EVENTFD | /bin/busybox dd of=/dev/vda bs=1 seek=4096 conv=notrunc 2>/dev/null && /bin/busybox sync && /bin/busybox dd if=/dev/vda bs=1 skip=4096 count=7 2>/dev/null"
    reply = bench.rpc(guest.connection, {"method": "exec", "cmd": command, "timeout": 5})
    if not reply.get("ok") or reply.get("exit_code") != 0 or base64.b64decode(reply.get("stdout", ""), validate=True) != b"EVENTFD":
        raise ValueError(f"agent/disk integrity failure: {reply}")
    pty = bench.interactive(guest.connection, "printf PTY", "PTY")
    return {"ping": ping, "exec": reply, "interactive": pty, "agent_poll_ms": 50}


def active_pause(guest):
    errors = []
    responses = []
    payloads = [bench.native_payload(index, 65536) for index in range(16)]

    def send():
        try:
            for payload in payloads:
                guest.connection.sendall(struct.pack("<I", len(payload)) + payload)
        except OSError as error:
            errors.append(str(error))

    writer = threading.Thread(target=send)
    guest.connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 16384)
    writer.start()
    try:
        # Observe actual reply bytes without consuming them: this is a real
        # outstanding I/O barrier, not a timer guessing when the guest runs.
        if not guest.connection.recv(4, socket.MSG_PEEK):
            raise EOFError("guest closed during active-I/O barrier")
        active_writer = writer.is_alive()
        if not active_writer:
            raise RuntimeError("the producer finished before the active-I/O pause barrier")
        guest.api("PATCH", "/vm", {"state": "Paused"})
        state = json.loads(guest.api("GET", "/vm"))
        if state["state"] != "Paused":
            raise ValueError(f"pause was not acknowledged: {state}")
        before = bench.thread_roster(guest.pid)
        time.sleep(0.2)
        after = bench.thread_roster(guest.pid)
        cpu = bench.cpu_delta(before, after)
        snapshot = guest.snapshot()
        guest.api("PATCH", "/vm", {"state": "Resumed"})
        for index, payload in enumerate(payloads):
            responses.append(bench.native_reply(guest.connection, index, payload))
        writer.join(timeout=5)
        if writer.is_alive() or errors:
            raise RuntimeError(f"active writer did not complete: {errors}")
        return {"messages": responses, "producer_outstanding_at_pause": active_writer, "paused_all_thread_cpu_seconds": cpu, "snapshot": snapshot}
    finally:
        if writer.is_alive():
            try:
                guest.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            writer.join(timeout=5)

def disconnect_pending(guest):
    bench.send_message(guest.connection, {
        "method": "exec",
        "cmd": "/bin/busybox dd if=/dev/zero bs=65536 count=16 2>/dev/null",
        "timeout": 5,
    })
    if len(guest.connection.recv(4, socket.MSG_PEEK)) != 4:
        raise EOFError("no live response at the disconnect barrier")
    guest.connection.shutdown(socket.SHUT_RDWR)
    guest.connection.close()
    guest.connection = None
    guest.connection, _ = guest.listener.accept()
    guest.connection.settimeout(5)
    ping = bench.rpc(guest.connection, {"method": "ping"})
    if not ping.get("ok"):
        raise ValueError(f"agent reconnect after pending-write close failed: {ping}")
    return {"response_observed_before_close": True, "guest_reconnected": True, "ping": ping}

def active_disk_pause(guest):
    replies, errors = [], []
    command = (
        "printf ACTIVE | /bin/busybox dd of=/dev/vda bs=1 seek=8192 conv=notrunc 2>/dev/null && "
        "/bin/busybox dd if=/dev/zero of=/dev/vda bs=4096 seek=16 count=3584 conv=notrunc 2>/dev/null && "
        "/bin/busybox sync && printf ACTIVE-DONE"
    )

    def execute():
        try:
            replies.append(bench.rpc(guest.connection, {"method": "exec", "cmd": command, "timeout": 20}))
        except (OSError, ValueError, EOFError) as error:
            errors.append(str(error))

    producer = threading.Thread(target=execute)
    producer.start()
    try:
        deadline = time.monotonic() + 5
        with (guest.path / "disk").open("rb", buffering=0) as backing:
            while True:
                backing.seek(8192)
                if backing.read(6) == b"ACTIVE":
                    break
                if not producer.is_alive() or time.monotonic() > deadline:
                    raise RuntimeError("active block marker did not appear before producer completion")
                time.sleep(0.001)
        if not producer.is_alive():
            raise RuntimeError("disk producer completed before pause admission")
        guest.api("PATCH", "/vm", {"state": "Paused"})
        before = bench.thread_roster(guest.pid)
        time.sleep(0.2)
        paused_cpu = bench.cpu_delta(before, bench.thread_roster(guest.pid))
        saved = guest.snapshot()
        guest.api("PATCH", "/vm", {"state": "Resumed"})
        producer.join(timeout=20)
        if producer.is_alive() or errors or len(replies) != 1:
            raise RuntimeError(f"active disk producer did not finish after resume: {errors}")
        reply = replies[0]
        if reply.get("exit_code") != 0 or base64.b64decode(reply.get("stdout", ""), validate=True) != b"ACTIVE-DONE":
            raise ValueError(f"active disk completion lost: {reply}")
        with (guest.path / "disk").open("rb") as backing:
            backing.seek(65536)
            if backing.read(14 * 1024 * 1024) != bytes(14 * 1024 * 1024):
                raise ValueError("active disk contents do not match guest write")
        return {"producer_outstanding_at_pause": True, "paused_all_thread_cpu_seconds": paused_cpu,
                "snapshot": saved, "reply": reply, "host_bulk_bytes_verified": 14 * 1024 * 1024}
    finally:
        if producer.is_alive():
            try:
                guest.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            producer.join(timeout=5)


def main():
    os.umask(0o077)
    def interrupted(_signum, _frame):
        raise RuntimeError("bounded fixture interrupted")
    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--binary", required=True)
    parser.add_argument("--mode", choices=["C00", "C10", "C01", "C11"], required=True)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--restore-from")
    parser.add_argument("--restore-api", action="store_true")
    parser.add_argument("--cli-only", action="store_true")
    parser.add_argument("--disk", action="store_true")
    parser.add_argument("--lifecycle", action="store_true")
    parser.add_argument("--disconnect-pending", action="store_true")
    parser.add_argument("--active-disk", action="store_true")
    parser.add_argument("--shutdown-paused", action="store_true")
    args = parser.parse_args()
    if args.active_disk and not args.disk:
        parser.error("--active-disk requires --disk")
    if args.restore_api and (not args.restore_from or args.cli_only):
        parser.error("--restore-api requires --restore-from and API mode")
    if args.cli_only and (args.lifecycle or args.active_disk or args.shutdown_paused):
        parser.error("CLI-only probe cannot use API lifecycle actions")
    out = bench.artifact_path(args.out)
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    binary, fixture = bench.artifact_path(args.binary), bench.artifact_path(args.fixture)
    restore = bench.artifact_path(args.restore_from) if args.restore_from else None
    os.sched_setaffinity(0, {1})
    result = {"status": "failed", "errors": [], "performance_merge_eligible": False, "mode": args.mode}
    guest = None
    bench.save_json(out / "manifest.json", {
        "binary_sha256": bench.digest(binary), "mode": args.mode, "cpus": [8], "client_cpus": [1],
        "heartbeat_ms": 0, "guest_ram_mib": 512, "vcpus": 1,
        "source_files_sha256": {str(path.relative_to(ROOT)): bench.digest(path) for path in (ROOT / "vmm/src").rglob("*.zig")},
        "source_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, check=True).stdout.decode().strip(),
        "restore_from": str(restore) if restore else None, "runner_sha256": bench.digest(Path(__file__)),
        "qualification": "correctness only, not performance adoption",
        "fresh_disk_fill_byte": 0xA5 if args.disk and not restore else None,
    })
    try:
        guest = Guest.__new__(Guest)
        guest.__init__(out, binary, args.mode, fixture, restore, args.disk, restore_api=args.restore_api, cli_only=args.cli_only)
        time.sleep(1)
        if guest.native:
            result["native"] = active_pause(guest) if args.lifecycle else bench.native_backpressure(guest.connection, 0, 65536)
        else:
            if args.disconnect_pending:
                result["disconnect_pending"] = disconnect_pending(guest)
            if restore and args.disk:
                check = bench.rpc(guest.connection, {
                    "method": "exec", "cmd": "/bin/busybox dd if=/dev/vda bs=1 skip=4096 count=7 2>/dev/null", "timeout": 5,
                })
                if check.get("exit_code") != 0 or base64.b64decode(check.get("stdout", ""), validate=True) != b"EVENTFD":
                    raise ValueError(f"restored disk did not preserve the previous marker: {check}")
                result["restored_disk"] = check
            result["agent"] = agent(guest, args.disk)
            if args.active_disk:
                result["active_disk"] = active_disk_pause(guest)
                result["after_resume"] = agent(guest, args.disk)
            elif args.lifecycle:
                guest.api("PATCH", "/vm", {"state": "Paused"})
                result["snapshot"] = guest.snapshot()
                guest.api("PATCH", "/vm", {"state": "Resumed"})
                result["after_resume"] = agent(guest, args.disk)
            if args.disk:
                with (guest.path / "disk").open("rb") as backing:
                    backing.seek(4096)
                    marker = backing.read(7)
                if marker != b"EVENTFD":
                    raise ValueError("guest success did not persist the real host disk marker")
                result["host_disk_marker"] = marker.decode()
            if restore and args.disk:
                with (guest.path / "disk").open("rb") as backing:
                    backing.seek(65536)
                    if backing.read(14 * 1024 * 1024) != bytes(14 * 1024 * 1024):
                        raise ValueError("restored active block producer did not finish intact")
                result["restored_active_block_bytes_verified"] = 14 * 1024 * 1024
        if args.shutdown_paused:
            guest.api("PATCH", "/vm", {"state": "Paused"})
            result["shutdown_from_acknowledged_pause"] = json.loads(guest.api("GET", "/vm"))["state"] == "Paused"
        if args.cli_only:
            bench.send_message(guest.connection, {"method": "exec", "cmd": "/bin/busybox reboot -f", "timeout": 5})
            code = guest.process.wait(timeout=15)
            if code != 0:
                raise RuntimeError(f"CLI guest shutdown failed: {code}")
            result["shutdown_exit_code"] = code
            result["actual_cli_shutdown"] = "KVM_EXIT_SHUTDOWN" if "guest shutdown (triple fault)" in (out / "vmm.stderr").read_text() else "other"
        else:
            result["shutdown_exit_code"] = guest.shutdown()
        result["status"] = "passed"
    except (OSError, ValueError, RuntimeError, EOFError, subprocess.SubprocessError) as error:
        result["errors"].append(f"{type(error).__name__}: {error}")
    finally:
        if guest is not None:
            try:
                guest.close()
            except (OSError, RuntimeError, subprocess.SubprocessError, AttributeError) as error:
                result["status"] = "failed"
                result["errors"].append(f"owned cleanup: {error}")
    bench.save_json(out / "result.json", result)
    print(json.dumps(result))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
