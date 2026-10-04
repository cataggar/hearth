"""Real enforced-jail regressions; run non-root under the fleet host lock.

Requires sudo -n mount/jail bootstrap and functional /dev/kvm. No skips.
FLINT_JAIL_TEST_BINARY selects the compiled binary; FLINT_JAIL_TEST_STRACE
optionally retains its actual enforced-filter trace.
"""

import fcntl
import json
import os
from pathlib import Path
import stat
import subprocess
import time
import unittest
from unittest.mock import patch

import jail_support

ROOT = Path(__file__).resolve().parents[2]


class JailedApi(jail_support.OwnedVm):
    def __init__(self):
        folder = ROOT / ".perf/jail-tests"
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        super().__init__(folder / f"{os.getpid()}-{time.time_ns()}")
        self.binary = Path(os.environ.get(
            "FLINT_JAIL_TEST_BINARY", ROOT / "vmm/zig-out/bin/flint",
        )).resolve()

    def __enter__(self):
        try:
            self.path.mkdir(mode=0o700)
            self.path_created = True
            self.stdout = (self.path / "stdout.log").open("wb")
            self.stderr = (self.path / "stderr.log").open("wb")
            argv = [
                str(self.binary), "--jail", str(self.path),
                "--jail-uid", str(os.getuid()), "--jail-gid", str(os.getgid()),
                "--api-sock", "api.sock",
            ]
            tracer = os.environ.get("FLINT_JAIL_TEST_STRACE")
            if tracer:
                argv = [tracer, "-f", "-o", str(self.path / "startup.strace"), *argv]
            argv = ["sudo", "-n", "--", *argv]
            self.process = subprocess.Popen(
                argv, cwd=self.path, stdout=self.stdout, stderr=self.stderr,
                start_new_session=True,
            )
            jail_support.save_json(self.path / "launch.json", {
                "argv": argv, "supervisor_pid": self.process.pid,
                "binary_sha256": jail_support.sha256(self.binary), "artifact_umask": "077",
                "uid": os.getuid(), "gid": os.getgid(),
            })
            deadline = time.monotonic() + 10
            while not (self.path / "api.sock").exists():
                if self.process.poll() is not None:
                    raise RuntimeError(f"jailed API exited: {self.process.returncode}")
                if time.monotonic() > deadline:
                    raise TimeoutError("jailed API socket did not become ready")
                time.sleep(0.02)
            self.pid = self.find_vm_pid()
            self.pid_start_ticks = jail_support.start_ticks(self.pid)
            jail_support.save_json(self.path / "pid.json", {"vmm_pid": self.pid})
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
            jail_support.save_json(vm.path / "permissions.json", observed)
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
        with JailedApi() as vm:
            status = subprocess.check_output(
                ["sudo", "-n", "cat", f"/proc/{vm.pid}/status"], text=True,
            )
            (vm.path / "process-status.txt").write_text(status)
            fields = dict(line.split(":", 1) for line in status.splitlines() if ":" in line)
            self.assertEqual(list(map(int, fields["Uid"].split())), [os.getuid()] * 4)
            self.assertEqual(list(map(int, fields["Gid"].split())), [os.getgid()] * 4)
            self.assertFalse(fields["Groups"].strip())
            self.assertEqual(fields["CapEff"].strip(), "0000000000000000")
            self.assertEqual(fields["NoNewPrivs"].strip(), "1")
            self.assertEqual(fields["Seccomp"].strip(), "2")
            self.assertIn(b"seccomp filter installed", (vm.path / "stderr.log").read_bytes())
            replies = []
            for memory in (512, 640, 512):
                self.assertEqual(vm.api("PUT", "/machine-config", {"mem_size_mib": memory}), b"")
                response = json.loads(vm.api("GET", "/machine-config"))
                self.assertEqual(response, {"mem_size_mib": memory, "vcpu_count": 1})
                replies.append(response)
            jail_support.save_json(vm.path / "checked-api-replies.json", replies)


class OwnedCleanup(unittest.TestCase):
    def fixture(self):
        class Supervisor:
            pid = 999
            returncode = None
            kill_called = False

            def poll(self):
                return self.returncode

            def terminate(self):
                self.returncode = -15

            def kill(self):
                self.kill_called = True
                self.returncode = -9

            def wait(self, timeout):
                if self.returncode is None:
                    raise subprocess.TimeoutExpired("owned-supervisor", timeout)
                return self.returncode

        vm = jail_support.OwnedVm(ROOT / ".perf")
        vm.process = Supervisor()
        vm.pid, vm.pid_start_ticks = 123, 10
        return vm

    def test_reused_vmm_pid_is_never_signalled(self):
        vm = self.fixture()
        with patch.object(vm, "find_vm_pid", return_value=123), \
                patch.object(jail_support, "start_ticks", return_value=20), \
                patch.object(jail_support, "save_json"), \
                patch.object(jail_support.subprocess, "run") as signal:
            vm.close()
        signal.assert_not_called()
        self.assertEqual(vm.process.returncode, -15)

    def test_pid_generation_is_rechecked_before_kill_escalation(self):
        vm = self.fixture()
        with patch.object(vm, "find_vm_pid", return_value=123), \
                patch.object(jail_support, "start_ticks", side_effect=[10, 20]), \
                patch.object(jail_support, "save_json"), \
                patch.object(jail_support.subprocess, "run") as signal:
            vm.close()
        self.assertEqual(signal.call_count, 1)
        self.assertEqual(signal.call_args.args[0], ["sudo", "-n", "kill", "-TERM", "123"])
        self.assertTrue(vm.process.kill_called)


if __name__ == "__main__":
    unittest.main()
