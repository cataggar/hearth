import importlib.util
import base64
import contextlib
from copy import deepcopy
import gzip
import io
import json
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("eventfd_runner", Path(__file__).with_name("run.py"))
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)

sys.path.insert(0, str(Path(__file__).parent))
import matrix
import performance
import probe_jail
import restore_stress


class EvidenceTests(unittest.TestCase):
    def test_explicit_owned_roster_handles_named_elf_and_rejects_stale_generation(self):
        process = subprocess.Popen([sys.executable, "-c", "import signal; signal.pause()"])
        try:
            stat = Path(f"/proc/{process.pid}/stat").read_text()
            start = int(stat[stat.rfind(")") + 2:].split()[19])
            command = [sys.executable, "-c", probe_jail.INSPECT, str(process.pid), str(process.pid)]
            rows = json.loads(subprocess.check_output([*command, str(start)], timeout=3))
            self.assertTrue(rows)
            self.assertTrue(all(row["pid"] == process.pid and int(row["start_ticks"]) == start for row in rows))
            self.assertEqual(json.loads(subprocess.check_output([*command, str(start + 1)], timeout=3)), [])
            self.assertEqual(json.loads(subprocess.check_output(
                [sys.executable, "-c", probe_jail.INSPECT, str(process.pid)], timeout=3)), [])
        finally:
            process.terminate()
            process.wait(timeout=3)

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
        helper = HarnessReviewTests()
        helper.root = self.root
        args, manifest = helper.controls()
        directories = sorted(args.baselines.glob("aa-*"))
        for update, error, all_controls in (
            ({"minimum_nonidle_seconds": 1}, "sustained", True),
            ({"cpu_accounting": None}, "missing recorded", True),
            ({"binary_sha256": "different"}, "supplied binary", True),
            ({"cpus": [9]}, "mixed recorded control", False),
        ):
            with self.subTest(update=update):
                for directory in directories:
                    RUNNER.save_json(directory / "manifest.json", {
                        **manifest, **(update if directory == directories[0] or all_controls else {}),
                    })
                with self.assertRaisesRegex(ValueError, error):
                    performance.freeze(args)
                self.assertFalse(args.out.exists())

    def test_noise_or_changed_conditions_reject_candidate_before_vm_start(self):
        helper = HarnessReviewTests()
        helper.root = self.root
        controls, manifest = helper.controls()
        frozen = helper.freeze(controls)
        fixture, out = controls.fixture, self.root / "candidate"
        out.mkdir(mode=0o700)
        gates = self.root / "gates.json"
        args = SimpleNamespace(out=out, fixture=fixture, binary=controls.binary,
                               gates=gates, mode="C10", long_primary=False, minimum_seconds=5)
        for status, cpus, error in (
            ("noise-inconclusive", [8], "noise gates have not passed"),
            ("noise-provisionally-acceptable", [9], "frozen recorded execution conditions"),
        ):
            with self.subTest(status=status, cpus=cpus):
                RUNNER.save_json(gates, {
                    **frozen, "status": status,
                    "execution_identity": {**frozen["execution_identity"], "cpus": cpus},
                })
                digest = performance.bench.digest
                with patch.object(performance.os, "geteuid", return_value=1000), \
                     patch.object(performance.os, "sched_setaffinity"), \
                     patch.object(performance.bench, "digest",
                                  side_effect=lambda path: digest(path) if path.is_file() else "owned absent diagnostic"), \
                     patch.object(performance.subprocess, "run", return_value=SimpleNamespace(stdout=b"commit\n")), \
                     patch.object(performance.control.Guest, "__init__", side_effect=AssertionError("VM must not start")) as start_vm, \
                     contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(performance.child(args), 1)
                    start_vm.assert_not_called()
                result = json.loads((out / "result.json").read_text())
                self.assertEqual(result["status"], "failed")
                self.assertIn(error, result["errors"][0])


