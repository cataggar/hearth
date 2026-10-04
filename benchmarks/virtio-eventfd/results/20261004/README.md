# VirtIO eventfd W0 results — 2026-10-04

**Decision: HOLD / INCONCLUSIVE / NOT PERFORMANCE-MERGE ELIGIBLE.**

Issue [#3](https://github.com/cataggar/hearth/issues/3) is **not complete**.
This is a partial baseline investigation and separately validated isolation
prerequisite, not a rejected accelerated prototype. No C00/C10/C01/C11,
eventfd registrations, readiness owners, queue decoder correction, IRQ policy
or numeric adoption gates have been implemented/ratified. Legacy remains the
only delivery path. No before/after candidate values or finite speedup exist.

Worktree: `/d/hearth/.perf/worktrees/virtio-eventfd`.
Branch: `copilot/perf-virtio-eventfd-20261004`.
Base: docs-only `b06ec0a6c19b4977bfb602c2daa1d94acf3eacf7`;
initial runtime sources match `b07f73b26b8ae876928d9c515b94bba1e9945870`.
Async block #1, vhost-net #2 and native-Zig #6 patches are excluded.

## Post-provisioning prerequisite recheck

A separate unchanged-L0 check executed at **16:34 UTC**, after the parent
verified common provisioning. Actual UID1000 KVM/IRQchip/eventfd-capability
preflight passes; current Node/npm/ip/fio/iperf3 and narrow KVM/vhost ACL
receipts are preserved. No optimized backend or new runtime is used.

* `post-noheart`: one timer-free 4 KiB request fails, zero completed round
  trips; sequence0 receives **0/4** header bytes at the one-second bound.
* `post-backpressure`: one 64 KiB×8 slow-reader burst fails, zero whole bursts;
  sequence3 again receives **36,808/65,544** response bytes, with the same
  partial hash as prior diagnostic failures.
* Aggregate `/proc/stat` is retained before, between and after these complete
  runs (including startup/warmup, **not just operation windows**). At
  CLK_TCK100 the nonidle/total tick deltas are **5,692/5,694** and
  **8,125/8,127** (approximately **99.965%/99.975% aggregate nonidle**).
  These prove substantial host contention, not backend CPU or causal
  attribution. Raw snapshots have no unrelated PID/comm/stack information.

The failures survive provisioning, but saturated-host bounded checks are not
quiet-host/A/A performance evidence. No numerical benefit/noise gate is frozen.
[Post-provision raw evidence](post-provision-blockers.tar.gz) and its checksum
are separate from the original W0 archive.

The runner now automatically records operation-window aggregate host snapshots,
a separate host-control interval, nonidle/steal controls (without guest-time
double counting), and its own hash. These changes pass **16 tooling tests**;
the two post-provision runs above predate that automatic collector and use
the explicitly documented outer snapshots. No historical field is fabricated.
The exact shared prerequisite and further actual API startup findings are
documented below. Earlier CLI-only proof is not promoted into API/lifecycle
acceptance.

## Shared prerequisite reused; actual CLI/API guest startup verified

Reused #1 commit `f2f9ab4c8e7a67097f2c3f52636327e9c41d5084` via local
`2305b11`, resolving prior jail ownership overlap and excluding unrelated
#1 result/spec/plan documents and all async backend work. Its no-follow-FD
normalization sets jail device dirs root:root0755 and nodes UID/GID0600,
with artifact umask077/host device permissions unchanged. Existing #3
supplementary-group clearing and ordinary poll7/epoll_pwait281 remain.
Only traced Unix API sendmsg46/recvmsg47 are added by that commit.

The isolated shared test initially fails import because it depends on the
absent #1 block runner. Follow-up
`013234a1eef5441deefc11bb8aa54c7e79f3429f` supplies a standalone generic
owned-process/Unix-HTTP helper instead, with PID/start-time validation before
termination/escalation and two deterministic stale-PID regressions.

Actual API configuration succeeds but `InstanceStart` initially diesSIGSYS:

1. Owned raw syscall tracing identifies204; own frozen-binary disassembly
   proves `Thread.getCpuCount` calls sched_getaffinity(PID0,size128,...).
   The follow-up permits **only PID0** queries; other-PID queries and
   affinity mutation remain denied.
2. Startup then dies on clone56. Own static `pthread_create` disassembly
   proves flags0x007d0f00, adding only musl's ignored legacy
   CLONE_DETACHED0x00400000 bit to the old0x003d0f00 thread mask. Namespace
   creation, non-Unix sockets, executable mprotect and eventfd2 remain denied.

The actual filtered fork/thread test verifies query plus thread create/join
and four continued SIGSYS denials. Intermediate two layout-test failures and
both startup failures remain raw evidence; final corrected tests pass.

Final **Safe and Debug each** execute33/33 unit tests and7/7 existing
integrations (five real guest/KVM, two CLI/error; existing heartbeat retained),
plus4/4 standalone fixture tests (two actual enforced-jail node/API cases
and two deterministic PID-generation cases). Final untraced enforced guest
boots are **4/4 pass**: CLI and API in each optimization. API boot accepts
five configuration/start exchanges and reaches the guest-initiated native
vsock connection. Its complete three-task roster (main, existing vCPU thread,
KVM helper) has all UID/GID1000, no groups/capabilities, Seccomp2/NNP1.
One additional traced Safe API boot passes. All private jails are cleaned
after owned processes join. No audit/filter bypass or root VM is used.

These are ordinary correctness prerequisites, **not C00/backend owners or
performance gains**. The frozen untouched-L0 binary/hash/failures remain
unchanged. API boot is not active-I/O pause/snapshot/error-path acceptance.

After all repairs, same-source separately labelled `repaired-safe` checks
still fail required no-heartbeat operations:

* Native4KiB echo after one-second silence: **1/1 fail**, sequence0 receives
  0/4header bytes; zero round trips.
* Native eight64KiB slow-reader burst after one-second silence: **1/1 fail**,
  sequence0 receives0/4header bytes; zero completed bursts.
* TAP idle-wake: **1/1 fail**, initial64B and eight64KiB messages validate,
  sequence16 after two-second silence receives0/4header bytes. Later bulk
  phase does not execute. All current VMM task credentials/filter are verified.
  VMM all-thread CPU0.03s/4.890601wall is only a diagnostic; host control is
  **78.09busyCPU seconds** (~15.967busy cores), idle/iowait0.12s, steal0.

Neither repaired startup nor these saturated failed workload windows provides
quiet A/A gates, a complete baseline/matrix or any accelerated candidate.
Failure timeouts are not finite latency/speedup denominators.
[Shared/repaired prerequisite raw evidence](repaired-prerequisites.tar.gz)
is separate from original L0 and includes only owned processes/scoped traces.

## Independent native TAP prerequisite (post-provisioning)

The native TCP listener reuses #3's existing numbered-payload/FNV echo
protocol, compiled with pinned Zig0.17/safe. It does not import #2's backend,
guest code, system-wide collector or private evidence. Its binary SHA-256 is
`8a292a7705bb5407f57e8ffa3e8ca3f8e9eb98d2c3365ab72b111f6b11b983ab`;
the timer-free initrd is
`eff0336837d75bb50fd6cf0b3a27b0f41e2464d47911d870d32944adcb84872d`.
The same pinned 5.10.245 kernel and BusyBox are used.

All cases run under bounded exclusive fleet phases in a private network
namespace, with owned `hef3tap0`, host192.0.2.1/30, guest192.0.2.2/30,
MTU1500, vnet header and offloads disabled. There is no uplink, NAT, host
NIC change, heartbeat, SDK CONNECT or polling guest fixture. VMMCPU8 and
clientCPU1 are separate reported physical cores. The current separately
labelled **isolation-control** binary, not frozen old L0 or C00, runs in
the enforced CLI jail. Before client admission its complete two-task roster
has UID/GID1000, empty groups, CapEff0, Seccomp2 and NoNewPrivs1.

* Native host-loopback protocol self-tests: **2/2 pass** (one initial-only,
  one including idle-wake phases); these are **not KVM/jail tests**.
* Initial-only real enforced-jail TAP prerequisite: **1/1 pass**; checked
  one64B echo and eight64KiB slow-reader messages (250ms delayed reader).
  This is one operation window, not sustained or halted-vCPU acceptance.
* Stronger real enforced-jail TAP prerequisite: **1/1 fails**. Initial64B
  echo and all eight64KiB messages (sequences8–15) validate. After two
  seconds of silence, sequence16 receives **0/4 header bytes** at the
  two-second bound. The subsequent after-silence64KiB phase never executes.
  The equivalent native host protocol passes every phase. No failed
  operation is assigned a finite latency or speedup.
* The failed KVM case records 0.03CPU seconds for all VMM tasks over its
  5.239568s operation window, but aggregate host control records
  **79.94 busyCPU seconds** (~15.257busy cores; idle/iowait3.83CPU seconds).
  The earlier initial-only case records27.53busyCPU seconds/1.727226wall
  (~15.939busy cores). These are saturation/noise controls, not eligible
  whole-window backend/kernel attribution or frozen performance baselines.
* Latest existing Python tooling suite: **16/16 pass**. TCP build:3/3 steps
  pass. Owned child/client processes are joined before the private jail
  is removed; no unrelated processes, stacks or task lists are collected.

The fixture closes a missing-prerequisite-tool gap while exposing a real
post-silence TAP servicing failure. It does not repair readiness, establish
actual halted residency, provide the full workload matrix, select an owner/
IRQ policy or make the experiment performance eligible. The original L0
failures and old archives remain unchanged.
[Owned TAP raw evidence](tap-prerequisites.tar.gz) is a separate checksummed
archive; it contains no unrelated task lists or system-wide perf data.

## Environment and controls

Actual host `vm31e`: Microsoft/Azure `Standard_D16ds_v5`, nested KVM,
Linux `6.18.31-1.3.azl4.x86_64`, Intel Xeon Platinum 8370C, 16 logical CPUs,
eight reported cores with SMT2. Runs use one vCPU, 512 MiB guest RAM, UID/GID
1000, unchanged synchronous block/userspace backends and guest features.
All builds/tests/VMs/profiles/fixture preparation hold the fleet's exclusive
`/d/hearth/.perf/fleet/host.lock`, use bounded commands and `umask 077`.
This workstream made no global device, driver, cache, NIC or security changes.
The original W0 timing series **precedes the parent's final common host
provisioning reported at 16:25 UTC**, including vhost module/device access
provisioning. They remain partial W0 diagnostics, not a frozen fully controlled
comparison. Future L0/C00/2×2 measurements must start after provisioning and
actual nonroot capability verification, retain fresh tool/library/device-state
metadata, and freeze gates before candidates. The immutable L0 binary/fixture
identity is preserved; no pre-provisioning timing is promoted into a gate.
The fleet lock serializes participating experiments, **not unrelated host
workloads**. “True idle” below means a no-traffic VM, not a fully idle host.
Whole-host `/proc/stat`/steal-time control snapshots were not collected in that
original series; its external contention is therefore unquantified. Only owned VMM-group
CPU and separately recorded client CPU are attributed. Future repeated A/A
windows must retain host controls as well, without inspecting or changing
unowned workloads. None of these diagnostics establishes whole-window kernel
CPU attribution for a future asynchronous IRQFD backend.

`/dev/kvm` is unchanged 0660 root:kvm; the account has the kvm group.
Real unprivileged preflight obtains KVM API 12, creates VM and IRQchip, and
reports IOEVENTFD, IRQFD and IRQFD_RESAMPLE capabilities supported.
Capability support is **not assignment or interrupt correctness**.

Zig 0.17.0, perf 6.18.31-1.16.azl4.x86_64, Node 22.22.0, npm 10.9.4,
fio 3.40, iproute2 6.14.0 and iperf3 3.19.1 are present. Earlier missing host
tools were subsequently provisioned by the parent; they are not claimed as
remaining blockers. No non-nested comparison is available.

Ordinary perf is restricted to userspace software events/tracefs visibility.
Scoped `sudo -n perf` successfully collects kernel/user software events,
DWARF stacks and KVM/syscall tracepoints. Hardware cycles/instructions are
unsupported even with sudo. No sysctl/tracefs permissions are widened.
Collectors/decoders use the project perf build-id directory.

Important immutable pins:

| Item | SHA-256 / resolved package hash |
|---|---|
| Guest Linux 5.10.245 bzImage | `4da539807474d189f1a15852046994e78d430a194c2e78b9255ae880069c7208` |
| Frozen untouched safe L0 Flint | `bd10cfef94ef4cf2402e485913b3f4a9ffb93f9cf80d25d0310d093b55111d23` |
| Timer-free native guest probe | `09d24f0b42ab2d9035a480591be051427a572cbcb3f03b0ac8f08932abd46baa` |
| Unchanged safe guest agent | `b2dfc29e8fafde8e7f0c88a0a624dd6400cde24e5c77ee572a4a56468329ff88` |
| Fixed safe isolation-control Flint, **not C00** | `c0c4ff843d69f2d1462435f97081f655f74b6cbf759f54bd6da94e49d1349ff8` |
| Final repaired Safe Flint, **not C00** | `d867268921392bb4a2e449398b2320d901c68b59acbc95e0176fdbb0dbaac2b2` |
| Final repaired Debug Flint, **not C00** | `5f2d0c068b4eae9d7a9b6ac006b76affe563c62c87ec4d923408c861d29f9542` |
| translate-c fork revision | `62d06a5d3e93c82727544e8113e4762a315ca0ed` |
| translate-c package | `translate_c-2.0.0-Q_BUWlpOBwBWvgGBM20tJq-GXgPio3v3UD39rXEn70KN` |
| Resolved Aro package, from generated dependency table | `aro-0.0.0-JSD1QtuBNwCASyBtNF3pqTl_W3oAJQGEVyFAtrBSE_Pa` |

Kernel/initrd/BusyBox/agent hashes, compiler SHA, expanded commands,
source/diff receipts, CPU affinity and per-operation arrays are in raw run
manifests. The old L0 executable was frozen before production jail changes.

## Required liveness and integrity findings

The native guest uses blocking guest-initiated AF_VSOCK on port 11000,
numbered 8–65,536-byte messages and independently checked FNV-1a/payload
integrity. It has no timers, heartbeat or unsupported host CONNECT dependency.
The ordinary unchanged agent uses guest-initiated port 1024.

* Native 4 KiB echo after one second of silence fails **4/4** no-heartbeat
  repetitions at the approximately one-second bound (`n0-0/1/2`,
  `nc-noheart`); zero round trips complete. Agent ping fails **1/1** (`a0-0`).
  These are failures, not finite latency observations or speedup denominators.
* With the separately labelled 10 ms serial-heartbeat fixture, checked native
  echo/exec/PTY output and a disk fsync/hash operation can complete.
  This does **not** establish halted-vCPU liveness.
* Eight concurrent-sender/250 ms slow-reader 64 KiB native messages fail
  **5/5** trials (`nbp-0/1/2`, `nbp-partial`, `nc-backpressure`).
  The corrected-affinity retry reaches sequence **3**, then receives
  **36,808 / 65,544** expected response-body bytes and times out:
  `e0e411b463fdb5dd5d8a9b63434b7672af86ba043a651fd8d375b60f576a132f`.
  Zero whole bursts pass. This proves the required backpressure liveness/
  integrity check is unsuccessful; a partial timeout alone is not proof of
  complete-message corruption. The source advertises 256 KiB receive credit
  with only a 256-byte pending host-write buffer, a correctness prerequisite
  needing explicit investigation rather than silent benchmark repair.

The source's malformed notification width/value/queue-ID gap is unchanged.
PIC routing appears as XT-PIC in the actual guest; ELCR/edge/level semantics
are not established. No compatible IRQFD policy has been selected.

## Baseline software profiles and variance

Earlier `nd-*`, `np-*`, agent/disk/idle runs pin VMM CPU8 and client CPU0,
which are reported SMT siblings. They remain raw **supplementary/confounded
diagnostics**, not promotion data. The runner now rejects this pairing.
Corrected `nc-*` runs pin VMM/all observed tasks CPU8 and client CPU1.
All following native runs use the identical 4 KiB/10 ms-heartbeat fixture.

| Unprofiled corrected-affinity repetition | Checked round trips | VMM/all-task CPU seconds | p50 / p95 / p99 ms |
|---|---:|---:|---|
| `nc-0`, 3.0094 s | 241 | 0.40 | 11.486 / 21.477 / 24.783 |
| `nc-1`, 3.0098 s | 208 | 0.40 | 11.558 / 25.302 / 72.450 |
| `nc-2`, 3.0203 s | 226 | 0.39 | 11.526 / 25.093 / 34.019 |

Between-run median sample SD **0.03609 ms**, CV **0.3132%**. Tails and
throughput vary substantially; three short diagnostics cannot freeze p99/
benefit/noise gates or supply a candidate confidence interval. CPU includes
both observed VMM-group tasks; client CPU is recorded separately. `/proc`
tick resolution is 10 ms, so short zero-CPU values do not mean free I/O.
Thread-roster changes invalidate accounting instead of dropping tasks.
The 675 passing corrected-affinity round trips pool to p50/p95/p99
**11.524 / 23.057 / 47.904 ms**; per-run CPU/op is
**1.660 / 1.923 / 1.726 ms**. No candidate contrast follows from these values.

Corrected-affinity `nc-stat`: 372,358,017 ns task-clock, 1,360 context
switches, zero migrations/faults over 3.0116 s. `nc-stacks`: **76 cpu-clock
samples, zero lost**, successful DWARF report/script. Stacks show KVM
run/exit/IRQ and polling costs; these small heartbeat-dominated profiles do
not demonstrate improvement potential or charge any future IRQFD worker.

Corrected `nc-trace`, approximately three seconds:

| Attribution | Count |
|---|---:|
| Kernel KVM entries/exits | 23,999 / 23,999 |
| Userspace returns | 11,021 = 10,125 IO + 896 MMIO |
| Observed exact four-byte notify writes | 184 = queue0 six + queue1 178 |
| Completed eligible VirtIO/GSI5 IRQ-line ioctls | 1,068 |
| Serial/GSI4 IRQ-line ioctls, **not eligible VirtIO savings** | 11,250 |

Eligible traced ioctl p50/p95/p99 approximately **2/4/5 µs**, including tracing
overhead. One ioctl pair is clipped at each collection boundary. Kernel exits
are not userspace returns; notification writes are not descriptor counts;
IRQ ioctls do not establish delivered/acknowledged interrupts.

Supplementary original true idle, heartbeat off (`ni-60`): **0.24 s
aggregate VMM CPU / 60.0001 s = 0.4000% of one core**; software task-clock
231,240,876 ns and 4,158 context switches. Only one idle window was collected:
this is not an idle-noise estimate or candidate delta guard.

Supplementary disk diagnostics (`db-v2-0/1/2`) mount a fresh ext4 clone,
write/fsync/hash 1 MiB of known zeros and unmount: **61.091 / 46.133 /
34.721 ms**; sample SD **13.2248 ms**, CV **27.9507%**.
Each is one logical operation, not 256 measured virtqueue completions.
These are not the disk workload matrix or a matched controlled comparison.
Twenty checked PTY first-byte/exit cases pass with the diagnostic heartbeat;
they do not test stdin RTT. The guest agent's independent **50 ms polling
workaround remains unchanged**.

The first stack decoder run rejected the deliberately UID-owned data when
root decoded without force. Its failure remains retained. Reprocessing the
same data with scoped `-f` succeeds in separate recovery artifacts.
The corrected-affinity collection succeeds directly; no failed run is
silently converted into a passing benchmark.

## Initial separately validated isolation prerequisite (historical)

L0 under `umask 077` makes root-owned 0700 jail directories/0600 nodes,
then gets KVM `AccessDenied` after UID drop. The surgical prerequisite assigns
private device dirs 0700 and nodes 0600 to configured UID/GID and clears
supplementary groups before privilege drop. Host nodes are unchanged.

That exposes an actual first-return SIGSYS. An owned enforced child's raw
syscall trace and frozen-binary disassembly identify syscall281
(`epoll_pwait`, used by Zig's epoll wrapper). Existing vsock source and baseline
stacks additionally use syscall7 (`poll`). Only these ordinary readiness calls
are admitted; argument-filtered clone/AF_UNIX/no-PROT_EXEC restrictions remain,
and **eventfd2 remains killed**.

After fixing, actual jailed boot reaches guest vsock connect. The complete
post-connect roster (`jail-fixed-roster`) has main `flint` and
`kvm-nx-lpage-re`, both observed **Kthread0**, all UID/GID fields1000,
empty supplementary groups, CapEff0, Seccomp2 and NoNewPrivs1.
The helper name is not used to bypass credentials or omit CPU.
Owned PID/start-time tuples are revalidated before cleanup. Every private
jail cleanup reports zero. This is boot/connect coverage, **not** eventfd,
TAP, API, active-I/O lifecycle or all failure-path isolation coverage.

## Validation actually executed

All commands below were bounded and held the exclusive host lock; builds used
`ZIG_GLOBAL_CACHE_DIR=$PWD/.perf/eventfd/cache`. No skip is a pass.

| Command, from worktree root unless noted | Actual passing count |
|---|---:|
| `python3 -m unittest discover -s benchmarks/virtio-eventfd -p 'test_*.py'` | Latest16 tooling tests |
| From `vmm/`: `zig build test -Dtarget=x86_64-linux -Doptimize=safe --summary all` | Latest33 unit tests |
| Same with `-Doptimize=debug` | Latest33 unit tests |
| From `vmm/`: `zig build integration-test -Dtarget=x86_64-linux -Doptimize=safe -Dintegration-kernel=../.perf/eventfd/fixtures/bzImage --summary all` | Seven integrations: **five real guest/KVM cases + two CLI/error cases** |
| Same with `-Doptimize=debug` | Same seven, no skips |
| `python3 -m unittest discover -s tools/perf -p test_jail_prerequisites.py -v` | Safe/Debug each4: two actual jailed node/API cases, two deterministic cleanup cases |
| `probe_jail.py --binary <final repaired Safe/Debug> [--api] ...` | Final four actual enforced CLI/API guest boot/connect checks, complete rosters |
| `zig fmt --check` on all modified Zig sources/build file | Pass |
| `probe_jail.py --binary vmm/zig-out/bin/flint --label isolation-control-fixed --out .perf/eventfd/results/jail-fixed-roster --jail .perf/eventfd/jail-fixed-roster` | One actual enforced guest boot/connect and complete task-credential check |

The latest enforced-filter unit case executes five real forked child scenarios:
readiness/current affinity/thread create+join succeed; AF_INET socket, eventfd2,
other-PID affinity query and affinity mutation each die with SIGSYS. Existing
integration tests retain their heartbeat and quiescent snapshot semantics;
they are not new active-I/O or cross-mode restore tests. Original 31-test
pre-change safe/debug and initial32-test correction runs remain separate; cached reruns are not
counted as additional executions.

## Durable artifacts, blockers and resumption

Tracked [w0-evidence.tar.gz](w0-evidence.tar.gz) contains the raw result tree,
including failed builds/boot/operations, expanded commands, manifests, per-op
arrays, rosters, perf data/text, original failed decoder and recovery files,
trace attribution, summaries and validation logs. [SHA256SUMS](SHA256SUMS)
authenticates the archive. It deliberately excludes large guest images,
executables, caches and unrelated worktrees. A member-level inventory is
inside the archive as `evidence-manifest.json`.
The full private working evidence/immutable fixtures remain under
`.perf/eventfd/results/` and `.perf/eventfd/fixtures/` in this worktree.

Remaining blockers/work:

1. Required native slow-reader/backpressure correctness/liveness does not
   pass on L0; no-heartbeat L0 also stalls. Shared controls must address these
   explicitly and disclose L0→C00 effects separately.
2. Implement/prove common notification validation, actual fair blocking
   TAP/dynamic-vsock/kick ownership, guest-ring ordering, reset generations
   and whole-VM bounded pause/snapshot/teardown semantics.
3. Establish actual guest IRQ trigger/ACK/EOI policy; implement and stress
   independent exact per-queue IOEVENTFD and compatible IRQFD/resampling,
   unwind/fallback and C00/C10/C01/C11, without silently downgraded samples.
4. Missing sustained/full required TAP, complete disk, concurrency, interactive stdin,
   active-I/O/reset/failure and actual cross-mode guest-restore matrix is
   **unexecuted**, not skipped-as-passing. Host tools now exist.
5. Repeat matched baseline/control/idle data, freeze numeric benefit/
   regression/noise gates before candidate results, and charge all affected
   backend/kernel IRQFD/eventfd/resample scheduler work.

No default adoption, performance-merge recommendation, merge or auto-merge is
authorized by these results. The active execution plan remains blocked; this
draft foundation can be reviewed independently, not described as issue closure.
