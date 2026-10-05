#!/usr/bin/env python3
"""Owned, project-local baseline capability probes; not an async benchmark gate.

Invoke under the fleet host lock. No backend selector or runtime patch is used.
The smoke workload is intentionally not a replacement for the specified fio,
offline package/build, concurrency, or acceptance sample matrix.
"""

import argparse
import base64
import csv
import hashlib
import http.client
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import socket
import struct
import subprocess
import statistics
import tarfile
import time


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / ".perf/blk-io"
KERNEL_HASH = "4da539807474d189f1a15852046994e78d430a194c2e78b9255ae880069c7208"
MAX_FRAME = 16 * 1024 * 1024


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")
    path.chmod(0o600)


def run_logged(argv, output, timeout=120, cwd=ROOT):
    with output.open("wb") as log:
        result = subprocess.run(
            argv, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, timeout=timeout,
            check=False,
        )
    return {"argv": argv, "exit_code": result.returncode, "log": str(output.relative_to(ROOT))}


def privileged_perf(argv):
    if not ARTIFACTS.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("perf paths must remain inside the project")
    for name in ("perf-buildid-cache", "perf-scratch"):
        directory = ARTIFACTS / name
        if directory.is_symlink():
            raise ValueError("perf paths must be nonsymlink project directories")
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = directory.stat()
        if info.st_uid != os.getuid() or info.st_mode & 0o777 != 0o700:
            raise PermissionError("perf paths must be caller-owned with mode0700")
    cache = ARTIFACTS / "perf-buildid-cache"
    return ["sudo", "-n", "--", "env", f"PERF_BUILDID_DIR={cache.resolve()}",
            f"TMPDIR={(ARTIFACTS / 'perf-scratch').resolve()}",
            "DEBUGINFOD_URLS=", "perf", *argv]


def receive_exact(connection, length):
    data = bytearray()
    while len(data) < length:
        part = connection.recv(length - len(data))
        if not part:
            raise ConnectionError("agent closed a partial frame")
        data.extend(part)
    return bytes(data)


def receive_frame(connection):
    length = struct.unpack("<I", receive_exact(connection, 4))[0]
    if length > MAX_FRAME:
        raise ValueError(f"agent frame exceeds {MAX_FRAME} bytes")
    return json.loads(receive_exact(connection, length))


def send_frame(connection, value):
    payload = json.dumps(value, separators=(",", ":")).encode()
    if len(payload) > MAX_FRAME:
        raise ValueError("outgoing frame exceeds protocol limit")
    connection.sendall(struct.pack("<I", len(payload)) + payload)


def request(api_path, method, target, body=None):
    payload = b"" if body is None else json.dumps(body).encode()
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(10)
        connection.connect(str(api_path))
        connection.sendall(
            f"{method} {target} HTTP/1.1\r\nHost: localhost\r\n"
            f"Content-Length: {len(payload)}\r\nConnection: close\r\n\r\n".encode() + payload
        )
        response = http.client.HTTPResponse(connection)
        response.begin()
        data = response.read()
        if response.status not in (200, 204):
            raise RuntimeError(f"{method} {target}: HTTP {response.status}: {data!r}")
        return data


