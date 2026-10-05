#!/usr/bin/env python3
"""Label-approved ephemeral qualification; private raw data, allowlisted receipts."""

import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import select
import shutil
import signal
import socket
import statistics
import subprocess
import sys
import threading
import time
import urllib.request
from types import SimpleNamespace

import analyze_trace
import control
import custody
import matrix
import performance
import restore_stress
import run as bench
import tap_probe
import visible_cpu

HOME = bench.ROOT / ".perf/eventfd-hosted"
PUBLIC = HOME / "public"
RAW = HOME / "raw"
MODES = ("C00", "C10", "C01", "C11")
GATES = {
    "benefit_percent": 10, "paired_confidence": .95,
    "mechanism_reduction_percent": 90, "max_throughput_regression_percent": 3,
    "max_cpu_latency_lifecycle_regression_percent": 5,
    "max_noise_cpu_latency_cv_percent": 10, "max_noise_throughput_cv_percent": 5,
    "idle_extra_core_percentage_points_per_sandbox": .1,
}
KERNEL_GAPS = [
    "irqfd workqueue dispatcher and scheduler outside the tagged function intervals",
    "marginal TAP/softirq and resample scheduling outside owned task/function intervals",
]
REQUIRED_GAPS = [
    "100 reset transitions and full active IRQ congestion",
    "20 active fresh cross-mode snapshots per mode/device mix",
    "10 failure-teardown cycles and 64-connection credit stress",
    "actual CLI/API save-on-halt and old/new legacy compatibility",
    "matched mixed-device 4/8-sandbox performance and pure-HLT idle",
]
KVM_CAPABILITIES = {"irqfd": 32, "ioeventfd": 36, "resample": 82, "immediate_exit": 136}
TEST_ERROR_LABELS = frozenset({
    "AccessDenied", "ConnectFailed", "FileNotFound", "GuestBootFailed",
    "InitrdBuildFailed", "KernelUnavailable", "NotDir",
    "TestExpectedEqual", "TestUnexpectedResult",
})


class Blocked(RuntimeError):
    pass


def save(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    bench.save_json(path, value)


def cpulist(text):
    values = set()
    for part in text.strip().split(","):
        bounds = list(map(int, part.split("-")))
        if len(bounds) > 2 or bounds[0] > bounds[-1]:
            raise ValueError("invalid CPU topology")
        values.update(range(bounds[0], bounds[-1] + 1))
    return values


def independent_cpus(topology):
    for vm in sorted(topology):
        for client in sorted(topology):
            if (client not in topology[vm]["siblings"] and vm not in topology[client]["siblings"]
                    and topology[vm]["core"] != topology[client]["core"]):
                return vm, client
    raise Blocked("fewer than two available independent physical cores")


def actual_topology():
    result = {}
    for cpu in sorted(os.sched_getaffinity(0)):
        root = Path(f"/sys/devices/system/cpu/cpu{cpu}/topology")
        result[cpu] = {
            "core": [int((root / "physical_package_id").read_text()),
                     int((root / "core_id").read_text())],
            "siblings": sorted(cpulist((root / "thread_siblings_list").read_text())),
        }
    return result


def owned_command(argv, name, seconds, cwd=bench.ROOT, environment=None):
    RAW.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (RAW / f"{name}.stdout").open("wb") as output, (RAW / f"{name}.stderr").open("wb") as errors:
        process = subprocess.Popen(
            ["timeout", "--signal=TERM", "--kill-after=30s", str(seconds), *map(str, argv)],
            cwd=cwd, stdout=output, stderr=errors, env=environment,
        )
        try:
            code = process.wait(timeout=seconds + 35)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=35)
    record = {"name": name, "returncode": code,
              "stdout_sha256": bench.digest(RAW / f"{name}.stdout"),
              "stderr_sha256": bench.digest(RAW / f"{name}.stderr")}
    save(RAW / f"{name}.command.json", {"argv": list(map(str, argv)), "cwd": str(cwd), **record})
    return record


def output(name):
    return (RAW / f"{name}.stdout").read_text(errors="replace")


def check_space(minimum):
    free = shutil.disk_usage(bench.ROOT).free
    if free < minimum:
        raise Blocked(f"owned phase capacity guard: {free} bytes available, {minimum} required")
    return free


def remove_owned_images(directory, names):
    directory = directory.resolve()
    directory.relative_to(bench.ROOT / ".perf")
    removed = []
    for name in names:
        if Path(name).name != name:
            raise Blocked("image cleanup requires explicit leaf names")
        path = directory / name
        if not path.exists():
            continue
        if path.is_symlink() or not path.is_file() or path.stat().st_uid != os.getuid():
            raise Blocked("refusing nonregular/symlink/nonowned image cleanup")
        record = {"path": str(path.relative_to(bench.ROOT)), "bytes": path.stat().st_size,
                  "sha256": bench.digest(path)}
        path.unlink()
        removed.append(record)
    return removed


def perf_binary():
    paths = [shutil.which("perf"), *sorted(Path("/usr/lib/linux-tools").glob("*/perf"), reverse=True)]
    attempts = []
    for index, candidate in enumerate(paths):
        if candidate and Path(candidate).is_file():
            name = f"perf-version-{index}"
            record = owned_command([candidate, "--version"], name, 5)
            attempts.append({"path": str(candidate), **record})
            save(PUBLIC / "perf-selection.json", attempts)
            if record["returncode"] == 0:
                return str(candidate), output(name).strip()
    raise Blocked("no functional installed perf executable")


def probe_kvm():
    fd = os.open("/dev/kvm", os.O_RDWR | os.O_CLOEXEC)
    try:
        version = fcntl.ioctl(fd, 0xAE00, 0)
        if version != 12:
            raise Blocked("actual KVM API is not12")
        vm_fd = fcntl.ioctl(fd, 0xAE01, 0)
        os.close(vm_fd)
        capabilities = {}
        for name, number in KVM_CAPABILITIES.items():
            try:
                capabilities[name] = fcntl.ioctl(fd, 0xAE03, number)
            except OSError as error:
                raise Blocked(f"actual KVM capability {name}({number}) query failed: {error}") from error
        return {"api_version": version, "nonroot_vm_create": True,
                "capabilities": capabilities}
    except OSError as error:
        raise Blocked(f"actual KVM admission probe failed: {error}") from error
    finally:
        os.close(fd)


def require_kvm_capabilities(record):
    capabilities = record.get("capabilities", {})
    if not isinstance(capabilities, dict):
        raise Blocked("actual KVM capability record malformed; no downgraded candidate")
    for name, number in KVM_CAPABILITIES.items():
        value = capabilities.get(name)
        if type(value) is not int or value <= 0:
            raise Blocked(f"actual KVM capability {name}({number}) unavailable: {value!r}; no downgraded candidate")


