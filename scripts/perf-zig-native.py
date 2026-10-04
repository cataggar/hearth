#!/usr/bin/env python3
"""Private, serialized command accounting for the native Zig experiment."""

import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import shutil
import statistics
import subprocess
import threading
import time


ROOT = Path(__file__).resolve().parents[1]
RUNNER_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def project_path(value):
    path = (ROOT / value).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError(f"path must be inside this worktree: {value}")
    return path


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def process_snapshot(root_pid):
    """Linux live tree RSS, including threads only once per address space."""
    processes = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text()
            fields = stat[stat.rfind(")") + 2:].split()
            processes[int(entry.name)] = (
                int(fields[1]), int(fields[21]) * os.sysconf("SC_PAGE_SIZE")
            )
        except (OSError, ValueError, IndexError):
            continue
    tree = {root_pid}
    while True:
        children = {pid for pid, (parent, _) in processes.items() if parent in tree}
        expanded = tree | children
        if expanded == tree:
            break
        tree = expanded
    return sum(processes[pid][1] for pid in tree if pid in processes), tree


def run_command(argv, cwd, output, env, timeout=900, sample_interval=0.02):
    """wait4 CPU includes descendants reaped by the child; RSS is sampled."""
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError(f"refusing to overwrite existing evidence: {output}")
    started = time.monotonic()
    peak_rss = 0
    observed_pids = set()
    samples = []
    timed_out = False
    stopped = threading.Event()
    with (output / "stdout.log").open("wb") as stdout, (output / "stderr.log").open("wb") as stderr:
        child = subprocess.Popen(
            argv, cwd=cwd, env=env, stdout=stdout, stderr=stderr, start_new_session=True
        )

        def sample():
            nonlocal peak_rss
            while not stopped.is_set():
                rss, pids = process_snapshot(child.pid)
                peak_rss = max(peak_rss, rss)
                observed_pids.update(pids)
                samples.append([time.monotonic() - started, rss, sorted(pids)])
                stopped.wait(sample_interval)

        def expire():
            nonlocal timed_out
            timed_out = True
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

        sampler = threading.Thread(target=sample, daemon=True)
        timer = threading.Timer(timeout, expire)
        sampler.start()
        timer.start()
        try:
            _, status, usage = os.wait4(child.pid, 0)
            child.returncode = os.waitstatus_to_exitcode(status)
            completed = time.monotonic()
        except BaseException:
            if child.returncode is None:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                _, status, _ = os.wait4(child.pid, 0)
                child.returncode = os.waitstatus_to_exitcode(status)
            raise
        finally:
            timer.cancel()
            stopped.set()
            sampler.join()
    result = {
        "argv": argv,
        "cwd": str(cwd.relative_to(ROOT)),
        "environment": {key: env[key] for key in (
            "ZIG_GLOBAL_CACHE_DIR", "ZIG_LOCAL_CACHE_DIR", "TMPDIR"
        ) if key in env},
        "exit_code": child.returncode,
        "timed_out": timed_out,
        "wall_seconds": completed - started,
        "wall_clock_method": "monotonic launch-to-blocking-wait4 completion; RSS sampler is independent",
        "runner_sha256": RUNNER_SHA256,
        "tree_user_seconds": usage.ru_utime,
        "tree_system_seconds": usage.ru_stime,
        "sampled_peak_tree_rss_bytes": peak_rss,
        "sample_interval_seconds": sample_interval,
        "observed_pids": sorted(observed_pids),
        "cpu_accounting": "wait4: child and descendants it reaps; excludes detached/unreaped workers",
        "rss_accounting": "sum live descendant process RSS; shared pages double counted; short-lived processes may be missed",
        "os_cache_policy": "uncontrolled host page cache; no global cache flush",
    }
    (output / "metrics.json").write_text(json.dumps(result, indent=2) + "\n")
    (output / "rss-samples.json").write_text(json.dumps(samples) + "\n")
    return result


