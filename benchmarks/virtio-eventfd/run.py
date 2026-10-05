#!/usr/bin/env python3
"""Untouched-L0 fixture and evidence collection; not a controlled-mode runner."""

import argparse
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import socket
import struct
import subprocess
import statistics
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
KERNEL_SHA256 = "4da539807474d189f1a15852046994e78d430a194c2e78b9255ae880069c7208"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def artifact_path(value):
    path = Path(value).resolve()
    path.relative_to(ROOT)
    return path


def save_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n")


def command(argv, out, name, timeout=30):
    started = time.time()
    try:
        environment = dict(os.environ, PERF_BUILDID_DIR=str(ROOT / ".perf/eventfd/perf-buildids"))
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=timeout, env=environment)
        stdout, stderr, status = result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired as error:
        stdout, stderr, status = error.stdout or b"", error.stderr or b"", "timeout"
    (out / (name + ".stdout")).write_bytes(stdout)
    (out / (name + ".stderr")).write_bytes(stderr)
    record = {
        "argv": argv,
        "cwd": str(ROOT),
        "started_unix": started,
        "elapsed_seconds": time.time() - started,
        "returncode": status,
    }
    save_json(out / (name + ".command.json"), record)
    return record


def newc_entry(name, data, mode, ino):
    encoded_name = name.encode() + b"\0"
    fields = (ino, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(encoded_name), 0)
    header = b"070701" + b"".join(f"{value:08x}".encode() for value in fields)
    prefix = header + encoded_name
    prefix += b"\0" * (-len(prefix) % 4)
    return prefix + data + b"\0" * (-len(data) % 4)


def prepare(args):
    """No external cpio, filesystem formatter, Docker image, or SDK CONNECT."""
    import gzip

    out = artifact_path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    kernel = artifact_path(args.kernel)
    tap_probe = getattr(args, "tap_probe", None)
    agent = artifact_path(tap_probe or args.probe or args.agent)
    busybox = Path(args.busybox)
    if digest(kernel) != KERNEL_SHA256:
        raise ValueError("kernel does not match the pinned 5.10.245 fixture")
    subprocess.run(["/usr/bin/busybox", "true"], check=True, cwd=ROOT)
    heartbeat = ""
    if args.heartbeat_ms:
        heartbeat = (
            "(while true; do echo DIAGNOSTIC_HEARTBEAT; "
            f"/bin/busybox sleep {args.heartbeat_ms / 1000:.3f}; done) &\n"
        )
    script = (
        "#!/bin/sh\nset -eu\n"
        "/bin/busybox mount -t devtmpfs devtmpfs /dev\n"
        "exec </dev/console >/dev/console 2>&1\n"
        "/bin/busybox mount -t proc proc /proc\n"
        "/bin/busybox mount -t sysfs sysfs /sys\n"
        "/bin/busybox mkdir -p /dev/pts\n"
        "/bin/busybox mount -t devpts devpts /dev/pts\n"
        "echo EVENTFD_L0_GUEST_READY\n"
        "/bin/busybox cat /proc/version /proc/cmdline /proc/interrupts\n"
        "/bin/busybox find /sys/bus/virtio/devices -maxdepth 2 -type l\n"
        + heartbeat
        + (
            "/bin/busybox ip link set lo up\n"
            "/bin/busybox ip addr add 192.0.2.2/30 dev eth0\n"
            "/bin/busybox ip link set eth0 mtu 1500 up\n"
            "exec /eventfd-guest-probe\n" if tap_probe
            else "exec /eventfd-guest-probe\n" if args.probe
            else "exec /hearth-agent\n"
        )
    ).encode()
    entries = [
        ("bin", b"", 0o40755),
        ("dev", b"", 0o40755),
        ("proc", b"", 0o40755),
        ("sys", b"", 0o40755),
        ("bench", b"", 0o40700),
        ("bin/busybox", busybox.read_bytes(), 0o100755),
        ("bin/sh", b"busybox", 0o120777),
        ("eventfd-guest-probe" if args.probe or tap_probe else "hearth-agent", agent.read_bytes(), 0o100755),
        ("init", script, 0o100755),
        ("TRAILER!!!", b"", 0),
    ]
    archive = b"".join(newc_entry(*entry, index + 1) for index, entry in enumerate(entries))
    (out / "init").write_bytes(script)
    (out / "initrd.cpio.gz").write_bytes(gzip.compress(archive, mtime=0))
    save_json(
        out / "fixture.json",
        {
            "kernel": str(kernel.relative_to(ROOT)),
            "kernel_sha256": digest(kernel),
            "guest_binary": str(agent.relative_to(ROOT)),
            "guest_binary_sha256": digest(agent),
            "busybox": str(busybox),
            "busybox_sha256": digest(busybox),
            "init_sha256": digest(out / "init"),
            "initrd_sha256": digest(out / "initrd.cpio.gz"),
            "diagnostic_heartbeat_ms": args.heartbeat_ms,
            "guest_agent_interactive_poll_ms": None if args.probe or tap_probe else 50,
            "native_probe": bool(args.probe or tap_probe),
            "transport": "tap-tcp" if tap_probe else "vsock",
            "unsupported": ["host-initiated CONNECT", "SDK tar/port-forward bulk"],
        },
    )


