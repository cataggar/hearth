import contextlib
import copy
import io
import json
import math
import os
from pathlib import Path
import shutil
import signal
import socket
import struct
import subprocess
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import hosted
import custody
import matrix
import performance
import visible_cpu


def matrices():
    rows = [{
        "name": name, "status": "passed", "known_scoped_cpu_per_operation": .01,
        "known_scoped_cpu_seconds": .1, "operation_seconds": 60 if name == "idle" else 6,
        "visible_host_cpu_per_operation": .01, "operations": 10,
        "visible_host_cpu": {"busy_cpu_seconds": .1, "operation_seconds": 6,
                             "busy_core_equivalents": .1 / 6, "precision_cpu_seconds_bound": .0001},
        "latency": {"p95": 10}, "bytes": 0 if name in ("idle", "exec", "interactive", "lifecycle") else 4096,
        "bytes_per_second": 0 if name in ("idle", "exec", "interactive", "lifecycle") else 4096 / 6,
    } for name in performance.WORKLOADS]
    controls = [{"busy_cpu_seconds": .0001, "operation_seconds": 6,
                 "precision_cpu_seconds_bound": .0001} for _ in range(2)]
    return [copy.deepcopy({"mode": "C00", "status": "passed", "rows": rows,
                           "background_controls": controls}) for _ in range(5)]


