# Product Spec: VirtIO ioeventfd/irqfd Performance Experiment

**Status**: Blocked qualification — four controlled modes implemented; timer-free integrity and separately scoped v2 restore evidence retained; historical80-cycle active disk oracle invalid pending corrected reruns; frozen performance gates unmet

### Independent runtime-review acceptance

Masking PIC/IOAPIC alone must not change an established route's edge/level
semantics. An actual trigger-bit reconfiguration must still reconcile while
masked; preservation is restricted to mask-only changes. Pending level completion must remain asserted across simultaneous
masks and deliver on IOAPIC unmask without another backend/MMIO wake. Test
the active→masked transition on real KVM for all controlled modes, including
used-before-IRQ, ACK/EOI and return to actual timer-free HLT.

Owner fatal publication must persist in the mapped KVM immediate-exit byte,
not rely on a transient SIGUSR1. Clear only before the final ordered failure
check; never clear afterwards, including API resume. Failure also wakes an
API-paused run loop. Deterministically inject a real owner error immediately
after admission/before KVM entry and during clear/resume for CLI/API paths;
require bounded fatal reporting and joined owners before memory teardown.

Historical80-cycle receipts remain intact but no longer prove an active disk
producer: the reviewed shell oracle can report RUNNING after a failed test.
The isolated harness fixes and actual corrected reruns are prerequisites,
not a relabeling of prior captures.

Final local review-fix acceptance: Debug/Safe each70 actual Zig+3 enforced
standalone cases, including eight active→masked guest IRQ scenarios, four
masked configuration changes and24 deterministic fatal paths per build.
All8 exact pre-entry paths observe consumed SIGUSR1 then actual KVM EINTR
with guest RIP unchanged; API pause/resume failure reporting and owner joins
complete. Hooks compile out of production. These are correctness repairs,
not performance evidence or closure of delegated harness/lifecycle gates.

**Last updated**: 2026-10-05