def summarize(rows):
    result = {}
    for metric in (
        "wall_seconds", "tree_user_seconds", "tree_system_seconds", "sampled_peak_tree_rss_bytes"
    ):
        values = [row[metric] for row in rows]
        mean = statistics.mean(values)
        deviation = statistics.stdev(values) if len(values) > 1 else 0
        result[metric] = {
            "n": len(values), "median": statistics.median(values), "mean": mean,
            "stdev": deviation, "cv": deviation / mean if mean else None,
            "min": min(values), "max": max(values),
            "mean_95pct_normal_interval": [
                mean - 1.96 * deviation / math.sqrt(len(values)),
                mean + 1.96 * deviation / math.sqrt(len(values)),
            ],
        }
    return result


def batch(manifest, output, lock_path):
    manifest_bytes = manifest.read_bytes()
    specification = json.loads(manifest_bytes)
    manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()

    def verify_identity():
        if specification["compiler"]["sha256"] != sha256(Path(specification["compiler"]["path"])):
            raise ValueError("compiler byte identity changed")
        for name, digest in specification["source_hashes"].items():
            if sha256(project_path(name)) != digest:
                raise ValueError(f"source identity changed: {name}")

    rows = []
    with Path(lock_path).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        verify_identity()
        output.mkdir(parents=True, exist_ok=False)
        (output / "manifest.json").write_bytes(manifest_bytes)
        started = time.monotonic()
        for command in specification["commands"]:
            verify_identity()
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", command["id"]):
                raise ValueError("batch command id must be a simple filename")
            if time.monotonic() - started > specification["phase_timeout_seconds"]:
                raise TimeoutError("bounded batch phase expired")
            env = os.environ.copy()
            for variable, key in (
                ("ZIG_GLOBAL_CACHE_DIR", "global_cache"), ("ZIG_LOCAL_CACHE_DIR", "local_cache")
            ):
                cache = project_path(command[key])
                cache.mkdir(parents=True, exist_ok=True)
                env[variable] = str(cache)
            row = run_command(
                command["argv"], project_path(command["cwd"]),
                output / command["id"], env, command["timeout_seconds"],
            )
            row["id"] = command["id"]
            row["manifest_sha256"] = manifest_digest
            rows.append(row)
            if row["exit_code"] != 0:
                break
    (output / "results.json").write_text(json.dumps(rows, indent=2) + "\n")
    return rows


