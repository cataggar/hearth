# Product Spec: Evaluate Asynchronous VirtIO Block I/O

**Status**: Evaluation in progress — baseline qualification incomplete; synchronous default unchanged
**Last updated**: 2026-10-04
**Issue**: [#1](https://github.com/cataggar/hearth/issues/1)
**Execution plan**: [perf-async-block-io](../exec-plans/active/perf-async-block-io.md)
**Execution evidence**: [baseline capability results](perf-async-block-io-results.md)

The untouched L0 execution verified project-local kernel/test support and retained
actual startup perf/stack diagnostics, but the unchanged enforced-jail API is
killed on `recvmsg` and the CLI cannot open jail device nodes created under
private umask. G0/G1 workload acceptance and A/A gates remain incomplete.
No asynchronous backend or qualifying performance comparison was implemented;
this is not an optimization rejection or a performance-merge recommendation.
Common host tools became available later; the results record the post-provisioning
inventory explicitly. Earlier captures remain capability diagnostics only.
Mandatory baseline sampling and frozen gates must use a newly established,
complete post-provisioning environment.
Fresh 16:11 UTC probes after fully verified host preparation confirm non-root
KVM VM creation and vhost-net access but reproduce both unchanged jail failures.
Those post-readiness startup diagnostics do not establish a workload baseline.
The separate repairs below now pass real enforced API/CLI guest capability
checks; the original L0 failures remain historical evidence, not current
failures of the repaired configuration or a performance comparison.

### Authorized correctness prerequisite — 16:18 UTC

Repair the demonstrated jail/API incompatibilities in a separate commit before
resuming the experiment. Keep untouched L0 binaries, failures and all unjailed
diagnostics distinct. Newly created jail device directories must be explicitly
root-owned and traversable (`0755`), with no dropped-user directory write
permission. Device nodes must be explicitly owned by the configured jail
UID/GID with mode `0600`, independently of ambient umask; artifact umask stays
`077`. Normalize through no-follow opened FDs before dropping privileges.
Allow only Unix API receive/send syscalls actually observed necessary under
the kill filter; retain AF_UNIX socket and clone/mprotect confinement.

Execute focused real-jail ownership/access and enforced-filter HTTP tests.
Declare the resulting identical repaired synchronous revision as a new
baseline, not a performance candidate or improvement over failed L0. Then
repeat G0/G1; no worker selection or correctness-only performance auto-merge.

Full-boot traces after that minimal commit additionally prove Zig 0.17 needs
self `sched_getaffinity` for API thread startup and `epoll_pwait` with a null
signal mask for the already-intended epoll wait. A separate compatibility
follow-up may allow only PID0 affinity reads and null-mask epoll waits, not
scheduler changes, other-process affinity inspection, or altered signal masks.
Keep each trace/revision distinct and test the new argument checks.
The next traced stage proves the existing vsock loop needs nonblocking `poll`
(timeout0), and Zig's thread flags include `CLONE_DETACHED`0x400000. Linux UAPI
declares that bit unused/ignored; recognizing it does not permit another
active clone capability. All namespace/process-escape flags stay denied.

### Repaired synchronous execution status

The identical repaired configuration `5ee81b1` now verifies real guest fio3.40
libaio loading, fully written1GiB, and achieved QD8/QD32. Short warm-read
diagnostic repeats plus actual all-listed-TID software stat/stack records
exist, but are not the complete G1 matrix or frozen numeric gates.
Current own controls find99.799875%whole-host busy under the shared lock;
no-heartbeat agent exec times out3/3 after five seconds idle. Original jail
repairs are complete; mandatory baseline idle progress and controlled total
CPU attribution remain blocked. The detailed results preserve both successful
capabilities and failed trials. No async worker/default or performance merge
is justified, and the full plan remains active/incomplete.

Further execution verifies the actual pinned offline disk-root package/build
fixture, short loaded exec/identified PTY and1/2/4 jailed topology capabilities.
Pause/snapshot/disk-copy/resume executes real guest state; fresh API/CLI
restored-agent checks block3/3 within30s. A single full-window flush profile
retains actual syscall wall-duration outliers, not qualified paired confidence.
Matched host controls98.824118%/99.849962%busy and shared ENOSPC/owned-image cleanup expose
additional environmental limits, not optimization gains. The separate jail
prerequisite todo is done; the implementation todo remains in progress.
See the results before treating any mandatory row or gate as accepted.

Collector tooling now explicitly scopes build-ID cache/scratch after sudo and
disables debuginfod lookup; real jailed collection/force-read decoding and
focused regressions pass. Historical root cache locations were not explicitly
scoped, and no global cache is inspected or cleaned. Own thread credential
captured5ee81b1 roster retains supplementary Groups0; a group-clearing correction is
not silently incorporated into prior profiles. Tooling acceptance is not a
backend decision or isolation/performance promotion.

### Common credential-hygiene prerequisite

The dropped jail process must not retain the bootstrap's supplementary
groups. Clear them before setgid/setuid, fail closed on error, and do not add
setgroups to the runtime seccomp allowlist. Test with a deliberately inherited
root group under the real enforced filter; confirm configured UID/GID,
empty supplementary groups and unchanged node/directory policy. Preserve the
prior5ee81b1 binaries/profiles. Treat the additional correction as a new common
synchronous revision, not an async gain or permission broadening.

This correction now passes32 units,7 real KVM integrations and12 Python cases
per Debug/Safe, plus4 actual jailed API/CLI disk-and-credential controls.
The fixed `x86_64-linux` target and original guest features are retained.
All observed new VMM tasks have empty supplementary groups; old5ee profiles
remain distinct. A fresh no-owned-VM host control still measures99.9375%busy
(79.94 busy CPU-s/5.0003wall-s). G0/G1 qualification remains blocked.

## Objective and scope

Determine whether moving backing-file operations off Flint's vCPU loop improves
disk throughput or sandbox responsiveness at acceptable **total** CPU and memory
cost. Profile first on nested Azure KVM; a negative keep/reject decision is a
valid outcome. Synchronous I/O remains the default until measured benefit and
correctness justify changing it.

This follows [architecture](../../ARCHITECTURE.md) and
[core beliefs](../design-docs/core-beliefs.md): real isolation, snapshot-first
lifecycle, low interactive latency, and no new SDK configuration burden. This
document specifies an experiment and acceptance contract, not measured results.

## Current source facts

Grounded in revision `b07f73b26b8ae876928d9c515b94bba1e9945870`; recheck these
facts against the execution revision before benchmarking.

| Surface | Current behavior and consequence |
|---------|----------------------------------|
| `vmm/src/main.zig:runLoop`, `injectIrq` | One vCPU. A `KVM_EXIT_MMIO` queue notification invokes `processQueues` inline, then pulses `KVM_IRQ_LINE`. Backing I/O blocks guest execution and other userspace device work. |
| `vmm/src/devices/virtio/mmio.zig:processQueues` | Block queue 0 is drained synchronously, up to its queue size per call. Processing sets `INT_USED_RING`; `getPollFd` only exposes TAP, not block completions. Reset currently clears transport/queue state without backend coordination. |
| `vmm/src/devices/virtio/blk.zig:processRequest` | Opens the backing file buffered `O_RDWR|O_CLOEXEC`; implements IN, OUT, FLUSH and GET_ID using `pread`, `pwrite`, `fdatasync`. Short reads are zero-filled; short writes retried; failures use `S_IOERR`, unsupported types `S_UNSUPP`. IN lengths include data plus status, OUT/FLUSH status only; malformed requests reach the MMIO error path's zero-length completion. Characterize error/GET_ID length details before splitting execution. |
| `vmm/src/devices/virtio/queue.zig` | Split queues, maximum 256 entries, host-owned avail/used tracking, bounds-checked chain traversal with cycle detection. Block uses a 16-descriptor capture array; there is no advertised maximum aggregate request byte size. `popAvail` advances immediately: async admission must reserve resources first. |
| `vmm/src/main.zig:VmRuntime`, `runLoopThread` | API pause uses `immediate_exit`, SIGUSR1 and a vCPU acknowledgement. Epoll runs with timeout zero **after KVM exits**; EINTR normally re-enters KVM without device servicing. CLI boot/restore passes no runtime. An event FD alone would not wake blocked `KVM_RUN`. In-kernel HLT can block there; a returned `KVM_EXIT_HLT` is currently terminal/save-on-halt. |
| `vmm/src/api.zig`, `snapshot.zig`, MMIO snapshot methods | Pause acknowledgement currently covers only the vCPU. Snapshot format v2 stores CPU/IRQ/device/queue state and guest memory, not disk contents or host work. Restore reopens supplied backends. New workers would make “vCPU stopped” insufficient. |
| `src/vm/snapshot.ts`, `src/sandbox/sandbox.ts` | These are the actual SDK snapshot paths (not the architecture map's `src/snapshot/`). Disk artifacts are separately copied/moved while paused. All I/O must be settled before the caller can copy that disk. |
| `vmm/src/main.zig:VmComponents.deinit`, restore functions | Fresh-boot cleanup deinitializes devices before memory; restore's defer ordering currently frees memory before devices. Worker shutdown must precede memory unmapping on **every** path. |
| `vmm/src/jail.zig`, `seccomp.zig` | Jail closes inherited FDs, pivots root, clears supplementary groups, drops UID/GID and applies optional cgroup limits. Seccomp is installed before guest interaction and permits filtered thread clone, futex, tkill and existing I/O/epoll; it does not whitelist eventfd or io_uring syscalls. An unlisted syscall kills, so fallback cannot rely on catching its errno. |

Block advertises only VERSION_1 and FLUSH, one split queue, with file capacity in
512-byte sectors. The API accepts one disk path and memory sizing; it reports
one vCPU, not configurable SMP. Root/read-only drive fields do not establish an
implemented read-only backend. Do not infer multiqueue, indirect descriptors,
EVENT_IDX, discard, direct host I/O or a selectable async backend from the API.

The [Zig migration plan](../exec-plans/completed/zig-017-ci.md) supplies compiler
fixture/perf prior art, not this baseline. It documents unavailable Azure host
hardware PMU, a controlled serial heartbeat needed by existing idle-vsock RX
polling, and absent host-initiated vsock CONNECT. Guest PMU is explicitly hidden
by `main.zig:normalizeCpuid`. Control/exec and PTY workloads can use the existing
guest-initiated port-1024 connection; SDK forwarding/tar-stream and clean
installed-image workloads must be capability-checked, not presumed working.

## Compatibility and correctness contract

1. **Interfaces and attribution.** Preserve guest feature bits, disk capacity,
   queue layout, control protocol and supported CLI/API boot/restore flows.
   Keep legacy MMIO notifications and IRQ pulses fixed for the primary
   comparison. [#3](https://github.com/cataggar/hearth/issues/3) is independent:
   ioeventfd/irqfd is not a prerequisite; any later combined experiment needs
   separate sync/async comparisons under each notification mode.
2. **Bounded ownership.** Capture header, descriptor metadata, head, validated
   offsets/lengths/directions, status destination and queue/device/memory generation
   before submission. Validate all ranges and checked arithmetic before host
   I/O. Workers must not traverse mutable guest descriptors or retain
   unprotected guest pointers. Prefer host-owned staging buffers and an owner
   that alone writes guest memory, used rings and interrupt state. Malicious
   descriptor/header mutation or ring reuse cannot redirect a completion.
3. **Backpressure and progress.** Bound admitted requests, queued completions,
   staging bytes and workers per device/VM. Reserve credits before consuming
   avail entries; saturation leaves unadmitted work available, not dropped.
   Completion processing must refill available work without requiring another
   guest doorbell. Oversized valid requests need bounded chunking/progress,
   not indefinite waits for more credits than the pool has, or an undocumented
   new request-size restriction. Partial chunks still produce exactly one
   final request completion.
4. **I/O semantics.** Preserve read zero-fill, write short-I/O handling,
   per-request status and completion-length rules, GET_ID and unsupported/error
   behavior. Establish synchronous differential tests, including failure after
   a partial transfer, rather than silently changing existing quirks. Flush
   waits for all earlier accepted writes, performs `fdatasync`, and cannot
   report success before durability is established. Later writes cannot cross
   that barrier; no broad reordering/parallel writes without proven overlap
   and barrier semantics. Never replay a possibly committed write on fallback.
5. **Actual wakeup.** Completions must be processed while guest idle/HALT waits
   inside `KVM_RUN`, without timers, heartbeats or busy polling added for
   block progress. A signal-kick path based on the existing mechanism is a
   candidate, not a proven solution: handle pending completion on EINTR and
   prove no lost wake across pre-entry, entry, blocked-run and pause races.
   Cover API and CLI modes. Preserve terminal HLT/save-on-halt behavior after
   safely draining; do not reinterpret every HLT as a running idle guest.
6. **Quiescence.** Stop admission, stop the vCPU, drain accepted I/O, publish
   applicable completions/IRQ state, then acknowledge pause. After successful
   pause there are no writes to disk/guest memory/queues/IRQs until resume.
   Snapshot captures one consistent boundary before SDK disk copying. Decide
   explicitly whether snapshot also synchronizes the backing FD; do not
   promise crash durability from an unperformed sync. Measure any added cost.
7. **Generations and cleanup.** Reset, restore and teardown invalidate old
   generation completions. Drain old writes before allowing a new generation
   to modify the same disk; suppress stale guest-memory/IRQ publication.
   Queue reconfiguration/disable must also invalidate or safely quiesce captured
   work; publication cannot use a newly changed size/address/ready state.
   Restore starts with empty host work and reconstructed resources, never
   serialized pointers, threads or pending host requests. Join/cancel safely
   before closing FDs/unmapping memory, including partial initialization and
   failure paths. No double completion, use-after-unmap, leaked FD or worker.
   A drain deadline failure must fail closed, not return successful pause or
   snapshot while work remains, or detach an unsafe worker. Resume/restore must
   service retained avail entries without depending on a fresh doorbell; do
   not apply vsock's stale-connection index workaround to block queues.
8. **Isolation and fallback.** Diagnose selected backend and initialization/
   capability failure explicitly. Retain synchronous operation and an
   experimental force-sync escape hatch. Fallback is safe before admission;
   later failure needs ordered quiescence/error handling. Worker threads
   inherit the jail/filter/cgroup. Keep clone/socket/mprotect restrictions;
   no new host device node, broad syscall allowance or weakened jail.

Prefer the simplest bounded FIFO worker first **if profiling supports it**.
Multiple workers and io_uring are conditional alternatives only if measured
worker cost/serialization warrants them. Ring support, required operations,
kernel/policy restrictions, cancellation, fixed-buffer lifetime and kernel
io-wq accounting must be verified. SQPOLL/idle spinning is not an assumed win.

## Measurement and decision contract

Run host-side `perf stat`, `perf record` with call stacks and `perf report` on
the baseline **before selecting a prototype**, and repeat on each candidate.
Attribute syscall durations, I/O service/queue time, scheduler off-CPU wait and
KVM exit/entry events where available. Include vCPU, API, backend/dispatcher
workers and attributable kernel I/O CPU; shifting cost to another thread is
not a speedup. Use software events if host PMU is absent, retaining probe
failures and available tracepoints. Guest hardware PMU is not an option.

Required workloads: 4 KiB random read/write at QD1 and higher depths,
sequential read/write, frequent flushes, offline representative package/build
work, concurrent VMs, and both exec and interactive vsock under disk load.
Report:

- IOPS/bytes per second and p50/p95/p99 full request latency (distinguish guest
  fio operation latency, VMM avail-to-used latency, and host syscall latency);
- exec submit-to-first-byte and submit-to-response, PTY input-to-identified
  reply, and timeout/error counts, with and without disk load;
- total CPU time per completed request/byte, syscall and KVM exit counts/cost,
  scheduler wait, peak/current in-flight work, staging/RSS/FD/thread counts;
- idle CPU/wakeups and pause, snapshot, resume/restore latency, including drain.

Record exact source revisions/dirty diff, compiler/optimization/binary hashes,
locked dependency revisions/hashes, host and guest kernels/configurations,
CPU/Azure SKU/nesting, VM count/vCPU/RAM, disk/filesystem/mount/cache/storage
settings, data/image sizes/hashes, workload/tool versions and complete commands,
warmup, samples, affinity, order/seeds, variation and trace loss. Retain raw
profiles, latency distributions, results and scripts in a private durable
artifact location. Prefer a quiet reserved host; measure background CPU/I/O
and label kernel attribution uncertainty instead of excluding it.

Nested Azure is mandatory for a default decision. Add a non-nested comparison
when available; explicitly record unavailability rather than extrapolating.
The recipe and capability/fixture gates are in the execution plan.

### Baseline-derived numeric gates

These are **provisional proposed thresholds, not observed results**. After
baseline/baseline repetitions, freeze each workload's absolute baseline,
noise interval, margins and primary metric **before prototype selection**.

| Gate | Proposed starting threshold |
|------|-----------------------------|
| Meaningful benefit | At least 20% lower loaded interactive p99, **or** at least 15% higher sustainable IOPS/throughput on a predeclared blocking workload with no interactive regression. Explain the profiled causal change. |
| Disk/representative regressions | At most 5% worse QD1 p50 or throughput/package/build elapsed time; at most 10% worse disk/interactive p95/p99 in every required comparison. |
| Total cost | At most 5% more total attributable CPU/completion; account deferred writeback through its final drain. No improvement claim based solely on vCPU task-clock. |
| Lifecycle | At most 10% worse pause and snapshot p95, measured separately and end-to-end with disk artifact copying; at most 5% worse resume/restore median. |
| Idle | At most +0.5 percentage points of one host core per VM, with no periodic block-completion wakeups. Report existing heartbeat cost separately. |
| Resource budget | Initially at most 32 admitted requests/device, 8 MiB staging and 1 MiB bookkeeping/device; at most 16 MiB incremental peak RSS/VM including worker stacks. Freeze a compatible budget after baseline, before choosing a prototype; account all ring/completion storage. |
| Correctness | Zero data mismatches, missing/duplicate/stale completions, successful-but-undurable flushes, leaks, unsafe snapshots or required test skips. |

Let `B` be the baseline metric and `N` the baseline/baseline 95% relative noise
bound. Proposed relative margins are `max(table percentage, 2N)`; turn them
into absolute gates using `B × (1 ± margin)`. Keep idle/resource/correctness
ceilings explicit, not proportionally inflated from near-zero baselines.
Use paired repeats and 95% confidence intervals: the benefit lower bound must
clear its frozen margin; regression upper bounds must stay within theirs.
If noise would expand a 5% gate beyond 10%, or a tail gate beyond 20%, collect
more data/control the host; do not approve a default with inconclusive results.
Do not tune margins after seeing candidate outcomes.

## Non-goals and open decisions

The original planning change performed no implementation/benchmarking. Current
baseline capability execution is recorded above; no qualifying disk benchmark
or backend implementation has passed its gate. No
compiler migration, notification optimization, guest PMU exposure, SMP/
multiqueue/new block features, storage/image redesign, unrelated vsock CONNECT
repair, SDK API expansion or broad cleanup belongs to this experiment.

Decisions at the designated plan gates:

- Does baseline show disk stalls rather than notification, guest polling,
  filesystem cache or nested scheduling as the limiting cause? Stop if not.
- How will a race-safe completion owner wake in both API and CLI paths?
  Which minimal synchronization/syscalls are needed under the installed jail?
- Which bounded staging/chunking and barrier model preserves existing large
  requests and error lengths? Is one ordered worker sufficient?
- What is the safe quiesce deadline/error state for uninterruptible host I/O,
  and does snapshot require an additional backing-file sync?
- Is experiment selection build-local or a developer-only CLI switch? It must
  work across boot/restore without adding SDK knobs or changing snapshots.
- Can the verified fixture supply fio, offline package/build tools and enough
  tail samples? Missing capabilities block that acceptance row, not pass it.
- After measured worker results, is io_uring worth its isolation/lifecycle
  complexity? A rejection or opt-in-only outcome remains acceptable.

Retain format-v2 compatibility by draining host work out of snapshots. Any
necessary format change requires an explicit compatibility decision before
implementation. The final report must select **keep synchronous**, **retain
experimental opt-in**, or **enable the proven backend by default**, with raw
evidence, limitations and a tested force-sync rollback.
