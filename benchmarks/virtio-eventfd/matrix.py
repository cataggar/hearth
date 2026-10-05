#!/usr/bin/env python3
"""Timer-free all-device correctness in an explicitly private network namespace."""

import argparse
import base64
import gzip
import json
import os
from pathlib import Path
import select
import signal
import socket
import struct
import subprocess
import sys
import threading
import time

import control
import run as bench
import tap_probe


def prepare(args):
    out = bench.artifact_path(args.out)
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    kernel = bench.artifact_path(args.kernel)
    if bench.digest(kernel) != bench.KERNEL_SHA256:
        raise ValueError("unexpected kernel")
    sources = {
        "bin/busybox": Path("/usr/bin/busybox"),
        "hearth-agent": bench.artifact_path(args.agent),
        "native-vsock": bench.artifact_path(args.native),
        "native-tcp": bench.artifact_path(args.tcp),
    }
    if args.disk_probe:
        sources["disk-probe"] = bench.artifact_path(args.disk_probe)
    init = (
        "#!/bin/sh\nset -eu\n"
        "/bin/busybox mount -t devtmpfs devtmpfs /dev\n"
        "exec </dev/console >/dev/console 2>&1\n"
        "/bin/busybox mount -t proc proc /proc\n"
        "/bin/busybox mount -t sysfs sysfs /sys\n"
        "/bin/busybox mkdir -p /dev/pts\n"
        "/bin/busybox mount -t devpts devpts /dev/pts\n"
        + ("/native-vsock &\n" if args.vsock_only else "" if args.profile_only else
           "/bin/busybox ip link set lo up\n"
           "/bin/busybox ip addr add 192.0.2.2/30 dev eth0\n"
           "/bin/busybox ip link set eth0 mtu 1500 up\n"
           "echo EVENTFD_ALL_DEVICE_READY\n"
           "/native-vsock &\necho $! >/bench/vsock-pid\n"
           "/native-tcp &\necho $! >/bench/tcp-pid\n")
        +
        "exec /hearth-agent\n"
    ).encode()
    disk_script = (
        "#!/bin/sh\nset -eu\n"
        "printf ACTIVE | /bin/busybox dd of=/dev/vda bs=1 seek=8192 conv=notrunc 2>/dev/null\n"
        "while [ -f /bench/run-disk ]; do\n"
        "/bin/busybox dd if=/dev/zero of=/dev/vda bs=4096 seek=16 count=3584 conv=notrunc 2>/dev/null\n"
        "/bin/busybox sync\n"
        "done\n"
        "printf DISK-DONE >/bench/disk-done\n"
    ).encode()
    entries = [(name, b"", 0o40755) for name in ("bin", "dev", "proc", "sys", "bench")]
    entries += [(name, path.read_bytes(), 0o100755) for name, path in sources.items()]
    entries += [("bin/sh", b"busybox", 0o120777), ("disk-load", disk_script, 0o100755),
                ("init", init, 0o100755), ("TRAILER!!!", b"", 0)]
    archive = b"".join(bench.newc_entry(*entry, index + 1) for index, entry in enumerate(entries))
    (out / "init").write_bytes(init)
    (out / "disk-load").write_bytes(disk_script)
    (out / "initrd.cpio.gz").write_bytes(gzip.compress(archive, mtime=0))
    bench.save_json(out / "fixture.json", {
        "kernel": str(kernel.relative_to(bench.ROOT)), "kernel_sha256": bench.digest(kernel),
        "initrd_sha256": bench.digest(out / "initrd.cpio.gz"),
        "init_sha256": bench.digest(out / "init"), "disk_script_sha256": bench.digest(out / "disk-load"),
        "sources_sha256": {name: bench.digest(path) for name, path in sources.items()},
        "diagnostic_heartbeat_ms": 0, "guest_agent_interactive_poll_ms": 50,
        "native_probe": False, "combined": not args.profile_only,
        "transport": "synchronous-block+userspace-TAP+native-vsock+unchanged-agent",
        "unsupported": ["host-initiated CONNECT", "SDK tar/port-forward bulk"],
    })


def rpc_exec(guest, command, timeout=15):
    reply = bench.rpc(guest.connection, {"method": "exec", "cmd": command, "timeout": timeout})
    if not reply.get("ok") or reply.get("exit_code") != 0:
        raise ValueError(f"guest command failed: {reply}")
    return base64.b64decode(reply.get("stdout", ""), validate=True)