class HarnessReviewTests(unittest.TestCase):
    def setUp(self):
        self.root = RUNNER.ROOT / ".perf/eventfd" / f"harness-review-unit-{RUNNER.os.getpid()}"
        self.root.mkdir(parents=True, mode=0o700, exist_ok=False)
        self.processes = []
        self.guest = SimpleNamespace(connection=object())

    def tearDown(self):
        (self.root / "run-disk").unlink(missing_ok=True)
        for process in self.processes:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=3)
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
        shutil.rmtree(self.root)

    def disk_rpc(self, _, request):
        # Execute only the harness's own recipe, mapped to this owned fixture.
        # The unchanged guest jsonStr scans but does not unescape the wire value.
        command = json.dumps(request["cmd"])[1:-1].replace("/bin/busybox", shutil.which("busybox"))
        command = command.replace("/bench", str(self.root)).replace("/disk-load", str(self.root / "disk-load"))
        if command.endswith("printf STARTED"):
            # Retain a supervisor that joins the actual background child.
            process = subprocess.Popen(
                ["/bin/sh", "-c", command + '; code=$?; printf "\\n%d\\n" "$code"; wait; exit "$code"'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=self.root,
            )
            self.processes.append(process)
            stdout = process.stdout.readline().rstrip(b"\n")
            status = int(process.stdout.readline())
            return {"ok": True, "exit_code": status, "stdout": base64.b64encode(stdout).decode()}
        completed = subprocess.run(
            ["/bin/sh", "-c", command], capture_output=True, timeout=3, cwd=self.root,
        )
        stdout = completed.stdout.replace(str(self.root / "disk-load").encode(), b"/disk-load")
        return {"ok": True, "exit_code": completed.returncode, "stdout": base64.b64encode(stdout).decode()}

    def disk_script(self):
        script = self.root / "disk-load"
        script.write_text(
            f'#!/bin/sh\nwhile [ -f "{self.root}/run-disk" ]; do sleep .02; done\n'
            f'printf DISK-DONE >"{self.root}/disk-done"\n'
        )
        return script

    def launch_disk(self):
        (self.root / "run-disk").touch()
        script = self.disk_script()
        process = subprocess.Popen(
            ["/bin/sh", str(script)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self.processes.append(process)
        (self.root / "disk-pid").write_text(str(process.pid))
        return process

    def test_disk_barrier_checks_live_owned_generation_not_stale_flags(self):
        process = self.launch_disk()
        with patch.object(matrix.bench, "rpc", side_effect=self.disk_rpc):
            identity = matrix.disk_running(self.guest)
            self.assertEqual(identity["pid"], process.pid)
            self.assertEqual(matrix.disk_running(self.guest, identity), identity)
            with self.assertRaisesRegex(RuntimeError, "generation changed"):
                matrix.disk_running(self.guest, {**identity, "start_ticks": identity["start_ticks"] + 1})
            (self.root / "disk-pid").write_text(str(RUNNER.os.getpid()))
            with self.assertRaisesRegex(RuntimeError, "live disk-load shell"):
                matrix.disk_running(self.guest)
            (self.root / "disk-pid").write_text(str(process.pid))
            (self.root / "run-disk").unlink()
            process.wait(timeout=3)
            (self.root / "disk-done").unlink()
            (self.root / "run-disk").touch()
            with self.assertRaisesRegex(ValueError, "guest command failed"):
                matrix.disk_running(self.guest, identity)

    def test_disk_barrier_propagates_stopped_completed_and_invalid_pid_failures(self):
        self.launch_disk()
        with patch.object(matrix.bench, "rpc", side_effect=self.disk_rpc):
            for state in ("stopped", "completed", "invalid-pid"):
                with self.subTest(state=state):
                    if state == "stopped":
                        (self.root / "run-disk").unlink()
                    elif state == "completed":
                        (self.root / "disk-done").touch()
                    else:
                        (self.root / "disk-pid").write_text("not-a-pid")
                    with self.assertRaisesRegex(ValueError, "guest command failed"):
                        matrix.disk_running(self.guest)
                    if state == "stopped":
                        (self.root / "run-disk").touch()
                    elif state == "completed":
                        (self.root / "disk-done").unlink()

    def test_disk_start_does_not_replace_an_existing_owned_producer(self):
        process = self.launch_disk()
        with patch.object(matrix.bench, "rpc", side_effect=self.disk_rpc):
            with self.assertRaisesRegex(ValueError, "guest command failed"):
                matrix.start_disk(self.guest)
            self.assertEqual(matrix.disk_running(self.guest)["pid"], process.pid)

    def test_disk_start_records_the_child_and_runs_until_explicit_controller_stop(self):
        self.disk_script()
        with patch.object(matrix.bench, "rpc", side_effect=self.disk_rpc):
            identity = matrix.start_disk(self.guest)
            self.assertEqual(int((self.root / "disk-pid").read_text()), identity["pid"])
            self.assertEqual(matrix.disk_running(self.guest, identity), identity)
            (self.root / "run-disk").unlink()
            self.processes[0].wait(timeout=3)
            self.assertEqual((self.root / "disk-done").read_bytes(), b"DISK-DONE")
            with self.assertRaisesRegex(ValueError, "guest command failed"):
                matrix.disk_running(self.guest, identity)

    def disk_reply(self, command, pid=b"42", start=b"123", state=b"S"):
        stat = pid + b" (sh) " + b" ".join([state, *([b"0"] * 18), start])
        return {"ok": True, "exit_code": 0,
                "stdout": base64.b64encode(stat + b"\n\n" + command).decode()}

    def test_disk_start_propagates_injected_backend_failure_without_retry(self):
        failure = RuntimeError("injected backend failure")
        started = {"ok": True, "exit_code": 0, "stdout": base64.b64encode(b"STARTED").decode()}
        with patch.object(matrix.bench, "rpc", side_effect=[started, failure]) as rpc, \
             patch.object(matrix.time, "sleep") as sleep:
            with self.assertRaises(RuntimeError) as caught:
                matrix.start_disk(self.guest)
            self.assertIs(caught.exception, failure)
            self.assertEqual(rpc.call_count, 2)
            sleep.assert_not_called()

    def test_disk_start_retries_only_known_pre_exec_child_and_fences_its_generation(self):
        started = {"ok": True, "exit_code": 0, "stdout": base64.b64encode(b"STARTED").decode()}
        pending = self.disk_reply(b"/bin/sh\0-c\0" + matrix.DISK_START_COMMAND.encode() + b"\0")
        ready = self.disk_reply(b"/bin/sh\0/disk-load\0")
        with patch.object(matrix.bench, "rpc", side_effect=[started, pending, ready]), \
             patch.object(matrix.time, "sleep") as sleep:
            self.assertEqual(matrix.start_disk(self.guest), {"pid": 42, "start_ticks": 123})
            sleep.assert_called_once_with(.005)
        for bad, message in (
            (self.disk_reply(b"/bin/sh\0/wrong-load\0"), "live disk-load shell"),
            (self.disk_reply(b"/bin/sh\0/disk-load\0", pid=b"bad"), "invalid recorded"),
            (self.disk_reply(b"/bin/sh\0/disk-load\0", state=b"Z"), "live disk-load shell"),
            (self.disk_reply(b"/bin/sh\0/disk-load\0", start=b"124"), "generation changed"),
        ):
            with self.subTest(message=message), \
                 patch.object(matrix.bench, "rpc", side_effect=[started, pending, bad]) as rpc, \
                 patch.object(matrix.time, "sleep") as sleep:
                with self.assertRaisesRegex(RuntimeError, message):
                    matrix.start_disk(self.guest)
                self.assertEqual(rpc.call_count, 3)
                sleep.assert_called_once_with(.005)
        with patch.object(matrix.bench, "rpc", return_value=pending):
            with self.assertRaisesRegex(RuntimeError, "live disk-load shell"):
                matrix.disk_running(self.guest)

    def test_disk_start_exec_retry_has_bounded_startup_deadline(self):
        started = {"ok": True, "exit_code": 0, "stdout": base64.b64encode(b"STARTED").decode()}
        pending = self.disk_reply(b"/bin/sh\0-c\0" + matrix.DISK_START_COMMAND.encode() + b"\0")
        with patch.object(matrix.bench, "rpc", side_effect=[started, pending]), \
             patch.object(matrix.time, "monotonic", side_effect=[0, 5]), \
             patch.object(matrix.time, "sleep") as sleep:
            with self.assertRaises(matrix.DiskProducerExecPending):
                matrix.start_disk(self.guest)
            sleep.assert_not_called()

    def test_restart_waits_for_actual_owned_process_exit_before_relaunch(self):
        processes = [subprocess.Popen([sys.executable, "-c", "import signal; signal.pause()"])
                     for _ in range(2)]
        self.processes.extend(processes)
        launched = self.root / "relaunch"
        def rpc(_, request):
            command = json.dumps(request["cmd"])[1:-1].replace("/bin/busybox", shutil.which("busybox"))
            command = command.replace("/bench", str(self.root))
            for name in ("vsock", "tcp"):
                app = self.root / ("native-" + name)
                app.write_text(f"#!/bin/sh\necho {name} >>{launched}\n")
                app.chmod(0o700)
                command = command.replace("/native-" + name, str(app))
            completed = subprocess.run(["/bin/sh", "-c", command + "; wait"], capture_output=True, timeout=8)
            return {"ok": True, "exit_code": completed.returncode,
                    "stdout": base64.b64encode(completed.stdout).decode()}
        with patch.object(matrix.bench, "rpc", side_effect=rpc):
            restore_stress.restart_native_apps(self.guest, [str(process.pid).encode() for process in processes])
        for process in processes:
            self.assertEqual(process.wait(timeout=3), -9)
        self.assertEqual(set(launched.read_text().split()), {"vsock", "tcp"})
        with patch.object(matrix.bench, "rpc") as rpc:
            with self.assertRaisesRegex(ValueError, "invalid recorded"):
                restore_stress.restart_native_apps(self.guest, [b"2", b"2"])
            rpc.assert_not_called()

    def fixture(self):
        kernel = self.root / "kernel"
        kernel.write_bytes(b"owned kernel fixture")
        for name in ("agent", "vsock", "tcp", "disk-probe"):
            (self.root / name).write_bytes(f"owned {name} fixture".encode())
        fixture = self.root / "fixture"
        with patch.object(matrix.bench, "KERNEL_SHA256", RUNNER.digest(kernel)):
            matrix.prepare(SimpleNamespace(
                out=fixture, kernel=kernel, agent=self.root / "agent", native=self.root / "vsock",
                tcp=self.root / "tcp", disk_probe=self.root / "disk-probe",
                vsock_only=False, profile_only=False,
            ))
        return fixture

    def rewrite_fixture_init(self, fixture, init):
        metadata = json.loads((fixture / "fixture.json").read_text())
        entries = [("init", init, 0o100755)]
        entries += [(name, (self.root / source).read_bytes(), 0o100755)
                    for name, source in (("native-vsock", "vsock"), ("native-tcp", "tcp"))]
        entries.append(("TRAILER!!!", b"", 0))
        archive = b"".join(RUNNER.newc_entry(*entry, index + 1) for index, entry in enumerate(entries))
        (fixture / "init").write_bytes(init)
        (fixture / "initrd.cpio.gz").write_bytes(gzip.compress(archive, mtime=0))
        metadata.update(init_sha256=RUNNER.digest(fixture / "init"),
                        initrd_sha256=RUNNER.digest(fixture / "initrd.cpio.gz"))
        RUNNER.save_json(fixture / "fixture.json", metadata)

    def test_current_matrix_fixture_preparation_is_idempotent_and_replaces_tcp(self):
        fixture = self.fixture()
        original_init = (fixture / "init").read_bytes()
        original_archive = (fixture / "initrd.cpio.gz").read_bytes()
        first, second = self.root / "first", self.root / "second"
        restore_stress.prepare(SimpleNamespace(prepare_from=fixture, out=first, tcp_binary=None))
        restore_stress.prepare(SimpleNamespace(prepare_from=first, out=second, tcp_binary=None))
        self.assertEqual((first / "init").read_bytes(), original_init)
        self.assertEqual((second / "init").read_bytes(), original_init)
        self.assertEqual((second / "initrd.cpio.gz").read_bytes(), original_archive)
        replacement = self.root / "replacement-tcp"
        replacement.write_bytes(b"owned replacement TCP payload")
        replaced = self.root / "replaced"
        restore_stress.prepare(SimpleNamespace(prepare_from=fixture, out=replaced, tcp_binary=replacement))
        metadata = json.loads((replaced / "fixture.json").read_text())
        self.assertEqual(metadata["sources_sha256"]["native-tcp"], RUNNER.digest(replacement))
        self.assertIn(replacement.read_bytes(), gzip.decompress((replaced / "initrd.cpio.gz").read_bytes()))
        self.assertEqual(metadata["boot_args"], "console=ttyS0 nokaslr reboot=t panic=1 pci=off nomodules")

    def test_old_fixture_normalizes_once_and_ambiguous_startup_fails(self):
        fixture = self.fixture()
        current = (fixture / "init").read_bytes()
        old = current.replace(
            b"/native-vsock &\necho $! >/bench/vsock-pid\n/native-tcp &\necho $! >/bench/tcp-pid\n",
            b"/native-vsock &\n/native-tcp &\n",
        )
        self.rewrite_fixture_init(fixture, old)
        normalized = self.root / "normalized"
        restore_stress.prepare(SimpleNamespace(prepare_from=fixture, out=normalized, tcp_binary=None))
        self.assertEqual((normalized / "init").read_bytes(), current)
        again = self.root / "again"
        restore_stress.prepare(SimpleNamespace(prepare_from=normalized, out=again, tcp_binary=None))
        self.assertEqual((again / "initrd.cpio.gz").read_bytes(), (normalized / "initrd.cpio.gz").read_bytes())
        for malformed in (
            old.replace(b"/native-tcp &", b"/native-tcp --unknown &"),
            current + b"/native-tcp &\n",
            old.replace(b"/native-vsock &\n", b"/native-vsock &\necho $! >/bench/vsock-pid\n"),
            old.replace(b"/native-vsock &", b"# /native-vsock &"),
        ):
            with self.subTest(init=malformed):
                self.rewrite_fixture_init(fixture, malformed)
                out = self.root / "rejected"
                with self.assertRaisesRegex(ValueError, "unknown or ambiguous"):
                    restore_stress.prepare(SimpleNamespace(prepare_from=fixture, out=out, tcp_binary=None))
                self.assertFalse(out.exists())

    def controls(self):
        fixture = self.fixture()
        binary = self.root / "binary"
        binary.write_bytes(b"owned control binary A")
        digest = lambda text: RUNNER.hashlib.sha256(text.encode()).hexdigest()
        manifest = {
            "binary_sha256": RUNNER.digest(binary), "fixture": json.loads((fixture / "fixture.json").read_text()),
            "mode": "C00", "cpus": [8], "client_cpus": [1], "vcpus": 1, "ram_mib": 512,
            "host_kernel": "owned host kernel", "host_arch": "x86_64", "host_provenance": "owned nested host",
            "non_nested_host": "unavailable", "pmu": "software fallback", "guest_pmu": "hidden",
            "compiler": "Zig0.17 static x86_64-linux-musl ReleaseSafe",
            "backends": "synchronous block, userspace TAP, native vsock",
            "storage": "fresh raw disk; QD1; host caches unchanged", "network": "private MTU1500/offloads0",
            "warmup": "checked traffic then silence", "samples": "17 fixed workload cells",
            "agent_poll_ms": 50, "heartbeat_ms": 0, "disk_seed": "0x31415926",
            "runner_sha256": RUNNER.digest(Path(performance.__file__)),
            "control_sha256": digest("control"), "observer_sha256": digest("observer"),
            "observer_object_sha256": digest("observer object"),
            "source_commit": "6c218b0a68a4d1bfd820852c56b39c501fb1ae4b",
            "source_files_sha256": {"vmm/src/main.zig": digest("owned source")},
            "started_unix": 1, "long_primary": False, "accounting": "all owned tasks plus irqfd work",
            "minimum_nonidle_seconds": 5, "cpu_accounting": "all owned task schedstat nanoseconds",
        }
        source = self.root / "controls"
        source.mkdir(mode=0o700)
        for index in range(5):
            directory = source / f"aa-{index}"
            directory.mkdir(mode=0o700)
            RUNNER.save_json(directory / "manifest.json", {**manifest, "started_unix": index,
                                                         "out": str(directory), "argv": [str(binary)]})
            RUNNER.save_json(directory / "result.json", {
                "status": "passed", "mode": "C00", "rows": [
                    {"name": name, "cpu_per_operation": 1, "latency": {"p95": 1},
                     "bytes": 4096, "bytes_per_second": 4096} for name in performance.WORKLOADS
                ],
            })
        return SimpleNamespace(baselines=source, binary=binary, fixture=fixture,
                               out=self.root / "gates.json"), manifest

    def freeze(self, args):
        with contextlib.redirect_stdout(io.StringIO()):
            performance.freeze(args)
        return json.loads(args.out.read_text())

    def test_verified_control_identity_allows_only_mode_time_and_location_variation(self):
        args, manifest = self.controls()
        recorded = args.baselines / "aa-4/manifest.json"
        relocated = deepcopy(manifest)
        relocated["fixture"]["kernel"] = "some/older/control/kernel-location"
        RUNNER.save_json(recorded, relocated)
        gates = self.freeze(args)
        self.assertEqual(gates["status"], "noise-provisionally-acceptable")
        self.assertEqual(gates["binary_sha256"], manifest["binary_sha256"])
        self.assertEqual(len(gates["baseline_manifest_sha256"]), 5)
        candidate = {**manifest, "mode": "C11", "started_unix": 100, "out": "different/run"}
        kernel_copy = self.root / "kernel-copy"
        shutil.copyfile(self.root / "kernel", kernel_copy)
        metadata = deepcopy(manifest["fixture"])
        metadata["kernel"] = str(kernel_copy.relative_to(RUNNER.ROOT))
        RUNNER.save_json(args.fixture / "fixture.json", metadata)
        candidate["fixture"] = metadata
        performance.validate_candidate_gates(gates, candidate, args.binary, args.fixture)

    def test_freeze_rejects_stale_supplied_binary_fixture_and_archive(self):
        args, _ = self.controls()
        for artifact in ("binary", "fixture", "initrd", "kernel"):
            with self.subTest(artifact=artifact):
                path = {
                    "binary": args.binary, "fixture": args.fixture / "fixture.json",
                    "initrd": args.fixture / "initrd.cpio.gz", "kernel": self.root / "kernel",
                }[artifact]
                original = path.read_bytes()
                if artifact == "fixture":
                    metadata = json.loads(original)
                    metadata["diagnostic_heartbeat_ms"] = 10
                    RUNNER.save_json(path, metadata)
                else:
                    path.write_bytes(b"different supplied artifact B")
                with self.assertRaisesRegex(ValueError, "supplied (binary|fixture)"):
                    self.freeze(args)
                self.assertFalse(args.out.exists())
                path.write_bytes(original)

    def test_freeze_rejects_mixed_recorded_control_artifacts_and_fixed_conditions(self):
        args, manifest = self.controls()
        path = args.baselines / "aa-4/manifest.json"
        differences = {
            "binary_sha256": "f" * 64, "source_commit": "a" * 40, "compiler": "other compiler",
            "source_files_sha256": {"vmm/src/main.zig": "b" * 64},
            "cpus": [9], "client_cpus": [2], "ram_mib": 1024, "host_provenance": "other host",
            "storage": "dropped host caches", "network": "offloads enabled",
            "cache_policy": "different additionally recorded cache policy",
            "warmup": "no warmup", "heartbeat_ms": 10, "long_primary": True,
            "fixture": {**manifest["fixture"], "initrd_sha256": "c" * 64},
        }
        for field, value in differences.items():
            with self.subTest(field=field):
                RUNNER.save_json(path, {**manifest, field: value})
                with self.assertRaisesRegex(ValueError, "mixed recorded control"):
                    self.freeze(args)
                self.assertFalse(args.out.exists())

    def test_freeze_rejects_missing_recorded_control_provenance(self):
        args, manifest = self.controls()
        path = args.baselines / "aa-4/manifest.json"
        for field in ("source_commit", "compiler", "source_files_sha256", "fixture", "storage", "cpus"):
            with self.subTest(field=field):
                missing = {key: value for key, value in manifest.items() if key != field}
                RUNNER.save_json(path, missing)
                with self.assertRaisesRegex(ValueError, "missing recorded execution provenance"):
                    self.freeze(args)
                self.assertFalse(args.out.exists())
        for field, value in (("compiler", ""), ("source_commit", ""), ("source_files_sha256", {}),
                             ("cpus", []), ("fixture", {**manifest["fixture"], "initrd_sha256": ""})):
            with self.subTest(field=field, empty=True):
                RUNNER.save_json(path, {**manifest, field: value})
                with self.assertRaisesRegex(ValueError, "missing recorded"):
                    self.freeze(args)
                self.assertFalse(args.out.exists())
        path.unlink()
        with self.assertRaisesRegex(ValueError, "missing recorded control manifest"):
            self.freeze(args)

    def test_candidate_rejects_stale_artifacts_conditions_and_unqualified_old_gates(self):
        args, manifest = self.controls()
        gates = self.freeze(args)
        candidate = {**manifest, "mode": "C10"}
        for field, value in (
            ("binary_sha256", "a" * 64), ("compiler", "other compiler"),
            ("cpus", [9]), ("storage", "changed caches"), ("long_primary", True),
            ("cache_policy", "different additionally recorded cache policy"),
        ):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "supplied binary|frozen recorded execution conditions"):
                    performance.validate_candidate_gates(gates, {**candidate, field: value}, args.binary, args.fixture)
        original = args.binary.read_bytes()
        args.binary.write_bytes(b"candidate B pretending to be control A")
        with self.assertRaisesRegex(ValueError, "supplied binary"):
            performance.validate_candidate_gates(gates, candidate, args.binary, args.fixture)
        args.binary.write_bytes(original)
        old = {"binary_sha256": RUNNER.digest(args.binary),
               "fixture_sha256": RUNNER.digest(args.fixture / "fixture.json")}
        with self.assertRaisesRegex(ValueError, "historical gates are unqualified"):
            performance.validate_candidate_gates(old, candidate, args.binary, args.fixture)


if __name__ == "__main__":
    unittest.main()
