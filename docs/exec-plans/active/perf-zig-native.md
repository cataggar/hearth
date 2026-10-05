# Execution Plan: Native Zig Codegen and Linker Experiment

**Status**: Partial implementation verified — native adoption rejected by size; full qualification incomplete

**Date**: 2026-10-04

**Issue**: [#6](https://github.com/cataggar/hearth/issues/6)

**Spec**: [Native Zig codegen and linker experiment](../../product-specs/perf-zig-native.md)

Implementation runs on `copilot/perf-zig-native-20261004` at base `b06ec0a`,
excluding #1/#2/#3 performance prototypes. A later, separately authorized
shared jail-correctness baseline is reused byte-for-byte for both arms; its
results are not pooled with untouched-runtime results or credited as speedups.
No production-default change or adoption is claimed. The merged #5 compiler
migration is a prerequisite already completed, not work to repeat.

### Post-orphan-cleanup restart

The parent stopped only the explicitly approved/revalidated old orphan
busy-loop shells. Previous saturation/noisy samples are not current controls.
Resume canonical `ced7ed7` group clearing and `e1d3be0` collector confinement
first, then refresh source/toolchain/target/topology identities, forced native
correctness and unchanged A/A. A fresh quiet window must be demonstrated, not
assumed. Keep the frozen gates, original artifacts and measurement boundaries;
monitor/reap only owned children and current storage before bounded phases.

Canonical ced/e1 selected files now match byte-for-byte. Explicit CI
LLVM/LLD/native/native Debug/safe refreshed cells pass forced32+7 and common3
per cell; unset defaults pass32+7. Own recorder/guard/archive suite passes21,
common protocol/cache suite9. Initial fresh locked host control is12.05% busy
(1.9279/16cores), not assumed quiet. Fresh size artifacts still fail the
unchanged10% gate. Old noisy/Group0 counts remain a separate epoch.

Manifest-driven paired `build` is implemented: dependency-source-only seeds,
independent cold caches, warm no-op and exact source-fragment rebuild, pristine
restoration on failure, fixed affinity/parallelism, raw artifacts and verified
archive retention. New `runtime` records actual jailed boots/restores,
numbered PTY ACKs, exec/disk/vsock, idle and1/2/4/8 concurrency, plus inherited
private stat/stack collectors; coverage pilots and full sample execution remain
incomplete. Neither tool's completion implies adoption or complete
asynchronous kernel CPU accounting.

Fresh Debug unchanged A/A now completes ten paired repetitions of all three
conditions: cold median114.0748s/CV2.5613%, warm26.2708ms/CV27.1557%,
codegen-changing rebuild0.982117s/CV3.5770% (20 observations each). The
512→513MiB cloned-source patch changes emitted `.text`; pristine source is
restored. Warm live-tree RSS sampling sometimes observes no process and cannot
qualify peak memory. A real ENOSPC interruption after five pairs is preserved;
verified same-manifest resume contributes the remaining five, not an automatic
noise/acceptance decision. Safe A/A and explicit Debug comparisons each retain
six complete pairs/36 rows; repeated resumes halt at the unchanged4GiB guard.
Safe comparison has not started. Partial medians/CVs are recorded in the spec,
not promoted to compilation-benefit qualification.

Corrected inherited stat captures contain real software/KVM counters. Initial
v3 group termination prevented stat flushing: empty captures are **not** valid
coverage despite successful guest commands. v4 signals the owned Flint process,
then waits for the collector to flush. Short restore-only49Hz windows have one
sample and no identifiable Flint entry; successful report generation is not
complete stack coverage. A separately retained new-process-restore plus1000
verified guest-exec augmentation produces identifiable Flint stacks in all four
cells,19–28 samples and zero reported loss. It is not isolated restore cost or
repeated profiler-overhead confidence. A paired250ms-process-CPU calibration
establishes this installed perf's blank-unit task-clock values are raw
nanoseconds (270,332,649 against0.250004s guest-free process CPU); no milliseconds
normalization is guessed.

Both fresh GNU/native-CPU safe backends again execute32+7, but enforced-jail
guest boot fails SIGSYS and each common suite passes2/3. Fresh Debug
no-heartbeat trials initially connect6/6, then all6/6 time out on post-five-second
exec within the fixed two-second host deadline. These baseline gaps are not
production idle/performance passes. Only completed own snapshots/caches are
compacted after exact-byte/link verification; the shared storage incident and
capacity guards remain documented, with no other task's resources removed.
Safe no-heartbeat likewise connects6/6 then completes0/6 post-idle execs.
Four renewed fixed-VMM agent guest/snapshot controls pass with empty groups.
The owned-network-namespace TAP recipe passes100/100 packets in each primary
cell with actual inherited software/KVM counters and verified namespace/node
teardown; this is basic ICMP acceptance, not TCP/UDP performance/sample minima.
Initial TUN-node cleanup failure is preserved separately and its exact owned
node cleaned before successful repetition. Nine completed own cache trees are
retained in exact-byte/link-verified archives, reducing logical storage by
5,000,446,260B without touching active caches/fixtures/other tasks. A second
capacity guard halts safe A/A after two pairs; later same-manifest resumes reach six pairs before
another unchanged guard interruption. Resume does not automatically qualify
pooling or noise.

The v4 full runtime attempt retains seven passing Debug boot/restore rows;
v4 pilots retain42 passing guest rows, not minimum-sample qualification.
An additional193 exact-byte-verified completed binary archives release
2,625,690,135 logical bytes; snapshot/cache/binary recovery totals about13.246GB.
Current fixtures, frozen runtime executables and active caches remain intact.
No independent free-space change is attributed to this task.

The parent's newer8.733/16-core locked whole-host control is separate from
this task's per-run controls and does not establish a quiet window or explain
old samples. No other workload is inspected/killed/moved and no cleanup is
reported as an optimization. Frozen gates and both storage guards remain fixed.

Owned-only descendant task-child traversal replaces global process metadata
scans. Profiled Flint uses a credential/start-time-checked pidfd to prevent
numeric PID reuse; failed collector flushing invalidates the capture after
owned-group cleanup. The current focused21 tests and four actual API-only
Debug/safe×LLVM/native jail/pidfd/stat/teardown controls pass. Those API-only
controls are not guest/KVM performance acceptance. v5 correctly rejects its
stale recorder hash. At the common-prerequisite coordinator's request, the
queued v6 phase is stopped before manifest preparation/VM startup pending a
validated correctness-only bridge and independent enforced-jail fixture.
The owned socket directory is empty and no fleet lock is held. No v6 rows
execute. Resume only after the bridge's exact hash/commands arrive, then freeze
new identities; do not pool earlier recorder/RSS-method measurements.

Canonical convergence is now verified against supplied `7dfee42`: own
cherry-pick `327f183` adds only the standalone fixture/contract, because the
three runtime/unit blobs already match byte-for-byte. No async/notification,
codegen, dependency or device option changes are imported. All five canonical
files match, and the kernel is the same verified5.10.245 input. Attempted
standalone three-case Debug/safe×LLVM/native and renewed forced32+7 phases
fail actual Err28 at output-directory creation before any command/VM launch.
A tiny retry aborts its512MiB capacity check; a third passes a1GiB pre-queue
check but again fails Err28 at locked launch. Zero new rows execute. This is
storage failure, not missing canonical repair or backend/permission rejection.
Independent free-space fluctuations are not attributed; pre-queue checks are
not reservations. All owned phases end, with no fixture/VM/helper/socket/lock.
The remaining named own compiler intermediates total only16,666,624 allocated
bytes; no active cache/frozen input is discarded. Resume with durable artifact
capacity, retaining4GiB/3GiB guards. Failure records are
`postcleanup-summary/canonical-bridge-storage-attempt{1,2,3}.json`.
Canonical correctness convergence is not optimization adoption.
A fourth standalone-only alternative checks512MiB inside the exclusive lock;
actual locked capacity is9,588,736B, so it aborts before any output/fixture
directory or compiler/test/VM. Zero accepted cases, no owned resource or held
lock. `canonical-bridge-storage-attempt4.json` preserves this direct proof;
the missing prerequisite is durable capacity, not a runtime repair or assumed
quieter machine. Do not weaken512MiB correctness or4GiB/3GiB measurement guards.
The next available v5 window actually completes all four static
Debug/safe×LLVM/native cells:32 forced units+7 real KVM+3 standalone enforced
API/CLI cases each, no skips/cached execution (128/28/12 total). All24 recorded
standalone PID paths are gone; private nodes/sockets removed. Commands/rosters/
cleanup are in `postcleanup-summary/canonical-v5-final.json`; different cache
histories make these test-build timings unsuitable for a compilation-speedup
comparison. The four earlier storage failures are not relabelled passing.
Own fresh locked5s control is6.4877 busy cores/0steal/0.01s iowait, not quiet
acceptance or the peer's1.64-core control. SMT8-9/client0-1 is freshly checked.
Fresh v7 current-source guest/stat preparation fails actual Err28 at manifest
directory creation under the fleet lock, before any manifest/VM/runtime row.
Completed v5 correctness remains valid; no backend rejection or runtime pass
is inferred. All owned phases end. Durable profile/measurement storage remains
necessary, with unchanged3GiB guard and separate new identities/epochs.
V8 continues the original runtime/stat pilots and a separately frozen ten-pair
safe reference A/A, with258 pinned source/package hashes and the owned-only
recorder epoch. Manifest creation succeeds, then actual3GiB/4GiB capacity
guards refuse before any VM/build row. Original512MiB source remains pristine.
`postcanonical-v8-capacity-refusals.json` retains exact errors; do not call zero
new rows a zero-cost/cached profile, unsupported backend or complete execution.
No #3 Azure/runtime/host measurement or other peer evidence is inherited.
V9 repeats identical v8 inputs after a peer-reported release/space increase;
actual3GiB/4GiB guards still refuse, zero new rows and pristine source. Both
phases end; exact diagnostics are in `postcanonical-v9-capacity-refusals.json`.
Peer capacity/control/cache/writeback regimes are not treated as own evidence.
Retained deny cases are BPF-evaluator assertions in the32-unit suite, not
real-kernel negative child executions. The separate three-case fixture supplies
actual enforced API/CLI permissions/disk/all-task-identity acceptance.

### Standalone ENOSPC cleanup follow-up

Reuse only the exact fixture/contract follow-up `98b10c21` on top of canonical
`7dfee42`. VMM/runtime/unit files and the four named static ELFs remain unchanged.
Validate four actual standalone cases per Debug/safe × LLVM/native cell,
including injected cleanup-evidence ENOSPC with owned teardown despite the
propagated error. Preserve v5 and guard-failure epochs separately. Each bounded
phase checks512MiB inside the exclusive fleet lock and releases between cells;
no compilation, profiler, performance image or measurement-guard change.
Own `3414df4` adopts only the exact two shared follow-up files; all three
VMM/runtime/unit blobs remain canonical `7dfee42`. Actual fresh cells pass
4/4 each,16/16 total, no skips, using the four hash-verified named ELFs.
Eight guest-disk boots and four injected-evidence-failure API children remain
small synchronous correctness, not agent/timer-free/runtime performance.
All32 recorded PID paths and private node/socket paths are gone, fault-case
logs close and injected ENOSPC propagates. Locked capacity is3.336–3.471GB at
those instants, not reserved capacity or a quiet-host certificate. Commands,
all-task identities, exact hashes and ordinary/fault cleanup records are in
`postcleanup-summary/canonical-cleanup-enospc-v1-final.json`. Existing128/28/12
v5 forced/standalone counts are not relabelled newly executed; all size,
GNU/default, safe-A/A and full profiling/runtime blockers remain.

## Evidence and fixed scope

The spec records inspected definitions at Hearth
`b07f73b26b8ae876928d9c515b94bba1e9945870`, installed Zig `0.17.0` API/help,
both package manifests, the immutable translate-c helper/Aro manifests, setup,
CI, tests and architecture. Consult
[toolchain spec](../../product-specs/zig-toolchain-ci.md),
[completed migration](../completed/zig-017-ci.md), and the
[prior recipe](https://github.com/cataggar/hearth/pull/5#issuecomment-5973822154).
Those historical acceptance/perf results are not native-backend acceptance.

The unchanged baseline leaves `use_llvm`/`use_lld` unset. The implementation
adds opt-in controls and preserves those defaults. Source setup requests `safe`;
normal VMM development defaults to `debug`; agent defaults to safe/static musl.
Observed CI-target defaults are native/native Debug and LLVM/LLD safe for all
three VMM artifacts. See the results below; historical planning uncertainty is
not a current unsupported-safe result.

One frozen compiler binary, source tree and experimental patch, target/CPU/ABI,
optimization and dependency set must be used throughout. Leave #1/#2/#3 device
changes out, including during baseline selection. Keep an unchanged guest
agent for VMM runs; evaluate the agent later with a fixed VMM.

## Work packages and dependencies

```text
W0 identity/default discovery, fixtures, A/A controls and gate freeze
  -> W1 opt-in wiring, diagnostic/support matrix and runner
  -> W2 native correctness + bidirectional cross-backend snapshot acceptance
W2 -> W3 controlled build measurement
W2 -> W4 nested-Azure runtime measurement
W3 + W4 -> W5 separate agent matrix/acceptance/measurement
W5 -> W6 keep/reject decision; optional adoption + rollback validation
```

W1 may develop runner/options while W0 finishes fixture inventory, but its
acceptance depends on frozen W0 inputs. W3 and W4 can be scheduled in either
order after W2; **never overlap their timed runs**. W5 requires a frozen,
correct VMM and a documented W3/W4 comparison, not adoption of native defaults.

Independent subtasks suitable for parallel work on separate development
resources: manifest/statistical-analysis tooling; opt-in build wiring; and
fixture/workload-runner preparation. Agent support *planning* can run alongside
these. Serialize shared build-file integration, correctness on the reserved
host and every timed build/profile. Do not run competing #1/#2/#3 experiments.

### W0 — Freeze identity, prerequisites and baseline gates

- Select an unchanged-runtime revision and identical options-only patch for
  all worktrees. Record parent/patch hashes and clean-state checks; do not use
  branches containing runtime experiments.
- Verify signed Zig `0.17.0`, real executable path and SHA-256/package identity.
  A release-mirror tooling commit is not necessarily the compiler source
  revision: record the compiler source identity if published, otherwise state
  unavailable and pin exact signed binary bytes. No new compiler version.
- Verify both translate-c hashes and its Aro pin against the spec. Record
  headers/libc versions and target-aware translation arguments. Keep dependency
  helper target, optimization and backend/linker settings invariant.
- Inventory current `zig build`, explicit debug/safe, CI x86_64-linux, and
  source-setup/native-target selections. Record query and resolved CPU/features,
  ABI/OS range/linkage separately; never assume Debug equals ReleaseSafe.
- Reserve a quiet nested Azure KVM host. Freeze CPU/SKU/host kernel/microcode,
  guest bzImage/initrd/agent/rootfs/disk hashes, one vCPU/128 MiB comparison
  fixture where supported, affinity and disk/TAP topology. A different SDK
  configuration is a separately frozen workload, not silently substituted.
- Verify non-root KVM access, actual VM creation, tools, available perf events
  and privileges. Keep profiling privilege separate from VMM privilege.
- Adapt the 10 ms-heartbeat fixture without changing its behavior between
  variants. Inventory no-heartbeat behavior and existing SDK/vsock CONNECT
  gaps. Record blocked cases with baseline logs, not as pass/zero latency.
- Repeated A/A controls establish variance. Freeze numeric success/regression
  gates from the spec, sampling policy and near-zero floors before viewing
  candidate results. Stabilize/noise-adjust prospectively; do not inflate
  tolerances to excuse a candidate regression.

**Exit:** immutable manifest, default-selection evidence, baseline support/gap
inventory, reserved host window and gate file. Missing KVM/perf/fixtures blocks
execution, not this planning document.

### W1 — Implement opt-in mechanics and classify support

1. Add proposed `vmm-codegen` / `vmm-linker` options (`auto` default), mapping
   `native/native` to the issue's `exe.use_llvm = false; exe.use_lld = false;`.
   Apply identically to unit and integration compile artifacts; analogous
   `agent-*` options are separate. `auto` preserves nullable fields.
2. Add opt-in `perf-force-test-run` so unit runs cannot be accepted from cache;
   preserve integration `has_side_effects`. Use it for baseline and candidates.
3. Add a narrow project-relative integration-kernel override, proposed
   `perf-test-kernel`, because today's fixture hardcodes `/tmp/vmlinuz-minimal`.
   Pass the identical kernel to every variant; retain normal test defaults.
   Keep default install layout for integration or explicitly pass/test a binary
   override too. Changing only `--prefix` would violate current test paths.
4. Build a repeatable runner using argument arrays, not shell-evaluated manifest
   strings. Use project-relative worktrees, caches, short private socket/fixture
   paths and artifact directories. No temporary-directory historical runner
   defaults or fixed CPU 8 assumptions.
5. Capture `--verbose`, `--verbose-link`, resolved build configuration and
   compiler diagnostics. Confirm artifact backend with generated/diagnostic
   compiler information and confirm linker selection through the exact
   compiler's selection evidence; an unset field or absent external LLD process
   is not proof. LLD can execute in process.
6. Probe the spec's five rows for VMM x86_64 Linux debug/safe, including native
   test artifacts. Explicitly classify unsupported mixed/optimization/libc
   cases with full commands and stderr; do not retry with weaker safety,
   altered features/ABI or hidden fallback.
7. Distinguish artifact flags from Zig's build configurer and translate-c helper.
   Do not set translate-c's separate `llvm` option to impersonate measured
   executable settings. Fix helper settings and account for their cost.
8. Freeze a representative codegen-affecting incremental source patch per
   component, applied identically to warmed copies. Save the patch/hash,
   impacted modules and pristine restoration check. Touch/comment-only edits
   are not the incremental experiment.

**Exit:** supported/failed/blocked matrix, executable/test identity evidence,
unchanged-default checks and runnable manifest-driven measurement tool. If
native/native is unsupported in safe, record that limitation; debug success
cannot justify a safe-production change.

### W2 — Execute correctness before timing

- For every supported candidate and explicit reference, execute VMM unit tests
  and all KVM integration cases in debug and safe. Reconcile current case
  inventory (31 top-level unit tests and seven integration cases) with runtime
  summaries at the chosen revision. Require no skips/cached runtime success.
- Verify that the actual installed executable and each test artifact have the
  requested backend; retain binary hashes/commands/counts/stderr. Current
  integration's install dependency and project-relative paths must be honored.
- Extend the prior guest smoke coverage to API errors/status/configuration,
  boot/readiness, protocol reconnect/framing, exec output/exit/timeout/signals,
  PTY input/output/resize, file contents, block read/write/fsync, supported
  guest-initiated vsock/TAP traffic, repeated pause/resume/stop/kill/teardown and
  concurrent lifecycle. Installed SDK gaps remain separate failure/block rows.
- Produce LLVM/LLD snapshots, kill the creator, reopen disk/net/vsock resources
  under native/native, and execute commands/read persisted state after restore.
  Reverse the direction. Include same-backend controls in both supported modes;
  snapshot file existence, format unit tests or restored API status is not
  sufficient. Do not alter snapshot format or isolation.
- For the actual source-build/native-target configuration, validate the same
  target/CPU/safety contract; do not infer it from CI-target success.

**Exit:** genuine native test execution and lifecycle/snapshot compatibility
evidence. An introduced failure stops measurement/adoption for that cell; a
documented baseline gap is not reclassified as successful candidate coverage.

### W3 — Measure build cost

- Prefetch dependencies separately, retaining download log/timing. Discover the
  compiler's dependency-only cache layout and seed independent local/global
  artifact caches identically; do not copy warmed helper/configurer outputs.
- Measure cold, warm no-op and identical incremental-patch builds at fixed
  parallelism/affinity. Compile native test artifacts separately with
  `integration-test-build`; do not include their execution in build timing.
- At least ten independent repetitions per condition/cell, counterbalanced
  reference/candidate order. Record OS page-cache policy; no global cache flush
  on a shared machine. Restore sources before all runtime runs.
- Account for whole-tree wall/CPU, simultaneous peak tree RSS, size/sections and
  translation/helper/link phases. Dedicated cgroup CPU accounting plus
  live-process RSS sampling can be used; publish sampling resolution, missing
  short-lived-process caveat and supporting `memory.peak` separately.
- Retain per-run raw measurements, patch/cache identities, complete logs and
  binary hashes. Summarize median/mean/standard deviation/CV/range/confidence
  intervals; do not remove inconvenient outliers or count downloads as codegen.

### W4 — Profile runtime on nested Azure

- Freeze exact VMM/guest binaries and fixtures from W2, with no W3 incremental
  edits. Do not rebuild while capturing runtime performance.
- Run fresh boot, snapshot + new-process restore, exec/PTY/files, representative
  block I/O, supported vsock/network, 1/2/4/8 concurrent sandboxes where feasible,
  and idle. Verify correctness during each run and count completed operations.
- Follow spec sample minima and session-level uncertainty. Increase independent
  boots/restores for stable p99 claims; their initial 30 samples are not strong
  tail evidence. Alternate/seed variant order and separate warmup samples.
- Capture real perf stat, stack-enabled record and report in repeated profiling
  runs; measure latency separately without profiling. Cover all VMM threads and
  independent affected helpers, early boot/restore and process churn, not only a
  single surviving PID. Normalize CPU/exits by in-window completed operations.
- Test software/KVM events when hardware PMU is absent. Report unavailable PMU
  and tracepoint coverage, lost samples and profiler overhead. The guest PMU is
  hidden/not assumed available; do not invent guest counters.
- Keep heartbeat and no-heartbeat rows separate. Baseline CONNECT/SDK/network
  blockers get logs and status, not fabricated rates or production claims.

**Exit:** raw build/runtime profiles and uncertainty-aware paired comparison
against explicit LLVM/LLD and the actually resolved current defaults.

### W5 — Evaluate the agent independently

Freeze a correct VMM and repeat the safe build matrix for documented
x86_64-linux and aarch64-linux queries, preserving resolved static musl.
Optional debug probes are labeled separately. Test native x86_64 fork/exec,
PTY/ioctl and timer artifacts and run guest protocol/lifecycle workloads with
the candidate agent; rebuild only the agent between paired runs.

Separate guest agent process CPU/software profiling from host VMM cost; host
task-clock includes guest execution and is not agent-exclusive accounting.
Cross-build AArch64 and inspect ELF/static linkage, but obtain matching native
hardware for tests/performance or explicitly leave that runtime cell blocked.
No AArch64 VMM support or cross-build-as-execution claim is introduced.

### W6 — Decide, optionally adopt and validate rollback

Classify keep/reject/inconclusive/unsupported per target/mode, including mixed
rows only with their own evidence. Compare with frozen numerical gates and
both explicit reference and actual defaults. A statistically unresolved
improvement, native-safe failure or isolated debug build win is not permission
to change safe setup/release defaults. Negative results satisfy the experiment.

Only for adopted cells, integrate build/test options, TypeScript source-build
paths and agent fallback, CI optimization/target coverage and documentation.
Preserve compiler version checks, immutable translation pins, signed ghr
installation, existing TypeScript job names, stable `Zig validation`,
skip rejection, `sg kvm` and non-root device access. Do not make the KVM device
world-writable or run acceptance as root.

Retain opt-out/known-good binary identities. Revert adopted artifact defaults
and source-build selection to their previous values, rebuild with the same
signed compiler, and execute retained snapshots/guest commands for rollback.
No snapshot conversion or data migration. Complete the plan only after durable
artifacts/decision are recorded; do not mark implementation complete now.

## Reproducible interfaces and remaining design examples

The artifact options, forced tests, project-relative kernel override and
`run`/`batch`/`summarize`/`probe` recorder are implemented. Exact executed argv,
status and identities are in private evidence. The `build`/`runtime` subcommands are implemented diagnostic interfaces;
complete qualification is not implied by executing them. All
operations must use `umask 077` and the exclusive fleet lock; direct identity,
prefetch, build and perf examples also require that lock.

### Identity and dependency prefetch, outside timing

```bash
ROOT="$(git rev-parse --show-toplevel)"
ZIG="$(command -v zig)"
OUT="$ROOT/.perf-zig-native"
test "$("$ZIG" version)" = 0.17.0
git rev-parse HEAD
readlink -f "$ZIG"
sha256sum "$ZIG" vmm/build.zig.zon agent/build.zig.zon
"$ZIG" env
mkdir -p "$OUT/dependencies"
(cd vmm && ZIG_GLOBAL_CACHE_DIR="$OUT/dependencies/global" \
  "$ZIG" build --fetch=all --cache-dir "$OUT/dependencies/vmm-local")
(cd agent && ZIG_GLOBAL_CACHE_DIR="$OUT/dependencies/global" \
  "$ZIG" build --fetch=all --cache-dir "$OUT/dependencies/agent-local")
```

Use the existing signed compiler installation contract if provisioning a new
host; do not install a newer compiler or modify dependency manifests. Prefetch
may itself compile build infrastructure; only dependency source packages, not
those compiled artifacts, seed cold-run caches.

### VMM support/build and real tests after W1

`VMM_TREE` is an isolated tree with the identical W1 patch. `VMM_TARGET` and
`VMM_CPU` are the exact resolved target/feature values frozen by W0, not
unilaterally changed to `native` or `baseline`. `MODE` is `debug` or `safe`.
Use pairs `auto/auto`, `llvm/lld`, `native/native`, and supported `llvm/native`
or `native/lld`; every cell has its own `CACHE`.

```bash
(cd "$VMM_TREE/vmm" && ZIG_GLOBAL_CACHE_DIR="$CACHE/global" \
  "$ZIG" build install integration-test-build \
  -Dtarget="$VMM_TARGET" -Dcpu="$VMM_CPU" -Doptimize="$MODE" \
  -Dvmm-codegen="$CODEGEN" -Dvmm-linker="$LINKER" \
  -Dperf-test-kernel="$KERNEL" \
  --cache-dir "$CACHE/local" --summary all --color off \
  --verbose --verbose-link)

(cd "$VMM_TREE/vmm" && ZIG_GLOBAL_CACHE_DIR="$CACHE/global" \
  "$ZIG" build test integration-test \
  -Dtarget="$VMM_TARGET" -Dcpu="$VMM_CPU" -Doptimize="$MODE" \
  -Dvmm-codegen="$CODEGEN" -Dvmm-linker="$LINKER" \
  -Dperf-test-kernel="$KERNEL" -Dperf-force-test-run=true \
  --cache-dir "$CACHE/local" --summary all --color off --verbose)
```

No custom install prefix is used in these integration commands. A standalone
`zig build` command with the same target/options is the measured executable
build; test compilation/execution are distinct observations. The implemented recorder enforces timeout, exit-code failure and persistent logs.
It does not itself enforce test counts/skips; correctness logs are explicitly
checked for the relevant epoch's31 or32 +7 passes and absence of skips/cached
runs. The paired build interface times only compile steps.

### Separate agent safe probes

```bash
(cd "$AGENT_TREE/agent" && ZIG_GLOBAL_CACHE_DIR="$CACHE/global" \
  "$ZIG" build -Dtarget="$AGENT_TARGET" -Dcpu="$AGENT_CPU" -Doptimize=safe \
  -Dagent-codegen="$CODEGEN" -Dagent-linker="$LINKER" \
  --cache-dir "$CACHE/local" --summary all --color off --verbose)
readelf -h -l "$AGENT_TREE/agent/zig-out/bin/hearth-agent"
```

`AGENT_TARGET` comes from frozen x86_64-linux/aarch64-linux musl resolution.
Run `zig build test` with the same arguments and forced execution only on a
matching native host; x86_64 cross-building AArch64 is build-only evidence.

### Runner and host perf capture

Implemented manifest-driven interfaces (counts, conditions and variant order
come from the frozen manifest, not additional CLI switches):

```bash
python3 scripts/perf-zig-native.py build \
  --manifest "$OUT/build-manifest.json" --output "$OUT/build"
python3 scripts/perf-zig-native.py runtime \
  --manifest "$OUT/runtime-manifest.json" --output "$OUT/runtime"
```

The manifest supplies sample counts, repetitions and counterbalanced order.
Runtime supports boot/restore, exec, PTY, disk, vsock, concurrency and idle;
unsupported TAP/network requires a separate explicit diagnostic recipe rather
than an invented successful row. Extend beyond the old
`migration-smoke.py` recipe: it lacks timed restore, concurrency/idle/PTY tails
and full process coverage.

After verifying event availability, representative *steady-state* capture is:

```bash
EVENTS=task-clock,context-switches,cpu-migrations,page-faults,kvm:kvm_exit,kvm:kvm_entry
perf stat -x, -e "$EVENTS" -p "$VMM_PIDS" \
  -o "$CAPTURE/perf-stat.csv" -- sleep 30
perf record -e cpu-clock -F 199 -g --call-graph dwarf \
  -p "$VMM_PIDS" -o "$CAPTURE/perf.data" -- sleep 30
perf report --stdio -i "$CAPTURE/perf.data" > "$CAPTURE/perf-report.txt"
```

Run stat/record in separately repeated active-workload windows; log exact
operation-count boundaries. `VMM_PIDS` includes all affected running processes,
not just one VMM; verify thread inheritance and helper coverage. These attach
examples alone do **not** cover process startup: the runner must use
command-mode profiling/inheritance or dedicated scoped accounting before
launch for boot/restore and changing concurrency. Include permitted backend
worker CPU separately where PID attachment cannot account for it.

Current restore CLI, to be driven by the runner with actual guest checks:

```bash
"$RESTORING_FLINT" --restore --vmstate-path "$STATE" --mem-path "$MEMORY" \
  --disk "$DISK" --vsock-cid 100 --vsock-uds "$VSOCK" --api-sock "$API"
```

Recreate the host guest-control listener first; add the same `--tap "$TAP"` if
the snapshot includes a network device. Do not restore disk/vsock/net snapshots
without reopening their backends. Execute this in both cross-backend directions
and verify guest command/file/I/O results, not merely process/API survival.

## Artifact manifest and persistence

Keep a manifest plus per-run build logs/metrics, environment/prerequisite
diagnostics, test logs, executable/fixture hashes, incremental patch, snapshots,
operation samples/counts, perf CSV/data/reports and analysis inputs under the
project-relative artifact root; publish an appropriately access-controlled
durable artifact bundle with the eventual decision.

Manifest fields: full source/patch/compiler/dependency revisions and hashes;
signed compiler asset/version; requested/resolved backend/linker per artifact;
all expanded command argv/environment; target/CPU/features/ABI/optimization/
libc/header/linkage; build job count; host/guest kernels, Azure SKU, CPU/microcode,
vCPU/RAM/affinity, kernel/driver/device/queue/TAP/disk topology; KVM/perf permission
state and PMU visibility; guest agent/rootfs/initrd/disk/snapshot hashes;
cache-seeding/download/OS-cache policy; fixture heartbeat, warmups, seed/order,
sample counts, concurrency, profiler intervals/events/stacks/lost samples;
baseline gate/noise decisions; unsupported/blocked diagnostics and cleanup.
Collect anonymous performance/environment data only, not workload secrets.

Clean up only runner-owned VM processes, TAPs/sockets/worktrees after retaining
required evidence. Do not delete shared caches or other experiments' artifacts.

## Likely future change files

| Files | Scope if implemented/adopted |
|-------|-----------------------------|
| `vmm/build.zig` | Opt-in executable/unit/integration artifact flags, forced test execution and narrowly scoped fixture options. |
| `vmm/src/integration_tests.zig` | Project-relative kernel/binary override where required; real compatible snapshot/fixture acceptance. No runtime backend rewrite. |
| `agent/build.zig`, `agent/src/posix.test.zig` | Separate artifact flags/native test execution; focused extra ABI regression tests only if warranted. |
| `scripts/perf-zig-native.py` (new, proposed) | Repeatable cache/patch/run/profiling accounting, manifests and sample analysis; verify final interface. |
| `src/cli/zig.ts`, `src/cli/setup.ts`, `src/cli/setup.test.ts` | Only if adopted: consistent safe/source-build selection for VMM/setup-agent fallback and version/error/idempotence behavior. Prebuilt agent provenance stays explicit. |
| `.github/workflows/ci.yml`, `README.md`, toolchain spec and these docs | Adopted supported target/mode coverage, signed install/non-root KVM/required checks and reproducible usage/results. |
| `vmm/build.zig.zon`, `agent/build.zig.zon` | Audit and hash only; pins must remain unchanged for this experiment. |

## Risks and unresolved decisions

- Exact safe/native ELF/libc and AArch64 codegen/linker support is unknown.
  Decide eligibility from the support matrix, not speculation or changed flags.
- Automatic backend choices may already be native in one mode; compare actual
  defaults and explicit reference without misattributing an existing choice.
- Helper/configurer compilation and libc work can dominate build time; native
  executable settings do not make all compiled build infrastructure native.
- Azure nested scheduling/PMU limits, host page-cache differences and heartbeat
  exits can obscure small effects. Predeclare noise gates; unresolved tails
  cannot support adoption. Retain nested-Azure evidence even if another host
  is available as supplemental data.
- Is the cold/incremental build-benefit gate the appropriate developer tradeoff,
  and are absolute idle/near-zero floors resolvable? Freeze the answer from
  baseline A/A before candidate results; no after-the-fact threshold tuning.
- Which mode/target should be adopted, if any? VMM and agent decisions are
  independent; cross-build-only support is insufficient for agent runtime claims.
- Project-relative fixture options are prerequisite harness work, not permission
  to fix pre-existing SDK/CONNECT or VirtIO polling gaps in #6.

## Completion checklist

- [x] Spec written first; linked issue, source-backed contract and active plan.
- [ ] Frozen identity/pins/default evidence, baseline gaps and numeric noise gates.
- [x] Opt-in artifact-consistent VMM matrix; unsupported/fallback diagnostics retained.
- [x] Real native unit and all KVM integration execution, no skips/cache acceptance.
- [ ] API/boot/protocol/exec/PTY/files/I/O/concurrent lifecycle checks.
- [x] LLVM -> native and native -> LLVM snapshots with actual restored execution.
- [ ] Repeated cold/warm/incremental wall/total CPU/tree RSS/size measurements.
- [ ] Nested Azure perf stat/stack record/report, runtime tails/throughput/CPU/exits.
- [ ] Heartbeat, unavailable PMU and pre-existing workload gaps explicitly reported.
- [ ] Independent agent static-musl targets; cross-build/native evidence separated.
- [x] Available raw reproducible artifacts, limitations and non-adoption decision persisted.
- [ ] If adopted, source builds/CI/docs wired consistently and rollback executed.

No cell was adopted, so the last item is not applicable; production source
builds/CI remain unchanged. The plan stays active because mandatory measurement
and independent-agent acceptance are incomplete. A deterministic size rejection
does not mark the remaining checkboxes complete.

## Original untouched-runtime results and remaining blockers

- **W0 partial:** exact signed compiler bytes, immutable helper/Aro pins, actual
  VMM artifact defaults/target/CPU features, non-root KVM API/VM creation and
  profile permissions are recorded. Compiler source revision is unpublished/
  unavailable, not inferred from the release mirror. Warm unchanged A/A has
  20 runs per mode: Debug median 118.21 ms/CV 39.00%; safe 77.60 ms/CV 22.06%.
  Explicit LLVM Debug A/A median 77.85 ms/CV 52.50%. Ten cold/incremental/runtime
  control pairs and a demonstrably quiet physical-host window are absent.
  Frozen gates disallow adoption; no retrospective noise relaxation occurred.
- **W1 implemented opt-ins/support:** all VMM artifacts and agent executable/
  POSIX tests receive nullable-default or explicit codegen/linker settings.
  Native/native, LLVM/native, LLVM/LLD and auto/auto pass in both VMM modes.
  Native/LLD is genuinely unsupported with the exact diagnostic
  `self-hosted backends do not support linking with LLD`. Initial kernel-path/
  configurer mistakes are retained separately, not classified as backend failures.
  Helper options remain `.{};` and their compiled caches are not cold seeds.
  Frozen codegen-affecting source patches exist but were never applied/measured.
  The recorder has ten focused passing tests, immutable command evidence, argv
  arrays, `wait4` reaped-tree CPU and nominal-20ms live-tree RSS sampling.
  RSS double-counts shared pages/misses short-lived processes; no cgroup peak
  or complete detached-worker accounting is claimed.
- **W2 core execution complete, broader lifecycle partial:** every supported
  CI-target row runs 31 unit + all 7 KVM tests in Debug and safe (eight
  invocations), zero skips/cached runtime acceptance. Native-CPU/GNU source-setup
  safe runs the same 38 tests for auto/auto, LLVM/LLD and native/native.
  Fixed-agent guest exec/exit/output/timeout/signals, files, disk fsync/read,
  spawn, PTY input/output/resize and pause/resume pass. Both cross-backend
  directions and same-backend controls pass with killed creators, independently
  reopened disk/vsock and actual restored guest state/execution in both
  CI-target modes and source-setup safe. TAP/concurrent lifecycle/full SDK
  framing are not accepted: the initial baseline PTY quoted command exposes
  pre-existing JSON-escape behavior; the harness uses a fixed quote-free command,
  not an agent/runtime fix. No-heartbeat and SDK CONNECT gaps remain unqualified.
  Guest/profile CLI commands omit `--jail`; they are unjailed compatibility
  evidence, not jailed/seccomp acceptance. Issue #1 reports a separate unchanged
  jailed baseline failure after UID1000/filter setup; #6 has not independently
  reproduced or attributed it and has not weakened isolation to obtain results.
- **W3 incomplete, size rejection established:** same-patch LLVM/LLD Debug/safe
  binaries are 7,638,200/6,827,040 bytes; native/native 22,914,417/21,779,241.
  Native grows **200.00%/219.01%**, failing the frozen 10% output-size gate.
  LLVM/native grows **81.97%/55.33%**. Source-setup safe native grows **195.95%**
  (5,973,080→17,677,529 bytes). Single discovery build durations are not controlled
  compilation-speed comparisons. No ten-pair cold/incremental benefit, phase-cost
  decomposition or valid build-regression confidence interval is claimed.
- **W4 partial, real profiles:** four genuine inherited command-mode
  software/KVM-stat and stack-record/report cells cover Debug/safe LLVM/LLD
  versus native/native, startup, the smoke operations, snapshot and new-process
  restore. Hardware PMU is unavailable; privileged trace stat runs a UID1000
  workload with initialized KVM group, not root VMM acceptance. Stack reports
  have 130/130/84/114 samples and zero lost samples. The one-window KVM exit
  counts are respectively 41,218/41,974/42,111/42,114: availability/correctness
  and exploratory profiles, not normalized repeated regression evidence.
  Boot/restore smoke times are single noisy samples, not product targets,
  p99 claims or proof of runtime improvement. Repeated workloads, sampling
  minima/tails/throughput, concurrency/idle/TAP and profiler overhead remain.
- **W5 incomplete:** the unchanged fixed x86_64 safe/static-musl agent passes
  three native POSIX tests. Candidate-agent build/runtime/CPU comparisons and
  both-target support matrix had not run in this original phase; see the later
  mechanical follow-up below. Native AArch64 execution is unavailable
  on this x86_64 host; a cross-build cannot close that specific cell.
- **W6 non-adoption:** VMM native/native and LLVM/native fail the immutable size
  budget against explicit LLVM/LLD, regardless of apparent single-build speed.
  Full statistical qualification is also incomplete. No performance-increasing
  PR, default/setup/CI adoption, merge or auto-merge is authorized.

### Shared baseline follow-up

- Exact cumulative common runtime/regression files from `5ee81b1` implement
  parent-authorized prerequisite commits `f2f9ab4` + `5ee81b1`.
  `tools/perf/blk-io.py` is the unchanged `7a71334` diagnostic dependency.
  All five selected files are byte-verified against upstream commits; no peer
  performance backend, issue-specific CI/docs or overlapping fixture options
  were imported. Original L0 binaries and logs remain separately retained.
- Repaired CI Debug/safe and native-CPU/GNU safe LLVM/LLD/native/native each
  actually pass **32 unit + all 7 KVM tests** (six invocations). Explicit forced
  units/integration side effects retain zero skips/cached runtime acceptance.
  The original 31-test inventory/results above are historical, not the new
  repaired-baseline inventory.
- Repaired native executable growth is **+270.26% Debug, +217.85% safe,
  +194.00% native-CPU/GNU safe**, against same-repaired-source LLVM/LLD.
  The unchanged 10% size budget still rejects adoption. Support durations
  include helpers/tests/cache effects, not qualifying build comparisons.
- The opt-in guest harness adds actual enforced `--jailed` execution, verifies
  UID/GID1000, CapEff0, NoNewPrivs1 and Seccomp2, and checks recorded owned task
  IDs disappear on teardown. It retains snapshot/disk evidence before deleting
  exact owned sockets/copied files/device nodes. Twelve focused Python tests
  pass, including wrong-credential/filter rejection and setup-failure cleanup.
- The earlier unjailed profiles remain unjailed. Shared jail repair does not
  qualify their performance, hidden-PMU, worker-CPU, tail or lifecycle gaps.
  The parent-provided **15.961/16 busy-core** control (zero iowait/steal) confirms
  why a fresh, quiet post-provisioning window and renewed unchanged A/A are
  still mandatory. Fleet flock is not an unrelated-load/host-idle guarantee;
  no unrelated process metadata/stacks are published or resources modified.
- The agent now has `test-build` for same-option POSIX-artifact cross-build
  discovery without execution. Mechanical support probes do not complete W5
  repeated build/guest-CPU/performance acceptance; native AArch64 hardware
  remains a separate required gap.
- Enforced CI-target snapshots pass all four directions in both modes:
  **eight** full guest/PTY/disk/lifecycle/new-process restore controls, with
  non-root/filter and task-teardown metadata. Common prerequisite tests pass
  **3/3 per CI backend/mode**.
- Those retained controls still use `5ee81b1` and report supplementary Groups0.
  The later peer-reported canonical correction
  `ced7ed72b5b2f80286e37ba8c9d5eada0cb90236` clears groups before the UID/GID
  drop; #6 had not integrated or executed it in that historical phase. The
  separately retained post-cleanup restart above refreshes this prerequisite.
  Parent integration must apply
  the same canonical correction to both arms and refresh identities/tests.
  Old counts remain protocol/snapshot evidence, not cleared-group production
  isolation; collector confinement `e1d3be0` is also not retroactive acceptance.
- GNU safe is **not** enforced-jail accepted. Both same-backend controls time
  out before the guest channel; common prerequisite tests pass **2/3 each**,
  with the guest-boot test reporting actual **SIGSYS (-31)**. Scoped owned-child
  ptrace identifies LLVM's last syscall stop as **28**, including 4096-byte/
  advice102 arguments, followed by exit159. Native's fatal syscall is not
  separately attributed. GNU cross-backend jailed restore remains blocked;
  no filter allowance/tunable/ABI/CPU fallback was introduced. An initial
  setpriv-based syscall profile loses VMM coverage across sudo bootstrap and
  is not accepted; direct-root perf captures 188 owned VMM events plus SIGSYS.
- Separate no-heartbeat safe controls initially respond **2/3 LLVM, 3/3
  native**. After five seconds, **0/2 and 0/3** execs complete within two seconds
  while the API remains Running; one LLVM trial already fails initial control.
  The five connected cases fail the raw SDK base-socket prerequisite with
  ENOENT. These are observed baseline gaps, not idle CPU/tail/performance or
  full installed-SDK acceptance.
- Independent safe agent support now covers all five pairs on both documented
  static-musl targets. All four supported x86_64 pairs force **3 POSIX tests**
  and pass four fixed-VMM enforced-jail guest/new-process restore controls.
  Non-agent cpio contents/metadata, VMM, kernel, disk and 10 ms heartbeat remain
  fixed. AArch64 auto/auto, LLVM/LLD and LLVM/native compile executable+POSIX
  artifacts only; no matching-native-hardware run is claimed.
- Agent native/LLD is explicitly unsupported on both targets. Native/native
  AArch64 instead **fails**, both compiler artifacts killed with SIGKILL;
  runner timeout false, 163.13 s, sampled tree RSS 32,610,631,680 B. No OOM attribution,
  backend-unsupported label, exact-unique-memory claim or weakened retry is
  made. Native x86_64 agent size grows **442.64%**, LLVM/native **51.62%**;
  AArch64 LLVM/native **48.18%**. These all fail the original 10% size budget,
  independently of VMM non-adoption. W5 repeated build/runtime/guest CPU and
  native AArch64 acceptance remain incomplete.

Repaired evidence adds `shared-jail-source.json`, `repaired-support`,
`repaired-source-setup`, `repaired-jail-tests`, `repaired-source-jail-tests`,
`repaired-jailed-snapshot-v2`, `repaired-jailed-gnu-v3` and
`runner-validation-repaired`. A redundant retention wrapper failed because
the recorder had already created its output directory; its failed downstream
GNU paths remain harness failures, not unsupported backends. The valid GNU
control attempts use the recorder's already-retained `repaired-source-setup`
binaries and fail as documented above. `agent-support`, `agent-guest`,
`repaired-identities`, `noheartbeat-diagnostic` and the scoped GNU perf/ptrace
diagnostics are retained independently; no negative rows are called passing.

Private evidence is retained at
`/d/hearth/.perf/worktrees/zig-native/.perf-zig-native/`, including manifests,
frozen gates, full argv/logs/metrics, builtin/cache associations, binary/fixture
hashes, actual snapshots and `perf.data`/stack reports. Initial invalid support
attempts and failed baseline PTY evidence remain separate. No downloads are
included in build-benefit results, and no historical #5 profile is reused as
native runtime evidence. See the spec's result table for reproducible locations.
