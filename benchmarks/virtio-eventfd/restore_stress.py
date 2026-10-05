#!/usr/bin/env python3
"""Repeated active mixed-device v2 capture and real new-process restore."""

import argparse
import gzip
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

import control
import matrix
import run as bench
import tap_probe


def connect_tcp():
    deadline = time.monotonic() + 8
    while True:
        try:
            connection = socket.create_connection(("192.0.2.2", 11000), timeout=2)
            connection.settimeout(10)
            return connection
        except ConnectionRefusedError:
            if time.monotonic() >= deadline:
                raise
            # Startup/relaunch only. Never generate wake traffic in idle
            # measurements or substitute polling for the VMM readiness owner.
            time.sleep(.005)


def prepare(args):
    source = bench.artifact_path(args.prepare_from)
    out = bench.artifact_path(args.out)
    metadata = json.loads((source / "fixture.json").read_text())
    if not metadata.get("combined") or bench.digest(source / "initrd.cpio.gz") != metadata["initrd_sha256"]:
        raise ValueError("preparation requires the pinned all-device fixture")
    archive = gzip.decompress((source / "initrd.cpio.gz").read_bytes())
    entries, offset = [], 0
    while offset < len(archive):
        header = archive[offset:offset + 110]
        if header[:6] != b"070701":
            raise ValueError("unexpected fixture cpio header")
        fields = [int(header[6 + index * 8:14 + index * 8], 16) for index in range(13)]
        mode, size, namesize = fields[1], fields[6], fields[11]
        name = archive[offset + 110:offset + 110 + namesize - 1].decode()
        start = (offset + 110 + namesize + 3) & ~3
        data = archive[start:start + size]
        offset = (start + size + 3) & ~3
        if name == "init":
            old = b"/native-vsock &\n/native-tcp &\n"
            new = (b"/native-vsock &\necho $! >/bench/vsock-pid\n"
                   b"/native-tcp &\necho $! >/bench/tcp-pid\n")
            if old not in data:
                raise ValueError("unknown native app startup fixture")
            data = data.replace(old, new)
        if name == "native-tcp" and args.tcp_binary:
            data = bench.artifact_path(args.tcp_binary).read_bytes()
        entries.append((name, data, mode))
        if name == "TRAILER!!!":
            break
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    init = next(data for name, data, _ in entries if name == "init")
    (out / "init").write_bytes(init)
    (out / "initrd.cpio.gz").write_bytes(gzip.compress(b"".join(
        bench.newc_entry(*entry, index + 1) for index, entry in enumerate(entries)), mtime=0))
    metadata.update({
        "init_sha256": bench.digest(out / "init"), "initrd_sha256": bench.digest(out / "initrd.cpio.gz"),
        "source_fixture_sha256": bench.digest(source / "fixture.json"),
        "boot_args": "console=ttyS0 nokaslr reboot=t panic=1 pci=off nomodules",
        "probe_pid_tracking": True, "classification": "new lifecycle fixture, not frozen performance fixture",
    })
    if args.tcp_binary:
        metadata["sources_sha256"]["native-tcp"] = bench.digest(bench.artifact_path(args.tcp_binary))
        metadata["tcp_reuseaddr"] = True
    bench.save_json(out / "fixture.json", metadata)
    return 0


