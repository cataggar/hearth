import importlib.util
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