def main():
    os.umask(0o077)
    scratch = project_path(".perf-zig-native/scratch")
    scratch.mkdir(parents=True, exist_ok=True)
    os.environ["TMPDIR"] = str(scratch)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", default="/d/hearth/.perf/fleet/host.lock")
    commands = parser.add_subparsers(dest="operation", required=True)
    run = commands.add_parser("run", help="account one exact argv, preserving failures")
    run.add_argument("--cwd", required=True)
    run.add_argument("--output", required=True)
    run.add_argument("--global-cache", required=True)
    run.add_argument("--local-cache", required=True)
    run.add_argument("--timeout", type=float, default=900)
    run.add_argument("--artifact", action="append", default=[], help="worktree-relative output to retain on success")
    run.add_argument("argv", nargs=argparse.REMAINDER)
    summary = commands.add_parser("summarize")
    summary.add_argument("directories", nargs="+")
    probe = commands.add_parser("probe", help="record KVM and perf permissions without changing host state")
    probe.add_argument("--output", required=True)
    multiple = commands.add_parser("batch", help="bounded manifest argv phase under one lock")
    multiple.add_argument("--manifest", required=True)
    multiple.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.operation == "summarize":
        rows = [json.loads((project_path(path) / "metrics.json").read_text()) for path in args.directories]
        if any(row["exit_code"] != 0 for row in rows):
            raise SystemExit("cannot summarize failed commands as successful build measurements")
        print(json.dumps(summarize(rows), indent=2))
        return
    if args.operation == "batch":
        rows = batch(project_path(args.manifest), project_path(args.output), args.lock)
        passed = bool(rows) and all(row["exit_code"] == 0 for row in rows)
        print(json.dumps(summarize(rows) if passed else rows, indent=2))
        raise SystemExit(0 if passed else 1)
    if args.operation == "probe":
        output = project_path(args.output)
        output.mkdir(parents=True, exist_ok=False)
        results = {"uid": os.getuid(), "groups": os.getgroups()}
        with Path(args.lock).open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                fd = os.open("/dev/kvm", os.O_RDWR | os.O_CLOEXEC)
                try:
                    results["kvm_api"] = fcntl.ioctl(fd, 0xAE00, 0)
                    vm = fcntl.ioctl(fd, 0xAE01, 0)
                    os.close(vm)
                    results["kvm_create_vm"] = "passed"
                finally:
                    os.close(fd)
            except OSError as error:
                results["kvm_create_vm"] = str(error)
            perf = [
                ("software", ["perf", "stat", "-x,", "-e",
                              "task-clock,context-switches,cpu-migrations,page-faults",
                              "--", "sleep", "0.2"]),
                ("hardware", ["perf", "stat", "-e", "cycles,instructions", "--", "sleep", "0.2"]),
                ("kvm-events", ["perf", "stat", "-e", "kvm:kvm_entry,kvm:kvm_exit", "--", "sleep", "0.2"]),
                ("record", ["perf", "record", "-e", "cpu-clock", "-F", "199", "-g",
                            "--call-graph", "dwarf", "-o", str(output / "perf.data"), "--",
                            "python3", "-c", "import time; end=time.monotonic()+0.5\nwhile time.monotonic()<end: pass"]),
                ("report", ["perf", "report", "--stdio", "-i", str(output / "perf.data")]),
                ("sudo", ["sudo", "-n", "true"]),
            ]
            for name, argv in perf:
                with (output / f"{name}.stdout").open("wb") as stdout, (output / f"{name}.stderr").open("wb") as stderr:
                    try:
                        completed = subprocess.run(
                            argv, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=30, check=False
                        )
                        results[name] = {"argv": argv, "exit_code": completed.returncode}
                    except (OSError, subprocess.TimeoutExpired) as error:
                        results[name] = {"argv": argv, "error": str(error)}
            if results["sudo"].get("exit_code") == 0 and results["kvm-events"].get("exit_code") != 0:
                argv = ["sudo", "-n", "perf", "stat", "-e", "kvm:kvm_entry,kvm:kvm_exit", "--", "sleep", "0.2"]
                with (output / "privileged-kvm.stdout").open("wb") as stdout, (output / "privileged-kvm.stderr").open("wb") as stderr:
                    completed = subprocess.run(argv, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=30, check=False)
                    results["privileged-kvm-events"] = {"argv": argv, "exit_code": completed.returncode}
        (output / "results.json").write_text(json.dumps(results, indent=2) + "\n")
        print(json.dumps(results, indent=2))
        return
    argv = args.argv[1:] if args.argv and args.argv[0] == "--" else args.argv
    if not argv:
        parser.error("an executable argv is required")
    env = os.environ.copy()
    for key, value in (
        ("ZIG_GLOBAL_CACHE_DIR", args.global_cache), ("ZIG_LOCAL_CACHE_DIR", args.local_cache)
    ):
        path = project_path(value)
        path.mkdir(parents=True, exist_ok=True)
        env[key] = str(path)
    cwd = project_path(args.cwd)
    output = project_path(args.output)
    with Path(args.lock).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        result = run_command(argv, cwd, output, env, args.timeout)
        if result["exit_code"] == 0:
            artifacts = []
            for value in args.artifact:
                artifact = project_path(value)
                retained = output / artifact.name
                if retained.exists():
                    raise ValueError(f"duplicate retained artifact: {retained}")
                shutil.copy2(artifact, retained)
                artifacts.append({
                    "path": value, "sha256": sha256(retained), "bytes": retained.stat().st_size
                })
                with (output / f"{artifact.name}.elf.txt").open("wb") as stream:
                    subprocess.run(
                        ["readelf", "-h", "-l", "-S", "-p", ".comment", str(retained)],
                        stdout=stream, stderr=subprocess.STDOUT, check=True,
                    )
            result["artifacts"] = artifacts
            (output / "metrics.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "observed_pids"}, indent=2))
    raise SystemExit(result["exit_code"] if result["exit_code"] >= 0 else 1)


if __name__ == "__main__":
    main()
