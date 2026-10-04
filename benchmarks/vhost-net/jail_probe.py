#!/usr/bin/env python3
"""Diagnose original/repaired enforced-jail controls without relaxing them."""

import argparse
import json
import os
import shutil
import signal
import stat
import sys
from pathlib import Path

sys.dont_write_bytecode = True
import runner


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backend", choices=("original", "userspace", "vhost", "auto"), default="vhost")
    parser.add_argument("--expect", choices=("access-denied", "sigsys", "privilege-drop"), default="access-denied")
    parser.add_argument("--uid", type=int, choices=(0, 1000), default=1000)
    parser.add_argument("--no-jail", action="store_true")
    parser.add_argument("--trace", action="store_true")
    parser.add_argument("--trace-all", action="store_true")
    args = parser.parse_args()
    args.trace = args.trace or args.trace_all
    os.umask(0o077)
    directory = args.output.resolve()
    if directory.exists():
        raise ValueError("refusing to overwrite jail evidence")
    directory.relative_to(runner.ROOT / ".perf")
    runner.private_directory(directory)
    runner.setup_tap(directory)
    jail = directory / "jail"
    runner.private_directory(jail)
    fixture = runner.ROOT / ".perf/vhost-net/20261004/fixture"
    for name in ("bzImage", "initrd.cpio.gz"):
        shutil.copyfile(fixture / name, jail / name)
        (jail / name).chmod(0o600)
        os.chown(jail / name, 1000, 1000)
    argv = [
        "taskset", "-c", "8", str(runner.ROOT / "vmm/zig-out/bin/flint"),
        str(jail / "bzImage") if args.no_jail else "bzImage",
        str(jail / "initrd.cpio.gz") if args.no_jail else "initrd.cpio.gz",
        "console=ttyS0 reboot=k panic=1 pci=off",
        "--tap", "hn2tap0",
    ]
    if not args.no_jail:
        argv.extend(("--jail", str(jail), "--jail-uid", str(args.uid), "--jail-gid", "1000"))
    if args.backend != "original":
        argv.extend(("--net-backend", args.backend))
    child_status = directory / "traced-child.json"
    if args.trace:
        wrapper = (
            "import json,pathlib,subprocess,sys; "
            "child=subprocess.Popen(sys.argv[2:]); status=child.wait(); "
            "pathlib.Path(sys.argv[1]).write_text(json.dumps({'pid':child.pid,'returncode':status,"
            "'absent_after_join':not pathlib.Path('/proc',str(child.pid)).exists()}))"
        )
        events = [] if args.trace_all else ["--event", "sched_getaffinity,epoll_pwait,poll"]
        argv = [
            "perf", "trace", *events, "--",
            sys.executable, "-c", wrapper, str(child_status), *argv,
        ]
    status = runner.command(argv, directory, "jail", timeout=20)
    result = {"status": status, "classification": "enforced-jail control diagnostic, not acceptance",
              "backend": args.backend, "expected_failure": args.expect, "trace": args.trace,
              "configured_uid": args.uid,
              "jailed": not args.no_jail,
              "nodes": {}}
    for name in ("dev", "dev/net", "dev/kvm", "dev/net/tun", "dev/vhost-net"):
        path = jail / name
        if path.exists():
            info = path.lstat()
            result["nodes"][name] = {"mode": oct(stat.S_IMODE(info.st_mode)),
                                     "uid": info.st_uid, "gid": info.st_gid}
    stderr = (directory / "jail.stderr").read_text(errors="replace")
    actual_status = status
    if args.trace:
        if child_status.exists():
            child = json.loads(child_status.read_text())
            runner.owned_file(child_status, json.dumps(child, indent=2) + "\n")
            result["traced_child"] = child
            actual_status = child["returncode"] if child["absent_after_join"] else None
        else:
            actual_status = None
    result["actual_child_status"] = actual_status
    result["access_denied"] = "AccessDenied" in stderr
    result["sigsys"] = actual_status == -signal.SIGSYS
    if args.expect == "access-denied":
        result["expected_failure_observed"] = actual_status == 1 and result["access_denied"]
    elif args.expect == "privilege-drop":
        result["expected_failure_observed"] = actual_status == 1 and (
            "VhostRequiresPrivilegeDrop" in stderr or
            (not args.no_jail and args.uid == 0 and "jail must drop root" in stderr)
        )
    else:
        result["expected_failure_observed"] = result["sigsys"]
    runner.owned_file(directory / "jail-result.json", json.dumps(result, indent=2) + "\n")
    for name in ("dev/kvm", "dev/net/tun", "dev/vhost-net"):
        (jail / name).unlink(missing_ok=True)
    for name in ("dev/net", "dev"):
        path = jail / name
        if path.exists():
            path.rmdir()
    return not result["expected_failure_observed"]


if __name__ == "__main__":
    raise SystemExit(main())
