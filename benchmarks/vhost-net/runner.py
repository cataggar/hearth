#!/usr/bin/env python3
"""Root fixture supervisor; Flint and host traffic peers always run as UID 1000."""

import argparse
from contextlib import ExitStack
import fcntl
import hashlib
import json
import os
import resource
import select
import signal
import shutil
import socket
import stat
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
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


def host_idle_control(directory, name, seconds=5):
    def snapshot():
        data = Path("/proc/stat").read_text()
        values = [int(x) for x in data.splitlines()[0].split()[1:]]
        return data, sum(values[i] for i in (0, 1, 2, 5, 6))
    begin, a = snapshot()
    started = time.monotonic()
    time.sleep(seconds)
    elapsed = time.monotonic() - started
    end, b = snapshot()
    cpu = (b - a) / os.sysconf("SC_CLK_TCK")
    owned_file(directory / f"{name}.json", json.dumps({
        "elapsed_seconds": elapsed, "busy_cpu_seconds": cpu, "busy_cores": cpu / elapsed,
        "classification": "aggregate no-owned-VM control; not task attribution",
        "begin": begin, "end": end,
    }, indent=2) + "\n")


def owned_file(path, data):
    path.write_text(data)
    path.chmod(0o600)
    os.chown(path, UID, GID)


