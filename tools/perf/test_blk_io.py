import importlib.util
from pathlib import Path
import subprocess
import socket
import struct
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location("blk_io", Path(__file__).with_name("blk-io.py"))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FragmentedConnection:
    def __init__(self, *parts):
        self.parts = list(parts)

    def recv(self, length):
        if not self.parts:
            return b""
        part = self.parts.pop(0)
        if len(part) > length:
            self.parts.insert(0, part[length:])
        return part[:length]


class ProtocolTests(unittest.TestCase):
    def test_fragmented_header_and_payload(self):
        payload = b'{"ok":true}'
        prefix = struct.pack("<I", len(payload))
        connection = FragmentedConnection(prefix[:1], prefix[1:3], prefix[3:],
                                          payload[:3], payload[3:])
        self.assertEqual(MODULE.receive_frame(connection), {"ok": True})

    def test_truncated_payload_is_not_success(self):
        connection = FragmentedConnection(struct.pack("<I", 10), b"{}")
        with self.assertRaises(ConnectionError):
            MODULE.receive_frame(connection)

    def test_oversized_header_is_rejected_before_reading_payload(self):
        connection = FragmentedConnection(struct.pack("<I", MODULE.MAX_FRAME + 1), b"unread")
        with self.assertRaises(ValueError):
            MODULE.receive_frame(connection)
        self.assertEqual(connection.parts, [b"unread"])

    def test_send_and_receive_roundtrip(self):
        sender, receiver = socket.socketpair()
        with sender, receiver:
            MODULE.send_frame(sender, {"method": "ping"})
            self.assertEqual(MODULE.receive_frame(receiver), {"method": "ping"})

    def test_exec_uses_existing_method_field(self):
        class Agent:
            data = b""

            def sendall(self, data):
                self.data += data

        vm = MODULE.OwnedVm(Path("."), 8)
        vm.agent = Agent()
        original = MODULE.receive_frame
        try:
            MODULE.receive_frame = lambda _: {
                "ok": True, "exit_code": 0, "stdout": "bWFya2VyCg==", "stderr": "",
            }
            response = vm.command("echo marker")
        finally:
            MODULE.receive_frame = original
        connection = FragmentedConnection(vm.agent.data)
        self.assertEqual(MODULE.receive_frame(connection),
                         {"method": "exec", "cmd": "echo marker", "timeout": 10})
        self.assertEqual(response["stdout"], "marker\n")

    def test_failed_guest_exit_is_not_counted_as_passing(self):
        vm = MODULE.OwnedVm(Path("."), 8)
        sender, receiver = socket.socketpair()
        with sender, receiver:
            vm.agent = sender
            MODULE.send_frame(receiver, {"ok": True, "exit_code": 1})
            with self.assertRaises(RuntimeError):
                vm.command("false")

    def test_failed_directory_creation_does_not_clean_existing_run(self):
        existing = mock.MagicMock(spec=Path)
        existing.mkdir.side_effect = FileExistsError("existing evidence")
        vm = MODULE.OwnedVm(existing, 8)
        with self.assertRaises(FileExistsError):
            vm.__enter__()
        existing.__truediv__.assert_not_called()


class PerfCacheTests(unittest.TestCase):
    def test_insecure_existing_cache_is_rejected_without_changing_permissions(self):
        root = MODULE.ARTIFACTS / "perf-cache-tests/insecure"
        root.mkdir(mode=0o700, parents=True)
        cache = root / "perf-buildid-cache"
        cache.mkdir(mode=0o700)
        cache.chmod(0o755)
        try:
            with mock.patch.object(MODULE, "ARTIFACTS", root):
                with self.assertRaises(PermissionError):
                    MODULE.privileged_perf(["stat", "--", "true"])
            self.assertEqual(cache.stat().st_mode & 0o777, 0o755)
        finally:
            cache.rmdir()
            root.rmdir()

    def test_symlink_cache_is_rejected_without_touching_its_target(self):
        root = MODULE.ARTIFACTS / "perf-cache-tests/symlink"
        root.mkdir(mode=0o700, parents=True)
        target = root / "target"
        target.mkdir(mode=0o700)
        target.chmod(0o755)
        cache = root / "perf-buildid-cache"
        cache.symlink_to(target, target_is_directory=True)
        try:
            with mock.patch.object(MODULE, "ARTIFACTS", root):
                with self.assertRaises(ValueError):
                    MODULE.privileged_perf(["record", "--", "true"])
            self.assertEqual(target.stat().st_mode & 0o777, 0o755)
        finally:
            cache.unlink()
            target.rmdir()
            root.rmdir()


