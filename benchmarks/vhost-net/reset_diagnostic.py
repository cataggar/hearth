#!/usr/bin/env python3
"""Observe only the owned reset cgroup's limits; never relax them."""

import argparse
import json
import os
from pathlib import Path
import signal
import threading
import time

import runner


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--boot-id", required=True)
    parser.add_argument("--backend", choices=("userspace", "vhost"), required=True)
    args = parser.parse_args()
    if not args.boot_id.replace("-", "").isalnum():
        parser.error("invalid owned boot ID")
    os.umask(0o077)
    def stop(_number, _frame):
        raise SystemExit("owned reset diagnostic stopped; joining children")
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    artifacts = runner.ROOT / ".perf/vhost-net/20261004"
    directory = artifacts / args.boot_id
    if directory.exists():
        raise ValueError("refusing to overwrite reset evidence")
    runner.private_directory(directory)
    runner.owned_file(directory / "source-reset-diagnostic.py", Path(__file__).read_text())
    cgroup = Path("/sys/fs/cgroup", f"hearth-vhost-net-{os.getpid()}-{args.boot_id}")
    cancel = threading.Event()
    samples = []
    failures = []

    def sample():
        try:
            while not cancel.wait(.002):
                if not cgroup.exists():
                    continue
                row = {"monotonic_ns": time.monotonic_ns()}
                for name in ("pids.current", "pids.peak", "pids.events", "memory.current",
                             "memory.peak", "memory.events"):
                    path = cgroup / name
                    try:
                        row[name] = path.read_text().strip()
                    except FileNotFoundError:
                        pass
                samples.append(row)
        except Exception as error:
            failures.append(repr(error))

    thread = threading.Thread(target=sample)
    thread.start()
    parameters = argparse.Namespace(
        artifact_dir=artifacts, fixture_id="fixture-reset", net_backend=args.backend,
        tap_name="h2p2484526", sample_label="owned-cgroup-reset-resource-diagnostic-not-performance",
        jail=True, host_controls=True, repetitions=1, modes=["rpc"], seconds=.5, warmup=0,
        profiles=False, reset=True, reset_count=100, concurrent=False, snapshot=False,
    )
    try:
        runner.boot(parameters, directory)
    finally:
        cancel.set()
        thread.join(timeout=5)
        runner.owned_file(directory / "owned-cgroup-limit-samples.json", json.dumps({
            "classification": "owned limit observation; helper does not wake guest or change runtime",
            "cgroup": str(cgroup), "samples": samples, "sampler_errors": failures,
        }, indent=2) + "\n")
    if failures:
        raise RuntimeError(f"owned cgroup sampler failed: {failures}")


if __name__ == "__main__":
    main()
