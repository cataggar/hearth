# Product Spec: Native Zig Codegen and Linker Experiment

**Status**: Opt-in support/correctness verified; native adoption rejected by size gate; full performance qualification incomplete

**Date**: 2026-10-04

**Issue**: [#6](https://github.com/cataggar/hearth/issues/6)

**Plan**: [Native Zig experiment](../exec-plans/active/perf-zig-native.md)

## Post-orphan-cleanup restart

The parent subsequently stopped only user-approved, revalidated pre-fleet orphan
busy-loop shells. Old host-saturation and timing observations are historical;
cleanup is not itself a quiet-window result or performance qualification.
Resume with canonical `ced7ed7` supplementary-group clearing and `e1d3be0`
collector confinement, identical across reference/candidate arms. The guest
verifier must reject inherited supplementary groups. Renew identities,
correctness and unchanged A/A before considering gains; retain the numerical
gates unchanged and do not pool old/new samples.

Fresh measurements must freeze current CPU sibling topology rather than old
numbering assumptions, monitor whole-host controls and artifact capacity, and
track/reap only owned fixture/helper children. No runtime prototype from peers
or source-default change is authorized by removing unrelated contention.

The restart copies `jail.zig`/the deterministic inherited-Group0 regression
exactly from `ced7ed7`, and the collector plus nine focused tests exactly from
`e1d3be0`. Fresh explicit LLVM/LLD and native/native Debug/safe cells execute
**32 unit + all 7 KVM** tests and **3 common-jail regressions each**, without
skips/cached execution. Unset Debug/safe also execute 32+7 after the build-only
unit step is added. All inspected owned VMM task credentials report empty
Groups, UID/GID1000, CapEff0, NoNewPrivs1 and Seccomp2; the verifier rejects
Group0 even if other isolation fields are correct.

The first fresh locked five-second no-VM control observes **1.9279 busy cores
of16 (12.05%)**, no steal and 0.02 seconds iowait. It is not a demonstrated quiet
window. Current topology is CPU pairs0-1,2-3,…14-15; CPU8/client1 do not share
SMT, contrary to an older numbering assumption. The owned `kvm-nx-lpage-re`
descriptor is observed with the VMM's Tgid and Kthread0, not inferred to be an
untracked process or necessarily userspace execution. Asynchronous disk/network
kernel CPU remains separately unquantified.

Fresh binary sizes still reject adoption: Debug LLVM7,670,088/native24,155,761
(+214.93%); safe LLVM6,855,240/native24,110,761 (+251.71%). These are correctness-build artifacts,
not ten-pair speed measurements. Own focused recording/guard/archive tests now
pass21/21; the common protocol/cache suite passes9/9. Invalid unittest discovery
(zero tests) and an incorrect non-root perf prefix are retained as harness
failures, not compiler/counter unsupported outcomes.

### Fresh measurement milestones and exclusions

Debug unchanged A/A completes ten counterbalanced pairs (20 observations per
condition), including genuinely artifact-cold configurer/translation/helper
work with only immutable package sources prefetched:

| Condition | Median | Mean | SD | CV |
|-----------|-------:|-----:|---:|---:|
| Cold | 114.0748s | 114.7441s | 2.9390s | 2.5613% |
| Warm no-op | 26.2708ms | 28.3056ms | 7.6866ms | 27.1557% |
| Codegen-affecting rebuild | 0.982117s | 0.981596s | 0.035112s | 3.5770% |

Paired B/A wall-delta median/SD are respectively−0.0875%/3.2260%,
−2.1182%/17.3696%, and−1.6403%/4.7131%. These are unchanged-reference noise
controls, **not** native speedups or prospectively relaxed gates. The first
cold126.228s observation remains included. Genuine ENOSPC halted after five
pairs; remaining five use exact-manifest, complete-pair/cache-SHA/source-identity
verified resume. Both recorder epochs and the interruption are retained, with
no automatic pooling qualification. Warm20ms RSS sampling sometimes misses the
entire short command; zeros do not establish its peak memory. The exact cloned
512→513MiB source patch changes emitted `.text`, unlike touch/comment edits;
original/clone source restoration is checked.

Actual inherited root software/KVM stat captures now flush after signalling
only the owned Flint process and waiting for perf. Earlier v3 guest-correct
rows with empty stat CSVs are explicitly excluded from counter coverage.
Unprofiled latency and49Hz/4KiB DWARF record/report are separate manifests;
successful nonempty files/report exit alone does not demonstrate all-task or
symbol coverage. Short restore-only windows contain one sample/no identifiable
Flint entry. A practical separate augmentation (new-process restore followed
by1000 verified guest executions) obtains identifiable Flint stacks in all
four Debug/safe×LLVM/native cells:26/25/19/28 samples, zero reported lost
samples. This longer interval is **not** isolated restore cost or repeated
profile-overhead confidence.

The installed perf prints task-clock with a blank unit field. A retained
250ms-process-CPU control reports raw270,332,649 against0.250004s process CPU;
the human report independently records270,835,528 and0.271635s user+system.
This verifies nanosecond scaling for this installation before normalization.
Host/guest hardware PMU remains unavailable; these are genuine software/KVM
counters, not invented cycles/instructions or agent-exclusive CPU.

Fresh GNU/native-CPU safe LLVM/native each execute32+7, but common enforced-jail
tests remain2/3 because guest boot exits SIGSYS; fresh GNU native binary is
15,260,974B, LLVM6,001,096B. Debug no-heartbeat controls initially connect6/6,
then all6/6 post-five-second execs time out within the two-second deadline.
Safe repeats the same result:6/6 initial connections,0/6 post-idle completions.
They are baseline failures, not successful production idle or latency samples.
Four refreshed fixed-LLVM-safe-VMM agent controls also pass actual jailed
guest/snapshot restoration with cleared supplementary groups; their old
mechanical POSIX/build rows are not relabelled fresh performance measurements.

A practical independent TAP recipe creates only an owned network namespace
and TAP, leaving host addresses/routes/NAT unchanged. All four primary cells
boot under the enforced jail and complete **100/100 ICMP packets each** with
inherited software/KVM counters. Namespace deletion and owned-node teardown
are verified. The first attempt reached guest networking but its helper failed
to remove the newly needed private `dev/net/tun` before `rmdir(dev)`;
that retained harness error is not a backend failure/pass. The exact recorded
owned node is cleaned and the corrected recipe repeated. These four basic
network controls do not constitute ten-session throughput/tail qualification,
TCP/UDP workload acceptance or complete asynchronous network CPU attribution.

Full runtime minima and safe/explicit build comparisons remain incomplete;
SDK CONNECT, repeated TAP performance, independent agent performance/native
AArch64 and complete asynchronous kernel CPU remain unqualified.

Private post-cleanup records use `evidence/postcleanup-*`; measurements,
correctness, codegen proof and exact-owned snapshot/cache archival manifests
are indexed under `evidence/postcleanup-summary/`. Snapshot compression verifies
all original bytes before deleting only owned redundant originals. Completed
own support/cache directories may likewise be byte/link-verified into private
archives outside measured regions; active measurement caches, canonical
fixtures and other tasks' resources are excluded. Shared storage failure and
4GiB build/3GiB runtime guards are not silently weakened.
After a second capacity interruption, nine completed own cache trees preserve
6,434,137,320 logical bytes in1,433,691,060 archive bytes, verified file/hardlink
contents and symlink targets before original deletion. The5,000,446,260 logical
byte difference is this task's recovery, not the whole filesystem's fluctuating
free-space delta.

### Current partial measurements and ownership hardening

Repeated exact-manifest resumptions stop at the unchanged capacity guards.
Safe unchanged A/A retains **six complete pairs/36 rows**, and the explicit
Debug LLVM/LLD versus native/native comparison retains **six pairs/36 rows**;
neither reaches the required ten pairs. Safe comparison has not started.
The complete-workload runtime attempt retains **seven passing Debug
boot/restore rows**, not complete pairs/minimum samples. v4 coverage pilots
retain42 successful guest rows (Debug none/stat/record12 each, safe none6);
safe stat/record pilots did not execute in that epoch.

| Incomplete six-pair condition | A median / CV | B median / CV |
|------------------------------|---------------|---------------|
| Safe unchanged cold | 138.6584s / 0.7818% | 139.4759s / 2.1367% |
| Safe unchanged warm | 27.1951ms / 94.4241% | 27.5564ms / 10.2499% |
| Safe unchanged rebuild | 24.8482s / 1.4469% | 24.7629s / 2.7238% |
| Debug LLVM/native cold | 119.5240s / 1.2040% | 115.4973s / 1.2604% |
| Debug LLVM/native warm | 27.0427ms / 5.3849% | 26.3733ms / 71.9047% |
| Debug LLVM/native rebuild | 4.9599s / 2.2589% | 1.0004s / 6.1134% |

These are partial diagnostics, **not compilation-benefit qualification**.
Missing paired samples, warm noise, accounting limitations and already-failing
size gates are not waived. Completed own binary retention additionally verifies
193 gzip archives against their original bytes and retains emitted `.text`
hashes:3,262,555,712 original bytes become636,865,577 archive bytes. Together
with documented snapshot/cache recovery this releases about13.246GB logical
owned storage; it does not attribute independent filesystem changes.
Frozen runtime executables, current fixtures and active caches are excluded.

The parent separately reports a fresh locked whole-host control of
**8.733/16 busy cores**. This is not this task's per-run attributable CPU, a
quiet-window certificate or retrospective attribution of recorded samples.
Old sixteen-core saturation remains historical. No unapproved workloads are
inspected, terminated or moved; no pre/post-cleanup optimization claim is made.

The recorder now walks only the launched process's descendant task `children`
links, not unrelated `/proc` process metadata. The jail verifier uses that
owned tree. Profiled Flint termination acquires a pidfd after checked
credentials and start-time revalidation, then signals the descriptor rather
than a potentially reused numeric PID. The live owned collector session group
is terminated only as a cleanup fallback; a collector that cannot flush is
reported invalid, never accepted.

The focused21-test suite passes, including unrelated-process traversal and
exited-pidfd regressions. Four actual Debug/safe×LLVM/native **API-only**
enforced-jail controls verify current-guard pidfd acquisition, nonempty inherited
software stat and complete owned teardown. They are **not guest/KVM/runtime
performance acceptance**. A stale v5 runtime manifest explicitly rejects the
changed recorder hash; that is an identity-guard diagnostic, not a backend
failure. The common-prerequisite coordinator then requests pausing CPU work
until its correctness-only bridge and independent enforced-jail fixture are
validated. The queued v6 phase is stopped **before manifest preparation or any
VM**, with an empty owned socket directory and no held fleet lock. No v6 guest
row is executed or claimed. Resumption must freeze the supplied validated
bridge/fixture and current script hashes in a new epoch, not pool the changed
recorder/RSS method into earlier measurements.

The coordinator subsequently supplies validated canonical
`7dfee42ed68fe1703744d6318f4be632113034b0`, based only on `b06ec0a`.
Own cherry-pick `327f183` adds only the standalone
`tools/perf/test_jail_baseline.py` and its contract. Existing jail/seccomp/unit
blobs already match exactly (`fcda3fbf0fbdb20285a6ebed9930456751b38ae7`,
`10d0c7bf65931d533d88caaaf5ac592a39f79333`,
`060c876e4680f15586662401dbaf8f2723229b2c`). All five canonical files match;
no compiler/device optimization is imported. Kernel5.10.245 retains the frozen
`4da53980…` SHA. Independent three-case fixture execution and renewed
forced32+7 execution are attempted for each named Debug/safe×LLVM/native ELF.
Both first phases fail actual **Err28 ENOSPC at output-directory creation,
before any compiler/test/VM**. A bounded tiny-fixture retry fails its512MiB
capacity check before launch. A third attempt observes more than1GiB before
queuing, but again fails actual Err28 at output-directory creation when the
fleet lock becomes available. **Zero new standalone or renewed forced-test
rows execute**; these are storage-launch failures, not missing jail repairs,
backend/permission failures or accepted tests.

Independent filesystem observations subsequently fluctuate from824MB to2.744GB,
524MB,794MB and1.662GB; no other owner's resource or cause is inspected or
attributed. A pre-queue capacity observation is not an artifact reservation.
All three attempts end, the owned socket directory is empty, and no canonical
fixture directory/VM/helper or held lock remains. The only remaining named
own compiler intermediates total16,666,624 allocated bytes; discarding those
cannot provide the missing multi-GiB measurement capacity. No further frozen
inputs/active caches are removed. Actual phase failures are indexed in
`postcleanup-summary/canonical-bridge-storage-attempt{1,2,3}.json`.
Resume these correctness cases with durable capacity at locked launch; the
4GiB build/3GiB runtime guards and all eligibility gates remain unchanged.
The denied-syscall/argument cases in the32-unit suite are **BPF-evaluator unit
assertions**, not real-kernel negative child executions. Actual enforced-filter
API/CLI permission, disk and all-task identity acceptance comes separately from
the three standalone cases; keep both evidence layers and counts distinct.

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
The separately authorized shared jail-correctness prerequisite is an exception
only as an identical repaired baseline for both arms. Preserve original
untouched-runtime evidence separately; do not credit that repair as a speedup.

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
The agent's `test-build` step compiles the POSIX test artifact without executing
it, allowing artifact-consistent AArch64 support discovery on an x86_64 host.
It does not satisfy matching-native-hardware execution or runtime acceptance.
The VMM's `test-build` similarly compiles unit tests; combine it with
`integration-test-build` for build-only accounting, never the executing test
steps.
`-Dperf-test-kernel=.perf-zig-native/bzImage` selects a kernel relative to
`vmm/`; absolute paths and `..` components are rejected. The build resolves
the override before integration fixtures change the child's working directory.
Without the override the historical integration-kernel default is retained.
Installed binary paths and install layout are unchanged.

The runner implements `run`, `batch`, `summarize`, manifest-driven `build` and
diagnostic `runtime`; full W4 qualification remains pending. `build` counterbalances
ten-or-more paired repetitions, begins each cell with empty local/global
artifact caches and shared prefetched immutable package sources, then measures
warm no-op and an exact source-fragment replacement. It restores each clone
even on build failure, never patches the actual worktree, forbids executing
test steps, retains per-condition binaries/ELF reports and records whole-host
CPU controls separately from attributable command CPU. Its cache-warm patched
rebuild launches a fresh compiler process, not an asserted experimental
in-process incremental compiler mode. Completed caches can be retained in
hash-verified gzip tar archives, including symlink/hardlink identity, outside
timed regions; no source inputs or another task's artifacts are removed.

`runtime` counterbalances fresh jailed boots/new-process restores, numbered
PTY ACK sessions, exec, block write/fsync/read, guest-initiated vsock ping,
no-client-traffic idle and1/2/4/8 concurrency. It verifies restored bytes and
actual guest execution, every inspected task's credentials, operation content
and teardown. Unprofiled and inherited private `perf stat`/49Hz4KiB DWARF
record/report runs are separate immutable manifests. Whole-host `/proc/stat`
controls are not attributed workload CPU; empirical p99 is not asserted
independent-tail confidence. Snapshot/disk archives are byte-verified outside
timed regions. Supported TAP/network, complete asynchronous kernel CPU, guest
agent-exclusive CPU and noise/tail qualification remain separate gates, not
implied by the diagnostic command's exit status.

Both interfaces use exact argument arrays, private
worktree-relative caches/logs and the fleet lock, and refuses to overwrite
evidence. `wait4` accounts for the command and its reaped descendants; sampled
live-tree RSS is not `/usr/bin/time` maximum RSS or cgroup `memory.peak`.
Detached/unreaped helpers and processes shorter than the sampling interval are
explicit accounting limitations. Full workload/tail/profile acceptance is
required before any performance adoption.

## Implementation evidence and current decision

The isolated implementation at `b06ec0a` on
`copilot/perf-zig-native-20261004` excludes #1/#2/#3 performance prototypes. It preserves the exact
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

### Separately repaired enforced-jail baseline

Later correctness reuses the exact shared prerequisite from
`f2f9ab4c8e7a67097f2c3f52636327e9c41d5084` and
`5ee81b163b266f9c7643fb67c88cb59fe7aa2878`. The cumulative `jail.zig`,
`seccomp.zig`, `tests.zig` and `test_jail_prerequisites.py` are byte-identical
to `5ee81b1`; the unchanged diagnostic `tools/perf/blk-io.py` dependency is
byte-identical to `7a71334d480fcdfc72172a26ee2a2998943ccd62`.
No peer device/backend optimization, CI/kernel-option wiring or issue-specific
documentation is imported.

This common repair makes private device ownership/modes independent of
`umask 077` and permits only traced, already-intended Unix-stream, current-thread
affinity, null-mask epoll and nonblocking-poll operations. Active clone/namespace
and executable-mapping restrictions remain; the ignored Linux `CLONE_DETACHED`
bit does not authorize additional active clone behavior. Regression tests still
deny AF_INET/AF_INET6, NEWUSER/NEWNS, PROT_EXEC, another PID's affinity, nonnull
epoll masks, blocking poll, eventfd and io_uring. Host device nodes, compiler
pins, guest agent, fixtures and backend algorithms are unchanged.

Both LLVM/LLD and native/native execute **32 unit + all 7 KVM tests** in CI Debug,
CI safe and native-CPU/GNU safe: six repaired invocations, without skips or
cached runtime acceptance. The original 31-test rows remain historical
untouched-runtime observations, not repaired-baseline measurements.

| Repaired pair | CI Debug bytes | CI safe bytes | Native-CPU/GNU safe bytes |
|---------------|---------------:|--------------:|-------------------------:|
| LLVM/LLD | 7,664,408 | 6,851,072 | 5,996,176 |
| native/native | 28,378,182 | 21,776,148 | 17,628,718 |
| Native size regression | **+270.26%** | **+217.85%** | **+194.00%** |

These same-repaired-source observations also fail the unchanged 10% size
budget; they are not build-speed or runtime-regression results. Earlier sizes,
warm A/A and unjailed profiles are not pooled with these post-provisioning rows.

The opt-in guest runner now accepts `--jailed`, bootstraps the jail separately
from guest acceptance, verifies the actual VMM's UID/GID1000, CapEff0,
NoNewPrivs1 and Seccomp2, and checks its recorded task IDs disappear during
teardown. All acceptance still runs as the configured non-root identity.
Private copied kernel/initrd/disk, owned device nodes and sockets are removed
after snapshots/disk state are retained. Failed fixture preparation also cleans
its owned listener/root; focused verification rejects root credentials and an
unenforced filter. Twelve runner tests pass.

All four enforced-jail snapshot directions pass in CI Debug and safe: **eight
controls**, killed creators, independently restored processes, preserved
guest/disk state and actual post-restore execution. Creator/restorer credentials,
filter state and recorded-task disappearance are retained for each control.
The common enforced-jail prerequisite suite passes **3/3 in each of those four
backend/mode cells**.

These controls use the exact `5ee81b1` prerequisite, whose retained VMM metadata
reports supplementary **Groups0** despite UID/GID1000 and CapEff0. A subsequent
peer-reported common correction,
`ced7ed72b5b2f80286e37ba8c9d5eada0cb90236`, checks `setgroups(0, NULL)` before
the UID/GID drop. It was published after this phase and has **not** been
integrated or executed by #6 **at that phase**; see the separately retained
post-cleanup restart above. The existing counts establish that older
configuration's protocol/snapshot compatibility, not cleared-group production
isolation. Parent integration must reuse the canonical correction on both arms
and renew identity/correctness evidence; no silent baseline substitution is made.
The peer's separate collector-cache/environment correction `e1d3be0` likewise
does not retroactively qualify these exploratory profiles.

The separately rebuilt native-CPU/GNU configuration is **not** jailed-guest
accepted. Both LLVM/LLD and native/native same-backend controls time out before
the guest channel is ready; their common prerequisite suites pass **2/3**,
with real guest boot failing because the VMM exits on **SIGSYS (-31)**.
An owned-child syscall tracer identifies the LLVM baseline's last syscall stop
as **28**, arguments including **4096 bytes/advice 102**, followed by exit159
(128 + SIGSYS). No syscall allowance, glibc tunable, ABI/CPU substitution or
filter bypass is used. Native's fatal syscall is not separately attributed.
The GNU bidirectional jailed snapshot cells remain blocked, not passed or
classified as unsupported codegen. Original GNU unjailed controls remain
distinct historical evidence.

The 10 ms-heartbeat fixture remains diagnostic. Enforced-jail exec/PTY/files/
disk and snapshots do not close the separately reported no-heartbeat, SDK
CONNECT, network, concurrency, tail or production-readiness gaps. New repaired
profiling/performance acceptance is not claimed; original unjailed profiles
do not become enforced-jail profiles retroactively.

A separate repaired CI-safe no-heartbeat fixture uses the unchanged original
agent. LLVM/LLD responds initially in **2/3** trials; native/native in **3/3**.
After five seconds of no-traffic VM idle, **0/2** and **0/3** execs respectively
complete within the two-second host deadline, while API state remains Running.
The remaining trial already times out on initial control. These are baseline
liveness diagnostics under contention, not idle CPU/tail samples or runtime
qualification. All five connected trials also fail the raw SDK Unix-socket
open prerequisite with **ENOENT** at the base vsock path. This does not execute
or accept the complete installed SDK CONNECT protocol.

The parent independently measured **15.961 busy cores out of 16** under the
fleet lock, with zero iowait/steal. That is a parent-provided environmental
control, not a retrospective measurement of these runs. The lock fences
cooperating experiments, not unrelated host load. A quiet reserved
post-provisioning window, renewed unchanged A/A and frozen environmental
controls remain prerequisites for positive performance qualification.
Unrelated processes and their metadata/stacks are neither altered nor
published.

Private, ignored raw evidence remains under the implementation worktree's
`.perf-zig-native/evidence/`: `aa-bounded`, `support-v2`, `kvm`,
`artifact-identities`, `source-setup`, `cross-snapshot`, `source-snapshot`,
`profiles`, `prerequisites` and `runner-validation-v2`. Metrics retain exact argv,
cache paths, CPU/RSS-accounting limitations and binary hashes. Initial harness
failures are separate from genuine unsupported-backend diagnostics.
Repaired records add `shared-jail-source.json`, `repaired-support`,
`repaired-source-setup`, `repaired-jail-tests`, `repaired-source-jail-tests`,
`repaired-jailed-snapshot-v2`, `repaired-jailed-gnu-v3` and
`runner-validation-repaired`. A redundant source-build retention wrapper
failed on an already-created evidence directory; its failed GNU follow-up
paths remain separate harness diagnostics, not unsupported compiler cells.
The initial credential-helper command-mode syscall recording contains only
owned `setpriv`/Python events, not VMM events; it is a coverage failure.
Direct-root perf bootstrapping subsequently captures 188 owned VMM events and
the fatal SIGSYS; scoped owned-child ptrace provides the denied syscall number.
Unavailable `seccomp:seccomp_filter` tracepoint diagnostics are retained.

### Independent agent mechanical support

Safe agent options are exercised independently of the VMM, including executable
and POSIX test artifacts. Unset agent defaults resolve to LLVM/LLD for both
documented targets. Retained builtin/cache associations establish baseline
`x86_64` or AArch64 `generic` CPU, static musl and safe optimization; ELF and
verbose linker records corroborate artifact identity. Helpers retain their
separate unchanged settings.

| Safe agent pair | x86_64 bytes / execution | AArch64 bytes / build-only result |
|-----------------|------------------------:|---------------------------------:|
| auto/auto | 4,624,880; 3 POSIX tests pass | 4,610,152; executable + tests compile |
| LLVM/LLD | 4,624,880; 3 POSIX tests pass | 4,610,152; executable + tests compile |
| native/native | 25,096,257; 3 POSIX tests pass | Failed: both artifact compilers killed |
| LLVM/native | 7,012,404; 3 POSIX tests pass | 6,831,109; executable + tests compile |
| native/LLD | Unsupported | Unsupported |

Native/LLD retains the exact `self-hosted backends do not support linking with
LLD` diagnostic for both targets. Native/native AArch64 instead fails with
`process terminated with signal KILL` for both compilation artifacts:
163.13 seconds, runner timeout **false**, nominal-20ms sampled peak tree RSS
32,610,631,680 bytes. This is not an attributed OOM diagnosis, a backend
unsupported diagnosis, exact unique-memory peak or native execution. No weaker
optimization/features/target or silent fallback is tried.

All four supported x86_64 agents also pass enforced-jail guest exec/PTY/files/
disk, pause/resume and new-process snapshot restoration with the **same fixed
repaired LLVM/LLD safe VMM**. Their separately frozen initrds differ only in
agent payload/size: common entry contents, permissions, ownership, inode and
cpio timestamps are verified unchanged. The same original kernel/disk and
10 ms heartbeat are used. These are four correctness controls, not repeated
agent latency/CPU measurements.

Agent native/native grows **442.64%** on x86_64, LLVM/native **51.62%**;
AArch64 LLVM/native grows **48.18%** in build-only evidence. Each exceeds the
unchanged 10% size budget. Neither component is adopted. Matching-native
AArch64 execution, independent guest-agent CPU accounting, controlled repeated
build/runtime performance and full production workloads remain unaccepted.
Raw records add `agent-support-source.json`, `agent-support`, `agent-guest`,
`repaired-identities`, `noheartbeat-diagnostic`, `repaired-gnu-direct-trace`
and `repaired-gnu-ptrace-trace`; fixture/script manifests remain private.
The active plan retains incomplete W0/W3/W4/W5 items: a quiet/noise-qualified
window, ten-pair cold/warm/codegen-affecting incremental comparisons, full
runtime sampling/concurrency/idle/TAP, no-heartbeat/SDK gap resolution and
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
