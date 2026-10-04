#!/usr/bin/env python3
"""Private-TAP prerequisite diagnostic; never a controlled-mode benchmark."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import struct
import subprocess
import sys
import time

from probe_jail import INSPECT, enforced_roster
from run import (
    ROOT, artifact_path, cpu_delta, digest, host_cpu_delta,
    native_backpressure, native_echo, save_json, thread_roster,
)


def require_private_namespace():
    if os.geteuid() != 0:
        raise ValueError("root is required only for private namespace/jail bootstrap")
    if Path("/proc/self/ns/net").stat().st_ino == Path("/proc/1/ns/net").stat().st_ino:
        raise ValueError("refusing network changes outside an unshared network namespace")


def client(args):
    if os.geteuid() == 0:
        raise ValueError("the host traffic client must be nonroot")
    result = {"status": "failed", "responses": [], "phases": [], "failures": [], "client_uid": os.getuid()}

    def checked(name, operation):
        phase = {"name": name, "status": "failed", "started_monotonic": time.monotonic()}
        result["phases"].append(phase)
        response = operation()
        phase["elapsed_seconds"] = time.monotonic() - phase["started_monotonic"]
        phase["status"] = "passed"
        result["responses"].append(response)

    try:
        started = time.monotonic()
        with socket.create_connection(("192.0.2.2", 11000), timeout=2) as connection:
            connection.settimeout(2)
            result["connect_ms"] = (time.monotonic() - started) * 1000
            checked("initial-64B-echo", lambda: native_echo(connection, 0, 64))
            checked("initial-8x64KiB-slow-reader", lambda: native_backpressure(connection, 1, 65536))
            time.sleep(2)
            checked("64B-echo-after-2s-silence", lambda: native_echo(connection, 16, 64))
            time.sleep(2)
            checked("8x64KiB-slow-reader-after-2s-silence", lambda: native_backpressure(connection, 3, 65536))
            result["status"] = "passed"
    except (OSError, EOFError, ValueError, RuntimeError) as error:
        result["failures"].append(f"{type(error).__name__}: {error}")
    save_json(artifact_path(args.out) / "client-result.json", result)
    return 0 if result["status"] == "passed" else 1


def setup_tap(uid):
    name = "hef3tap0"
    fd = os.open("/dev/net/tun", os.O_RDWR | os.O_CLOEXEC)
    try:
        fcntl.ioctl(fd, 0x400454CA, struct.pack("16sH22x", name.encode(), 0x0002 | 0x1000 | 0x4000))
        fcntl.ioctl(fd, 0x400454CC, uid)
        fcntl.ioctl(fd, 0x400454CB, 1)
        fcntl.ioctl(fd, 0x400454D0, 0)
    finally:
        os.close(fd)
    for arguments in (
        ["link", "set", "lo", "up"],
        ["addr", "add", "192.0.2.1/30", "dev", name],
        ["link", "set", name, "mtu", "1500", "up"],
    ):
        subprocess.run(["/usr/bin/busybox", "ip", *arguments], check=True, cwd=ROOT, timeout=5)
    return name


def supervise(args):
    require_private_namespace()
    if args.uid <= 0 or args.gid <= 0:
        raise ValueError("fixture UID/GID must be nonroot")
    if (args.uid, args.gid) != (int(os.environ.get("SUDO_UID", "0")), int(os.environ.get("SUDO_GID", "0"))):
        raise ValueError("fixture UID/GID must match the invoking nonroot sudo account")
    out = artifact_path(args.out)
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chown(out, args.uid, args.gid)

    def record(name, data):
        path = out / name
        save_json(path, data)
        os.chown(path, args.uid, args.gid)

    def demote_client():
        os.setgroups([])
        os.setgid(args.gid)
        os.setuid(args.uid)
        os.sched_setaffinity(0, {args.client_cpu})

    allowed = os.sched_getaffinity(0)
    siblings = Path(f"/sys/devices/system/cpu/cpu{args.cpu}/topology/thread_siblings_list").read_text().strip()
    sibling_cpus = set()
    for part in siblings.split(","):
        bounds = part.split("-")
        sibling_cpus.update(range(int(bounds[0]), int(bounds[-1]) + 1))
    if {args.cpu, args.client_cpu} - allowed or args.client_cpu in sibling_cpus:
        raise ValueError("client and VMM affinity must be allowed and on separate physical cores")

    jail, child, peer = out / "jail", None, None
    serial_path = out / "guest-serial.txt"
    result = {"status": "failed", "errors": [], "performance_merge_eligible": False}
    manifest = {
        "classification": "native protocol fixture self-test" if args.selftest else "enforced-jail TAP prerequisite diagnostic",
        "source_baseline": "b07f73b26b8ae876928d9c515b94bba1e9945870",
        "label": args.label, "cpus": [args.cpu], "client_cpus": [args.client_cpu],
        "namespace": os.readlink("/proc/self/ns/net"), "host_kernel": os.uname().release,
        "heartbeat_ms": 0, "sdk_connect_used": False, "uplink": None, "nat": None,
        "host": "192.0.2.1/30", "guest": "192.0.2.2/30", "mtu": 1500,
        "tap_offloads": 0, "tap_flags": "IFF_TAP|IFF_NO_PI|IFF_VNET_HDR",
        "runner_sha256": digest(Path(__file__)), "client_uid": args.uid, "client_gid": args.gid,
        "vmm_uid_after_bootstrap": args.uid, "vmm_gid_after_bootstrap": args.gid,
        "vcpus": 1, "guest_ram_mib": 512, "started_unix": time.time(),
        "measurement": "prerequisite only; no frozen A/A or benefit gates",
    }
    try:
        if args.selftest:
            subprocess.run(["/usr/bin/busybox", "ip", "link", "set", "lo", "up"], check=True, timeout=5)
            subprocess.run(
                ["/usr/bin/busybox", "ip", "addr", "add", "192.0.2.2/32", "dev", "lo"],
                check=True, timeout=5,
            )
            binary = artifact_path(args.native)
            argv = [str(binary)]
        else:
            fixture = artifact_path(args.fixture)
            metadata = json.loads((fixture / "fixture.json").read_text())
            if metadata.get("transport") != "tap-tcp" or metadata["diagnostic_heartbeat_ms"] != 0:
                raise ValueError("TAP acceptance prerequisite requires the native timer-free TCP fixture")
            kernel = artifact_path(metadata["kernel"])
            if digest(kernel) != metadata["kernel_sha256"] or digest(fixture / "initrd.cpio.gz") != metadata["initrd_sha256"]:
                raise ValueError("fixture changed after preparation")
            manifest["fixture"] = metadata
            name = setup_tap(args.uid)
            manifest["tap"] = name
            binary = artifact_path(args.binary)
            jail.mkdir(mode=0o700, exist_ok=False)
            os.chown(jail, args.uid, args.gid)
            for source, name in ((kernel, "bzImage"), (fixture / "initrd.cpio.gz", "initrd.cpio.gz")):
                shutil.copyfile(source, jail / name)
                os.chown(jail / name, args.uid, args.gid)
            argv = [
                str(binary), "--jail", str(jail), "--jail-uid", str(args.uid), "--jail-gid", str(args.gid),
                "/bzImage", "/initrd.cpio.gz",
                "console=ttyS0 nokaslr reboot=k panic=1 pci=off nomodules",
                "--tap", "hef3tap0",
            ]
            if args.virtio_mode:
                argv.extend(["--virtio-mode", args.virtio_mode])
        manifest["binary_sha256"] = digest(binary)
        manifest["argv"] = argv
        source = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, check=True, timeout=5)
        manifest["source_sha"] = source.stdout.decode().strip()
        diff = subprocess.run(["git", "diff", "--", "vmm", "agent"], cwd=ROOT, capture_output=True, check=True, timeout=5)
        (out / "source-diff.txt").write_bytes(diff.stdout)
        manifest["source_diff_sha256"] = digest(out / "source-diff.txt")
        with serial_path.open("wb") as serial, (out / "vmm.stderr").open("wb") as stderr:
            os.chown(serial_path, args.uid, args.gid)
            os.chown(out / "vmm.stderr", args.uid, args.gid)
            child = subprocess.Popen(
                argv, cwd=ROOT, stdout=serial, stderr=stderr,
                preexec_fn=demote_client if args.selftest else None,
            )
            os.sched_setaffinity(child.pid, {args.cpu})
            manifest["pid"] = child.pid
            record("manifest.json", manifest)
            # std.debug.print writes the TCP marker to stderr.
            deadline = time.monotonic() + 15
            while b"eventfd-tcp-probe: listening" not in serial_path.read_bytes() + (out / "vmm.stderr").read_bytes():
                if child.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError(f"native TCP listener not ready; child_status={child.poll()}")
                time.sleep(0.02)
            if not args.selftest:
                inspected = subprocess.run(
                    [sys.executable, "-c", INSPECT, str(child.pid)],
                    capture_output=True, check=True, timeout=3,
                )
                rows = json.loads(inspected.stdout)
                record("enforced-roster.json", rows)
                if not enforced_roster(rows, args.uid, args.gid):
                    raise RuntimeError("VMM post-drop credentials/filter fail the isolation gate")
            time.sleep(1)
            before = thread_roster(child.pid)
            host_before = Path("/proc/stat").read_text()
            started = time.monotonic()
            peer_argv = [sys.executable, str(Path(__file__)), "--client", "--out", str(out)]
            record("client-command.json", {"argv": peer_argv, "cwd": str(ROOT), "uid": args.uid, "gid": args.gid})
            with (out / "client.stdout").open("wb") as stdout, (out / "client.stderr").open("wb") as stderr:
                peer = subprocess.Popen(peer_argv, cwd=ROOT, stdout=stdout, stderr=stderr, preexec_fn=demote_client)
                result["client_exit_code"] = peer.wait(timeout=20)
            elapsed = time.monotonic() - started
            host_after = Path("/proc/stat").read_text()
            result["operation_window_seconds"] = elapsed
            result["host_noise_control"] = host_cpu_delta(host_before, host_after, elapsed)
            record("host-controls.json", {"before": host_before, "after": host_after, "seconds": elapsed})
            if child.poll() is None:
                after = thread_roster(child.pid)
                record("threads.json", {"before": before, "after": after})
                result["all_child_thread_cpu_seconds"] = cpu_delta(before, after)
            else:
                result["all_child_thread_cpu_seconds"] = None
                result["cpu_accounting"] = "child exited during window; do not omit departed threads"
            if result["client_exit_code"] != 0:
                raise RuntimeError("native TCP request/backpressure validation failed; see client-result.json")
            result["status"] = "passed"
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        result["errors"].append(f"{type(error).__name__}: {error}")
    finally:
        for process in (peer, child):
            if process is not None:
                if process.poll() is None:
                    process.send_signal(signal.SIGTERM)
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)
                result["client_final_exit_code" if process is peer else "child_final_exit_code"] = process.returncode
        if jail.exists():
            shutil.rmtree(jail)
        record("manifest.json", manifest)
        record("result.json", result)
        for path in out.iterdir():
            if path.is_file():
                os.chown(path, args.uid, args.gid)
    print(json.dumps(result))
    return 0 if result["status"] == "passed" else 1


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--client", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--uid", type=int, default=1000)
    parser.add_argument("--gid", type=int, default=1000)
    parser.add_argument("--cpu", type=int, default=8)
    parser.add_argument("--client-cpu", type=int, default=1)
    parser.add_argument("--label", default="isolation-control")
    parser.add_argument("--virtio-mode", choices=["L0", "C00", "C10", "C01", "C11"])
    parser.add_argument("--binary", default=".perf/eventfd/fixtures/isolation-control/flint")
    parser.add_argument("--native", default="vmm/zig-out/bin/eventfd-tcp-probe")
    parser.add_argument("--fixture", default=".perf/eventfd/fixtures/tap-no-heartbeat")
    args = parser.parse_args()
    return client(args) if args.client else supervise(args)


if __name__ == "__main__":
    raise SystemExit(main())