class HostedGuards(unittest.TestCase):
    def test_actual_pty_frame_timeout_retains_allowlisted_header_and_body_points(self):
        for body in (False, True):
            with self.subTest(body=body):
                client, peer = socket.socketpair()
                with client, peer:
                    client.settimeout(.05)
                    if body:
                        peer.sendall(struct.pack("<I", 9))
                    else:
                        payload = json.dumps({"type": "stdout", "data": "UFRZ"}).encode()
                        peer.sendall(struct.pack("<I", len(payload)) + payload)
                    progress = hosted.WorkloadProgress("interactive")
                    with self.assertRaises(TimeoutError) as caught:
                        performance.workload(SimpleNamespace(connection=client), None,
                                             "interactive", progress.point)
                    if not body:
                        self.assertEqual(hosted.hashlib.sha256(str(caught.exception).encode()).hexdigest(),
                                         "c1da153ef0b9b0a0d96c2cf3178d31a6c91488fdbc21bbe34e8a689798fddf29")
                    location = progress.snapshot()
                    self.assertEqual(location["workload"], "interactive")
                    self.assertEqual(location["suboperations"]["interactive"], {
                        "substage": "pty-stream",
                        "error_point": "receive-body" if body else "receive-header",
                        "operation_index": 0,
                    })
                    self.assertNotIn("PTY", json.dumps(location))

    def test_progress_rejects_unknown_and_keeps_concurrent_sources_separate(self):
        progress = hosted.WorkloadProgress("concurrent")
        progress.point("tap-65536", "native-echo", "exchange", 8)
        progress.point("vsock-65536", "native-echo", "exchange", 9)
        self.assertEqual(set(progress.snapshot()["suboperations"]),
                         {"concurrent", "tap-65536", "vsock-65536"})
        original = progress.snapshot()
        for workload, stage, point, index in (
                ("PRIVATE", "native-echo", "exchange", 0),
                ("exec", "PRIVATE", "receive-header", 0),
                ("exec", "agent-rpc", "PRIVATE", 0),
                ("exec", "agent-rpc", "receive-header", True)):
            with self.assertRaisesRegex(hosted.Blocked, "source-allowlisted"):
                progress.point(workload, stage, point, index)
        self.assertEqual(progress.snapshot(), original)
        self.assertNotIn("PRIVATE", json.dumps(progress.snapshot()))
        progress.point("concurrent", "workload", "begin", 0)
        self.assertEqual(set(progress.snapshot()["suboperations"]), {"concurrent"})

    def test_failed_cell_persists_preoperation_and_fine_context_without_raw_error(self):
        root = hosted.bench.ROOT / ".perf/eventfd" / f"aa-location-test-{os.getpid()}"
        root.mkdir(mode=0o700, parents=True, exist_ok=False)
        stages = []
        original = hosted.save

        class Guest:
            def __init__(self, *_args, **_kwargs):
                self.native_connection = None
                self.path = root

            def close(self):
                raise RuntimeError("PRIVATE cleanup failure")

        def recorded_save(path, result):
            if path.name == "result.json":
                stages.append(copy.deepcopy(result))
            original(path, result)

        def failed_sample(_guest, _tcp, name, _cores, progress):
            self.assertEqual(name, "interactive")
            progress.point(name, "pty-stream", "receive-header", 7)
            raise TimeoutError("PRIVATE guest stderr/argv")

        from unittest.mock import Mock
        tcp = Mock()
        (root / "host.json").write_text(json.dumps(
            {"client_cpu": 0, "vm_cpu": 2, "visible_logical_cores": 4}))
        with patch.object(hosted.os, "geteuid", return_value=1000), \
                patch.object(hosted.os, "sched_setaffinity"), \
                patch.object(hosted, "PUBLIC", root), \
                patch.object(hosted, "validate_pins"), \
                patch.object(hosted.visible_cpu, "quiet", return_value={}), \
                patch.object(hosted.control, "Guest", Guest), \
                patch.object(hosted.socket, "create_connection", return_value=tcp), \
                patch.object(hosted.control, "agent"), \
                patch.object(hosted.bench, "native_echo"), \
                patch.object(hosted.time, "sleep"), \
                patch.object(hosted.performance, "WORKLOADS", ["interactive"]), \
                patch.object(hosted, "sample", side_effect=failed_sample), \
                patch.object(hosted, "save", side_effect=recorded_save):
            try:
                self.assertEqual(hosted.cell(SimpleNamespace(
                    out=root, mode="C00", profile=None, scale_count=None, lifecycle=False)), 1)
            finally:
                shutil.rmtree(root)
        self.assertEqual(stages[0]["active_workload"]["suboperations"]["interactive"]["error_point"], "begin")
        final = stages[-1]
        self.assertEqual(final["failure_type"], "TimeoutError")
        self.assertEqual(final["active_workload"]["suboperations"]["interactive"]["operation_index"], 7)
        self.assertEqual(final["active_workload"]["suboperations"]["interactive"]["error_point"], "receive-header")
        self.assertEqual(final["status"], "failed")
        self.assertEqual(final["active_phase"], "matrix")
        self.assertTrue(final["cleanup_failed"])
        self.assertNotIn("PRIVATE", json.dumps(final))

    def test_redirected_cache_prepares_native_fixture_parent_before_build(self):
        root = hosted.bench.ROOT / ".perf/eventfd" / f"hosted-cache-test-{os.getpid()}"
        (root / "vmm").mkdir(mode=0o700, parents=True, exist_ok=False)
        try:
            self.assertFalse((root / "vmm/.zig-cache").exists())

            def first_build(*_args, **_kwargs):
                self.assertTrue((root / "vmm/.zig-cache").is_dir())
                self.assertEqual((root / "vmm/.zig-cache").stat().st_mode & 0o777, 0o700)
                raise RuntimeError("stop before compiler execution")

            with patch.object(hosted.bench, "ROOT", root), \
                    patch.object(hosted.shutil, "which", return_value="zig"), \
                    patch.object(hosted.subprocess, "check_output", return_value="0.17.0\n"), \
                    patch.object(hosted.bench, "digest", return_value=hosted.bench.KERNEL_SHA256), \
                    patch.object(hosted, "save"), \
                    patch.object(hosted, "require_execution", side_effect=first_build) as execute, \
                    patch.dict(os.environ, ZIG_LOCAL_CACHE_DIR=str(root / "redirected-cache")):
                with self.assertRaisesRegex(RuntimeError, "stop before compiler"):
                    hosted.build_inputs([], "a" * 40)
                execute.assert_called_once()
        finally:
            shutil.rmtree(root)

    def test_native_failure_diagnostics_never_publish_unknown_text(self):
        text = (
            "error: 'integration_tests.test.boot to userspace' failed:\n"
            "/PRIVATE/trace:42: return error.GuestBootFailed;\n"
            "environment SECRET=PRIVATE; error.PrivateCredential\n"
            "error: 'PRIVATE.test.SECRET' failed:\n"
            "disk image PRIVATE; error.FileNotFound\n"
            "66/71 tests passed\n"
        )
        diagnostics = hosted.native_test_failure_diagnostics(text)
        self.assertEqual(diagnostics["failure_headers"], 2)
        self.assertEqual(diagnostics["unknown_failure_headers"], 1)
        self.assertEqual(diagnostics["failures"], [{
            "test": "integration_tests.test.boot to userspace",
            "observed_error_labels": ["GuestBootFailed"],
        }])
        self.assertNotIn("PRIVATE", json.dumps(diagnostics))
        self.assertNotIn("SECRET", json.dumps(diagnostics))

    def test_failed_native_phase_keeps_coverage_rejection_and_safe_diagnostics(self):
        root = hosted.bench.ROOT / ".perf/eventfd" / f"hosted-failure-test-{os.getpid()}"
        root.mkdir(mode=0o700, parents=True, exist_ok=False)
        try:
            (root / "zig-Debug.stderr").write_text(
                "error: 'integration_tests.test.API boot and VM status' failed:\n"
                "/PRIVATE/trace: return error.FileNotFound;\n"
                "66/71 tests passed\n"
            )
            phases = []
            with patch.object(hosted, "RAW", root), \
                    patch.object(hosted, "check_space"), \
                    patch.object(hosted, "owned_command", return_value={"name": "zig-Debug", "returncode": 1}), \
                    patch.object(hosted, "output", return_value=""), \
                    patch.object(hosted, "save") as save:
                with self.assertRaisesRegex(hosted.Blocked, "zig-Debug failed"):
                    hosted.require_execution("zig-Debug", ["zig", "build"], 600, phases, tests=70)
                save.assert_called_once()
            self.assertEqual(phases[0]["test_counts"], [(66, 71)])
            self.assertTrue(phases[0]["coverage_rejected"])
            self.assertFalse(phases[0]["skip_detected"])
            self.assertEqual(phases[0]["test_failure_diagnostics"]["failures"], [{
                "test": "integration_tests.test.API boot and VM status",
                "observed_error_labels": ["FileNotFound"],
            }])
            self.assertNotIn("PRIVATE", json.dumps(phases))
        finally:
            shutil.rmtree(root)

    def test_kvm_probe_records_immediate_exit_and_closes_owned_descriptors(self):
        with patch.object(hosted.os, "open", return_value=41), \
                patch.object(hosted.os, "close") as close, \
                patch.object(hosted.fcntl, "ioctl", side_effect=[12, 42, 1, 1, 1, 1]) as ioctl:
            record = hosted.probe_kvm()
        self.assertEqual(record["capabilities"]["immediate_exit"], 1)
        self.assertEqual(ioctl.call_args_list[-1].args, (41, 0xAE03, 136))
        self.assertEqual([call.args for call in close.call_args_list], [(42,), (41,)])
        hosted.require_kvm_capabilities(record)

    def test_api12_without_immediate_exit_cannot_admit_host(self):
        for unavailable in (0, -1, None, True, "1"):
            with self.subTest(value=unavailable):
                record = {"api_version": 12, "nonroot_vm_create": True,
                          "capabilities": {name: 1 for name in hosted.KVM_CAPABILITIES}}
                if unavailable is None:
                    del record["capabilities"]["immediate_exit"]
                else:
                    record["capabilities"]["immediate_exit"] = unavailable
                with self.assertRaisesRegex(hosted.Blocked, r"immediate_exit\(136\)"):
                    hosted.require_kvm_capabilities(record)
        with self.assertRaisesRegex(hosted.Blocked, "malformed"):
            hosted.require_kvm_capabilities({"capabilities": []})

    def test_kvm_capability_query_failure_is_blocked_and_closes_fd(self):
        failure = OSError("injected capability query failure")
        with patch.object(hosted.os, "open", return_value=41), \
                patch.object(hosted.os, "close") as close, \
                patch.object(hosted.fcntl, "ioctl", side_effect=[12, 42, 1, 1, 1, failure]):
            with self.assertRaisesRegex(hosted.Blocked, r"immediate_exit\(136\).*capability query failure") as caught:
                hosted.probe_kvm()
        self.assertIs(caught.exception.__cause__, failure)
        self.assertEqual([call.args for call in close.call_args_list], [(42,), (41,)])

    def test_affinity_excludes_smt_siblings_in_both_directions(self):
        topology = {
            0: {"core": [0, 0], "siblings": [0, 1]},
            1: {"core": [0, 0], "siblings": [0, 1]},
            2: {"core": [0, 1], "siblings": [2, 3]},
            3: {"core": [0, 1], "siblings": [2, 3]},
        }
        self.assertEqual(hosted.independent_cpus(topology), (0, 2))
        with self.assertRaises(hosted.Blocked):
            hosted.independent_cpus({key: topology[key] for key in (0, 1)})
        with self.assertRaises(hosted.Blocked):
            hosted.independent_cpus({
                0: {"core": [0, 0], "siblings": [0]},
                2: {"core": [0, 1], "siblings": [0, 2]},
            })
        self.assertEqual(hosted.cpulist("2-3,8,12-13"), {2, 3, 8, 12, 13})

    def test_incomplete_short_zero_and_unknown_cpu_cannot_freeze(self):
        for bad in (None, 0, math.nan, math.inf):
            samples = matrices()
            samples[0]["rows"][0]["visible_host_cpu_per_operation"] = bad
            with self.assertRaises(hosted.Blocked):
                hosted.freeze(samples, {})
        samples = matrices()
        samples[0]["rows"][0]["operation_seconds"] = 4.99
        with self.assertRaises(hosted.Blocked):
            hosted.freeze(samples, {})
        samples = matrices()
        samples[0]["rows"].pop()
        with self.assertRaises(hosted.Blocked):
            hosted.freeze(samples, {})
        with self.assertRaises(hosted.Blocked):
            hosted.freeze(matrices()[:4], {})

    def test_failed_noise_never_admits_candidates(self):
        samples = matrices()
        for index, sample in enumerate(samples):
            sample["rows"][0]["bytes_per_second"] *= index + 1
        gate = hosted.freeze(samples, {})
        self.assertEqual(gate["status"], "noise-inconclusive")
        self.assertIn(performance.WORKLOADS[0], gate["exceeds_noise_caps"])
        sha = "a" * 40
        with patch.dict(os.environ, GITHUB_REPOSITORY="cataggar/hearth", GITHUB_ACTIONS="true"), \
                patch.object(hosted.subprocess, "check_output", return_value=sha + "\n"), \
                patch.object(hosted.subprocess, "run", return_value=SimpleNamespace(returncode=0)), \
                patch.object(hosted, "host_probe", return_value=({"vm_cpu": 0, "client_cpu": 2}, "perf")), \
                patch.object(hosted, "build_inputs", return_value={}), \
                patch.object(hosted, "run_cell", side_effect=samples) as run, \
                patch.object(hosted, "remove_owned_images", return_value=[]), \
                patch.object(hosted, "save") as save, patch.object(hosted, "receipt"), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(hosted.qualify(sha), 1)
        self.assertEqual(run.call_count, 5)
        self.assertTrue(all(call.args[1] == "C00" for call in run.call_args_list))
        decisions = [call.args[1] for call in save.call_args_list if call.args[0].name == "decision.json"]
        self.assertEqual(decisions[-1]["status"], "negative-hosted-noise-decision")
        self.assertFalse(decisions[-1]["performance_merge_eligible"])

    def test_pairs_require_five_real_positive_samples(self):
        for candidate in ([1] * 4, [1, 1, 1, 1, 0], [1, 1, 1, 1, math.nan]):
            with self.assertRaises(hosted.Blocked):
                hosted.paired_interval([1] * 5, candidate)
        interval = hosted.paired_interval([1, 2, 3, 4, 5], [.8, 1.6, 2.4, 3.2, 4])
        self.assertAlmostEqual(interval["upper_ratio"], .8)

    def test_mechanism_excludes_serial_and_cannot_divide_by_unknown_control(self):
        def profile(notify, irq):
            return {"status": "passed", "operations": 100, "attribution": {
                "attributed_notify_userspace_returns": {"blk:queue0": notify},
                "completed_irq_line_ioctl_calls": {"blk": irq, "non-virtio-or-unattributed": 999}}}
        profiles = {"C00": profile(100, 200), "C10": profile(0, 200),
                    "C01": profile(100, 0), "C11": profile(0, 0)}
        report = hosted.mechanism(profiles)
        self.assertEqual(report["C10"]["reduction_percent"]["notify_userspace_returns_per_operation"], 100)
        self.assertEqual(report["C01"]["reduction_percent"]["eligible_irq_line_ioctls_per_operation"], 100)
        self.assertFalse(report["performance_merge_eligible"])
        profiles["C00"] = profile(0, 0)
        with self.assertRaises(hosted.Blocked):
            hosted.mechanism(profiles)

    def test_known_cpu_gain_and_proven_pause_regression_cannot_qualify(self):
        blocks = []
        for baseline in matrices():
            block = {}
            for mode in hosted.MODES:
                sample = copy.deepcopy(baseline)
                sample["mode"] = mode
                for row in sample["rows"]:
                    if mode != "C00":
                        row["visible_host_cpu_per_operation"] *= .8
                        row["visible_host_cpu"]["busy_cpu_seconds"] *= .8
                        row["visible_host_cpu"]["busy_core_equivalents"] *= .8
                        row["known_scoped_cpu_per_operation"] = 1000000
                        if row["name"] == "lifecycle":
                            row["latency"]["p95"] *= 50
                block[mode] = sample
            blocks.append(block)
        report = hosted.compare(blocks)
        self.assertTrue(report["all_candidates_have_demonstrated_regression"])
        self.assertFalse(report["performance_merge_eligible"])
        self.assertFalse(report["owned_detail_added"])
        self.assertFalse(report["background_subtracted"])
        self.assertTrue(report["unexecuted_required_coverage"])
        for check in report["diagnostic_gate_checks"].values():
            self.assertTrue(check["visible_primary_benefit_95_lower_at_least_10_percent"])
            self.assertFalse(check["qualified"])

    def test_background_uncertainty_can_hide_an_apparent_twenty_percent_gain(self):
        blocks = []
        for baseline in matrices():
            block = {}
            for mode in hosted.MODES:
                sample = copy.deepcopy(baseline)
                for control in sample["background_controls"]:
                    control["busy_cpu_seconds"] = .05
                if mode != "C00":
                    for row in sample["rows"]:
                        row["visible_host_cpu_per_operation"] *= .8
                        row["visible_host_cpu"]["busy_cpu_seconds"] *= .8
                block[mode] = sample
            blocks.append(block)
        report = hosted.compare(blocks)
        check = report["diagnostic_gate_checks"]["C11"]
        self.assertTrue(check["residual_could_hide_required_benefit"])
        self.assertFalse(check["visible_primary_benefit_95_lower_at_least_10_percent"])
        self.assertFalse(report["performance_merge_eligible"])

    def test_background_uncertainty_cannot_prove_a_cpu_regression(self):
        blocks = []
        for baseline in matrices():
            block = {}
            for mode in hosted.MODES:
                sample = copy.deepcopy(baseline)
                for control in sample["background_controls"]:
                    control["busy_cpu_seconds"] = .05
                if mode != "C00":
                    for row in sample["rows"]:
                        row["visible_host_cpu_per_operation"] *= 1.2
                        row["visible_host_cpu"]["busy_cpu_seconds"] *= 1.2
                block[mode] = sample
            blocks.append(block)
        report = hosted.compare(blocks)
        self.assertFalse(report["all_candidates_have_demonstrated_regression"])
        for check in report["diagnostic_gate_checks"].values():
            self.assertFalse(check["demonstrated_regressions"])
            self.assertTrue(check["regression_bounds_inconclusive"])

    def test_upload_projection_drops_payload_and_unknown_nested_fields(self):
        row = {
            "name": "exec", "latency_ms": [1], "guest_memory": b"PRIVATE",
            "disk": b"PRIVATE", "environment": {"SECRET": "PRIVATE"},
            "threads_before": [{"tid": 123, "start_ticks": 1, "environment": {"SECRET": "PRIVATE"}}],
            "kernel_work_before": {"status": "passed", "foreign_inventory": ["PRIVATE"],
                                   "kernel_work": {"inject": {"cpu_ns": 10, "jobs": 1, "SECRET": "PRIVATE"},
                                                   "foreign": {"cpu_ns": 20, "jobs": 1}}},
        }
        text = json.dumps(hosted.row_projection(row))
        self.assertNotIn("PRIVATE", text)
        self.assertNotIn("foreign", text)
        self.assertIn('"cpu_ns": 10', text)

    def test_wrong_source_or_environment_stops_before_host_probe(self):
        with patch.object(hosted.subprocess, "check_output", return_value="b" * 40), \
                patch.object(hosted, "host_probe") as probe:
            with self.assertRaises(hosted.Blocked):
                hosted.qualify("a" * 40)
            probe.assert_not_called()

    def test_image_cleanup_rejects_symlinks_and_preserves_unnamed_files(self):
        root = hosted.bench.ROOT / ".perf/eventfd" / f"image-cleanup-test-{os.getpid()}"
        root.mkdir(mode=0o700, parents=True, exist_ok=False)
        try:
            (root / "memory").write_bytes(b"owned synthetic image")
            (root / "other").write_bytes(b"preserved")
            (root / "disk").symlink_to(root / "other")
            with self.assertRaises(hosted.Blocked):
                hosted.remove_owned_images(root, ("disk",))
            self.assertTrue((root / "other").exists())
            result = hosted.remove_owned_images(root, ("memory",))
            self.assertEqual(result[0]["bytes"], 21)
            self.assertFalse((root / "memory").exists())
            self.assertTrue((root / "other").exists())
        finally:
            shutil.rmtree(root)