def thread_roster(pid):
    result = []
    for task in sorted(Path(f"/proc/{pid}/task").iterdir()):
        tid = int(task.name)
        stat = (task / "stat").read_text()
        # comm can contain spaces and parentheses; fields start after its final ')'.
        fields = stat[stat.rfind(")") + 2 :].split()
        scheduling = (task / "schedstat").read_text().split()
        result.append(
            {
                "tid": tid,
                "comm": (task / "comm").read_text().strip(),
                "utime_ticks": int(fields[11]),
                "stime_ticks": int(fields[12]),
                "start_ticks": int(fields[19]),
                "cpu_runtime_ns": int(scheduling[0]),
                "affinity": sorted(os.sched_getaffinity(tid)),
            }
        )
    return result


def cpu_delta(before, after):
    if {row["tid"] for row in before} != {row["tid"] for row in after}:
        raise ValueError("thread roster changed during sample; invalidate, do not omit CPU")
    old = {row["tid"]: row for row in before}
    if any("cpu_runtime_ns" in row for row in before + after):
        if not all("cpu_runtime_ns" in row and "start_ticks" in row for row in before + after):
            raise ValueError("mixed CPU accounting models; invalidate sample")
        if any(row["start_ticks"] != old[row["tid"]]["start_ticks"] for row in after):
            raise ValueError("thread generation changed during sample")
        elapsed = [row["cpu_runtime_ns"] - old[row["tid"]]["cpu_runtime_ns"] for row in after]
        if any(value < 0 for value in elapsed):
            raise ValueError("owned CPU execution counter reset")
        return sum(elapsed) / 1e9
    ticks = sum(
        row["utime_ticks"] + row["stime_ticks"]
        - old[row["tid"]]["utime_ticks"] - old[row["tid"]]["stime_ticks"]
        for row in after
    )
    return ticks / os.sysconf("SC_CLK_TCK")


def host_cpu_delta(before, after, seconds):
    def counters(text):
        line = next(line for line in text.splitlines() if line.startswith("cpu "))
        return [int(value) for value in line.split()[1:9]]

    old, new = counters(before), counters(after)
    delta = [end - start for start, end in zip(old, new)]
    if len(delta) != 8 or any(value < 0 for value in delta):
        raise ValueError("host CPU counters reset or have an unsupported layout")
    ticks = os.sysconf("SC_CLK_TCK")
    total = sum(delta) / ticks
    idle = (delta[3] + delta[4]) / ticks
    return {
        "nonidle_including_steal_cpu_seconds": total - idle,
        "idle_or_iowait_cpu_seconds": idle,
        "steal_cpu_seconds": delta[7] / ticks,
        "nonidle_one_core_equivalent_percent": 100 * (total - idle) / seconds,
        "scope": "aggregate host noise control, not owned backend CPU attribution",
    }


