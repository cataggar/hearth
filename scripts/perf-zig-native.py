#!/usr/bin/env python3
"""Private, serialized command accounting for the native Zig experiment."""

import argparse
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import signal
import shutil
import statistics
import subprocess
import tarfile
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


def host_cpu_snapshot():
    values = list(map(int, Path("/proc/stat").read_text().splitlines()[0].split()[1:]))
    return time.monotonic(), values


def host_cpu_delta(before, after):
    elapsed = after[0] - before[0]
    ticks = [end - start for start, end in zip(before[1], after[1])]
    hz = os.sysconf("SC_CLK_TCK")
    busy = sum(ticks[index] for index in (0, 1, 2, 5, 6)) / hz
    return {
        "elapsed_seconds": elapsed, "busy_cpu_seconds": busy,
        "busy_cores": busy / elapsed, "iowait_seconds": ticks[4] / hz,
        "steal_seconds": ticks[7] / hz,
        "definition": "user+nice+system+irq+softirq; no guest double count",
        "scope": "whole host, not attributable workload CPU",
    }


def build_argv(specification, variant):
    component = specification["component"]
    if component not in ("vmm", "agent"):
        raise ValueError("component must be vmm or agent")
    codegen, linker = variant["codegen"], variant["linker"]
    if codegen not in ("auto", "llvm", "native") or linker not in ("auto", "lld", "native"):
        raise ValueError("invalid backend or linker")
    if specification["mode"] not in ("debug", "safe"):
        raise ValueError("only debug/safe measurements are permitted")
    steps = specification["steps"]
    if not steps or any(step not in ("install", "test-build", "integration-test-build") for step in steps):
        raise ValueError("build measurements must not execute tests")
    if component == "agent" and "integration-test-build" in steps:
        raise ValueError("agent has no integration compile step")
    argv = [
        specification["compiler"]["path"], "build", *steps,
        f"-Dtarget={specification['target']}", f"-Doptimize={specification['mode']}",
        f"-D{component}-codegen={codegen}", f"-D{component}-linker={linker}",
        f"-j{specification['jobs']}", "--summary", "all", "--color", "off",
        "--verbose", "--verbose-link",
    ]
    if specification.get("cpu") is not None:
        argv.append(f"-Dcpu={specification['cpu']}")
    affinity = specification["affinity"]
    if not affinity or any(not isinstance(cpu, int) or cpu < 0 for cpu in affinity):
        raise ValueError("a nonempty explicit CPU affinity is required")
    return ["taskset", "-c", ",".join(map(str, affinity)), *argv]


def incremental_source(original, change):
    before, after = change["before"].encode(), change["after"].encode()
    if before == after or original.count(before) != 1:
        raise ValueError("incremental patch must replace exactly one nonidentical source fragment")
    return original.replace(before, after)


def archive_artifact_caches(cell):
    inventory = {}
    links = {}
    for directory in ("global", "local"):
        for path in (cell / directory).rglob("*"):
            if path.is_symlink():
                links[str(path.relative_to(cell))] = os.readlink(path)
            elif path.is_file():
                inventory[str(path.relative_to(cell))] = sha256(path)
    archive = cell / "artifact-caches.tar.gz"
    with tarfile.open(archive, "w:gz", compresslevel=1) as stream:
        for directory in ("global", "local"):
            stream.add(cell / directory, arcname=directory, recursive=True)
    verified = {}
    verified_links = {}
    with tarfile.open(archive, "r:gz") as stream:
        for member in stream:
            if member.isfile() or member.islnk():
                source = stream.extractfile(member)
                with source:
                    verified[member.name] = hashlib.file_digest(source, "sha256").hexdigest()
            elif member.issym():
                verified_links[member.name] = member.linkname
    if inventory != verified or links != verified_links:
        raise RuntimeError("cache archive identity mismatch; uncompressed caches retained")
    (cell / "cache-inventory.json").write_text(json.dumps({
        "files": inventory, "symlinks": links, "archive_sha256": sha256(archive),
        "policy": "all raw cache files retained in verified gzip tar; original directories removed only after completed measurements",
    }, indent=2) + "\n")
    for directory in ("global", "local"):
        shutil.rmtree(cell / directory)