def host_probe():
    topology = actual_topology()
    record = {
        "kernel": os.uname().release, "architecture": os.uname().machine,
        "uid": os.getuid(), "gid": os.getgid(),
        "topology": topology, "topology_scope": "actual guest-exposed package/core/SMT; hidden host placement is not assumed",
        "available_bytes": shutil.disk_usage(bench.ROOT).free,
        "azure": {"verified": False}, "nesting": {"verified": False},
        "non_nested_comparison": "not available; no persistent resource requested",
    }
    save(PUBLIC / "host.json", record)
    vm, client = independent_cpus(topology)
    record.update(vm_cpu=vm, client_cpu=client)
    record["visible_logical_cores"] = len(cpulist(Path("/sys/devices/system/cpu/online").read_text()))
    record["runner_environment"] = os.environ.get("RUNNER_ENVIRONMENT", "unverified")
    check_space(4 * 1024**3)
    flags = next(line.split(":", 1)[1].split() for line in Path("/proc/cpuinfo").read_text().splitlines()
                 if line.startswith("flags"))
    record["nesting"] = {"verified": "hypervisor" in flags,
                         "hypervisor_flag": "hypervisor" in flags,
                         "virtualization_flag": next((x for x in ("vmx", "svm") if x in flags), None)}
    record["dmi"] = {
        name: (Path("/sys/class/dmi/id") / name).read_text().strip()
        for name in ("sys_vendor", "product_name")
    }
    # Read only the two nonidentifying scalar IMDS fields; no instance document,
    # IDs, tags, IPs, proxy environment or redirects are read/uploaded.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *_):
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        fields = {}
        for field in ("vmSize", "azEnvironment"):
            request = urllib.request.Request(
                f"http://169.254.169.254/metadata/instance/compute/{field}"
                "?api-version=2021-02-01&format=text", headers={"Metadata": "true"})
            with opener.open(request, timeout=2) as response:
                value = response.read(256).decode().strip()
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
                raise ValueError("unrecognized scalar IMDS response")
            fields[field] = value
        record["azure"] = {"verified": fields["azEnvironment"].startswith("Azure"), **fields}
    except (OSError, ValueError):
        record["azure"]["reason"] = "bounded scalar Azure IMDS unavailable"
    save(PUBLIC / "host.json", record)
    if (record["architecture"] != "x86_64" or not record["azure"]["verified"]
            or not record["nesting"]["verified"]):
        raise Blocked("actual Azure/nesting/x86_64 identity unsuitable or unverifiable")
    if os.geteuid() == 0:
        raise Blocked("runner/controller must be nonroot")
    record["kvm"] = probe_kvm()
    save(PUBLIC / "host.json", record)
    require_kvm_capabilities(record["kvm"])
    perf, version = perf_binary()
    record["perf_binary_sha256"] = bench.digest(Path(perf))
    record["perf_version"] = version
    for privilege, prefix in (("user", []), ("root", ["sudo", "-n"])):
        record[privilege + "_perf"] = {}
        for kind, events in (("software", "task-clock,context-switches,cpu-migrations"),
                             ("pmu", "cycles,instructions"),
                             ("trace", "kvm:kvm_exit,kvm:kvm_userspace_exit,syscalls:sys_enter_ioctl,sched:sched_switch")):
            result = owned_command([*prefix, perf, "stat", "-e", events, "--",
                                    sys.executable, "-c", "sum(range(1000000))"], f"probe-{privilege}-{kind}", 10)
            record[privilege + "_perf"][kind] = result
    record["sudo_namespace"] = owned_command(["sudo", "-n", "unshare", "--net", "--", "true"],
                                             "probe-netns", 5)
    record["cpu_accounting"] = {"primary": visible_cpu.SCOPE, "background_subtracted": False,
                                "owned_detail_added": False, "owned_attribution_gaps": KERNEL_GAPS}
    save(PUBLIC / "host.json", record)
    if record["root_perf"]["software"]["returncode"] or record["sudo_namespace"]["returncode"]:
        raise Blocked("scoped software perf or owned network namespace unavailable")
    if record["runner_environment"] != "github-hosted":
        raise Blocked("ephemeral hosted isolation provenance unverified")
    return record, perf


def native_test_failure_diagnostics(text):
    known = {
        f"{path.stem}.test.{name}"
        for path in (bench.ROOT / "vmm/src").rglob("*.zig")
        for name in re.findall(r'(?m)^\s*test "([^"\r\n]+)"', path.read_text())
    }
    headers = list(re.finditer(r"(?m)^error: '([^'\r\n]{1,256})' failed:", text))
    failures = []
    unknown = 0
    for index, header in enumerate(headers):
        identifier = header.group(1)
        if identifier not in known:
            unknown += 1
            continue
        end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        labels = set(re.findall(r"\berror\.([A-Za-z][A-Za-z0-9_]*)\b", text[header.end():end]))
        failures.append({"test": identifier, "observed_error_labels": sorted(labels & TEST_ERROR_LABELS)})
    return {
        "scope": "source-allowlisted test identifiers and observed error labels, not proven causes",
        "failure_headers": len(headers), "unknown_failure_headers": unknown,
        "failures": failures,
    }


def require_execution(name, argv, seconds, phases, cwd=bench.ROOT, environment=None, tests=None):
    check_space(4 * 1024**3)
    record = owned_command(argv, name, seconds, cwd, environment)
    record["argv"] = list(map(str, argv))
    if tests is not None:
        text = output(name) + (RAW / f"{name}.stderr").read_text(errors="replace")
        counts = [tuple(map(int, pair)) for pair in re.findall(r"(\d+)/(\d+) tests passed", text)]
        record["test_counts"] = counts
        record["skip_detected"] = bool(re.search(r"\bskip(?:ped)?\b", text, re.I))
        record["test_failure_diagnostics"] = native_test_failure_diagnostics(text)
        if (record["skip_detected"] or sum(total for _, total in counts) < tests
                or any(passed != total for passed, total in counts)):
            record["coverage_rejected"] = True
    phases.append(record)
    save(PUBLIC / "phases.json", phases)
    if record["returncode"] or record.get("coverage_rejected"):
        raise Blocked(f"{name} failed or actual coverage incomplete; see sanitized phase receipt")