def recv_exact(connection, count):
    result = bytearray()
    while len(result) < count:
        try:
            chunk = connection.recv(count - len(result))
        except TimeoutError as error:
            raise TimeoutError(
                f"receive timed out: received={len(result)}, expected={count}, "
                f"partial_sha256={hashlib.sha256(result).hexdigest()}"
            ) from error
        if not chunk:
            raise EOFError("agent connection closed")
        result.extend(chunk)
    return bytes(result)


def send_message(connection, request):
    payload = json.dumps(request).encode()
    connection.sendall(struct.pack("<I", len(payload)) + payload)


def receive_message(connection):
    size = struct.unpack("<I", recv_exact(connection, 4))[0]
    if size > 16 * 1024 * 1024:
        raise ValueError("oversized guest response")
    return json.loads(recv_exact(connection, size))


def rpc(connection, request):
    send_message(connection, request)
    return receive_message(connection)


def interactive(connection, command_text, expected):
    started = time.monotonic()
    send_message(connection, {
        "method": "spawn", "cmd": command_text, "interactive": True, "cols": 80, "rows": 24,
    })
    output = bytearray()
    first_byte_ms = None
    while True:
        message = receive_message(connection)
        if message.get("type") == "stdout":
            data = base64.b64decode(message["data"], validate=True)
            if data and first_byte_ms is None:
                first_byte_ms = (time.monotonic() - started) * 1000
            output.extend(data)
        elif message.get("type") == "exit":
            if message.get("code") != 0 or bytes(output) != expected.encode() or first_byte_ms is None:
                raise ValueError(f"PTY integrity/exit mismatch: {message}, stdout={bytes(output)!r}")
            return {"ok": True, "first_byte_ms": first_byte_ms, "stdout": base64.b64encode(output).decode()}
        else:
            raise ValueError(f"unexpected PTY response: {message}")


def native_payload(sequence, size):
    return struct.pack("<Q", sequence) + bytes((index + sequence) % 256 for index in range(size - 8))


def native_reply(connection, sequence, payload):
    try:
        count = struct.unpack("<I", recv_exact(connection, 4))[0]
    except TimeoutError as error:
        raise TimeoutError(f"native sequence={sequence} header: {error}") from error
    if count != len(payload) + 8:
        raise ValueError(f"native probe length mismatch: sequence={sequence}, expected={len(payload) + 8}, actual={count}")
    try:
        reply = recv_exact(connection, count)
    except TimeoutError as error:
        raise TimeoutError(f"native sequence={sequence} body: {error}") from error
    checksum = 0xCBF29CE484222325
    for byte in payload:
        checksum = ((checksum ^ byte) * 0x100000001B3) & ((1 << 64) - 1)
    if struct.unpack("<Q", reply[:8])[0] != checksum or reply[8:] != payload:
        raise ValueError(
            f"native probe sequence/payload/checksum mismatch: sequence={sequence}, "
            f"expected_sha256={hashlib.sha256(payload).hexdigest()}, "
            f"actual_sha256={hashlib.sha256(reply[8:]).hexdigest()}"
        )
    return {"ok": True, "sequence": sequence, "bytes_each_direction": len(payload), "checksum": checksum}


def native_echo(connection, sequence, size):
    payload = native_payload(sequence, size)
    connection.sendall(struct.pack("<I", len(payload)) + payload)
    return native_reply(connection, sequence, payload)


