#!/usr/bin/env python3
"""Publish selective owned evidence, never VM images or scheduler/raw trace data."""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile

import run as bench


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = bench.artifact_path(args.out)
    if out.exists():
        raise ValueError("immutable evidence output already exists")
    root = bench.ROOT / ".perf/eventfd"
    selected = []
    permitted_text = {
        "perf-stat.txt", "perf.stderr", "cpu-report.stdout", "cpu-report.stderr",
        "vmm.stderr", "serial.txt", "irqfd-observer.stderr",
    }
    for stage in ("w1", "w2", "w3", "w4"):
        for path in (root / stage).rglob("*"):
            if not path.is_file() or path.is_symlink() or "j" in path.relative_to(root).parts:
                continue
            if path.suffix == ".json" or path.name in permitted_text or path.suffix == ".log":
                if path.stat().st_size > 20 * 1024 * 1024:
                    raise ValueError(f"unexpected oversized selective evidence: {path.name}")
                selected.append(path)
    records = []
    with tarfile.open(out, "w:gz", compresslevel=6) as archive:
        for path in sorted(selected):
            if path.name == "perf-stat.txt" and path.stat().st_uid != os.getuid():
                payload = subprocess.run(
                    ["sudo", "-n", "cat", str(path)], check=True, capture_output=True, timeout=5).stdout
            else:
                payload = path.read_bytes()
            name = str(path.relative_to(root))
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(payload), 0o600, 0
            archive.addfile(info, io.BytesIO(payload))
            records.append({"path": name, "bytes": len(payload),
                            "sha256": hashlib.sha256(payload).hexdigest()})
        manifest = json.dumps({
            "schema": 1, "source_commit": subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=bench.ROOT, capture_output=True, check=True).stdout.decode().strip(),
            "collector_sha256": bench.digest(Path(__file__)),
            "classification": "selective raw own receipts; not full qualification or adoption",
            "excluded": ["VM memory/disk/state", "initrds/third-party binaries",
                         "perf raw data", "decoded syscall/scheduler trace with foreign next-task fields"],
            "private_raw_preservation": "owned trace gzip and zero-extent sparse files preserve exact SHA",
            "files": records,
        }, indent=2).encode()
        info = tarfile.TarInfo("EVIDENCE-MANIFEST.json")
        info.size, info.mode, info.mtime = len(manifest), 0o600, 0
        archive.addfile(info, io.BytesIO(manifest))
    with tarfile.open(out, "r:gz") as archive:
        manifest = json.load(archive.extractfile("EVIDENCE-MANIFEST.json"))
        for record in manifest["files"]:
            payload = archive.extractfile(record["path"]).read()
            if len(payload) != record["bytes"] or hashlib.sha256(payload).hexdigest() != record["sha256"]:
                raise ValueError("archive readback mismatch")
    print(json.dumps({"archive": str(out.relative_to(bench.ROOT)), "sha256": bench.digest(out),
                      "bytes": out.stat().st_size, "verified_files": len(records)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