def command(argv, directory, name, user=False, timeout=120, trigger_rx=False, env=None):
    begin = time.monotonic_ns()
    with (directory / f"{name}.stdout").open("wb") as out, (directory / f"{name}.stderr").open("wb") as err:
        child = subprocess.Popen(
            argv, cwd=ROOT, stdout=out, stderr=err, start_new_session=True,
            preexec_fn=demote if user else None,
            env=env,
        )
        trigger = None
        try:
            if trigger_rx:
                trigger = subprocess.Popen(
                    ["python3", "-c",
                     "import socket,time; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); "
                     "[(s.sendto(b'owned malformed RX trigger',('192.0.2.2',7999)),time.sleep(.05)) for _ in range(10)]"],
                    cwd=ROOT, stdout=subprocess.DEVNULL, stderr=err, preexec_fn=demote)
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
            if trigger is not None:
                if trigger.poll() is None:
                    trigger.terminate()
                trigger.wait(timeout=5)
    for suffix in ("stdout", "stderr"):
        os.chown(directory / f"{name}.{suffix}", UID, GID)
    owned_file(directory / f"{name}.command.json", json.dumps({
        "argv": [str(value) for value in argv], "exit_status": status,
        "process_group": child.pid,
        "actual_returncode": child.returncode,
        "owned_pid_absent_after_join": not Path("/proc", str(child.pid)).exists(),
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


def inventory(directory, name, owned_pid=None):
    for filename in ("stat", "softirqs", "net/softnet_stat", "net/dev"):
        owned_file(directory / f"{name}.proc-{filename.replace('/', '-')}.txt", Path("/proc", filename).read_text())
    command(["ps", "-Lo", "pid,tid,psr,comm,cgroup", "-p", str(owned_pid or os.getpid())],
            directory, f"{name}.owned-tasks")
    command(["/usr/bin/busybox", "ip", "addr", "show"], directory, f"{name}.addresses")
    command(["/usr/bin/busybox", "ip", "route", "show"], directory, f"{name}.routes")
    if owned_pid is not None:
        fields = ("Name", "Pid", "Tgid", "PPid", "Uid", "Gid", "Groups", "CapEff",
                  "NoNewPrivs", "Seccomp", "Seccomp_filters", "Kthread", "Cpus_allowed_list")
        tasks = {}
        task_root = Path("/proc", str(owned_pid), "task")
        for task in task_root.iterdir() if task_root.exists() else []:
            try:
                values = {}
                for line in (task / "status").read_text().splitlines():
                    key, _, value = line.partition(":")
                    if key in fields:
                        values[key] = value.strip()
                values["cgroup"] = (task / "cgroup").read_text()
                values["namespaces"] = {name: os.readlink(task / "ns" / name)
                                        for name in ("net", "mnt", "user", "pid")}
                tasks[task.name] = values
            except FileNotFoundError:
                pass
        owned_file(directory / f"{name}.owned-status.json", json.dumps(tasks, indent=2) + "\n")
        owned_file(directory / f"{name}.owned-fds.json", json.dumps({
            "pid": owned_pid, "fd_count": len(list(Path("/proc", str(owned_pid), "fd").iterdir())),
        }, indent=2) + "\n")


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


def sparse_copy(source, target):
    expected = hashlib.sha256()
    zero = bytes(4096)
    size = 0
    with source.open("rb") as src, target.open("xb") as dst:
        while chunk := src.read(16 * 1024 * 1024):
            expected.update(chunk)
            for offset in range(0, len(chunk), 4096):
                page = chunk[offset:offset + 4096]
                if page != zero:
                    dst.seek(size + offset)
                    dst.write(page)
            size += len(chunk)
        dst.truncate(size)
    actual = hashlib.sha256()
    with target.open("rb") as dst:
        while chunk := dst.read(16 * 1024 * 1024):
            actual.update(chunk)
    if actual.digest() != expected.digest():
        raise RuntimeError("sparse correctness-input copy changed raw bytes")


class JailedLayout:
    def __init__(self, directory, fixture=None, backing=None, tap_name="hn2tap0"):
        private_directory(directory)
        self.directory = directory
        self.tap_name = tap_name
        self.root = directory / "jail"
        if self.root.exists():
            raise ValueError("refusing to reuse a jail")
        private_directory(self.root)
        self.cgroup = Path("/sys/fs/cgroup", f"hearth-vhost-net-{os.getpid()}-{directory.name}")
        self.cgroup.mkdir(mode=0o700)
        try:
            (self.cgroup / "memory.max").write_text(str(1024 * 1024 * 1024))
            (self.cgroup / "pids.max").write_text("16")
            if fixture:
                for name in ("bzImage", "initrd.cpio.gz"):
                    shutil.copyfile(fixture / name, self.root / name)
                    (self.root / name).chmod(0o600)
                    os.chown(self.root / name, UID, GID)
            if backing:
                for name, source in backing.items():
                    os.link(source, self.root / name, follow_symlinks=False)
            owned_file(directory / "jail-layout.json", json.dumps({
                "root": str(self.root), "cgroup": str(self.cgroup),
                "memory_max": (self.cgroup / "memory.max").read_text().strip(),
                "pids_max": (self.cgroup / "pids.max").read_text().strip(),
                "cpu_max_available": (self.cgroup / "cpu.max").exists(),
                "bootstrap_groups": [0], "required_worker_groups": [],
                "backing": {name: str(source) for name, source in (backing or {}).items()},
            }, indent=2) + "\n")
        except BaseException:
            self.cgroup.rmdir()
            raise

    def argv(self, binary):
        return [
            "setpriv", "--groups=0", "--", "taskset", "-c", "8", str(binary),
            "--jail", str(self.root), "--jail-uid", str(UID), "--jail-gid", str(GID),
            "--jail-cgroup", self.cgroup.name, "--jail-memory", "1024", "--tap", self.tap_name,
        ]

    def verify(self, pid, backend, name):
        inventory(self.directory, name, pid)
        tasks = json.loads((self.directory / f"{name}.owned-status.json").read_text())
        if not tasks:
            raise RuntimeError("no owned jailed tasks to verify")
        namespaces = tasks[str(pid)]["namespaces"]
        if namespaces["net"] != os.readlink("/proc/self/ns/net"):
            raise RuntimeError("VMM left its owned fixture network namespace")
        for row in tasks.values():
            if not (
                row["Uid"].split() == [str(UID)] * 4
                and row["Gid"].split() == [str(GID)] * 4
                and row["Groups"] == ""
                and int(row["CapEff"], 16) == 0
                and row["NoNewPrivs"] == "1"
                and row["Seccomp"] == "2"
                and row["Cpus_allowed_list"] == "8"
                and row["cgroup"].strip() == f"0::/{self.cgroup.name}"
                and row["namespaces"] == namespaces
            ):
                raise RuntimeError(f"jailed task confinement mismatch: {row}")
        workers = sum(row["Name"].startswith("vhost-") for row in tasks.values())
        if workers != (1 if backend == "vhost" else 0):
            raise RuntimeError(f"unexpected owned vhost worker population: {workers}")
        nodes = {}
        expected = {"dev/kvm": 232, "dev/net/tun": 200}
        if backend == "vhost":
            expected["dev/vhost-net"] = 238
        for node_name, minor in expected.items():
            s = (self.root / node_name).lstat()
            if not (stat.S_ISCHR(s.st_mode) and stat.S_IMODE(s.st_mode) == 0o600
                    and s.st_uid == UID and s.st_gid == GID
                    and os.major(s.st_rdev) == 10 and os.minor(s.st_rdev) == minor):
                raise RuntimeError(f"jailed device ownership mismatch: {node_name}")
            nodes[node_name] = {"uid": s.st_uid, "gid": s.st_gid, "mode": oct(stat.S_IMODE(s.st_mode))}
        for directory_name in ("dev", "dev/net"):
            s = (self.root / directory_name).lstat()
            if s.st_uid != 0 or s.st_gid != 0 or stat.S_IMODE(s.st_mode) != 0o755:
                raise RuntimeError(f"jailed device directory mismatch: {directory_name}")
        owned_file(self.directory / f"{name}-confinement.json", json.dumps({
            "passed": True, "owned_task_count": len(tasks), "vhost_workers": workers,
            "nodes": nodes, "cgroup": str(self.cgroup),
            "cpu_max_available": (self.cgroup / "cpu.max").exists(),
        }, indent=2) + "\n")

    def close(self):
        current = (self.cgroup / "pids.current").read_text().strip()
        members = (self.cgroup / "cgroup.procs").read_text().strip()
        result = {
            "pids_current": current, "members": members,
            "memory_current": (self.cgroup / "memory.current").read_text().strip(),
            "cpu_stat": (self.cgroup / "cpu.stat").read_text(),
            "worker_and_process_joined": current == "0" and not members,
        }
        if current != "0" or members:
            raise RuntimeError("owned jail cgroup still has a process/worker after join")
        self.cgroup.rmdir()
        for name in ("dev/vhost-net", "dev/net/tun", "dev/kvm", "api.sock"):
            (self.root / name).unlink(missing_ok=True)
        for name in ("dev/net", "dev"):
            path = self.root / name
            if path.exists():
                path.rmdir()
        owned_file(self.directory / "jail-closed.json", json.dumps(result, indent=2) + "\n")


def setup_tap(directory, name="hn2tap0"):
    if not name or len(name.encode()) > 15 or any(
        c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in name
    ):
        raise ValueError("invalid owned TAP name")
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


def workload(directory, mode, name, seconds, warmup, profile=None, variant_override=None, rpc_rate=None):
    if mode == "idle":
        warmup = 0
    peer = [
        "taskset", "-c", "9", "python3", str(directory / "source-collect.py"),
        "--mode", mode, "--warmup-seconds", str(warmup), "--seconds", str(seconds),
        "--output", str(directory / f"{name}.json"),
    ]
    if mode == "rpc" and rpc_rate:
        peer += ["--rpc-rate", str(rpc_rate)]
    variant_path = directory / "variant.json"
    if variant_path.exists():
        variant = variant_override or json.loads(variant_path.read_text())
        peer += ["--backend", variant["effective_backend"],
                 "--notification", variant["notification"]]
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


def scoped_profile(directory, vmm_pid, mode, name, seconds, warmup, profile, rpc_rate=None):
    with ExitStack() as cleanup:
        descriptors = []
        for _ in range(3):
            read_fd, write_fd = os.pipe2(os.O_CLOEXEC)
            cleanup.callback(os.close, read_fd)
            cleanup.callback(os.close, write_fd)
            descriptors.extend((read_fd, write_fd))
        return _scoped_profile(directory, vmm_pid, mode, name, seconds, warmup,
                               profile, *descriptors, rpc_rate=rpc_rate)


def _scoped_profile(directory, vmm_pid, mode, name, seconds, warmup, profile,
                    gate_read, gate_write, control_read, control_write, ack_read, ack_write,
                    rpc_rate=None):
    variant = json.loads((directory / "variant.json").read_text())
    peer_argv = [
        "taskset", "-c", "9", "python3", str(directory / "source-collect.py"),
        "--mode", mode, "--seconds", str(seconds), "--warmup-seconds", str(warmup),
        "--backend", variant["effective_backend"], "--notification", variant["notification"],
        "--output", str(directory / f"{name}.json"),
        "--start-fd", str(gate_read),
    ]
    if mode == "rpc" and rpc_rate:
        peer_argv += ["--rpc-rate", str(rpc_rate)]
    collector = None
    cache = directory / "perf-buildid"
    cache.mkdir(mode=0o700, exist_ok=True)
    profile_env = {**os.environ, "PERF_BUILDID_DIR": str(cache), "TMPDIR": str(directory),
                   "DEBUGINFOD_URLS": "", "PYTHONDONTWRITEBYTECODE": "1"}
    with (directory / f"{name}.peer.log").open("wb") as output:
        peer = subprocess.Popen(peer_argv, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                                preexec_fn=demote, pass_fds=(gate_read,))
    try:
        events = "task-clock,context-switches,cpu-migrations,page-faults,kvm:kvm_entry,kvm:kvm_exit"
        if profile == "stat":
            perf_argv = [
                "perf", "stat", "-p", f"{vmm_pid},{peer.pid}", "-e", events, "-x,",
                "-o", str(directory / f"{name}.stat.csv"),
            ]
        else:
            perf_argv = [
                "perf", "record", "-p", f"{vmm_pid},{peer.pid}", "--no-buildid-cache",
                "-e", "cpu-clock", "-F", "49", "-g", "--call-graph", "dwarf,4096",
                "-o", str(directory / f"{name}.perf.data"),
            ]
        perf_argv += ["--delay=-1", "--control", f"fd:{control_read},{ack_write}"]
        with (directory / f"{name}.perf.log").open("wb") as output:
            collector = subprocess.Popen(perf_argv, cwd=ROOT, stdout=output,
                                         stderr=subprocess.STDOUT, env=profile_env,
                                         pass_fds=(control_read, ack_write))
        os.write(control_write, b"enable\n")
        deadline = time.monotonic() + 5
        acknowledgement = b""
        while b"ack\n" not in acknowledgement:
            remaining = deadline - time.monotonic()
            if collector.poll() is not None or remaining <= 0:
                raise RuntimeError("owned perf did not acknowledge enabled capture")
            if select.select([ack_read], [], [], min(remaining, .1))[0]:
                acknowledgement += os.read(ack_read, 64)
        os.write(gate_write, b"R")
        peer_status = peer.wait(timeout=seconds + warmup + 30)
        stopped_by_supervisor = collector.poll() is None
        if stopped_by_supervisor:
            collector.send_signal(signal.SIGINT)
        perf_status = collector.wait(timeout=10)
        owned_file(directory / f"{name}.profile.json", json.dumps({
            "peer_argv": peer_argv, "perf_argv": perf_argv, "peer_pid": peer.pid,
            "vmm_pid": vmm_pid, "peer_status": peer_status, "perf_status": perf_status,
            "stopped_by_supervisor_sigint": stopped_by_supervisor,
            "scope": "owned VMM tasks (including owner vhost worker) and owned peer only",
            "private_buildid_dir": str(cache), "debuginfod_enabled": False,
            "collector_enabled_ack": True, "peer_start_barrier": "released after perf control ack",
            "limitations": [
                "not whole-host CPU or performance acceptance",
                "network work on unowned ksoftirqd CPUs is not captured or attributed",
                "aggregate /proc CPU/softirq deltas include unrelated activity",
                "nested Azure physical-hypervisor CPU and hardware PMU unavailable",
            ],
        }, indent=2) + "\n")
        expected_stop = stopped_by_supervisor and perf_status == -signal.SIGINT
        if profile == "record" and (perf_status == 0 or expected_stop):
            command(["perf", "report", "--stdio", "--force", "-i", str(directory / f"{name}.perf.data"),
                     "--sort", "comm,dso,symbol"], directory, f"{name}.report", env=profile_env)
            command(["perf", "script", "-i", str(directory / f"{name}.perf.data"),
                     "--force", "--show-lost-events"], directory, f"{name}.stacks", env=profile_env)
        return peer_status or (0 if expected_stop else perf_status)
    finally:
        for child in (peer, collector):
            if child is not None and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)


def malformed_restore(directory, binary, transport, memory_directory=None, jailed=False):
    memory_directory = memory_directory or directory
    state = (memory_directory / "baseline.vmstate").read_bytes()
    net_offset = len(state) - 10 - 144
    queue = transport["queues"][0]
    avail_entry = queue["avail_gpa"] + 4 + (queue["last_avail_idx"] % queue["size"]) * 2
    memory = directory / "malformed.mem"
    shutil.copyfile(memory_directory / "baseline.mem", memory)
    memory.chmod(0o600)
    os.chown(memory, UID, GID)
    fd = os.open(memory, os.O_RDWR | os.O_CLOEXEC)
    def run_case(label, backend, state_path, trigger_rx=False):
        layout = None
        if jailed:
            case = directory / label
            private_directory(case)
            source = case / "input.mem"
            sparse_copy(memory, source)
            source.chmod(0o600)
            os.chown(source, UID, GID)
            case_state = case / "input.vmstate"
            shutil.copyfile(state_path, case_state)
            case_state.chmod(0o600)
            os.chown(case_state, UID, GID)
            layout = JailedLayout(case, backing={
                "baseline.vmstate": case_state, "baseline.mem": source,
            })
            argv = [*layout.argv(binary), "--restore", "--vmstate-path", "baseline.vmstate",
                    "--mem-path", "baseline.mem", "--net-backend", backend]
        else:
            argv = ["taskset", "-c", "8", str(binary), "--restore",
                    "--vmstate-path", str(state_path), "--mem-path", str(memory),
                    "--tap", "hn2tap0", "--net-backend", backend]
        try:
            return command(argv, directory, label, user=not jailed, timeout=10, trigger_rx=trigger_rx)
        finally:
            if layout:
                layout.close()
    try:
        head = struct.unpack("<H", os.pread(fd, 2, avail_entry))[0]
        desc = queue["desc_gpa"] + head * 16
        patches = [
            ("indirect", desc + 12, struct.pack("<H", 6), "UnadvertisedNetDescriptorFlags"),
            ("direction", desc + 12, struct.pack("<H", 0), "InvalidNetDescriptorDirection"),
            ("cycle", desc + 12, struct.pack("<HH", 3, head), "DescChainCycle"),
            ("gpa-overflow", desc, struct.pack("<Q", 0xfffffffffffffff8), "GuestMemoryOutOfBounds"),
            ("short-header", desc + 8, struct.pack("<IHH", 11, 2, 0), "NetBufferMissingHeader"),
            ("invalid-head", avail_entry, struct.pack("<H", queue["size"]), "InvalidDescIndex"),
        ]
        results = []
        for name, offset, patch, expected in patches:
            original = os.pread(fd, len(patch), offset)
            os.pwrite(fd, patch, offset)
            for backend in ("userspace", "vhost", "auto"):
                label = f"malformed-{name}-{backend}"
                status = run_case(label, backend, memory_directory / "baseline.vmstate", trigger_rx=True)
                stderr = (directory / f"{label}.stderr").read_text(errors="replace")
                passed = status not in (0, 124) and expected in stderr and "effective=userspace reason=" not in stderr
                results.append({"name": name, "backend": backend, "status": status,
                                "expected_error": expected, "passed": passed,
                                "offset": offset, "patch_hex": patch.hex()})
            os.pwrite(fd, original, offset)
        bad_state = bytearray(state)
        struct.pack_into("<Q", bad_state, net_offset + 45 + 3, queue["desc_gpa"] + 1)
        state_path = directory / "malformed.vmstate"
        state_path.write_bytes(bad_state)
        state_path.chmod(0o600)
        os.chown(state_path, UID, GID)
        for backend in ("vhost", "auto"):
            label = f"malformed-queue-alignment-{backend}"
            status = run_case(label, backend, state_path)
            stderr = (directory / f"{label}.stderr").read_text(errors="replace")
            results.append({"name": "queue-alignment", "backend": backend, "status": status,
                            "expected_error": "InvalidNetQueueAlignment",
                            "passed": status not in (0, 124) and "InvalidNetQueueAlignment" in stderr
                            and "effective=userspace reason=" not in stderr})
        feature_state = bytearray(state)
        features = struct.unpack_from("<Q", feature_state, net_offset + 25)[0]
        struct.pack_into("<Q", feature_state, net_offset + 25, features & ~(1 << 32))
        state_path.write_bytes(feature_state)
        for backend in ("userspace", "vhost", "auto"):
            label = f"malformed-features-{backend}"
            status = run_case(label, backend, state_path)
            stderr = (directory / f"{label}.stderr").read_text(errors="replace")
            results.append({"name": "version1-feature", "backend": backend, "status": status,
                            "expected_error": "NetVersion1NotNegotiated",
                            "passed": status == 1 and "NetVersion1NotNegotiated" in stderr
                            and "effective=userspace reason=" not in stderr})
        owned_file(directory / "malformed-results.json", json.dumps(results, indent=2) + "\n")
        if not all(row["passed"] for row in results):
            raise RuntimeError("real KVM malformed-queue rejection failed")
    finally:
        os.close(fd)


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


def hide_vhost(directory, kind):
    if not kind:
        return
    path = directory / "unavailable-vhost-device"
    path.write_bytes(b"")
    path.chmod(0o600)
    if kind == "uapi":
        os.chown(path, UID, GID)
    subprocess.run(["mount", "--bind", str(path), "/dev/vhost-net"], check=True)
    owned_file(directory / "vhost-capability-control.json", json.dumps({
        "kind": kind, "scope": "owned private mount namespace only; host node/ACL unchanged",
    }, indent=2) + "\n")


def strict_unavailable(args, directory):
    private_directory(directory)
    freeze_tools(directory)
    setup_tap(directory)
    hide_vhost(directory, getattr(args, "vhost_unavailable", None))
    fixture = args.artifact_dir / getattr(args, "fixture_id", "fixture")
    argv = [
        "taskset", "-c", "8", str(ROOT / "vmm/zig-out/bin/flint"),
        str(fixture / "bzImage"), str(fixture / "initrd.cpio.gz"),
        "console=ttyS0 reboot=k panic=1 pci=off", "--tap", "hn2tap0", "--net-backend", "vhost",
    ]
    status = command(argv, directory, "strict", user=True, timeout=20)
    stderr = (directory / "strict.stderr").read_text(errors="replace")
    expected = "VhostAccessDenied" if args.vhost_unavailable == "permission" else "VhostUapiUnsupported"
    passed = status == 1 and expected in stderr and "effective=userspace reason=" not in stderr
    owned_file(directory / "strict-result.json", json.dumps({
        "status": status, "expected": expected, "passed": passed,
        "classification": "real KVM strict preactivation error; not jail acceptance",
    }, indent=2) + "\n")
    if not passed:
        raise RuntimeError("strict unavailable vhost did not fail visibly and unwind")


def resource_failures(args, directory):
    private_directory(directory)
    freeze_tools(directory)
    setup_tap(directory)
    fixture = args.artifact_dir / args.fixture_id
    results = []
    for limit in (12, 14, 15):
        for backend in ("vhost", "auto"):
            name = f"fd-limit-{limit}-{backend}"
            argv = [
                "prlimit", f"--nofile={limit}:{limit}", "--", "taskset", "-c", "8",
                str(ROOT / "vmm/zig-out/bin/flint"), str(fixture / "bzImage"),
                str(fixture / "initrd.cpio.gz"), "console=ttyS0 reboot=k panic=1 pci=off",
                "--tap", "hn2tap0", "--net-backend", backend,
            ]
            status = command(argv, directory, name, user=True, timeout=20)
            stderr = (directory / f"{name}.stderr").read_text(errors="replace")
            passed = status == 1 and "NetEventfdFailed" in stderr and "effective=userspace reason=" not in stderr
            results.append({"limit": limit, "backend": backend, "status": status, "passed": passed,
                            "expected": "NetEventfdFailed, fatal resource failure; no auto fallback"})
    owned_file(directory / "resource-results.json", json.dumps(results, indent=2) + "\n")
    if not all(row["passed"] for row in results):
        raise RuntimeError("forced vhost setup resource failure did not fail and unwind")


def boot(args, directory):
    private_directory(directory)
    freeze_tools(directory)
    tap_name = getattr(args, "tap_name", "hn2tap0")
    setup_tap(directory, tap_name)
    hide_vhost(directory, getattr(args, "vhost_unavailable", None))
    sock = directory / "flint.sock"
    if len(str(sock).encode()) >= 108:
        raise ValueError("fixture API socket path exceeds sockaddr_un limit; use a shorter boot ID")
    log = directory / "serial.log"
    binary = ROOT / "vmm/zig-out/bin/flint"
    fixture = args.artifact_dir / getattr(args, "fixture_id", "fixture")
    backend = getattr(args, "net_backend", None)
    jailed = getattr(args, "jail", False)
    if getattr(args, "host_controls", False):
        host_idle_control(directory, "host-before")
    layout = JailedLayout(directory, fixture=fixture, tap_name=tap_name) if jailed else None
    memory_directory = layout.root if layout else directory
    if layout:
        sock = layout.root / "api.sock"
        argv = [*layout.argv(binary), "--api-sock", "api.sock"]
    else:
        argv = ["taskset", "-c", "8", str(binary), "--api-sock", str(sock)]
    if backend:
        argv += ["--net-backend", backend]
    try:
        with log.open("wb") as output:
            child = subprocess.Popen(
                argv,
                cwd=directory, stdout=output, stderr=subprocess.STDOUT, preexec_fn=None if layout else demote,
            )
    except BaseException:
        if layout:
            layout.close()
        raise
    traffic = None
    try:
        os.chown(log, UID, GID)
        owned_file(directory / "flint-pid.txt", str(child.pid) + "\n")
        owned_file(directory / "variant.json", json.dumps({
            "requested_backend": backend or "original-userspace",
            "classification": getattr(args, "sample_label", None) or "correctness diagnostic, not performance qualification",
            "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
            "argv": argv,
            "jailed": jailed, "memory_directory": str(memory_directory),
        }, indent=2) + "\n")
        deadline = time.monotonic() + 15
        while not sock.exists():
            if child.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("Flint API did not become ready")
            time.sleep(0.01)
        responses = [
            request(sock, "PUT", "/machine-config", {"vcpu_count": 1, "mem_size_mib": 512}),
            request(sock, "PUT", "/boot-source", {
                "kernel_image_path": "bzImage" if layout else str(fixture / "bzImage"),
                "initrd_path": "initrd.cpio.gz" if layout else str(fixture / "initrd.cpio.gz"),
                "boot_args": "console=ttyS0 reboot=k panic=1 pci=off",
            }),
            request(sock, "PUT", "/network-interfaces/eth0", {"iface_id": "eth0", "host_dev_name": tap_name}),
            request(sock, "PUT", "/actions", {"action_type": "InstanceStart"}),
        ]
        owned_file(directory / "api-configuration.txt", "\n".join(responses))
        deadline = time.monotonic() + 15
        while "PERF_TAP_READY" not in log.read_text(errors="replace"):
            if child.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("guest TAP fixture did not become ready")
            time.sleep(0.01)
        variant_path = directory / "variant.json"
        variant = json.loads(variant_path.read_text())
        variant["effective_backend"] = (
            "vhost" if "effective=vhost" in log.read_text(errors="replace") else "userspace")
        variant["notification"] = (
            "common blocked-poll, MMIO-exit kick, direct IRQ" if backend
            else "unchanged synchronous MMIO, direct IRQ, exit-driven RX")
        owned_file(variant_path, json.dumps(variant, indent=2) + "\n")
        topology_path = directory / "topology.json"
        topology = json.loads(topology_path.read_text())
        topology["backend"] = variant["effective_backend"]
        topology["notifications"] = variant["notification"]
        owned_file(topology_path, json.dumps(topology, indent=2) + "\n")
        inventory(directory, "ready", child.pid)
        if layout:
            layout.verify(child.pid, variant["effective_backend"], "ready-verified")
        summary = []
        for repetition in range(args.repetitions):
            for mode in args.modes:
                name = f"{'correctness' if backend else 'aa'}-{repetition:02d}-{mode}"
                summary.append({"name": name, "status": workload(
                    directory, mode, name, args.seconds, getattr(args, "warmup", 10),
                    rpc_rate=getattr(args, "rpc_rate", None))})
        if args.profiles:
            for mode in dict.fromkeys([*args.modes, "idle"]):
                for profile in ("stat", "record"):
                    name = f"profile-{mode}-{profile}"
                    summary.append({
                        "name": name,
                        "status": scoped_profile(directory, child.pid, mode, name, args.seconds,
                                                 0 if mode == "idle" else args.warmup, profile,
                                                 rpc_rate=getattr(args, "rpc_rate", None)),
                    })
        owned_file(directory / "summary.json", json.dumps(summary, indent=2) + "\n")
        owned_file(directory / "api-final-status.txt", request(sock, "GET", "/vm"))
        if args.reset:
            reset_checks = []
            for iteration in range(getattr(args, "reset_count", 3)):
                status = command(
                    ["taskset", "-c", "9", "python3", "-c",
                     "import socket; s=socket.create_connection(('192.0.2.2',7003),5); "
                     "s.sendall(b'RSET'); assert s.recv(4)==b'OKAY'; s.close()"],
                    directory, f"reset-{iteration}", user=True, timeout=10)
                deadline = time.monotonic() + 15
                while log.read_text(errors="replace").count("PERF_RESET_OK") < iteration + 1:
                    if child.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("guest virtio-net reset/rebind did not complete")
                    time.sleep(0.01)
                payload_status = workload(directory, "rpc", f"reset-{iteration}-rpc", 0.5, 0)
                reset_checks.append({"iteration": iteration, "request_status": status,
                                     "payload_status": payload_status})
                if status or payload_status:
                    raise RuntimeError("reset/rebind payload check failed")
                inventory(directory, f"reset-{iteration}", child.pid)
                if layout:
                    layout.verify(child.pid, variant["effective_backend"], f"reset-{iteration}-verified")
            owned_file(directory / "reset-results.json", json.dumps(reset_checks, indent=2) + "\n")
        if args.concurrent:
            status = command(
                ["taskset", "-c", "9", "python3", str(ROOT / "benchmarks/vhost-net/client_concurrency.py"),
                 "--output", str(directory / "concurrent.json")],
                directory, "concurrent", user=True, timeout=60)
            if status:
                raise RuntimeError("concurrent payload check failed")
        if args.snapshot:
            transitions = []
            if args.traffic_snapshot:
                with (directory / "traffic.log").open("wb") as output:
                    traffic = subprocess.Popen(
                        ["taskset", "-c", "9", "python3", str(ROOT / "benchmarks/vhost-net/slow_reader.py"),
                         "--directory", str(directory)],
                        stdout=output, stderr=subprocess.STDOUT, preexec_fn=demote)
                deadline = time.monotonic() + 10
                while not (directory / "traffic-ready").exists():
                    if traffic.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("in-flight peer did not become ready")
                    time.sleep(0.01)
                time.sleep(0.2)
            for method, route, body in (
                ("PATCH", "/vm", {"state": "Paused"}),
                ("PUT", "/snapshot/create", {"snapshot_path": "baseline.vmstate", "mem_file_path": "baseline.mem"}),
            ):
                begin = time.monotonic_ns()
                response = request(sock, method, route, body)
                transitions.append({"route": route, "duration_ms": (time.monotonic_ns() - begin) / 1e6,
                                    "response": response})
            inventory(directory, "paused", child.pid)
            first_hash = hashlib.sha256((memory_directory / "baseline.mem").read_bytes()).hexdigest()
            if args.traffic_snapshot:
                request(sock, "PUT", "/snapshot/create",
                        {"snapshot_path": "fenced.vmstate", "mem_file_path": "fenced.mem"})
                second_hash = hashlib.sha256((memory_directory / "fenced.mem").read_bytes()).hexdigest()
                owned_file(directory / "traffic-fence.json", json.dumps({
                    "first_sha256": first_hash, "second_sha256": second_hash,
                    "paused_ram_identical": first_hash == second_hash,
                }, indent=2) + "\n")
                if first_hash != second_hash:
                    raise RuntimeError("guest RAM changed after pause acknowledgement")
            state = (memory_directory / "baseline.vmstate").read_bytes()
            if state[:8] != b"FLINTSNP" or struct.unpack_from("<II", state, 16) != (2, 1):
                raise RuntimeError("unexpected baseline snapshot version/device count")
            net_offset = len(state) - 10 - 144
            if struct.unpack_from("<I", state, net_offset - 4)[0] != 144:
                raise RuntimeError("unexpected baseline net snapshot layout")
            net = state[net_offset:net_offset + 144]
            transport = {
                "classification": (
                    "common net pause/snapshot/resume diagnostic; traffic/cross-backend restore not yet accepted"
                    if backend else "baseline vCPU-only pause/snapshot/resume; not vhost worker or traffic acceptance"),
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
            if traffic is not None:
                owned_file(directory / "traffic-release", "resume acknowledged\n")
                if traffic.wait(timeout=90):
                    raise RuntimeError("in-flight payload check failed")
            if workload(directory, "rpc", "post-resume-rpc", 0.5, 0):
                raise RuntimeError("post-resume payload check failed")
            inventory(directory, "resumed", child.pid)
            if args.restore_backend:
                request(sock, "PATCH", "/vm", {"state": "Paused"})
                child.terminate()
                child.wait(timeout=5)
                sock.unlink(missing_ok=True)
                if layout:
                    layout.close()
                    layout = None
                    layout = JailedLayout(directory / "restore", backing={
                        "baseline.vmstate": memory_directory / "baseline.vmstate",
                        "baseline.mem": memory_directory / "baseline.mem",
                    }, tap_name=tap_name)
                    sock = layout.root / "api.sock"
                    restore_argv = [*layout.argv(binary), "--restore",
                                    "--vmstate-path", "baseline.vmstate", "--mem-path", "baseline.mem",
                                    "--net-backend", args.restore_backend, "--api-sock", "api.sock"]
                else:
                    restore_argv = [
                        "taskset", "-c", "8", str(binary), "--restore",
                        "--vmstate-path", str(memory_directory / "baseline.vmstate"),
                        "--mem-path", str(memory_directory / "baseline.mem"), "--tap", tap_name,
                        "--net-backend", args.restore_backend, "--api-sock", str(sock),
                    ]
                with (directory / "restore.log").open("wb") as output:
                    child = subprocess.Popen(restore_argv, cwd=directory, stdout=output,
                                             stderr=subprocess.STDOUT, preexec_fn=None if layout else demote)
                owned_file(directory / "restore-pid.txt", str(child.pid) + "\n")
                deadline = time.monotonic() + 15
                while not sock.exists():
                    if child.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("restored API did not become ready")
                    time.sleep(0.01)
                inventory(directory, "restored", child.pid)
                if layout:
                    layout.verify(child.pid, args.restore_backend, "restored-verified")
                restore_variant = {**variant, "effective_backend": args.restore_backend,
                                   "restore_argv": restore_argv}
                owned_file(directory / "restore-variant.json", json.dumps(restore_variant, indent=2) + "\n")
                checks = {mode: workload(directory, mode, f"restored-{mode}", 0.5, 0,
                                        variant_override=restore_variant)
                          for mode in ("rpc", "h2g", "g2h", "wake")}
                after_hash = hashlib.sha256((memory_directory / "baseline.mem").read_bytes()).hexdigest()
                owned_file(directory / "restore-cow.json", json.dumps({
                    "from_backend": backend, "to_backend": args.restore_backend,
                    "format_version": 2, "payload_checks": checks,
                    "backing_before_sha256": first_hash, "backing_after_sha256": after_hash,
                    "map_private_backing_unchanged": first_hash == after_hash,
                }, indent=2) + "\n")
                if any(checks.values()) or first_hash != after_hash:
                    raise RuntimeError("cross-backend restore payload/CoW check failed")
            if args.malformed:
                request(sock, "PATCH", "/vm", {"state": "Paused"})
                child.terminate()
                child.wait(timeout=5)
                if layout:
                    layout.close()
                    layout = None
                malformed_restore(directory, binary, transport, memory_directory, jailed=jailed)
    finally:
        if traffic is not None and traffic.poll() is None:
            traffic.terminate()
            traffic.wait(timeout=5)
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        try:
            owned_file(directory / "flint-exit-status.txt", str(child.returncode) + "\n")
        finally:
            if layout:
                layout.close()
        if getattr(args, "host_controls", False):
            host_idle_control(directory, "host-after")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--phase", choices=("probe", "boot", "quiet", "selftest", "strict", "resource"), required=True)
    parser.add_argument("--boot-id", default="boot-01")
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--profiles", action="store_true")
    parser.add_argument("--net-backend", choices=("userspace", "vhost", "auto"))
    parser.add_argument("--warmup", type=float, default=10)
    parser.add_argument("--rpc-rate", type=float)
    parser.add_argument("--sample-label")
    parser.add_argument("--tap-name", default="hn2tap0")
    parser.add_argument("--host-controls", action="store_true")
    parser.add_argument("--snapshot", action="store_true")
    parser.add_argument("--traffic-snapshot", action="store_true")
    parser.add_argument("--restore-backend", choices=("userspace", "vhost"))
    parser.add_argument("--malformed", action="store_true")
    parser.add_argument("--concurrent", action="store_true")
    parser.add_argument("--vhost-unavailable", choices=("permission", "uapi"))
    parser.add_argument("--fixture-id", choices=("fixture", "fixture-reset"), default="fixture")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--reset-count", type=int, default=3)
    parser.add_argument("--jail", action="store_true")
    parser.add_argument("--control-id")
    parser.add_argument("--modes", nargs="+", choices=("rpc", "h2g", "g2h", "wake", "idle"),
                        default=["rpc", "h2g", "g2h", "wake"])
    args = parser.parse_args()
    if not 1 <= args.reset_count <= 256:
        parser.error("reset-count must be between1 and256")
    if args.rpc_rate is not None and args.rpc_rate <= 0:
        parser.error("rpc-rate must be positive")
    if args.phase == "strict" and not args.vhost_unavailable:
        parser.error("strict phase needs an owned unavailable-device control")
    if args.traffic_snapshot or args.restore_backend or args.malformed:
        args.snapshot = True
    if args.phase in ("probe", "quiet"):
        raise ValueError("new profiling requires a scoped owned-process/kernel collector; historical all-host stack capture is disabled")
    os.umask(0o077)
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
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
        elif args.phase == "strict":
            strict_unavailable(args, directory)
        elif args.phase == "resource":
            resource_failures(args, directory)
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