def build_inputs(phases, source):
    zig = shutil.which("zig")
    if not zig or subprocess.check_output([zig, "version"], text=True).strip() != "0.17.0":
        raise Blocked("signed exact Zig0.17 compiler unavailable")
    pins = {"source": source, "compiler_sha256": bench.digest(Path(zig).resolve()),
            "target": "x86_64-linux-musl", "compiler_backend": "existing default; no override",
            "kernel_sha256": bench.digest(HOME / "bzImage"),
            "cache_policy": "one private cache; build all inputs once before any matrix",
            "backends": "synchronous block/userspace TAP/unchanged agent; no async/vhost/native override",
            "agent_interactive_poll_ms": 50, "heartbeat_ms": 0, "production_mode_default": "L0"}
    pins["source_files_sha256"] = {
        str(path.relative_to(bench.ROOT)): bench.digest(path)
        for folder in ("vmm/src", "agent/src") for path in sorted((bench.ROOT / folder).rglob("*.zig"))}
    save(PUBLIC / "pins.json", pins)
    if pins["kernel_sha256"] != bench.KERNEL_SHA256:
        raise Blocked("guest kernel differs from the CI signed/hash-checked input")
    # Integration fixtures use this parent even when Zig's local cache is redirected.
    (bench.ROOT / "vmm/.zig-cache").mkdir(mode=0o700, exist_ok=True)
    for optimize in ("Debug", "ReleaseSafe"):
        require_execution(f"zig-{optimize}", [
            zig, "build", "install", "test", "eventfd-test", "integration-test",
            "-Dtarget=x86_64-linux-musl", f"-Doptimize={optimize}",
            f"-Dintegration-kernel={HOME / 'bzImage'}", "--summary", "all", "--color", "off",
        ], 600, phases, bench.ROOT / "vmm", tests=70)
        binary = HOME / f"flint-{optimize}"
        shutil.copyfile(bench.ROOT / "vmm/zig-out/bin/flint", binary)
        binary.chmod(0o700)
        pins[optimize + "_sha256"] = bench.digest(binary)
        environment = dict(os.environ, FLINT_JAIL_TEST_BINARY=str(binary),
                           FLINT_JAIL_TEST_KERNEL=str(HOME / "bzImage"), FLINT_JAIL_TEST_REVISION=source)
        require_execution(f"jail-{optimize}", [
            sys.executable, "-m", "unittest", "discover", "-s", "tools/perf",
            "-p", "test_jail_baseline.py", "-v"], 180, phases, environment=environment)
        if "Ran 3 tests" not in (RAW / f"jail-{optimize}.stderr").read_text():
            raise Blocked("standalone full-jail coverage did not actually execute three cases")
        for root in sorted((bench.ROOT / ".perf/jail-baseline").glob("*")):
            launch = root / "launch.json"
            if launch.is_file():
                ownership = json.loads(launch.read_text())
                if (ownership.get("source_revision") == source
                        and ownership.get("binary_sha256") == pins[optimize + "_sha256"]):
                    removed = remove_owned_images(root, ("disk.raw", "bzImage", "initrd.cpio.gz"))
                    save(PUBLIC / f"jail-image-cleanup-{optimize}-{root.name}.json", removed)
    require_execution("agent", [zig, "build", "-Dtarget=x86_64-linux-musl", "-Doptimize=safe"],
                      300, phases, bench.ROOT / "agent")
    require_execution("native-probes", [
        zig, "build", "eventfd-guest-probe", "eventfd-tcp-probe",
        "-Dtarget=x86_64-linux-musl", "-Doptimize=ReleaseSafe"], 300, phases, bench.ROOT / "vmm")
    require_execution("disk-probe", [
        zig, "cc", "-target", "x86_64-linux-musl", "-O2",
        bench.ROOT / "benchmarks/virtio-eventfd/disk_probe.c", "-o", HOME / "disk-probe"], 120, phases)
    observer_build = owned_command([
        "/usr/bin/clang", "-target", "bpf", "-O2", "-g", "-c",
        bench.ROOT / "tools/perf/irqfd_cpu.bpf.c", "-o", HOME / "irqfd_cpu.bpf.o"], "irqfd-observer-build", 60)
    phases.append(observer_build)
    save(PUBLIC / "phases.json", phases)
    matrix.prepare(SimpleNamespace(out=HOME / "fixture", kernel=HOME / "bzImage",
                   agent=bench.ROOT / "agent/zig-out/bin/hearth-agent",
                   native=bench.ROOT / "vmm/zig-out/bin/eventfd-guest-probe",
                   tcp=bench.ROOT / "vmm/zig-out/bin/eventfd-tcp-probe",
                   disk_probe=HOME / "disk-probe", profile_only=False, vsock_only=False))
    bench.prepare(SimpleNamespace(out=HOME / "native-fixture", kernel=HOME / "bzImage",
                  agent=bench.ROOT / "agent/zig-out/bin/hearth-agent", probe=bench.ROOT / "vmm/zig-out/bin/eventfd-guest-probe",
                  busybox="/usr/bin/busybox", heartbeat_ms=0))
    for fixture in ("fixture", "native-fixture"):
        metadata_path = HOME / fixture / "fixture.json"
        metadata = json.loads(metadata_path.read_text())
        metadata["boot_args"] = "console=ttyS0 nokaslr reboot=t panic=1 pci=off nomodules"
        save(metadata_path, metadata)
    pins["fixture"] = json.loads((HOME / "fixture/fixture.json").read_text())
    pins["native_fixture"] = json.loads((HOME / "native-fixture/fixture.json").read_text())
    pins["observer_object_sha256"] = bench.digest(HOME / "irqfd_cpu.bpf.o") if observer_build["returncode"] == 0 else None
    pins["bpf_compiler_sha256"] = bench.digest(Path("/usr/bin/clang").resolve())
    pins["runner_files_sha256"] = {name: bench.digest(Path(module.__file__))
                                  for name, module in (("hosted", sys.modules[__name__]), ("control", control),
                                                       ("matrix", matrix), ("performance", performance), ("run", bench))}
    pins["runner_files_sha256"]["visible_cpu"] = bench.digest(Path(visible_cpu.__file__))
    pins["runner_files_sha256"]["restore_stress"] = bench.digest(Path(restore_stress.__file__))
    pins["runner_files_sha256"]["custody"] = bench.digest(Path(custody.__file__))
    save(PUBLIC / "pins.json", pins)
    return pins


def row_projection(row):
    names = ("name", "status", "latency_ms", "latency", "operations", "bytes", "operation_seconds",
             "owned_all_task_cpu_seconds", "owned_irqfd_function_cpu_seconds",
             "known_scoped_cpu_seconds", "known_scoped_cpu_per_operation", "bytes_per_second",
             "visible_host_cpu", "visible_host_cpu_per_operation", "completed_workload_end_ns",
             "threads_before", "threads_after", "kernel_work_before", "kernel_work_after",
             "client_cpu_seconds", "host_noise", "idle_wake_ms", "batches")
    result = {key: row[key] for key in names if key in row}
    for name in ("threads_before", "threads_after"):
        if name in result:
            result[name] = [{key: task[key] for key in ("tid", "comm", "utime_ticks", "stime_ticks",
                                                       "start_ticks", "cpu_runtime_ns", "affinity") if key in task}
                            for task in result[name]]
    for name in ("kernel_work_before", "kernel_work_after"):
        if name in result:
            result[name] = kernel_projection(result[name])
    return result


def kernel_projection(record):
    result = {name: record[name] for name in ("status", "kernel_irqfd_cpu_seconds",
                                             "incomplete_work_at_boundary") if name in record}
    result["kernel_work"] = {
        name: {key: record["kernel_work"][name][key] for key in ("cpu_ns", "jobs")}
        for name in ("anomalies", "inject", "shutdown") if name in record.get("kernel_work", {})}
    return result


def observer_detail(observer, result, phase, finish=False):
    if observer is None:
        return None
    try:
        return kernel_projection(observer.finish() if finish else observer.read())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        observer.abort()
        result["irqfd_function_detail_status"] = "incomplete; never substituted with zero"
        result.setdefault("irqfd_detail_failures", []).append({
            "phase": phase, "type": type(error).__name__,
            "message_sha256": hashlib.sha256(str(error).encode()).hexdigest()})
        return None


def validate_pins():
    pins = json.loads((PUBLIC / "pins.json").read_text())
    if (bench.digest(HOME / "flint-ReleaseSafe") != pins["ReleaseSafe_sha256"]
            or bench.digest(HOME / "bzImage") != pins["kernel_sha256"]
            or json.loads((HOME / "fixture/fixture.json").read_text()) != pins["fixture"]
            or json.loads((HOME / "native-fixture/fixture.json").read_text()) != pins["native_fixture"]
            or (pins["observer_object_sha256"] is not None
                and bench.digest(HOME / "irqfd_cpu.bpf.o") != pins["observer_object_sha256"])):
        raise Blocked("frozen binary/kernel/fixture/accounting inputs changed")


def sample(guest, tcp, name, visible_cores):
    before = bench.thread_roster(guest.pid)
    client_before = time.process_time()
    host_before = visible_cpu.capture()
    started_ns = time.monotonic_ns()
    started = started_ns / 1e9
    latency, byte_count, _ = performance.workload(guest, tcp, name)
    batches = 1
    if name != "idle":
        while time.monotonic() - started < 5:
            more, size, _ = performance.workload(guest, tcp, name)
            latency.extend(more)
            byte_count += size
            batches += 1
    completed_ns = time.monotonic_ns()
    operation_seconds = (completed_ns - started_ns) / 1e9
    time.sleep(.1)
    accounting_end_ns = time.monotonic_ns()
    host_cpu = visible_cpu.delta(host_before, visible_cpu.capture(),
                                 started_ns, accounting_end_ns, visible_cores)
    host_cpu["fixed_completion_tail_seconds"] = .1
    host_cpu["completed_workload_end_ns"] = completed_ns
    host_cpu["new_operations_in_tail"] = 0
    after = bench.thread_roster(guest.pid)
    cpu = bench.cpu_delta(before, after)
    if cpu < 0 or not latency:
        raise ValueError("invalid CPU/count boundary")
    result = {
        "name": name, "status": "passed", "latency_ms": latency, "latency": performance.summary(latency),
        "operations": len(latency), "bytes": byte_count, "operation_seconds": operation_seconds,
        "owned_all_task_cpu_seconds": cpu, "owned_irqfd_function_cpu_seconds": None,
        "known_scoped_cpu_seconds": None, "known_scoped_cpu_per_operation": None,
        "visible_host_cpu": host_cpu,
        "visible_host_cpu_per_operation": host_cpu["busy_cpu_seconds"] / len(latency),
        "completed_workload_end_ns": completed_ns,
        "bytes_per_second": byte_count / operation_seconds,
        "threads_before": before, "threads_after": after,
        "client_cpu_seconds": time.process_time() - client_before,
        "batches": batches,
    }
    if name == "idle":
        result["idle_wake_ms"] = {}
        for kind, connection in (("vsock", guest.native_connection), ("tap", tcp)):
            began = time.monotonic()
            bench.native_echo(connection, 700, 64)
            result["idle_wake_ms"][kind] = 1000 * (time.monotonic() - began)
            if result["idle_wake_ms"][kind] > 1000:
                raise RuntimeError("timer-free idle wake exceeded one second")
    return row_projection(result)


