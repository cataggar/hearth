#!/usr/bin/env python3
"""Enforced vsock 16/64-total-connection fairness and fd-reuse acceptance."""

import argparse
import json
import os
import signal
import subprocess
import time

import control
import matrix
import run as bench


def main():
    os.umask(0o077)
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(RuntimeError("bounded connections phase interrupted")))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--binary", required=True)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--mode", choices=["C00", "C10", "C01", "C11"], required=True)
    args = parser.parse_args()
    out = bench.artifact_path(args.out)
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.sched_setaffinity(0, {1})
    guest, peers = None, []
    result = {"status": "failed", "errors": [], "mode": args.mode, "performance_merge_eligible": False}
    try:
        guest = control.Guest.__new__(control.Guest)
        guest.__init__(out, bench.artifact_path(args.binary), args.mode, bench.artifact_path(args.fixture))
        peers.append(guest.native_connection)
        for count in (16, 64):
            while len(peers) + 1 < count:
                if matrix.rpc_exec(guest, "/native-vsock >/dev/null 2>&1 & printf SPAWNED") != b"SPAWNED":
                    raise ValueError("native connection fixture failed to spawn")
                peer, _ = guest.native_listener.accept()
                peer.settimeout(8)
                peers.append(peer)
            time.sleep(.2)
            result[f"total_connections_{count}"] = [
                bench.native_echo(peer, index, 4096) for index, peer in enumerate(peers)
            ]
            ping = bench.rpc(guest.connection, {"method": "ping"})
            if not ping.get("ok"):
                raise ValueError("64-connection traffic starved the unchanged agent")
        for peer in peers[1:33]:
            peer.shutdown(2)
            peer.close()
        peers = [peers[0], *peers[33:]]
        # A control round-trip observes the guest's close/reset handling before
        # allocating the same slots; this is not a guessed fd-reuse sleep.
        matrix.rpc_exec(guest, "printf REUSE")
        for _ in range(32):
            if matrix.rpc_exec(guest, "/native-vsock >/dev/null 2>&1 & printf SPAWNED") != b"SPAWNED":
                raise ValueError("reuse spawn failed")
            peer, _ = guest.native_listener.accept()
            peer.settimeout(8)
            peers.append(peer)
        result["after_32_closes_and_reconnects"] = [
            bench.native_echo(peer, 1000 + index, 65536) for index, peer in enumerate(peers)
        ]
        result["bound"] = "64 total backend connections =63 native +1 unchanged agent; no unsupported CONNECT"
        result["shutdown_exit_code"] = guest.shutdown()
        result["status"] = "passed"
    except (OSError, ValueError, RuntimeError, EOFError, subprocess.SubprocessError) as error:
        result["errors"].append(f"{type(error).__name__}: {error}")
    finally:
        for peer in peers[1:]:
            peer.close()
        if guest is not None:
            guest.close()
    bench.save_json(out / "result.json", result)
    print(json.dumps({"status": result["status"], "mode": args.mode, "errors": result["errors"]}))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
