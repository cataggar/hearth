import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import collect
import runner


class FragmentedSocket:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.sent = b""

    def recv(self, size):
        if not self.chunks:
            return b""
        data = self.chunks.pop(0)
        if len(data) > size:
            self.chunks.insert(0, data[size:])
        return data[:size]

    def sendall(self, data):
        self.sent += data


class CollectorTests(unittest.TestCase):
    def test_profile_gate_eof_does_not_start_workload(self):
        read_fd, write_fd = os.pipe2(os.O_CLOEXEC)
        os.close(write_fd)
        with self.assertRaisesRegex(ValueError, "barrier was not released"):
            collect.wait_for_profile(read_fd)
        with self.assertRaises(OSError):
            os.fstat(read_fd)

    def test_partial_reads_and_early_eof(self):
        self.assertEqual(collect.receive(FragmentedSocket([b"a", b"bc", b"def"]), 6), b"abcdef")
        with self.assertRaises(ConnectionError):
            collect.receive(FragmentedSocket([b"abc"]), 4)

    def test_rpc_validates_sequence_and_payload(self):
        sequence = 257
        expected = sequence.to_bytes(8, "little") + bytes((sequence + i) % 256 for i in range(56))
        sock = FragmentedSocket([expected[:7], expected[7:]])
        self.assertEqual(collect.transaction(sock, "rpc", sequence), 64)
        self.assertEqual(sock.sent, expected)
        with self.assertRaisesRegex(ValueError, "mismatch"):
            collect.transaction(FragmentedSocket([bytes(64)]), "rpc", sequence)

    def test_busy_cpu_omits_idle_iowait_and_guest_double_count(self):
        stat = "cpu 100 20 30 400 50 6 7 8 90 10\ncpu0 0 0 0 0\n"
        self.assertEqual(collect.busy_ticks(stat), 163)
        with self.assertRaises(ValueError):
            collect.busy_ticks("cpu 1 2")

    def test_empty_samples_have_no_invented_percentiles(self):
        self.assertEqual(collect.percentiles([]), {"p50": None, "p95": None, "p99": None})
        self.assertEqual(collect.percentiles([4, 1, 2, 3]), {"p50": 2, "p95": 4, "p99": 4})

    def test_active_timeout_retains_successful_prefix_and_correct_denominators(self):
        args = SimpleNamespace(
            mode="rpc", host="192.0.2.2", timeout_seconds=3,
            warmup_seconds=0, seconds=60, idle_seconds=1,
            backend="vhost", notification="common blocked-poll",
        )
        cpu = [
            {"busy_ticks": ticks, "clock_ticks_per_second": 100}
            for ticks in (100, 101, 110, 111)
        ]
        connection = MagicMock()
        with (
            patch.object(collect.socket, "create_connection", return_value=connection),
            patch.object(collect, "cpu_snapshot", side_effect=cpu),
            patch.object(collect.time, "monotonic", side_effect=[0, 0, 0, 0, 0, 0, 1, 1]),
            patch.object(collect, "transaction", side_effect=[64, TimeoutError("test timeout")]),
        ):
            result = collect.run(args)
        self.assertEqual(result["attempted_active_requests"], 2)
        self.assertEqual(result["successful_requests"], 1)
        self.assertEqual(result["payload_bytes_one_direction"], 64)
        self.assertEqual(result["errors"][0]["phase"], "active")
        self.assertEqual(result["active_seconds"], 1)
        self.assertEqual(result["active_whole_host_cpu_seconds_per_request"], 0.09)
        self.assertEqual(result["active_whole_host_cpu_seconds_per_payload_byte"], 0.09 / 64)
        self.assertEqual(result["backend"], "vhost")
        self.assertEqual(result["notification"], "common blocked-poll")

    def test_fixed_rate_does_not_send_beyond_active_window(self):
        args = SimpleNamespace(
            mode="rpc", host="192.0.2.2", timeout_seconds=3, warmup_seconds=0,
            seconds=0.12, idle_seconds=1, rpc_rate=20,
        )
        clock = [0.0]
        calls = []
        def advance(seconds):
            clock[0] += seconds
        def transact(_sock, _mode, sequence):
            calls.append((sequence, clock[0]))
            advance(0.01)
            return 64
        cpu = {"busy_ticks": 0, "clock_ticks_per_second": 100}
        with (
            patch.object(collect.socket, "create_connection", return_value=MagicMock()),
            patch.object(collect, "cpu_snapshot", return_value=cpu),
            patch.object(collect.time, "monotonic", side_effect=lambda: clock[0]),
            patch.object(collect.time, "sleep", side_effect=advance),
            patch.object(collect, "transaction", side_effect=transact),
        ):
            result = collect.run(args)
        self.assertEqual(calls, [(0, 0), (1, 0.05), (2, 0.1)])
        self.assertAlmostEqual(result["active_seconds"], 0.12)
        self.assertEqual(result["successful_requests"], 3)


class RunnerTests(unittest.TestCase):
    def test_partial_profile_pipe_setup_unwinds_all_descriptors(self):
        before = len(list(Path("/proc/self/fd").iterdir()))
        real_pipe = os.pipe2
        calls = []
        def create_pipe(flags):
            if calls:
                raise OSError("owned pipe limit")
            calls.append(True)
            return real_pipe(flags)
        with patch.object(runner.os, "pipe2", side_effect=create_pipe):
            with self.assertRaisesRegex(OSError, "owned pipe limit"):
                runner.scoped_profile(Path("."), 1, "rpc", "fixture", 1, 0, "stat")
        self.assertEqual(before, len(list(Path("/proc/self/fd").iterdir())))

    def test_vm_is_stopped_if_post_spawn_metadata_fails(self):
        child = MagicMock()
        child.poll.return_value = None
        with (
            patch.object(runner, "private_directory"),
            patch.object(runner, "freeze_tools"),
            patch.object(runner, "setup_tap"),
            patch.object(runner, "owned_file"),
            patch.object(runner.Path, "open", return_value=MagicMock()),
            patch.object(runner.subprocess, "Popen", return_value=child),
            patch.object(runner.os, "chown", side_effect=PermissionError("test metadata failure")),
        ):
            with self.assertRaisesRegex(PermissionError, "test metadata failure"):
                runner.boot(SimpleNamespace(artifact_dir=Path(".")), Path("."))
        child.terminate.assert_called_once_with()
        child.wait.assert_called_once_with(timeout=5)


if __name__ == "__main__":
    unittest.main()
