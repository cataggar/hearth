import errno
import os
import time
import unittest
from pathlib import Path
from unittest import mock

import runner
import lifecycle_fault


class RunnerFixtures(unittest.TestCase):
    def test_failed_snapshot_compaction_keeps_source_and_removes_partial_copy(self):
        previous = os.umask(0o077)
        directory = runner.ROOT / ".perf/vhost-net/unit-fixtures" / f"{os.getpid()}-{time.time_ns()}"
        directory.mkdir(parents=True, mode=0o700)
        source = directory / "snapshot.mem"
        target = directory / "snapshot.mem.sparse-correctness"
        payload = b"frozen-snapshot" + bytes(8192)
        source.write_bytes(payload)
        def partial_copy(_source, output):
            output.write_bytes(b"partial")
            raise OSError(errno.ENOSPC, "owned sparse evidence full")
        try:
            with mock.patch.object(runner, "sparse_copy", side_effect=partial_copy):
                with self.assertRaises(OSError):
                    runner.compact_correctness_snapshot(source)
            self.assertEqual(source.read_bytes(), payload)
            self.assertFalse(target.exists())
        finally:
            target.unlink(missing_ok=True)
            source.unlink()
            directory.rmdir()
            os.umask(previous)

    def test_lifecycle_rejection_distinguishes_ack_decline_and_fatal_disconnect(self):
        for response, acknowledged in (
            ("HTTP/1.1 204 No Content", True),
            (RuntimeError('HTTP/1.1 400 Bad Request\r\n{"fault_message":"VM has exited"}'), False),
            (ConnectionRefusedError("owned fatal exit"), False),
        ):
            with self.subTest(response=response):
                with mock.patch.object(runner, "request", **(
                    {"side_effect": response} if isinstance(response, Exception)
                    else {"return_value": response}
                )):
                    self.assertEqual(lifecycle_fault.rejection(
                        Path("owned.sock"), "PATCH", "/vm", {"state": "Paused"})["acknowledged"],
                        acknowledged)

    def test_lifecycle_timeout_and_unrecognized_response_are_not_rejection_proof(self):
        for error in (TimeoutError("not joined"), RuntimeError("")):
            with self.subTest(error=error):
                with mock.patch.object(runner, "request", side_effect=error):
                    with self.assertRaises(type(error)):
                        lifecycle_fault.rejection(Path("owned.sock"), "PATCH", "/vm", {})

    def test_sparse_copy_keeps_zero_tail_and_nonzero_payload(self):
        previous = os.umask(0o077)
        directory = runner.ROOT / ".perf/vhost-net/unit-fixtures" / f"{os.getpid()}-{time.time_ns()}"
        directory.mkdir(parents=True, mode=0o700)
        source, target = directory / "source", directory / "copy"
        try:
            payload = bytes(8192) + b"owned-payload" * 1000 + bytes(8192) + bytes(17)
            source.write_bytes(payload)
            runner.sparse_copy(source, target)
            self.assertEqual(target.read_bytes(), payload)
            with self.assertRaises(FileExistsError):
                runner.sparse_copy(source, target)
        finally:
            target.unlink(missing_ok=True)
            source.unlink(missing_ok=True)
            directory.rmdir()
            os.umask(previous)

    def test_evidence_enospc_cannot_prevent_empty_jail_resource_cleanup(self):
        layout = object.__new__(runner.JailedLayout)
        layout.directory = Path("unused-owned-output")
        layout.cgroup = mock.MagicMock()
        fields = {
            "pids.current": "0", "cgroup.procs": "",
            "memory.current": "4096", "cpu.stat": "usage_usec 1\n",
        }
        layout.cgroup.__truediv__.side_effect = lambda name: mock.Mock(
            read_text=mock.Mock(return_value=fields[name]))
        layout.root = mock.MagicMock()
        nodes = {}
        layout.root.__truediv__.side_effect = lambda name: nodes.setdefault(name, mock.MagicMock())
        with mock.patch.object(runner, "owned_file", side_effect=OSError(errno.ENOSPC, "owned evidence full")):
            with self.assertRaises(OSError):
                layout.close()
        layout.cgroup.rmdir.assert_called_once()
        for name in ("dev/vhost-net", "dev/net/tun", "dev/kvm", "api.sock"):
            nodes[name].unlink.assert_called_once()
        nodes["dev/net"].rmdir.assert_called_once()
        nodes["dev"].rmdir.assert_called_once()