class PerfCapture:
    def __init__(self, path, command, errors):
        self.path = path
        self.fds = []
        self.created = []
        self.process = None
        self.deadline = time.monotonic() + 30
        self.ready = path / "recording-ready"
        self.paths = [path / name for name in ("perf-control", "perf-ack", "perf-release")]
        try:
            for fifo in self.paths:
                os.mkfifo(fifo, 0o600)
                self.created.append(fifo)
                self.fds.append(os.open(fifo, os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC))
            self.process = subprocess.Popen([
                "sudo", "-n", "env", f"PERF_BUILDID_DIR={HOME / 'perf-buildids'}",
                "timeout", "--kill-after=5s", "30", *map(str, command),
                "--delay=-1", f"--control=fifo:{self.paths[0]},{self.paths[1]}",
                "--", sys.executable, "-c",
                "from pathlib import Path; import sys; "
                "Path(sys.argv[1]).touch(); "
                "f=open(sys.argv[2],'rb',buffering=0); "
                "sys.exit(0 if f.read(1)==b'S' else 1)",
                str(self.ready), str(self.paths[2]),
            ], stderr=errors)
            limit = min(self.deadline, time.monotonic() + 5)
            while not self.ready.exists():
                self.check_alive()
                if time.monotonic() >= limit:
                    raise Blocked("scoped collector did not reach disabled readiness")
                time.sleep(.01)
        except BaseException:
            self.close()
            raise

    def check_alive(self):
        if self.process.poll() is not None:
            raise Blocked("scoped collector terminated before the completed-operation disable fence")
        if time.monotonic() >= self.deadline:
            raise Blocked("finite scoped collection budget exhausted")

    def command(self, name):
        self.check_alive()
        if select.select([self.fds[1]], [], [], 0)[0]:
            if os.read(self.fds[1], 4096):
                raise Blocked("unsolicited scoped collector acknowledgement")
        sent_ns = time.monotonic_ns()
        os.write(self.fds[0], (name + "\n").encode())
        limit = min(self.deadline, time.monotonic() + 5)
        response = b""
        while b"\n" not in response:
            self.check_alive()
            remaining = limit - time.monotonic()
            if remaining <= 0:
                raise Blocked(f"scoped collector {name} acknowledgement unavailable")
            if select.select([self.fds[1]], [], [], min(.05, remaining))[0]:
                response += os.read(self.fds[1], 4096)
                if len(response) > 4:
                    raise Blocked("malformed scoped collector acknowledgement")
        if response != b"ack\n":
            raise Blocked("malformed scoped collector acknowledgement")
        self.check_alive()
        return {"sent_ns": sent_ns, "ack_ns": time.monotonic_ns()}

    def release(self):
        self.check_alive()
        os.write(self.fds[2], b"S")
        if self.process.wait(timeout=max(.001, self.deadline - time.monotonic())) != 0:
            raise Blocked("actual scoped profile collection unavailable")

    def close(self):
        try:
            if self.process is not None and self.process.poll() is None:
                # Popen retains the unreaped wrapper identity; namespace custody
                # additionally pins and joins its perf/sentinel descendants.
                subprocess.run(["sudo", "-n", "kill", "-TERM", str(self.process.pid)],
                               check=False, timeout=5)
                self.process.wait(timeout=10)
        finally:
            for fd in self.fds:
                os.close(fd)
            self.fds = []
            for path in self.created:
                path.unlink(missing_ok=True)
            self.created = []


def profile_batches(guest, capture):
    enabled = capture.command("enable")
    batches = []
    began = time.monotonic()
    while time.monotonic() - began < 12:
        capture.check_alive()
        # Reserve disable/ack/release time within the unchanged30-second budget.
        timeout = min(20, math.floor(capture.deadline - time.monotonic() - 5))
        if timeout <= 0:
            raise Blocked("no complete-batch reserve within the finite collection budget")
        started_ns = time.monotonic_ns()
        data = json.loads(matrix.rpc_exec(guest, "/disk-probe flush 4096 128", timeout))
        completed_ns = time.monotonic_ns()
        capture.check_alive()
        if type(data.get("operations")) is not int or data["operations"] != 128:
            raise ValueError("profile operation integrity/count changed")
        batches.append({"started_ns": started_ns, "completed_ns": completed_ns, "operations": 128})
    disabled = capture.command("disable")
    if not batches or any(not enabled["ack_ns"] <= row["started_ns"] <= row["completed_ns"]
                          <= disabled["sent_ns"] for row in batches):
        raise Blocked("counted operations are not bracketed by acknowledged perf fences")
    capture.release()
    return {"operations": sum(row["operations"] for row in batches),
            "capture_boundaries": {"enable": enabled, "disable": disabled, "batches": batches,
                                   "collector_budget_seconds": 30,
                                   "completed_operation_seconds": (batches[-1]["completed_ns"]
                                                                  - batches[0]["started_ns"]) / 1e9}}


