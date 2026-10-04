# Product Spec: Native Zig Codegen and Linker Experiment

**Status**: Opt-in support/correctness verified; native adoption rejected by size gate; full performance qualification incomplete

**Date**: 2026-10-04

**Issue**: [#6](https://github.com/cataggar/hearth/issues/6)

**Plan**: [Native Zig experiment](../exec-plans/active/perf-zig-native.md)

This is an experiment specification, not a benchmark result
or decision to change defaults. The compiler migration in
[#5](https://github.com/cataggar/hearth/pull/5) is complete.

## Goal and boundaries

Determine whether native Zig code generation and linking materially improve
build cost while preserving correctness and acceptable runtime behavior.
Compare explicit LLVM/LLD with explicit native/native; supported mixed cases
isolate the two effects. A negative or target-/mode-specific result is useful.
Faster compilation alone is not evidence of faster sandbox execution.

Use the same exact compiler binary, Hearth revision and experiment patch,
resolved target/CPU/features/ABI, optimization, headers/libc, and immutable
translate-c/Aro pins on both sides. Do not combine this with runtime experiments
[#1](https://github.com/cataggar/hearth/issues/1),
[#2](https://github.com/cataggar/hearth/issues/2), or
[#3](https://github.com/cataggar/hearth/issues/3). No snapshot-format, isolation,
device-algorithm, protocol, optimization-level, or architecture changes belong
here. Do not disable safety checks or remove CPU features to make a backend work.

[Core beliefs](../design-docs/core-beliefs.md) and
[architecture](../../ARCHITECTURE.md) remain the contract. Boot under 150 ms,
restore under 50 ms, and exec-to-first-byte under 10 ms are product targets,
not results established by this experiment or its heartbeat fixture.

## Source-backed starting point

Planning inspected Hearth revision `b07f73b26b8ae876928d9c515b94bba1e9945870`.
Implementation must choose and freeze its own revision, excluding #1/#2/#3.

| Area | Current definition and consequence |
|------|------------------------------------|
| [Flint build](../../vmm/build.zig) | Uses `standardTargetOptions` and `standardOptimizeOption`; links libc and target-aware translated `kvm_abi`. `exe`, unit tests, and integration tests do not set `use_llvm` or `use_lld`. |
| VMM optimization | Normal `zig build` defaults to `.debug` without a release request. Current compiler CLI spellings are `-Doptimize=debug` and `-Doptimize=safe`; `safe` is the ReleaseSafe comparison, not `ReleaseFast`. |
| [Agent build](../../agent/build.zig) | Defaults to `.safe` and x86_64 Linux musl; Linux target forms with omitted ABI are normalized to musl and linked statically. Explicit GNU targets retain the glibc >= 2.34 default needed for `openpty`. Executable and POSIX tests leave backend/linker unset. |
| [Source builds](../../src/cli/zig.ts) | Checks exactly `0.17.0`, then runs `zig build -Doptimize=safe`; no backend flags. [Setup](../../src/cli/setup.ts) copies default `zig-out/bin` outputs; agent setup tries a prebuilt download before this fallback. |
| [CI](../../.github/workflows/ci.yml) | Flint x86_64 Linux debug/safe builds and unit tests; both documented agent targets built safe; x86_64 agent POSIX tests; separate non-root KVM integration and required-result gate. Signed compiler installation must remain intact. |
| Test wiring | `test`, `integration-test-build`, and `integration-test` are real VMM steps. Integration execution has `has_side_effects = true`, depends on installation, and currently includes seven cases, five requiring real guest boot/KVM. Unit-run cache acceptance must not replace execution. |
| [Integration fixture](../../vmm/src/integration_tests.zig) | Hardcodes `zig-out/bin/flint`, `../../zig-out/bin/flint` from its project-relative fixture, and `/tmp/vmlinuz-minimal`; requires static BusyBox, `bsdcpio`, and gzip. A custom install prefix alone would test the wrong binary. |

**Verified default uncertainty:** the repository requests compiler defaults,
not LLVM/LLD explicitly. The installed compiler identified itself as `0.17.0`
during planning; no artifact was built to establish its resolved backend/linker.
Do not label current debug and safe artifacts as the same backend. Discover and
record actual choices for each executable, test artifact, target, and mode before
measuring; configuration fields and absence of an external linker process are
not sufficient proof of a resolved linker.

Both [package manifests](../../vmm/build.zig.zon) and
[agent manifest](../../agent/build.zig.zon) require Zig `0.17.0` and pin:

- translate-c `62d06a5d3e93c82727544e8113e4762a315ca0ed`,
  `translate_c-2.0.0-Q_BUWlpOBwBWvgGBM20tJq-GXgPio3v3UD39rXEn70KN`.
- Its [locked Aro dependency](https://github.com/cataggar/translate-c/blob/62d06a5d3e93c82727544e8113e4762a315ca0ed/build.zig.zon):
  `d0c8c4d9c55daa7ef6e40cf0f630a5b5e900989b`,
  `aro-0.0.0-JSD1QtuBNwCASyBtNF3pqTl_W3oAJQGEVyFAtrBSE_Pa`.

The installed Zig 0.17 `Build.Step.Compile` supports nullable `use_llvm` and
`use_lld`, serializes them per artifact, and `Maker/Step/Compile.zig` emits
`-fllvm`/`-fno-llvm` and `-flld`/`-fno-lld`. These are not a repository-wide
`zig build -Dllvm` switch. The
[translate-c build](https://github.com/cataggar/translate-c/blob/62d06a5d3e93c82727544e8113e4762a315ca0ed/build.zig)
has its own `llvm` option controlling its helper executable; Hearth currently
supplies an empty dependency-options object. Translator target/optimization
arguments affect translated output, not necessarily helper compilation.
Keep build configurer/helper settings identical, include their cost, and
distinguish them from measured executable codegen. Do not change dependency pins.

## Experiment matrix and opt-in behavior

Run each row for VMM **x86_64 Linux debug and safe**. Freeze the resolved ABI,
CPU model/features, OS range, libc and linker inputs from current builds; record
both the documented `x86_64-linux` query and its resolved target. A separate
source-setup/native-target check must preserve its actual CPU/features rather
than silently substituting the CI target.

| Configuration | `use_llvm` | `use_lld` | Purpose / support status |
|---------------|------------|-----------|--------------------------|
| Current defaults | unset | unset | Required discovery/control; actual selection unverified. |
| LLVM/LLD | `true` | `true` | Explicit reference; verify each target/mode/artifact, not inferred from old CI. |
| Native/native | `false` | `false` | Requested experiment; compilation, libc linking and runtime support unverified. |
| LLVM/native | `true` | `false` | Linker isolation only where the exact compiler supports it. |
| Native/LLD | `false` | `true` | Codegen isolation only where the exact compiler supports it. |

For every cell record requested and resolved settings, executable and test
support, diagnostic/exit status, and one of: verified build, verified native
execution, unsupported, failed, or blocked by a named prerequisite. Do not
silently fall back. If mixed cases are rejected, the two effects cannot be
separately attributed. A default row that already selects native/native is not
an independent backend transition.

Initially freeze the guest-agent binary, rootfs/initrd and guest kernel byte for
byte across VMM variants. Use a working current agent if available; any legacy
agent needed for the historical fixture is a separately labeled fixture, not a
compiler migration to repeat.

After the VMM comparison, evaluate the agent independently with a fixed VMM:

- Documented `x86_64-linux` and `aarch64-linux` forms, resolved respectively to
  static musl targets. Required safe matrix above; debug may be a separately
  labeled diagnostic matrix. Unsupported codegen/linker/optimization/target
  combinations are explicit outcomes.
- Execute x86_64 unit and guest workloads on matching native hardware. AArch64
  cross-building, ELF inspection, or emulation is not native execution; obtain
  matching hardware for a runtime claim, otherwise report that acceptance gap.
- Preserve translated libc, PTY, signal, C ABI and static linkage. Explicit GNU
  behavior must remain unchanged even though GNU-agent benchmarking is not the
  primary matrix.

Opt-in build options are `-Dvmm-codegen=auto|llvm|native`
and `-Dvmm-linker=auto|lld|native`, with analogous `-Dagent-*` options. `auto`
leaves the fields unset and remains default. Apply each pair to the executable,
unit and integration compile artifacts, not just the installed binary. Provide
a diagnostic manifest and an opt-in forced-test-execution mechanism; retain
integration side effects. Neither source setup nor release/CI defaults change
during measurement. Keep helper/compiler-driver codegen fixed, not implicitly
propagated through these options.

`-Dperf-force-test-run=true` bypasses unit-run cache acceptance for both
packages. Integration runs retain their unconditional side effects.
`-Dperf-test-kernel=.perf-zig-native/bzImage` selects a kernel relative to
`vmm/`; absolute paths and `..` components are rejected. The build resolves
the override before integration fixtures change the child's working directory.
Without the override the historical integration-kernel default is retained.
Installed binary paths and install layout are unchanged.

The initial runner implements `run` and `summarize`, not the full proposed
W3/W4 build/runtime interfaces. It uses exact argument arrays, private
worktree-relative caches/logs and the fleet lock, and refuses to overwrite
evidence. `wait4` accounts for the command and its reaped descendants; sampled
live-tree RSS is not `/usr/bin/time` maximum RSS or cgroup `memory.peak`.
Detached/unreaped helpers and processes shorter than the sampling interval are
explicit accounting limitations. Full workload/tail/profile acceptance is
required before any performance adoption.

## Implementation evidence and current decision

The isolated implementation at `b06ec0a` on
`copilot/perf-zig-native-20261004` excludes #1/#2/#3. It preserves the exact
signed Zig binary, translation pins, optimization/safety, target queries and
helper options. Its compiler SHA-256 is
`7c61539af19fa4082c94848f1c2b57b89e76dc6cfd5bd4c57764c3caf8f82272`.
The release mirror identifies tooling, not a published compiler-source revision;
that revision remains unavailable. No source-setup, agent fallback, CI or
production-default changes were made.

Observed VMM `x86_64-linux` resolves to baseline `x86_64`, **static musl**.
Generated builtin files associated with each executable/unit/integration cache
manifest establish that unset Debug selects `stage2_x86_64`, while unset safe
selects `stage2_llvm`. Exact verbose link invocations establish native `zig ld`
and `ld.lld`, respectively. Unset Debug is therefore not a new native transition.
Configurer/translate-c settings stay unset and must not be described as all-native.

| VMM artifact pair | Debug executable bytes | Safe executable bytes | Actual execution |
|-------------------|-----------------------:|----------------------:|------------------|
| auto/auto | 27,932,017 | 6,827,040 | 31 unit + all 7 KVM cases per mode |
| LLVM/LLD | 7,638,200 | 6,827,040 | 31 unit + all 7 KVM cases per mode |
| native/native | 22,914,417 | 21,779,241 | 31 unit + all 7 KVM cases per mode |
| LLVM/native | 13,899,030 | 10,604,102 | 31 unit + all 7 KVM cases per mode |
| native/LLD | no artifact | no artifact | Unsupported: `self-hosted backends do not support linking with LLD` |

Every supported row executes tests forcibly, without skips or cached runtime
acceptance. Native safe is supported; a Debug-only claim is unnecessary and
would be misleading. The actual source-setup query (no target/CPU override,
native CPU/GNU, safe) also passes 31 unit + all 7 KVM cases for auto/auto,
LLVM/LLD and native/native. Its LLVM/LLD and native/native executables are
5,973,080 and 17,677,529 bytes, respectively.

Native/native fails the prospectively frozen 10% output-size regression gate:
**+200.00% Debug and +219.01% safe** versus explicit LLVM/LLD; source-setup safe
is **+195.95%**. LLVM/native also fails, at **+81.97%/+55.33%**. These are
retained artifact-size observations, not repeated build-speed results.
No cell is authorized for default adoption or a performance-increasing PR.

Non-root guest acceptance uses a fixed current agent, one vCPU/128 MiB,
64 MiB ext4 disk and the separate 10 ms-heartbeat fixture. LLVM→LLVM,
LLVM→native, native→LLVM and native→native snapshots pass in both CI-target
modes and source-setup safe. Each creator is terminated; a new process reopens
disk/vsock resources and executes commands and reads preserved guest/disk state.
Exec exit/output/timeout/signals, files, block write/fsync/read, spawn, PTY
input/output/resize and repeated pause/resume are checked. This is correctness
evidence, not latency/tail qualification; TAP/concurrent lifecycle remain absent.
These CLI guest/profile invocations do **not** supply `--jail`: they establish
unjailed VMM compatibility only, not jailed/seccomp sandbox acceptance.
The issue #1 peer separately reports an unchanged jailed baseline exiting on
the first machine-config request after UID1000/seccomp setup; #6 has not
independently reproduced or attributed that failure. No filter bypass or
isolation change is authorized by the unjailed results.
The baseline agent mishandles JSON-escaped shell quotes: an initial PTY command
printed `input:"hello"` instead of `input:hello`. Its failing evidence is retained;
the frozen acceptance command avoids embedded double quotes without changing
agent code. This does not establish general JSON-string/SDK acceptance.

On the nested Azure D16ds_v5 host, software perf and privileged KVM trace events
work. Four genuine command-mode stat/stack-record/report runs cover both modes
and LLVM/LLD versus native/native, including fresh boot, exec/PTY/files/disk,
snapshot, creator teardown and independent restore. Profiling uses inheritance,
not attachment to one surviving PID; privileged stat drops the workload to UID
1000 with its KVM group. Stack reports contain VMM symbols and zero lost samples.
Hardware cycles/instructions are unavailable; guest PMU counters are not claimed.
These single profiling windows include Python/credential-helper CPU and are
**not** a repeated runtime-regression result or agent-exclusive CPU measurement.

Unchanged warm A/A controls (20 observations per mode, ten pairs) have Debug
median 118.21 ms/CV 39.00% and safe median 77.60 ms/CV 22.06%.
No cold/incremental or runtime-tail baseline was established. Gates remain
invalid for positive adoption, and no tolerances were relaxed after candidates.
Single support-build durations include helper/test/cache effects and must not
be published as qualifying compilation speedups.

Private, ignored raw evidence remains under the implementation worktree's
`.perf-zig-native/evidence/`: `aa-bounded`, `support-v2`, `kvm`,
`artifact-identities`, `source-setup`, `cross-snapshot`, `source-snapshot`,
`profiles`, `prerequisites` and `runner-validation-v2`. Metrics retain exact argv,
cache paths, CPU/RSS-accounting limitations and binary hashes. Initial harness
failures are separate from genuine unsupported-backend diagnostics.
The active plan retains incomplete W0/W3/W4/W5 items: a quiet/noise-qualified
window, ten-pair cold/warm/codegen-affecting incremental comparisons, full
runtime sampling/concurrency/idle/TAP, no-heartbeat/SDK gap reproduction and
the independent agent matrix. Native AArch64 execution is specifically
unavailable on this x86_64 host; neither a cross-build nor missing execution is
a pass. Negative size evidence does not silently complete these obligations.

## Build measurement contract

1. Prefetch the identical pinned dependency tree outside timed regions; retain
   download timings separately. Give every target/mode/variant/repetition
   independent local and global artifact caches seeded with the same
   dependency-only contents. Do not seed a cold run with a compiled configurer,
   translation helper, libc or linker output.
2. Measure dependency-prefetched **cold compilation**, unchanged **warm no-op
   build**, and **incremental build** separately. Freeze filesystem/page-cache
   conditions; cold Zig caches are not automatically cold OS caches. No global
   cache flush on a shared host. Record the compiler's incremental-mode setting;
   a warmed-cache source rebuild is not necessarily in-process incremental
   codegen. Keep that setting identical, with any unsupported mode explicit.
3. Freeze one representative, codegen-affecting source patch per component
   before comparing variants. Apply exactly the same patch/parent hash to each
   warmed tree, not a timestamp touch or comment-only edit; restore pristine
   sources before runtime/correctness acceptance. Record patch and binary hashes.
4. Measure installed executable builds first and native test-artifact
   compilation separately, without timing test execution as compilation.
   Repeat each condition at least ten times per variant in counterbalanced
   order, at fixed parallelism and affinity on an otherwise quiet host.
5. Record wall time, aggregate user/system CPU for the whole build process tree,
   peak simultaneous process-tree RSS, and output size/ELF sections. Include
   C translation, configurer, libc/toolchain helpers and linking, including
   in-process work. Retain subprocess timelines and sampling definitions.
   `/usr/bin/time -v` alone is not aggregate process-tree RSS.
6. Use dedicated process/cgroup accounting for total CPU and sample the live
   process-tree RSS with a disclosed interval/missed-process limitation;
   cgroup `memory.peak` is supporting data, not falsely labeled RSS. Report
   per-stage attribution where observable, plus median, mean, standard
   deviation, range/CV and confidence intervals. Keep outliers with reasons.

## Runtime measurement contract

Nested Azure KVM is mandatory, with fixed host/kernel/SKU, target and fixtures.
Record host and guest kernels, microcode/CPU/features, vCPU/RAM, all-thread
affinity, storage and TAP topology, queue/driver state, disk/cache/reset policy,
warmups, counters, workload seeds and concurrency. Reserve an exclusive window:
no compilation, agent/backend experiments, or #1/#2/#3 benchmark runs alongside.

Measure fresh boot to actual readiness, snapshot creation, restoration into a
new process to successful guest execution, exec submit-to-first-byte and full
completion, PTY input/output/resize, file operations, representative block
read/write/fsync, supported guest-initiated vsock and TAP/network traffic,
concurrent sandboxes, and idle. Define completed operations and byte counts;
report throughput, p50/p95/p99, total CPU and KVM exits per completed operation.

Proposed minimums: 30 independent boots and snapshot/restore pairs per variant;
ten independent sessions with at least 1,000 exec/PTY operations each and at
least 100 block/network operations each; concurrency 1/2/4/8 where the reserved
host fits; ten 60-second idle windows. Use session-level uncertainty rather
than treating correlated requests as independent boots. Small boot/restore
datasets get p99 labeled descriptive/underpowered; increase samples before
tail-based adoption. Repeat paired baseline A/A controls and retain all samples.

Use actual host `perf stat`, `perf record` with call stacks, and
`perf report --stdio`. Enumerate every VMM thread/process and affected backend
helper; cover process creation/restore rather than attaching only after boot.
Normalize counters by work completed inside the exact capture interval.
Collect unprofiled latency runs and separately repeated instrumented runs so
profiling overhead cannot masquerade as backend latency.

Validate hardware events before requesting them. If Azure hides host PMU
cycles/instructions, use task-clock, context switches, CPU migrations, page
faults and available `kvm:kvm_entry`/`kvm:kvm_exit` tracepoints; retain unavailable
event errors. The guest PMU is hidden/not assumed usable. Separate agent guest
CPU accounting from host VMM/guest-execution CPU; use guest process accounting
or supported software profiling rather than inventing guest hardware counters.
Preserve raw counters, `perf.data`, stack reports, lost-sample/event-coverage
diagnostics, operation counts and exact command lines.

### Fixture and baseline limitations

The [completed migration plan](../exec-plans/completed/zig-017-ci.md) and
[published recipe](https://github.com/cataggar/hearth/pull/5#issuecomment-5973822154)
are prior art, not #6 measurements. That minimal fixture uses a **10 ms serial
heartbeat** to compensate for the pre-existing idle-vsock RX/userspace-exit
dependency. Keep it identical and disclosed in comparative runs. Run a separate
no-heartbeat diagnostic; a timeout is a baseline limitation, not native success.
Heartbeat idle/tail figures are not production latency or true quiescent CPU.

The unchanged Flint backend lacks a host-initiated vsock `CONNECT` listener.
SDK forwarding/tar-stream paths, installed Docker/Ubuntu setup, and native
AArch64 execution have historical acceptance gaps. Recheck and expose each
baseline gap separately; unavailable workloads are neither passing tests nor
production-performance evidence. Do not repair those runtime gaps in this
experiment or skip supported coverage to obtain a green result.

The prior runner uses host temporary directories and a fixed CPU/kernel path,
and omits parts of this matrix. It must be adapted before reuse: explicit
project-relative fixtures/socket paths, frozen allowed affinity, kernel path,
restore/cross-backend tests, richer workloads and capture boundaries. Do not
execute the historical recipe verbatim.

## Correctness and compatibility gates

- Execute real native-variant VMM unit tests and **all** integration cases in
  debug and safe, with no skips or cached runtime acceptance. Capture test
  executable/backend identity, count, summary, non-root KVM access and stderr.
- Exercise API configuration/status/errors, fresh boot/readiness, protocol
  framing/reconnection, command output/exit/timeout/signals, PTY/resize, file
  bytes, block/network I/O, pause/resume, graceful stop/kill/repeated teardown
  and concurrent lifecycle. Validate expected contents, not just elapsed time.
- Create snapshots with LLVM/LLD, restore with native/native, and reverse the
  direction. Stop the creator, supply identical disk/net/vsock backends, resume
  the restored guest and verify actual exec, file/state continuity and I/O.
  Include same-backend controls and both supported VMM modes; device-format
  unit round trips or a restored status endpoint alone are insufficient.
- In the separate agent phase, execute POSIX fork/exec, `openpty`/ioctl and timer
  tests for each supported native variant and validate guest behavior.
- Preserve bounds/safe checks, syscall/libc ABI, target-aware translations,
  snapshot formats, isolation and non-root KVM. An unsupported primary native
  cell blocks adoption for that cell; document it rather than change semantics.

## Baseline gates, decision and rollback

Freeze a baseline-derived numerical gate file **before examining candidate
results or choosing defaults**. These are proposed starting thresholds, not
measured noise or accepted criteria:

| Dimension | Proposed gate against explicit LLVM/LLD |
|-----------|----------------------------------------|
| Build benefit | At least 15% lower median cold wall time and 10% lower median incremental wall time in the intended adopted mode; confidence interval excludes no benefit. |
| Other build costs | No >5% warm-build wall regression; no >10% total CPU, peak tree RSS or output-size regression. Near-zero warm timings require a predeclared absolute resolution floor. |
| Runtime | No >5% p50 latency or throughput regression; no >10% p95/p99 latency regression; no >5% CPU/operation or exits/operation regression for supported cases. |
| Idle | No increase exceeding the larger of 5% baseline CPU and 0.01 core per sandbox; heartbeat and true-idle diagnostics remain separate. |
| Correctness | Zero introduced failures/skips; actual bidirectional cross-backend restore and required native execution. |

Use A/A baseline variance and confidence intervals to validate these gates;
establish absolute floors for near-zero metrics and sufficient tail samples.
If noise cannot resolve a proposed tolerance, stabilize the host or collect
more samples. Any justified noise adjustment must be documented and frozen
before candidate capture, never relaxed after a bad result. Compare also with
actual current defaults so an adoption decision cannot hide regressions against
today's backend. A statistically unresolved result is inconclusive, not a win.

Record keep/reject/inconclusive/unsupported per target/mode, with raw artifacts,
risks and tradeoffs. Mixed-only adoption requires its own correctness/runtime
evidence. Opt-in remains default policy until all relevant gates pass.

If adopted, consistently wire VMM/agent definitions, native test artifacts,
TypeScript source-build setup and fallback, target/optimization CI coverage and
docs. Preserve signed Zig installation, required-result rejection of skipped
jobs, and `sg kvm`/non-root execution. Agent adoption requires separate evidence;
a VMM win does not authorize it. Rollback restores artifact options/defaults to
their previous values, rebuilds known-good binaries with the unchanged signed
compiler/pins, and verifies restore/guest execution against retained snapshots.
No snapshot conversion, user data change or isolation relaxation is allowed.