def native_backpressure(connection, sequence, size):
    payloads = [native_payload(sequence * 8 + index, size) for index in range(8)]
    send_errors = []

    def send():
        try:
            for payload in payloads:
                connection.sendall(struct.pack("<I", len(payload)) + payload)
        except OSError as error:
            send_errors.append(str(error))

    sender = threading.Thread(target=send, name="owned-native-sender")
    sender.start()
    try:
        # Bounded slow reader, not a producer waiting for itself: receiving
        # starts independently even when the concurrent sender is blocked.
        time.sleep(0.25)
        responses = [
            native_reply(connection, sequence * 8 + index, payload)
            for index, payload in enumerate(payloads)
        ]
        sender.join(timeout=2)
        if sender.is_alive() or send_errors:
            raise ValueError(f"native sender did not finish: {send_errors}")
        return {
            "ok": True, "messages": responses, "slow_reader_seconds": 0.25,
            "bytes_each_direction": size * 8,
        }
    finally:
        if sender.is_alive():
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sender.join(timeout=2)
            if sender.is_alive():
                raise RuntimeError("owned sender could not be joined")


def await_marker(child, serial_path, marker, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise RuntimeError(f"VMM exited before guest marker: {child.returncode}")
        if marker in serial_path.read_bytes():
            return
        time.sleep(0.02)
    raise TimeoutError(f"guest did not emit {marker!r}")


def perf_collect(pid, out, profile, seconds, sudo, trace_events, buffer_pages=None):
    tids = ",".join(str(row["tid"]) for row in thread_roster(pid))
    if profile == "stat":
        argv = [
            "perf", "stat", "-t", tids, "-e",
            "task-clock,context-switches,cpu-migrations,page-faults",
            "-o", str(out / "perf-stat.txt"), "--", "sleep", str(seconds),
        ]
    elif profile == "stacks":
        argv = [
            "perf", "record", "-t", tids, "-e", "cpu-clock", "-F", "199",
            "-g", "--call-graph", "dwarf", "-o", str(out / "cpu.data"),
            "--", "sleep", str(seconds),
        ]
    else:
        argv = [
            "perf", "record", "-t", tids, "-e", "kvm:kvm_entry",
            "-e", "kvm:kvm_exit", "-e", "syscalls:sys_enter_ioctl",
            "-e", "syscalls:sys_exit_ioctl", "-o", str(out / "kvm-ioctl.data"),
            "--", "sleep", str(seconds),
        ]
        insertion = argv.index("--")
        argv[insertion:insertion] = [item for event in trace_events for item in ("-e", event)]
    if buffer_pages is not None:
        if profile == "stat" or not 1 <= buffer_pages <= 4096:
            raise ValueError("buffer pages require a bounded recording profile")
        insertion = argv.index("--")
        argv[insertion:insertion] = ["-m", str(buffer_pages)]
    if sudo:
        argv = [
            "sudo", "-n", "timeout", "--kill-after=5", str(seconds + 10),
            "env", f"PERF_BUILDID_DIR={ROOT / '.perf/eventfd/perf-buildids'}",
        ] + argv
    record = {"argv": argv, "cwd": str(ROOT), "started_unix": time.time()}
    save_json(out / "perf.command.json", record)
    handle = (out / "perf.stderr").open("wb")
    environment = dict(os.environ, PERF_BUILDID_DIR=str(ROOT / ".perf/eventfd/perf-buildids"))
    process = subprocess.Popen(argv, cwd=ROOT, stdout=handle, stderr=handle, env=environment)
    return process, handle


def run(args):
    out = artifact_path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    binary, fixture = artifact_path(args.binary), artifact_path(args.fixture)
    metadata = json.loads((fixture / "fixture.json").read_text())
    if metadata.get("transport", "vsock") != "vsock":
        raise ValueError("use tap_probe.py for a private-namespace TAP fixture")
    kernel = artifact_path(metadata["kernel"])
    initrd = fixture / "initrd.cpio.gz"
    if digest(kernel) != metadata["kernel_sha256"] or digest(initrd) != metadata["initrd_sha256"]:
        raise ValueError("fixture changed after preparation")
    prefix = out / "vsock"
    native = metadata["native_probe"]
    if native != (args.workload in ("native-echo", "native-backpressure")):
        if args.workload != "idle":
            raise ValueError("workload does not match native versus agent fixture")
    sock_path = str(prefix) + ("_11000" if native else "_1024")
    if len(sock_path.encode()) >= 108:
        raise ValueError("UDS path exceeds sockaddr_un limit")
    affinity = {int(cpu) for cpu in args.cpus.split(",")}
    if not affinity <= os.sched_getaffinity(0):
        raise ValueError("requested affinity is outside allowed cpuset")
    allowed = os.sched_getaffinity(0)
    sibling_cpus = set(affinity)
    for cpu in affinity:
        topology = Path(f"/sys/devices/system/cpu/cpu{cpu}/topology/thread_siblings_list").read_text().strip()
        for part in topology.split(","):
            bounds = part.split("-")
            sibling_cpus.update(range(int(bounds[0]), int(bounds[-1]) + 1))
    if args.client_cpus:
        client_affinity = {int(cpu) for cpu in args.client_cpus.split(",")}
    else:
        choices = sorted(allowed - sibling_cpus)
        if not choices:
            raise ValueError("no separate client CPU; specify a viable cpuset")
        client_affinity = {choices[0]}
    if not client_affinity <= allowed or client_affinity & sibling_cpus:
        raise ValueError("client affinity must be allowed and separate from VMM and its SMT siblings")
    os.sched_setaffinity(0, client_affinity)
    argv = [
        str(binary), str(kernel), str(initrd),
        "console=ttyS0 nokaslr reboot=k panic=1 pci=off nomodules",
        "--vsock-cid", "43", "--vsock-uds", str(prefix),
    ]
    if args.disk:
        argv.extend(["--disk", str(artifact_path(args.disk))])
    manifest = {
        "variant": "L0", "accelerated": False,
        "argv": argv, "cwd": str(ROOT), "started_unix": time.time(),
        "source_baseline": "b07f73b26b8ae876928d9c515b94bba1e9945870",
        "binary_sha256": digest(binary), "fixture": metadata,
        "runner_sha256": digest(Path(__file__)),
        "host_kernel": os.uname().release, "vcpus": 1, "guest_ram_mib": 512,
        "cpus": sorted(affinity), "profile": args.profile,
        "client_cpus": sorted(os.sched_getaffinity(0)),
        "seconds": args.seconds, "requests": args.requests,
        "workload": args.workload, "guest_command": args.command,
        "expected_stdout": args.expected,
        "payload_bytes": args.payload_bytes,
        "latency_timeout_seconds": args.timeout, "ticks_per_second": os.sysconf("SC_CLK_TCK"),
        "sdk_connect_used": False, "warmup": "boot/agent marker then 1 second silence",
        "cache_policy": "fresh boot, host caches unchanged, synchronous userspace backends",
        "pins_sha256": {
            path: digest(ROOT / path)
            for path in ("vmm/build.zig.zon", "agent/build.zig.zon", "package-lock.json")
        },
        "non_nested_comparison": "not available on this host",
        "perf_privilege": "sudo collector; VMM remains nonroot" if args.sudo_perf else "current uid",
        "vmm_uid": os.getuid(), "vmm_gid": os.getgid(),
    }
    source_record = command(["git", "rev-parse", "HEAD"], out, "source")
    command(["git", "diff", "--", "vmm", "agent"], out, "source-diff")
    command(["/home/g/.local/bin/zig", "version"], out, "compiler-version")
    manifest["source_command_returncode"] = source_record["returncode"]
    manifest["source_sha"] = (out / "source.stdout").read_text().strip()
    manifest["source_diff_sha256"] = digest(out / "source-diff.stdout")
    manifest["compiler_sha256"] = digest("/home/g/.local/bin/zig")
    save_json(out / "manifest.json", manifest)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.settimeout(10)
    listener.bind(sock_path)
    listener.listen(1)
    profiler, perf_handle, child, connection = None, None, None, None
    serial_path = out / "guest-serial.txt"
    result = {"status": "failed", "latencies_ms": [], "responses": [], "failures": []}
    try:
        with serial_path.open("wb") as serial, (out / "vmm.stderr").open("wb") as stderr:
            child = subprocess.Popen(argv, cwd=ROOT, stdout=serial, stderr=stderr)
            os.sched_setaffinity(child.pid, affinity)
            manifest["pid"] = child.pid
            save_json(out / "manifest.json", manifest)
            connection, _ = listener.accept()
            connection.settimeout(args.timeout)
            await_marker(child, serial_path, b"connected", 10)
            manifest["connected_marker_seconds_since_launch"] = time.time() - manifest["started_unix"]
            save_json(out / "manifest.json", manifest)
            time.sleep(1)
            if args.profile != "none":
                profiler, perf_handle = perf_collect(
                    child.pid, out, args.profile, args.seconds, args.sudo_perf, args.trace_event,
                )
                time.sleep(0.15)
            before = thread_roster(child.pid)
            save_json(out / "threads-before.json", before)
            host_started = time.monotonic()
            host_before = Path("/proc/stat").read_text()
            client_before = resource.getrusage(resource.RUSAGE_SELF)
            started = time.monotonic()
            if args.workload == "idle":
                time.sleep(args.seconds)
            else:
                for index in range(args.requests):
                    if time.monotonic() - started >= args.seconds:
                        break
                    request = {"method": "ping"} if args.workload == "ping" else {
                        "method": "exec", "cmd": args.command, "timeout": 2,
                    }
                    sent = time.monotonic()
                    try:
                        if args.workload == "native-backpressure":
                            response = native_backpressure(connection, index, args.payload_bytes)
                        elif native:
                            response = native_echo(connection, index, args.payload_bytes)
                        elif args.workload == "interactive":
                            response = interactive(connection, args.command, args.expected)
                        else:
                            response = rpc(connection, request)
                        elapsed = (time.monotonic() - sent) * 1000
                        if not response.get("ok"):
                            raise ValueError(f"guest rejected operation: {response}")
                        if args.workload == "exec":
                            stdout = base64.b64decode(response.get("stdout", ""), validate=True)
                            if response.get("exit_code") != 0 or stdout != args.expected.encode():
                                raise ValueError(f"guest integrity/exit mismatch: {response}")
                        result["responses"].append(response)
                        result["latencies_ms"].append(elapsed)
                    except (TimeoutError, EOFError, OSError, ValueError) as error:
                        result["failures"].append({"request": index, "error": str(error)})
                        # A partial framed response is not safely reusable.
                        break
            measured_seconds = time.monotonic() - started
            after = thread_roster(child.pid)
            save_json(out / "threads-after.json", after)
            host_after = Path("/proc/stat").read_text()
            host_seconds = time.monotonic() - host_started
            (out / "host-proc-stat-before.txt").write_text(host_before)
            (out / "host-proc-stat-after.txt").write_text(host_after)
            result["host_cpu_control"] = host_cpu_delta(host_before, host_after, host_seconds)
            result["host_cpu_control"]["window_seconds"] = host_seconds
            result["measured_seconds"] = measured_seconds
            result["all_thread_cpu_seconds"] = cpu_delta(before, after)
            client_after = resource.getrusage(resource.RUSAGE_SELF)
            result["client_cpu_seconds"] = (
                client_after.ru_utime + client_after.ru_stime
                - client_before.ru_utime - client_before.ru_stime
            )
            result["completed_operations"] = len(result["latencies_ms"])
            if args.workload != "idle" and not result["completed_operations"] and not result["failures"]:
                result["failures"].append({"error": "no real operations completed"})
            result["status"] = "passed" if not result["failures"] else "failed"
            if args.workload == "idle":
                result["idle_one_core_percent"] = 100 * result["all_thread_cpu_seconds"] / measured_seconds
            elif not result["completed_operations"]:
                result["cpu_per_operation"] = None
            else:
                result["cpu_per_operation"] = result["all_thread_cpu_seconds"] / result["completed_operations"]
            if profiler:
                status = profiler.wait(timeout=args.seconds + 10)
                result["perf_returncode"] = status
                if status != 0:
                    result["status"] = "failed"
                    result["failures"].append({"error": f"perf failed: {status}"})
    except (TimeoutError, EOFError, OSError, ValueError, RuntimeError) as error:
        result["failures"].append({"error": str(error)})
    finally:
        if profiler and profiler.poll() is None:
            try:
                profiler.wait(timeout=args.seconds + 20)
            except subprocess.TimeoutExpired:
                if args.sudo_perf:
                    subprocess.run(["sudo", "-n", "kill", "-TERM", str(profiler.pid)], cwd=ROOT, check=True)
                else:
                    profiler.kill()
                profiler.wait(timeout=5)
        if perf_handle:
            perf_handle.close()
        if connection:
            connection.close()
        listener.close()
        Path(sock_path).unlink(missing_ok=True)
        if child:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
            result["vmm_exit_code_after_owned_teardown"] = child.returncode
        save_json(out / "result.json", result)
    if args.profile == "stacks" and (out / "cpu.data").exists():
        if args.sudo_perf:
            command(["sudo", "-n", "chown", f"{os.getuid()}:{os.getgid()}", str(out / "cpu.data")], out, "own-cpu-data")
        prefix = [
            "sudo", "-n", "env", f"PERF_BUILDID_DIR={ROOT / '.perf/eventfd/perf-buildids'}",
        ] if args.sudo_perf else []
        # Only our private collector file was returned to the invoking uid.
        # Root perf otherwise rejects that deliberate ownership transfer.
        force = ["-f"] if args.sudo_perf else []
        report = command(prefix + ["perf", "report", "--stdio"] + force + ["-i", str(out / "cpu.data")], out, "cpu-report")
        stacks = command(prefix + ["perf", "script"] + force + ["-i", str(out / "cpu.data")], out, "cpu-stacks")
        if report["returncode"] != 0 or stacks["returncode"] != 0:
            result["status"] = "failed"
            result["failures"].append({"error": "perf stack/report decoding failed"})
    if args.profile == "trace" and (out / "kvm-ioctl.data").exists():
        if args.sudo_perf:
            command(["sudo", "-n", "chown", f"{os.getuid()}:{os.getgid()}", str(out / "kvm-ioctl.data")], out, "own-trace-data")
        trace = command(["perf", "script", "-i", str(out / "kvm-ioctl.data")], out, "kvm-ioctl")
        if trace["returncode"] != 0:
            result["status"] = "failed"
            result["failures"].append({"error": "perf trace decoding failed"})
    if args.profile == "stat" and args.sudo_perf and (out / "perf-stat.txt").exists():
        command(["sudo", "-n", "chown", f"{os.getuid()}:{os.getgid()}", str(out / "perf-stat.txt")], out, "own-stat")
    save_json(out / "result.json", result)
    print(json.dumps(result))
    return 0 if result["status"] == "passed" else 1


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summarize(args):
    rows = []
    for value in args.runs:
        directory = artifact_path(value)
        manifest = json.loads((directory / "manifest.json").read_text())
        result = json.loads((directory / "result.json").read_text())
        rows.append({"path": str(directory.relative_to(ROOT)), "manifest": manifest, "result": result})
    groups = {}
    for row in rows:
        manifest = row["manifest"]
        conditions = {
            field: manifest.get(field) for field in (
                "variant", "workload", "profile", "guest_command", "expected_stdout",
                "binary_sha256", "compiler_sha256", "runner_sha256", "host_kernel", "source_baseline",
                "cpus", "client_cpus", "vcpus", "guest_ram_mib", "payload_bytes",
                "requests", "seconds", "latency_timeout_seconds", "cache_policy",
                "warmup", "perf_privilege",
            )
        }
        conditions["fixture"] = manifest["fixture"]
        argv = manifest.get("argv", [])
        conditions["disk"] = argv[argv.index("--disk") + 1] if "--disk" in argv else None
        key = json.dumps(conditions, sort_keys=True)
        groups.setdefault(key, []).append(row)
    report = {
        "status": "passed" if all(row["result"]["status"] == "passed" for row in rows) else "failed",
        "all_runs": rows, "groups": [],
        "candidate_comparisons": None, "numeric_gates": "not frozen; C00/noise unavailable",
        "performance_merge_eligible": False,
    }
    for key, samples in groups.items():
        valid = [row["result"] for row in samples if row["result"]["status"] == "passed"]
        latencies = [latency for row in valid for latency in row["latencies_ms"]]
        medians = [statistics.median(row["latencies_ms"]) for row in valid if row["latencies_ms"]]
        report["groups"].append({
            "conditions": json.loads(key),
            "executed_runs": len(samples), "passed_runs": len(valid),
            "failed_runs": len(samples) - len(valid),
            "completed_operations_in_passing_runs": sum(row["completed_operations"] for row in valid),
            "latency_ms": {name: percentile(latencies, fraction) for name, fraction in (
                ("p50", 0.50), ("p95", 0.95), ("p99", 0.99),
            )},
            "per_run_median_ms": medians,
            "median_standard_deviation_ms": statistics.stdev(medians) if len(medians) > 1 else None,
            "median_coefficient_of_variation_percent": (
                100 * statistics.stdev(medians) / statistics.mean(medians)
                if len(medians) > 1 and statistics.mean(medians) else None
            ),
            "cpu_seconds_per_operation": [row.get("cpu_per_operation") for row in valid],
            "idle_one_core_percent": [row["idle_one_core_percent"] for row in valid if "idle_one_core_percent" in row],
        })
    save_json(artifact_path(args.out), report)
    print(json.dumps(report))
    return 0 if report["status"] == "passed" else 1


def positive_float(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be positive and finite")
    return number


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="phase", required=True)
    fixture = commands.add_parser("prepare")
    fixture.add_argument("--kernel", required=True)
    fixture.add_argument("--agent", required=True)
    native = fixture.add_mutually_exclusive_group()
    native.add_argument("--probe", help="Use the timer-free native vsock guest probe instead of the agent")
    native.add_argument("--tap-probe", help="Use the timer-free native TCP guest probe instead of the agent")
    fixture.add_argument("--busybox", default="/usr/bin/busybox")
    fixture.add_argument("--heartbeat-ms", type=int, default=0)
    fixture.add_argument("--out", required=True)
    runner = commands.add_parser("run")
    runner.add_argument("--binary", required=True)
    runner.add_argument("--fixture", required=True)
    runner.add_argument("--disk")
    runner.add_argument("--workload", choices=[
        "idle", "ping", "exec", "interactive", "native-echo", "native-backpressure",
    ], required=True)
    runner.add_argument("--command", default="printf x")
    runner.add_argument("--expected", default="x")
    runner.add_argument("--profile", choices=["none", "stat", "stacks", "trace"], default="none")
    runner.add_argument("--sudo-perf", action="store_true", help="Elevate only perf, never the VMM; do not alter host settings")
    runner.add_argument("--trace-event", action="append", default=[], choices=[
        "kvm:kvm_userspace_exit", "kvm:kvm_mmio", "kvm:kvm_set_irq",
    ], help="Add only independently verified available attribution tracepoints")
    runner.add_argument("--seconds", type=positive_float, default=5)
    runner.add_argument("--requests", type=positive_int, default=1000)
    runner.add_argument("--payload-bytes", type=positive_int, default=4096)
    runner.add_argument("--timeout", type=positive_float, default=1)
    runner.add_argument("--cpus", required=True)
    runner.add_argument("--client-cpus", help="Separate client CPUs; default excludes VMM SMT siblings")
    runner.add_argument("--out", required=True)
    summary = commands.add_parser("summarize")
    summary.add_argument("--runs", nargs="+", required=True)
    summary.add_argument("--out", required=True)
    args = parser.parse_args()
    if args.phase == "run" and not 8 <= args.payload_bytes <= 65536:
        parser.error("--payload-bytes must be between 8 and 65536")
    if args.phase == "prepare":
        if args.heartbeat_ms < 0:
            parser.error("--heartbeat-ms must not be negative")
        prepare(args)
        return 0
    if args.phase == "summarize":
        return summarize(args)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
