#!/usr/bin/env python3
"""Separate userspace returns from kernel-handled exits in a captured L0 trace."""

import argparse
from collections import Counter
import json
from pathlib import Path
import re

from run import artifact_path, percentile, save_json

LINE = re.compile(r"\s(\d+)\s+\[\d+\]\s+(\d+\.\d+):\s+(\S+):\s+(.*)")


def analyze(lines, devices):
    events, kernel_reasons, user_reasons, kicks, irq_edges = (Counter() for _ in range(5))
    pending, irq_times = {}, []
    unpaired_exits = 0
    irq_calls = Counter()
    pending_notify, userspace_notify = {}, Counter()
    for line in lines:
        match = LINE.search(line)
        if not match:
            continue
        tid, timestamp, event, detail = match.groups()
        timestamp = float(timestamp)
        events[event] += 1
        if event == "kvm:kvm_entry":
            # A handled MMIO resumes in-kernel; do not carry its classification
            # into a later, unrelated userspace return.
            pending_notify.pop(tid, None)
        elif event == "kvm:kvm_exit":
            reason = re.search(r"reason (\S+)", detail)
            if reason:
                kernel_reasons[reason[1]] += 1
        elif event == "kvm:kvm_userspace_exit":
            reason = re.search(r"reason (\S+)", detail)
            user_reasons[reason[1] if reason else detail] += 1
            notify = pending_notify.pop(tid, None)
            if notify is not None and reason and "MMIO" in reason[1]:
                userspace_notify[notify] += 1
        elif event == "kvm:kvm_mmio":
            write = re.search(r"mmio write len (\d+) gpa (0x[\da-f]+) val (0x[\da-f]+)", detail)
            if write and int(write[1]) == 4:
                for device in devices:
                    if int(write[2], 16) == device["mmio_base"] + 0x50:
                        key = f'{device["kind"]}:queue{int(write[3], 16)}'
                        kicks[key] += 1
                        pending_notify[tid] = key
        elif event == "syscalls:sys_enter_ioctl":
            request = re.search(r"cmd: (0x[\da-f]+)", detail)
            if request:
                pending[tid] = {"request": int(request[1], 16), "started": timestamp}
        elif event == "kvm:kvm_set_irq":
            irq = re.search(r"gsi (\d+) level (\d+) source (\d+)", detail)
            if irq:
                gsi, level, source = (int(value) for value in irq.groups())
                irq_edges[f"gsi{gsi}:level{level}:source{source}"] += 1
                if tid in pending:
                    pending[tid].update(gsi=gsi, level=level, source=source)
        elif event == "syscalls:sys_exit_ioctl":
            call = pending.pop(tid, None)
            if call is None:
                unpaired_exits += 1
                continue
            # These request numbers are observed in this translated-header L0
            # trace, not production definitions of a new ioctl interface.
            if call["request"] == 0x4008AE61:
                target = next((device for device in devices if device["gsi"] == call.get("gsi")), None)
                kind = target["kind"] if target else "non-virtio-or-unattributed"
                irq_calls[kind] += 1
                if target:
                    irq_times.append((timestamp - call["started"]) * 1_000_000)
    return {
        "events": dict(events),
        "kernel_exit_reasons": dict(kernel_reasons),
        "userspace_exit_reasons": dict(user_reasons),
        "observed_four_byte_notify_writes": dict(kicks),
        "attributed_notify_userspace_returns": dict(userspace_notify),
        "irq_line_edges": dict(irq_edges),
        "completed_irq_line_ioctl_calls": dict(irq_calls),
        "eligible_irq_line_ioctl_profiled_us": {
            name: percentile(irq_times, fraction)
            for name, fraction in (("p50", 0.50), ("p95", 0.95), ("p99", 0.99))
        },
        "unpaired_ioctl_exits_at_window_boundary": unpaired_exits,
        "pending_ioctl_entries_at_window_boundary": len(pending),
        "limitations": [
            "IRQ ioctl intervals include tracing overhead and are not unprofiled latency gates",
            "notify counters count writes, not descriptors or completed application operations",
            "kernel exit tracepoints are not userspace-return counters",
            "no completion-integrity or interrupt-delivery success inferred from IRQ writes",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    directory = artifact_path(args.run)
    devices = [
        {"kind": kind, "mmio_base": int(address, 16), "gsi": int(gsi)}
        for kind, address, gsi in re.findall(
            r"virtio-(blk|net|vsock) at MMIO 0x([\da-f]+) IRQ (\d+)",
            (directory / "vmm.stderr").read_text(),
        )
    ]
    if not devices:
        raise ValueError("no actual device/GSI roster in VMM diagnostics")
    with (directory / "kvm-ioctl.stdout").open() as trace:
        result = analyze(trace, devices)
    result["devices"] = devices
    result["run"] = str(directory)
    save_json(artifact_path(args.out), result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
