#!/usr/bin/env bash
set -euo pipefail
umask 077
export PYTHONDONTWRITEBYTECODE=1
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT"
LOCK=/d/hearth/.perf/fleet/host.lock
OUT=.perf/vhost-net/20261004
mkdir -p "$OUT"
case "${1:-}" in
  prepare)
    if test -e "$OUT/fixture/hashes.txt"; then
      echo "refusing to overwrite the retained, pinned fixture" >&2
      exit 2
    fi
    mkdir -p "$OUT/fixture"
    if ! test -e "$OUT/fixture/bzImage"; then
      curl --fail --location --max-time 60 \
        https://github.com/joshuaisaact/hearth/releases/download/kernel-5.10.245/bzImage \
        --output "$OUT/fixture/bzImage.download"
      mv "$OUT/fixture/bzImage.download" "$OUT/fixture/bzImage"
    fi
    flock -x -w 600 "$LOCK" timeout 600 bash -euc '
      cd "$1"
      umask 077
      OUT=.perf/vhost-net/20261004
      if test -e "$OUT/fixture/hashes.txt"; then
        echo "refusing to overwrite the retained, pinned fixture" >&2
        exit 2
      fi
      mkdir -p "$OUT/fixture/guest/bin" "$OUT/fixture/guest/dev" "$OUT/fixture/guest/proc" "$OUT/fixture/guest/sys"
      echo "4da539807474d189f1a15852046994e78d430a194c2e78b9255ae880069c7208  $OUT/fixture/bzImage" | sha256sum --check
      zig version > "$OUT/fixture/zig-version.txt"
      zig cc -target x86_64-linux-musl -O2 -static -Wall -Wextra -Werror \
        benchmarks/vhost-net/guest.c -o "$OUT/fixture/guest/bin/peer"
      cp /usr/bin/busybox "$OUT/fixture/guest/bin/busybox"
      ln -sf busybox "$OUT/fixture/guest/bin/sh"
      cp benchmarks/vhost-net/guest-init.sh "$OUT/fixture/guest/init"
      chmod 700 "$OUT/fixture/guest/init"
      (cd "$OUT/fixture/guest" && find . -print | LC_ALL=C sort | bsdcpio -o -H newc) \
        | gzip -n > "$OUT/fixture/initrd.cpio.gz"
      sha256sum "$OUT/fixture/bzImage" "$OUT/fixture/initrd.cpio.gz" "$OUT/fixture/guest/bin/"* \
        vmm/zig-out/bin/flint benchmarks/vhost-net/guest.c benchmarks/vhost-net/guest-init.sh \
        > "$OUT/fixture/hashes.txt"
      file "$OUT/fixture/guest/bin/peer" "$OUT/fixture/guest/bin/busybox" > "$OUT/fixture/file.txt"
      zig cc --version > "$OUT/fixture/cc-version.txt"
    ' bash "$ROOT"
    ;;
  prepare-reset)
    flock -x -w 600 "$LOCK" timeout 300 bash -euc '
      cd "$1"
      umask 077
      export PATH=/home/g/.local/bin:/usr/bin:$PATH
      OUT=.perf/vhost-net/20261004
      NEW=$OUT/fixture-reset
      if test -e "$NEW"; then
        echo "refusing to overwrite reset fixture" >&2
        exit 2
      fi
      mkdir -p "$NEW/guest/bin" "$NEW/guest/dev" "$NEW/guest/proc" "$NEW/guest/sys"
      cp "$OUT/fixture/bzImage" "$NEW/bzImage"
      cp "$OUT/fixture/guest/bin/busybox" "$NEW/guest/bin/busybox"
      ln -s busybox "$NEW/guest/bin/sh"
      zig cc -target x86_64-linux-musl -O2 -static -Wall -Wextra -Werror \
        benchmarks/vhost-net/guest.c -o "$NEW/guest/bin/peer"
      cp benchmarks/vhost-net/guest-init.sh "$NEW/guest/init"
      chmod 700 "$NEW/guest/init"
      (cd "$NEW/guest" && find . -print | LC_ALL=C sort | bsdcpio -o -H newc) \
        | gzip -n > "$NEW/initrd.cpio.gz"
      sha256sum "$NEW/bzImage" "$NEW/initrd.cpio.gz" "$NEW/guest/bin/"* \
        benchmarks/vhost-net/guest.c benchmarks/vhost-net/guest-init.sh > "$NEW/hashes.txt"
    ' bash "$ROOT"
    ;;
  probe|boot|quiet|selftest|strict|resource)
    PHASE=$1
    shift
    flock -x -w 600 "$LOCK" timeout 900 sudo -n env PYTHONDONTWRITEBYTECODE=1 unshare --mount --net -- \
      python3 benchmarks/vhost-net/runner.py --artifact-dir "$OUT" --phase "$PHASE" "$@"
    ;;
  test)
    flock -x -w 600 "$LOCK" timeout 600 bash -euc '
      cd "$1"
      umask 077
      python3 -m unittest discover -s benchmarks/vhost-net -p "test_*.py" -v
      cd vmm
      zig build test -Dtarget=x86_64-linux -Doptimize=debug --summary all
      zig build test -Dtarget=x86_64-linux -Doptimize=safe --summary all
    ' bash "$ROOT"
    ;;
  *)
    echo "usage: $0 prepare|prepare-reset|boot|strict|selftest|test [fixture options]" >&2
    exit 2
    ;;
esac
