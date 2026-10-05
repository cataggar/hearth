"""Generation-pinned custody of one supervisor's descendants, across sessions."""

import ctypes
import os
from pathlib import Path
import select
import signal
import subprocess
import time


class CustodyError(RuntimeError):
    pass


def identity(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()
    except FileNotFoundError:
        return None
    return {"pid": pid, "state": fields[0], "ppid": int(fields[1]), "start_ticks": int(fields[19])}


class Supervisor:
    def __init__(self):
        if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
            raise CustodyError("owned cleanup requires Linux pidfd support")
        try:
            probe = os.pidfd_open(os.getpid())
            try:
                signal.pidfd_send_signal(probe, 0)
            finally:
                os.close(probe)
        except OSError as error:
            raise CustodyError("kernel pidfd custody unavailable before controller launch") from error
        self.libc = ctypes.CDLL(None, use_errno=True)
        old = ctypes.c_int()
        if self.libc.prctl(37, ctypes.byref(old), 0, 0, 0) != 0:
            raise CustodyError("cannot query child-subreaper admission")
        self.old_subreaper = old.value
        if self.libc.prctl(36, 1, 0, 0, 0) != 0:
            raise CustodyError("cannot establish child-subreaper custody before launch")
        self.root = identity(os.getpid())
        self.records = {}
        self.controller = None
        self.interrupted = None
        self.handlers = {}

    def alive(self, record):
        return not select.select([record["pidfd"]], [], [], 0)[0]

    def register(self, pid, parent):
        before = identity(pid)
        if before is None or before["ppid"] != parent["pid"]:
            return
        if (pid, before["start_ticks"]) in self.records:
            return
        try:
            fd = os.pidfd_open(pid)
        except ProcessLookupError:
            return
        after, actual_parent = identity(pid), identity(parent["pid"])
        if (after is None or actual_parent is None
                or after["start_ticks"] != before["start_ticks"]
                or after["ppid"] != parent["pid"]
                or actual_parent["start_ticks"] != parent["start_ticks"]):
            os.close(fd)
            return
        key = (pid, after["start_ticks"])
        if key in self.records:
            os.close(fd)
            return
        self.records[key] = {
            **after, "parent_start_ticks": parent["start_ticks"], "pidfd": fd,
            "registered_ns": time.monotonic_ns(), "signals": [], "reaped": False,
        }

    def discover(self):
        # Only explicit own task trees are read; subreaper adoption retains orphans.
        pending = [self.root]
        seen = set()
        while pending:
            parent = pending.pop()
            key = (parent["pid"], parent["start_ticks"])
            if key in seen:
                continue
            seen.add(key)
            before = identity(parent["pid"])
            if before is None or before["start_ticks"] != parent["start_ticks"]:
                continue
            children = set()
            try:
                tasks = list(Path(f"/proc/{parent['pid']}/task").iterdir())
                for task in tasks:
                    try:
                        children.update(map(int, (task / "children").read_text().split()))
                    except FileNotFoundError:
                        pass
            except FileNotFoundError:
                continue
            after = identity(parent["pid"])
            if after is None or after["start_ticks"] != parent["start_ticks"]:
                continue
            for pid in children:
                self.register(pid, parent)
                actual = identity(pid)
                if actual is not None and (pid, actual["start_ticks"]) in self.records:
                    pending.append(self.records[(pid, actual["start_ticks"])])

    def send(self, record, signum):
        if not self.alive(record):
            return
        actual = identity(record["pid"])
        if actual is None or actual["start_ticks"] != record["start_ticks"]:
            raise CustodyError("refusing changed owned PID generation")
        if signum in record["signals"]:
            return
        try:
            signal.pidfd_send_signal(record["pidfd"], signum)
        except ProcessLookupError:
            return
        record["signals"].append(signum)

    def reap(self):
        for record in self.records.values():
            if record is self.controller or record["reaped"]:
                continue
            actual = identity(record["pid"])
            if actual is None or actual["start_ticks"] != record["start_ticks"]:
                continue
            try:
                pid, status = os.waitpid(record["pid"], os.WNOHANG)
            except ChildProcessError:
                continue
            if pid:
                record.update(reaped=True, wait_status=status)

    def descendants(self):
        return [row for row in self.records.values()
                if row is not self.controller and self.alive(row)]

    def cleanup(self, process, seconds, term_grace):
        began = time.monotonic()
        deadline = began + seconds
        descendants_deadline = deadline - min(5, seconds / 3)
        self.discover()
        self.send(self.controller, signal.SIGTERM)
        while time.monotonic() < descendants_deadline:
            self.discover()
            self.reap()
            for row in self.descendants():
                self.send(row, signal.SIGTERM if time.monotonic() < began + term_grace else signal.SIGKILL)
            if time.monotonic() >= began + term_grace:
                # Freeze controller admission before the final descendant sweep.
                self.send(self.controller, signal.SIGSTOP)
            process.poll()
            if not self.descendants():
                actual = identity(self.controller["pid"])
                stopped = (actual is not None and actual["start_ticks"] == self.controller["start_ticks"]
                           and actual["state"] in ("T", "t"))
                if not self.alive(self.controller) or stopped:
                    break
            time.sleep(.01)
        self.discover()
        self.reap()
        before_kill = [(row["pid"], row["start_ticks"]) for row in self.descendants()]
        self.send(self.controller, signal.SIGKILL)
        try:
            process.wait(timeout=max(.001, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            pass
        # Controller death adopts any last fork; the same generation checks apply.
        while time.monotonic() < deadline:
            self.discover()
            self.reap()
            for row in self.descendants():
                self.send(row, signal.SIGKILL)
            if not self.descendants() and process.poll() is not None:
                self.reap()
                break
            time.sleep(.01)
        survivors = [row for row in self.records.values() if self.alive(row)]
        return {"cleanup_seconds": time.monotonic() - began,
                "alive_before_controller_kill": before_kill,
                "surviving_generations": [[row["pid"], row["start_ticks"]] for row in survivors]}

    def run(self, argv, work_seconds, cleanup_seconds=30, term_grace=5, **kwargs):
        def interrupted(signum, _frame):
            self.interrupted = signum
        self.handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
        for sig in self.handlers:
            signal.signal(sig, interrupted)
        process = subprocess.Popen(argv, **kwargs)
        self.register(process.pid, self.root)
        generation = identity(process.pid)
        if generation is None or (process.pid, generation["start_ticks"]) not in self.records:
            raise CustodyError("controller was not registered before supervision")
        self.controller = self.records[(process.pid, generation["start_ticks"])]
        deadline = time.monotonic() + work_seconds
        reason = "completed"
        failure = None
        try:
            while True:
                self.discover()
                self.reap()
                if process.poll() is not None:
                    break
                if self.interrupted is not None:
                    reason = "signal"
                    break
                if time.monotonic() >= deadline:
                    reason = "timeout"
                    break
                time.sleep(.02)
        except (OSError, ValueError, RuntimeError) as error:
            reason, failure = "custody-error", type(error).__name__
        orphaned = bool(self.descendants())
        cleanup = self.cleanup(process, cleanup_seconds, term_grace)
        rows = [{key: value for key, value in row.items() if key != "pidfd"}
                for row in self.records.values()]
        receipt = {
            "status": "failed" if cleanup["surviving_generations"] or cleanup["alive_before_controller_kill"] else "passed",
            "termination_reason": reason, "controller_returncode": process.returncode,
            "work_budget_seconds": work_seconds, "cleanup_budget_seconds": cleanup_seconds,
            "subreaper": True, "registrations": rows, **cleanup,
        }
        if failure is not None:
            receipt["failure_type"] = failure
        code = (124 if reason == "timeout" else 128 + self.interrupted if reason == "signal"
                else process.returncode)
        if receipt["status"] != "passed" or failure is not None or (code == 0 and orphaned):
            code = 1
        return code, receipt

    def close(self):
        for record in self.records.values():
            os.close(record["pidfd"])
        for sig, handler in self.handlers.items():
            signal.signal(sig, handler)
        if self.libc.prctl(36, self.old_subreaper, 0, 0, 0) != 0:
            raise CustodyError("cannot restore child-subreaper setting")