def make_fixture():
    fixture = ARTIFACTS / "fixture"
    kernel = fixture / "bzImage"
    if sha256(kernel) != KERNEL_HASH:
        raise ValueError("unverified kernel; fetch the pinned CI release first")
    root = fixture / "initramfs"
    root.mkdir(mode=0o700)
    for name in ("bin", "dev", "proc", "sys", "mnt"):
        (root / name).mkdir(mode=0o700)
    shutil.copyfile("/usr/bin/busybox", root / "bin/busybox")
    shutil.copyfile(ARTIFACTS / "baseline/hearth-agent-safe", root / "bin/hearth-agent")
    for name in ("busybox", "hearth-agent"):
        (root / "bin" / name).chmod(0o700)
    (root / "bin/sh").symlink_to("busybox")
    (root / "init").write_text(
        "#!/bin/sh\nset -eu\n"
        "/bin/busybox mount -t devtmpfs devtmpfs /dev\n"
        "exec </dev/console >/dev/console 2>&1\n"
        "/bin/busybox mount -t proc proc /proc\n"
        "/bin/busybox mount -t sysfs sysfs /sys\n"
        "/bin/busybox mount -t ext4 /dev/vda /mnt\n"
        "echo BLOCK_FIXTURE_BOOT_OK\n"
        # Existing vsock RX needs ordinary KVM exits. Account this independently.
        "case \"$(/bin/busybox cat /proc/cmdline)\" in\n"
        "  *perf_heartbeat=1*) (while :; do echo HB; /bin/busybox usleep 10000; done) & ;;\n"
        "esac\n"
        "exec /bin/hearth-agent\n"
    )
    (root / "init").chmod(0o700)
    archive = fixture / "initrd.cpio.gz"
    entries = ["."]
    entries.extend(str(path.relative_to(root)) for path in sorted(root.rglob("*")))
    with (fixture / "cpio.log").open("wb") as errors, archive.open("wb") as output:
        pack = subprocess.Popen(
            ["bsdcpio", "-o", "-H", "newc", "--null"], cwd=root,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
        )
        compress = None
        try:
            compress = subprocess.Popen(["gzip", "-n"], stdin=pack.stdout, stdout=output)
            pack.stdout.close()
            pack.communicate(("\0".join(entries) + "\0").encode(), timeout=60)
            if pack.returncode != 0 or compress.wait(timeout=60) != 0:
                raise RuntimeError("initramfs packing failed")
        finally:
            for child in (pack, compress):
                if child is not None and child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)
    disk = fixture / "disk.ext4"
    with disk.open("wb") as output:
        output.truncate(8 * 1024**3)
    result = run_logged(
        ["mke2fs", "-q", "-F", "-t", "ext4", "-E", "lazy_itable_init=0,lazy_journal_init=0",
         str(disk)], fixture / "mke2fs.log",
    )
    if result["exit_code"] != 0:
        raise RuntimeError("ext4 fixture failed")
    save_json(fixture / "manifest.json", {
        "kernel_sha256": sha256(kernel), "initrd_sha256": sha256(archive),
        "busybox_sha256": sha256(root / "bin/busybox"),
        "agent_sha256": sha256(root / "bin/hearth-agent"),
        "disk_bytes": disk.stat().st_size, "prefilled_data_bytes": 0,
        "fixture_status": "capability smoke only; fio/package/build not provisioned",
        "mke2fs": result,
    })


