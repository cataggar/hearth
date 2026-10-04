#!/usr/bin/env python3
"""Real timer-free 1/4/8-sandbox active and pure-native HLT-idle acceptance."""

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time

import control
import matrix
import run as bench


def main():
    os.umask(0o077)
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(RuntimeError("bounded scale phase interrupted")))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--binary", required=True)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--mode", choices=["C00", "C10", "C01", "C11"], required=True)
    parser.add_argument("--count", type=int, choices=[1, 4, 8], required=True)
    args = parser.parse_args()
    out = bench.artifact_path(args.out)
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.sched_setaffinity(0, {1})
    guests, observers, producers = [], [], []
    result = {"status": "failed", "errors": [], "count": args.count, "mode": args.mode,
              "performance_merge_eligible": False, "classification": "concurrency correctness/idle diagnostics; fixed one-core VMM budget"}
    try:
        for index in range(args.count):
            directory = out / f"g{index}"
            directory.mkdir(mode=0o700)
            guest = control.Guest.__new__(control.Guest)
            guests.append(guest)
            guest.__init__(directory, bench.artifact_path(args.binary), args.mode, bench.artifact_path(args.fixture), disk=True)
            if not guest.native:
                raise ValueError("pure-native timer-free fixture required; no agent polling timer")
            observers.append(matrix.Observer(guest))
            bench.native_echo(guest.connection, 0, 4096)
        time.sleep(.2)
        before = [bench.thread_roster(guest.pid) for guest in guests]
        kernel_before = [observer.read() for observer in observers]
        host_before = Path("/proc/stat").read_text()
        started = time.monotonic()
        time.sleep(60)
        seconds = time.monotonic() - started
        after = [bench.thread_roster(guest.pid) for guest in guests]
        kernel_after = [observer.read() for observer in observers]
        vm_cpu = sum(bench.cpu_delta(old, new) for old, new in zip(before, after))
        kernel_cpu = sum(new["kernel_irqfd_cpu_seconds"] - old["kernel_irqfd_cpu_seconds"]
                         for old, new in zip(kernel_before, kernel_after))
        result["idle"] = {
            "seconds": seconds, "all_vm_task_cpu_seconds": vm_cpu, "irqfd_kernel_work_cpu_seconds": kernel_cpu,
            "one_core_percentage_points_per_sandbox": 100 * (vm_cpu + kernel_cpu) / seconds / args.count,
            "host_noise": bench.host_cpu_delta(host_before, Path("/proc/stat").read_text(), seconds),
            "threads_before": before, "threads_after": after,
            "heartbeat_ms": 0, "guest_agent_present": False, "backend_timers": False,
        }
        result["idle_wake_ms"] = []
        for index, guest in enumerate(guests):
            started = time.monotonic()
            bench.native_echo(guest.connection, index + 1, 64)
            latency = (time.monotonic() - started) * 1000
            if latency > 1000:
                raise RuntimeError("pure halted idle wake exceeded one-second bound")
            result["idle_wake_ms"].append(latency)
        responses, errors = {}, []
        def active(index, guest):
            try:
                responses[index] = [bench.native_echo(guest.connection, number, 65536) for number in range(32)]
            except Exception as error:
                errors.append(str(error))
        for index, guest in enumerate(guests):
            producer = threading.Thread(target=active, args=(index, guest))
            producers.append(producer)
            producer.start()
        for producer in producers:
            producer.join(timeout=30)
        if errors or any(producer.is_alive() for producer in producers):
            raise RuntimeError(f"concurrent native I/O failed: {errors}")
        result["concurrent_verified_messages_per_sandbox"] = {index: len(value) for index, value in responses.items()}
        result["shutdown_exit_codes"] = [guest.shutdown() for guest in guests]
        result["kernel_work"] = [observer.finish() for observer in observers]
        observers = []
        result["status"] = "passed"
    except (OSError, ValueError, RuntimeError, EOFError, subprocess.SubprocessError) as error:
        result["errors"].append(f"{type(error).__name__}: {error}")
    finally:
        for observer in observers:
            try:
                observer.finish()
            except Exception as error:
                result["errors"].append(f"observer cleanup: {error}")
        for guest in guests:
            if any(producer.is_alive() for producer in producers):
                guest.connection.shutdown(2)
            guest.close()
        for producer in producers:
            producer.join(timeout=5)
    bench.save_json(out / "result.json", result)
    print(json.dumps({"status": result["status"], "count": args.count, "mode": args.mode,
                      "idle": result.get("idle", {}).get("one_core_percentage_points_per_sandbox"),
                      "errors": result["errors"]}))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
