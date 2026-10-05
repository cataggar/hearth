#!/usr/bin/env python3
"""Inject owned vhost stop failures; pause/resume/snapshot must not acknowledge."""

import argparse
import array
import ctypes
import json
import os
from pathlib import Path
import select
import signal
import socket
import subprocess
import threading
import time

import fault_probe
import runner


def run_case(directory, operation, backend, queue):
    runner.private_directory(directory)
    baseline_fds = len(list(Path("/proc/self/fd").iterdir()))
    binary = runner.ROOT / "vmm/zig-out/bin/flint"
    layout = runner.JailedLayout(directory, fixture=runner.ROOT / ".perf/vhost-net/20261004/fixture")
    parent, channel = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
    parent.settimeout(10)
    child, listener, controller = None, None, None
    configured = threading.Event()
    paused = threading.Event()
    errors = []
    result = {"operation": operation, "backend": backend, "queue": queue,
              "injected": False, "notifications": [],
              "classification": "real restrictive lifecycle fault, not performance"}
    sock = layout.root / "api.sock"

    def configure():
        try:
            deadline = time.monotonic() + 15
            while not sock.exists():
                if child.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("owned API startup failed")
                time.sleep(.01)
            for route, body in (
                ("/machine-config", {"vcpu_count": 1, "mem_size_mib": 512}),
                ("/boot-source", {"kernel_image_path": "bzImage", "initrd_path": "initrd.cpio.gz",
                                  "boot_args": "console=ttyS0 reboot=k panic=1 pci=off"}),
                ("/network-interfaces/eth0", {"iface_id": "eth0", "host_dev_name": layout.tap_name}),
                ("/actions", {"action_type": "InstanceStart"}),
            ):
                response = runner.request(sock, "PUT", route, body)
                if not response.startswith("HTTP/1.1 204"):
                    raise RuntimeError(f"owned configuration rejected: {response}")
            configured.set()
        except Exception as error:
            errors.append(repr(error))

    def pause():
        try:
            result["pause_response"] = runner.request(sock, "PATCH", "/vm", {"state": "Paused"})
        except Exception as error:
            errors.append(repr(error))
        finally:
            paused.set()

    try:
        argv = layout.argv(binary)
        argv = [*argv[:6], "python3", str(runner.ROOT / "benchmarks/vhost-net/ioctl_fault.py"),
                "--operation", operation, "--metadata", str(directory / "filter.json"),
                "--notify-fd", str(channel.fileno()), "--", *argv[6:],
                "--api-sock", "api.sock", "--net-backend", backend]
        with (directory / "serial.log").open("wb") as output:
            child = subprocess.Popen(argv, cwd=directory, stdout=output, stderr=subprocess.STDOUT,
                                     pass_fds=(channel.fileno(),))
        channel.close()
        _, ancillary, _, _ = parent.recvmsg(64, socket.CMSG_SPACE(array.array("i").itemsize))
        descriptors = []
        for level, kind, data in ancillary:
            if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                fds = array.array("i")
                fds.frombytes(data[:len(data) - len(data) % fds.itemsize])
                descriptors.extend(fds)
        if len(descriptors) != 1:
            for fd in descriptors:
                os.close(fd)
            raise RuntimeError("expected one owned fault listener")
        listener = descriptors[0]
        poller = select.poll()
        poller.register(listener, select.POLLIN)
        controller = threading.Thread(target=configure)
        controller.start()
        deadline = time.monotonic() + 35
        ready = False
        while not paused.is_set():
            if errors or child.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError(f"owned lifecycle fault incomplete: {errors}")
            text = (directory / "serial.log").read_text(errors="replace")
            if not ready and configured.is_set() and "PERF_TAP_READY" in text and "effective=vhost" in text:
                controller.join(timeout=5)
                layout.verify(child.pid, "vhost", "ready-verified")
                if runner.workload(directory, "rpc", "before-fault", .2, 0):
                    raise RuntimeError("pre-fault real TCP payload failed")
                ready = True
                controller = threading.Thread(target=pause)
                controller.start()
            if not any(flags & select.POLLIN for _, flags in poller.poll(10)):
                continue
            notification = fault_probe.Notification()
            fault_probe.ioctl(listener, 0xc0502100, notification)
            members = (layout.cgroup / "cgroup.threads").read_text().split()
            if notification.pid != child.pid and str(notification.pid) not in members:
                raise RuntimeError("notification outside owned cgroup")
            if Path(f"/proc/{notification.pid}/exe").resolve() != binary:
                raise RuntimeError("notification outside owned Flint")
            fd = os.open(f"/proc/{notification.pid}/mem", os.O_RDONLY | os.O_CLOEXEC)
            try:
                state = os.pread(fd, 8, notification.data.args[2])
            finally:
                os.close(fd)
            index, value = int.from_bytes(state[:4], "little"), int.from_bytes(state[4:], "little")
            stop = operation == "GET_VRING_BASE" or value == 0xffffffff
            inject = ready and stop and index == queue and not result["injected"]
            response = fault_probe.Response(notification.id, 0, -5 if inject else 0, 0 if inject else 1)
            fault_probe.ioctl(listener, 0xc0182101, response)
            result["notifications"].append({"owned_tid": notification.pid, "queue": index,
                                            "stop_operation": stop, "injected": inject})
            result["injected"] |= inject
        controller.join(timeout=5)
        result["resume_response"] = runner.request(sock, "PATCH", "/vm", {"state": "Resumed"})
        result["snapshot_response"] = runner.request(sock, "PUT", "/snapshot/create", {
            "snapshot_path": "declined.vmstate", "mem_file_path": "declined.mem"})
        runner.inventory(directory, "after-rejection", child.pid)
        tasks = json.loads((directory / "after-rejection.owned-status.json").read_text())
        result["owned_workers_after_rejection"] = sum(r["Name"].startswith("vhost-") for r in tasks.values())
        result["snapshot_files_absent"] = not any((layout.root / n).exists()
                                                  for n in ("declined.vmstate", "declined.mem"))
        result["passed"] = (
            result["injected"] and not errors and
            all(not result[n].startswith("HTTP/1.1 204")
                for n in ("pause_response", "resume_response", "snapshot_response")) and
            result["owned_workers_after_rejection"] == 0 and result["snapshot_files_absent"] and
            "operation=" in (directory / "serial.log").read_text(errors="replace") and
            "effective=userspace reason=" not in (directory / "serial.log").read_text(errors="replace")
        )
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        if controller is not None:
            controller.join(timeout=12)
        if listener is not None:
            os.close(listener)
        parent.close()
        channel.close()
        layout.close()
        result["supervisor_fds_before_after"] = [baseline_fds, len(list(Path("/proc/self/fd").iterdir()))]
        result["passed"] = result.get("passed", False) and result["supervisor_fds_before_after"][0] == result["supervisor_fds_before_after"][1]
        result["errors"] = errors
        runner.owned_file(directory / "result.json", json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    def stop(_number, _frame):
        raise SystemExit("owned lifecycle supervisor stopped; joining child")
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    directory = args.output.resolve()
    directory.relative_to(runner.ROOT / ".perf")
    if directory.exists():
        raise ValueError("refusing to overwrite fault evidence")
    runner.private_directory(directory)
    runner.owned_file(directory / "source.py", Path(__file__).read_text())
    runner.setup_tap(directory)
    results = []
    for operation in ("SET_VRING_KICK", "SET_BACKEND", "GET_VRING_BASE"):
        for backend in ("vhost", "auto"):
            for queue in (0, 1):
                results.append(run_case(directory / f"{operation.lower()}-{backend}-{queue}",
                                        operation, backend, queue))
    runner.owned_file(directory / "results.json", json.dumps(results, indent=2) + "\n")
    if not all(r["passed"] for r in results):
        raise RuntimeError("owned lifecycle fault matrix failed")


if __name__ == "__main__":
    main()