def inventory():
    path = ARTIFACTS / "baseline"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    commands = {
        "source": ["git", "rev-parse", "HEAD"],
        "source-status": ["git", "status", "--short"],
        "source-diff": ["git", "diff", "--", "vmm", "agent", "tools/perf", ".github/workflows/ci.yml"],
        "compiler": ["/home/g/.local/bin/zig", "version"],
        "kernel": ["uname", "-a"],
        "cpu": ["lscpu"],
        "storage": ["findmnt", "-T", str(ROOT), "-o", "SOURCE,FSTYPE,OPTIONS,TARGET"],
        "perf-version": ["perf", "--version"],
        "perf-list": ["perf", "list", "--details"],
        "python": ["python3", "--version"],
        "libc": ["ldd", "--version"],
        "busybox": ["busybox", "--help"],
        "ext4": ["mke2fs", "-V"],
        "hardware-probe": privileged_perf(["stat", "-e", "cycles,instructions", "--", "sleep", "0.2"]),
        "software-probe": privileged_perf(["stat", "-e",
                           "task-clock,context-switches,cpu-migrations,page-faults", "--", "sleep", "0.2"]),
        "trace-events": ["sudo", "-n", "cat", "/sys/kernel/tracing/available_events"],
    }
    results = {name: run_logged(argv, path / f"{name}.txt") for name, argv in commands.items()}
    kvm = os.open("/dev/kvm", os.O_RDWR | os.O_CLOEXEC)
    try:
        version = fcntl.ioctl(kvm, 0xAE00, 0)
        if version != 12:
            raise RuntimeError(f"KVM API version is {version}, not 12")
        vm = fcntl.ioctl(kvm, 0xAE01, 0)
        os.close(vm)
    finally:
        os.close(kvm)
    files = [
        "vmm/build.zig.zon", "agent/build.zig.zon", ".perf/blk-io/baseline/flint-safe",
        ".perf/blk-io/baseline/hearth-agent-safe", ".perf/blk-io/fixture/bzImage",
    ]
    dependencies = {}
    for archive in sorted((ARTIFACTS / "zig-global-cache/p").glob("*.tar.gz")):
        with tarfile.open(archive) as package:
            for entry in package.getmembers():
                if entry.name.endswith("/build.zig.zon"):
                    manifest = package.extractfile(entry).read()
                    dependencies[str(archive.relative_to(ROOT))] = {
                        "archive_sha256": sha256(archive),
                        "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
                        "manifest": manifest.decode(),
                    }
    save_json(path / "manifest.json", {
        "execution_revision": "b06ec0a6c19b4977bfb602c2daa1d94acf3eacf7",
        "runtime_source_revision": "b07f73b26b8ae876928d9c515b94bba1e9945870",
        "backend": "unchanged synchronous; legacy MMIO/IRQ; no experimental selector",
        "compiler": "Zig 0.17.0; -Dtarget=x86_64-linux -Doptimize=safe",
        "agent": "Zig 0.17.0; -Dtarget=x86_64-linux-musl -Doptimize=safe",
        "uid": os.getuid(), "gid": os.getgid(), "affinity": sorted(os.sched_getaffinity(0)),
        "kvm_api": version, "vm_creation": "passed",
        "perf_event_paranoid": Path("/proc/sys/kernel/perf_event_paranoid").read_text().strip(),
        "commands": results,
        "files": {name: sha256(ROOT / name) for name in files},
        "resolved_dependency_manifests": dependencies,
        "not_measured": ["non-nested host", "Azure storage service-level latency"],
    })