**Issue**: [#3](https://github.com/cataggar/hearth/issues/3)

**Execution plan**: [VirtIO eventfd experiment](../exec-plans/active/perf-virtio-eventfd.md)

### Ephemeral hosted qualification alternative

Shared-host noise is not a terminal experiment result. A separate
`ubuntu-24.04` GitHub-hosted job may collect a **new**, unpooled epoch, only
when the parent applies `perf-qualify-virtio-eventfd` to same-repository PR9
from `copilot/perf-virtio-eventfd-20261004`. Only `pull_request:labeled`
triggers it: no pushes, manual dispatch, fork code, persistent runner,
write permission, credential persistence or `pull_request_target`.
The event's exact head SHA, signed Zig0.17, verified5.10.245 kernel,
static-musl target, one production Safe binary and deterministic fixtures
are fixed across modes; no compiler/backend optimization is imported.

The job must verify Azure identity, nesting, functional nonroot KVM,
available independent physical cores/SMT, space and profiling privileges.
Do not assume the hosted VM is quiet or suitable. Choose VMM/client affinity
from the actual allowed topology, not vm31e CPU8/1. Run current real KVM/
mask/reset and full-jail checks, fresh five-repeat C00 A/A, then freeze the
unchanged numeric/noise gates **before** any candidate performance sample.
Collect matched paired controls, primary stat/stacks/exit attribution,
latency/throughput, all backend task CPU and scoped asynchronous IRQ work,
lifecycle/idle/scaling where resources permit. Missing kernel dispatcher,
scheduler or softirq attribution remains explicit detail coverage, never
zero or a complete attribution claim. The parent-refined visible-host total
below may qualify primary CPU independently if its quiet/uncertainty proof
passes. A bounded partial experiment cannot
claim adoption or turn unexecuted required coverage into a pass.

Only an explicit allowlist of sanitized receipts is uploaded: no guest
memory/disks, raw global traces, foreign process inventories, cloud resource
identifiers, environment dumps or secrets. Preserve failed/inconclusive
summaries and owned cleanup. The single run is bounded by time/storage;
unsuitable identity/resources and unavailable collection are actual blocked
outcomes. Parent applies the label only after source is published; until
then this alternative is **awaiting execution**, not a measured result.
Legacy default, draft/HOLD, prior evidence and all existing gates remain.

**Parent refinement:** on a verified isolated hosted VM, the primary total
CPU may instead be aggregate visible-host `/proc/stat`
user+nice+system+irq+softirq deltas over exactly marked completed-operation
windows. Linux user/nice already includes guest CPU: never add guest ticks
again, count `-a task-clock` as busy CPU, subtract unverified background or
claim Azure's physical hypervisor cost. Owned task/BPF CPU remains separate
mechanism detail and is never added to this total. Repeated no-VM before/after
quiet controls, counter/read precision and paired uncertainty bound residual
background. If that bound could hide the required benefit/regression limit,
qualification remains inconclusive/red. This is a new measurement epoch,
not reclassification of vm31e or relaxation of any numeric gate.

The [canonical jail correctness prerequisite](perf-jail-baseline.md) is reused
from `7dfee42` (`85e6f3b` provenance). Own exact bare canonical Debug/Safe each
pass32 units+3 actual enforced cases; this experiment each passes63+3.
Jail matches the canonical blob exactly; the experimental filter intentionally
retains only its existing confined eventfd2/SO_ERROR additions. The standalone
fixture now uses the supported positional command line, not an invented
`--cmdline` option. These are isolation/default-L0 correctness controls, not
performance or full current-head lifecycle acceptance; the experiment remains
blocked. New ELF identities and raw evidence are separate from older epochs.

## Goal

Pause-regression investigation must attribute actual synchronous kernel
deassignment separately from owner/vCPU fences. Test-only timing must not
become a production hot-path cost or substitute for matched Linux performance.
IRQ acceptance must include actual IRET followed by timer-free HLT, not stop at
an ISR's userspace exit; one already queued level EOI-before-ACK interrupt may
be handled, but repeated stale delivery or failure to sleep is a failure.
Masks/resets must retain generation and callback-drain barriers.

The executed stage now passes Debug/Safe66+3 each and32 native post-IRET
KVM-HLT cases, including bounded queued level interrupts and masked/reset
epochs. The separate nine-queue diagnostic places98.58–99.17% of C10/C11
pause wall inside synchronous deassignment calls; this is not kernel CPU
or Linux workload performance. All barriers remain; no safe minimal runtime
shortcut or gain is adopted. Earlier Linux pause regressions, failed noise,
halt-save0/4, legacy compatibility and full active congestion remain blockers.

Determine whether `KVM_IOEVENTFD` queue kicks and `KVM_IRQFD` completion
interrupts improve Flint on nested Azure KVM. Test each independently and then
together. Registration alone is not success: queues and host-originated I/O
must progress while the vCPU is blocked in `KVM_RUN`, including guest HLT,
without busy waiting, periodic kicks, or timer-driven device polling.

This is a falsifiable experiment, not a promised acceleration. A rejected
prototype with reproducible profiles, correctness findings, and a keep/reject
decision satisfies the investigation. W0 environment verification and untouched
baseline collection have produced real liveness/backpressure failures and
software profiles. This is **not** a completed/rejected prototype. No owner topology, IRQ policy, accelerated
mode, numeric gate, or default promotion had been selected in the published W0.
The parent's continuation instruction now authorizes W1: per-device blocking
owners are implemented in C00, with real no-heartbeat integrity/lifecycle
evidence. The independent accelerator modes now pass focused real KVM and Linux
integrity/lifecycle checks. Historical pre-cleanup C00 controls (85 cells) froze
numeric gates before candidate measurements; every non-idle class exceeded a
noise cap in that historical cohort. Historical longer primary diagnostics
suggest19–24% known-CPU reductions, but lack
qualified paired inference and complete scheduling attribution. C10/C11 also
show severe pause deassignment costs. Adoption gates and full stress/performance
coverage remain incomplete; no default promotion is justified.

**Actual results and durable evidence**:
[2026-10-04 controlled experiment report](../../benchmarks/virtio-eventfd/results/20261004/README.md).
Untouched L0 timer-free native traffic stalls after silence; eight 64 KiB
slow-reader messages also stall with a separately labelled heartbeat.
All four modes pass native-vsock/TAP/disk/agent/PTY, active-I/O acknowledged pause,
snapshot/resume, paused shutdown and sixteen actual cross-mode new-process v2
restores. Combined block/TAP/vsock outstanding-I/O snapshots also pass in all
four modes, subject to the reviewed active-disk oracle limitation above.
The80 repeated mixed fresh-process receipts no longer establish active disk
acceptance;64-connection/reuse and twelve native1/4/8-VM observations remain
separately scoped. Full mixed-sandbox/performance
qualification remains outstanding; these repairs are not eventfd acceleration. No
performance merge or default adoption is eligible.

**Fresh post-cleanup evidence (2026-10-05):** historical saturation and earlier
candidate diagnostics are not current qualification. Five fresh C00 matrices
pass85 integrity cells, but13/16 non-idle classes fail unchanged noise caps;
primary FLUSH CPU/op375.383µs has17.232% CV. No fresh candidate performance
sample was collected. Generation-checked nanosecond CPU accounting sums all
owned tasks over sustained≥5-second non-idle cells and cannot pool with legacy
short/tick windows. Current static-musl Safe/Debug each pass63 tests, four
enforced-jail cases and twelve total four-mode timer-free Linux cells. Fresh
native-only1/4/8-VM idle/concurrency checks and four IOAPIC EOI-first scenarios
per optimization pass; they do not close mixed-device scaling or active storm
acceptance. The linked report preserves exact pins, fresh profiles/noise,
183 recorded absent owned PID/TID numbers and the missing helper census.
Legacy default, fixed adoption gates and HOLD decision remain unchanged.

The subsequent current-binary4/8-sandbox mixed-device correctness matrix
passes8/8 mode/count cells (48 enforced sandboxes,12,288 checked64KiB TAP/
vsock messages) with actual common outstanding-I/O barriers, loaded exec/PTY,
whole-disk integrity, zero-CPU pause/resume and graceful joins. Its preserved
failed16-message pilot is not passing; the128-message retry retains the real
live-writer assertion. Collector/gate rejection tests pass20/20. This closes
unrun active scaling integrity, not candidate performance/idle regressions,
full IRQ storm/race coverage, old↔new legacy or actual save-on-halt.

Actual enforced CLI save-on-halt checks now expose a mandatory failure:
C00/C10/C01/C11 each verifies initial agent/disk/PTY integrity and reaches
`System halted`, but fails the20-second exit/save bound with both requested
snapshot files absent. Zero actual halt-save cases pass. Current corrected L0
stalls in agent traffic before issuing halt and is not counted as a halt case.
Successful API snapshots/reboot shutdown do not replace this acceptance;
the report preserves actual flags, halt markers, errors and owned cleanup.

A separately pinned fixture-only three-port diagnostic on corrected C00
passes5675 exact64-byte RPC echoes,41×8MiB host→guest,15×8MiB guest→host and
one TCP wake, with actual enforced jail/private mount+network namespace and
graceful owner join. Host initiates TCP to guest listeners; byte/sequence/
acknowledgement checks are not CRC. Only authorized guest/protocol Git objects
are reused, not sibling runtime or whole commits. No agent/heartbeat/periodic
serial workaround is added. These short cases do not substitute for untouched
L0, noise-qualified paired performance or demand; the linked receipt discloses
aggregate-CPU, raw-counter and helper-census limits. All existing blockers hold.

The common restore path retains snapshot v2 and the guest reconnect policy:
it publishes the standard `VIRTIO_VSOCK_EVENT_TRANSPORT_RESET` through the
already-existing event queue. This wakes the unchanged agent from obsolete
connections instead of expecting serialized host fds or a serial heartbeat.
Host generation counters and restore admission flags are not serialized.

The work follows [architecture](../../ARCHITECTURE.md) and
[core beliefs](../design-docs/core-beliefs.md): preserve hardware isolation,
snapshot-first lifecycle, and the simple SDK. Performance claims must not
trade correctness or idle CPU for headline latency.

## Current verified findings

Source inspection at `b07f73b26b8ae876928d9c515b94bba1e9945870`:

| Surface | Verified behavior and consequence |
|---|---|
| [`main.zig`](../../vmm/src/main.zig), `runLoop` | One vCPU is created. Queue notifications take `KVM_EXIT_MMIO`; the caller synchronously calls `processQueues`. TAP `epoll_wait(..., 0)`, dynamic vsock polling, and buffered vsock writes run only after `vcpu.run()` returns. Eliminating notification returns without moving actual servicing can strand work. |
| `main.zig`, `injectIrq`; [`kvm/vm.zig`](../../vmm/src/kvm/vm.zig), `setIrqLine` | Each injection requests high then low through two `KVM_IRQ_LINE` ioctls (the IRQ-line API referred to as `KVM_SET_IRQ_LINE` in the issue). Device slots receive IRQ/GSI `5 + slot`; the in-kernel PIC/IOAPIC and PIT are created. Serial also uses this helper and is not an attributed VirtIO gain. |
| [`virtio/mmio.zig`](../../vmm/src/devices/virtio/mmio.zig) | Transport writes accept four-byte data; driver features are masked against advertised features, queues check readiness, and processing requires `DRIVER_OK`. `INTERRUPT_ACK` clears bits in `interrupt_status`. A reset clears transport and queue state. No worker synchronization exists. |
| Notification validation gap | `MMIO_QUEUE_NOTIFY` itself does not decode the value. The caller processes queues at that offset even if `handleWrite` rejected the length; `processQueues` services the backend's relevant queues rather than selecting by notification value. Do not describe the baseline as already validating queue IDs. Shared validation and any corrected semantics must be measured separately from eventfd acceleration. |
| [`virtio/queue.zig`](../../vmm/src/devices/virtio/queue.zig), [`memory.zig`](../../vmm/src/memory.zig) | Split rings, maximum size 256, host-owned `last_avail_idx`/`next_used_idx`, descriptor-chain cycle checks and guest-memory bounds checks. Ring publication uses ordinary memory reads/writes today. A concurrent guest/worker design needs an explicit ordering and ownership argument, not just an fd. |
| [`virtio/blk.zig`](../../vmm/src/devices/virtio/blk.zig) | One queue; synchronous `pread`/`pwrite` and `fdatasync`, with capacity/status checks. Keep these operations and durability semantics unchanged in the notification experiment. |
| [`virtio/net.zig`](../../vmm/src/devices/virtio/net.zig) | Two queues, RX/TX; userspace nonblocking TAP with a 12-byte vnet header, MAC/status features and `readv`/`writev`. No vhost backend. RX availability and guest buffer replenishment must both wake servicing. |
| [`virtio/vsock.zig`](../../vmm/src/devices/virtio/vsock.zig) | Three queue slots (RX/TX/event); existing processing handles TX and pending RX control/data, not a new event-queue protocol. Guest-initiated connections map to host `${uds_path}_${port}` listeners. Up to 64 dynamic connection fds, credits, pending control packets, and bounded partial-write buffers require readiness/backpressure handling. |
| [`api.zig`](../../vmm/src/api.zig), `VmRuntime`; [`snapshot.zig`](../../vmm/src/snapshot.zig) | API pause uses atomics, `immediate_exit` and SIGUSR1 to stop the vCPU. Snapshot assumes that is sufficient to freeze device state and memory. New backend workers invalidate that assumption until a whole-VM quiescence barrier is implemented. CLI boot, API boot, both restore paths and save-on-halt all require coverage. |
| MMIO/queue snapshot helpers | Snapshot v2 stores transport status, features, interrupt status, ring addresses and host indices; backends are reopened. Live TAP/vsock connections are not restored. Vsock restore sets `last_avail_idx = next_used_idx` to discard old connection descriptors. Preserve/test this reconnect policy; host fds and eventfd counts are not restorable state. |
| [`kvm/abi.zig`](../../vmm/src/kvm/abi.zig), [`kvm/system.zig`](../../vmm/src/kvm/system.zig) | ABI is translated from target Linux headers; the system wrapper checks API version 12 but has no eventfd capability wrapper. Preserve useful raw errno/request context when adding capability/registration diagnostics. |
| [`jail.zig`](../../vmm/src/jail.zig), [`seccomp.zig`](../../vmm/src/seccomp.zig) | Jail setup closes inherited fds and drops privileges before KVM setup. Seccomp is installed before guest interaction; read/write/ioctl/epoll are allowed, but `eventfd2` is not listed. Worker threads must inherit the enforced filter. Do not move initialization outside the isolation boundary to bypass it. |

Existing [`tests.zig`](../../vmm/src/tests.zig) covers memory, translated ABI,
queue snapshot round trips and seccomp structure; it does not establish
eventfd, transport notification, or IRQ acknowledgement correctness. The seven
[`integration_tests.zig`](../../vmm/src/integration_tests.zig) cases exercise
usage/error, userspace boot, API status/pause/resume and snapshots with a
BusyBox serial heartbeat. They do not test block/TAP/vsock under active I/O or
prove halted-vCPU liveness. W0 now adds `-Dintegration-kernel`, resolving project-relative fixtures before
child working directories change; the historical CI default remains compatible.

The completed [Zig migration plan](../exec-plans/completed/zig-017-ci.md)
reports an Azure nested-KVM compiler comparison, not eventfd results. Its
minimal fixture used a controlled **10 ms serial heartbeat** to work around
idle vsock polling. Hardware cycles/instructions were unavailable. Reuse Zig
0.17 on both sides, not its latency figures or heartbeat as proof of liveness.
The baseline lacks a host-initiated vsock `CONNECT` listener: SDK port-forward
and tar-stream transfer are blocked there. Guest-agent interactive PTY code
also has a 50 ms polling workaround; hold it constant and report its effect.

## Experiment boundaries and controls

Capture untouched legacy **L0** before deciding worker topology, IRQ mode or
defaults. If common plumbing is necessary, establish a second **controlled
legacy C00** with the same reactor, validation, ownership and lifecycle changes
as every prototype, but ordinary MMIO kicks and IRQ-line delivery.

| Required controlled variant | Queue kick | VirtIO completion interrupt |
|---|---|---|
| C00: controlled legacy baseline | Validated MMIO exit | IRQ-line path |
| C10: ioeventfd-only | Per-queue ioeventfd | Same IRQ-line path |
| C01: irqfd-only | Same validated MMIO exit | Per-device irqfd |
| C11: combined | Per-queue ioeventfd | Per-device irqfd |

All four use identical guest images, drivers, compiler, features, queue sizes,
storage/TAP/vsock backends and servicing budgets. Compare C00 with L0 separately
to disclose reactor/validation cost or benefit. Factor contrasts C10/C00,
C01/C00, C11/C01 and C11/C10 distinguish mechanisms and their interaction.
A fixed-heartbeat comparative L0 series, if needed to get operations completed,
is a separately labelled diagnostic, not the primary liveness or latency gate.
If L0 cannot finish without it, report a stall, not an invented speedup ratio.

[Vhost-net #2](https://github.com/cataggar/hearth/issues/2) and
[async block #1](https://github.com/cataggar/hearth/issues/1) may coordinate
shared readiness/control plumbing, but are **not prerequisites** for this
experiment and must be disabled/excluded from its attributed comparisons.
Cross-feature experiments may follow only after separate baselines and results.

### Non-goals

- No vhost-net, io_uring/AIO, disk caching or durability changes, interrupt
  coalescing feature, packed rings, multiqueue, additional vCPUs, guest PMU,
  architecture expansion or compiler migration.
- No new VirtIO features, notification-data negotiation, SDK modes, vsock
  CONNECT/port-forward/tar support, or replacement guest interactive protocol.
- No broad seccomp relaxation, root-running VMM, external network dependency,
  or serialization of host resources.
- No default enablement or performance-improvement claim without passing the
  predeclared gates. A lifecycle format change is not assumed necessary.

## Required correctness contract

### Notifications and servicing

1. Use a common decoder for four-byte, aligned `QUEUE_NOTIFY` writes and valid
   queue IDs. Register `(VM, MMIO base + 0x050, length 4, DATAMATCH queue ID)`
   individually for supported queues only when the negotiated transport and
   queue state permit it. No address-only/any-length wildcard. Unsupported
   notification-data features remain unadvertised; future negotiation that
   changes the payload must use a compatible decoder or fall back.
2. Invalid width/value/address, wrong device/queue, disabled queue, pre-
   `DRIVER_OK` and stale-generation notifications must not service an unrelated
   queue. Unmatched writes still exit to the shared validation path. Queue-
   ready/status/feature writes remain ordinary MMIO; they coordinate
   registration changes with the device owner.
3. A blocking readiness reactor must service kicks and host TAP/vsock
   readability/writability independently of vCPU returns. C01 must still
   service ordinary MMIO kicks, and C10 must inject its legacy IRQs from the
   backend owner while the vCPU is blocked. Timer ticks are not the solution.
4. Nonblocking CLOEXEC eventfds use eight-byte counter reads/writes. Accumulated
   counts represent wakeups, **not descriptor counts**. Handle EINTR, EAGAIN,
   repeated/spurious wakeups and registration failure; reconcile ring state
   and recheck after draining so an arrival at the sleep boundary is not lost.
   Bound work fairly; if a budget expires with work remaining, schedule local
   ready work rather than wait for a kick the guest may suppress.
5. Prevent hot epoll loops when TAP/vsock is readable but there are no guest
   buffers or vsock credits. Rearm from RX kicks/credit updates. Enable socket
   write readiness only for actual pending writes; remove it once drained.
   Register/unregister dynamic connections before fd reuse.
6. Give each device's rings, queue indices, transport/IRQ state and backend
   connections one host mutation owner. Serialize MMIO configuration/ACK/reset
   through that owner or an equivalently reviewed lock/message protocol;
   define publication barriers for descriptor/avail reads and used writes
   concurrent with the guest. API snapshot may read only after all owners
   acknowledge quiescence. Memory may not be unmapped while workers refer to it.
7. Preserve request validation, disk ordering/FLUSH status, TAP headers,
   vsock credits and existing reconnect semantics. Verify payloads, used-ring
   indices and request IDs, not merely return-code or throughput counters.
   Notifications can legitimately coalesce; no lost work, duplicate
   completions, missing required IRQs or spurious post-reset delivery is allowed.

### Interrupt semantics

- Keep slot/GSI routing, device feature negotiation, interrupt-status bits,
  `INTERRUPT_ACK` masking and non-VirtIO serial behavior. Publish completion
  state/used ring before signalling the interrupt. Count completion batches
  separately from descriptors and from actual injected IRQs.
- Establish the guest's PIC/IOAPIC route and edge/level trigger mode in the
  baseline. The existing high/low pulse is not proof that level irqfd is
  interchangeable. Choose and document the compatible policy before coding
  the IRQ variant; any common semantic correction needs its own paired control.
- If level-triggered semantics are required, check `KVM_CAP_IRQFD_RESAMPLE` and
  use `KVM_IRQFD_FLAG_RESAMPLE` with a dedicated resamplefd. KVM deasserts on
  resampling/EOI and signals that fd; the owner drains it and requeues only if
  device interrupt status still requires service. Guest VirtIO ACK and irqchip
  EOI are distinct events. Test ACK-before-EOI, EOI-before-ACK, partially cleared
  bits, concurrent completion/ACK, masked IRQs and pending status across restore.
- An eventfd write is not a high/low setter; writing zero is not deassertion.
  Prove reset/deassign/pause behavior for the selected KVM mode, including a
  currently asserted line. Do not mix independently tracked IRQ sources on
  one GSI or deassert an irqfd by assuming a legacy low ioctl clears its source.
  If compatible semantics cannot be demonstrated, retain legacy IRQ delivery
  for that device/host and label the variant unavailable.

### Lifecycle, capabilities and isolation

Pause must stop admission, interrupt the vCPU, wake sleeping owners through a
control event, and wait for their in-flight work and mutations to reach a
defined stable boundary. Blocking synchronous disk operations may delay the
barrier; define a bounded wait/failure response instead of reporting a false
pause. No queue work or irqfd/resample callbacks may mutate memory, indices or
irqchip state during snapshot serialization.

Drain/reconcile pending kicks and IRQ state, synchronously deassign KVM
registrations as needed, and settle in-flight delivery **before** capturing
the coherent logical device/irqchip boundary. Preserve pending logical work;
do not throw it away by discarding counters. Review the order with KVM
irqchip save/restore, since deassignment may change line state. Resume and
restore recreate registrations from stable device identity/queue readiness,
reconcile rings/status and wake pending work before guest execution continues.
Host fd integers, eventfd counter values, epoll tokens and thread identities
never enter the snapshot. Retain snapshot-v2 compatibility if the quiesced
logical state suffices; otherwise explicitly design/version compatibility
before implementation, rather than silently changing the byte layout.

Reset/queue disable invalidates an ownership generation, quiesces old work,
deassigns with the exact registration tuple, removes epoll interest, and
discards only old-generation wakeups before reconfiguration. Teardown joins
owners and detaches registrations before closing fds, devices, VM and memory.
Cover partial setup and failed restore; fd reuse must not turn stale events
into notifications for another sandbox/device.

Probe `KVM_CAP_IOEVENTFD`, `KVM_CAP_IRQFD` and resampling where required.
Unsupported capabilities keep the existing path with an explicit reason.
Registration failures must identify request, mode, device/queue/GSI and errno;
roll back partial assignments and diagnose permission/resource/programming
failures, not disguise them as successful accelerated samples. Never retry
indefinitely or half-enable a variant. Expected unsupported fallback is a
functional result, not passing evidence for the unavailable experiment.

Allow only required eventfd/readiness/control syscalls with justified flags;
retain existing namespace, privilege, AF_UNIX, thread-clone and no-PROT_EXEC
restrictions. Test enforced jail/seccomp, not audit-only. No additional host
device or guest memory access is granted to workers.

## Measurement and acceptance

Nested Azure KVM is mandatory; non-nested KVM is an optional comparison whose
absence must be stated. Collect baseline **before design decisions** using
host `perf stat`, `perf record` with stacks and `perf report`; add available
KVM entry/exit tracepoints or `perf kvm stat`. Guest PMU is hidden by
`normalizeCpuid`; Azure hardware PMU may also be unavailable. Record capability/
permission failures and use software events/stacks, never fabricated cycles.

Run notification-heavy disk reads/writes/FLUSH, bidirectional TAP bulk and small
messages, supported guest-initiated vsock bulk/credit/backpressure, agent exec
and interactive first-byte/round-trip latency, concurrent sandboxes and idle.
Do not invoke unsupported CONNECT-based SDK paths as acceptance fixtures.
Measure throughput, p50/p95/p99, total host CPU per operation across **all**
VMM/backend threads, variance, kicks/completions/batches, userspace KVM returns
by reason, IRQ ioctl counts/time, eventfd syscalls and scheduling costs.
KVM tracepoint exits include kernel-handled exits: they are not automatically
userspace exits removed by ioeventfd. Keep client CPU separately visible.

Retain a manifest, immutable fixture hashes, exact commands, compiler/source/
dependency pins, host/guest kernels, Azure SKU/CPU/nesting, vCPU/RAM, driver and
IRQ state, affinity, cache/storage/network policy, warmups and samples.
Retain raw L0/C00 and every prototype's perf data/reports, counters, failures
and repeated-run distributions; distinguish profiled from unprofiled samples.

Freeze numeric gates from L0/C00 noise **before inspecting prototype results**.
The following are **provisional suggested criteria**, not measured thresholds:

| Gate | Suggested threshold to ratify from baseline |
|---|---|
| Correctness/liveness | Zero integrity, lost-work, duplicate-completion or stale-IRQ failures. Synthetic halted-vCPU I/O completes within 1 s without a heartbeat; 100 pause/resume/reset transitions and 20 active-I/O snapshot/restore cycles per controlled mode/device mix, plus 10 teardown/error cycles, with zero leaks. |
| Demonstrated benefit | On a preselected notification-heavy workload, at least 10% lower aggregate CPU/op **or** 10% lower p95 latency, with a paired 95% confidence interval excluding no benefit, and the mechanism counters explaining it. No selection of only the best run. |
| Mechanism check | C10 removes at least 90% of eligible notification userspace exits; C01 removes at least 90% of eligible VirtIO completion IRQ-line ioctls. These checks explain the mechanism, not prove end-to-end benefit; resampling/syscall/thread costs are charged in full. |
| Regression guard | Throughput loss at most 3%; CPU/op and each latency percentile increase at most 5%; boot/pause/snapshot/restore medians and p95 at most 5% worse than their paired control. Report unmet broader boot/restore/exec product targets separately rather than claiming to fix them. |
| Idle guard | Aggregate idle CPU increase at most 0.1 percentage point of one host core per sandbox, no continuously runnable servicing thread, no periodic timer/heartbeat introduced. Apply both one-sandbox and concurrent idle cases. |

Use repeated legacy-vs-legacy runs to estimate noise and set comparison windows.
If baseline noise exceeds a suggested relative threshold, record a justified
larger threshold before prototype evaluation, but cap it at 5% throughput and
10% CPU/latency/lifecycle. Above those caps, or with idle noise hiding the idle
bound, collect more/quieter samples or mark the decision inconclusive; do not
quietly relax gates after seeing a loss. Mandatory tests must execute on real
KVM; missing fixtures, unavailable required modes, timeouts and skipped cases
are blocked/failed coverage, never skipped-as-passing.

## Default, rollback and open decisions

### W0 isolation prerequisite

Under the required private `umask 077`, L0 creates root-owned jail device
directories with mode 0700 and nodes with mode 0600, then fails `/dev/kvm` open
after dropping to UID 1000. The common isolation prerequisite explicitly assigns
jail-local device directories to root-owned 0755 and KVM/TUN nodes to the
configured nonroot UID/GID with 0600, using no-follow opened FDs and explicit
mode normalization before the privilege drop. It changes
neither host device permissions nor device access outside the private jail.
It also clears supplementary groups before the configured UID/GID drop.

A real enforced child then revealed SIGSYS after its first KVM return.
Owned-process raw syscall tracing and frozen-binary disassembly identify
`epoll_pwait` (281), emitted by Zig's `epoll_wait` wrapper, missing from the
whitelist. The existing vsock backend also uses `poll` (7), verified in its
source and baseline software stacks. Only these two ordinary readiness calls
are added; `eventfd2` remains denied. A real forked enforced-filter test permits
readiness while still killing AF_INET socket creation and eventfd2.
The fixed jailed guest actually connects; its complete observed two-task roster
has UID/GID 1000, no supplementary groups/capabilities, Seccomp 2 and
NoNewPrivs 1. This covers boot/connect, not the whole eventfd isolation matrix.

These fixes are not C00 or an eventfd performance effect. L0 evidence remains
tied to its frozen old binary; the corrected isolation build is labelled
separately. Guest ring/IRQ/snapshot implementation remains unchanged.

Shared prerequisite `f2f9ab4c8e7a67097f2c3f52636327e9c41d5084` additionally
permits the actually traced Unix API `sendmsg`/`recvmsg` calls (46/47).
Its standalone regression dependency must not import the #1 benchmark.
Actual ownership/API traffic tests execute in Debug and Safe, including empty
groups/capabilities and PID-generation-checked teardown. The unchanged frozen
L0 failures remain separate.

Actual enforced API `InstanceStart` subsequently dies on syscall204.
Owned-process tracing and own-binary disassembly identify
`Thread.getCpuCount` querying `sched_getaffinity(0,128,...)`. Permit this
read-only query only for PID0; keep other-PID queries and affinity mutation
denied. Real forked enforced-filter tests must verify both the query and
continued denials, then actual CLI/API guest boot must be rerun. This ordinary
thread-startup prerequisite is not a backend owner or eventfd change.
The next traced denial is clone56: own `pthread_create` disassembly passes
0x007d0f00, including musl's ignored legacy CLONE_DETACHED0x00400000 bit.
Permit only that additional compatibility bit in the existing thread mask;
keep namespace creation denied and verify real filtered thread create/join.

The independent TAP prerequisite fixture uses the same numbered payload/FNV
protocol as the native vsock probe over a guest TCP listener. BusyBox configures
only a private namespace's owned TAP and guest interface; there is no uplink,
NAT, SDK CONNECT, timer or heartbeat. The host client is nonroot. The supervisor
must verify the actual VMM's post-drop credentials and enforced filter before
traffic, retain failed connections as failures, and remove only its owned
child/jail. A protocol fixture self-test is not guest/KVM acceptance, and an
isolation-repaired TAP result is not an original-L0 or C00 measurement.

Legacy delivery remains the default while planned and during experiments.
Prefer the simplest passing mode, including ioeventfd-only or irqfd-only;
do not presume combined wins. Default promotion requires the mandatory Azure
results, full lifecycle/isolation gates and an explicitly recorded decision.
Retain independently selectable legacy kick/IRQ paths, detected-mode
diagnostics and cross-mode snapshot tests for rollback. If no mode benefits,
reject acceleration; assess common correctness plumbing separately.

Decisions requiring evidence:

1. Which workload/exit breakdown justifies a shared owner versus per-device
   owners? Synchronous block can stall a shared reactor; topology must neither
   borrow #1 async block nor silently sacrifice net/vsock tails.
2. What route/trigger semantics does the pinned guest actually program, and is
   compatible resampling available on the mandatory Azure host?
3. Can quiescence/deassignment/reconciliation preserve snapshot v2 without
   additional logical IRQ state? What bounded pause error is safe on stalled I/O?
4. Which TAP/vsock fixtures pass payload/backpressure checks on L0, and how much
   do guest-agent polling and existing backend limitations obscure latency?
5. Which experimental mode selector and counters stay VMM/internal rather than
   enlarging the SDK? What per-device fallback is understandable and testable?
6. Are available host software events/tracepoints precise enough for attribution,
   and what baseline-derived numeric gates/sample size can be frozen?

### W1 common owner decision

The timer-free L0 vsock and post-silence TAP failures, and the source's exclusive
post-KVM_RUN polling, justify independent blocking readiness. Use per-device
owners for C00 and every accelerated mode: block remains synchronous within
its owner and cannot stall network/vsock servicing. All transport/ring/backend
mutation is serialized through that owner; the vCPU issues synchronous MMIO
control requests. Bounded batches revisit control before more data work.
Pause stops vCPU admission, acknowledges every backend owner and disables
readiness before logical rings/memory/IRQchip are captured. Resume reconciles
pending work before running the guest. New host wake fds are not snapshot state.
This chooses correctness plumbing, not a performance winner or default.

### W2 implemented delivery and lifecycle policy

The default remains L0; `--virtio-mode C00|C10|C01|C11` selects one strict
experimental mode, never a silently downgraded sample. All use the same
per-device owner, bounded budgets, ring validation/publication, synchronous
block backend and userspace TAP. Owner control uses an eventfd/futex mailbox;
idle readiness blocks in epoll without a timer. Dynamic vsock IN/OUT interests
respect credits and real partial writes, with generation-safe fd lifetimes.

Actual guest PIC/IOAPIC trigger/mask state determines a common IRQ policy.
Edge routes pulse; level routes remain asserted until logical ACK and use
IRQFD RESAMPLE when accelerated. ACK-before-EOI explicitly deassigns, drains
and recreates the irqfd source; zero writes or closing an fd are not deassertion.
Tiny real KVM guests verify used-before-IRQ, halted wake, both ACK/EOI orders,
counter aggregation and exact DWORD DATAMATCH/unmatched MMIO.
The follow-up dedicated suite passes14/14 tests in both Debug/ReleaseSafe:
masked PIC edge/level sources leave the guest halted until unmask in both
IRQ_LINE/IRQFD modes; masked level reset drains/deassigns the stale source,
then only a fresh publication wakes the guest. These checks do not complete
active IOAPIC-mask/congestion acceptance or justify performance adoption.

IOAPIC acceptance must use an actual enabled LAPIC/IOAPIC vector with both
PICs masked, not infer that path from PIC tests or host writes alone. Include
pending level completion while the masked PIC remains edge-configured:
masked-route selection must retain the level assertion until unmask/ACK,
rather than allow an ephemeral pulse to erase it. Verify mask/unmask,
ACK/EOI and reset epochs with timer-free guest observations in both modes.
The real unchanged-policy oracle now fails its masked IOAPIC level case
(15/16 dedicated tests pass). Common policy must preserve a level assertion
when both routes are masked and either is level; active-route choice and
mixed-active rejection remain unchanged. Fresh static-musl Debug/ReleaseSafe
actually pass55/55 each (39 units+16 dedicated,15 real enforced KVM plus one
policy unit). Each executes eight new unmasked edge/level and masked level
unmask/reset IOAPIC scenarios across IRQ_LINE/IRQFD. Both fresh binaries pass
4/4 hermetic jail cases, including deliberately inherited root-group clearing;
fresh ReleaseSafe passes12/12 native/agent/disk/TAP no-heartbeat four-mode
cells with enforced task identity. The seven prior integration cases are not
rerun or relabelled. New IOAPIC cases cover ACK-before-EOI, not complete active
congestion/EOI-first acceptance. This verified common correctness fix is not
an eventfd performance improvement; exact pins and raw evidence are in the
[results](../../benchmarks/virtio-eventfd/results/20261004/README.md).

The parent independently reported15.961/16 busy cores during a locked idle
control, with no iowait/steal, at22:33 UTC. This is externally reported control
evidence, not an owned baseline repetition. A quieter reserved window/host is
still required; frozen gates remain unchanged and no default promotion occurs.

The parent subsequently reports explicit user-approved cleanup of15 verified
old orphan busy-loop shells. This is not this task's cleanup or a performance
benefit. All earlier saturation/noisy measurements remain historical: fresh
controlled baselines and C00 A/A must precede new gates/candidate inference.
New short-window accounting records owned-task scheduler execution nanoseconds
alongside legacy ticks and start times, with generation/roster/counter guards;
nonidle cells run at least five seconds. Pin the collector/window metadata,
and do not pool this new methodology with the old matrix.

Pause also retires pending userspace MMIO/PIO through an immediate-exit
KVM_RUN reentry before owner fences and snapshot acknowledgement. A real
microguest verifies the emulated result/RIP while no subsequent guest
instruction executes. Host fds, counters and epochs remain absent from v2.
Normal shutdown joins owners and reports backend failure before cleanup.

Enforced isolation admits only eventfd2(init0, NONBLOCK|CLOEXEC) and
getsockopt(SOL_SOCKET,SO_ERROR) for the new control paths. An optional
PR_SET_NAME157 attempt was correctly killed by the filter; the naming syscall
was removed rather than admitted. Owner TIDs/fd identities are diagnostic logs.

The shared #1 compatibility follow-up
`5ee81b163b266f9c7643fb67c88cb59fe7aa2878` additionally narrows poll7 to
timeout0 and epoll_pwait281 to a NULL signal-mask pointer (both halves).
These restrictions cover actual existing vsock and blocking owner operations;
no arbitrary blocking poll or signal-mask override is needed. Reconcile its
exact blocks with experimental dispatch and validate before accepting a new
binary. Historical production/measurement pins remain immutable, and none of
the shared jail fixes are counted as eventfd acceleration.

The original four bounded acquisition requests (300s,180s,900s and
nonblocking) ended before any compiler/test/VM started. That publication
boundary remains in the immutable pending receipt. A subsequently acquired
exclusive window on2026-10-05 actually passes **39 unit +14 dedicated tests**
in ReleaseSafe and builds a separately pinned static-musl binary
`4c3bd1bd56cd4c58aa1c581658a473e640a0e759c41057459dd1dd1fd3fad5de`.
The same reconciled runtime subsequently passes Debug60/60, ReleaseSafe's
separate7/7 existing integration,4/4 hermetic Python jail cases per optimization
(deliberately seeded group0),17/17 benchmark Python and12/12 fresh four-mode
native/agent/disk/TAP no-heartbeat cells. New Debug SHA256:
`5b9f7201168d1b0b614d3d31d69da6813385c006aeb800999c989146f60dc84d`.
The verified selective archive contains136 hashed files and no VM images;
all64 recorded owned PID/TID numbers are absent at that seal boundary.
These b8a9-runtime results do not cover the later IOAPIC correction.
No new performance sample is collected; historical build19/performance/L0
pins remain immutable and are not relabelled as this new filter.

Shared `ced7ed72b5b2f80286e37ba8c9d5eada0cb90236` now supplies the existing
checked supplementary-group clearing semantics and a deterministic inherited
root-group regression. The hermetic #3 helper reuses its `setpriv --groups=0`
launch wrapper; the new case actually passes on both pinned binaries.

An ephemeral, unpinned, owned-TGID/exact-function BPF observer accounts actual
on-CPU `irqfd_inject`/`irqfd_shutdown` work and subtracts scheduler off-CPU
intervals. It emits only aggregate CPU/jobs, no foreign task names/stacks.
Combined integrity runs observe 2,386/3,178 injection jobs for C01/C11,
zero anomalies or incomplete work; C00/C10 correctly observe zero irqfd work.
These are attribution self-tests, not qualified performance gains.
