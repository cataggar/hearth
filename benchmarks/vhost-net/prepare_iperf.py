#!/usr/bin/env python3
"""Copy the verified installed iperf closure into a separate guest fixture."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-id", default="fixture-iperf")
    parser.add_argument("--server-console", action="store_true")
    args = parser.parse_args()
    if not args.fixture_id.startswith("fixture-iperf") or not args.fixture_id.replace("-", "").isalnum():
        parser.error("invalid owned iperf fixture ID")
    os.umask(0o077)
    base = ROOT / ".perf/vhost-net/20261004"
    source, target = base / "fixture", base / args.fixture_id
    if target.exists():
        raise ValueError("refusing to replace fixture evidence")
    target.mkdir(mode=0o700)
    guest = target / "guest"
    shutil.copytree(source / "guest", guest, symlinks=True)
    shutil.copyfile(source / "bzImage", target / "bzImage")
    binary = Path(shutil.which("iperf3") or "")
    if not binary.is_file():
        raise RuntimeError("installed iperf3 is missing")
    closure = subprocess.check_output(["ldd", str(binary)], text=True)
    paths = {Path(word) for line in closure.splitlines() for word in line.split() if word.startswith("/")}
    paths.add(binary)
    cancellation = Path("/lib64/libgcc_s.so.1")
    if not cancellation.is_file():
        raise RuntimeError("installed pthread_cancel runtime libgcc_s.so.1 is missing")
    paths.add(cancellation)
    hashes = {}
    for path in sorted(paths):
        destination = guest / path.relative_to("/")
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copyfile(path, destination)
        destination.chmod(0o700)
        hashes[str(path)] = hashlib.sha256(destination.read_bytes()).hexdigest()
    script = (guest / "init").read_text()
    if not script.endswith("wait\n"):
        raise RuntimeError("unexpected original init; do not rewrite it")
    (guest / "perf-state").mkdir(mode=0o700)
    server = f"TMPDIR=./perf-state {binary} -s -B 192.0.2.2 -p 5201 --forceflush"
    script = script[:-5] + (
        f"{{ {binary} --version; {server}; }} >/dev/console 2>&1 &\nwait\n"
        if args.server_console else f"{server} >/dev/null 2>&1 &\nwait\n")
    (guest / "init").write_text(script)
    (guest / "init").chmod(0o700)
    with (target / "initrd.cpio.gz").open("wb") as output:
        subprocess.run(
            ["bash", "-o", "pipefail", "-c",
             "find . -print | LC_ALL=C sort | bsdcpio -o -H newc | gzip -n"],
            cwd=guest, stdout=output, check=True,
        )
    for name in ("bzImage", "initrd.cpio.gz"):
        hashes[name] = hashlib.sha256((target / name).read_bytes()).hexdigest()
    (target / "manifest.json").write_text(json.dumps({
        "classification": "separate installed-binary guest tool closure; no baseline replacement",
        "iperf_version": subprocess.check_output([str(binary), "--version"], text=True),
        "dependencies": closure, "hashes": hashes, "no_heartbeat": True,
        "conditional_dependencies": {"pthread_cancel": str(cancellation)},
        "server_console_diagnostic": args.server_console,
    }, indent=2) + "\n")
    for path in target.iterdir():
        if path.is_file():
            path.chmod(0o600)
    print(json.dumps({"fixture": str(target), "files_in_closure": len(paths), "hashes": hashes}))


if __name__ == "__main__":
    main()
