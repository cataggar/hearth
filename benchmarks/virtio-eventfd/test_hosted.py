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


def matrices():
    rows = [{
        "name": name, "status": "passed", "known_scoped_cpu_per_operation": .01,
        "known_scoped_cpu_seconds": .1, "operation_seconds": 60 if name == "idle" else 6,
        "latency": {"p95": 10}, "bytes": 0 if name in ("idle", "exec", "interactive", "lifecycle") else 4096,
        "bytes_per_second": 0 if name in ("idle", "exec", "interactive", "lifecycle") else 4096 / 6,
    } for name in performance.WORKLOADS]
    return [copy.deepcopy({"mode": "C00", "status": "passed", "rows": rows}) for _ in range(5)]


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
            samples[0]["rows"][0]["known_scoped_cpu_per_operation"] = bad
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
                        row["known_scoped_cpu_per_operation"] *= .8
                        if row["name"] == "lifecycle":
                            row["latency"]["p95"] *= 50
                block[mode] = sample
            blocks.append(block)
        report = hosted.compare(blocks)
        self.assertTrue(report["all_candidates_have_demonstrated_regression"])
        self.assertFalse(report["performance_merge_eligible"])
        self.assertFalse(report["full_kernel_accounting"])
        self.assertTrue(report["unexecuted_required_coverage"])
        for check in report["diagnostic_gate_checks"].values():
            self.assertTrue(check["known_primary_benefit_95_lower_at_least_10_percent"])
            self.assertFalse(check["qualified"])

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


class ObserverCleanup(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
