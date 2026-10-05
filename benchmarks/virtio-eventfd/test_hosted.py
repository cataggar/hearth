import contextlib
import copy
import io
import json
import math
import os
from pathlib import Path
import shutil
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import hosted
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
