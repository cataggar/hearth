#!/usr/bin/env python3
"""Freeze fresh A/A noise before reading any candidate performance data."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[2]
BOOTS = {"pc-aa1": 4, "pc-aa2": 3, "pc-aa3": 3}


def population(values):
    median = statistics.median(values)
    mad = statistics.median(abs(v - median) for v in values)
    return {"count": len(values), "median": median, "mean": statistics.mean(values),
            "sample_sd": statistics.stdev(values), "min": min(values), "max": max(values),
            "mad": mad, "mad_over_median": mad / median if median else None,
            "samples": values}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.relative_to(ROOT / ".perf")
    if output.exists():
        raise ValueError("refusing to overwrite preregistered noise")
    prereg_path = ROOT / ".perf/vhost-net/post-cleanup-20261004/preregister.json"
    prereg = json.loads(prereg_path.read_text())
    base = ROOT / ".perf/vhost-net/20261004"
    modes = {}
    raw = []
    hashes = {}
    controls = []
    for boot, repeats in BOOTS.items():
        directory = base / boot
        if not json.loads((directory / "jail-closed.json").read_text())["worker_and_process_joined"]:
            raise ValueError("baseline ownership was not joined")
        variant = json.loads((directory / "variant.json").read_text())
        if (variant["effective_backend"] != "userspace" or
                variant["binary_sha256"] != "5b1fd2bf28d988602de3a924be3fa36dee27ae677aa7a38de11f8e41272ec68e"):
            raise ValueError("baseline selected an unexpected backend")
        summary = json.loads((directory / "summary.json").read_text())
        if len(summary) != repeats * 3 or any(r["status"] for r in summary):
            raise ValueError("incomplete or failed baseline windows")
        for name in ("host-before", "host-after"):
            controls.append({"boot": boot, "control": name,
                             "busy_cores": json.loads((directory / f"{name}.json").read_text())["busy_cores"]})
        for repetition in range(repeats):
            for mode in ("rpc", "h2g", "g2h"):
                path = directory / f"correctness-{repetition:02d}-{mode}.json"
                encoded = path.read_bytes()
                data = json.loads(encoded)
                hashes[str(path.relative_to(ROOT))] = hashlib.sha256(encoded).hexdigest()
                if (data["errors"] or data["successful_requests"] != data["attempted_active_requests"]
                        or data["warmup_seconds"] != 10 or data["requested_seconds"] != 60
                        or not 60 <= data["active_seconds"] < 62
                        or data["warmup_successful_requests"] <= 0):
                    raise ValueError(f"invalid baseline population: {path}")
                row = {
                    "boot": boot, "repetition": repetition, "mode": mode,
                    "requests": data["successful_requests"],
                    "request_rate": data["successful_requests"] / data["active_seconds"],
                    "goodput": data["goodput_payload_bytes_per_second"],
                    "aggregate_cpu_per_unit": data[
                        "active_whole_host_cpu_seconds_per_request" if mode == "rpc"
                        else "active_whole_host_cpu_seconds_per_payload_byte"],
                    "client_cpu_per_unit": data["active_process_cpu_seconds"] / (
                        data["successful_requests"] if mode == "rpc" else data["payload_bytes_one_direction"]),
                    **data["rtt_ms_percentiles"],
                }
                raw.append(row)
    for mode in ("rpc", "h2g", "g2h"):
        rows = [r for r in raw if r["mode"] == mode]
        modes[mode] = {key: population([r[key] for r in rows])
                       for key in ("request_rate", "goodput", "aggregate_cpu_per_unit",
                                   "client_cpu_per_unit", "p50", "p95", "p99")}
    noise = max(p["mad_over_median"] for group in modes.values()
                for key, p in group.items() if key != "client_cpu_per_unit")
    capacity = modes["rpc"]["request_rate"]["median"]
    result = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "classification": "fresh A/A noise, not vhost benefit or attributable total-network CPU",
        "preregister_sha256": hashlib.sha256(prereg_path.read_bytes()).hexdigest(),
        "preregister": prereg, "boot_counts": BOOTS, "modes": modes, "raw": raw,
        "source_hashes": hashes, "controls": controls,
        "conservative_N": noise, "minimum_benefit_above_2N_percent": 200 * noise,
        "frozen_rpc_rate_50_percent": capacity * .5,
        "frozen_rpc_rate_80_percent": capacity * .8,
        "gates": {"cpu_reduction_percent": 10, "goodput_increase_percent": 15,
                  "active_regression_percent": 5, "idle_increment_core_per_vm": .01,
                  "tail_increment": "max(5%,1ms)", "paired_95pct_ci_excludes_zero": True},
        "limitations": [
            "10 windows per mode clustered in3boots, not30 independent boots",
            "aggregate CPU includes unrelated activity; no subtraction or attribution claim",
            "client CPU is not total-network CPU; kernel/softirq reconciliation is outstanding",
            "candidate performance files are never read by this script",
        ],
    }
    output.write_text(json.dumps(result, indent=2) + "\n")
    output.chmod(0o600)
    print(json.dumps({"windows": len(raw), "N": noise, "rpc_capacity": capacity,
                      "minimum_benefit_above_2N_percent": 200 * noise}))


if __name__ == "__main__":
    main()