class OwnedVm:
    def __init__(self, path, cpu, jailed=True, heartbeat=True, boot_mode="api",
                 trace_startup=False, startup_perf="none", startup_frequency=199):
        self.path = path
        self.path_created = False
        self.cpu = cpu
        self.jailed = jailed
        self.heartbeat = heartbeat
        self.boot_mode = boot_mode
        self.trace_startup = trace_startup
        self.startup_perf = startup_perf
        self.startup_frequency = startup_frequency
        self.process = None
        self.pid = None
        self.agent = None
        self.stdout = None
        self.stderr = None
        self.listener = None

    def __enter__(self):
        try:
            self.path.mkdir(mode=0o700)
            self.path_created = True
            for source, target in (
                ("fixture/bzImage", "bzImage"),
                ("fixture/initrd.cpio.gz", "initrd.cpio.gz"),
                ("fixture/disk.ext4", "disk.ext4"),
            ):
                subprocess.run(
                    ["cp", "--reflink=auto", str(ARTIFACTS / source), str(self.path / target)],
                    check=True, timeout=120,
                )
            self.listener = socket.socket(socket.AF_UNIX)
            self.listener.settimeout(15)
            self.listener.bind(str(self.path / "vsock_1024"))
            self.listener.listen(1)
            self.stdout = (self.path / "serial.log").open("wb")
            self.stderr = (self.path / "vmm.log").open("wb")
            argv = ["taskset", "-c", str(self.cpu), str(ARTIFACTS / "baseline/flint-safe")]
            if self.jailed:
                argv = ["sudo", "-n", "--", *argv, "--jail", str(self.path),
                        "--jail-uid", str(os.getuid()), "--jail-gid", str(os.getgid())]
            prefix = "/" if self.jailed else str(self.path) + "/"
            boot_args = ("console=ttyS0 reboot=k panic=1 pci=off rdinit=/init "
                         f"perf_heartbeat={int(self.heartbeat)}")
            if self.boot_mode == "api":
                argv.extend(["--api-sock", "api.sock"])
            else:
                argv.extend([prefix + "bzImage", prefix + "initrd.cpio.gz", boot_args,
                             "--disk", prefix + "disk.ext4", "--vsock-cid", "100",
                             "--vsock-uds", prefix + "vsock"])
            if self.trace_startup:
                if not self.jailed:
                    raise ValueError("startup trace requires the unchanged enforced jail")
                argv = ["sudo", "-n", "--", str(ARTIFACTS / "tools/strace/usr/bin/strace"),
                        "-f", "-o", str(self.path / "startup.strace"), *argv[3:]]
            if self.startup_perf != "none":
                if not self.jailed or self.trace_startup:
                    raise ValueError("startup perf requires a jailed, untraced baseline")
                if self.startup_perf == "stat":
                    collector = ["stat", "-x,", "-o", str(self.path / "perf-stat.csv"),
                                 "-e", "task-clock,context-switches,cpu-migrations,page-faults"]
                else:
                    collector = ["record", "-q", "-e", "cpu-clock", "-F", str(self.startup_frequency),
                                 "-g", "--call-graph", "dwarf", "-o", str(self.path / "perf.data")]
                argv = [*privileged_perf(collector), "--", *argv[3:]]
            self.process = subprocess.Popen(
                argv, cwd=self.path, stdout=self.stdout, stderr=self.stderr,
                start_new_session=True,
            )
            save_json(self.path / "launch.json", {
                "argv": argv, "supervisor_pid": self.process.pid, "jailed": self.jailed,
                "heartbeat": self.heartbeat, "boot_mode": self.boot_mode,
            })
            if self.boot_mode == "api":
                deadline = time.monotonic() + 15
                while not (self.path / "api.sock").exists():
                    if self.process.poll() is not None:
                        raise RuntimeError(f"VMM exited before API: {self.process.returncode}")
                    if time.monotonic() > deadline:
                        raise TimeoutError("API socket did not become ready")
                    time.sleep(0.02)
            else:
                deadline = time.monotonic() + 15
                self.listener.settimeout(0.1)
                while True:
                    if self.process.poll() is not None:
                        raise RuntimeError(f"VMM exited before guest connected: {self.process.returncode}")
                    if time.monotonic() > deadline:
                        raise TimeoutError("guest control connection did not become ready")
                    try:
                        self.agent, _ = self.listener.accept()
                        break
                    except TimeoutError:
                        continue
            self.pid = self.find_vm_pid()
            save_json(self.path / "pid.json", {"vmm_pid": self.pid, "supervisor_pid": self.process.pid})
            if self.boot_mode == "api":
                self.api("PUT", "/machine-config", {"mem_size_mib": 512})
                self.api("PUT", "/boot-source", {
                    "kernel_image_path": prefix + "bzImage", "initrd_path": prefix + "initrd.cpio.gz",
                    "boot_args": boot_args,
                })
                self.api("PUT", "/drives/disk", {
                    "drive_id": "disk", "path_on_host": prefix + "disk.ext4",
                    "is_root_device": False, "is_read_only": False,
                })
                self.api("PUT", "/vsock", {"guest_cid": 100, "uds_path": prefix + "vsock"})
                self.api("PUT", "/actions", {"action_type": "InstanceStart"})
                self.agent, _ = self.listener.accept()
            self.agent.settimeout(10)
            return self
        except BaseException:
            self.close()
            raise

    def find_vm_pid(self):
        if not self.jailed:
            return self.process.pid
        pending = [self.process.pid]
        while pending:
            parent = pending.pop()
            try:
                children_path = Path(f"/proc/{parent}/task/{parent}/children")
                try:
                    children = children_path.read_text().split()
                except PermissionError:
                    children = subprocess.run(
                        ["sudo", "-n", "cat", str(children_path)], capture_output=True,
                        text=True, check=True, timeout=5,
                    ).stdout.split()
                for child in children:
                    executable = Path(f"/proc/{child}/comm").read_text().strip()
                    if executable.startswith("flint"):
                        return int(child)
                    pending.append(int(child))
            except FileNotFoundError:
                continue
        raise RuntimeError("owned sudo VMM child PID could not be identified")

    def api(self, method, target, body=None):
        return request(self.path / "api.sock", method, target, body)

    def command(self, cmd, timeout=10):
        start = time.monotonic_ns()
        send_frame(self.agent, {"method": "exec", "cmd": cmd, "timeout": timeout})
        response = receive_frame(self.agent)
        elapsed = (time.monotonic_ns() - start) / 1e6
        if response.get("ok") is not True or response.get("exit_code") != 0:
            raise RuntimeError(f"guest command failed: {response!r}")
        output = base64.b64decode(response.get("stdout", "")).decode(errors="replace")
        return {"cmd": cmd, "response_ms": elapsed, "stdout": output,
                "stderr": base64.b64decode(response.get("stderr", "")).decode(errors="replace")}

    def close(self):
        if self.agent is not None:
            self.agent.close()
        if self.listener is not None:
            self.listener.close()
        if self.process is not None and self.process.poll() is None:
            if self.pid is None:
                try:
                    self.pid = self.find_vm_pid()
                except (OSError, RuntimeError):
                    pass
            try:
                still_owned = self.pid is not None and self.find_vm_pid() == self.pid
            except (OSError, RuntimeError):
                still_owned = False
            if still_owned:
                subprocess.run(
                    ["sudo", "-n", "kill", "-TERM", str(self.pid)] if self.jailed
                    else ["kill", "-TERM", str(self.pid)],
                    check=False, timeout=10,
                )
            else:
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    still_owned = still_owned and self.find_vm_pid() == self.pid
                except (OSError, RuntimeError):
                    still_owned = False
                if still_owned:
                    subprocess.run(
                        ["sudo", "-n", "kill", "-KILL", str(self.pid)] if self.jailed
                        else ["kill", "-KILL", str(self.pid)],
                        check=False, timeout=10,
                    )
                self.process.kill()
                self.process.wait(timeout=5)
        for output in (self.stdout, self.stderr):
            if output is not None:
                output.close()
        if self.process is not None:
            save_json(self.path / "exit.json", {
                "supervisor_pid": self.process.pid, "vmm_pid": self.pid,
                "supervisor_exit_code": self.process.returncode,
            })
        if self.path_created:
            for name in ("api.sock", "vsock_1024"):
                (self.path / name).unlink(missing_ok=True)

    def __exit__(self, *_):
        self.close()