def profile(guest, observer, args, result):
    perf = args.perf
    roster = bench.thread_roster(guest.pid)
    tids = ",".join(str(row["tid"]) for row in roster)
    path = bench.artifact_path(args.out)
    events = ["kvm:kvm_entry", "kvm:kvm_exit", "kvm:kvm_userspace_exit", "kvm:kvm_mmio",
              "kvm:kvm_set_irq", "syscalls:sys_enter_ioctl", "syscalls:sys_exit_ioctl",
              "syscalls:sys_enter_read", "syscalls:sys_exit_read", "syscalls:sys_enter_write",
              "syscalls:sys_exit_write", "syscalls:sys_enter_epoll_pwait", "sched:sched_switch"]
    if args.profile == "stat":
        command = [perf, "stat", "-t", tids, "-e", "task-clock,context-switches,cpu-migrations,page-faults",
                   "-o", path / "stat.txt"]
    else:
        command = [perf, "record", "-t", tids, "-m", "2048", "-o", path / "profile.data"]
        command += (["-e", "cpu-clock", "-F", "99", "-g", "--call-graph", "dwarf,8192"]
                    if args.profile == "stacks" else [item for event in events for item in ("-e", event)])
    errors = (path / "perf.stderr").open("wb")
    capture = None
    try:
        capture = PerfCapture(path, command, errors)
        before = observer_detail(observer, result, "before")
        result.update(profile_batches(guest, capture))
    finally:
        try:
            if capture is not None:
                capture.close()
        finally:
            errors.close()
    after = bench.thread_roster(guest.pid)
    result["profiled_owned_all_task_cpu_seconds"] = bench.cpu_delta(roster, after)
    result["threads_before"] = roster
    result["threads_after"] = after
    result["kernel_work_before"] = before
    result["kernel_work_after"] = observer_detail(observer, result, "after")
    text = (path / "perf.stderr").read_text()
    if re.search(r"(lost|dropped)\s+[1-9][0-9]*|[1-9][0-9]*\s+(lost|dropped)", text, re.I):
        raise Blocked("profile loss detected; never qualifying attribution")
    if args.profile == "stat":
        result["owned_perf_stat"] = subprocess.check_output(
            ["sudo", "-n", "cat", str(path / "stat.txt")], text=True, timeout=5)
    else:
        decode = subprocess.run(["sudo", "-n", "env", f"PERF_BUILDID_DIR={HOME / 'perf-buildids'}",
                                 perf, "report" if args.profile == "stacks" else "script",
                                 "-f", *(["--stdio"] if args.profile == "stacks" else []),
                                 "-i", str(path / "profile.data")], capture_output=True, timeout=45)
        (path / "decoded.txt").write_bytes(decode.stdout)
        (path / "decode.stderr").write_bytes(decode.stderr)
        if decode.returncode:
            raise Blocked("owned profile decoding failed")
        if re.search(rb"PERF_RECORD_LOST|\bLOST\s+[1-9]|(?:lost|dropped)\s+[1-9][0-9]*|[1-9][0-9]*\s+(?:lost|dropped)",
                     decode.stdout + decode.stderr, re.I):
            raise Blocked("decoded profile loss detected; never qualifying attribution")
        if args.profile == "stacks":
            report = decode.stdout.decode(errors="replace")
            if not re.search(r"\bflint\b", report) or not re.search(r"Samples:\s*[1-9]", report):
                raise Blocked("no identifiable owned Flint stack samples")
            # Perf report contains symbols/counts, not its DWARF stack bytes.
            result["owned_stack_report"] = report
        else:
            devices = [{"kind": kind, "mmio_base": int(address, 16), "gsi": int(gsi)}
                       for kind, address, gsi in re.findall(
                           r"virtio-(blk|net|vsock) at MMIO 0x([\da-f]+) IRQ (\d+)",
                           (path / "vmm.stderr").read_text())]
            if not devices:
                raise Blocked("actual device attribution unavailable")
            result["attribution"] = analyze_trace.analyze(decode.stdout.decode().splitlines(), devices)
            if not result["attribution"]["events"].get("kvm:kvm_exit", 0):
                raise Blocked("no observable kernel exits in the scoped trace")
            if args.mode == "C00" and (
                    not sum(result["attribution"]["attributed_notify_userspace_returns"].values())
                    or not sum(value for key, value in result["attribution"]["completed_irq_line_ioctl_calls"].items()
                               if key != "non-virtio-or-unattributed")):
                raise Blocked("functioning C00 trace lacks eligible notification/IRQ attribution")


def cell(args):
    if os.geteuid() == 0:
        raise Blocked("backend/controller execution must be nonroot")
    out = bench.artifact_path(args.out)
    host = json.loads((PUBLIC / "host.json").read_text())
    validate_pins()
    os.sched_setaffinity(0, {host["client_cpu"]})
    if args.scale_count:
        return native_scale(args, host)
    if args.lifecycle:
        result = restore_stress.cycle(
            SimpleNamespace(binary=HOME / "flint-ReleaseSafe", fixture=HOME / "fixture",
                            mode=args.mode, vm_cpu=host["vm_cpu"]), out / "cycle")
        error_hashes = [hashlib.sha256(error.encode()).hexdigest() for error in result.get("errors", [])]
        result = {key: result[key] for key in ("status", "mode", "snapshot", "snapshot_sha256",
                                             "paused_all_task_cpu_seconds", "source_exit", "restore_exit",
                                             "restored_disk_bytes_verified", "bulky_images_removed_after_verified_restore",
                                             "outstanding_sources_at_capture", "disk_producer_at_capture",
                                             "restored_disk_producer") if key in result}
        result["classification"] = "one actual active mixed fresh v2 restore, not20/old-new/full lifecycle"
        result["failure_message_sha256"] = error_hashes
        result["owned_image_cleanup"] = remove_owned_images(out / "cycle", ("state", "memory", "disk"))
        result["performance_merge_eligible"] = False
        save(out / "result.json", result)
        return 0 if result["status"] == "passed" else 1
    result = {"status": "failed", "mode": args.mode, "rows": [],
              "classification": "profiled" if args.profile else "unprofiled matched matrix",
              "visible_host_cpu_method": visible_cpu.SCOPE, "owned_attribution_gaps": KERNEL_GAPS,
              "performance_merge_eligible": False}
    guest, tcp, observer = None, None, None
    try:
        result["background_controls"] = [visible_cpu.quiet(5.1, host["visible_logical_cores"])]
        guest = control.Guest.__new__(control.Guest)
        guest.__init__(out, HOME / "flint-ReleaseSafe", args.mode, HOME / "fixture",
                       disk=True, tap="hef3tap0", vm_cpu=host["vm_cpu"])
        tcp = socket.create_connection(("192.0.2.2", 11000), timeout=8)
        tcp.settimeout(10)
        if args.profile and json.loads((PUBLIC / "pins.json").read_text())["observer_object_sha256"]:
            try:
                observer = matrix.Observer(guest, HOME / "irqfd_cpu.bpf.o")
                result["irqfd_function_detail_status"] = "available"
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
                result["irqfd_function_detail_status"] = "unavailable; never substituted with zero"
        else:
            result["irqfd_function_detail_status"] = "not collected in unprofiled primary windows"
        control.agent(guest, True)
        for connection in (tcp, guest.native_connection):
            bench.native_echo(connection, 600, 64)
        time.sleep(1)
        if args.profile:
            profile(guest, observer, args, result)
        else:
            for name in performance.WORKLOADS:
                result["rows"].append(sample(guest, tcp, name, host["visible_logical_cores"]))
                save(out / "result.json", result)
        checksum = matrix.rpc_exec(guest, "/bin/busybox sha256sum /dev/vda", 20).decode().split()[0]
        if checksum != bench.digest(guest.path / "disk"):
            raise ValueError("whole real disk guest/host integrity failure")
        result["shutdown_exit_code"] = guest.shutdown()
        if observer is not None:
            result["kernel_work_final"] = observer_detail(observer, result, "final", finish=True)
            observer = None
        result["status"] = "passed"
    except (OSError, ValueError, RuntimeError, EOFError, subprocess.SubprocessError) as error:
        result["failure_type"] = type(error).__name__
        if isinstance(error, Blocked):
            result["reason"] = str(error)
        if isinstance(error, OSError):
            result["errno"] = error.errno
        result["failure_message_sha256"] = hashlib.sha256(str(error).encode()).hexdigest()
    finally:
        if observer is not None:
            try:
                observer.finish()
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
                observer.abort()
                result["observer_cleanup_failed"] = True
        if tcp is not None:
            tcp.close()
        if guest is not None:
            try:
                guest.close()
                result["cleanup"] = json.loads((out / "teardown.json").read_text())
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
                result["cleanup_failed"] = True
                result["status"] = "failed"
        if not result.get("cleanup_failed"):
            result.setdefault("background_controls", []).append(
                visible_cpu.quiet(5.1, host["visible_logical_cores"]))
        save(out / "result.json", result)
    return 0 if result["status"] == "passed" else 1


