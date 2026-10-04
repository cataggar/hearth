#!/usr/bin/env python3
"""Root fixture supervisor; Flint and host traffic peers always run as UID 1000."""

import argparse
import fcntl
import hashlib
import json
import os
import resource
import signal
import socket
import struct
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UID = 1000
GID = 1000


def demote():
    os.setgroups([36])
    os.setgid(GID)
    os.setuid(UID)
    os.umask(0o077)


def private_directory(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chown(path, UID, GID)


def owned_file(path, data):
    path.write_text(data)
    path.chmod(0o600)
    os.chown(path, UID, GID)


def command(argv, directory, name, user=False, timeout=120):
    begin = time.monotonic_ns()
    with (directory / f"{name}.stdout").open("wb") as out, (directory / f"{name}.stderr").open("wb") as err:
        child = subprocess.Popen(
            argv, cwd=ROOT, stdout=out, stderr=err, start_new_session=True,
            preexec_fn=demote if user else None,
        )
        try:
            status = child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            status = 124
        finally:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=5)
    for suffix in ("stdout", "stderr"):
        os.chown(directory / f"{name}.{suffix}", UID, GID)
    owned_file(directory / f"{name}.command.json", json.dumps({
        "argv": [str(value) for value in argv], "exit_status": status,
        "process_group": child.pid,
        "begin_monotonic_ns": begin, "end_monotonic_ns": time.monotonic_ns(),
    }, indent=2) + "\n")
    return status


def request(path, method, target, body=None):
    payload = json.dumps(body).encode() if body is not None else b""
    wire = (
        f"{method} {target} HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\n"
        f"Content-Length: {len(payload)}\r\nConnection: close\r\n\r\n"
    ).encode() + payload
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(10)
        sock.connect(str(path))
        sock.sendall(wire)
        response = bytearray()
        while True:
            data = sock.recv(8192)
            if not data:
                break
            response.extend(data)
    response = response.decode()
    if not response.startswith(("HTTP/1.1 200", "HTTP/1.1 204")):
        raise RuntimeError(response)
    return response


def inventory(directory, name):
    for filename in ("stat", "softirqs", "net/softnet_stat", "net/dev"):
        owned_file(directory / f"{name}.proc-{filename.replace('/', '-')}.txt", Path("/proc", filename).read_text())
    command(["ps", "-eLo", "pid,tid,psr,comm,cgroup"], directory, f"{name}.tasks")
    command(["/usr/bin/busybox", "ip", "addr", "show"], directory, f"{name}.addresses")
    command(["/usr/bin/busybox", "ip", "route", "show"], directory, f"{name}.routes")


def freeze_tools(directory):
    hashes = {}
    for name in ("collect.py", "runner.py", "run.sh", "guest.c", "guest-init.sh"):
        source = ROOT / "benchmarks/vhost-net" / name
        data = source.read_bytes()
        destination = directory / f"source-{name}"
        destination.write_bytes(data)
        destination.chmod(0o600)
        os.chown(destination, UID, GID)
        hashes[name] = hashlib.sha256(data).hexdigest()
    owned_file(directory / "tool-source-hashes.json", json.dumps(hashes, indent=2) + "\n")


def setup_tap(directory):
    name = "hn2tap0"
    fd = os.open("/dev/net/tun", os.O_RDWR | os.O_CLOEXEC)
    try:
        fcntl.ioctl(fd, 0x400454CA, struct.pack("16sH22x", name.encode(), 0x0002 | 0x1000 | 0x4000))
        fcntl.ioctl(fd, 0x400454CC, UID)
        fcntl.ioctl(fd, 0x400454CB, 1)
        fcntl.ioctl(fd, 0x400454D0, 0)
    finally:
        os.close(fd)
    for args in (
        ["link", "set", "lo", "up"],
        ["addr", "add", "192.0.2.1/30", "dev", name],
        ["link", "set", name, "mtu", "1500", "up"],
    ):
        if subprocess.run(["/usr/bin/busybox", "ip", *args], check=False).returncode:
            raise RuntimeError(f"fixture network setup failed: {args}")
    owned_file(directory / "topology.json", json.dumps({
        "namespace": os.readlink("/proc/self/ns/net"), "supervisor_pid": os.getpid(),
        "tap": name, "owner_uid": UID, "host": "192.0.2.1/30", "guest": "192.0.2.2/30",
        "mtu": 1500, "tun_offloads": 0, "tap_flags": "IFF_TAP|IFF_NO_PI|IFF_VNET_HDR",
        "uplink": None, "nat": None, "guest_vcpus": 1, "guest_memory_mib": 512,
        "flint_cpu": 8, "client_cpu": 9, "flint_uid": UID, "client_uid": UID,
        "backend": "userspace", "notifications": "MMIO exits/direct IRQ/exit-driven RX",
    }, indent=2) + "\n")