def smoke(args):
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", args.name):
        raise ValueError("run name must be a single safe project-local basename")
    path = ARTIFACTS / args.name
    if path.exists():
        raise FileExistsError("run directory already exists; preserve evidence and choose a new name")
    try:
        with OwnedVm(path, args.cpu, jailed=not args.unjailed, heartbeat=not args.no_heartbeat,
                     boot_mode=args.boot_mode, trace_startup=args.trace_startup,
                     startup_perf=args.startup_perf, startup_frequency=args.startup_frequency) as vm:
            output = vm.command("echo AGENT_EXEC_OK; /bin/busybox uname -a; "
                                "/bin/busybox cat /proc/mounts; /bin/busybox cat /proc/meminfo")
            disk = None
            if args.disk_probe:
                marker = "ASYNC_BLOCK_BASELINE_CAPABILITY"
                disk = vm.command(
                    "set -eu; /bin/busybox cat /sys/block/vda/stat; "
                    f"printf {marker} > /mnt/probe.txt; /bin/busybox sync; "
                    "/bin/busybox cat /mnt/probe.txt; /bin/busybox sha256sum /mnt/probe.txt; "
                    "/bin/busybox cat /sys/block/vda/stat"
                )
                if hashlib.sha256(marker.encode()).hexdigest() not in disk["stdout"]:
                    raise RuntimeError("guest disk capability marker hash did not match")
            save_json(path / "smoke.json", {
                "status": "passed", "exec": output, "pid": vm.pid, "disk_capability": disk,
                "acceptance": "capability smoke only; not a performance or async acceptance cell",
            })
    except (OSError, RuntimeError, TimeoutError, ConnectionError) as error:
        path.mkdir(mode=0o700, exist_ok=True)
        save_json(path / "smoke.json", {"status": "blocked", "error": str(error)})
        raise
    finally:
        data = path / "perf.data"
        if args.startup_perf == "record" and data.exists():
            reports = {
                "report": ["report", "--force", "--stdio", "--percent-limit", "0.5", "-i", str(data)],
                "header": ["report", "--force", "--stdio", "--header-only", "-i", str(data)],
                "buildids": ["buildid-list", "-i", str(data)],
                "samples": ["script", "--force", "-i", str(data), "-F", "comm,pid,tid,event"],
            }
            save_json(path / "perf-reports.json", {
                name: run_logged(privileged_perf(argv), path / f"perf-{name}.txt")
                for name, argv in reports.items()
            })