def native_scale(args, host):
    count = args.scale_count
    available = int(next(line.split()[1] for line in Path("/proc/meminfo").read_text().splitlines()
                         if line.startswith("MemAvailable:"))) * 1024
    out = bench.artifact_path(args.out)
    result = {"status": "failed", "mode": args.mode, "count": count,
              "classification": "pure-native1/4/8 idle/concurrency; not mixed-device scaling performance",
              "cpu_scope": visible_cpu.SCOPE, "owned_attribution_gaps": KERNEL_GAPS,
              "performance_merge_eligible": False, "guest_agent_present": False, "heartbeat_ms": 0}
    result["available_memory_bytes"] = available
    result["required_memory_bytes"] = (count * 512 + 1024) * 1024**2
    if available < result["required_memory_bytes"]:
        result.update(status="blocked", reason="actual available memory insufficient for complete native scaling cell")
        save(out / "result.json", result)
        return 1
    guests, workers = [], []
    try:
        result["background_controls"] = [visible_cpu.quiet(60, host["visible_logical_cores"])]
        for index in range(count):
            directory = out / f"g{index}"
            directory.mkdir(mode=0o700)
            guest = control.Guest.__new__(control.Guest)
            guests.append(guest)
            guest.__init__(directory, HOME / "flint-ReleaseSafe", args.mode, HOME / "native-fixture",
                           vm_cpu=host["vm_cpu"])
            bench.native_echo(guest.connection, 0, 4096)
        time.sleep(.2)
        before = [bench.thread_roster(guest.pid) for guest in guests]
        for guest, roster in zip(guests, before):
            channels = [subprocess.check_output(
                ["sudo", "-n", "cat", f"/proc/{guest.pid}/task/{task['tid']}/wchan"],
                text=True, timeout=5).strip() for task in roster]
            if "kvm_vcpu_block" not in channels:
                raise Blocked("pure-native guest is not verified in actual KVM HLT")
        host_before = visible_cpu.capture()
        started_ns = time.monotonic_ns()
        started = started_ns / 1e9
        time.sleep(60)
        ended_ns = time.monotonic_ns()
        seconds = (ended_ns - started_ns) / 1e9
        host_cpu = visible_cpu.delta(host_before, visible_cpu.capture(),
                                     started_ns, ended_ns, host["visible_logical_cores"])
        after = [bench.thread_roster(guest.pid) for guest in guests]
        cpu = sum(bench.cpu_delta(a, b) for a, b in zip(before, after))
        result["idle"] = {
            "seconds": seconds, "owned_all_task_cpu_seconds": cpu, "owned_irqfd_function_cpu_seconds": None,
            "visible_host_cpu": host_cpu,
            "visible_busy_core_percentage_points_per_sandbox": 100 * host_cpu["busy_cpu_seconds"] / seconds / count,
            "threads_before": before, "threads_after": after,
            "qualification": "single measured point; background/precision may still hide0.1pp gate",
        }
        result["wake_ms"] = []
        for guest in guests:
            started = time.monotonic()
            bench.native_echo(guest.connection, 1, 64)
            result["wake_ms"].append(1000 * (time.monotonic() - started))
            if result["wake_ms"][-1] > 1000:
                raise Blocked("true-idle wake exceeds one second")
        latencies, errors = {}, []
        def traffic(index, guest):
            values = []
            try:
                for number in range(64):
                    started = time.monotonic()
                    bench.native_echo(guest.connection, number, 65536)
                    values.append(1000 * (time.monotonic() - started))
                latencies[index] = values
            except (OSError, ValueError, RuntimeError, EOFError):
                errors.append(index)
        for index, guest in enumerate(guests):
            worker = threading.Thread(target=traffic, args=(index, guest))
            workers.append(worker)
            worker.start()
        for worker in workers:
            worker.join(timeout=30)
        if errors or any(worker.is_alive() for worker in workers):
            raise Blocked("actual native scaling traffic did not complete with integrity")
        result["concurrent_latency_ms"] = latencies
        result["shutdown_exit_codes"] = [guest.shutdown() for guest in guests]
        result["status"] = "passed"
    except (OSError, ValueError, RuntimeError, EOFError, subprocess.SubprocessError) as error:
        result["failure_type"] = type(error).__name__
        if isinstance(error, Blocked):
            result["reason"] = str(error)
    finally:
        for guest in guests:
            if guest.connection is not None and any(worker.is_alive() for worker in workers):
                try:
                    guest.connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            try:
                guest.close()
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
                result["cleanup_failed"] = True
                result["status"] = "failed"
        for worker in workers:
            worker.join(timeout=5)
        if not result.get("cleanup_failed"):
            result.setdefault("background_controls", []).append(
                visible_cpu.quiet(60, host["visible_logical_cores"]))
        save(out / "result.json", result)
    return 0 if result["status"] == "passed" else 1


def namespace(args):
    deadline = time.monotonic() + 360
    tap_probe.require_private_namespace()
    uid, gid = int(os.environ["SUDO_UID"]), int(os.environ["SUDO_GID"])
    if uid <= 0 or gid <= 0:
        raise Blocked("namespace bootstrap must originate from nonroot")
    out = bench.artifact_path(args.out)
    out.mkdir(mode=0o700)
    os.chown(out, uid, gid)
    tap_probe.setup_tap(uid)
    def demote():
        os.setgroups([])
        os.setgid(gid)
        os.setuid(uid)
    argv = [sys.executable, str(Path(__file__)), "cell", "--out", str(out), "--mode", args.mode]
    if args.profile:
        argv += ["--profile", args.profile, "--perf", args.perf]
    if args.scale_count:
        argv += ["--scale-count", str(args.scale_count)]
    if args.lifecycle:
        argv += ["--lifecycle"]
    supervisor = custody.Supervisor()
    try:
        work_budget = min(330, deadline - time.monotonic() - 30)
        if work_budget <= 0:
            raise Blocked("namespace bootstrap exhausted the reserved descendant cleanup budget")
        code, record = supervisor.run(argv, work_seconds=work_budget, cleanup_seconds=30,
                                      cwd=bench.ROOT, preexec_fn=demote)
        path = out / "custody.json"
        save(path, record)
        os.chown(path, uid, gid)
        return code
    finally:
        supervisor.close()


def run_cell(name, mode, phases, deadline, profile_kind=None, perf=None, scale_count=None, lifecycle=False):
    if time.monotonic() + 395 > deadline:
        raise Blocked("bounded hosted time reserve exhausted before a complete cell")
    check_space(3 * 1024**3)
    out = RAW / name
    argv = ["sudo", "-n", "unshare", "--net", "--", sys.executable, str(Path(__file__)),
            "namespace", "--out", str(out), "--mode", mode]
    if profile_kind:
        argv += ["--profile", profile_kind, "--perf", perf]
    if scale_count:
        argv += ["--scale-count", str(scale_count)]
    if lifecycle:
        argv += ["--lifecycle"]
    record = owned_command(argv, name, 360)
    phases.append(record)
    save(PUBLIC / "phases.json", phases)
    result = json.loads((out / "result.json").read_text()) if (out / "result.json").exists() else {
        "status": "blocked", "mode": mode, "reason": "cell did not produce an actual receipt",
        "performance_merge_eligible": False}
    supervision = json.loads((out / "custody.json").read_text()) if (out / "custody.json").exists() else {}
    result["supervision"] = {key: supervision[key] for key in (
        "status", "termination_reason", "controller_returncode", "work_budget_seconds",
        "cleanup_budget_seconds", "cleanup_seconds", "subreaper", "surviving_generations",
        "alive_before_controller_kill", "cleanup_errors", "unsafe_registrations") if key in supervision}
    save(PUBLIC / f"{name}.json", result)
    if (record["returncode"] or result["status"] != "passed"
            or supervision.get("status") != "passed"
            or supervision.get("termination_reason") != "completed"
            or supervision.get("controller_returncode") != 0):
        raise Blocked(f"{name} failed; no zero CPU or skipped-as-pass replacement")
    return result