class ObserverCleanup(unittest.TestCase):
    def test_optional_failed_detail_is_unavailable_not_zero_or_primary_failure(self):
        from unittest.mock import Mock
        observer = SimpleNamespace(read=Mock(side_effect=RuntimeError("owned detail unavailable")),
                                   abort=Mock())
        result = {}
        self.assertIsNone(hosted.observer_detail(observer, result, "before"))
        observer.abort.assert_called_once()
        self.assertEqual(result["irqfd_detail_failures"][0]["phase"], "before")
        self.assertNotIn("status", result)
        self.assertNotIn("kernel_irqfd_cpu_seconds", result)

    def test_not_ready_observer_closes_owned_protocol_and_joins(self):
        root = hosted.bench.ROOT / ".perf/eventfd" / f"hosted-observer-test-{os.getpid()}"
        root.mkdir(mode=0o700, parents=True, exist_ok=False)
        observer = matrix.Observer.__new__(matrix.Observer)
        process = SimpleNamespace(stdin=io.StringIO(), stdout=io.StringIO())
        from unittest.mock import Mock
        process.wait = Mock(return_value=1)
        try:
            with patch.object(matrix.subprocess, "Popen", return_value=process), \
                    patch.object(matrix.select, "select", return_value=([], [], [])):
                with self.assertRaisesRegex(RuntimeError, "did not become ready"):
                    observer.__init__(SimpleNamespace(out=root, pid=123, pid_start_ticks=456),
                                      root / "owned-object.bpf.o")
            self.assertTrue(process.stdin.closed)
            self.assertTrue(observer.handle.closed)
            process.wait.assert_called_once_with(timeout=8)
        finally:
            shutil.rmtree(root)