class PreparedImageTests(unittest.TestCase):
    def test_failed_exit_evidence_still_removes_owned_sockets(self):
        paths = {name: mock.Mock() for name in ("exit.json", "api.sock", "vsock_1024")}
        path = mock.MagicMock(spec=Path)
        path.__truediv__.side_effect = paths.__getitem__
        vm = MODULE.OwnedVm(path, 8, jailed=False)
        vm.path_created = True
        vm.process = mock.Mock()
        vm.process.poll.return_value = 0
        with mock.patch.object(MODULE, "save_json", side_effect=OSError("No space left on device")):
            with self.assertRaisesRegex(OSError, "No space left"):
                vm.close()
        for name in ("api.sock", "vsock_1024"):
            paths[name].unlink.assert_called_once_with(missing_ok=True)

    def test_copy_fence_precedes_launch(self):
        path = mock.MagicMock(spec=Path)
        events = []
        vm = MODULE.OwnedVm(path, 8, jailed=False, sync_fixture=True)
        def stop_before_vm(*args, **kwargs):
            events.append("spawn")
            raise OSError("stop before VM")

        with mock.patch.object(MODULE.subprocess, "run"), \
                mock.patch.object(MODULE.socket, "socket"), \
                mock.patch.object(MODULE, "fence_prepared_image",
                                  side_effect=lambda _: events.append("fence")), \
                mock.patch.object(MODULE.subprocess, "Popen",
                                  side_effect=stop_before_vm):
            with self.assertRaisesRegex(OSError, "stop before VM"):
                vm.__enter__()
        self.assertEqual(events, ["fence", "spawn"])

    def test_copy_fence_failure_never_launches(self):
        path = mock.MagicMock(spec=Path)
        vm = MODULE.OwnedVm(path, 8, jailed=False, sync_fixture=True)
        with mock.patch.object(MODULE.subprocess, "run"), \
                mock.patch.object(MODULE, "fence_prepared_image",
                                  side_effect=OSError("owned copy sync failed")), \
                mock.patch.object(MODULE.subprocess, "Popen") as spawn:
            with self.assertRaisesRegex(OSError, "owned copy sync failed"):
                vm.__enter__()
            spawn.assert_not_called()

    def test_stale_recorded_pid_is_not_signaled(self):
        process = subprocess.Popen(
            [MODULE.sys.executable, "-I", "-B", "-S", "-c", "import time; time.sleep(60)"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        stamp = MODULE.start_time(process.pid)
        try:
            self.assertFalse(MODULE.signal_owned_pid(process.pid, stamp + 1, 15))
            self.assertIsNone(process.poll())
        finally:
            MODULE.signal_owned_pid(process.pid, stamp, 15)
            process.wait(timeout=5)

    def test_recorded_owned_pidfd_signal_is_delivered(self):
        process = subprocess.Popen(
            [MODULE.sys.executable, "-I", "-B", "-S", "-c", "import time; time.sleep(60)"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        stamp = MODULE.start_time(process.pid)
        try:
            self.assertTrue(MODULE.signal_owned_pid(process.pid, stamp, 15))
            self.assertEqual(process.wait(timeout=5), -15)
        finally:
            if process.poll() is None:
                MODULE.signal_owned_pid(process.pid, stamp, 9)
                process.wait(timeout=5)

if __name__ == "__main__":
    unittest.main()