def diagnose():
    manifest = ARTIFACTS / "baseline/manifest.json"
    initial = ARTIFACTS / "baseline/manifest-initial.json"
    if manifest.exists() and not initial.exists():
        shutil.copyfile(manifest, initial)
    inventory()
    control = ARTIFACTS / "idle-capability-control"
    control.mkdir(mode=0o700)
    (control / "proc-stat-before.txt").write_text(Path("/proc/stat").read_text())
    before = time.monotonic_ns()
    time.sleep(5)
    after = time.monotonic_ns()
    (control / "proc-stat-after.txt").write_text(Path("/proc/stat").read_text())
    save_json(control / "window.json", {
        "elapsed_ns": after - before, "kind": "whole-host idle capability control",
        "not_attribution": "other users remain active; no VMM disk workload executed",
    })
    series = []
    configurations = [
        ("diag-api-trace", "api", True, "none"),
        ("diag-cli-trace", "cli", True, "none"),
    ]
    configurations.extend((f"diag-api-stat-{number}", "api", False, "stat") for number in range(1, 4))
    configurations.extend((f"diag-api-record-{number}", "api", False, "record") for number in range(1, 4))
    for name, boot_mode, trace_startup, startup_perf in configurations:
        args = argparse.Namespace(
            name=name, cpu=8, unjailed=False, no_heartbeat=False, boot_mode=boot_mode,
            trace_startup=trace_startup, startup_perf=startup_perf,
            startup_frequency=199,
            disk_probe=False,
        )
        try:
            smoke(args)
            status = "passed"
            error = None
        except (OSError, RuntimeError, TimeoutError, ConnectionError) as failure:
            status = "blocked"
            error = str(failure)
        series.append({"name": name, "status": status, "error": error})
    save_json(ARTIFACTS / "diagnostic-series.json", {
        "series": series, "cpu": 8, "jailed": True,
        "scope": "startup/capability diagnostics, NOT baseline disk-performance samples",
        "mandatory_performance_cells_executed": 0, "prototype_selected": False,
    })


def read_private(path):
    try:
        return path.read_text()
    except PermissionError:
        return subprocess.run(
            ["sudo", "-n", "cat", str(path)], capture_output=True, text=True, check=True,
            timeout=10,
        ).stdout