DISK_START_COMMAND = (
    "/bin/busybox test ! -e /bench/disk-pid && "
    "/bin/busybox test ! -e /bench/run-disk && "
    "/bin/busybox test ! -e /bench/disk-done && "
    "/bin/busybox touch /bench/run-disk && "
    "{ /bin/sh /disk-load >/dev/null 2>&1 & echo $! >/bench/disk-pid; } && "
    "printf STARTED"
)


class DiskProducerExecPending(RuntimeError):
    def __init__(self, identity):
        super().__init__("recorded disk producer has not completed exec")
        self.identity = identity


def disk_running(guest, expected=None, *, startup=False):
    # The unchanged agent returns raw JSON string escapes; validated numeric
    # expansions and echo keep this recipe free of quotes/backslashes.
    data = rpc_exec(guest, (
        "/bin/busybox test -f /bench/run-disk && "
        "/bin/busybox test ! -f /bench/disk-done && "
        "pid=$(/bin/busybox cat /bench/disk-pid) && "
        "case $pid in ''|*[!0-9]*) exit 1;; esac && "
        "/bin/busybox test $pid -gt 1 && "
        "/bin/busybox kill -0 $pid && "
        "/bin/busybox cat /proc/$pid/stat && /bin/busybox echo && "
        "/bin/busybox cat /proc/$pid/cmdline"
    ))
    stat, separator, command = data.partition(b"\n\n")
    prefix, stat_separator, fields_bytes = stat.rpartition(b") ")
    fields = fields_bytes.split()
    pid, comm_separator, _ = prefix.partition(b" (")
    if (not separator or not stat_separator or not comm_separator or len(fields) < 20
            or fields[0] not in (b"R", b"S", b"D", b"T", b"t", b"I", b"W", b"K", b"P")):
        raise RuntimeError("recorded disk producer is not a live disk-load shell")
    if not pid.isdigit() or not fields[19].isdigit():
        raise RuntimeError("invalid recorded disk producer identity")
    identity = {"pid": int(pid), "start_ticks": int(fields[19])}
    if identity["pid"] <= 1 or identity["start_ticks"] < 0 or (expected is not None and identity != expected):
        raise RuntimeError("recorded disk producer generation changed")
    if command != b"/bin/sh\0/disk-load\0":
        if startup and command == b"/bin/sh\0-c\0" + DISK_START_COMMAND.encode() + b"\0":
            raise DiskProducerExecPending(identity)
        raise RuntimeError("recorded disk producer is not a live disk-load shell")
    return identity


def start_disk(guest):
    if rpc_exec(guest, DISK_START_COMMAND) != b"STARTED":
        raise RuntimeError("disk background fixture did not start")
    # The child's exec may trail its parent's PID-recording RPC response.
    deadline = time.monotonic() + 5
    identity = None
    while True:
        try:
            return disk_running(guest, identity, startup=True)
        except DiskProducerExecPending as error:
            identity = error.identity
            if time.monotonic() >= deadline:
                raise
            time.sleep(.005)


class Outstanding:
    def __init__(self, connection):
        self.connection = connection
        self.payloads = [bench.native_payload(index, 65536) for index in range(16)]
        self.errors = []
        self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 16384)
        self.writer = threading.Thread(target=self.send)
        self.writer.start()

    def send(self):
        try:
            for payload in self.payloads:
                self.connection.sendall(struct.pack("<I", len(payload)) + payload)
        except OSError as error:
            self.errors.append(str(error))

    def barrier(self):
        if len(self.connection.recv(4, socket.MSG_PEEK)) != 4 or not self.writer.is_alive():
            raise RuntimeError("no actual outstanding slow-reader I/O at the pause barrier")

    def finish(self):
        responses = [bench.native_reply(self.connection, index, payload) for index, payload in enumerate(self.payloads)]
        self.writer.join(timeout=10)
        if self.writer.is_alive() or self.errors:
            raise RuntimeError(f"producer failed: {self.errors}")
        return responses

    def close(self):
        if self.writer.is_alive():
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.writer.join(timeout=10)