def probe(directory):
    private_directory(directory)
    for name, argv, user in (
        ("perf-version", ["perf", "--version"], False),
        ("perf-list", ["perf", "list"], False),
        ("identity", ["id"], True),
        ("host-kernel", ["uname", "-a"], False),
        ("cpu", ["lscpu"], False),
        ("vhost-user-capability", ["python3", "-c", (
            "import os,fcntl,struct,json; before=len(os.listdir('/proc/self/fd')); "
            "fd=os.open('/dev/vhost-net',os.O_RDWR|os.O_CLOEXEC); data=bytearray(8); "
            "fcntl.ioctl(fd,0x8008af00,data,True); features=struct.unpack('<Q',data)[0]; os.close(fd); "
            "print(json.dumps({'uid':os.getuid(),'get_features_hex':hex(features),"
            "'version_1':bool(features&(1<<32)),'vhost_header':bool(features&(1<<27)),"
            "'fds_before':before,'fds_after':len(os.listdir('/proc/self/fd')),"
            "'set_owner_executed':False,'queue_or_memory_setup_executed':False}))"
        )], True),
        ("software-user", ["perf", "stat", "-a", "-e", "task-clock,context-switches,cpu-migrations,page-faults", "--", "sleep", "1"], True),
        ("software-root", ["perf", "stat", "-a", "-e", "task-clock,context-switches,cpu-migrations,page-faults", "--", "sleep", "1"], False),
        ("hardware", ["perf", "stat", "-a", "-e", "cycles,instructions", "--", "sleep", "1"], False),
        ("kvm-tracepoints", ["perf", "stat", "-a", "-e", "kvm:kvm_entry,kvm:kvm_exit", "--", "sleep", "1"], False),
        ("kvm-stat-alternative", ["perf", "record", "-a", "--no-buildid-cache", "-e", "kvm:kvm_entry,kvm:kvm_exit", "-o", str(directory / "kvm-probe.data"), "--", "sleep", "1"], False),
        ("software-record", ["perf", "record", "-a", "--no-buildid-cache", "-e", "cpu-clock", "-F", "49", "-g", "--call-graph", "dwarf,4096", "-o", str(directory / "probe.perf.data"), "--", "sleep", "1"], False),
        ("software-report", ["perf", "report", "--stdio", "-i", str(directory / "probe.perf.data"), "--sort", "comm,dso,symbol"], False),
    ):
        command(argv, directory, name, user=user)
    capabilities = {}
    for device in ("/dev/kvm", "/dev/net/tun", "/dev/vhost-net"):
        try:
            fd = os.open(device, os.O_RDWR | os.O_CLOEXEC)
            os.close(fd)
            capabilities[device] = {"root_open": "supported"}
        except OSError as error:
            capabilities[device] = {"root_open": "unsupported", "errno": error.errno, "reason": str(error)}
    owned_file(directory / "devices.json", json.dumps(capabilities, indent=2) + "\n")


def workload(directory, mode, name, seconds, warmup, profile=None):
    if mode == "idle":
        warmup = 0
    peer = [
        "taskset", "-c", "9", "python3", str(directory / "source-collect.py"),
        "--mode", mode, "--warmup-seconds", str(warmup), "--seconds", str(seconds),
        "--output", str(directory / f"{name}.json"),
    ]
    # perf must remain root, but the peer must not retain its privileges.
    if profile:
        peer = ["runuser", "-u", "g", "--", *peer]
    inventory(directory, f"{name}.begin")
    if profile == "stat":
        events = "task-clock,context-switches,cpu-migrations,page-faults"
        probe_path = directory.parent / "probes/kvm-tracepoints.command.json"
        if probe_path.exists() and json.loads(probe_path.read_text())["exit_status"] == 0:
            events += ",kvm:kvm_entry,kvm:kvm_exit"
        argv = [
            "perf", "stat", "-a", "-x,", "-e", events,
            "-o", str(directory / f"{name}.stat.csv"), "--", *peer,
        ]
    elif profile == "record":
        argv = [
            "perf", "record", "-a", "--no-buildid-cache", "-e", "cpu-clock", "-F", "49",
            "-g", "--call-graph", "dwarf,4096",
            "-o", str(directory / f"{name}.perf.data"), "--", *peer,
        ]
    else:
        argv = peer
    status = command(argv, directory, name, user=profile is None, timeout=seconds + warmup + 30)
    inventory(directory, f"{name}.end")
    if profile == "record":
        command(
            ["perf", "report", "--stdio", "-i", str(directory / f"{name}.perf.data"), "--sort", "comm,dso,symbol"],
            directory, f"{name}.report",
        )
        command(
            ["perf", "script", "-i", str(directory / f"{name}.perf.data"), "--show-lost-events"],
            directory, f"{name}.stacks",
        )
        probe_path = directory.parent / "probes/kvm-tracepoints.command.json"
        if probe_path.exists() and json.loads(probe_path.read_text())["exit_status"] == 0:
            command(
                ["perf", "record", "-a", "--no-buildid-cache", "-e", "kvm:kvm_entry,kvm:kvm_exit",
                 "-o", str(directory / f"{name}.kvm.data"),
                 "--", *peer[:-1], str(directory / f"{name}.kvm-workload.json")],
                directory, f"{name}.kvm-record", timeout=seconds + warmup + 30,
            )
            command(
                ["perf", "kvm", "-i", str(directory / f"{name}.kvm.data"),
                 "stat", "report", "--stdio"],
                directory, f"{name}.kvm-report",
            )
    return status


