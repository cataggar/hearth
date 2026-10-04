#!/usr/bin/env python3
"""Reproduce the unmodified common jail prerequisite without relaxing it."""

import argparse
import json
import os
import shutil
import stat
from pathlib import Path

import runner


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
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
        "bzImage", "initrd.cpio.gz", "console=ttyS0 reboot=k panic=1 pci=off",
        "--jail", str(jail), "--jail-uid", "1000", "--jail-gid", "1000",
        "--tap", "hn2tap0", "--net-backend", "vhost",
    ]
    status = runner.command(argv, directory, "jail", timeout=20)
    result = {"status": status, "classification": "common jail prerequisite reproduction, not acceptance",
              "nodes": {}}
    for name in ("dev", "dev/net", "dev/kvm", "dev/net/tun", "dev/vhost-net"):
        path = jail / name
        if path.exists():
            info = path.lstat()
            result["nodes"][name] = {"mode": oct(stat.S_IMODE(info.st_mode)),
                                     "uid": info.st_uid, "gid": info.st_gid}
    result["common_failure"] = "AccessDenied" in (directory / "jail.stderr").read_text(errors="replace")
    runner.owned_file(directory / "jail-result.json", json.dumps(result, indent=2) + "\n")
    for name in ("dev/kvm", "dev/net/tun", "dev/vhost-net"):
        (jail / name).unlink(missing_ok=True)
    for name in ("dev/net", "dev"):
        path = jail / name
        if path.exists():
            path.rmdir()
    return status != 1 or not result["common_failure"]


if __name__ == "__main__":
    raise SystemExit(main())