class Observer:
    def __init__(self, guest, object_path=None):
        self.handle = (guest.out / "irqfd-observer.stderr").open("wb")
        self.process = subprocess.Popen([
            "sudo", "-n", "timeout", "--kill-after=5", "400", "python3",
            str(bench.ROOT / "tools/perf/irqfd_cpu.py"),
            "--pid", str(guest.pid), "--start-ticks", str(guest.pid_start_ticks),
            "--object", str(bench.artifact_path(object_path) if object_path is not None
                            else bench.ROOT / ".perf/eventfd/w2/irqfd_cpu.bpf.o"),
        ], cwd=bench.ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.handle, text=True)
        try:
            if not select.select([self.process.stdout], [], [], 8)[0]:
                raise RuntimeError("bounded kernel CPU observer did not become ready")
            line = self.process.stdout.readline()
            if not line:
                raise RuntimeError("scoped kernel CPU observer failed; inspect preserved verifier diagnostics")
            self.ready = json.loads(line)
            if not self.ready.get("ready"):
                raise RuntimeError(f"kernel CPU observer not ready: {self.ready}")
        except BaseException:
            self.abort()
            raise

    def abort(self):
        if self.process.stdin is not None:
            try:
                self.process.stdin.close()
            except BrokenPipeError:
                pass
        try:
            self.process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            subprocess.run(["sudo", "-n", "kill", "-TERM", str(self.process.pid)], check=True, timeout=5)
            self.process.wait(timeout=8)
        finally:
            self.handle.close()

    def finish(self):
        try:
            self.process.stdin.write("STOP\n")
            self.process.stdin.flush()
            stdout, _ = self.process.communicate(timeout=8)
        except BaseException:
            self.abort()
            raise
        finally:
            self.handle.close()
        result = json.loads(stdout)
        if self.process.returncode != 0 or result["status"] != "passed":
            raise RuntimeError(f"incomplete kernel work accounting: {result}")
        return result

    def read(self):
        self.process.stdin.write("READ\n")
        self.process.stdin.flush()
        if not select.select([self.process.stdout], [], [], 5)[0]:
            raise RuntimeError("observer read timeout")
        result = json.loads(self.process.stdout.readline())
        if result["status"] != "passed":
            raise RuntimeError(f"invalid CPU boundary: {result}")
        return result


