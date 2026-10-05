#!/usr/bin/env python3
"""Private jailed capability/resource faults; no host device policy changes."""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
import runner


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backend", choices=("vhost", "auto"), required=True)
    fault = parser.add_mutually_exclusive_group(required=True)
    fault.add_argument("--kind", choices=("permission", "uapi"))
    fault.add_argument("--fd-limit", type=int, choices=(12, 14, 15))
    args = parser.parse_args()
    os.umask(0o077)
    directory = args.output.resolve()
    directory.relative_to(runner.ROOT / ".perf")
    if directory.exists() or os.getuid() != 0:
        raise ValueError("root private namespace and fresh owned output required")
    runner.private_directory(directory)
    runner.freeze_tools(directory)
    runner.owned_file(directory / "source-capability_probe.py", Path(__file__).read_text())
    runner.setup_tap(directory)
    layout = runner.JailedLayout(
        directory, fixture=runner.ROOT / ".perf/vhost-net/20261004/fixture")
    argv = [*layout.argv(runner.ROOT / "vmm/zig-out/bin/flint"), "--net-backend", args.backend]
    if args.fd_limit:
        argv = ["prlimit", f"--nofile={args.fd_limit}:{args.fd_limit}", "--", *argv,
                "bzImage", "initrd.cpio.gz", "console=ttyS0 reboot=k panic=1 pci=off"]
    else:
        argv += ["--api-sock", "api.sock"]
    result = {"classification": "enforced-jail owned fault diagnostic; not performance",
              "backend": args.backend, "kind": args.kind, "fd_limit": args.fd_limit,
              "argv": argv, "passed": False}
    child = None
    log = directory / "serial.log"
    try:
        with log.open("wb") as output:
            child = subprocess.Popen(argv, cwd=directory, stdout=output, stderr=subprocess.STDOUT)
        result["pid"] = child.pid
        if args.fd_limit:
            result["actual_status"] = child.wait(timeout=20)
            text = log.read_text(errors="replace")
            result["passed"] = (result["actual_status"] == 1 and "NetEventfdFailed" in text
                                and "effective=userspace reason=" not in text)
        else:
            sock = layout.root / "api.sock"
            deadline = time.monotonic() + 15
            while not sock.exists():
                if child.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("jailed capability API did not become ready")
                time.sleep(0.01)
            node = layout.root / "dev/vhost-net"
            result["declared_node_before_fault"] = {
                "uid": node.stat().st_uid, "gid": node.stat().st_gid,
                "mode": oct(node.stat().st_mode & 0o777)}
            if args.kind == "permission":
                node.chmod(0)
            else:
                node.unlink()
                node.write_bytes(b"")
                node.chmod(0o600)
                os.chown(node, runner.UID, runner.GID)
            expected = "VhostAccessDenied" if args.kind == "permission" else "VhostUapiUnsupported"
            for method, route, body in (
                ("PUT", "/machine-config", {"vcpu_count": 1, "mem_size_mib": 512}),
                ("PUT", "/boot-source", {"kernel_image_path": "bzImage", "initrd_path": "initrd.cpio.gz",
                                        "boot_args": "console=ttyS0 reboot=k panic=1 pci=off"}),
                ("PUT", "/network-interfaces/eth0", {"iface_id": "eth0", "host_dev_name": "hn2tap0"}),
            ):
                runner.request(sock, method, route, body)
            try:
                result["start_response"] = runner.request(sock, "PUT", "/actions", {"action_type": "InstanceStart"})
            except (RuntimeError, OSError) as error:
                result["start_error"] = str(error)
            deadline = time.monotonic() + 15
            while True:
                text = log.read_text(errors="replace")
                ready = "PERF_TAP_READY" in text
                if ready or child.poll() is not None or (args.backend == "vhost" and expected in text):
                    break
                if time.monotonic() > deadline:
                    raise TimeoutError("capability selection did not finish")
                time.sleep(0.01)
            result["expected_error"] = expected
            if args.backend == "auto":
                if not ready or f"effective=userspace reason={expected}" not in text:
                    raise RuntimeError("early auto fallback was not explicit and usable")
                runner.owned_file(directory / "variant.json", json.dumps({
                    "effective_backend": "userspace", "notification": "common blocked-poll/direct IRQ",
                    "jailed": True, "injected_fault": args.kind}, indent=2) + "\n")
                layout.verify(child.pid, "userspace", "fallback-verified")
                checks = {mode: runner.workload(directory, mode, f"fallback-{mode}", 0.5, 0)
                          for mode in ("rpc", "h2g", "g2h", "wake")}
                result["payload_checks"] = checks
                result["passed"] = not any(checks.values())
            else:
                result["passed"] = expected in text and not ready and "effective=userspace reason=" not in text
                result["actual_status_at_diagnosis"] = child.poll()
    finally:
        if child is not None:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
            result["actual_join_status"] = child.returncode
            result["owned_pid_absent_after_join"] = not Path("/proc", str(child.pid)).exists()
        try:
            runner.owned_file(directory / "result.json", json.dumps(result, indent=2) + "\n")
        finally:
            layout.close()
        for path in (directory, *directory.rglob("*")):
            if not path.is_symlink():
                os.chown(path, runner.UID, runner.GID)
    if not result["passed"]:
        raise RuntimeError("jailed capability/resource control failed")


if __name__ == "__main__":
    def terminate(_number, _frame):
        raise SystemExit("owned capability supervisor terminated")
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    main()
