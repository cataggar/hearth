"""Real enforced-jail regressions; run non-root under the fleet host lock.

Requires sudo -n mount/jail bootstrap, setpriv and functional /dev/kvm. No skips.
FLINT_JAIL_TEST_BINARY selects the compiled binary; FLINT_JAIL_TEST_STRACE
optionally retains its actual enforced-filter trace.
"""

import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("blk_io", ROOT / "tools/perf/blk-io.py")
blk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(blk)


class JailedApi(blk.OwnedVm):
    def __init__(self, inherit_root_group=False, extra_args=(), prepare=None, cli_args=None):
        folder = ROOT / ".perf/blk-io/jail-tests"
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        super().__init__(folder / f"{os.getpid()}-{time.time_ns()}", 8)
        self.binary = Path(os.environ.get(
            "FLINT_JAIL_TEST_BINARY", ROOT / "vmm/zig-out/bin/flint",
        )).resolve()
        self.inherit_root_group = inherit_root_group
        self.extra_args = extra_args
        self.prepare = prepare
        self.cli_args = cli_args

    def __enter__(self):
        try:
            self.path.mkdir(mode=0o700)
            self.path_created = True
            if self.prepare is not None:
                self.prepare(self)
            self.stdout = (self.path / "stdout.log").open("wb")
            self.stderr = (self.path / "stderr.log").open("wb")
            argv = [
                str(self.binary), "--jail", str(self.path),
                "--jail-uid", str(os.getuid()), "--jail-gid", str(os.getgid()),
                *(("--api-sock", "api.sock") if self.cli_args is None else self.cli_args),
                *self.extra_args,
            ]
            tracer = os.environ.get("FLINT_JAIL_TEST_STRACE")
            if tracer:
                argv = [tracer, "-f", "-o", str(self.path / "startup.strace"), *argv]
            if self.inherit_root_group:
                argv = ["setpriv", "--groups=0", "--", *argv]
            argv = ["sudo", "-n", "--", *argv]
            self.process = subprocess.Popen(
                argv, cwd=self.path, stdout=self.stdout, stderr=self.stderr,
                start_new_session=True,
            )
            blk.save_json(self.path / "launch.json", {
                "argv": argv, "supervisor_pid": self.process.pid,
                "binary_sha256": blk.sha256(self.binary), "artifact_umask": "077",
                "uid": os.getuid(), "gid": os.getgid(),
            })
            deadline = time.monotonic() + 10
            while self.cli_args is None and not (self.path / "api.sock").exists():
                if self.process.poll() is not None:
                    raise RuntimeError(f"jailed API exited: {self.process.returncode}")
                if time.monotonic() > deadline:
                    raise TimeoutError("jailed API socket did not become ready")
                time.sleep(0.02)
            while True:
                try:
                    self.pid = self.find_vm_pid()
                    break
                except RuntimeError:
                    if self.process.poll() is not None or time.monotonic() > deadline:
                        raise
                    time.sleep(0.02)
            blk.save_json(self.path / "pid.json", {"vmm_pid": self.pid})
            return self
        except BaseException:
            self.close()
            raise

    def close(self):
        try:
            super().close()
        finally:
            if self.path_created:
                subprocess.run(
                    ["sudo", "-n", "rm", "-f", "--", str(self.path / "dev/kvm")],
                    check=True, timeout=10,
                )
                dev = self.path / "dev"
                if dev.exists():
                    subprocess.run(
                        ["sudo", "-n", "rmdir", "--", str(dev)],
                        check=True, timeout=10,
                    )
                for pid in (self.pid, self.process.pid if self.process else None):
                    if pid is not None and Path(f"/proc/{pid}").exists():
                        raise RuntimeError(f"owned jailed process remains: {pid}")