def cycle(args, out):
    out.mkdir(mode=0o700)
    source, restored, tcp, restored_tcp, producers = None, None, None, None, []
    result = {"status": "failed", "errors": [], "mode": args.mode,
              "performance_merge_eligible": False}
    try:
        binary, fixture = bench.artifact_path(args.binary), bench.artifact_path(args.fixture)
        source = control.Guest.__new__(control.Guest)
        source.__init__(out, binary, args.mode, fixture, disk=True, tap="hef3tap0",
                        vm_cpu=getattr(args, "vm_cpu", 8))
        result["before"] = control.agent(source, True)
        tcp = connect_tcp()
        matrix.rpc_exec(source, "/bin/busybox touch /bench/run-disk; /bin/sh /disk-load >/dev/null 2>&1 & printf STARTED")
        deadline = time.monotonic() + 5
        with (source.path / "disk").open("rb", buffering=0) as disk:
            while True:
                disk.seek(8192)
                if disk.read(6) == b"ACTIVE":
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError("actual disk completion absent at mixed-I/O barrier")
                time.sleep(.001)
        producers = [matrix.Outstanding(source.native_connection), matrix.Outstanding(tcp)]
        for producer in producers:
            producer.barrier()
        if matrix.rpc_exec(source, "/bin/busybox test -f /bench/run-disk && /bin/busybox test ! -f /bench/disk-done; printf RUNNING") != b"RUNNING":
            raise RuntimeError("disk producer ended before capture")
        source.api("PATCH", "/vm", {"state": "Paused"})
        before = bench.thread_roster(source.pid)
        time.sleep(.1)
        result["paused_all_task_cpu_seconds"] = bench.cpu_delta(before, bench.thread_roster(source.pid))
        if result["paused_all_task_cpu_seconds"] != 0:
            raise RuntimeError("acknowledged pause did not fence all mutation owners")
        result["snapshot"] = source.snapshot()
        result["snapshot_sha256"] = {name: bench.digest(out / name) for name in ("state", "memory", "disk")}
        result["outstanding_sources_at_capture"] = ["block-producer", "vsock-slow-reader", "TAP-slow-reader"]
        source.api("PATCH", "/vm", {"state": "Resumed"})
        result["source_vsock"] = producers[0].finish()
        result["source_tap"] = producers[1].finish()
        for producer in producers:
            producer.close()
        producers = []
        tcp.close()
        tcp = None
        result["source_exit"] = source.shutdown()
        source.close()
        source = None

        destination = out / "restore"
        destination.mkdir(mode=0o700)
        restored = control.Guest.__new__(control.Guest)
        restored.__init__(destination, binary, args.mode, fixture, out, disk=True,
                          tap="hef3tap0", restore_api=True, accept_native=False,
                          vm_cpu=getattr(args, "vm_cpu", 8))
        # v2 intentionally does not serialize live host connections. The
        # unchanged agent reconnects; the fixture explicitly restarts its two
        # native apps rather than promising transparent stream preservation.
        pids = matrix.rpc_exec(restored, "/bin/busybox cat /bench/vsock-pid /bench/tcp-pid").split()
        if len(pids) != 2 or any(not pid.isdigit() or int(pid) <= 1 for pid in pids):
            raise ValueError("invalid recorded owned guest probe PIDs")
        command = (
            "/bin/busybox kill -9 " + " ".join(pid.decode() for pid in pids)
            + "; /native-vsock >/bench/vsock-restarted 2>&1 & "
            "/native-tcp >/bench/tcp-restarted 2>&1 & printf RESTARTED"
        )
        if matrix.rpc_exec(restored, command) != b"RESTARTED":
            raise RuntimeError("fixture applications did not restart after transport reset")
        restored.native_connection, _ = restored.native_listener.accept()
        restored.native_connection.settimeout(10)
        restored_tcp = connect_tcp()
        result["restored_vsock"] = bench.native_backpressure(restored.native_connection, 0, 65536)
        result["restored_tap"] = bench.native_backpressure(restored_tcp, 0, 65536)
        if matrix.rpc_exec(restored, "/bin/busybox rm /bench/run-disk; while [ ! -f /bench/disk-done ]; do /bin/busybox sleep 0.01; done; /bin/busybox cat /bench/disk-done", 20) != b"DISK-DONE":
            raise RuntimeError("restored active block producer did not complete")
        with (restored.path / "disk").open("rb") as backing:
            backing.seek(4096)
            if backing.read(7) != b"EVENTFD":
                raise ValueError("snapshot lost source's actual disk marker")
            backing.seek(65536)
            if backing.read(14 * 1024 * 1024) != bytes(14 * 1024 * 1024):
                raise ValueError("restored producer lost/corrupted disk data")
        result["restored_disk_bytes_verified"] = 14 * 1024 * 1024
        result["restored_agent"] = control.agent(restored, True)
        restored.api("PATCH", "/vm", {"state": "Paused"})
        result["restore_exit"] = restored.shutdown()
        result["status"] = "passed"
    except (OSError, ValueError, RuntimeError, EOFError, subprocess.SubprocessError) as error:
        result["errors"].append(f"{type(error).__name__}: {error}")
        if restored is not None and restored.connection is not None:
            try:
                result["guest_probe_failure_logs"] = matrix.rpc_exec(
                    restored, "/bin/busybox cat /bench/tcp-restarted /bench/vsock-restarted", 3).decode(errors="replace")
            except (OSError, ValueError, RuntimeError, EOFError):
                pass
    finally:
        for producer in producers:
            producer.close()
        for connection in (tcp, restored_tcp):
            if connection is not None:
                connection.close()
        for guest in (source, restored):
            if guest is not None:
                try:
                    guest.close()
                except (OSError, RuntimeError, AttributeError, subprocess.SubprocessError) as error:
                    result["status"] = "failed"
                    result["errors"].append(f"cleanup: {error}")
        if result["status"] == "passed":
            for name in ("state", "memory", "disk"):
                (out / name).unlink()
            result["bulky_images_removed_after_verified_restore"] = True
    bench.save_json(out / "result.json", result)
    return result


