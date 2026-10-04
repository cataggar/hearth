# Product Spec: Capability-gated vhost-net Evaluation

**Status**: Evaluation blocked; reject current vhost adoption, userspace unchanged
**Last updated**: 2026-10-04
**Issue**: [#2 — Perf-profile and evaluate a vhost-net backend for Flint](https://github.com/cataggar/hearth/issues/2)
**Execution plan**: [perf-vhost-net](../exec-plans/active/perf-vhost-net.md)

This is an experiment specification, not an implemented vhost backend.
The userspace backend remains the default. The 2026-10-04 evaluation first
records the current backend in an isolated diagnostic TAP fixture; that fixture
is not evidence of an existing product consumer. Backend implementation remains
conditional on S0 relevance and the mandatory lifecycle gates.

## Executed disposition (2026-10-04)

The [execution evidence](../perf-results/vhost-net-20261004.md) records three
unchanged nested-Azure boots, 120 unsuccessful requested TAP workload runs,
seven validated active RPC responses, actual system-wide software/KVM profiles,
and a successful independent native-peer protocol check. No current product
TAP consumer was demonstrated. Pre-existing unrelated host processes saturated
nearly all 16 logical CPUs; a quiet-host total-CPU/noise qualification is not
available. The full active-window and tail observation floors are not met.

Reject/defer adding a vhost backend for the current product. This is **not**
a measured vhost loss or improvement: A′ and B were not implemented or run.
Non-root vhost feature probing succeeds after host provisioning, but device
presence does not prove 12-byte framing, worker quiescence, authoritative used
cursors, snapshot portability, CoW, confinement or resource isolation. Those
mandatory contracts remain unproven. The execution plan stays active/blocked
rather than claiming implementation completion or recommending a performance
merge. There is no new selector, SDK mode, jail relaxation or runtime change.

Post-provisioning retries separately freeze tools/libraries/device ACLs and
confirm actual non-root KVM creation plus vhost feature access without FD loss.
Four further requested network windows fail with zero active completions.
Lower-volume whole-host stack/direct-KVM idle recordings and no-VM controls
succeed, but background saturation remains about 16 cores. Earlier partial
environment samples are diagnostics, not a controlled comparison; profiler
overload/frontend failures are preserved. Readiness does not resolve relevance,
qualified A/A noise or kernel lifecycle/confinement proof.

## Objective and applicability

Determine whether Linux vhost-net reduces **total host CPU cost** or improves
relevant TAP networking on nested Azure KVM without weakening isolation,
correctness, idle behavior, or snapshot semantics. A negative result, including
“no current product workload benefits,” is a successful evaluation.

First identify actual Flint TAP consumers, their traffic, and why they matter.
The shipped SDK's internet path is HTTP CONNECT over VirtIO-vsock, not
VirtIO-net. Faster synthetic TAP traffic does not establish faster `npm install`,
`Sandbox.exec()`, SDK forwarding, or tar transfers. An opt-in raw-network use
case must be demonstrated before accepting the maintenance cost. Do not add a
new SDK TAP mode merely to manufacture that relevance.

## Current source findings

Inspected source revision: `b07f73b26b8ae876928d9c515b94bba1e9945870`.
Historical architecture diagrams describe TAP/NAT; current code and
[networking design](../design-docs/networking.md) determine applicability.

| Surface | Current behavior and implication |
|---------|----------------------------------|
| `vmm/src/devices/virtio/net.zig` | Opens `/dev/net/tun`, attaches `IFF_TAP \| IFF_NO_PI \| IFF_VNET_HDR`, sets a **12-byte** vnet header and nonblocking FD. `processTx()`/`pollRx()` walk split rings and use `writev`/`readv`, with at most 16 descriptors collected per chain. Merely loading `vhost_net` changes none of this. |
| `net.zig`, `vmm/src/devices/virtio/mmio.zig` | Offers only `VIRTIO_F_VERSION_1`, MAC, and link status for net, with RX queue 0 and TX queue 1. MMIO filters driver feature writes against offered features; `processQueues()`/`pollRx()` require `DRIVER_OK`. There is no existing vhost ownership/activation hook. |
| `vmm/src/devices/virtio/queue.zig` | Maximum queue size is 256. Tracks `last_avail_idx` and `next_used_idx` in userspace, bounds-checks guest slices, detects chain cycles and invalid indices, and serializes host tracking. Kernel-owned queues cannot leave these counters stale at snapshot time. |
| `vmm/src/main.zig`, `vmm/src/kvm/vm.zig` | `MMIO_QUEUE_NOTIFY` exits synchronously service queues; `injectIrq()` uses `setIrqLine()` high then low. TAP is registered in epoll, but `epoll_wait(..., 0)` runs **after** `KVM_RUN` returns. This is not an independent idle RX wakeup mechanism. No ioeventfd/irqfd wrappers exist here. |
| `vmm/src/memory.zig`, `main.zig`, `vmm/src/snapshot.zig` | A single guest RAM mapping is registered at GPA 0, slot 0. Restore uses writable `MAP_PRIVATE` demand-paged snapshot memory. vhost must register the actual current HVA and preserve private CoW semantics, not switch to shared memory. |
| `main.zig`, `vmm/src/api.zig`, `snapshot.zig`, `mmio.zig` | API pause acknowledges the stopped vCPU, not kernel network workers. Snapshots save transport/queue state and MAC, not live host FDs. Reset clears transport/queues without a backend stop hook. Restore recreates devices before loading memory; its memory cleanup currently precedes device cleanup through defer ordering. These paths require explicit worker fences before attaching a kernel backend. |
| `vmm/src/jail.zig`, `vmm/src/seccomp.zig` | Jail setup precedes device opens, closes inherited FDs, creates KVM and optionally TUN nodes, then drops privileges. No vhost node is declared. Seccomp allows ioctl without request filtering and epoll/read/write, but not `eventfd2`; socket/clone/mprotect restrictions must remain intact. |
| `src/sandbox/sandbox.ts`, `src/vm/snapshot.ts`, `src/sandbox/types.ts` | Fresh/base boot configure block and vsock only; restore supplies disk/vsock, not `--tap`. `CreateOptions` has no network backend option. `enableInternet()` starts the proxy and supplies proxy environment variables. `forwardPort()` and transfers use vsock CONNECT. |
| `src/network/proxy.ts` | Port 1027 UDS accepts HTTP CONNECT and relays through Node `net.connect`. vhost-net cannot accelerate this path. |
| `vmm/src/tests.zig`, `vmm/src/integration_tests.zig`, `src/sandbox/sandbox.test.ts` | Unit tests cover memory bounds, queue snapshot round-trip and seccomp structure, not net RX/TX. The seven integration tests cover boot/API/pause/snapshot with a serial-heartbeat BusyBox guest and no TAP traffic. SDK tests cover proxy/vsock behavior, not TAP. |

`main.zig::normalizeCpuid()` hides the guest PMU. The completed
[Zig migration plan](../exec-plans/completed/zig-017-ci.md) records existing
idle-vsock limitations and absent host-initiated vsock CONNECT support, blocking
baseline SDK forwarding/tar acceptance. Do not reclassify those as passing
coverage or vhost regressions. Installed-image and native AArch64 gaps also
remain explicit; this experiment targets x86_64 Linux KVM.

## Non-goals

- No acceleration or redesign of vsock, the proxy, SDK networking or Azure VF
  drivers; no new product NAT, bridge, routing, or public SDK networking API.
  Experiment-owned external-path routing is only a measurement fixture.
- No PCI transport, multiqueue, packed/indirect rings, mergeable RX buffers,
  checksum/GSO/TSO features, or larger queues added to improve benchmark scores.
- No compiler migration, guest PMU enablement, asynchronous block work, kernel
  fork, broad jail relaxation, or assumption that another perf issue must land.
- No default change from module/device presence, Flint-only CPU measurements,
  non-nested-only results, or unprofiled microbenchmarks.

## Required backend contract

### Capability selection and failure

Proposed experiment selector: `userspace` (unchanged default), `vhost` (strict
request), and `auto` (explicit opt-in capability fallback). These are **not
current CLI/API options**. Probe only when a TAP backend is requested.

Report requested and effective backend, notification/IRQ mode, negotiated
features, and a stable reason plus failing operation/errno for unavailable
device, access denied, unsupported kernel ABI/features, unsupported memory or
queue layout, header/TAP mismatch, eventfd failure, or confinement denial.
`auto` may choose userspace only before activation, after fully unwinding partial
vhost setup. Strict `vhost` fails visibly; an invalid guest queue or uncertain
runtime ownership is an error, not a silent “unsupported” fallback. Never switch
backends while both could consume a queue or write guest memory.

Selection/device permissions must be declared before jail setup. Preboot API
requests cannot broaden the jail after privilege drop. No-vhost hosts must keep
working with userspace and explain any explicitly requested fallback.

### VirtIO-MMIO and kernel setup

Reuse device identity, MAC/status config, MMIO register layout, two existing
split queues, guest feature filtering, and interrupt status/acknowledgement.
Both variants must offer and negotiate the same existing feature set.

The prototype must actually:

1. Open `/dev/vhost-net` with close-on-exec and establish `VHOST_SET_OWNER`.
2. Query `VHOST_GET_FEATURES` and configure `VHOST_SET_FEATURES`; distinguish
   guest transport/data features from
   MAC/status config handled in Flint and vhost-private feature bits. Reject an
   unsupported mandatory negotiated data feature rather than silently changing
   guest semantics. Explicitly select header ownership
   (`VHOST_NET_F_VIRTIO_NET_HDR`) and prove **12-byte v1 framing** against the
   existing TAP configuration in both directions.
3. Register `VHOST_SET_MEM_TABLE` from the same live GPA/HVA/length mapping as
   KVM. Validate range arithmetic and keep mapping lifetime longer than all
   possible kernel access.
4. At validated queue-ready/feature/`DRIVER_OK` transitions, configure
   `VHOST_SET_VRING_NUM`, translated/checked `VHOST_SET_VRING_ADDR`, and base
   cursors; create and connect per-queue kick/call eventfds. Validate queue size,
   alignment, complete ring bounds, direction, and unadvertised features.
5. Attach the same TAP FD to RX and TX using `VHOST_NET_SET_BACKEND`. Kernel and
   userspace queue consumers/TAP readers must be mutually exclusive.
6. Handle completions and errors independently of unrelated vCPU exits.
   Preserve `INT_USED_RING`, ACK, pending completion and IRQ semantics; do not
   assume a kernel call eventfd itself updates MMIO interrupt status.

Guest descriptors are untrusted while kernel workers operate. Verify Linux
vhost validation against malformed rings, cyclic/out-of-range chains, bad buffer
directions, and mutations; moving validation into the kernel must not create
cross-VM memory access or host failures. Any unavoidable semantic difference
needs an explicit decision, not benchmark-only acceptance.

### Notifications and isolation of the hypothesis

Maintain an unchanged userspace baseline. Also compare userspace and vhost with
the **same** functioning kick/completion adapter and IRQ configuration:
initially MMIO-exit kicks and Flint's direct high/low IRQ delivery, with a
blocking event dispatcher/IRQ bridge able to wake an idle vCPU. The userspace
control arm must receive the same necessary dispatcher/wakeup changes.

[Issue #3](https://github.com/cataggar/hearth/issues/3) may supply tested eventfd
dispatch/lifecycle primitives. Inspect their contract before reuse. It is not
a prerequisite to recording baseline, probing vhost or rejecting the idea.
If unavailable, implement a net-only adapter in the future experiment; do not
substitute periodic polling or a serial heartbeat for idle liveness. Optional
ioeventfd/irqfd comparisons are separate matched arms, not bundled vhost gains.

### Lifecycle and isolation invariants

- Pause acknowledges **vCPU plus backend quiescence**. Stop new kicks, detach
  both TAP queue backends, synchronously stop/flush kernel accesses using the
  pinned kernel's documented behavior, and fence completion dispatch before
  returning. A stopped vCPU alone is insufficient.
- Obtain kernel consumed-available cursors (`VHOST_GET_VRING_BASE`) and reconcile
  used-ring tracking after quiescence. That ioctl is not a getter for every
  userspace counter: establish an authoritative, validated used-cursor strategy.
  Do not serialize stale `Queue` fields or blindly trust guest-writable indices.
  If safe cursor handoff cannot be demonstrated, reject the backend.
- Snapshot preserves transport, features, MAC, queue progress and pending IRQ
  state consistently with frozen RAM. No host FD, worker identity, HVA or
  eventfd counter becomes restorable state. Prefer existing format v2; any
  necessary incompatible change requires an explicit compatibility decision.
- Resume re-arms queues/notifications with recovered cursors and performs a
  race-safe pending-work check. Restore reconstructs memory registration,
  kernel queues, TAP/eventfds and pending completions against **new** memory
  before guest execution; userspace↔vhost restore/fallback must be tested.
- Reset, queue disable/reconfiguration, setup failure and teardown stop/flush
  workers and dispatch before clearing rings, reusing FDs or unmapping RAM.
  No writes or interrupts from an old device generation may reach a new one.
  Fix restore cleanup ordering as part of future backend integration.
- Use only explicitly requested vhost/TUN devices inside the jail, approved
  node ownership/mode and required syscalls (notably `eventfd2`). Retain root
  drop, AF_UNIX-only sockets, clone/mprotect restrictions and cgroup limits.
  Do not pass privileged FDs around `close_range` or run the VMM as root to
  avoid confinement work. Verify kernel-worker accounting/resource isolation.
- TAP/kernel socket buffers and remote TCP state are not snapshot artifacts.
  State the pause/reconnect/retry policy; promise neither preservation of
  external connections nor exactly-once delivery across an external snapshot
  boundary. Guest ring completions must still be consistent and nonduplicated.

## Measurement and acceptance

Nested Azure KVM is mandatory for an adoption decision. Non-nested KVM is useful
but optional; disclose absence. Separate isolated guest↔host TAP traffic from
Azure external TAP traffic and from the vsock proxy negative control. Keep
Azure VF binding/driver state fixed across all arms.

For the unchanged baseline **and every runnable prototype**, retain actual
host Linux `perf stat`, `perf record` stacks and `perf report --stdio`; include
KVM entry/exit tracepoints or `perf kvm stat` where available. Include Flint,
host peers, TAP/network stack, softirq and vhost kernel workers in total host
CPU, with system-wide profiles and quiet-host controls. Process-only CPU
reduction is not success. Host PMU events may also be unavailable on Azure:
record that limitation and use software events/stacks and available tracepoints.

Required cases: small-packet RPC, TCP bulk both directions, idle-to-active
request latency, and 1/4/8 concurrent VMs when host capacity permits. Report
throughput/goodput, p50/p95/p99, loss/retransmissions/errors, total CPU seconds
per successful byte/request, context switches, KVM entries/exits and idle CPU.
Record requested/effective backend, unsuccessful/timeout cases and capacities
that could not be tested, not just successful samples.

Record commits, dirty diff, compiler/build flags and dependency pins, binary/
guest-image hashes, host/guest kernels, CPU/Azure SKU and outer/guest sizing,
CPU affinity and worker placement, MTU/offloads/negotiated features/queues,
topology, VF binding, commands/tool versions, warmup, sample counts, cache
conditions, background activity, variance and raw profiles. The plan supplies
the reproducible fixture and profiling recipe.

### Proposed numeric gates — freeze after baseline, before default selection

These are proposed thresholds, **not observed improvements**. Establish
baseline medians, paired-run variance and confidence intervals before
performance-driven implementation/default decisions; register final gates
before inspecting prototype comparisons.

| Gate | Proposed rule |
|------|---------------|
| Relevant benefit | For an established TAP use case on nested Azure: at least **10% lower total CPU/request or CPU/byte** with noninferior goodput, or **15% higher goodput** with no more than **5% higher total CPU/unit**. Include all affected work, not only Flint. |
| Noise qualification | Let `N` be baseline repeated-run relative dispersion (MAD/median) for the deciding metric. Benefit must exceed both the stated threshold and **2 × N**, with a paired 95% confidence interval excluding zero. Baseline repetitions/noise rules are frozen before prototype analysis. |
| Active regressions | No more than **5% lower goodput**, **5% higher CPU/unit** or **5% higher p95/p99** on other required active cases. RPC loss/data corruption/duplicate completion is zero; no increase in network error/loss rate or unstable retransmission pattern. |
| Idle/lifecycle regressions | Idle increase at most **0.01 logical CPU core/VM**; idle-to-active and pause/snapshot/restore p95/p99 increases at most **max(5% of baseline, 1 ms)**. No busy loop, new hangs, FD/worker leak or stale memory writes. |
| Evidence floor | At least **10 paired samples/arm/case across 3 fresh boots**, 10 s warmup and 60 s active windows; at least 100,000 successful small RPC observations/arm and 1,000 idle-wakeup observations/arm for tails. Report sample insufficiency and intervals instead of claiming p99 certainty. |

If baseline noise prevents resolving a regression gate, improve experimental
control or mark the outcome inconclusive; do not widen gates after seeing a
prototype. Any baseline-derived noise adjustment needs its numeric rationale
recorded before comparisons. Correctness and confinement gates cannot be
relaxed statistically.

Adopt at most an opt-in backend first. A default change additionally requires
relevant reproducible benefit, all correctness/lifecycle tests, unsupported
capability fallback, unchanged proxy/control behavior, and a documented
operational/maintenance decision. Roll back to userspace on regressions while
preserving supported snapshot portability; do not live-switch an active VM.

## Risks and open decisions

1. **Relevance:** are there current external/direct-Flint TAP users, or only a
   synthetic capability? Without an identified consumer, keep/reject by default.
2. **Kernel ABI/lifecycle:** which nested Azure kernel supports the unchanged
   modern header/features, synchronous detach and safe cursor recovery? Confirm
   against the exact kernel, including partial setup failures and CoW memory.
3. **Dispatcher reuse:** is #3's net event dispatcher available and proven under
   direct IRQ delivery? Otherwise isolate a minimal net-only adapter.
4. **Confinement/resources:** how are vhost workers charged/pinned on that kernel,
   and can the requested jailed UID attach the persistent TAP without retained
   network privileges? No broad permission workaround is acceptable.
5. **Cost:** kernel workers may merely move CPU, increase concurrent-VM memory/
   scheduling cost, pin demand-paged RAM or worsen lifecycle latency. Include
   these costs and rejection reasons even if bulk throughput improves.

Future host tools/device access are experiment prerequisites, not blockers to
completing this planning document. Use `unsupported`, `blocked` (with specific
missing prerequisite), `failed`, `inconclusive`, and `measured` distinctly in
future results. Planning completion is not experiment completion.
