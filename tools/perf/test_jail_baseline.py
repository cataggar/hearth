"""Standalone synchronous jail prerequisite acceptance; no perf/worker imports.

Run non-root under the common fleet lock with umask077. Requires sudo -n,
setpriv, /dev/kvm, static BusyBox, bsdcpio, gzip and the verified kernel.
FLINT_JAIL_TEST_BINARY/KERNEL select immutable row inputs. No skips.
"""

import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import stat
import subprocess
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
KERNEL_SHA256 = "4da539807474d189f1a15852046994e78d430a194c2e78b9255ae880069c7208"
MARKER = b"JAIL_BASELINE_DISK_OK"


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def proc_text(pid, suffix):
    return subprocess.check_output(
        ["sudo", "-n", "cat", f"/proc/{pid}/{suffix}"], text=True, timeout=5,
    )


def start_time(pid):
    return proc_text(pid, "stat").rsplit(")", 1)[1].split()[19]


class OwnedJail:
    def __init__(self, api=True):
        self.api_mode = api
        self.binary = Path(os.environ["FLINT_JAIL_TEST_BINARY"]).resolve()
        self.kernel = Path(os.environ["FLINT_JAIL_TEST_KERNEL"]).resolve()
        self.path = ROOT / ".perf/jail-baseline" / f"{os.getpid()}-{time.time_ns()}"
        self.process = None
        self.pid = None
        self.owned = {}
        self.output = None
        self.errors = None

    def prepare(self):
        if digest(self.kernel) != KERNEL_SHA256:
            raise RuntimeError("kernel differs from verified common5.10.245 input")
        shutil.copyfile(self.kernel, self.path / "bzImage")
        tree = self.path / "initrd-root"
        for folder in (tree, tree / "bin", tree / "dev"):
            folder.mkdir(mode=0o700)
        shutil.copyfile("/usr/bin/busybox", tree / "bin/busybox")
        (tree / "bin/busybox").chmod(0o700)
        (tree / "bin/sh").symlink_to("busybox")
        (tree / "init").write_text(
            "#!/bin/sh\nset -eu\n"
            "[ -c /dev/console ] || /bin/busybox mknod /dev/console c 5 1\n"
            "exec </dev/console >/dev/console 2>&1\n"
            "/bin/busybox mount -t devtmpfs devtmpfs /dev\n"
            "/bin/busybox dd if=/dev/zero of=/dev/vda bs=4096 count=1 conv=fsync\n"
            "/bin/busybox dd if=/dev/vda of=/checked bs=4096 count=1\n"
            "/bin/busybox sha256sum /checked\n"
            "echo JAIL_BASELINE_DISK_OK\n"
            "while :; do /bin/busybox sleep 1; done\n"
        )
        (tree / "init").chmod(0o700)
        entries = [".", *(str(p.relative_to(tree)) for p in sorted(tree.rglob("*")))]
        pack = compress = None
        with (self.path / "cpio.log").open("wb") as errors, \
                (self.path / "initrd.cpio.gz").open("wb") as output:
            try:
                pack = subprocess.Popen(
                    ["bsdcpio", "-o", "-H", "newc", "--null"], cwd=tree,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
                )
                compress = subprocess.Popen(["gzip", "-n"], stdin=pack.stdout, stdout=output)
                pack.stdout.close()
                pack.communicate(("\0".join(entries) + "\0").encode(), timeout=30)
                if pack.returncode or compress.wait(timeout=30):
                    raise RuntimeError("fixture packing failed")
            finally:
                for process in (pack, compress):
                    if process is not None and process.poll() is None:
                        process.kill()
                        process.wait(timeout=5)
        (self.path / "disk.raw").write_bytes(bytes([0xa3]) * (1024 * 1024))

    def find_owned(self):
        queue = [self.process.pid]
        while queue:
            pid = queue.pop(0)
            try:
                stamp = start_time(pid)
                self.owned.setdefault(pid, stamp)
                children = proc_text(pid, f"task/{pid}/children").split()
                queue.extend(int(child) for child in children)
                fields = dict(line.split(":", 1) for line in
                              proc_text(pid, "status").splitlines() if ":" in line)
                if (fields["Uid"].split() == [str(os.getuid())] * 4 and
                        fields["Seccomp"].strip() == "2"):
                    return pid
            except subprocess.CalledProcessError:
                continue
        return None

    def __enter__(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path.mkdir(mode=0o700)
        try:
            self.prepare()
            self.output = (self.path / "stdout.log").open("wb")
            self.errors = (self.path / "stderr.log").open("wb")
            args = [str(self.binary), "--jail", str(self.path),
                    "--jail-uid", str(os.getuid()), "--jail-gid", str(os.getgid())]
            if self.api_mode:
                args += ["--api-sock", "api.sock"]
            else:
                args += ["/bzImage", "/initrd.cpio.gz", "--disk", "/disk.raw",
                         "--cmdline", "console=ttyS0 reboot=k panic=1 pci=off rdinit=/init"]
            tracer = os.environ.get("FLINT_JAIL_TEST_STRACE")
            if tracer:
                args = [tracer, "-f", "-o", str(self.path / "startup.strace"), *args]
            args = ["sudo", "-n", "setpriv", "--groups=0", "--", *args]
            self.process = subprocess.Popen(
                args, cwd=self.path, stdout=self.output, stderr=self.errors,
                start_new_session=True,
            )
            save(self.path / "launch.json", {
                "argv": args, "supervisor_pid": self.process.pid,
                "binary_sha256": digest(self.binary), "kernel_sha256": digest(self.kernel),
                "artifact_umask": "077", "inherited_supplementary_groups": [0],
                "source_revision": os.environ.get("FLINT_JAIL_TEST_REVISION"),
                "scope": "synchronous correctness only; no worker/perf/notification features",
            })
            deadline = time.monotonic() + 15
            while self.pid is None:
                self.pid = self.find_owned()
                if self.process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("enforced VMM identity did not become ready")
                if self.pid is None:
                    time.sleep(0.02)
            save(self.path / "owned-pids.json", self.owned)
            while self.api_mode and not (self.path / "api.sock").exists():
                if self.process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("enforced API did not become ready")
                time.sleep(0.02)
            return self
        except BaseException:
            self.close()
            raise

    def request(self, method, route, body=None):
        payload = json.dumps(body).encode() if body is not None else b""
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(15)
            previous = Path.cwd()
            try:
                os.chdir(self.path)
                client.connect("api.sock")
            finally:
                os.chdir(previous)
            client.sendall(
                f"{method} {route} HTTP/1.1\r\nHost: localhost\r\n"
                f"Content-Length: {len(payload)}\r\nConnection: close\r\n\r\n".encode() + payload
            )
            response = b""
            while True:
                data = client.recv(4096)
                if not data:
                    break
                response += data
                if len(response) > 65536:
                    raise RuntimeError("bounded HTTP response exceeded")
        header, result = response.split(b"\r\n\r\n", 1)
        if header.splitlines()[0].split()[1] not in (b"200", b"204"):
            raise RuntimeError(f"HTTP prerequisite failure: {response!r}")
        return result

    def boot(self):
        self.request("PUT", "/drives/root", {"drive_id": "root", "path_on_host": "/disk.raw"})
        self.request("PUT", "/boot-source", {
            "kernel_image_path": "/bzImage", "initrd_path": "/initrd.cpio.gz",
            "boot_args": "console=ttyS0 reboot=k panic=1 pci=off rdinit=/init",
        })
        self.request("PUT", "/actions", {"action_type": "InstanceStart"})

    def close(self):
        try:
            if self.process is not None:
                if self.process.poll() is None:
                    self.find_owned()
                for pid, stamp in reversed(list(self.owned.items())):
                    try:
                        if start_time(pid) == stamp:
                            subprocess.run(["sudo", "-n", "kill", "-TERM", "--", str(pid)],
                                           check=False, timeout=5, stderr=subprocess.DEVNULL)
                    except subprocess.CalledProcessError:
                        pass
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    for pid, stamp in reversed(list(self.owned.items())):
                        try:
                            if start_time(pid) == stamp:
                                subprocess.run(["sudo", "-n", "kill", "-KILL", "--", str(pid)],
                                               check=False, timeout=5, stderr=subprocess.DEVNULL)
                        except subprocess.CalledProcessError:
                            pass
                    self.process.wait(timeout=5)
                save(self.path / "cleanup.json", {
                    "recorded_pids": self.owned, "exit_code": self.process.returncode,
                    "live_pid_paths": [pid for pid in self.owned if Path(f"/proc/{pid}").exists()],
                })
        finally:
            for stream in (self.output, self.errors):
                if stream is not None:
                    stream.close()
            try:
                subprocess.run(["sudo", "-n", "rm", "-f", "--", str(self.path / "dev/kvm")],
                               check=True, timeout=5)
                if (self.path / "dev").exists():
                    subprocess.run(["sudo", "-n", "rmdir", "--", str(self.path / "dev")],
                                   check=True, timeout=5)
            finally:
                (self.path / "api.sock").unlink(missing_ok=True)

    def __exit__(self, *_):
        self.close()


class JailBaseline(unittest.TestCase):
    def setUp(self):
        self.assertNotEqual(os.getuid(), 0, "run non-root; only bootstrap uses sudo")
        old = os.umask(0o077)
        self.addCleanup(os.umask, old)

    def identity(self, vm):
        tids = subprocess.check_output(["sudo", "-n", "ls", f"/proc/{vm.pid}/task"],
                                       text=True, timeout=5).split()
        roster = {}
        for tid in tids:
            status = proc_text(vm.pid, f"task/{tid}/status")
            fields = dict(line.split(":", 1) for line in status.splitlines() if ":" in line)
            self.assertEqual(fields["Uid"].split(), [str(os.getuid())] * 4)
            self.assertEqual(fields["Gid"].split(), [str(os.getgid())] * 4)
            self.assertEqual(fields["Groups"].split(), [])
            self.assertEqual(fields["Seccomp"].strip(), "2")
            self.assertEqual(fields["NoNewPrivs"].strip(), "1")
            self.assertEqual(int(fields["CapEff"], 16), 0)
            roster[tid] = status
        save(vm.path / "owned-roster.json", roster)

    def disk(self, vm):
        deadline = time.monotonic() + 30
        while MARKER not in (vm.path / "stdout.log").read_bytes():
            self.assertIsNone(vm.process.poll(), "enforced guest exited")
            self.assertLess(time.monotonic(), deadline, "guest disk IO did not finish")
            time.sleep(0.02)
        expected = hashlib.sha256(bytes(4096)).hexdigest().encode()
        self.assertIn(expected, (vm.path / "stdout.log").read_bytes())
        self.assertEqual((vm.path / "disk.raw").read_bytes(),
                         bytes(4096) + bytes([0xa3]) * (1024 * 1024 - 4096))
        self.identity(vm)

    def test_enforced_api_and_explicit_private_permissions(self):
        before = Path("/dev/kvm").stat()
        with OwnedJail() as vm:
            directory = (vm.path / "dev").stat()
            device = (vm.path / "dev/kvm").stat()
            self.assertEqual((directory.st_uid, directory.st_gid, stat.S_IMODE(directory.st_mode)),
                             (0, 0, 0o755))
            self.assertEqual((device.st_uid, device.st_gid, stat.S_IMODE(device.st_mode)),
                             (os.getuid(), os.getgid(), 0o600))
            fd = os.open(vm.path / "dev/kvm", os.O_RDWR | os.O_CLOEXEC)
            try:
                self.assertEqual(fcntl.ioctl(fd, 0xAE00, 0), 12)
            finally:
                os.close(fd)
            self.identity(vm)
            for memory in (512, 640, 512):
                self.assertEqual(vm.request("PUT", "/machine-config", {"mem_size_mib": memory}), b"")
                self.assertEqual(json.loads(vm.request("GET", "/machine-config")),
                                 {"mem_size_mib": memory, "vcpu_count": 1})
        after = Path("/dev/kvm").stat()
        self.assertEqual((before.st_dev, before.st_ino, before.st_uid, before.st_gid, before.st_mode),
                         (after.st_dev, after.st_ino, after.st_uid, after.st_gid, after.st_mode))

    def test_enforced_api_thread_epoll_and_guest_disk(self):
        with OwnedJail() as vm:
            vm.boot()
            self.disk(vm)

    def test_enforced_cli_guest_disk(self):
        with OwnedJail(api=False) as vm:
            self.disk(vm)

    def test_cleanup_evidence_enospc_still_removes_owned_resources(self):
        capacity = os.statvfs(ROOT)
        self.assertGreaterEqual(capacity.f_bavail * capacity.f_frsize, 64 * 1024 * 1024)
        original_save = save

        def fail_cleanup_evidence(path, value):
            if path.name == "cleanup.json":
                raise OSError(errno.ENOSPC, "injected cleanup evidence failure")
            original_save(path, value)

        vm = OwnedJail()
        with mock.patch.dict(OwnedJail.close.__globals__, {"save": fail_cleanup_evidence}):
            with self.assertRaises(OSError) as failure:
                with vm:
                    self.identity(vm)
                    self.assertEqual(json.loads(vm.request("GET", "/machine-config"))["vcpu_count"], 1)
        self.assertEqual(failure.exception.errno, errno.ENOSPC)
        self.assertIsNotNone(vm.process.returncode)
        self.assertTrue(vm.owned)
        self.assertFalse(any(Path(f"/proc/{pid}").exists() for pid in vm.owned))
        self.assertTrue(vm.output.closed)
        self.assertTrue(vm.errors.closed)
        self.assertFalse((vm.path / "cleanup.json").exists())
        self.assertFalse((vm.path / "dev").exists())
        self.assertFalse((vm.path / "api.sock").exists())
        original_save(vm.path / "cleanup-fault-audit.json", {
            "fault": "injected ENOSPC while saving cleanup.json",
            "recorded_pids": vm.owned,
            "exit_code": vm.process.returncode,
            "live_pid_paths": [],
            "logs_closed": True,
            "private_nodes_and_socket_gone": True,
        })
