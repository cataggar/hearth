import importlib.util
import os
import json
from pathlib import Path
import sys
import socket
import struct
import unittest
from unittest.mock import MagicMock, patch


spec = importlib.util.spec_from_file_location(
    "perf_zig_native", Path(__file__).with_name("perf-zig-native.py")
)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
vm_spec = importlib.util.spec_from_file_location(
    "perf_zig_native_vm", Path(__file__).with_name("perf-zig-native-vm.py")
)
vm_runner = importlib.util.module_from_spec(vm_spec)
vm_spec.loader.exec_module(vm_runner)


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output = runner.ROOT / ".perf-zig-native" / "runner-tests" / str(os.getpid())
        cls.output.mkdir(parents=True, exist_ok=False)

    def test_rejects_paths_outside_worktree(self):
        with self.assertRaises(ValueError):
            runner.project_path("../another-worktree")

    def test_preserves_failed_command_and_arguments(self):
        output = self.output / "failure"
        result = runner.run_command(
            [sys.executable, "-c", "import sys; print(sys.argv[1]); sys.exit(7)", "not; a shell"],
            runner.ROOT, output, {}, timeout=10,
        )
        self.assertEqual(result["exit_code"], 7)
        self.assertEqual((output / "stdout.log").read_text().strip(), "not; a shell")
        self.assertGreater(result["tree_user_seconds"] + result["tree_system_seconds"], 0)

    def test_timeout_is_not_success(self):
        result = runner.run_command(
            [sys.executable, "-c", "import time; time.sleep(10)"],
            runner.ROOT, self.output / "timeout",
            {}, timeout=0.05,
        )
        self.assertTrue(result["timed_out"])
        self.assertNotEqual(result["exit_code"], 0)

    def test_cpu_accounts_waited_descendant(self):
        result = runner.run_command(
            [sys.executable, "-c",
             "import subprocess, sys; subprocess.run([sys.executable, '-c', "
             "'import time; end=time.process_time()+0.15\\nwhile time.process_time()<end: pass'])"],
            runner.ROOT, self.output / "descendant",
            {}, timeout=10,
        )
        self.assertEqual(result["exit_code"], 0)
        self.assertGreaterEqual(result["tree_user_seconds"] + result["tree_system_seconds"], 0.15)
        self.assertGreater(len(result["observed_pids"]), 1)

    def test_refuses_evidence_overwrite(self):
        output = self.output / "existing"
        output.mkdir(parents=True)
        (output / "metrics.json").write_text("{}")
        with self.assertRaises(ValueError):
            runner.run_command([sys.executable, "-c", "pass"], runner.ROOT, output, {}, timeout=10)

    def test_batch_rejects_changed_source_before_execution(self):
        manifest = self.output / "manifest.json"
        manifest.write_text(json.dumps({
            "compiler": {"path": sys.executable, "sha256": runner.sha256(Path(sys.executable))},
            "source_hashes": {"vmm/build.zig": "incorrect hash"},
            "commands": [],
        }))
        with self.assertRaisesRegex(ValueError, "source identity changed"):
            runner.batch(manifest, self.output / "batch", self.output / "lock")

    def test_batch_refuses_summary_overwrite(self):
        manifest = self.output / "empty-manifest.json"
        manifest.write_text(json.dumps({
            "compiler": {"path": sys.executable, "sha256": runner.sha256(Path(sys.executable))},
            "source_hashes": {},
            "commands": [],
            "phase_timeout_seconds": 10,
        }))
        output = self.output / "existing-batch"
        output.mkdir()
        (output / "results.json").write_text("preserve")
        with self.assertRaises(FileExistsError):
            runner.batch(manifest, output, self.output / "batch-lock")
        self.assertEqual((output / "results.json").read_text(), "preserve")

    def test_guest_frames_are_not_coalesced(self):
        left, right = socket.socketpair()
        try:
            vm_runner.send(left, {"ok": True, "first": 1})
            vm_runner.send(left, {"ok": True, "second": 2})
            self.assertEqual(vm_runner.receive(right), {"ok": True, "first": 1})
            self.assertEqual(vm_runner.receive(right), {"ok": True, "second": 2})
        finally:
            left.close()
            right.close()

    def test_guest_truncated_frame_fails(self):
        left, right = socket.socketpair()
        try:
            left.sendall(struct.pack("<I", 4) + b"{")
            left.close()
            with self.assertRaisesRegex(RuntimeError, "channel closed"):
                vm_runner.receive(right)
        finally:
            left.close()
            right.close()

    def test_fixture_pipeline_cleans_child_if_compressor_missing(self):
        agent = self.output / "agent"
        init = self.output / "init"
        agent.write_text("agent")
        init.write_text("init")
        child = MagicMock()
        child.poll.return_value = None
        with patch.object(
            vm_runner.shutil, "copy2",
            side_effect=lambda source, destination: Path(destination).write_bytes(b"fixture"),
        ), patch.object(
            vm_runner.subprocess, "Popen", side_effect=[child, FileNotFoundError("gzip missing")]
        ):
            with self.assertRaisesRegex(FileNotFoundError, "gzip missing"):
                vm_runner.prepare([
                    "--agent", str(agent), "--init", str(init),
                    "--output", str(self.output / "pipeline-failure"),
                ])
        child.kill.assert_called_once()
        child.wait.assert_called_once()


if __name__ == "__main__":
    unittest.main()
