import importlib.util
import contextlib
import io
import json
from pathlib import Path
import shutil
import socket
import struct
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("eventfd_runner", Path(__file__).with_name("run.py"))
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class EvidenceTests(unittest.TestCase):
    def test_newc_alignment_and_contents(self):
        for name, data in (("init", b"#!/bin/sh\n"), ("a", b""), ("bin/sh", b"busybox")):
            archive = RUNNER.newc_entry(name, data, 0o100755, 1)
            self.assertEqual(archive[:6], b"070701")
            fields = [int(archive[6 + i * 8 : 14 + i * 8], 16) for i in range(13)]
            self.assertEqual(fields[6], len(data))
            self.assertEqual(fields[11], len(name) + 1)
            self.assertEqual(archive[110 : 110 + fields[11]], name.encode() + b"\0")
            data_offset = (110 + fields[11] + 3) & ~3
            self.assertEqual(archive[data_offset : data_offset + len(data)], data)
            self.assertEqual(len(archive) % 4, 0)

    def test_cpu_accounting_includes_every_thread(self):
        before = [
            {"tid": 1, "utime_ticks": 1, "stime_ticks": 2},
            {"tid": 2, "utime_ticks": 5, "stime_ticks": 8},
        ]
        after = [
            {"tid": 1, "utime_ticks": 3, "stime_ticks": 7},
            {"tid": 2, "utime_ticks": 9, "stime_ticks": 11},
        ]
        self.assertEqual(RUNNER.cpu_delta(before, after), 14 / RUNNER.os.sysconf("SC_CLK_TCK"))

    def test_thread_roster_changes_invalidate_cpu_sample(self):
        before = [{"tid": 1, "utime_ticks": 0, "stime_ticks": 0}]
        with self.assertRaisesRegex(ValueError, "roster changed"):
            RUNNER.cpu_delta(before, [])
        with self.assertRaisesRegex(ValueError, "roster changed"):
            RUNNER.cpu_delta([], before)

    def test_framed_response_integrity(self):
        client, peer = socket.socketpair()
        with client, peer:
            response = b'{"ok":true}'
            peer.sendall(struct.pack("<I", len(response)) + response)
            self.assertEqual(RUNNER.rpc(client, {"method": "ping"}), {"ok": True})
            frame_size = struct.unpack("<I", RUNNER.recv_exact(peer, 4))[0]
            self.assertIn(b'"method": "ping"', RUNNER.recv_exact(peer, frame_size))

    def test_closed_and_oversized_responses_fail(self):
        client, peer = socket.socketpair()
        with client, peer:
            peer.sendall(struct.pack("<I", 16 * 1024 * 1024 + 1))
            with self.assertRaisesRegex(ValueError, "oversized"):
                RUNNER.rpc(client, {"method": "ping"})
        client, peer = socket.socketpair()
        with client:
            peer.close()
            with self.assertRaises(EOFError):
                RUNNER.recv_exact(client, 4)

    def test_native_integrity_failure_is_not_a_completed_operation(self):
        client, peer = socket.socketpair()
        with client, peer:
            payload = RUNNER.native_payload(44, 16)
            peer.sendall(struct.pack("<I", len(payload) + 8) + b"\0" * 8 + b"x" * len(payload))
            with self.assertRaisesRegex(ValueError, "sequence/payload/checksum mismatch"):
                RUNNER.native_reply(client, 44, payload)

    def test_backpressure_failure_joins_sender_after_shutdown_error(self):
        released = threading.Event()

        class ClosedPeer:
            def sendall(self, _):
                if not released.wait(2):
                    raise TimeoutError("sender did not receive shutdown")
                raise OSError("peer closed")

            def shutdown(self, _):
                released.set()
                raise OSError("socket already disconnected")

        with patch.object(RUNNER, "native_reply", side_effect=TimeoutError("stalled frame")):
            with self.assertRaisesRegex(TimeoutError, "stalled frame"):
                RUNNER.native_backpressure(ClosedPeer(), 0, 8)
        self.assertFalse(any(thread.name == "owned-native-sender" for thread in threading.enumerate()))

    def test_real_pty_stream_framing_and_exit_are_checked(self):
        client, peer = socket.socketpair()
        with client, peer:
            for message in ({"type": "stdout", "data": "eA=="}, {"type": "exit", "code": 0}):
                payload = json.dumps(message).encode()
                peer.sendall(struct.pack("<I", len(payload)) + payload)
            response = RUNNER.interactive(client, "printf x", "x")
            self.assertTrue(response["ok"])
            self.assertIsNotNone(response["first_byte_ms"])
            self.assertEqual(response["stdout"], "eA==")

    def test_artifacts_cannot_escape_worktree(self):
        self.assertEqual(RUNNER.artifact_path("benchmarks"), RUNNER.ROOT / "benchmarks")
        with self.assertRaises(ValueError):
            RUNNER.artifact_path(RUNNER.ROOT.parent / "other-worktree")

    def test_failed_runs_never_become_passing_latency_samples(self):
        root = RUNNER.ROOT / ".perf/eventfd/results" / f"summary-unit-{RUNNER.os.getpid()}"
        root.mkdir(parents=True, mode=0o700, exist_ok=False)
        try:
            for name, status, latencies in (("good", "passed", [10, 20]), ("stalled", "failed", [0.001])):
                directory = root / name
                directory.mkdir(mode=0o700)
                RUNNER.save_json(directory / "manifest.json", {
                    "variant": "L0", "workload": "ping", "profile": "none",
                    "fixture": {"diagnostic_heartbeat_ms": 0}, "guest_command": "printf x",
                })
                RUNNER.save_json(directory / "result.json", {
                    "status": status, "latencies_ms": latencies, "completed_operations": len(latencies),
                })
            out = root / "summary.json"
            with contextlib.redirect_stdout(io.StringIO()):
                status = RUNNER.summarize(SimpleNamespace(runs=[root / "good", root / "stalled"], out=out))
            report = json.loads(out.read_text())
            self.assertEqual(status, 1)
            self.assertEqual(report["status"], "failed")
            self.assertFalse(report["performance_merge_eligible"])
            self.assertEqual(report["groups"][0]["failed_runs"], 1)
            self.assertEqual(report["groups"][0]["latency_ms"]["p50"], 15)
            self.assertEqual(len(report["all_runs"]), 2)
        finally:
            shutil.rmtree(root)

    def test_differing_payload_or_affinity_never_pool(self):
        root = RUNNER.ROOT / ".perf/eventfd/results" / f"conditions-unit-{RUNNER.os.getpid()}"
        root.mkdir(parents=True, mode=0o700, exist_ok=False)
        try:
            directories = []
            for index, (payload_bytes, cpus) in enumerate(((4096, [8]), (65536, [8]), (4096, [9]))):
                directory = root / str(index)
                directory.mkdir(mode=0o700)
                directories.append(directory)
                RUNNER.save_json(directory / "manifest.json", {
                    "variant": "L0", "workload": "native-echo", "profile": "none",
                    "fixture": {"diagnostic_heartbeat_ms": 10}, "guest_command": "",
                    "payload_bytes": payload_bytes, "cpus": cpus,
                })
                RUNNER.save_json(directory / "result.json", {
                    "status": "passed", "latencies_ms": [index + 1], "completed_operations": 1,
                })
            out = root / "summary.json"
            with contextlib.redirect_stdout(io.StringIO()):
                RUNNER.summarize(SimpleNamespace(runs=directories, out=out))
            report = json.loads(out.read_text())
            self.assertEqual(len(report["groups"]), 3)
            self.assertTrue(all(group["executed_runs"] == 1 for group in report["groups"]))
        finally:
            shutil.rmtree(root)


if __name__ == "__main__":
    unittest.main()
