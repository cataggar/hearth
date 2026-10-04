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
runtime_spec = importlib.util.spec_from_file_location(
    "perf_native_runtime", Path(__file__).with_name("perf-zig-native-runtime.py")
)
runtime_runner = importlib.util.module_from_spec(runtime_spec)
runtime_spec.loader.exec_module(runtime_runner)


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

    def test_build_measurement_rejects_test_execution(self):
        specification = {
            "component": "vmm", "mode": "safe", "steps": ["integration-test"],
        }
        with self.assertRaisesRegex(ValueError, "must not execute tests"):
            runner.build_argv(specification, {"codegen": "llvm", "linker": "lld"})

    def test_incremental_patch_rejects_ambiguous_or_unchanged_source(self):
        for original, change in (
            (b"x x", {"before": "x", "after": "y"}),
            (b"x", {"before": "x", "after": "x"}),
        ):
            with self.subTest(original=original, change=change), self.assertRaises(ValueError):
                runner.incremental_source(original, change)

    def test_build_failure_restores_incremental_source(self):
        manifest = self.output / "build-manifest.json"
        original = (runner.ROOT / "vmm/src/main.zig").read_bytes()
        manifest.write_text(json.dumps({
            "component": "vmm", "mode": "safe", "target": "x86_64-linux",
            "compiler": {"path": sys.executable, "sha256": runner.sha256(Path(sys.executable))},
            "source_hashes": {}, "steps": ["install"], "jobs": 1, "affinity": [0],
            "observer_affinity": sorted(os.sched_getaffinity(0)), "repeats": 10,
            "variants": [
                {"id": "a", "codegen": "llvm", "linker": "lld"},
                {"id": "b", "codegen": "llvm", "linker": "lld"},
            ],
            "conditions": ["cold", "warm", "incremental"], "minimum_free_bytes": 0,
            "timeout_seconds": 10,
            "incremental_patch": {
                "file": "src/main.zig", "before": "DEFAULT_MEM_SIZE = 512",
                "after": "DEFAULT_MEM_SIZE = 513",
            },
        }))

        def fake_build(argv, cwd, output, env, timeout):
            output.mkdir()
            binary = cwd / "zig-out/bin/flint"
            binary.parent.mkdir(parents=True, exist_ok=True)
            binary.write_bytes(b"owned fake executable")
            return {"exit_code": 7 if output.name == "incremental" else 0}

        output = self.output / "failed-build"
        with patch.object(runner, "run_command", side_effect=fake_build), \
                patch.object(runner.subprocess, "run"), patch.object(runner.fcntl, "flock"):
            with self.assertRaisesRegex(RuntimeError, "build failed"):
                runner.build_measurements(manifest, output, self.output / "build-lock")
        self.assertEqual((output / "r00-v0/source/src/main.zig").read_bytes(), original)
        self.assertEqual((runner.ROOT / "vmm/src/main.zig").read_bytes(), original)
        self.assertEqual(json.loads((output / "results.json").read_text())[-1]["exit_code"], 7)
        retained = (output / "results.json").read_bytes()
        with patch.object(runner.fcntl, "flock"), self.assertRaisesRegex(
            ValueError, "complete paired repetitions",
        ):
            runner.build_measurements(manifest, output, self.output / "build-lock", resume=True)
        self.assertEqual((output / "results.json").read_bytes(), retained)

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

    def test_pty_exit_is_not_a_completed_numbered_operation(self):
        machine = MagicMock()
        with patch.object(runtime_runner.vm, "send"), patch.object(
            runtime_runner.vm, "receive", return_value={"type": "exit", "code": 0},
        ):
            with self.assertRaisesRegex(RuntimeError, "before its numbered ACK"):
                runtime_runner.pty_samples(machine, 1)

    def test_profiled_shutdown_lets_collector_flush_after_owned_vmm_exit(self):
        machine = vm_runner.Vm.__new__(vm_runner.Vm)
        machine.jailed = True
        machine.collector = ["stat"]
        machine.process = MagicMock(pid=4000)
        machine.jail_status = {"pid": 4001}
        with patch.object(vm_runner.subprocess, "run") as execute:
            machine.signal("TERM")
        self.assertEqual(execute.call_args.args[0][-1], "4001")

    def test_snapshot_archives_preserve_exact_bytes_before_owned_deletion(self):
        folder = self.output / "archive"
        folder.mkdir()
        source = folder / "memory.snap"
        source.write_bytes(b"owned snapshot contents" * 100)
        digest = runner.sha256(source)
        runtime_runner.compact_snapshots(folder)
        self.assertFalse(source.exists())
        manifest = json.loads((folder / "snapshot-archives.json").read_text())
        self.assertEqual(manifest[0]["sha256"], digest)
        with runtime_runner.gzip.open(folder / "memory.snap.gz", "rb") as stream:
            self.assertEqual(stream.read(), b"owned snapshot contents" * 100)

    def test_cache_archival_preserves_symlinks_and_hardlinked_contents(self):
        cell = self.output / "cache-archive"
        (cell / "global").mkdir(parents=True)
        (cell / "local").mkdir()
        source = cell / "global/object"
        source.write_bytes(b"owned immutable cached object")
        os.link(source, cell / "local/object")
        (cell / "global/alias").symlink_to("object")
        runner.archive_artifact_caches(cell)
        self.assertFalse((cell / "global").exists())
        self.assertFalse((cell / "local").exists())
        inventory = json.loads((cell / "cache-inventory.json").read_text())
        self.assertEqual(inventory["files"]["global/object"], inventory["files"]["local/object"])
        self.assertEqual(inventory["symlinks"]["global/alias"], "object")

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

    def test_jail_verification_rejects_wrong_uid_groups_or_unenforced_filter(self):
        vm = vm_runner.Vm.__new__(vm_runner.Vm)
        vm.process = MagicMock(pid=4321)
        entry = MagicMock()
        entry.name = "4322"
        for uid, groups, seccomp in ((0, "", 2), (os.getuid(), "0", 2), (os.getuid(), "", 0)):
            with self.subTest(uid=uid, groups=groups, seccomp=seccomp):
                def read_child(name):
                    value = MagicMock()
                    value.read_text.return_value = (
                        "4322 (flint) S 4321 4321"
                        if name == "stat" else
                        f"Name:\tflint\nUid:\t{uid} {uid} {uid} {uid}\n"
                        f"Gid:\t{os.getgid()} {os.getgid()} {os.getgid()} {os.getgid()}\n"
                        f"Groups:\t{groups}\nCapEff:\t0000000000000000\n"
                        f"NoNewPrivs:\t1\nSeccomp:\t{seccomp}\n"
                    )
                    return value
                entry.__truediv__.side_effect = read_child
                with patch.object(vm_runner, "Path") as proc:
                    proc.return_value.iterdir.return_value = [entry]
                    with self.assertRaisesRegex(RuntimeError, "incorrect credentials or unenforced jail"):
                        vm.verify_jail()

    def test_vm_setup_failure_removes_owned_socket_directory(self):
        output = self.output / "vm-setup-failure"
        output.mkdir()
        with patch.object(vm_runner.shutil, "copyfile", side_effect=FileNotFoundError("disk missing")):
            with self.assertRaisesRegex(FileNotFoundError, "disk missing"):
                vm_runner.Vm(
                    self.output / "missing-vmm", output, self.output / "kernel",
                    self.output / "initrd", self.output / "disk", 0, jailed=True,
                )
        self.assertEqual(list((runner.ROOT / ".perf-zig-native" / "s").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