class ProfileBoundaries(unittest.TestCase):
    def capture(self):
        from unittest.mock import Mock
        capture = hosted.PerfCapture.__new__(hosted.PerfCapture)
        capture.process = SimpleNamespace(poll=Mock(return_value=None))
        capture.fds = [101, 102]
        capture.deadline = hosted.time.monotonic() + 2
        capture.command_lock = threading.Lock()
        capture.command_epoch = 0
        capture.ack_failed = False
        return capture

    def test_exact_perf_frame_completes_across_partial_reads_including_nul(self):
        for fragments in ((b"ack\n\0",), (b"a", b"ck", b"\n", b"\0")):
            with self.subTest(fragments=fragments):
                capture = self.capture()
                ready = [([], [], []), *[([102], [], []) for _ in fragments], ([], [], [])]
                with patch.object(hosted.select, "select", side_effect=ready), \
                        patch.object(hosted.os, "read", side_effect=fragments) as read, \
                        patch.object(hosted.os, "write", return_value=7):
                    fence = capture.command("enable")
                self.assertEqual(read.call_count, len(fragments))
                self.assertEqual(fence["ack_frame_hex"], "61636b0a00")
                self.assertEqual(fence["epoch"], 1)
                self.assertFalse(capture.ack_failed)

    def test_extra_coalesced_unknown_and_stale_frames_poison_epoch(self):
        for response in (b"ack\n\0ack\n\0", b"ack\nX", b"bad\n\0"):
            with self.subTest(response=response):
                capture = self.capture()
                with patch.object(hosted.select, "select", side_effect=[([], [], []), ([102], [], [])]), \
                        patch.object(hosted.os, "read", return_value=response), \
                        patch.object(hosted.os, "write", return_value=7):
                    with self.assertRaisesRegex(hosted.Blocked, "malformed"):
                        capture.command("enable")
                with self.assertRaisesRegex(hosted.Blocked, "cannot be reused"):
                    capture.command("disable")
        capture = self.capture()
        with patch.object(hosted.select, "select", return_value=([102], [], [])), \
                patch.object(hosted.os, "read", return_value=b"ack\n\0"), \
                patch.object(hosted.os, "write") as write:
            with self.assertRaisesRegex(hosted.Blocked, "unsolicited"):
                capture.command("disable")
            write.assert_not_called()
        capture = self.capture()
        with patch.object(hosted.select, "select", side_effect=[
                ([], [], []), ([102], [], []), ([102], [], [])]), \
                patch.object(hosted.os, "read", side_effect=[b"ack\n\0", b"ack\n\0"]), \
                patch.object(hosted.os, "write", return_value=7):
            with self.assertRaisesRegex(hosted.Blocked, "after completed frame"):
                capture.command("enable")
        capture = self.capture()
        with self.assertRaisesRegex(hosted.Blocked, "unknown.*command"):
            capture.command("snapshot")

    def test_one_pending_epoch_and_missing_terminator_never_succeed(self):
        capture = self.capture()
        capture.command_lock.acquire()
        try:
            with patch.object(hosted.os, "write") as write:
                with self.assertRaisesRegex(hosted.Blocked, "already pending"):
                    capture.command("disable")
                write.assert_not_called()
        finally:
            capture.command_lock.release()
        capture = self.capture()
        with patch.object(hosted.select, "select", side_effect=[([], [], []), ([102], [], [])]), \
                patch.object(hosted.os, "read", return_value=b"ack\n"), \
                patch.object(hosted.os, "write", return_value=7), \
                patch.object(capture, "check_alive", side_effect=[None, None, hosted.Blocked("finite scoped collection budget exhausted")]):
            with self.assertRaisesRegex(hosted.Blocked, "budget exhausted"):
                capture.command("enable")
        self.assertTrue(capture.ack_failed)

    def exercise(self, premature=False):
        clock = SimpleNamespace(ns=0)

        class Capture:
            deadline = 30

            def check_alive(self):
                if premature and clock.ns >= 15_000_000_000:
                    raise hosted.Blocked("scoped collector terminated")

            def command(self, name):
                self.check_alive()
                return {"sent_ns": clock.ns, "ack_ns": clock.ns}

            def release(self):
                self.check_alive()

        def batch(*_args):
            clock.ns += 3_900_000_000
            return b'{"operations":128}'

        with patch.object(hosted.time, "monotonic", side_effect=lambda: clock.ns / 1e9), \
                patch.object(hosted.time, "monotonic_ns", side_effect=lambda: clock.ns), \
                patch.object(matrix, "rpc_exec", side_effect=batch):
            return hosted.profile_batches(None, Capture())

    def test_delayed_final_batch_is_fully_inside_disable_fence(self):
        result = self.exercise()
        self.assertEqual(result["operations"], 512)
        bounds = result["capture_boundaries"]
        self.assertEqual(len(bounds["batches"]), 4)
        self.assertEqual(bounds["completed_operation_seconds"], 15.6)
        self.assertEqual(bounds["disable"]["sent_ns"], 15_600_000_000)
        self.assertLessEqual(bounds["batches"][-1]["completed_ns"], bounds["disable"]["sent_ns"])

    def test_zero_exit_at_old_fifteen_second_boundary_rejects_whole_sample(self):
        with self.assertRaisesRegex(hosted.Blocked, "collector terminated"):
            self.exercise(premature=True)

    def test_acknowledgement_is_required_and_malformed_response_rejected(self):
        from unittest.mock import Mock
        for response in (b"ack\n\0", b"bad\n"):
            with self.subTest(response=response):
                control_read, control_write = os.pipe()
                ack_read, ack_write = os.pipe()
                capture = hosted.PerfCapture.__new__(hosted.PerfCapture)
                capture.process = SimpleNamespace(poll=Mock(return_value=None))
                capture.fds = [control_write, ack_read]
                capture.deadline = hosted.time.monotonic() + 2
                capture.command_lock = threading.Lock()
                capture.command_epoch = 0
                capture.ack_failed = False

                def acknowledge():
                    self.assertEqual(os.read(control_read, 4096), b"enable\n")
                    os.write(ack_write, response)

                worker = threading.Thread(target=acknowledge)
                worker.start()
                try:
                    if response == b"ack\n\0":
                        fence = capture.command("enable")
                        self.assertLessEqual(fence["sent_ns"], fence["ack_ns"])
                    else:
                        with self.assertRaisesRegex(hosted.Blocked, "malformed"):
                            capture.command("enable")
                    capture.ack_failed = False
                    capture.process.poll.return_value = 0
                    with self.assertRaisesRegex(hosted.Blocked, "terminated"):
                        capture.command("disable")
                finally:
                    worker.join(timeout=2)
                    for fd in (control_read, control_write, ack_read, ack_write):
                        os.close(fd)
                self.assertFalse(worker.is_alive())