def freeze(samples, pins):
    if len(samples) != 5 or any(sample["status"] != "passed" or sample["mode"] != "C00"
                                or len(sample["rows"]) != len(performance.WORKLOADS)
                                or {row["name"] for row in sample["rows"]} != set(performance.WORKLOADS)
                                for sample in samples):
        raise Blocked("five complete passing C00 matrices required before candidates")
    noise = {}
    for name in performance.WORKLOADS:
        rows = [next(row for row in sample["rows"] if row["name"] == name) for sample in samples]
        if any(row["status"] != "passed"
               or not isinstance(row["visible_host_cpu_per_operation"], (int, float))
               or not math.isfinite(row["visible_host_cpu_per_operation"])
               or row["visible_host_cpu_per_operation"] < 0
               or (name != "idle" and row["visible_host_cpu_per_operation"] == 0)
               or not math.isfinite(row["latency"]["p95"]) or row["latency"]["p95"] <= 0
               or not math.isfinite(row["bytes_per_second"]) or row["bytes_per_second"] < 0
               or (row["bytes"] and row["bytes_per_second"] == 0)
               or (name != "idle" and row["operation_seconds"] < 5) for row in rows):
            raise Blocked("CPU unavailable/zero or sustained baseline incomplete")
        noise[name] = {
            "visible_host_cpu_per_operation": performance.summary([row["visible_host_cpu_per_operation"] for row in rows]),
            "p95_ms": performance.summary([row["latency"]["p95"] for row in rows]),
            "throughput": performance.summary([row["bytes_per_second"] for row in rows]) if rows[0]["bytes"] else None,
        }
    exceeds = [name for name, data in noise.items() if name != "idle" and
               (data["visible_host_cpu_per_operation"]["cv"] > .1 or data["p95_ms"]["cv"] > .1
                or (data["throughput"] and data["throughput"]["cv"] > .05))]
    return {"status": "noise-inconclusive" if exceeds else "noise-provisionally-acceptable",
            "candidate_performance_observed": False, "pins_sha256": hashlib.sha256(json.dumps(pins, sort_keys=True).encode()).hexdigest(),
            "gates": GATES, "noise": noise, "exceeds_noise_caps": exceeds,
            "cpu_scope": visible_cpu.SCOPE, "background_subtracted": False, "owned_detail_added": False,
            "background_bound": visible_cpu.background_upper(
                [control for sample in samples for control in sample["background_controls"]]),
            "owned_attribution_gaps": KERNEL_GAPS}


def paired_interval(control_values, candidates):
    if len(control_values) != 5 or len(candidates) != 5 or any(
            not math.isfinite(value) or value <= 0 for value in control_values + candidates):
        raise Blocked("five complete positive finite pairs required; missing CPU is not zero")
    logs = [math.log(candidate / baseline) for baseline, candidate in zip(control_values, candidates)]
    center = statistics.mean(logs)
    width = 2.776445105 * statistics.stdev(logs) / math.sqrt(5)
    return {"paired_n": 5, "confidence": .95, "model": "paired log-ratio Student-t(df4), preregistered",
            "mean_ratio": math.exp(center), "lower_ratio": math.exp(center - width),
            "upper_ratio": math.exp(center + width)}


def compare(blocks):
    result = {"status": "blocked-incomplete-qualification", "performance_merge_eligible": False,
              "cpu_scope": visible_cpu.SCOPE, "background_subtracted": False, "owned_detail_added": False,
              "owned_attribution_gaps": KERNEL_GAPS,
              "unexecuted_required_coverage": REQUIRED_GAPS, "contrasts": {}}
    background = visible_cpu.background_upper(
        [control for block in blocks for sample in block.values()
         for control in sample["background_controls"]])
    result["background_bound"] = background
    result["diagnostic_gate_checks"] = {}
    for candidate, baseline in (("C10", "C00"), ("C01", "C00"), ("C11", "C00"),
                                ("C11", "C01"), ("C11", "C10")):
        contrast = {}
        for name in performance.WORKLOADS:
            if name == "idle":
                differences = []
                for block in blocks:
                    pair = [next(row for row in block[mode]["rows"] if row["name"] == name)
                            for mode in (baseline, candidate)]
                    differences.append(100 * (pair[1]["visible_host_cpu"]["busy_core_equivalents"]
                                              - pair[0]["visible_host_cpu"]["busy_core_equivalents"]))
                contrast[name] = {"visible_busy_extra_core_pp": differences,
                                  "single60s_agent_idle_is_not_pure_HLT_scaling": True}
                continue
            values = {}
            for metric in ("visible_host_cpu_per_operation", "p95_ms", "bytes_per_second"):
                arrays = [[next(row for row in block[mode]["rows"] if row["name"] == name) for block in blocks]
                          for mode in (baseline, candidate)]
                extract = lambda row: row["latency"]["p95"] if metric == "p95_ms" else row[metric]
                if metric == "bytes_per_second" and not arrays[0][0]["bytes"]:
                    continue
                values[metric] = paired_interval(*[[extract(row) for row in rows] for rows in arrays])
                if metric == "visible_host_cpu_per_operation":
                    budgets = [visible_cpu.residual_fraction(old, new, background)
                               for old, new in zip(*arrays)]
                    bounds = [visible_cpu.sensitivity_bounds(
                        old, new, background, values[metric]["lower_ratio"], values[metric]["upper_ratio"])
                        for old, new in zip(*arrays)]
                    values[metric]["residual_bound_fraction"] = max(budgets)
                    values[metric]["control_denominator_may_be_all_residual"] = any(
                        bound["control_denominator_may_be_all_residual"] for bound in bounds)
                    values[metric]["conservative_upper_ratio"] = (
                        None if values[metric]["control_denominator_may_be_all_residual"]
                        else max(bound["conservative_upper_ratio"] for bound in bounds))
                    values[metric]["conservative_lower_ratio"] = min(
                        bound["conservative_lower_ratio"] for bound in bounds)
                    values[metric]["background_subtracted"] = False
            contrast[name] = values
        result["contrasts"][f"{candidate}/{baseline}"] = contrast
        if baseline == "C00":
            regressions = []
            uncertainty = []
            for name, metrics in contrast.items():
                if name == "idle":
                    uncertainty.append({"name": name, "metric": "single-agent idle requires repeated pure-HLT/background bound"})
                    continue
                for metric, interval in metrics.items():
                    if ((metric == "bytes_per_second" and interval["upper_ratio"] < .97)
                            or (metric == "visible_host_cpu_per_operation" and interval["conservative_lower_ratio"] > 1.05)
                            or (metric == "p95_ms" and interval["lower_ratio"] > 1.05)):
                        regressions.append({"name": name, "metric": metric, "paired95": interval})
                    if ((metric == "visible_host_cpu_per_operation" and (
                            interval["conservative_upper_ratio"] is None or interval["conservative_upper_ratio"] > 1.05))
                            or (metric == "p95_ms" and interval["upper_ratio"] > 1.05)
                            or (metric == "bytes_per_second" and interval["lower_ratio"] < .97)):
                        uncertainty.append({"name": name, "metric": metric})
            primary = contrast["disk-flush-4096"]["visible_host_cpu_per_operation"]["conservative_upper_ratio"]
            result["diagnostic_gate_checks"][candidate] = {
                "visible_primary_benefit_95_lower_at_least_10_percent":
                    primary is not None and primary <= .9,
                "demonstrated_regressions": regressions,
                "residual_could_hide_required_benefit":
                    primary is None or primary > .9,
                "regression_bounds_inconclusive": uncertainty,
                "visible_CPU_scope": visible_cpu.SCOPE,
                "qualified": False}
    result["all_candidates_have_demonstrated_regression"] = all(
        result["diagnostic_gate_checks"][mode]["demonstrated_regressions"] for mode in MODES[1:])
    return result


