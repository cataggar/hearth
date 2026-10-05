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

import performance

SPEC = importlib.util.spec_from_file_location("eventfd_runner", Path(__file__).with_name("run.py"))
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class EvidenceTests(unittest.TestCase):
    def test_host_controls_do_not_double_count_guest_cpu(self):
        before = "cpu  0 0 0 0 0 0 0 0 0 0\n"
        after = "cpu  100 0 20 30 10 0 0 5 80 0\n"
        result = RUNNER.host_cpu_delta(before, after, 2)
        ticks = RUNNER.os.sysconf("SC_CLK_TCK")
        self.assertAlmostEqual(result["nonidle_including_steal_cpu_seconds"], 125 / ticks)
        self.assertAlmostEqual(result["idle_or_iowait_cpu_seconds"], 40 / ticks)
        self.assertAlmostEqual(result["steal_cpu_seconds"], 5 / ticks)
        self.assertAlmostEqual(result["nonidle_one_core_equivalent_percent"], 100 * 125 / ticks / 2)

    def test_reset_host_counters_invalidate_controls(self):
        with self.assertRaisesRegex(ValueError, "counters reset"):
            RUNNER.host_cpu_delta(
                "cpu  100 0 0 0 0 0 0 0\n", "cpu  99 0 0 0 0 0 0 0\n", 1,
            )

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

    def test_nanosecond_cpu_includes_all_threads_without_tick_quantization(self):
        before = [
            {"tid": 1, "start_ticks": 10, "cpu_runtime_ns": 100},
            {"tid": 2, "start_ticks": 20, "cpu_runtime_ns": 200},
        ]
        after = [
            {"tid": 1, "start_ticks": 10, "cpu_runtime_ns": 5100},
            {"tid": 2, "start_ticks": 20, "cpu_runtime_ns": 20200},
        ]
        self.assertEqual(RUNNER.cpu_delta(before, after), .000025)
        with self.assertRaisesRegex(ValueError, "generation changed"):
            RUNNER.cpu_delta(before, [after[0], {**after[1], "start_ticks": 21}])
        with self.assertRaisesRegex(ValueError, "counter reset"):
            RUNNER.cpu_delta(before, [{**after[0], "cpu_runtime_ns": 99}, after[1]])
        with self.assertRaisesRegex(ValueError, "mixed CPU accounting"):
            RUNNER.cpu_delta(before, [{k: v for k, v in after[0].items() if k != "cpu_runtime_ns"}, after[1]])

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


class FrozenGateTests(unittest.TestCase):
    def setUp(self):
        self.root = RUNNER.ROOT / ".perf/eventfd/results" / f"freeze-unit-{RUNNER.os.getpid()}"
        self.root.mkdir(parents=True, mode=0o700, exist_ok=False)

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_short_old_or_mixed_baselines_cannot_freeze(self):
        binary, fixture = self.root / "binary", self.root / "fixture"
        binary.write_bytes(b"pinned")
        fixture.mkdir(mode=0o700)
        RUNNER.save_json(fixture / "fixture.json", {})
        manifest = {
            "binary_sha256": RUNNER.digest(binary), "fixture": {},
            "minimum_nonidle_seconds": 5, "cpu_accounting": "schedstat ns",
            "runner_sha256": "runner", "control_sha256": "control",
            "observer_sha256": "observer", "observer_object_sha256": "object",
            "source_files_sha256": {}, "cpus": [8], "client_cpus": [1],
            "vcpus": 1, "ram_mib": 512,
        }
        directories = [self.root / f"aa-{index}" for index in range(5)]
        for directory in directories:
            directory.mkdir(mode=0o700)
            RUNNER.save_json(directory / "result.json", {"status": "passed", "mode": "C00"})
        args = SimpleNamespace(baselines=self.root, binary=binary, fixture=fixture,
                               out=self.root / "gates.json")
        for update, error in (
            ({"minimum_nonidle_seconds": 1}, "sustained"),
            ({"cpu_accounting": None}, "sustained"),
            ({"binary_sha256": "different"}, "conditions changed"),
            ({"cpus": [9]}, "conditions changed"),
        ):
            with self.subTest(update=update):
                for directory in directories:
                    RUNNER.save_json(directory / "manifest.json", {
                        **manifest, **(update if directory == directories[0] or "sustained" in error else {}),
                    })
                with self.assertRaisesRegex(ValueError, error):
                    performance.freeze(args)
                self.assertFalse(args.out.exists())

    def test_noise_or_changed_conditions_reject_candidate_before_vm_start(self):
        fixture, out = self.root / "fixture", self.root / "candidate"
        fixture.mkdir(mode=0o700)
        out.mkdir(mode=0o700)
        RUNNER.save_json(fixture / "fixture.json", {})
        gates = self.root / "gates.json"
        args = SimpleNamespace(out=out, fixture=fixture, binary=self.root / "binary",
                               gates=gates, mode="C10", long_primary=False, minimum_seconds=5)
        for status, cpus, error in (
            ("noise-inconclusive", [8], "noise gates have not passed"),
            ("noise-provisionally-acceptable", [9], "conditions differ"),
        ):
            with self.subTest(status=status, cpus=cpus):
                RUNNER.save_json(gates, {
                    "binary_sha256": "hash", "fixture_sha256": "hash", "status": status,
                    "baseline_conditions": {"cpus": cpus, "minimum_nonidle_seconds": 5},
                })
                with patch.object(performance.os, "geteuid", return_value=1000), \
                     patch.object(performance.os, "sched_setaffinity"), \
                     patch.object(performance.bench, "digest", return_value="hash"), \
                     patch.object(performance.subprocess, "run", return_value=SimpleNamespace(stdout=b"commit\n")), \
                     patch.object(performance.control.Guest, "__init__", side_effect=AssertionError("VM must not start")) as start_vm, \
                     contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(performance.child(args), 1)
                    start_vm.assert_not_called()
                result = json.loads((out / "result.json").read_text())
                self.assertEqual(result["status"], "failed")
                self.assertIn(error, result["errors"][0])


if __name__ == "__main__":
    unittest.main()
