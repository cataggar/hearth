# Product Spec: Zig Toolchain and CI

**Status**: In progress
**Last updated**: 2026-10-03

## Goal

Build Flint and the guest agent with Zig 0.17.0 without changing the sandbox
protocol, snapshot format, isolation, or supported VMM architecture. Add CI that
actually builds and tests the Zig components, while retaining the existing
TypeScript checks.

## Requirements

- Pin Zig 0.17.0 in package manifests and use pinned, target-aware translate-c
  dependencies for Linux KVM and guest libc headers.
- Fetch the translate-c 2.0.0 compatibility fork and its unchanged Aro dependency
  from GitHub using immutable commits and content hashes. No transitive source
  fetch should depend on Codeberg availability.
- Preserve safe optimization for installed binaries. Source-build setup checks
  the compiler version before building and reports an actionable error.
- Install the compiler in CI with `cataggar/ghr/actions/install@v0.6.1`, selecting
  signed `cataggar/zig@v0.17.0` with its public verification key. Use read-only
  workflow permissions.
- On hosted Linux runners, check formatting, build/test Flint in debug and safe
  modes, and build the agent for x86_64-linux and aarch64-linux.
- Run KVM integration separately on a verified KVM-capable Linux runner. Check
  kernel, KVM, and initrd prerequisites explicitly; an entirely skipped suite is
  not passing integration coverage. Never run untrusted PR code on this
  persistent development VM.
- Grant the ephemeral runner access through `kvm` group membership and start
  KVM steps with that group active. Do not run acceptance as root or make
  `/dev/kvm` world-writable.
- Provide a stable Zig validation status that fails on failed or unexpectedly
  skipped required jobs. Keep existing TypeScript job names and checks.
- Validate boot, lifecycle and snapshot operations against the existing guest
  kernel. Preserve compiler-transition snapshot and guest-protocol compatibility.

## Performance Gate

Compare a working 0.16 build and the compiler-only 0.17 port on nested Azure KVM
using host-side `perf stat`, `perf record`, and `perf report`. Record compiler,
commit, kernel, CPU/SKU, commands, optimization, samples, variance, and limitations.
Use software events if hardware PMU events are unavailable. Investigate meaningful
regressions; do not attribute a compiler change to the later VirtIO experiments.

## Non-goals

No ioeventfd/irqfd, vhost-net, async block I/O, new VMM architectures, snapshot
format changes, or unrelated SDK behavior changes are included.
