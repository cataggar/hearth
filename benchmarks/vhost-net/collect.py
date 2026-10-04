#!/usr/bin/env python3
"""Unchanged-userspace TAP diagnostic; this is not an SDK workload."""

import argparse
import json
import math
import os
import socket
import struct
import time
from pathlib import Path


def receive(sock, size):
    result = bytearray()
    while len(result) < size:
        data = sock.recv(size - len(result))
        if not data:
            raise ConnectionError(f"short response: {len(result)}/{size}")
        result.extend(data)
    return bytes(result)


def percentiles(values):
    if not values:
        return {key: None for key in ("p50", "p95", "p99")}
    ordered = sorted(values)
    return {
        f"p{p}": ordered[max(0, math.ceil(len(ordered) * p / 100) - 1)]
        for p in (50, 95, 99)
    }


def busy_ticks(stat):
    fields = [int(value) for value in stat.splitlines()[0].split()[1:]]
    if len(fields) < 7:
        raise ValueError("incomplete /proc/stat CPU line")
    return sum(fields[index] for index in (0, 1, 2, 5, 6))


def cpu_snapshot():
    lines = Path("/proc/stat").read_text()
    return {
        "raw": lines,
        "busy_ticks": busy_ticks(lines),
        "clock_ticks_per_second": os.sysconf("SC_CLK_TCK"),
        "softirqs": Path("/proc/softirqs").read_text(),
        "softnet": Path("/proc/net/softnet_stat").read_text(),
        "time_ns": time.monotonic_ns(),
    }


def transaction(sock, mode, sequence):
    if mode in ("rpc", "wake"):
        payload = struct.pack("<Q", sequence) + bytes((sequence + i) % 256 for i in range(56))
        sock.sendall(payload)
        if receive(sock, 64) != payload:
            raise ValueError("RPC sequence/payload mismatch")
        return 64
    size = 8 * 1024 * 1024
    chunk = b"\x5a" * 65536
    sock.sendall(struct.pack("<Q", size))
    if mode == "h2g":
        for _ in range(size // len(chunk)):
            sock.sendall(chunk)
    else:
        for _ in range(size // len(chunk)):
            if receive(sock, len(chunk)) != chunk:
                raise ValueError("bulk payload mismatch")
    count, errors = struct.unpack("<QQ", receive(sock, 16))
    if count != size or errors:
        raise ValueError(f"bulk acknowledgement mismatch: {count} bytes, {errors} corrupt")
    return size


def run(args):
    results = {
        "mode": args.mode,
        "backend": getattr(args, "backend", "userspace"),
        "notification": getattr(args, "notification", "unchanged synchronous MMIO, direct IRQ, exit-driven RX"),
        "warmup_seconds": args.warmup_seconds,
        "requested_seconds": args.seconds,
        "successful_requests": 0,
        "attempted_active_requests": 0,
        "payload_bytes_one_direction": 0,
        "errors": [],
        "rtt_ms": [],
        "start_cpu": cpu_snapshot(),
    }
    start = time.monotonic()
    phase = "idle" if args.mode == "idle" else "connect"
    try:
        if args.mode == "idle":
            time.sleep(args.seconds)
        else:
            port = {"rpc": 7000, "wake": 7000, "h2g": 7001, "g2h": 7002}[args.mode]
            with socket.create_connection((args.host, port), args.timeout_seconds) as sock:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                sock.settimeout(args.timeout_seconds)
                sequence = 0
                phase = "warmup"
                warmup_end = time.monotonic() + args.warmup_seconds
                while time.monotonic() < warmup_end:
                    transaction(sock, args.mode, sequence)
                    sequence += 1
                results["active_start_cpu"] = cpu_snapshot()
                active_start = time.monotonic()
                phase = "active"
                while time.monotonic() - active_start < args.seconds:
                    if args.mode == "wake":
                        time.sleep(args.idle_seconds)
                    begin = time.monotonic_ns()
                    results["attempted_active_requests"] += 1
                    size = transaction(sock, args.mode, sequence)
                    elapsed_ms = (time.monotonic_ns() - begin) / 1e6
                    results["rtt_ms"].append(elapsed_ms)
                    results["successful_requests"] += 1
                    results["payload_bytes_one_direction"] += size
                    sequence += 1
                results["active_seconds"] = time.monotonic() - active_start
                results["active_end_cpu"] = cpu_snapshot()
    except (OSError, ValueError, ConnectionError) as error:
        results["errors"].append({"phase": phase, "type": type(error).__name__, "message": str(error)})
        if phase == "active":
            results["active_seconds"] = time.monotonic() - active_start
            results["active_end_cpu"] = cpu_snapshot()
    results["whole_command_seconds"] = time.monotonic() - start
    results["end_cpu"] = cpu_snapshot()
    results["rtt_ms_percentiles"] = percentiles(results["rtt_ms"])
    results["percentile_population"] = (
        "successful responses only; failures are separate, not a censored timeout tail estimate"
    )
    results["whole_host_busy_cpu_seconds"] = (
        results["end_cpu"]["busy_ticks"] - results["start_cpu"]["busy_ticks"]
    ) / results["end_cpu"]["clock_ticks_per_second"]
    if "active_seconds" in results:
        results["goodput_payload_bytes_per_second"] = (
            results["payload_bytes_one_direction"] / results["active_seconds"]
        )
        results["active_whole_host_busy_cpu_seconds"] = (
            results["active_end_cpu"]["busy_ticks"] - results["active_start_cpu"]["busy_ticks"]
        ) / results["active_end_cpu"]["clock_ticks_per_second"]
        if results["successful_requests"]:
            results["active_whole_host_cpu_seconds_per_request"] = (
                results["active_whole_host_busy_cpu_seconds"] / results["successful_requests"]
            )
            results["active_whole_host_cpu_seconds_per_payload_byte"] = (
                results["active_whole_host_busy_cpu_seconds"] / results["payload_bytes_one_direction"]
            )
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("rpc", "wake", "h2g", "g2h", "idle"), required=True)
    parser.add_argument("--host", default="192.0.2.2")
    parser.add_argument("--warmup-seconds", type=float, default=10)
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--idle-seconds", type=float, default=1)
    parser.add_argument("--timeout-seconds", type=float, default=3)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backend", default="userspace")
    parser.add_argument("--notification", default="unchanged synchronous MMIO, direct IRQ, exit-driven RX")
    args = parser.parse_args()
    if args.seconds <= 0 or args.warmup_seconds < 0 or args.timeout_seconds <= 0 or args.idle_seconds < 0:
        parser.error("durations must be positive; warmup and idle may be zero")
    result = run(args)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if not key.endswith("_cpu") and key != "rtt_ms"}))
    return bool(result["errors"])


if __name__ == "__main__":
    raise SystemExit(main())