class JailPrerequisites(unittest.TestCase):
    def setUp(self):
        if os.getuid() == 0:
            self.fail("run tests non-root; only the jail bootstrap uses sudo")
        self.old_umask = os.umask(0o077)
        self.addCleanup(os.umask, self.old_umask)

    def prepare_block_guest(self, vm, continuous=False):
        kernel = Path(os.environ.get("FLINT_JAIL_TEST_KERNEL", ROOT / ".ci/guest/bzImage"))
        self.assertEqual(blk.sha256(kernel), blk.KERNEL_HASH)
        shutil.copyfile(kernel, vm.path / "bzImage")
        root = vm.path / "initrd-root"
        root.mkdir(mode=0o700)
        (root / "bin").mkdir(mode=0o700)
        (root / "dev").mkdir(mode=0o700)
        shutil.copyfile("/usr/bin/busybox", root / "bin/busybox")
        (root / "bin/busybox").chmod(0o700)
        (root / "bin/sh").symlink_to("busybox")
        workload = (
            "i=0\nwhile :; do\n"
            "i=$((i+1))\n"
            "printf '%016d\\n' \"$i\" >/payload\n"
            "/bin/busybox dd if=/payload of=/dev/vda bs=512 conv=fsync\n"
            "echo APPLICATION_COUNTER=$i\n"
            "done\n"
        ) if continuous else (
            "/bin/busybox dd if=/dev/zero of=/dev/vda bs=131072 count=1 conv=fsync\n"
            "/bin/busybox dd if=/dev/vda of=/checked bs=131072 count=1\n"
            "/bin/busybox sha256sum /checked\n"
            "echo JAIL_BLOCK_WORKER_IO_OK\n"
            "while :; do /bin/busybox sleep 1; done\n"
        )
        (root / "init").write_text(
            "#!/bin/sh\nset -eu\n"
            "[ -c /dev/console ] || /bin/busybox mknod /dev/console c 5 1\n"
            "exec </dev/console >/dev/console 2>&1\n"
            "/bin/busybox mount -t devtmpfs devtmpfs /dev\n"
            "echo APPLICATION_INITIAL_BOOT\n" + workload
        )
        (root / "init").chmod(0o700)
        entries = [".", *(str(path.relative_to(root)) for path in sorted(root.rglob("*")))]
        with (vm.path / "cpio.log").open("wb") as errors, \
                (vm.path / "initrd.cpio.gz").open("wb") as output:
            pack = subprocess.Popen(
                ["bsdcpio", "-o", "-H", "newc", "--null"], cwd=root,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
            )
            compress = None
            try:
                compress = subprocess.Popen(["gzip", "-n"], stdin=pack.stdout, stdout=output)
                pack.stdout.close()
                pack.communicate(("\0".join(entries) + "\0").encode(), timeout=30)
                self.assertEqual(pack.returncode, 0)
                self.assertEqual(compress.wait(timeout=30), 0)
            finally:
                for child in (pack, compress):
                    if child is not None and child.poll() is None:
                        child.kill()
                        child.wait(timeout=5)
        (vm.path / "disk.raw").write_bytes(bytes([0xa3]) * (1024 * 1024))

    def start_block_api(self, vm, continuous=False):
        self.prepare_block_guest(vm, continuous)
        self.assertEqual(vm.api("PUT", "/drives/root", {
            "drive_id": "root", "path_on_host": "/disk.raw", "io_backend": "worker",
        }), b"")
        vm.api("PUT", "/boot-source", {
            "kernel_image_path": "/bzImage", "initrd_path": "/initrd.cpio.gz",
            "boot_args": "console=ttyS0 reboot=k panic=1 pci=off rdinit=/init",
        })
        vm.api("PUT", "/actions", {"action_type": "InstanceStart"})

    def check_block_guest(self, vm):
        deadline = time.monotonic() + 30
        while b"JAIL_BLOCK_WORKER_IO_OK" not in (vm.path / "stdout.log").read_bytes():
            self.assertIsNone(vm.process.poll(), "jailed block guest exited")
            self.assertLess(time.monotonic(), deadline, "jailed block guest never completed IO")
            time.sleep(0.02)
        expected = hashlib.sha256(bytes(131072)).hexdigest().encode()
        self.assertIn(expected, (vm.path / "stdout.log").read_bytes())
        self.assertEqual((vm.path / "disk.raw").read_bytes(),
                         bytes(131072) + bytes([0xa3]) * (1024 * 1024 - 131072))

    def boot_block_guest(self, vm):
        self.start_block_api(vm)
        self.check_block_guest(vm)

    def test_real_cli_worker_guest_io_under_enforced_jail(self):
        with JailedApi(inherit_root_group=True, prepare=self.prepare_block_guest, cli_args=(
            "/bzImage", "/initrd.cpio.gz",
            "--disk", "/disk.raw", "--block-backend", "worker",
            "--cmdline", "console=ttyS0 reboot=k panic=1 pci=off rdinit=/init",
        )) as vm:
            self.check_block_guest(vm)
            self.assertIn(b"effective=worker", (vm.path / "stderr.log").read_bytes())
            self.check_worker_identity(vm)

    def test_worker_pause_snapshot_and_fresh_api_restore_application_state(self):
        def counters(vm):
            return [int(line.split(b"=", 1)[1]) for line in
                    (vm.path / "stdout.log").read_bytes().split(b"\n")[:-1]
                    if line.startswith(b"APPLICATION_COUNTER=")]

        def await_counter(vm, minimum):
            deadline = time.monotonic() + 30
            while not counters(vm) or counters(vm)[-1] < minimum:
                self.assertIsNone(vm.process.poll())
                self.assertLess(time.monotonic(), deadline, "application state did not progress")
                time.sleep(0.01)

        with JailedApi(inherit_root_group=True) as original:
            self.start_block_api(original, continuous=True)
            await_counter(original, 3)
            self.assertIn(b"effective=worker", (original.path / "stderr.log").read_bytes())
            for _ in range(3):
                original.api("PATCH", "/vm", {"state": "Paused"})
                paused = (original.path / "disk.raw").read_bytes()
                time.sleep(0.03)
                self.assertEqual((original.path / "disk.raw").read_bytes(), paused)
                original.api("PATCH", "/vm", {"state": "Resumed"})
            original.api("PATCH", "/vm", {"state": "Paused"})
            before = counters(original)[-1]
            disk = (original.path / "disk.raw").read_bytes()
            self.assertGreaterEqual(int(disk[:16]), before)
            original.api("PUT", "/snapshot/create", {
                "snapshot_path": "worker.vmstate", "mem_file_path": "worker.mem",
            })
            def copy_state(vm):
                for name in ("worker.vmstate", "worker.mem", "disk.raw"):
                    shutil.copyfile(original.path / name, vm.path / name)
            with JailedApi(inherit_root_group=True, prepare=copy_state) as restored:
                restored.api("PUT", "/drives/root", {
                    "drive_id": "root", "path_on_host": "/disk.raw", "io_backend": "worker",
                })
                restored.api("PUT", "/snapshot/load", {
                    "snapshot_path": "worker.vmstate", "mem_file_path": "worker.mem",
                })
                restored.api("PUT", "/actions", {"action_type": "InstanceStart"})
                await_counter(restored, before + 2)
                self.assertIn(b"effective=worker", (restored.path / "stderr.log").read_bytes())
                self.check_worker_identity(restored)
                self.assertNotIn(b"APPLICATION_INITIAL_BOOT",
                                 (restored.path / "stdout.log").read_bytes())
                restored.api("PATCH", "/vm", {"state": "Paused"})
                self.assertGreater(int((restored.path / "disk.raw").read_bytes()[:16]), before)
                blk.save_json(restored.path / "application-restore.json", {
                    "saved_counter": before, "restored_counters": counters(restored),
                    "initial_boot_not_reexecuted": True,
                })
            with JailedApi(inherit_root_group=True, prepare=copy_state, cli_args=(
                "--restore", "--vmstate-path", "/worker.vmstate", "--mem-path", "/worker.mem",
                "--disk", "/disk.raw", "--block-backend", "worker",
            )) as restored_cli:
                await_counter(restored_cli, before + 2)
                self.assertNotIn(b"APPLICATION_INITIAL_BOOT",
                                 (restored_cli.path / "stdout.log").read_bytes())
                self.assertGreater(int((restored_cli.path / "disk.raw").read_bytes()[:16]), before)
                self.assertIn(b"effective=worker", (restored_cli.path / "stderr.log").read_bytes())
                self.check_worker_identity(restored_cli)
                blk.save_json(restored_cli.path / "application-restore.json", {
                    "saved_counter": before, "restored_counters": counters(restored_cli),
                    "initial_boot_not_reexecuted": True, "mode": "CLI",
                })

    def test_real_api_worker_io_inherits_enforced_jail_and_private_identity(self):
        with JailedApi(inherit_root_group=True) as vm:
            self.boot_block_guest(vm)
            self.assertIn(b"effective=worker", (vm.path / "stderr.log").read_bytes())
            self.check_worker_identity(vm)

    def check_worker_identity(self, vm):
        tids = subprocess.check_output(
            ["sudo", "-n", "ls", f"/proc/{vm.pid}/task"], text=True).split()
        roster = []
        for tid in tids:
            status = subprocess.check_output(
                ["sudo", "-n", "cat", f"/proc/{vm.pid}/task/{tid}/status"], text=True)
            fields = dict(line.split(":", 1) for line in status.splitlines() if ":" in line)
            self.assertEqual(fields["Uid"].split(), [str(os.getuid())] * 4)
            self.assertEqual(fields["Gid"].split(), [str(os.getgid())] * 4)
            self.assertEqual(fields["Groups"].split(), [])
            self.assertEqual(fields["Seccomp"].strip(), "2")
            self.assertEqual(fields["NoNewPrivs"].strip(), "1")
            self.assertEqual(int(fields["CapEff"], 16), 0)
            roster.append({"tid": int(tid), "status": status})
        blk.save_json(vm.path / "checked-worker-roster.json", roster)

    def test_force_sync_overrides_api_worker_before_admission(self):
        with JailedApi(extra_args=("--force-sync",)) as vm:
            self.boot_block_guest(vm)
            self.assertNotIn(b"effective=worker", (vm.path / "stderr.log").read_bytes())
            self.assertIn(b"force_sync=true", (vm.path / "stderr.log").read_bytes())

    def test_private_umask_keeps_directory_traversable_and_device_owner_only(self):
        host = Path("/dev/kvm").stat()
        with JailedApi() as vm:
            directory = (vm.path / "dev").stat()
            device = (vm.path / "dev/kvm").stat()
            observed = {
                "directory": {"uid": directory.st_uid, "gid": directory.st_gid,
                              "mode": oct(stat.S_IMODE(directory.st_mode))},
                "device": {"uid": device.st_uid, "gid": device.st_gid,
                           "mode": oct(stat.S_IMODE(device.st_mode))},
            }
            blk.save_json(vm.path / "permissions.json", observed)
            self.assertEqual((directory.st_uid, directory.st_gid), (0, 0))
            self.assertEqual(stat.S_IMODE(directory.st_mode), 0o755)
            self.assertTrue(stat.S_ISCHR(device.st_mode))
            self.assertEqual((device.st_uid, device.st_gid), (os.getuid(), os.getgid()))
            self.assertEqual(stat.S_IMODE(device.st_mode), 0o600)
            fd = os.open(vm.path / "dev/kvm", os.O_RDWR | os.O_CLOEXEC)
            try:
                self.assertEqual(fcntl.ioctl(fd, 0xAE00, 0), 12)
            finally:
                os.close(fd)
            self.assertEqual(os.umask(0o077), 0o077)
        after = Path("/dev/kvm").stat()
        self.assertEqual(
            (after.st_dev, after.st_ino, after.st_uid, after.st_gid, after.st_mode),
            (host.st_dev, host.st_ino, host.st_uid, host.st_gid, host.st_mode),
        )

    def test_real_api_receive_and_send_under_kill_filter_after_uid_drop(self):
        with JailedApi(inherit_root_group=True) as vm:
            status = subprocess.check_output(
                ["sudo", "-n", "cat", f"/proc/{vm.pid}/status"], text=True,
            )
            (vm.path / "process-status.txt").write_text(status)
            fields = dict(line.split(":", 1) for line in status.splitlines() if ":" in line)
            self.assertEqual(list(map(int, fields["Uid"].split())), [os.getuid()] * 4)
            self.assertEqual(list(map(int, fields["Gid"].split())), [os.getgid()] * 4)
            self.assertEqual(fields["Groups"].split(), [])
            self.assertEqual(int(fields["CapEff"].strip(), 16), 0)
            self.assertEqual(fields["NoNewPrivs"].strip(), "1")
            self.assertEqual(fields["Seccomp"].strip(), "2")
            self.assertIn(b"seccomp filter installed", (vm.path / "stderr.log").read_bytes())
            replies = []
            for memory in (512, 640, 512):
                self.assertEqual(vm.api("PUT", "/machine-config", {"mem_size_mib": memory}), b"")
                response = json.loads(vm.api("GET", "/machine-config"))
                self.assertEqual(response, {"mem_size_mib": memory, "vcpu_count": 1})
                replies.append(response)
            blk.save_json(vm.path / "checked-api-replies.json", replies)

    def test_real_api_boots_guest_under_enforced_thread_and_epoll_filters(self):
        kernel = Path(os.environ.get("FLINT_JAIL_TEST_KERNEL", ROOT / ".ci/guest/bzImage"))
        self.assertEqual(blk.sha256(kernel), blk.KERNEL_HASH)
        with JailedApi() as vm:
            shutil.copyfile(kernel, vm.path / "bzImage")
            root = vm.path / "initrd-root"
            root.mkdir(mode=0o700)
            (root / "bin").mkdir(mode=0o700)
            (root / "dev").mkdir(mode=0o700)
            shutil.copyfile("/usr/bin/busybox", root / "bin/busybox")
            (root / "bin/busybox").chmod(0o700)
            (root / "bin/sh").symlink_to("busybox")
            (root / "init").write_text(
                "#!/bin/sh\nset -eu\n"
                "[ -c /dev/console ] || /bin/busybox mknod /dev/console c 5 1\n"
                "exec </dev/console >/dev/console 2>&1\n"
                "echo JAIL_GUEST_BOOT_OK\n"
                "while :; do /bin/busybox sleep 1; done\n"
            )
            (root / "init").chmod(0o700)
            entries = [".", *(str(path.relative_to(root)) for path in sorted(root.rglob("*")))]
            with (vm.path / "cpio.log").open("wb") as errors, \
                    (vm.path / "initrd.cpio.gz").open("wb") as output:
                pack = subprocess.Popen(
                    ["bsdcpio", "-o", "-H", "newc", "--null"], cwd=root,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
                )
                compress = None
                try:
                    compress = subprocess.Popen(["gzip", "-n"], stdin=pack.stdout, stdout=output)
                    pack.stdout.close()
                    pack.communicate(("\0".join(entries) + "\0").encode(), timeout=30)
                    self.assertEqual(pack.returncode, 0)
                    self.assertEqual(compress.wait(timeout=30), 0)
                finally:
                    for child in (pack, compress):
                        if child is not None and child.poll() is None:
                            child.kill()
                            child.wait(timeout=5)
            vm.api("PUT", "/boot-source", {
                "kernel_image_path": "/bzImage", "initrd_path": "/initrd.cpio.gz",
                "boot_args": "console=ttyS0 reboot=k panic=1 pci=off rdinit=/init",
            })
            vm.api("PUT", "/actions", {"action_type": "InstanceStart"})
            deadline = time.monotonic() + 15
            while b"JAIL_GUEST_BOOT_OK" not in (vm.path / "stdout.log").read_bytes():
                self.assertIsNone(vm.process.poll(), "jailed guest process exited")
                self.assertLess(time.monotonic(), deadline, "jailed guest never reached userspace")
                time.sleep(0.05)


if __name__ == "__main__":
    unittest.main()
