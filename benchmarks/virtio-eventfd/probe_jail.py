#!/usr/bin/env python3
"""Inspect only this disposable jailed L0 child and its actual thread filters."""

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time

from run import ROOT, artifact_path, command, digest, save_json

INSPECT = """
import json,pathlib,sys
root=int(sys.argv[1]); pending=[root]; seen=set(); rows=[]
while pending:
    pid=pending.pop()
    if pid in seen: continue
    seen.add(pid)
    try:
        base=pathlib.Path(f'/proc/{pid}')
        pending.extend(int(x) for x in (base/'task'/str(pid)/'children').read_text().split())
        if (base/'comm').read_text().strip() != 'flint': continue
        stat=(base/'stat').read_text()
        start_ticks=stat[stat.rfind(')')+2:].split()[19]
        for task in (base/'task').iterdir():
            status=dict(line.split(':',1) for line in (task/'status').read_text().splitlines() if ':' in line)
            rows.append({'pid':pid,'tid':int(task.name),'start_ticks':start_ticks,
                         'comm':(task/'comm').read_text().strip(),
                         'Kthread':status.get('Kthread','unknown').strip(),
                         **{key:status[key].strip() for key in ('Uid','Gid','Groups','CapEff','Seccomp','NoNewPrivs')}})
    except FileNotFoundError:
        pass
print(json.dumps(rows))
"""


def enforced_roster(rows, uid, gid):
    userspace = [row for row in rows if row["Kthread"] == "0"]
    return bool(userspace) and all(row["Kthread"] in ("0", "1") for row in rows) and all(
        set(row["Uid"].split()) == {str(uid)}
        and set(row["Gid"].split()) == {str(gid)}
        and not row["Groups"].split()
        and row["Seccomp"] == "2" and row["NoNewPrivs"] == "1"
        and row["CapEff"] == "0000000000000000" for row in userspace
    )


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--jail", required=True)
    parser.add_argument("--binary", default=".perf/eventfd/fixtures/legacy/flint")
    parser.add_argument("--label", default="L0")
    parser.add_argument("--trace-syscalls", action="store_true")
    args = parser.parse_args()
    out, jail = artifact_path(args.out), artifact_path(args.jail)
    out.mkdir(parents=True, exist_ok=False)
    jail.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(ROOT / ".perf/eventfd/fixtures/bzImage", jail / "bzImage")
    shutil.copyfile(ROOT / ".perf/eventfd/fixtures/native-hb0/initrd.cpio.gz", jail / "initrd.cpio.gz")
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(jail / "vsock_11000"))
    listener.listen(1)
    listener.settimeout(8)
    workload = [
        "timeout", "--kill-after=2", "15",
        str(artifact_path(args.binary)),
        "--jail", str(jail), "--jail-uid", str(os.getuid()), "--jail-gid", str(os.getgid()),
        "/bzImage", "/initrd.cpio.gz",
        "console=ttyS0 nokaslr reboot=k panic=1 pci=off nomodules",
        "--vsock-cid", "43", "--vsock-uds", "/vsock",
    ]
    argv = ["sudo", "-n"] + workload
    if args.trace_syscalls:
        argv = [
            "sudo", "-n", "env", f"PERF_BUILDID_DIR={ROOT / '.perf/eventfd/perf-buildids'}",
            "perf", "record", "-e", "raw_syscalls:sys_enter", "-e", "raw_syscalls:sys_exit",
            "-o", str(out / "syscalls.data"), "--",
        ] + workload
    save_json(out / "command.json", {
        "argv": argv, "cwd": str(ROOT), "started_unix": time.time(),
        "label": args.label, "binary_sha256": digest(artifact_path(args.binary)),
    })
    result = {"status": "failed", "threads": [], "errors": []}
    with (out / "guest-serial.txt").open("wb") as serial, (out / "vmm.stderr").open("wb") as stderr:
        child = subprocess.Popen(argv, cwd=ROOT, stdout=serial, stderr=stderr)
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and child.poll() is None:
                inspected = subprocess.run(
                    ["sudo", "-n", "python3", "-c", INSPECT, str(child.pid)],
                    cwd=ROOT, capture_output=True, timeout=3, check=True,
                )
                rows = json.loads(inspected.stdout)
                if rows and any(row["Uid"].split()[1] == str(os.getuid()) for row in rows):
                    result["threads"] = rows
                    if not enforced_roster(rows, os.getuid(), os.getgid()):
                        result["errors"].append("a post-drop VMM thread retains uid/capabilities or lacks the enforced filter")
                        break
                    try:
                        connection, _ = listener.accept()
                        connection.close()
                        inspected = subprocess.run(
                            ["sudo", "-n", "python3", "-c", INSPECT, str(child.pid)],
                            cwd=ROOT, capture_output=True, timeout=3, check=True,
                        )
                        result["threads"] = json.loads(inspected.stdout)
                        if enforced_roster(result["threads"], os.getuid(), os.getgid()):
                            result["status"] = "passed"
                        else:
                            result["errors"].append("guest-connected thread roster fails isolation checks")
                    except TimeoutError:
                        result["errors"].append("enforced jailed guest did not connect")
                    break
                time.sleep(0.05)
            if not result["threads"]:
                result["errors"].append("no post-drop VMM thread roster observed")
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            result["errors"].append(str(error))
        finally:
            # The supervisor bounds the whole owned process tree; on observed
            # isolation failure, stop precisely the identified VMM immediately.
            if child.poll() is None:
                inspected = subprocess.run(
                    ["sudo", "-n", "python3", "-c", INSPECT, str(child.pid)],
                    cwd=ROOT, capture_output=True, timeout=3,
                )
                live = json.loads(inspected.stdout) if inspected.returncode == 0 else []
                owned = {(row["pid"], row["start_ticks"]) for row in result["threads"]}
                for pid in {row["pid"] for row in live if (row["pid"], row["start_ticks"]) in owned}:
                    subprocess.run(["sudo", "-n", "kill", "-TERM", str(pid)], cwd=ROOT, capture_output=True)
            result["supervisor_exit_code"] = child.wait(timeout=20)
            listener.close()
            (jail / "vsock_11000").unlink(missing_ok=True)
            cleanup = subprocess.run(["sudo", "-n", "rm", "-rf", "--", str(jail)], cwd=ROOT, capture_output=True)
            result["private_jail_cleanup_exit_code"] = cleanup.returncode
    if args.trace_syscalls and (out / "syscalls.data").exists():
        command(
            ["sudo", "-n", "chown", f"{os.getuid()}:{os.getgid()}", str(out / "syscalls.data")],
            out, "trace-owned-file",
        )
        result["trace_decode"] = command(
            ["sudo", "-n", "env", f"PERF_BUILDID_DIR={ROOT / '.perf/eventfd/perf-buildids'}",
             "perf", "script", "-f", "-i", str(out / "syscalls.data"),
             "-F", "comm,pid,time,event,trace"],
            out, "syscalls",
        )
    save_json(out / "result.json", result)
    print(json.dumps(result))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