def analyze():
    clocks = []
    switches = []
    for path in sorted(ARTIFACTS.glob("diag-api-stat-*/perf-stat.csv")):
        for row in csv.reader(read_private(path).splitlines()):
            if len(row) >= 3 and row[2] == "task-clock":
                # PERF_COUNT_SW_TASK_CLOCK is a nanosecond counter; retain raw CSV.
                clocks.append(int(row[0]) / 1e6)
            elif len(row) >= 3 and row[2] == "context-switches":
                switches.append(int(row[0]))
    profiles = {}
    for path in sorted(ARTIFACTS.glob("diag-api-record*/perf-report.txt")):
        report = path.read_text()
        samples = re.search(r"# Samples: (\d+)\s+of event 'cpu-clock'", report)
        lost = re.search(r"# Total Lost Samples: (\d+)", report)
        profiles[str(path.parent.relative_to(ROOT))] = {
            "samples": int(samples[1]) if samples else 0,
            "lost_samples": int(lost[1]) if lost else None,
            "no_samples_diagnostic": "data has no samples" in report,
        }
    control = ARTIFACTS / "idle-capability-control"
    before = list(map(int, (control / "proc-stat-before.txt").read_text().splitlines()[0].split()[1:9]))
    after = list(map(int, (control / "proc-stat-after.txt").read_text().splitlines()[0].split()[1:9]))
    deltas = [end - start for start, end in zip(before, after)]
    total = sum(deltas)
    busy = total - deltas[3] - deltas[4] - deltas[7]
    tools = [ARTIFACTS / "tools/strace.deb", ARTIFACTS / "fixture/ubuntu-base.tar.gz"]
    save_json(ARTIFACTS / "analysis.json", {
        "decision": "blocked at G0; keep synchronous; not eligible for performance merge",
        "prototype_selected": False, "baseline_numeric_gates_frozen": False,
        "required_disk_performance_cells_executed": 0,
        "before_after_performance": None,
        "startup_failure_task_clock_ms": {
            "samples": clocks, "mean": statistics.mean(clocks),
            "sample_standard_deviation": statistics.stdev(clocks),
            "scope": "taskset + aborted VMM startup; NOT disk CPU/completion or A/A gate noise",
            "context_switches": switches,
        },
        "startup_profiles": profiles,
        "whole_host_idle_capability_control": {
            "proc_stat_delta_jiffies": deltas, "busy_percent": 100 * busy / total,
            "iowait_percent": 100 * deltas[4] / total, "steal_percent": 100 * deltas[7] / total,
            "scope": "one 5s host control; external work included; NOT attributable kernel I/O cost",
        },
        "auxiliary_download_sha256": {str(path.relative_to(ROOT)): sha256(path) for path in tools},
    })


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="mode", required=True)
    subcommands.add_parser("fixture")
    subcommands.add_parser("inventory")
    subcommands.add_parser("diagnose")
    subcommands.add_parser("analyze")
    command = subcommands.add_parser("smoke")
    command.add_argument("--name", default="smoke-jailed")
    command.add_argument("--cpu", type=int, default=8)
    command.add_argument("--unjailed", action="store_true",
                         help="capability diagnosis only; not valid acceptance profiling")
    command.add_argument("--no-heartbeat", action="store_true")
    command.add_argument("--disk-probe", action="store_true",
                         help="write/sync/verify one guest marker, NOT a performance workload")
    command.add_argument("--boot-mode", choices=("api", "cli"), default="api")
    command.add_argument("--trace-startup", action="store_true")
    command.add_argument("--startup-perf", choices=("none", "stat", "record"), default="none",
                         help="profile startup failure, NOT the disk acceptance workload")
    command.add_argument("--startup-frequency", type=int, choices=range(1, 10000), default=199,
                         metavar="HZ")
    args = parser.parse_args()
    if args.mode == "fixture":
        make_fixture()
    elif args.mode == "inventory":
        inventory()
    elif args.mode == "diagnose":
        diagnose()
    elif args.mode == "analyze":
        analyze()
    else:
        if args.cpu not in os.sched_getaffinity(0):
            parser.error("selected CPU is outside permitted affinity")
        smoke(args)


if __name__ == "__main__":
    main()
