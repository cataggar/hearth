#!/usr/bin/env python3
"""Owned, bounded in-flight TCP payload check across a VM traffic snapshot."""

import argparse
import json
import socket
import struct
import time
from pathlib import Path

from collect import receive


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    result = {"bytes": 0, "errors": [], "classification": "correctness only"}
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
            sock.settimeout(90)
            sock.connect(("192.0.2.2", 7002))
            size = 8 * 1024 * 1024
            sock.sendall(struct.pack("<Q", size))
            (args.directory / "traffic-ready").write_text("request sent; reader withheld\n")
            deadline = time.monotonic() + 90
            while not (args.directory / "traffic-release").exists():
                if time.monotonic() > deadline:
                    raise TimeoutError("snapshot supervisor did not release reader")
                time.sleep(0.01)
            for _ in range(size // 65536):
                if receive(sock, 65536) != b"\x5a" * 65536:
                    raise ValueError("in-flight payload mismatch")
                result["bytes"] += 65536
            count, errors = struct.unpack("<QQ", receive(sock, 16))
            if count != size or errors:
                raise ValueError(f"in-flight acknowledgement mismatch: {count}/{errors}")
            result["acknowledgement"] = {"bytes": count, "errors": errors}
    except (OSError, ValueError, ConnectionError) as error:
        result["errors"].append({"type": type(error).__name__, "message": str(error)})
    (args.directory / "traffic-result.json").write_text(json.dumps(result, indent=2) + "\n")
    return bool(result["errors"])


if __name__ == "__main__":
    raise SystemExit(main())