def selftest(directory):
    private_directory(directory)
    freeze_tools(directory)
    for args in (["link", "set", "lo", "up"], ["addr", "add", "192.0.2.2/32", "dev", "lo"]):
        subprocess.run(["/usr/bin/busybox", "ip", *args], check=True)
    children = []
    try:
        for port in (7000, 7001, 7002):
            with (directory / f"peer-{port}.log").open("wb") as output:
                child = subprocess.Popen(
                    [str(ROOT / ".perf/vhost-net/20261004/fixture/guest/bin/peer"), str(port)],
                    stdout=output, stderr=subprocess.STDOUT, preexec_fn=demote, start_new_session=True,
                )
            children.append(child)
        owned_file(directory / "peer-process-groups.json", json.dumps([child.pid for child in children]) + "\n")
        deadline = time.monotonic() + 5
        while not all(f"PERF_LISTEN {port}" in (directory / f"peer-{port}.log").read_text() for port in (7000, 7001, 7002)):
            if time.monotonic() > deadline or any(child.poll() is not None for child in children):
                raise RuntimeError("native fixture peer failed to listen")
            time.sleep(0.01)
        for mode in ("rpc", "h2g", "g2h", "wake"):
            status = workload(directory, mode, f"native-{mode}", 2, 0)
            if status:
                raise RuntimeError(f"native fixture protocol selftest failed: {mode}")
        owned_file(directory / "classification.txt", "Native host loopback protocol test only: no Flint, KVM or TAP performance.\n")
    finally:
        for child in children:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=5)


