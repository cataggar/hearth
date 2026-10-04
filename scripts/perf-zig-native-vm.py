#!/usr/bin/env python3
"""Guest-execution snapshot acceptance; invoke through the fleet-locked runner."""

import argparse
import base64
from contextlib import suppress
import hashlib
import http.client
import importlib.util
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


ROOT = Path(__file__).resolve().parents[1]


def project_path(value):
    path = (ROOT / value).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("fixture and output paths must remain in this worktree")
    return path


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class UnixHttp(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("localhost", timeout=10)
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(str(self.path))


def api(path, method, route, payload=None, expected=204):
    connection = UnixHttp(path)
    try:
        connection.request(method, route, None if payload is None else json.dumps(payload),
                           {"Content-Type": "application/json"})
        response = connection.getresponse()
        body = response.read().decode()
        if response.status != expected:
            raise RuntimeError(f"{method} {route}: {response.status}, expected {expected}: {body}")
        return body
    finally:
        connection.close()


def exact(connection, count):
    result = bytearray()
    while len(result) < count:
        chunk = connection.recv(count - len(result))
        if not chunk:
            raise RuntimeError("guest control channel closed")
        result.extend(chunk)
    return bytes(result)


def send(connection, value):
    payload = json.dumps(value).encode()
    connection.sendall(struct.pack("<I", len(payload)) + payload)


def receive(connection):
    count = struct.unpack("<I", exact(connection, 4))[0]
    if count > 16 * 1024 * 1024:
        raise RuntimeError(f"invalid guest frame length: {count}")
    return json.loads(exact(connection, count))


def request(connection, value):
    send(connection, value)
    result = receive(connection)
    if not result.get("ok"):
        raise RuntimeError(f"guest {value.get('method')}: {result}")
    return result


def execute(connection, command, expected_code=0, timeout=5):
    result = request(connection, {"method": "exec", "cmd": command, "timeout": timeout})
    if result["exit_code"] != expected_code:
        raise RuntimeError(f"guest command failed: {command}: {result}")
    return base64.b64decode(result["stdout"])


class Vm:
    def __init__(self, binary, folder, kernel, initrd, disk, cpu, restore=False, jailed=False, collector=None):
        self.folder = folder
        self.jailed = jailed
        self.collector = collector
        self.process = None
        self.control = None
        self.log = None
        self.listener = None
        self.socket_dir = ROOT / ".perf-zig-native" / "s" / f"{os.getpid()}-{time.monotonic_ns()}"
        self.socket_dir.mkdir(parents=True, mode=0o700)
        self.workdir = self.socket_dir if jailed else folder
        self.api_path = self.socket_dir / "a"
        self.vsock_path = self.socket_dir / "v"
        try:
            if len(str(self.vsock_path)) + 5 >= 108:
                raise ValueError("Unix socket path too long")
            self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.listener.settimeout(20)
            self.listener.bind(str(self.vsock_path) + "_1024")
            self.listener.listen(1)
            if restore and jailed:
                for name in ("disk.ext4", "state.snap", "memory.snap"):
                    shutil.copyfile(folder / name, self.workdir / name)
            elif not restore:
                shutil.copyfile(disk, self.workdir / "disk.ext4")
            if jailed and not restore:
                shutil.copyfile(kernel, self.workdir / "bzImage")
                shutil.copyfile(initrd, self.workdir / "initrd.cpio.gz")
            self.log = (folder / ("restore.log" if restore else "boot.log")).open("wb")
            argv = ["taskset", "-c", str(cpu), str(binary),
                    "--api-sock", "/a" if jailed else str(self.api_path)]
            if jailed:
                argv = ["sudo", "-n", "--", *argv, "--jail", str(self.workdir),
                        "--jail-uid", str(os.getuid()), "--jail-gid", str(os.getgid())]
            if restore:
                argv += ["--restore", "--vmstate-path", "state.snap", "--mem-path", "memory.snap",
                         "--disk", "disk.ext4", "--vsock-cid", "100",
                         "--vsock-uds", "/v" if jailed else str(self.vsock_path)]
            if collector:
                if not jailed:
                    raise ValueError("privileged collector requires the enforced non-root jail")
                specification = importlib.util.spec_from_file_location(
                    "native_perf_prerequisite", ROOT / "tools/perf/blk-io.py",
                )
                support = importlib.util.module_from_spec(specification)
                specification.loader.exec_module(support)
                argv = support.privileged_perf([*collector, "--", *argv[3:]])
            self.started = time.perf_counter()
            self.process = subprocess.Popen(
                argv, cwd=self.workdir, stdout=self.log, stderr=self.log, start_new_session=jailed,
            )
        except BaseException:
            self.close()
            raise
        try:
            deadline = time.monotonic() + 10
            while not self.api_path.exists():
                if self.process.poll() is not None:
                    raise RuntimeError(f"VMM exited: {self.process.returncode}")
                if time.monotonic() > deadline:
                    raise TimeoutError("VMM API startup")
                time.sleep(0.002)
            if not restore:
                api(self.api_path, "GET", "/no-such-route", expected=404)
                api(self.api_path, "PUT", "/machine-config", {"vcpu_count": 1, "mem_size_mib": 128})
                api(self.api_path, "PUT", "/boot-source", {
                    "kernel_image_path": "/bzImage" if jailed else str(kernel),
                    "initrd_path": "/initrd.cpio.gz" if jailed else str(initrd),
                    "boot_args": "console=ttyS0 reboot=k panic=1 pci=off rdinit=/init",
                })
                api(self.api_path, "PUT", "/drives/disk", {
                    "drive_id": "disk", "path_on_host": "disk.ext4",
                    "is_root_device": False, "is_read_only": False,
                })
                api(self.api_path, "PUT", "/vsock", {
                    "guest_cid": 100, "uds_path": "/v" if jailed else str(self.vsock_path),
                })
                api(self.api_path, "PUT", "/actions", {"action_type": "InstanceStart"})
            self.control, _ = self.listener.accept()
            self.control.settimeout(15)
            request(self.control, {"method": "ping"})
            if jailed:
                self.verify_jail()
            self.listener.close()
            self.listener = None
            self.ready_ms = (time.perf_counter() - self.started) * 1000
        except BaseException:
            self.close()
            raise

    def verify_jail(self):
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            try:
                raw = (entry / "stat").read_text()
                fields = raw[raw.rfind(")") + 2:].split()
                if int(fields[2]) != self.process.pid:
                    continue
                values = dict(line.split(":", 1) for line in
                              (entry / "status").read_text().splitlines() if ":" in line)
                if values["Name"].strip() != "flint":
                    continue
                self.jail_status = {"pid": int(entry.name), **{
                    key: values[key].strip() for key in
                    ("Uid", "Gid", "Groups", "CapEff", "NoNewPrivs", "Seccomp")
                }}
                if (list(map(int, values["Uid"].split())) != [os.getuid()] * 4
                        or list(map(int, values["Gid"].split())) != [os.getgid()] * 4
                        or values["Groups"].split()
                        or int(values["CapEff"].strip(), 16) != 0
                        or values["NoNewPrivs"].strip() != "1"
                        or values["Seccomp"].strip() != "2"):
                    raise RuntimeError("owned VMM has incorrect credentials or unenforced jail")
                self.jail_status["task_ids"] = sorted(
                    int(task.name) for task in (entry / "task").iterdir()
                )
                self.jail_status["task_status"] = []
                for tid in self.jail_status["task_ids"]:
                    task = dict(line.split(":", 1) for line in
                                (entry / "task" / str(tid) / "status").read_text().splitlines()
                                if ":" in line)
                    self.jail_status["task_status"].append({
                        key: task.get(key, "").strip() for key in
                        ("Name", "Tgid", "Pid", "PPid", "Kthread", "Uid", "Gid",
                         "Groups", "CapEff", "NoNewPrivs", "Seccomp")
                    })
                    if task.get("Kthread", "").strip() == "0" and (
                            list(map(int, task["Uid"].split())) != [os.getuid()] * 4
                            or list(map(int, task["Gid"].split())) != [os.getgid()] * 4
                            or task["Groups"].split()
                            or int(task["CapEff"].strip(), 16) != 0
                            or task["NoNewPrivs"].strip() != "1"
                            or task["Seccomp"].strip() != "2"):
                        raise RuntimeError("owned VMM userspace thread has incorrect jail credentials")
                return
            except (OSError, ValueError, IndexError):
                continue
        raise RuntimeError("could not verify owned VMM UID/capabilities/enforced jail")

    def signal(self, value):
        if self.jailed:
            target = (self.jail_status["pid"] if self.collector and hasattr(self, "jail_status")
                      else -self.process.pid)
            subprocess.run(["sudo", "-n", "kill", f"-{value}", "--",
                            str(target)], check=True, timeout=5)
        else:
            self.process.send_signal(getattr(signal, f"SIG{value}"))

    def close(self):
        if self.control:
            self.control.close()
            self.control = None
        if self.process and self.process.poll() is None:
            self.signal("TERM")
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.signal("KILL")
                self.process.wait(timeout=3)
        if self.log:
            self.log.close()
            self.log = None
        if self.listener:
            self.listener.close()
            self.listener = None
        if self.jailed and hasattr(self, "jail_status"):
            deadline = time.monotonic() + 3
            while any((Path("/proc") / str(tid)).exists()
                      for tid in self.jail_status["task_ids"]):
                if time.monotonic() >= deadline:
                    raise RuntimeError("owned VMM tasks remain after termination")
                time.sleep(0.01)
            self.cleanup_verified = True
        for name in ("a", "v", "v_1024"):
            (self.socket_dir / name).unlink(missing_ok=True)
        if self.jailed:
            for name in ("disk.ext4", "state.snap", "memory.snap"):
                source = self.workdir / name
                if source.exists():
                    shutil.copyfile(source, self.folder / name)
            for name in ("disk.ext4", "state.snap", "memory.snap", "bzImage", "initrd.cpio.gz"):
                (self.workdir / name).unlink(missing_ok=True)
            device = self.workdir / "dev" / "kvm"
            if device.exists():
                subprocess.run(["sudo", "-n", "rm", "-f", "--", str(device)],
                               check=True, timeout=5)
            directory = self.workdir / "dev"
            if directory.exists():
                subprocess.run(["sudo", "-n", "rmdir", "--", str(directory)],
                               check=True, timeout=5)
        if self.socket_dir.exists():
            self.socket_dir.rmdir()


def smoke(vm):
    connection = vm.control
    assert execute(connection, "printf exec-ok") == b"exec-ok"
    assert execute(connection, "exit 7", expected_code=7) == b""
    assert execute(connection, "exec sleep 3", expected_code=-1, timeout=1) == b""
    assert execute(connection, "kill -TERM $$", expected_code=-1) == b""
    response = request(connection, {"method": "exec", "cmd": "printf out; printf err >&2", "timeout": 5})
    assert response["exit_code"] == 0
    assert base64.b64decode(response["stdout"]) == b"out"
    assert base64.b64decode(response["stderr"]) == b"err"
    contents = b"cross-backend-file\n"
    request(connection, {"method": "write_file", "path": "/work/native.txt",
                         "data": base64.b64encode(contents).decode()})
    assert base64.b64decode(request(connection, {"method": "read_file", "path": "/work/native.txt"})["data"]) == contents
    assert execute(connection, "printf disk-state >/mnt/state; sync; cat /mnt/state") == b"disk-state"
    assert execute(connection, "dd if=/dev/zero of=/mnt/io bs=4096 count=16 conv=fsync 2>/dev/null; wc -c </mnt/io").strip() == b"65536"
    for interactive in (False, True):
        send(connection, {"method": "spawn", "cmd": "printf spawn-ok", "interactive": interactive})
        output = bytearray()
        while True:
            result = receive(connection)
            if result.get("type") == "stdout":
                output.extend(base64.b64decode(result["data"]))
            if result.get("type") == "exit":
                assert result["code"] == 0, result
                break
        assert b"spawn-ok" in output, output
    send(connection, {"method": "spawn", "cmd": "stty -echo; IFS= read -r line; stty size; printf input:%s $line",
                      "interactive": True})
    send(connection, {"type": "resize", "cols": 100, "rows": 40})
    send(connection, {"type": "stdin", "data": base64.b64encode(b"hello\n").decode()})
    output = bytearray()
    while True:
        response = receive(connection)
        if response.get("type") == "stdout":
            output.extend(base64.b64decode(response["data"]))
        if response.get("type") == "exit":
            assert response["code"] == 0, response
            break
    assert b"40 100" in output and b"input:hello" in output, output
    api(vm.api_path, "PUT", "/snapshot/create",
        {"snapshot_path": "invalid.snap", "mem_file_path": "invalid.mem"}, expected=400)
    for _ in range(3):
        api(vm.api_path, "PATCH", "/vm", {"state": "Paused"})
        assert "Paused" in api(vm.api_path, "GET", "/vm", expected=200)
        api(vm.api_path, "PATCH", "/vm", {"state": "Resumed"})
        assert execute(connection, "cat /work/native.txt") == contents
    return {"exec_exit": "passed", "files": "passed", "block_write_fsync_read": "passed",
            "spawn": "passed", "pty_output": "passed", "pause_resume": "passed",
            "pty_input_resize": "passed", "timeout_signals": "passed",
            "tap": "not supplied", "sdk_connect": "baseline listener absent"}


def prepare(argv):
    parser = argparse.ArgumentParser(description="Freeze one agent/initrd/disk fixture outside timed runtime")
    parser.add_argument("--agent", required=True)
    parser.add_argument("--init", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    agent, init, output = (project_path(getattr(args, key)) for key in ("agent", "init", "output"))
    output.mkdir(parents=True, exist_ok=False)
    root = output / "root"
    root.mkdir(mode=0o700)
    for directory in ("bin", "dev", "proc", "sys", "work", "mnt", "root"):
        (root / directory).mkdir(mode=0o700)
    shutil.copy2(agent, root / "hearth-agent")
    shutil.copy2("/usr/bin/busybox", root / "bin" / "busybox")
    shutil.copy2(init, root / "init")
    (root / "init").chmod(0o700)
    for name in ("sh", "mount", "mkdir", "cat", "sleep", "printf", "dd", "stty", "wc", "sync", "kill"):
        (root / "bin" / name).symlink_to("busybox")
    paths = ["."] + sorted(str(path.relative_to(root)) for path in root.rglob("*"))
    with (output / "guest.cpio.gz").open("wb") as stream:
        cpio = gzip = None
        try:
            cpio = subprocess.Popen(["bsdcpio", "--null", "-o", "-H", "newc"],
                                    cwd=root, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            gzip = subprocess.Popen(["gzip", "-n"], stdin=cpio.stdout, stdout=stream)
            cpio.stdout.close()
            cpio.stdin.write(("\0".join(paths) + "\0").encode())
            cpio.stdin.close()
            cpio_status = cpio.wait()
            gzip_status = gzip.wait()
            if cpio_status != 0 or gzip_status != 0:
                raise RuntimeError(f"initrd preparation failed: cpio={cpio_status}, gzip={gzip_status}")
        finally:
            for child in (gzip, cpio):
                if child and child.poll() is None:
                    child.kill()
            for child in (gzip, cpio):
                if child:
                    child.wait()
            if cpio:
                for pipe in (cpio.stdin, cpio.stdout):
                    if not pipe.closed:
                        with suppress(OSError):
                            pipe.close()
    disk = output / "disk.ext4"
    with disk.open("wb") as stream:
        stream.truncate(64 * 1024 * 1024)
    subprocess.run(["mkfs.ext4", "-q", "-F", "-U", "00000000-0000-0000-0000-000000000006",
                    "-E", "lazy_itable_init=0,lazy_journal_init=0", str(disk)], check=True)
    result = {name: digest(path) for name, path in (
        ("agent_sha256", agent), ("busybox_sha256", root / "bin" / "busybox"),
        ("init_sha256", init), ("initrd_sha256", output / "guest.cpio.gz"), ("disk_sha256", disk)
    )}
    (output / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


def main():
    os.umask(0o077)
    if len(sys.argv) > 1 and sys.argv[1] == "prepare":
        prepare(sys.argv[2:])
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--creator", required=True)
    parser.add_argument("--restorer", required=True)
    parser.add_argument("--kernel", required=True)
    parser.add_argument("--initrd", required=True)
    parser.add_argument("--disk", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--cpu", type=int, required=True)
    parser.add_argument("--heartbeat-ms", type=int, choices=(0, 10), required=True)
    parser.add_argument("--jailed", action="store_true")
    args = parser.parse_args()
    if os.getuid() == 0:
        raise SystemExit("guest acceptance must not run as root")
    creator, restorer, kernel, initrd, disk, output = (
        project_path(getattr(args, key)) for key in ("creator", "restorer", "kernel", "initrd", "disk", "output")
    )
    output.mkdir(parents=True, exist_ok=False)
    result = {"creator_sha256": digest(creator), "restorer_sha256": digest(restorer),
              "kernel_sha256": digest(kernel), "initrd_sha256": digest(initrd),
              "disk_template_sha256": digest(disk), "uid": os.getuid(), "cpu": args.cpu,
              "vcpu": 1, "memory_mib": 128, "heartbeat_ms": args.heartbeat_ms,
              "workload_sha256": digest(Path(__file__)), "jailed": args.jailed}
    vm = None
    vm_role = "creator"
    try:
        vm = Vm(creator, output, kernel, initrd, disk, args.cpu, jailed=args.jailed)
        if args.jailed:
            result["creator_jail_status"] = vm.jail_status
        result["boot_ready_ms"] = vm.ready_ms
        result["smoke"] = smoke(vm)
        vm.control.close()
        vm.control = None
        time.sleep(0.3)
        api(vm.api_path, "PATCH", "/vm", {"state": "Paused"})
        then = time.perf_counter()
        api(vm.api_path, "PUT", "/snapshot/create",
            {"snapshot_path": "state.snap", "mem_file_path": "memory.snap"})
        result["snapshot_ms"] = (time.perf_counter() - then) * 1000
        vm.close()
        if args.jailed:
            result["creator_cleanup_verified"] = vm.cleanup_verified
        vm = None
        restored = Vm(restorer, output, kernel, initrd, disk, args.cpu,
                      restore=True, jailed=args.jailed)
        vm = restored
        vm_role = "restorer"
        if args.jailed:
            result["restorer_jail_status"] = restored.jail_status
        assert execute(restored.control, "cat /work/native.txt; cat /mnt/state") == b"cross-backend-file\ndisk-state"
        assert execute(restored.control, "printf restored-exec") == b"restored-exec"
        result["restore_ready_ms"] = restored.ready_ms
        result["restored_guest_execution"] = "passed"
        result["state_sha256"] = digest(output / "state.snap")
        result["memory_sha256"] = digest(output / "memory.snap")
        result["status"] = "passed"
    except BaseException as error:
        result["status"] = "failed"
        result["error"] = repr(error)
        raise
    finally:
        try:
            if vm:
                vm.close()
                if args.jailed:
                    result[f"{vm_role}_cleanup_verified"] = vm.cleanup_verified
        except BaseException as error:
            result["status"] = "failed"
            result["cleanup_error"] = repr(error)
            raise
        finally:
            (output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
