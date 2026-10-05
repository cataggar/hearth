#!/usr/bin/env python3
"""Eight owned concurrent TCP clients; payload correctness, not throughput."""

import argparse
import concurrent.futures
import json
import socket
from pathlib import Path

from collect import transaction


def client(index):
    mode = "rpc" if index < 4 else "h2g" if index < 6 else "g2h"
    port = {"rpc": 7000, "h2g": 7001, "g2h": 7002}[mode]
    result = {"client": index, "mode": mode, "checked_requests": 0, "checked_bytes": 0, "errors": []}
    try:
        with socket.create_connection(("192.0.2.2", port), 30) as sock:
            sock.settimeout(30)
            for sequence in range(32 if mode == "rpc" else 1):
                result["checked_bytes"] += transaction(sock, mode, index * 1000 + sequence)
                result["checked_requests"] += 1
    except (OSError, ValueError, ConnectionError) as error:
        result["errors"].append({"type": type(error).__name__, "message": str(error)})
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(client, range(8)))
    args.output.write_text(json.dumps({
        "classification": "eight clients in one VM, not four/eight-VM performance acceptance",
        "clients": results,
    }, indent=2) + "\n")
    return any(row["errors"] for row in results)


if __name__ == "__main__":
    raise SystemExit(main())