def boot(args, directory):
    private_directory(directory)
    freeze_tools(directory)
    setup_tap(directory)
    sock = directory / "flint.sock"
    log = directory / "serial.log"
    binary = ROOT / "vmm/zig-out/bin/flint"
    fixture = args.artifact_dir / "fixture"
    with log.open("wb") as output:
        child = subprocess.Popen(
            ["taskset", "-c", "8", str(binary), "--api-sock", str(sock)],
            cwd=directory, stdout=output, stderr=subprocess.STDOUT, preexec_fn=demote,
        )
    try:
        os.chown(log, UID, GID)
        owned_file(directory / "flint-pid.txt", str(child.pid) + "\n")
        deadline = time.monotonic() + 15
        while not sock.exists():
            if child.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("Flint API did not become ready")
            time.sleep(0.01)
        responses = [
            request(sock, "PUT", "/machine-config", {"vcpu_count": 1, "mem_size_mib": 512}),
            request(sock, "PUT", "/boot-source", {
                "kernel_image_path": str(fixture / "bzImage"),
                "initrd_path": str(fixture / "initrd.cpio.gz"),
                "boot_args": "console=ttyS0 reboot=k panic=1 pci=off",
            }),
            request(sock, "PUT", "/network-interfaces/eth0", {"iface_id": "eth0", "host_dev_name": "hn2tap0"}),
            request(sock, "PUT", "/actions", {"action_type": "InstanceStart"}),
        ]
        owned_file(directory / "api-configuration.txt", "\n".join(responses))
        deadline = time.monotonic() + 15
        while "PERF_TAP_READY" not in log.read_text(errors="replace"):
            if child.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("guest TAP fixture did not become ready")
            time.sleep(0.01)
        inventory(directory, "ready")
        summary = []
        for repetition in range(args.repetitions):
            for mode in args.modes:
                name = f"aa-{repetition:02d}-{mode}"
                summary.append({"name": name, "status": workload(directory, mode, name, args.seconds, 10)})
        if args.profiles:
            for mode in dict.fromkeys([*args.modes, "idle"]):
                for profile in ("stat", "record"):
                    name = f"profile-{mode}-{profile}"
                    summary.append({
                        "name": name,
                        "status": workload(directory, mode, name, 60 if mode == "idle" else args.seconds, 10, profile),
                    })
        owned_file(directory / "summary.json", json.dumps(summary, indent=2) + "\n")
        owned_file(directory / "api-final-status.txt", request(sock, "GET", "/vm"))
        if args.snapshot:
            transitions = []
            for method, route, body in (
                ("PATCH", "/vm", {"state": "Paused"}),
                ("PUT", "/snapshot/create", {"snapshot_path": "baseline.vmstate", "mem_file_path": "baseline.mem"}),
            ):
                begin = time.monotonic_ns()
                response = request(sock, method, route, body)
                transitions.append({"route": route, "duration_ms": (time.monotonic_ns() - begin) / 1e6,
                                    "response": response})
            state = (directory / "baseline.vmstate").read_bytes()
            if state[:8] != b"FLINTSNP" or struct.unpack_from("<II", state, 16) != (2, 1):
                raise RuntimeError("unexpected baseline snapshot version/device count")
            net_offset = len(state) - 10 - 144
            if struct.unpack_from("<I", state, net_offset - 4)[0] != 144:
                raise RuntimeError("unexpected baseline net snapshot layout")
            net = state[net_offset:net_offset + 144]
            transport = {
                "classification": "baseline vCPU-only pause/snapshot/resume; not vhost worker or traffic acceptance",
                "format_version": 2, "device_id": struct.unpack_from("<I", net)[0],
                "status": net[16], "driver_features_hex": hex(struct.unpack_from("<Q", net, 25)[0]),
                "interrupt_status": struct.unpack_from("<I", net, 37)[0],
                "mac": ":".join(f"{byte:02x}" for byte in net[138:144]),
                "queues": [
                    dict(zip(("size", "ready", "desc_gpa", "avail_gpa", "used_gpa", "last_avail_idx", "next_used_idx"),
                             struct.unpack_from("<HBQQQHH", net, 45 + index * 31)))
                    for index in (0, 1)
                ],
            }
            owned_file(directory / "observed-net-transport.json", json.dumps(transport, indent=2) + "\n")
            begin = time.monotonic_ns()
            response = request(sock, "PATCH", "/vm", {"state": "Resumed"})
            transitions.append({"route": "/vm/resume", "duration_ms": (time.monotonic_ns() - begin) / 1e6,
                                "response": response})
            owned_file(directory / "baseline-lifecycle.json", json.dumps(transitions, indent=2) + "\n")
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        owned_file(directory / "flint-exit-status.txt", str(child.returncode) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--phase", choices=("probe", "boot", "quiet", "selftest"), required=True)
    parser.add_argument("--boot-id", default="boot-01")
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--profiles", action="store_true")
    parser.add_argument("--snapshot", action="store_true")
    parser.add_argument("--control-id")
    parser.add_argument("--modes", nargs="+", choices=("rpc", "h2g", "g2h", "wake", "idle"),
                        default=["rpc", "h2g", "g2h", "wake"])
    args = parser.parse_args()
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    def terminate(_number, _frame):
        raise SystemExit("fixture supervisor terminated; unwinding owned children")
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    os.chdir(ROOT)
    args.artifact_dir = args.artifact_dir.resolve()
    args.artifact_dir.relative_to(ROOT / ".perf")
    if os.getuid() != 0:
        raise RuntimeError("the isolated namespace fixture requires sudo; Flint itself runs as UID 1000")
    if args.phase == "probe":
        directory = args.artifact_dir / "probes"
        if (directory / "perf-version.command.json").exists():
            raise ValueError("refusing to overwrite retained probes")
    elif args.phase in ("quiet", "selftest"):
        name = args.control_id or args.phase
        if not name.replace("-", "").isalnum():
            raise ValueError("invalid control ID")
        directory = args.artifact_dir / name
        if directory.exists():
            raise ValueError("refusing to overwrite retained control evidence")
    else:
        if not args.boot_id.replace("-", "").isalnum() or args.repetitions <= 0 or args.seconds <= 0:
            raise ValueError("invalid boot ID, repetition count or active duration")
        directory = args.artifact_dir / args.boot_id
        if directory.exists():
            raise ValueError("refusing to overwrite a retained boot")
    try:
        if args.phase == "probe":
            probe(directory)
        elif args.phase == "boot":
            boot(args, directory)
        elif args.phase == "selftest":
            selftest(directory)
        else:
            private_directory(directory)
            freeze_tools(directory)
            for profile in ("stat", "record"):
                workload(directory, "idle", f"quiet-{profile}", 60, 0, profile)
    finally:
        if directory.exists():
            for path in (directory, *directory.rglob("*")):
                if not path.is_symlink():
                    os.chown(path, UID, GID)


if __name__ == "__main__":
    main()