class DescendantCustody(unittest.TestCase):
    def test_exit_reaped_between_liveness_and_lookup_is_normal_no_signal(self):
        process = subprocess.Popen(
            [sys.executable, "-c", "import sys; print('READY',flush=True); sys.stdin.read()"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, start_new_session=True)
        fd = None
        try:
            self.assertTrue(hosted.select.select([process.stdout], [], [], 5)[0])
            self.assertEqual(process.stdout.readline(), b"READY\n")
            before = custody.identity(process.pid)
            fd = os.pidfd_open(process.pid)
            record = {**before, "pidfd": fd, "signals": []}
            supervisor = custody.Supervisor.__new__(custody.Supervisor)
            original = custody.identity

            def exited(pid):
                self.assertEqual(pid, process.pid)
                self.assertTrue(supervisor.alive(record))
                process.kill()
                process.wait(timeout=5)
                self.assertIsNone(original(pid))
                return None

            with patch.object(custody, "identity", side_effect=exited), \
                    patch.object(custody.signal, "pidfd_send_signal") as send:
                supervisor.send(record, signal.SIGTERM)
                send.assert_not_called()
            self.assertFalse(supervisor.alive(record))
            self.assertEqual(record["signals"], [])
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            process.stdin.close()
            process.stdout.close()
            if fd is not None:
                os.close(fd)

    def test_unsupported_kernel_pidfd_is_rejected_before_controller_launch(self):
        with patch.object(custody.os, "pidfd_open", side_effect=OSError(38, "injected ENOSYS")), \
                patch.object(custody.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(custody.CustodyError, "before controller launch"):
                custody.Supervisor()
            launch.assert_not_called()

    def exercise(self, orphan, refused=False):
        root = hosted.bench.ROOT / ".perf/eventfd" / f"custody-test-{os.getpid()}-{int(orphan)}-{int(refused)}"
        root.mkdir(mode=0o700, parents=True, exist_ok=False)
        child = ("import os,signal,time; from pathlib import Path; "
                 "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                 "Path(__import__('sys').argv[1]).touch(); time.sleep(60)")
        controller = (
            "import json,signal,subprocess,sys,time; from pathlib import Path; import custody; "
            "root=Path(sys.argv[1]); signal.signal(signal.SIGTERM,signal.SIG_IGN); "
            f"children=[subprocess.Popen([sys.executable,'-c',{child!r},str(root/f'ready-{{n}}')],"
            f"start_new_session=True) for n in range({1 if orphan else 9})]; "
            "(root/'children.json').write_text(json.dumps([custody.identity(p.pid) for p in children])); "
            "deadline=time.monotonic()+5\n"
            "while not all((root/f'ready-{n}').exists() for n in range(len(children))):\n"
            " if time.monotonic()>deadline: raise RuntimeError('child startup failed')\n"
            " time.sleep(.01)\n"
            + ("sys.exit(0)" if orphan else "time.sleep(60)")
        )
        refusal = (
            "class Refusal(custody.Supervisor):\n"
            " def __init__(self):\n"
            "  super().__init__(); self.refused=None; self.inject=True\n"
            " def send(self,row,signum):\n"
            "  if row is not self.controller:\n"
            "   if self.refused is None: self.refused=(row['pid'],row['start_ticks'])\n"
            "   if self.inject and (row['pid'],row['start_ticks'])==self.refused:\n"
            "    raise custody.CustodyError('injected per-registration verification refusal')\n"
            "  return super().send(row,signum)\n"
        ) if refused else ""
        fixture_cleanup = (
            " supervisor.inject=False\n"
            " for row in supervisor.records.values(): supervisor.send(row,signal.SIGKILL)\n"
            " deadline=time.monotonic()+3\n"
            " while time.monotonic()<deadline:\n"
            "  supervisor.reap()\n"
            "  try: os.waitpid(supervisor.controller['pid'],os.WNOHANG)\n"
            "  except ChildProcessError: pass\n"
            "  if all(custody.identity(row['pid']) is None for row in supervisor.records.values()): break\n"
            "  time.sleep(.01)\n"
            " assert all(custody.identity(row['pid']) is None for row in supervisor.records.values())\n"
            " Path(sys.argv[1],'fixture-cleanup.json').write_text(json.dumps({'injection_removed':True,'all_reaped':True}))\n"
        ) if refused else ""
        program = (
            "import json,os,signal,sys,time; from pathlib import Path; import custody\n"
            + refusal
            + f"supervisor={'Refusal' if refused else 'custody.Supervisor'}()\n"
            "try:\n"
            f" code,receipt=supervisor.run([sys.executable,'-c',{controller!r},sys.argv[1]],"
            "work_seconds=2,cleanup_seconds=3,term_grace=.1)\n"
            " Path(sys.argv[1],'receipt.json').write_text(json.dumps({'code':code,**receipt}))\n"
            "finally:\n"
            + fixture_cleanup
            + " supervisor.close()\n"
        )
        process = None
        try:
            process = subprocess.Popen([sys.executable, "-c", program, str(root)],
                                       cwd=Path(hosted.__file__).parent,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            output, errors = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, (output, errors))
            receipt = json.loads((root / "receipt.json").read_text())
            self.assertEqual(receipt["status"], "failed" if refused else "passed")
            if not refused:
                self.assertEqual(receipt["surviving_generations"], [])
                self.assertEqual(receipt["alive_before_controller_kill"], [])
            self.assertLess(receipt["cleanup_seconds"], 3.2 if refused else 3)
            children = json.loads((root / "children.json").read_text())
            self.assertEqual(len(children), 1 if orphan else 9)
            for child_identity in children:
                self.assertIsNone(custody.identity(child_identity["pid"]))
                registration = next(row for row in receipt["registrations"]
                                    if (row["pid"], row["start_ticks"]) ==
                                    (child_identity["pid"], child_identity["start_ticks"]))
                if refused and [registration["pid"], registration["start_ticks"]] in receipt["unsafe_registrations"]:
                    self.assertFalse(registration["reaped"])
                    self.assertEqual(registration["signals"], [])
                else:
                    self.assertTrue(registration["reaped"])
            if refused:
                self.assertEqual(json.loads((root / "fixture-cleanup.json").read_text()),
                                 {"injection_removed": True, "all_reaped": True})
            return receipt
        finally:
            # Only the recorded synthetic generations may be signalled on failure.
            if (root / "children.json").exists():
                for child_identity in json.loads((root / "children.json").read_text()):
                    actual = custody.identity(child_identity["pid"])
                    if actual is not None and actual["start_ticks"] == child_identity["start_ticks"]:
                        fd = os.pidfd_open(actual["pid"])
                        try:
                            if custody.identity(actual["pid"]) == actual:
                                signal.pidfd_send_signal(fd, signal.SIGKILL)
                        finally:
                            os.close(fd)
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate(timeout=5)
            shutil.rmtree(root)

    def test_timeout_reaps_eight_separate_session_vms_and_auxiliary_collector(self):
        receipt = self.exercise(orphan=False)
        self.assertEqual(receipt["code"], 124)
        self.assertEqual(receipt["termination_reason"], "timeout")
        self.assertEqual(receipt["controller_returncode"], -signal.SIGKILL)

    def test_successful_controller_cannot_leave_separate_session_orphan(self):
        receipt = self.exercise(orphan=True)
        self.assertEqual(receipt["code"], 1)
        self.assertEqual(receipt["controller_returncode"], 0)
        self.assertEqual(receipt["termination_reason"], "completed")

    def test_registration_error_preserves_failed_receipt_and_cleans_other_children(self):
        receipt = self.exercise(orphan=False, refused=True)
        self.assertEqual(receipt["code"], 1)
        self.assertEqual(len(receipt["unsafe_registrations"]), 1)
        self.assertEqual(receipt["surviving_generations"], receipt["unsafe_registrations"])
        self.assertEqual(receipt["alive_before_controller_kill"], receipt["unsafe_registrations"])
        self.assertTrue(receipt["cleanup_errors"])
        for error in receipt["cleanup_errors"]:
            self.assertEqual(error["type"], "CustodyError")
            self.assertEqual(error["error"], "injected per-registration verification refusal")
            self.assertEqual([error["pid"], error["start_ticks"]], receipt["unsafe_registrations"][0])
        self.assertEqual(sum(row["reaped"] for row in receipt["registrations"]), 8)
        print(json.dumps({"expected_failed_custody_receipt": {
            key: receipt[key] for key in ("status", "code", "cleanup_errors",
                                         "unsafe_registrations", "surviving_generations")},
                          "other_owned_children_reaped": 8, "fixture_injection_removed_and_reaped": True}))

    def test_changed_generation_cannot_be_signalled(self):
        from unittest.mock import Mock
        supervisor = custody.Supervisor.__new__(custody.Supervisor)
        supervisor.alive = Mock(return_value=True)
        record = {"pid": 123, "start_ticks": 456, "pidfd": 7, "signals": []}
        with patch.object(custody, "identity", return_value={"pid": 123, "start_ticks": 457}), \
                patch.object(custody.signal, "pidfd_send_signal") as send:
            with self.assertRaisesRegex(custody.CustodyError, "changed owned PID generation"):
                supervisor.send(record, signal.SIGKILL)
            send.assert_not_called()


class VisibleBusyAccounting(unittest.TestCase):
    def test_busy_excludes_steal_iowait_and_does_not_add_guest_again(self):
        with patch.object(visible_cpu.Path, "open", return_value=io.StringIO(
                "cpu 100 1 20 300 10 2 3 5 80 7\n")), \
                patch.object(visible_cpu.Path, "read_text", return_value="0-3"), \
                patch.object(visible_cpu.time, "monotonic_ns", side_effect=[1, 2]):
            after = visible_cpu.capture()
        after.update(read_start_ns=2000000001, read_end_ns=2000000002)
        before = {"ticks": [0] * 8, "read_start_ns": 0, "read_end_ns": 1,
                  "online_cpu_ids": "0-3",
                  "ticks_per_second": after["ticks_per_second"]}
        result = visible_cpu.delta(before, after, 2, 2000000000, 4)
        self.assertEqual(result["busy_cpu_seconds"], 126 / after["ticks_per_second"])
        self.assertEqual(result["steal_seconds_excluded"], 5 / after["ticks_per_second"])
        self.assertFalse(result["owned_detail_added"])
        self.assertFalse(result["background_subtracted"])
        self.assertEqual(len(after["ticks"]), 8)

    def test_sensitivity_bounds_include_denominator_uncertainty(self):
        old = matrices()[0]["rows"][0]
        new = copy.deepcopy(old)
        old["visible_host_cpu"]["precision_cpu_seconds_bound"] = 0
        new["visible_host_cpu"]["precision_cpu_seconds_bound"] = 0
        background = {"one_core_rate_upper": .1 / 6 * .1}
        result = visible_cpu.sensitivity_bounds(old, new, background, .95, .95)
        self.assertGreater(result["conservative_upper_ratio"], 1.05)
        self.assertFalse(result["background_subtracted"])
        background["one_core_rate_upper"] *= 11
        result = visible_cpu.sensitivity_bounds(old, new, background, .95, .95)
        self.assertIsNone(result["conservative_upper_ratio"])
        self.assertFalse(result["background_subtracted"])

    def test_reset_and_unbracketed_completed_windows_are_rejected(self):
        before = {"ticks": [1] * 8, "read_start_ns": 0, "read_end_ns": 10, "ticks_per_second": 100}
        after = {"ticks": [2] * 8, "read_start_ns": 100, "read_end_ns": 110, "ticks_per_second": 100}
        for start, stop in ((9, 90), (11, 101)):
            with self.assertRaises(ValueError):
                visible_cpu.delta(before, after, start, stop, 4)
        after["ticks"][0] = 0
        with self.assertRaisesRegex(ValueError, "reset"):
            visible_cpu.delta(before, after, 11, 90, 4)


if __name__ == "__main__":
    unittest.main()
