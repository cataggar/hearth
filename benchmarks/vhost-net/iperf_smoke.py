#!/usr/bin/env python3
"""Execute the separate guest tool closure; this is not deciding performance."""

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
    parser.add_argument("--fixture-id", default="fixture-iperf")
    args = parser.parse_args()
    if (not args.boot_id.replace("-", "").isalnum() or
            not args.fixture_id.startswith("fixture-iperf") or
            not args.fixture_id.replace("-", "").isalnum()):
        parser.error("invalid owned boot ID")
    os.umask(0o077)
    def stop(_number, _frame):
        raise SystemExit("owned guest-tool smoke stopped; joining children")
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    artifacts = runner.ROOT / ".perf/vhost-net/20261004"
    directory = artifacts / args.boot_id
    if directory.exists():
        raise ValueError("refusing to overwrite smoke evidence")
    rows, errors = [], []
    finished = threading.Event()
    cancel = threading.Event()

    def clients():
        try:
            deadline = time.monotonic() + 20
            while not (directory / "ready-verified.owned-status.json").exists():
                if cancel.is_set() or time.monotonic() > deadline:
                    raise RuntimeError("owned jailed guest did not become ready")
                time.sleep(.01)
            for udp in (False, True):
                for reverse in (False, True):
                    name = f"iperf-{'udp' if udp else 'tcp'}-{'g2h' if reverse else 'h2g'}"
                    argv = ["taskset", "-c", "9", "/usr/bin/iperf3",
                            "-c", "192.0.2.2", "-p", "5201", "-t", "3", "-O", "0",
                            "-J", "--get-server-output"]
                    if reverse:
                        argv.append("-R")
                    if udp:
                        argv += ["-u", "-b", "10M", "-l", "1200"]
                    status = runner.command(argv, directory, name, user=True, timeout=12,
                                            env={**os.environ, "TMPDIR": str(directory)})
                    data = json.loads((directory / f"{name}.stdout").read_text())
                    end = data.get("end", {})
                    received = end.get("sum_received", {})
                    passed = status == 0 and "error" not in data and received.get("bytes", 0) > 0
                    if udp:
                        passed = passed and received.get("lost_packets", -1) == 0
                    rows.append({
                        "name": name, "status": status, "passed": passed,
                        "received": received,
                        "sent": end.get("sum_sent", {}),
                        "classification": "3s loader/protocol/loss-free smoke; not performance or idle acceptance",
                    })
            runner.owned_file(directory / "iperf-smoke.json", json.dumps(rows, indent=2) + "\n")
            runner.owned_file(directory / "source-iperf-smoke.py", Path(__file__).read_text())
        except Exception as error:
            errors.append(repr(error))
        finally:
            finished.set()

    thread = threading.Thread(target=clients)
    thread.start()
    parameters = argparse.Namespace(
        artifact_dir=artifacts, fixture_id=args.fixture_id, net_backend=args.backend,
        tap_name="h2p2484526", sample_label="separate-guest-iperf-smoke-not-performance-or-idle",
        jail=True, host_controls=True, repetitions=1, modes=["idle"], seconds=35, warmup=0,
        profiles=False, reset=False, concurrent=False, snapshot=False,
    )
    try:
        runner.boot(parameters, directory)
    finally:
        cancel.set()
        thread.join(timeout=20)
    if not finished.is_set() or errors or len(rows) != 4 or not all(r["passed"] for r in rows):
        runner.owned_file(directory / "iperf-smoke-errors.json", json.dumps(errors, indent=2) + "\n")
        raise RuntimeError(f"owned guest iperf smoke failed: {errors}")


if __name__ == "__main__":
    main()
