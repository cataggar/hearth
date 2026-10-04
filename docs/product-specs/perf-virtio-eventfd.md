# Product Spec: VirtIO ioeventfd/irqfd Performance Experiment

**Status**: Blocked after partial W0; acceleration remains unimplemented/disabled

**Last updated**: 2026-10-04

**Issue**: [#3](https://github.com/cataggar/hearth/issues/3)

**Execution plan**: [VirtIO eventfd experiment](../exec-plans/active/perf-virtio-eventfd.md)

## Goal

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
mode, numeric gate, or default promotion has been selected.

**Actual results and durable evidence**:
[2026-10-04 W0 report](../../benchmarks/virtio-eventfd/results/20261004/README.md).
Timer-free native traffic stalls after silence; eight 64 KiB slow-reader
messages also stall with a separately labelled heartbeat. C00/C10/C01/C11,
their correctness/lifecycle tests and the required full performance matrix
remain outstanding. No performance merge or default adoption is eligible.

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
jail-local device directories (0700) and KVM/TUN nodes (0600) to the configured
nonroot UID/GID before the privilege drop. It changes
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