def child(args):
    if os.geteuid() == 0:
        raise ValueError("stress controller must be nonroot")
    os.sched_setaffinity(0, {1})
    out = bench.artifact_path(args.out)
    results = []
    for index in range(args.cycles):
        result = cycle(args, out / f"{index:02d}")
        results.append(result)
        print(json.dumps({"cycle": index, "mode": args.mode, "status": result["status"],
                          "errors": result["errors"]}), flush=True)
        if result["status"] != "passed":
            break
    passed = len(results) == args.cycles and all(row["status"] == "passed" for row in results)
    bench.save_json(out / "result.json", {
        "status": "passed" if passed else "failed", "mode": args.mode,
        "actual_cycles": len(results), "requested_cycles": args.cycles,
        "passed": sum(row["status"] == "passed" for row in results),
        "binary_sha256": bench.digest(bench.artifact_path(args.binary)),
        "runner_sha256": bench.digest(Path(__file__)), "heartbeat_ms": 0,
        "guest_application_reconnection": "fixture relaunch; unchanged agent transport-reset reconnect",
        "performance_merge_eligible": False,
    })
    return 0 if passed else 1


def main():
    os.umask(0o077)
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(RuntimeError("bounded stress interrupted")))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--binary")
    parser.add_argument("--fixture")
    parser.add_argument("--prepare-from")
    parser.add_argument("--tcp-binary")
    parser.add_argument("--mode", choices=["C00", "C10", "C01", "C11"])
    parser.add_argument("--cycles", type=int, default=20)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.prepare_from:
        return prepare(args)
    if not all((args.binary, args.fixture, args.mode)):
        parser.error("stress requires --binary, --fixture and --mode")
    if not 1 <= args.cycles <= 20:
        parser.error("cycles must be bounded to 1..20")
    if args.child:
        return child(args)
    tap_probe.require_private_namespace()
    uid, gid = int(os.environ["SUDO_UID"]), int(os.environ["SUDO_GID"])
    if uid <= 0 or gid <= 0:
        raise ValueError("bootstrap requires original nonroot identity")
    out = bench.artifact_path(args.out)
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chown(out, uid, gid)
    tap_probe.setup_tap(uid)

    def demote():
        os.setgroups([])
        os.setgid(gid)
        os.setuid(uid)

    command = [sys.executable, str(Path(__file__)), "--child", "--out", str(out),
               "--binary", args.binary, "--fixture", args.fixture, "--mode", args.mode,
               "--cycles", str(args.cycles)]
    process = subprocess.Popen(command, cwd=bench.ROOT, preexec_fn=demote)
    try:
        return process.wait(timeout=600)
    except BaseException:
        process.send_signal(signal.SIGTERM)
        process.wait(timeout=20)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