def correctness(args):
    if os.geteuid() == 0:
        raise ValueError("traffic controller must be nonroot")
    out = bench.artifact_path(args.out)
    os.sched_setaffinity(0, {1})
    guest, tcp, producers, observer = None, None, [], None
    result = {"status": "failed", "errors": [], "mode": args.mode, "performance_merge_eligible": False}
    binary, fixture = bench.artifact_path(args.binary), bench.artifact_path(args.fixture)
    bench.save_json(out / "manifest.json", {
        "binary_sha256": bench.digest(binary), "fixture": json.loads((fixture / "fixture.json").read_text()),
        "mode": args.mode, "cpus": [8], "client_cpus": [1], "heartbeat_ms": 0,
        "vcpus": 1, "guest_ram_mib": 512, "tap_offloads": 0,
        "classification": "all-device correctness, not candidate performance",
        "namespace": os.readlink("/proc/self/ns/net"), "runner_sha256": bench.digest(Path(__file__)),
    })
    try:
        guest = control.Guest.__new__(control.Guest)
        guest.__init__(out, binary, args.mode, fixture, disk=True, tap="hef3tap0")
        observer = Observer(guest)
        tcp = socket.create_connection(("192.0.2.2", 11000), timeout=8)
        tcp.settimeout(10)
        result["initial_agent"] = control.agent(guest, True)
        result["initial_vsock"] = bench.native_echo(guest.native_connection, 40, 64)
        result["initial_tap"] = bench.native_echo(tcp, 40, 64)
        time.sleep(1)
        result["idle_wake_vsock"] = bench.native_echo(guest.native_connection, 41, 64)
        result["idle_wake_tap"] = bench.native_echo(tcp, 41, 64)
        disk_identity = start_disk(guest)
        deadline = time.monotonic() + 5
        with (guest.path / "disk").open("rb", buffering=0) as disk:
            while True:
                disk.seek(8192)
                if disk.read(6) == b"ACTIVE":
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError("no actual block completion at concurrent barrier")
                time.sleep(0.001)
        producers = [Outstanding(guest.native_connection), Outstanding(tcp)]
        for producer in producers:
            producer.barrier()
        result["loaded_interactive"] = bench.interactive(guest.connection, "printf CONCURRENT", "CONCURRENT")
        result["disk_producer_at_pause"] = disk_running(guest, disk_identity)
        guest.api("PATCH", "/vm", {"state": "Paused"})
        before = bench.thread_roster(guest.pid)
        time.sleep(0.2)
        result["paused_all_thread_cpu_seconds"] = bench.cpu_delta(before, bench.thread_roster(guest.pid))
        if result["paused_all_thread_cpu_seconds"] != 0:
            raise RuntimeError("backend ran while acknowledged paused")
        result["snapshot"] = guest.snapshot()
        result["outstanding_sources_at_pause"] = ["live-continuous-block-producer", "native-vsock", "userspace-TAP"]
        guest.api("PATCH", "/vm", {"state": "Resumed"})
        result["vsock_messages"] = producers[0].finish()
        result["tap_messages"] = producers[1].finish()
        if rpc_exec(guest, "/bin/busybox rm /bench/run-disk; while [ ! -f /bench/disk-done ]; do /bin/busybox sleep 0.01; done; /bin/busybox cat /bench/disk-done", 20) != b"DISK-DONE":
            raise RuntimeError("active disk did not finish after resume")
        with (guest.path / "disk").open("rb") as backing:
            backing.seek(65536)
            if backing.read(14 * 1024 * 1024) != bytes(14 * 1024 * 1024):
                raise ValueError("concurrent raw disk integrity failure")
        result["host_disk_bytes_verified"] = 14 * 1024 * 1024
        result["after_resume_agent"] = control.agent(guest, True)
        guest.api("PATCH", "/vm", {"state": "Paused"})
        result["shutdown_exit_code"] = guest.shutdown()
        result["kernel_work_accounting"] = observer.finish()
        observer = None
        result["status"] = "passed"
    except (OSError, ValueError, RuntimeError, EOFError, subprocess.SubprocessError) as error:
        result["errors"].append(f"{type(error).__name__}: {error}")
    finally:
        if observer is not None:
            try:
                result["failed_window_kernel_work_accounting"] = observer.finish()
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                result["errors"].append(f"observer cleanup: {error}")
        for producer in producers:
            producer.close()
        if tcp is not None:
            tcp.close()
        if guest is not None:
            try:
                guest.close()
            except (OSError, RuntimeError, subprocess.SubprocessError, AttributeError) as error:
                result["status"] = "failed"
                result["errors"].append(f"cleanup: {error}")
    bench.save_json(out / "result.json", result)
    print(json.dumps(result))
    return 0 if result["status"] == "passed" else 1


def namespace(args):
    tap_probe.require_private_namespace()
    uid, gid = int(os.environ["SUDO_UID"]), int(os.environ["SUDO_GID"])
    if uid <= 0 or gid <= 0:
        raise ValueError("private bootstrap must originate from nonroot")
    out = bench.artifact_path(args.out)
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chown(out, uid, gid)
    tap_probe.setup_tap(uid)

    def demote():
        os.setgroups([])
        os.setgid(gid)
        os.setuid(uid)
        os.sched_setaffinity(0, {1})

    argv = [sys.executable, str(Path(__file__)), "--child", "--out", str(out),
            "--binary", args.binary, "--fixture", args.fixture, "--mode", args.mode]
    child_process = subprocess.Popen(argv, cwd=bench.ROOT, preexec_fn=demote)
    try:
        return child_process.wait(timeout=100)
    except BaseException:
        child_process.send_signal(signal.SIGTERM)
        try:
            child_process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            child_process.kill()
            child_process.wait(timeout=5)
        raise


def main():
    os.umask(0o077)
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(RuntimeError("bounded matrix interrupted")))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--binary")
    parser.add_argument("--fixture")
    parser.add_argument("--mode", choices=["C00", "C10", "C01", "C11"])
    parser.add_argument("--kernel")
    parser.add_argument("--agent")
    parser.add_argument("--native")
    parser.add_argument("--tcp")
    parser.add_argument("--disk-probe")
    parser.add_argument("--profile-only", action="store_true")
    parser.add_argument("--vsock-only", action="store_true")
    args = parser.parse_args()
    if args.prepare:
        prepare(args)
        return 0
    return correctness(args) if args.child else namespace(args)


if __name__ == "__main__":
    raise SystemExit(main())
