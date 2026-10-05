"""Visible Linux busy CPU; operation boundaries and unsubtracted uncertainty."""

import math
import os
from pathlib import Path
import statistics
import time

BUSY = (0, 1, 2, 5, 6)
SCOPE = ("all visible-host CPU: user+nice+system+irq+softirq; guest already in user/nice; "
         "includes VMM, peers and deferred kernel/scheduler work; not physical Azure hypervisor CPU")


def capture():
    before = time.monotonic_ns()
    online = Path("/sys/devices/system/cpu/online").read_text().strip()
    with Path("/proc/stat").open() as file:
        line = file.readline()
    after = time.monotonic_ns()
    fields = line.split()
    if fields[0] != "cpu" or len(fields) < 9:
        raise ValueError("unsupported aggregate /proc/stat layout")
    return {"ticks": list(map(int, fields[1:9])), "online_cpu_ids": online, "read_start_ns": before,
            "read_end_ns": after, "ticks_per_second": os.sysconf("SC_CLK_TCK")}


def delta(before, after, start_ns, end_ns, visible_cores):
    if (before["ticks_per_second"] != after["ticks_per_second"] or visible_cores < 1
            or before.get("online_cpu_ids") != after.get("online_cpu_ids")
            or not before["read_end_ns"] <= start_ns < end_ns <= after["read_start_ns"]):
        raise ValueError("CPU counters do not bracket the completed-operation interval")
    if len(before["ticks"]) != 8 or len(after["ticks"]) != 8 or before["ticks_per_second"] <= 0:
        raise ValueError("unsupported visible CPU counter layout/clock")
    if before.get("online_cpu_ids") is not None:
        bounds = [list(map(int, part.split("-"))) for part in before["online_cpu_ids"].split(",")]
        if any(len(item) > 2 or item[-1] < item[0] for item in bounds) or sum(
                item[-1] - item[0] + 1 for item in bounds) != visible_cores:
            raise ValueError("visible online CPU count changed from recorded host")
    ticks = [new - old for old, new in zip(before["ticks"], after["ticks"])]
    if len(ticks) != 8 or any(value < 0 for value in ticks):
        raise ValueError("visible CPU counters reset")
    hz = before["ticks_per_second"]
    seconds = (end_ns - start_ns) / 1e9
    # Linux sums each aggregate category before converting to USER_HZ. Each
    # endpoint difference has <1 tick/category error, not an added guest field.
    precision = len(BUSY) / hz + visible_cores * (
        start_ns - before["read_start_ns"] + after["read_end_ns"] - end_ns) / 1e9
    busy = sum(ticks[index] for index in BUSY) / hz
    return {"busy_cpu_seconds": busy, "operation_seconds": seconds,
            "precision_cpu_seconds_bound": precision,
            "steal_seconds_excluded": ticks[7] / hz, "iowait_seconds_excluded": ticks[4] / hz,
            "idle_seconds": ticks[3] / hz, "busy_core_equivalents": busy / seconds,
            "operation_start_ns": start_ns, "operation_end_ns": end_ns,
            "before": before, "after": after, "delta_ticks": ticks,
            "visible_cores": visible_cores, "scope": SCOPE,
            "background_subtracted": False, "owned_detail_added": False}


def quiet(seconds, visible_cores):
    before = capture()
    start = time.monotonic_ns()
    time.sleep(seconds)
    end = time.monotonic_ns()
    result = delta(before, capture(), start, end, visible_cores)
    result["classification"] = "no owned VM/workload; actual visible background, never subtracted"
    return result


def background_upper(controls):
    if len(controls) < 5:
        raise ValueError("at least five actual quiet controls required")
    if any(not math.isfinite(row["operation_seconds"]) or row["operation_seconds"] <= 0
           or not math.isfinite(row["precision_cpu_seconds_bound"]) or row["precision_cpu_seconds_bound"] < 0
           for row in controls):
        raise ValueError("invalid quiet duration/precision")
    rates = [row["busy_cpu_seconds"] / row["operation_seconds"] for row in controls]
    if any(not math.isfinite(value) or value < 0 for value in rates):
        raise ValueError("invalid quiet background observation")
    precision = max(row["precision_cpu_seconds_bound"] / row["operation_seconds"] for row in controls)
    # df4 is conservative for >=5 controls; use the observed envelope too.
    upper = max(max(rates), statistics.mean(rates) +
                2.776445105 * statistics.stdev(rates) / math.sqrt(len(rates))) + precision
    return {"n": len(rates), "observed_rates": rates, "one_core_rate_upper": upper,
            "model": "max(observed envelope, mean+conservative95%t) plus counter/read precision",
            "background_subtracted": False}


def residual_fraction(baseline, candidate, background):
    old = baseline["visible_host_cpu"]
    new = candidate["visible_host_cpu"]
    per_op = baseline["visible_host_cpu_per_operation"]
    if per_op <= 0:
        raise ValueError("positive measured control CPU required")
    budget = (old["precision_cpu_seconds_bound"] / baseline["operations"]
              + new["precision_cpu_seconds_bound"] / candidate["operations"]
              + background["one_core_rate_upper"] * old["operation_seconds"] / baseline["operations"])
    return budget / per_op


def sensitivity_bounds(baseline, candidate, background, lower_ratio, upper_ratio):
    measured = baseline["visible_host_cpu_per_operation"]
    if measured <= 0:
        raise ValueError("positive measured control CPU required")
    old, new = baseline["visible_host_cpu"], candidate["visible_host_cpu"]
    old_precision = old["precision_cpu_seconds_bound"] / baseline["operations"] / measured
    new_precision = new["precision_cpu_seconds_bound"] / candidate["operations"] / measured
    old_background = background["one_core_rate_upper"] * old["operation_seconds"] / baseline["operations"] / measured
    new_background = background["one_core_rate_upper"] * new["operation_seconds"] / candidate["operations"] / measured
    denominator = 1 - old_precision - old_background
    return {
        "conservative_upper_ratio": (upper_ratio + new_precision) / denominator if denominator > 0 else None,
        "conservative_lower_ratio": max(0, lower_ratio - new_precision - new_background) / (1 + old_precision),
        "control_residual_fraction": old_precision + old_background,
        "candidate_residual_fraction": new_precision + new_background,
        "control_denominator_may_be_all_residual": denominator <= 0,
        "background_subtracted": False,
        "model": "worst-case background/counter/read perturbation of paired95% ratio; measured CPU untouched",
    }