def mechanism(profiles):
    baseline = profiles["C00"]
    def rates(profile):
        if profile["status"] != "passed" or profile["operations"] <= 0:
            raise Blocked("complete actual primary trace operations required")
        attribution = profile["attribution"]
        return {
            "notify_userspace_returns_per_operation": sum(
                attribution["attributed_notify_userspace_returns"].values()) / profile["operations"],
            "eligible_irq_line_ioctls_per_operation": sum(
                value for name, value in attribution["completed_irq_line_ioctl_calls"].items()
                if name != "non-virtio-or-unattributed") / profile["operations"]}
    control_rates = rates(baseline)
    if any(value <= 0 for value in control_rates.values()):
        raise Blocked("baseline eligible mechanism denominator unavailable, not infinite improvement")
    result = {"classification": "profiled mechanism ratios; not unprofiled CPU/latency gain",
              "C00": control_rates, "performance_merge_eligible": False}
    for mode in MODES[1:]:
        values = rates(profiles[mode])
        values["reduction_percent"] = {
            name: 100 * (1 - value / control_rates[name]) for name, value in values.items()}
        result[mode] = values
    return result


def receipt(expected):
    PUBLIC.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not (PUBLIC / "decision.json").exists():
        save(PUBLIC / "decision.json", {
            "status": "blocked-before-complete-execution", "expected_source": expected,
            "reason": "prerequisite step failed, job cancelled, or bounded experiment interrupted",
            "setup_outcomes": {name: os.environ.get(f"EVENTFD_{name.upper()}_OUTCOME", "unavailable")
                               for name in ("prerequisites", "zig", "kernel", "measure")},
            "performance_merge_eligible": False, "default": "legacy", "auto_merge": False})
    save(PUBLIC / "sha256sums.json", {
        path.name: bench.digest(path) for path in sorted(PUBLIC.glob("*.json"))
        if path.name != "sha256sums.json"})


def qualify(expected):
    if not re.fullmatch(r"[0-9a-f]{40}", expected):
        raise Blocked("invalid immutable source SHA")
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=bench.ROOT, text=True).strip()
    if (source != expected or os.environ.get("GITHUB_REPOSITORY") != "cataggar/hearth"
            or os.environ.get("GITHUB_ACTIONS") != "true"):
        raise Blocked("not the approved exact-source ephemeral hosted job")
    if subprocess.run(["git", "diff", "--quiet", "HEAD"], cwd=bench.ROOT).returncode:
        raise Blocked("tracked working source differs from the approved immutable head")
    deadline = time.monotonic() + 160 * 60
    phases = []
    decision = {"status": "blocked", "source": source, "performance_merge_eligible": False,
                "default": "legacy", "auto_merge": False}
    try:
        host, perf = host_probe()
        pins = build_inputs(phases, source)
        preregister = {"gates": GATES, "source": source, "pins": pins,
                       "vmm_cpu": host["vm_cpu"], "client_cpu": host["client_cpu"],
                       "aa_repetitions": 5, "paired_blocks": 5, "minimum_nonidle_seconds": 5,
                       "primary": "disk-flush-4096", "idle_seconds": 60,
                       "candidate_order": [["C10", "C01", "C11"], ["C01", "C11", "C10"], ["C11", "C10", "C01"],
                                           ["C01", "C10", "C11"], ["C11", "C01", "C10"]],
                       "paired_model": "paired log-ratio Student-t(df4), two-sided95%",
                       "primary_cpu": visible_cpu.SCOPE,
                       "fixed_completion_tail_seconds": .1, "background_subtracted": False,
                       "owned_task_BPF_detail_added_to_primary": False,
                       "background_controls": "before+after no-VM5.1s/matrix;60s/native idle",
                       "residual_policy": "worst-case background/counter/read perturbation of paired95% ratio must preserve unchanged gates; measured CPU untouched",
                       "owned_attribution_gaps": KERNEL_GAPS, "required_coverage": REQUIRED_GAPS}
        save(PUBLIC / "preregister.json", preregister)
        samples = [run_cell(f"aa-{index}", "C00", phases, deadline) for index in range(5)]
        gates = freeze(samples, pins)
        save(PUBLIC / "gates.json", gates)
        if gates["status"] != "noise-provisionally-acceptable":
            decision["status"] = "negative-hosted-noise-decision"
            decision["reason"] = "actual complete A/A exceeds unchanged gates; zero candidate samples"
        else:
            trace_profiles = {}
            for kind in ("stat", "stacks", "trace"):
                profile_result = run_cell(f"profile-{kind}-C00", "C00", phases, deadline, kind, perf)
                if kind == "trace":
                    trace_profiles["C00"] = profile_result
            blocks = []
            for index, order in enumerate(preregister["candidate_order"]):
                block = {"C00": run_cell(f"pair-{index}-C00", "C00", phases, deadline)}
                for mode in order:
                    block[mode] = run_cell(f"pair-{index}-{mode}", mode, phases, deadline)
                blocks.append(block)
            comparison = compare(blocks)
            save(PUBLIC / "paired.json", comparison)
            if comparison["all_candidates_have_demonstrated_regression"]:
                decision.update(status="negative-proven-required-regressions",
                                reason="each candidate has a demonstrated mandatory paired regression")
            for kind in ("stat", "stacks", "trace"):
                for mode in MODES[1:]:
                    profile_result = run_cell(f"profile-{kind}-{mode}", mode, phases, deadline, kind, perf)
                    if kind == "trace":
                        trace_profiles[mode] = profile_result
            save(PUBLIC / "mechanism.json", mechanism(trace_profiles))
            for mode in MODES:
                run_cell(f"active-restore-{mode}", mode, phases, deadline, lifecycle=True)
            for count in (1, 4, 8):
                for mode in MODES:
                    run_cell(f"native-scale-{count}-{mode}", mode, phases, deadline, scale_count=count)
            decision["status"] = ("negative-proven-required-regressions"
                                  if comparison["all_candidates_have_demonstrated_regression"]
                                  else "blocked-incomplete-lifecycle-scaling-qualification")
            decision["owned_attribution_gaps"] = KERNEL_GAPS
            decision["unexecuted_required_coverage"] = REQUIRED_GAPS
            decision["reason"] = ("each candidate has a demonstrated mandatory paired regression"
                                  if comparison["all_candidates_have_demonstrated_regression"]
                                  else "visible total CPU still requires bounded residual uncertainty and complete adoption coverage")
    except (OSError, ValueError, RuntimeError, EOFError, subprocess.SubprocessError) as error:
        decision["reason"] = str(error) if isinstance(error, Blocked) else type(error).__name__
    finally:
        try:
            decision["owned_input_image_cleanup"] = remove_owned_images(HOME, ("bzImage", "disk-probe"))
            for name in ("fixture", "native-fixture"):
                decision.setdefault("owned_input_image_cleanup", []).extend(
                    remove_owned_images(HOME / name, ("initrd.cpio.gz",)))
        except (OSError, ValueError, RuntimeError):
            decision["owned_image_cleanup_failed"] = True
            decision["measurement_decision_before_cleanup"] = decision["status"]
            decision["status"] = "blocked-owned-image-cleanup"
        save(PUBLIC / "decision.json", decision)
        receipt(expected)
        print(json.dumps(decision))
    return 1


def main():
    os.umask(0o077)
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(Blocked("bounded owned phase interrupted")))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("qualify", "namespace", "cell", "receipt"))
    parser.add_argument("--expected-sha")
    parser.add_argument("--out")
    parser.add_argument("--mode", choices=MODES)
    parser.add_argument("--profile", choices=("stat", "stacks", "trace"))
    parser.add_argument("--perf")
    parser.add_argument("--scale-count", type=int, choices=(1, 4, 8))
    parser.add_argument("--lifecycle", action="store_true")
    args = parser.parse_args()
    if args.phase == "qualify":
        return qualify(args.expected_sha)
    if args.phase == "receipt":
        receipt(args.expected_sha)
        return 0
    return namespace(args) if args.phase == "namespace" else cell(args)


if __name__ == "__main__":
    raise SystemExit(main())
