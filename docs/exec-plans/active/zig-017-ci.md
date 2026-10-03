# Execution Plan: Zig 0.17.0 and ghr-based CI

**Status**: In progress
**Issue**: #4
**Spec**: [Zig Toolchain and CI](../../product-specs/zig-toolchain-ci.md)

## Parallel Workstreams

1. Port `vmm/`: build APIs, translated KVM bindings, language/library changes,
   debug/safe builds, and focused unit/integration behavior.
2. Port `agent/`: target-aware translated libc bindings and both Linux targets,
   preserving PTY, protocol, signal, and file-transfer behavior.
3. Add CI and source-build version checks: signed ghr installation, explicit KVM
   prerequisites, required-result gate, and focused setup tests.

Each implementation runs in an isolated worktree rooted at the spec commit.
The unchanged source is retained in another worktree for the 0.16 baseline.

## Integration and Acceptance

- Merge the workstreams into one integration branch and resolve only migration
  coupling, not unrelated pre-existing behavior.
- Validate TypeScript build/type checks, Zig formatting, debug/safe unit builds,
  both guest-agent targets, and real KVM integration.
- Exercise original/new snapshot compatibility and guest communication.
- Collect compiler-only perf comparisons with repeatable commands and disclose
  unavailable hardware, tools, or coverage rather than claiming success.
- Update directly related setup/build documentation and record actual results.
- Publish a PR, confirm actual CI execution, and enable auto-merge only after
  the required acceptance gates are satisfied.

## Results

The three isolated workstreams were integrated and reviewed. Both packages use
the same immutable translate-c 2.0.0 release revision and content hash.

### Local acceptance

- Flint debug and safe: 31 unit tests and 7 real KVM integration tests each.
- Guest agent: 3 native fork/exec, PTY, and timer tests; both documented target
  builds produce static musl binaries.
- TypeScript typecheck/build, 49 existing CI tests, and 10 focused source-build
  tests pass. The installed-image setup tests require a provisioned rootfs and
  are not counted as passing on this host.
- The new agent boots on kernel 5.10.245 and passes control, exec, file I/O,
  noninteractive/PTY spawn, pause/resume, snapshot, and VirtIO-block smoke checks.
- Snapshots produced by 0.16 restore with 0.17, and vice versa, with the required
  backends supplied and actual guest execution observed after restore.
- A separate read-only review found no significant introduced issues.

### Compiler-only perf comparison

Host: Azure Standard_D16ds_v5, Intel Xeon Platinum 8370C, Linux
6.18.31-1.3.azl4.x86_64, nested KVM, one vCPU pinned to host CPU 8, 128 MiB guest
RAM, kernel 5.10.245, and a 64 MiB ext4 VirtIO backing file. Both variants use the
same unchanged guest source built with Zig 0.15.2: the original agent does not
build with released 0.16, while the original VMM does. Guest-agent migration is
tested separately rather than confounding the VMM compiler comparison.

Each compiler has ten fresh-boot samples, twenty exec samples per boot, five
1 MiB write-and-fsync samples per boot, and one snapshot per boot. The image/cache
conditions and serial heartbeat are identical. The existing idle-vsock polling
limitation requires a controlled 10 ms heartbeat in this minimal fixture; these
are comparative measurements, not production latency claims.

| Measurement | Zig 0.16 | Zig 0.17 |
|-------------|----------|----------|
| Boot median | 910.93 ms | 925.60 ms |
| Boot standard deviation | 26.34 ms | 45.90 ms |
| Exec median | 0.297 ms | 0.295 ms |
| Exec p95 / p99 | 10.626 / 11.022 ms | 0.378 / 0.707 ms |
| 1 MiB write-and-fsync median | 10.191 ms | 7.535 ms |
| I/O standard deviation | 5.788 ms | 4.936 ms |
| Snapshot median | 45.624 ms | 45.247 ms |
| Profiled workload iterations in 3 s | 264 | 417 |
| Profile task-clock / iteration | 2.31 ms | 2.07 ms |
| KVM exits / iteration | 136.36 | 117.06 |

Actual host-side `perf stat` includes task-clock, context switches, migrations,
page faults, and KVM exit/entry tracepoints. `perf record -e cpu-clock -F 199 -g
--call-graph dwarf` and `perf report --stdio` capture the active exec/disk workload;
both reports have zero lost samples. Hardware cycles/instructions are unavailable
on this Azure VM and are not substituted with invented values. Profiles show
KVM ioctl/exit handling, emulation, and file I/O in both variants.

No material compiler regression was observed: the 1.6% boot-median increase is
smaller than the measured run variation, and CPU cost per profiled iteration did
not increase. The large tail/I/O differences are sensitive to fixture scheduling
and are not claimed as proven compiler speedups. Use 0.17 on both sides of the
subsequent VirtIO experiments.

### Remaining merge and coverage gates

Actual hosted PR CI, including KVM execution and the required-result gate, must
pass before merge. Raw perf data, reports, workload runner, and fixture assets
are retained as session artifacts; publish their reproducible recipe with the PR.

The unchanged Flint backend has no host-initiated vsock `CONNECT` listener, so
SDK port-forward/tar-stream acceptance is already blocked on the baseline.
Clean Docker-based Ubuntu image setup and native AArch64 execution are not
verified on this host. Keep these gaps explicit in #4 rather than claiming
complete end-to-end coverage or implementing unrelated backend work here.