def build_measurements(manifest, output, lock_path, resume=False):
    frozen = manifest.read_bytes()
    specification = json.loads(frozen)
    if specification["repeats"] < 10:
        raise ValueError("build comparisons require at least ten paired repetitions")
    variants = specification["variants"]
    if len(variants) != 2:
        raise ValueError("one bounded experiment compares exactly two variants")
    if specification.get("cache_retention", "uncompressed") not in ("uncompressed", "verified-archive"):
        raise ValueError("unknown cache retention policy")
    for variant in variants:
        build_argv(specification, variant)
    component = specification["component"]
    source = project_path(component)
    packages = source / "zig-pkg"
    conditions = specification["conditions"]
    if not conditions or conditions[0] != "cold" or any(
            condition not in ("cold", "warm", "incremental") for condition in conditions):
        raise ValueError("cold must initialize each independent cache before warm/incremental")
    if len(set(conditions)) != len(conditions) or (
            "warm" in conditions and "incremental" in conditions
            and conditions.index("warm") > conditions.index("incremental")):
        raise ValueError("conditions must be unique and preserve pristine cold/warm before incremental")
    change = specification.get("incremental_patch")
    if "incremental" in conditions and not change:
        raise ValueError("incremental measurement requires an exact codegen-affecting patch")
    if change:
        changed_file = project_path(f"{component}/{change['file']}")
        if not changed_file.is_relative_to(source / "src"):
            raise ValueError("incremental patch must stay in component source")
        incremental_source(changed_file.read_bytes(), change)
    rows = []
    first_repeat = 0
    if resume:
        with Path(lock_path).open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if (output / "manifest.json").read_bytes() != frozen:
                raise ValueError("resume manifest bytes changed")
            rows = json.loads((output / "results.json").read_text())
            completed = sorted({row["repeat"] for row in rows})
            first_repeat = len(completed)
            if completed != list(range(first_repeat)) or len(rows) != first_repeat * 2 * len(conditions):
                raise ValueError("resume requires complete paired repetitions; partial cells are retained, not reused")
            for repeat in completed:
                for index, variant in enumerate(variants):
                    cell = output / f"r{repeat:02d}-v{index}"
                    selected = [row for row in rows if row["repeat"] == repeat and row["variant"] == variant["id"]]
                    if sorted(row["condition"] for row in selected) != sorted(conditions) or any(
                            row["exit_code"] != 0 or row["manifest_sha256"] != hashlib.sha256(frozen).hexdigest()
                            for row in selected):
                        raise ValueError("resume contains failed or different-input measurements")
                    if specification.get("cache_retention") == "verified-archive":
                        inventory = json.loads((cell / "cache-inventory.json").read_text())
                        if sha256(cell / "artifact-caches.tar.gz") != inventory["archive_sha256"]:
                            raise ValueError("completed cache archive identity changed")
                    if change and sha256(cell / "source" / change["file"]) != sha256(changed_file):
                        raise ValueError("completed clone is not pristine")
            checkpoint = output / f"resume-{time.monotonic_ns()}.json"
            checkpoint.write_text(json.dumps({
                "completed_pairs": first_repeat, "remaining_pairs": specification["repeats"] - first_repeat,
                "manifest_unchanged": True, "runner_sha256": RUNNER_SHA256,
                "available_bytes": shutil.disk_usage(ROOT).free,
                "scope": "capacity interruption retained; host controls/variance must be evaluated, no automatic pooling qualification",
            }, indent=2) + "\n")
            checkpoint.with_suffix(".py").write_bytes(Path(__file__).read_bytes())
    else:
        output.mkdir(parents=True, exist_ok=False)
        (output / "manifest.json").write_bytes(frozen)
        (output / "runner.py").write_bytes(Path(__file__).read_bytes())
    original_affinity = os.sched_getaffinity(0)
    try:
        os.sched_setaffinity(0, specification["observer_affinity"])
        for repeat in range(first_repeat, specification["repeats"]):
            order = range(2) if repeat % 2 == 0 else reversed(range(2))
            with Path(lock_path).open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                if sha256(Path(specification["compiler"]["path"])) != specification["compiler"]["sha256"]:
                    raise ValueError("compiler identity changed")
                for name, digest in specification["source_hashes"].items():
                    if sha256(project_path(name)) != digest:
                        raise ValueError(f"source/package identity changed: {name}")
                if shutil.disk_usage(ROOT).free < specification["minimum_free_bytes"]:
                    raise OSError("insufficient artifact capacity; no evidence/cache deletion performed")
                for index in order:
                    variant = variants[index]
                    cell = output / f"r{repeat:02d}-v{index}"
                    tree = cell / "source"
                    tree.mkdir(parents=True)
                    preparation_started = time.monotonic()
                    shutil.copytree(source / "src", tree / "src")
                    for name in ("build.zig", "build.zig.zon"):
                        shutil.copy2(source / name, tree / name)
                    if not packages.is_dir():
                        raise FileNotFoundError("prefetch source-only zig-pkg before measuring; no downloads permitted")
                    (tree / "zig-pkg").symlink_to(packages, target_is_directory=True)
                    global_cache, local_cache = cell / "global", cell / "local"
                    global_cache.mkdir()
                    local_cache.mkdir()
                    env = os.environ.copy()
                    env["ZIG_GLOBAL_CACHE_DIR"] = str(global_cache)
                    env["ZIG_LOCAL_CACHE_DIR"] = str(local_cache)
                    source_patch = tree / change["file"] if change else None
                    pristine = source_patch.read_bytes() if source_patch else None
                    try:
                        for condition in conditions:
                            if condition == "incremental":
                                source_patch.write_bytes(incremental_source(pristine, change))
                            if condition == "cold" and (any(global_cache.iterdir()) or any(local_cache.iterdir())):
                                raise ValueError("cold artifact caches are not empty")
                            before = host_cpu_snapshot()
                            row = run_command(
                                build_argv(specification, variant), tree, cell / condition,
                                env, specification["timeout_seconds"],
                            )
                            row.update({
                                "repeat": repeat, "variant": variant["id"], "condition": condition,
                                "manifest_sha256": hashlib.sha256(frozen).hexdigest(),
                                "whole_host_control": host_cpu_delta(before, host_cpu_snapshot()),
                                "preparation_seconds_untimed": before[0] - preparation_started if condition == "cold" else None,
                                "cache_policy": "independent empty artifact caches, shared prefetched immutable source packages; no OS-cache flush",
                                "incremental_policy": "new compiler process, codegen-affecting patch, warm artifact caches; experimental incremental CLI flags unset",
                            })
                            artifacts = []
                            executable = tree / "zig-out/bin" / ("flint" if component == "vmm" else "hearth-agent")
                            if executable.is_file() and "install" in specification["steps"]:
                                artifacts.append(executable)
                            artifacts.extend(path for path in local_cache.glob("o/*/test") if path.is_file())
                            retained = cell / condition / "artifacts"
                            retained.mkdir()
                            row["artifacts"] = []
                            for artifact_index, artifact in enumerate(artifacts):
                                copy = retained / f"{artifact_index}-{artifact.name}"
                                shutil.copy2(artifact, copy)
                                row["artifacts"].append({
                                    "source_path": str(artifact.relative_to(ROOT)),
                                    "sha256": sha256(copy), "bytes": copy.stat().st_size,
                                })
                                with (retained / f"{copy.name}.elf.txt").open("wb") as stream:
                                    subprocess.run(
                                        ["readelf", "-h", "-l", "-S", "-p", ".comment", str(copy)],
                                        stdout=stream, stderr=subprocess.STDOUT, check=True,
                                    )
                            (cell / condition / "metrics.json").write_text(json.dumps(row, indent=2) + "\n")
                            rows.append(row)
                            (output / "results.json").write_text(json.dumps(rows, indent=2) + "\n")
                            if row["exit_code"] != 0 or not artifacts:
                                raise RuntimeError(f"build failed/missing measured artifacts: {repeat}/{variant['id']}/{condition}")
                    finally:
                        if source_patch:
                            source_patch.write_bytes(pristine)
                            if sha256(source_patch) != hashlib.sha256(pristine).hexdigest():
                                raise RuntimeError("pristine source restoration failed")
                    if specification.get("cache_retention") == "verified-archive":
                        archive_artifact_caches(cell)
    finally:
        os.sched_setaffinity(0, original_affinity)
    grouped = {
        f"{variant['id']}/{condition}": summarize([
            row for row in rows if row["variant"] == variant["id"] and row["condition"] == condition
        ]) for variant in variants for condition in conditions
    }
    (output / "summary.json").write_text(json.dumps(grouped, indent=2) + "\n")
    return grouped


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
    builds = commands.add_parser("build", help="paired cold/warm/codegen-patch builds with source-only dependency seeds")
    builds.add_argument("--manifest", required=True)
    builds.add_argument("--output", required=True)
    builds.add_argument("--resume", action="store_true", help="resume only verified complete paired repetitions of identical manifest")
    runtime = commands.add_parser("runtime", help="paired jailed lifecycle/operation diagnostics with private inherited perf")
    runtime.add_argument("--manifest", required=True)
    runtime.add_argument("--output", required=True)
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
    if args.operation == "build":
        print(json.dumps(build_measurements(
            project_path(args.manifest), project_path(args.output), args.lock, args.resume,
        ), indent=2))
        return
    if args.operation == "runtime":
        specification = importlib.util.spec_from_file_location(
            "perf_native_runtime", Path(__file__).with_name("perf-zig-native-runtime.py"),
        )
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        result = module.runtime(project_path(args.manifest), project_path(args.output), args.lock)
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result["failed"] == 0 and result["rows"] else 1)
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
            prerequisite = importlib.util.spec_from_file_location(
                "native_private_perf", ROOT / "tools/perf/blk-io.py",
            )
            support = importlib.util.module_from_spec(prerequisite)
            prerequisite.loader.exec_module(support)
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
                if argv[0] == "perf":
                    argv = support.privileged_perf(argv[1:])[3:]
                    if name == "report":
                        argv.insert(argv.index("--stdio") + 1, "--force")
                with (output / f"{name}.stdout").open("wb") as stdout, (output / f"{name}.stderr").open("wb") as stderr:
                    try:
                        completed = subprocess.run(
                            argv, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=30, check=False
                        )
                        results[name] = {"argv": argv, "exit_code": completed.returncode}
                    except (OSError, subprocess.TimeoutExpired) as error:
                        results[name] = {"argv": argv, "error": str(error)}
            if results["sudo"].get("exit_code") == 0 and results["kvm-events"].get("exit_code") != 0:
                argv = support.privileged_perf(["stat", "-e", "kvm:kvm_entry,kvm:kvm_exit", "--", "sleep", "0.2"])
                with (output / "privileged-kvm.stdout").open("wb") as stdout, (output / "privileged-kvm.stderr").open("wb") as stderr:
                    completed = subprocess.run(argv, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=30, check=False)
                    results["privileged-kvm-events"] = {"argv": argv, "exit_code": completed.returncode}
            for name, events in (
                ("privileged-software", "task-clock,context-switches,cpu-migrations,page-faults"),
                ("privileged-hardware", "cycles,instructions"),
            ):
                argv = support.privileged_perf(["stat", "-x,", "-e", events, "--", "sleep", "0.2"])
                with (output / f"{name}.stdout").open("wb") as stdout, (output / f"{name}.stderr").open("wb") as stderr:
                    completed = subprocess.run(argv, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=30, check=False)
                    results[name] = {"argv": argv, "exit_code": completed.returncode}
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
