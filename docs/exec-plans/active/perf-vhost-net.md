# Execution Plan: Evaluate Flint vhost-net

**Status**: Blocked — direct-ring S1 contract mismatch; adoption unqualified
**Last updated**: 2026-10-04
**Issue**: [#2](https://github.com/cataggar/hearth/issues/2)
**Spec**: [Capability-gated vhost-net Evaluation](../../product-specs/perf-vhost-net.md)

Planning is complete when this spec and plan are reviewed and persisted.
The 2026-10-04 execution uses the unchanged source in the dedicated
`copilot/perf-vhost-net-20261004` worktree. `benchmarks/vhost-net/` contains an
isolated diagnostic fixture and a sequence/payload-validating collector, not a
new SDK mode or a relevant product consumer. Actual results and exclusions are
recorded separately; recipes below are not themselves execution evidence.
Experiment completion requires the evidence/checklist at the end, including a
valid keep/reject outcome. The default remains userspace.

## Execution findings (2026-10-04)

See [actual results and exclusions](../../perf-results/vhost-net-20261004.md).
S0 found a direct CLI/API capability but no demonstrated current consumer;
the SDK still uses vsock. The diagnostic fixture is not product demand.
The parent reopened S1 on 2026-10-04: known exit-driven readiness failures do
not alone reject a net-only functioning A′ adapter/prototype. Investigate exact
kernel detach/flush, authoritative used-cursor error paths, pending IRQ handoff
and worker isolation with concrete source/API evidence before rejecting safety
or selecting a safe strict opt-in prototype. Reuse the exact separate shared
jail prerequisite when available; never count its repair as a speedup. Default
adoption remains unjustified without meaningful demand and qualified measurements.
The ensuing publisher-verified exact-kernel investigation and real non-root
UAPI probes are now recorded in the report's S1 section. The direct guest-ring
proposal fails required unadvertised-feature validation: kernel TX processes
INDIRECT despite VERSION_1-only SET_FEATURES. Pre-scanning mutable guest rings
cannot enforce the constraint. A mediated/shadow-ring implementation would
need a separately justified design; this task does not silently add one.

The unchanged safe binary boots a real VirtIO-MMIO/TAP guest on nested Azure.
Across three boots, all 120 requested network runs fail before completing their
60 s active windows (106 connection failures, 13 warmup failures, one active
timeout). Seven active RPC responses validate exact sequence/payload. Host-wide
`perf stat`, software call-stack recordings/reports and KVM traces were retained
for RPC, both bulk directions, wakeup attempts and idle. A native host-loopback
protocol check passes independently. Existing debug/safe unit tests pass
31/31 each; six focused fixture tests pass (five collector cases and launcher
cleanup on a post-spawn metadata failure).

The baseline cannot establish deciding CPU/unit noise or credible tails.
Pre-existing unrelated processes consume nearly all 16 host CPUs despite the
fleet lock. No such resources were killed or reconfigured. The device appeared
after parent provisioning: UID 1000 `VHOST_GET_FEATURES` succeeds. Initially no
backend was activated; later S1 probes do configure actual owner, memory table,
rings, eventfds and TAP outside Flint. These are characterization, not A′/B.
They verify checked framing, sampled detach/write fencing, file-private CoW
and worker join/FD cleanup. Naive used-index handoff is demonstrably wrong:
poisoned RAM seeds 30482 rather than expected 3; explicit trusted reseeding
works in the controlled case. Malformed TX advances avail without used and
signals ERR, requiring sticky fatal handling before any inferred handoff.
Production IRQ/ACK, traffic snapshot and enforced worker isolation are unrun.

Current disposition: **reject/defer backend adoption for lack of relevance;
full execution remains blocked**. A′, B, their before/after deltas, vhost
correctness, UDP, 4/8-VM concurrency, external Azure TAP and installed-image SDK
controls are not passed. Baseline installed VMM/kernel/rootfs assets are absent;
forward/transfer CONNECT support is also missing in the unchanged source.
Frozen gate rules and raw artifacts are referenced by the results document.
Do not claim a completed implementation or qualified performance comparison
while the mandatory execution remains missing. A relevant consumer is required
to reopen backend implementation/adoption, not to accept a negative evaluation;
the parent coordinator may separately qualify the retained S0 rejection.

After common provisioning was fully verified, a 16:27 UTC manifest freezes
tools, linked libraries, source/image hashes and device ACLs. UID-1000 actual
KVM creation and vhost GET_FEATURES close without an FD-count change. Two
additional TAP boots attempt four network windows; all four fail (three warmup,
one active) with zero validated active responses. Earlier samples remain
pre-boundary failure diagnostics, not a post-provisioning controlled baseline.
Post-provisioning profiler overload/timeouts and KVM frontend aborts are
retained. A separately identified lower-volume DWARF/direct-KVM retry completes
VM idle and matched no-VM captures; software reports lose zero samples, but
the no-VM software control still consumes 959.75 CPU s/60 s (~15.996 cores).
Corrected global `perf kvm -i ... stat report --stdio` syntax produces fourteen
offline reports without erasing original errors. Six fixture tests still pass.
No A/A deciding noise, product relevance, complete lifecycle/confinement proof
or performance delta is established by these retries. A fresh locked five-second
/proc/stat control independently verifies 15.986985 busy cores using
user+nice+system+irq+softirq, not system-wide task-clock. Two final S1 probe
repetitions each run nine cases/eight observation assertions, with no FD/thread
leak; accepting unadvertised INDIRECT is an observed contract failure, not a pass.

## Source-backed starting point

At `b07f73b26b8ae876928d9c515b94bba1e9945870`, Flint has a two-queue
userspace TAP backend with modern VirtIO-MMIO and 12-byte vnet headers
(`vmm/src/devices/virtio/net.zig`). Kicks exit through MMIO, IRQs use two
`setIrqLine()` calls, and TAP epoll polling occurs only after vCPU exits
(`vmm/src/main.zig`, `vmm/src/kvm/vm.zig`). There is no kernel queue backend or
eventfd dispatcher to select today.

The SDK configures block/vsock, not TAP (`src/sandbox/sandbox.ts`,
`src/vm/snapshot.ts`). `src/vm/api.ts::putNetworkInterface()` exists, but no
SDK boot path calls it. HTTP CONNECT internet access uses
`src/network/proxy.ts`; SDK forwarding and transfers also use vsock. Initial
relevance is therefore **direct-Flint opt-in TAP**, not general Hearth internet
performance. S0 must identify a real consumer or recommend rejection/deferment.

Snapshot/pause/reset currently have no kernel-worker fence. Restore recreates
devices before memory exists and its defers release restored memory before
device teardown. Adding vhost without changing that ordering is unsafe.
`Queue`'s userspace cursor fields must reflect kernel progress before saving.
Use the detailed findings/invariants in the spec as implementation acceptance,
not architecture diagrams' older TAP/NAT assumptions.

## Work graph and stage deliverables

Stages are work items, not promises to implement an optimization.

| Stage | True prerequisites | Work and exit evidence |
|-------|--------------------|------------------------|
| **S0 — Establish relevance** | None | Inventory direct CLI/API TAP callers and representative raw TCP/UDP/RPC uses; distinguish hypothetical demand from current consumers. Trace a candidate using guest route/device state and TAP byte/packet counters while a separate proxy control uses vsock. Record the product decision and supported audience. No new SDK TAP mode. |
| **S1 — Capability/lifecycle design** | None; coordinate with S0 | Inspect the exact Azure kernel vhost UAPI/implementation for features, header ownership, memory registration, worker quiescence/cursor recovery and resource accounting. Design strict/auto fallback diagnostics, bounded queue validation, narrow jail access, cleanup ownership and snapshot handoff. Inspect #3 primitives if available. Stop if no safe lifecycle exists; do not add a kernel fork. |
| **S2 — Fixed fixture and profiling harness** | S0's topology classification | Prepare pinned guest tools/image, isolated TAP namespace, raw RPC latency collector and run/manifest helpers. Establish worker/CPU accounting and available software/hardware/tracepoint events. Verify these against userspace; no vhost required. |
| **S3 — Baseline and preregister gates** | S2 | Collect the unchanged baseline's complete workload/perf matrix on nested Azure, including failed idle cases and raw stacks. Establish sample noise, numerical success/regression gates from the spec and freeze environment/measurement choices before prototype results. Baseline profiles are required before performance-driven backend implementation decisions. |
| **S4 — Common notification control arm** | S1 + S3 | Reuse proven #3 code or implement a minimal net-only blocking dispatcher. Keep MMIO-exit kicks and direct high/low IRQ mode fixed. Add a userspace control arm with the same dispatcher/idle wakeup used by vhost. Prove completion status/ACK and pause/reset generation fences. Profile this prototype separately. |
| **S5a — Kernel setup and queues** | S1 + S3 + S4 interface contract | Implement the opt-in backend, memory table, negotiated features/header sizes, queue addresses/base cursors, kick/call eventfds and TAP binding with deterministic unwind. Workers may not be enabled before S5b fences are integrated. |
| **S5b — Lifecycle/confinement integration** | S1 + S3 + S4 interface contract | Add pause/resume, queue disable/reset, snapshot cursor handoff, restore reconstruction, cleanup ordering and jail device/syscall policy. Can proceed independently of S5a's data path using mocks; integrate before traffic. |
| **S6 — Correctness acceptance** | S4 + integrated S5a/S5b | Execute focused unit and real nested-KVM network/lifecycle/isolation tests. Test designs, malformed-queue fixtures and capability mocks may be prepared independently during S1/S2. No performance/default decision with failing correctness. |
| **S7 — Matched performance comparison** | S3 + S6 | Profile every runnable arm with identical features/topology/notifications/IRQs. Repeat required cases on nested Azure; optional non-nested runs explicitly labeled. Optional #3 factorial comparisons require those individual primitives to pass correctness, not issue closure. |
| **S8 — Keep/reject and rollback decision** | S0 + S3 + S7 for runnable prototypes | Apply frozen gates, report complexity/correctness/resource costs and relevant benefits. An earlier rejection may instead cite S0 (no consumer) or S1 (unsupported/unsafe design), retaining S3 baseline evidence and explicitly labeling unrun prototype comparisons. Update results and move the implementation plan to completed only after its recorded disposition. |

S0/S1 and fixture-independent correctness design are independent workstreams.
S5a/S5b share a contract, not an implied sequential dependency. Baseline and
documentation can finish without #3. If hardware/tools prevent S3, report an
experiment prerequisite blockage and retain available evidence; do not call it
successful measurement or a blocker to this planning task.

## Proposed future file surfaces

These are proposed edits only; not files to change during planning.

| Path | Bounded purpose |
|------|-----------------|
| `vmm/src/devices/virtio/net.zig` | Retain userspace implementation/TAP/MAC; own explicit selected backend and mutually exclusive consumers. Preserve the existing advertised feature set. |
| **New** `vmm/src/devices/virtio/vhost_net.zig` | Linux vhost owner/memory/vring/TAP setup, capability errors, quiesce/rearm, cursor handoff and exhaustive FD cleanup. Use a small Linux UAPI binding; if translated headers are needed, add a scoped `vhost_abi.h` and import in `vmm/build.zig`, not a new unpinned dependency. |
| `vmm/src/devices/virtio/mmio.zig`, `queue.zig` | Activation/configuration validation hooks, common interrupt status/ACK synchronization, reset/queue-disable hooks and backend-neutral snapshot progress. Never poll a vhost-owned ring in userspace. |
| `vmm/src/main.zig` | Proposed `--net-backend userspace\|vhost\|auto` selector, common net dispatcher/IRQ bridge, pause acknowledgement including workers, clean resume and memory-after-backend teardown ordering in both restore variants. Track FDs/devices by generation. |
| `vmm/src/api.zig` | Preboot backend option/diagnostics and postboot lifecycle error propagation. Declare permissions before jail setup; reject undeclared privileged backend requests. |
| `vmm/src/memory.zig`, `snapshot.zig` | Memory-table inputs and lifetime, stopped-worker assertion at snapshot, safe cursor persistence and restored-memory activation. Keep MAP_PRIVATE and existing v2 format if possible. |
| `vmm/src/jail.zig`, `seccomp.zig` | Add only requested vhost node, restricted UID ownership/mode and `eventfd2`. Existing ioctl allowance is broad: do not describe it as an existing per-request allowlist or widen it further. Preserve all current argument-filtered restrictions. |
| `vmm/src/kvm/vm.zig`, `kvm/abi.h` | Only if separately testing/reusing #3's KVM eventfd capabilities. Not needed to hide MMIO exits in the first vhost comparison. |
| `vmm/src/tests.zig`, `integration_tests.zig`, `vmm/build.zig` | Focused net validation/failure/lifecycle coverage and an explicit project-relative kernel override for reproducible network integration fixtures. Retain existing tests. |
| **New** `benchmarks/vhost-net/` | Future `run.sh`, `tcp-rr.py`, manifest/report helpers and fixture recipe. Explicitly selects/evidences backend and notification modes; retains raw samples/profiles outside committed source under `.perf/vhost-net/`. This harness does not currently exist. |
| `src/sandbox/sandbox.test.ts` | Regression-only execution of installed-image proxy/checkpoint tests where supported; no TAP/SDK API extension. Preserve baseline blocked SDK coverage in reporting. |

`src/sandbox/sandbox.ts`, `src/network/proxy.ts`, `src/sandbox/types.ts`, and
`src/vm/snapshot.ts` are applicability/control-plane references, not expected
implementation targets. Do not reroute those paths through net for this issue.

## Prototype implementation contract

### Ownership, activation, and diagnostics

1. Probe the requested kernel ABI under the intended UID/jail. Record
   `/dev/vhost-net` absence/permission, accepted features and each setup errno.
   Module loading is optional provisioning, **never** a completed backend.
2. Create close-on-exec eventfds/vhost FD; `VHOST_SET_OWNER`, feature negotiation
   (`VHOST_GET_FEATURES`/`VHOST_SET_FEATURES`) and `VHOST_SET_MEM_TABLE` use the
   current GPA-0 memory mapping. Distinguish MAC/status handled in MMIO from
   kernel-consumed negotiated features and
   `VHOST_NET_F_VIRTIO_NET_HDR`. Preserve VERSION_1 and 12-byte TAP/header behavior;
   fallback rather than enabling mergeable buffers or offloads.
3. Translate and bounds/alignment-check complete guest rings before
   `VHOST_SET_VRING_NUM/ADDR/BASE/KICK/CALL` and `VHOST_NET_SET_BACKEND`.
   Validate two queues, power-of-two size ≤256 and negotiated/readiness status.
   Kernel ring processing replaces, not duplicates, `processTx()/pollRx()`.
4. Start only after both queues/features are valid and lifecycle fences exist.
   MMIO queue notify values must map to RX/TX kicks with correct write width;
   invalid values must not hit another queue. Completion handling drains call
   eventfds, sets MMIO used-ring status and delivers the unchanged direct IRQ.
   Calls are not a replacement for transport ACK semantics.
5. `userspace` is default, strict `vhost` reports failure, opt-in `auto` unwinds
   partial setup and reports userspace plus reason before enabling guest work.
   Guest corruption and uncertain live ownership are failures, not capability
   fallback. Runtime re-selection requires stop/fence/cursor handoff or VM reset.

### Independent service and #3 coordination

Define one contract for kick consumption, completions, blocking wakeup,
interrupt/ACK state and stop/rearm. Inspect #3's concrete implementation and
tests before reuse; do not depend on its unmeasured performance conclusions.
If it is not ready, scope S4 to net only: blocked epoll dispatcher, MMIO exit
writing a selected kick, userspace TAP readiness, and a call-eventfd bridge
using the existing two IRQ-line ioctls. Synchronize MMIO reads/ACKs with the
dispatcher, and signal a paused/blocked vCPU without a periodic timer.

Use these arms:

| Arm | Queue backend | Kicks / IRQ | Attribution |
|-----|---------------|-------------|-------------|
| **A** | Current userspace | Current synchronous MMIO / direct IRQ; current exit-driven RX | Unchanged baseline; record idle shortcomings, do not mask them. |
| **A′** | Userspace | Common functioning dispatcher, MMIO-exit kick / direct IRQ bridge | Cost/benefit of necessary dispatcher/wakeup changes versus A. |
| **B** | vhost-net | Same common dispatcher, MMIO-exit kick / direct IRQ bridge | Backend-only comparison versus A′. |
| **Optional A′/B variants** | Each backend | ioeventfd only, irqfd only, then both, where #3 proves support | Matched notification factorials; never B+acceleration versus A without separating effects. |

Keep affinity, IRQ routing/status/ACK policy and event-loop behavior fixed for
each A′/B pair. Kernel-internal batching remains a backend property but must be
recorded. Do not use extra guest features, IRQ coalescing knobs, serial
heartbeats, spin loops or arbitrary timer wakes to make one arm look better.

### Worker fences and snapshot boundary

Confirm the exact kernel's synchronous detach/stop guarantees rather than
assuming an ioctl return stops all access. Required sequence:

- Stop guest execution and new producer/dispatcher actions; detach both queue
  TAP backends, stop/flush kernel vrings and fence callbacks.
- Use `VHOST_GET_VRING_BASE` for consumed available cursors. It does **not**
  return `next_used_idx`; prove how authoritative used progress is recovered
  without trusting guest mutations. Capture pending completions/interrupt
  status with memory frozen, then serialize existing transport/queue state.
- On resume, restore vring bases, attach TAP, rearm events and check pending
  work without a lost-wakeup window; acknowledge API success only after safe
  transition. On snapshot failure remain safely paused or safely rearm.
- On restore, create resource owners inactive, load/validate MAP_PRIVATE memory
  and transport state, register the new HVA, recover queues and arm backend
  before guest execution. Test both backend choices independently of which
  produced the snapshot; never serialize FDs/HVAs/workers.
- Queue disable/reset/teardown and all error unwinds detach/flush/join/unregister
  before clearing state, reusing FDs or unmapping RAM. Correct restore LIFO
  cleanup ordering and load-error cleanup; stale event generations cannot reach
  newly created devices.

Freeze guest rings consistently, not external socket state. Tests must separate
legitimate remote reconnection/retry and packets left in host TAP buffers from
duplicate guest completions, lost committed ring work or post-pause writes.
Unsafe cursor/quiescence behavior is a reject outcome, not a reason to skip
snapshot acceptance.

## Reproducible measurement recipe

Commands below are **future execution recipes**, not commands run for this
planning task. Use a dedicated quiet Linux test host; avoid measuring shared
users' workloads. All fixtures/artifacts stay project-relative, not in temporary
directories. Prepare tools only for the experiment; retain their versions/hashes.

### 1. Pin environment and probe perf

From the repository root, for each arm/repetition:

```bash
RUN=.perf/vhost-net/2026-10-04-A-01
mkdir -p "$RUN"
git rev-parse HEAD > "$RUN/commit.txt"
git --no-pager diff > "$RUN/source.diff"
git --no-pager status --short > "$RUN/status.txt"
zig version > "$RUN/zig-version.txt"
cp vmm/build.zig.zon agent/build.zig.zon package-lock.json "$RUN/"
uname -a > "$RUN/host-kernel.txt"
lscpu > "$RUN/cpu.txt"
id > "$RUN/identity.txt"
perf --version > "$RUN/perf-version.txt"
perf list > "$RUN/perf-events.txt"
sudo perf stat -a -e task-clock,context-switches,cpu-migrations,page-faults \
  -o "$RUN/software-probe.txt" -- sleep 1
sudo perf stat -a -e cycles,instructions -o "$RUN/hardware-probe.txt" -- sleep 1
sudo perf stat -a -e kvm:kvm_entry,kvm:kvm_exit \
  -o "$RUN/kvm-probe.txt" -- sleep 1
```

Retain stderr/exit status from probes. If hardware events fail, explicitly label
them unavailable and continue with software events. If KVM tracepoints fail,
try host `perf kvm stat` and retain the reason if neither is accessible. Do not
change host security settings globally or call missing counts zero. Flint hides
guest PMU counters, so guest hardware cycles are not an alternative. Azure
“host CPU” means the Linux outer-VM host of Flint, not invisible physical Azure
hypervisor CPU.

Use Zig **0.17.0**, target `x86_64-linux`, `-Doptimize=safe` for all measured
Flint builds. Preserve manifests' translate-c commit
`62d06a5d3e93c82727544e8113e4762a315ca0ed` and package hash; record unchanged
transitive Aro pin/hash as in the toolchain spec. Record source revisions for A,
A′ and B separately, toolchain binary hash, built VMM hash, guest-image/tool
hashes, and all commands:

```bash
(cd vmm && zig build -Dtarget=x86_64-linux -Doptimize=safe)
sha256sum vmm/zig-out/bin/flint > "$RUN/flint.sha256"
```

Manually record Azure SKU, outer vCPU/RAM sizing, guest 1 vCPU/512 MiB sizing
(or an explicitly frozen alternative), CPU model/governor/affinity, host and
guest kernels, network namespace/addresses/routes, MTU, queue size/features,
TAP/guest offloads, kernel worker placement, cgroup accounting and background
load. Capture `ip -d link`, `ethtool -k`, `ethtool -i`, `lspci -nnk` and Azure
VF binding state before/after each group of comparisons. **Do not** rebind VF,
change accelerated-networking state or vary external drivers between arms.

### 2. Isolated TAP fixture, with no Azure external dependency

S2 must prepare a pinned initramfs containing static BusyBox (including `ip`,
`tcpsvd`, `cat`) and a pinned static `iperf3`, or the exact equivalent dependencies
in a copied, hashed rootfs. Validate kernel VirtIO-MMIO/net support and guest
interface discovery; do not assume the existing CI heartbeat guest tests net.
The guest init mounts proc/sysfs/devtmpfs, sets `eth0` to `192.0.2.2/30`,
MTU 1500, brings up loopback, starts:

```sh
/bin/busybox tcpsvd 192.0.2.2 7000 /bin/busybox cat >/dev/null 2>&1 &
/bin/iperf3 -s -B 192.0.2.2 -p 5201 >/dev/null 2>&1 &
echo PERF_TAP_READY
wait
```

The echo endpoint returns the exact bytes, enabling sequence/payload checks
without Python in the guest. There is **no periodic serial heartbeat**,
per-interval server console output, or default route. Log/hash the complete
init script, tool provenance, linker
dependencies, archive and guest feature/offload checks. Package the prepared
tree using the existing integration fixture's newc/gzip approach:

```bash
(cd "$RUN/guest" && find . -print | LC_ALL=C sort | bsdcpio -o -H newc) \
  | gzip -n > "$RUN/initrd.cpio.gz"
sha256sum "$RUN/initrd.cpio.gz" > "$RUN/guest.sha256"
```

Use the same guest kernel/archive for every arm. One available pinned kernel
source is the existing CI's 5.10.245 release; if used, verify:

```bash
curl --fail --location \
  https://github.com/joshuaisaact/hearth/releases/download/kernel-5.10.245/bzImage \
  --output "$RUN/bzImage"
echo "4da539807474d189f1a15852046994e78d430a194c2e78b9255ae880069c7208  $RUN/bzImage" \
  | sha256sum --check
```

Create only an experiment-owned network namespace and persistent TAP:

```bash
ROOT=$(pwd)
RUN_USER=$(id -un)
NS=hearth-perf-vhost2
TAP=hn2tap0
sudo ip netns add "$NS"
sudo ip -n "$NS" link set lo up
sudo ip netns exec "$NS" ip tuntap add dev "$TAP" mode tap \
  user "$RUN_USER" vnet_hdr
sudo ip -n "$NS" addr add 192.0.2.1/30 dev "$TAP"
sudo ip -n "$NS" link set "$TAP" mtu 1500 up
```

Keep this namespace away from host uplinks/bridges/NAT. Record and disable
supported offloads identically on TAP/guest; retain errors for unsupported
ethtool controls, never enable a feature for just one arm. The TAP's owner
allows the non-root VMM to attach without giving it general network privileges.
Allocate available `VMM_CPUS` and disjoint `CLIENT_CPUS`; also record where
vhost/softirq work actually runs, not just Flint's affinity.

Start the **current** A binary in a separate terminal, retain its PID/TIDs and
logs, then wait for the API socket:

```bash
(
  cd "$RUN"
  sudo ip netns exec "$NS" runuser -u "$RUN_USER" -- taskset -c "$VMM_CPUS" \
    "$ROOT/vmm/zig-out/bin/flint" --api-sock "$ROOT/$RUN/flint.sock"
)
```

Configure through the existing API (these routes exist now):

```bash
SOCK="$ROOT/$RUN/flint.sock"
curl --fail --silent --show-error --unix-socket "$SOCK" -X PUT \
  -H 'Content-Type: application/json' -d '{"vcpu_count":1,"mem_size_mib":512}' \
  http://localhost/machine-config
curl --fail --silent --show-error --unix-socket "$SOCK" -X PUT \
  -H 'Content-Type: application/json' \
  -d "{\"kernel_image_path\":\"$ROOT/$RUN/bzImage\",\"initrd_path\":\"$ROOT/$RUN/initrd.cpio.gz\",\"boot_args\":\"console=ttyS0 reboot=k panic=1 pci=off\"}" \
  http://localhost/boot-source
curl --fail --silent --show-error --unix-socket "$SOCK" -X PUT \
  -H 'Content-Type: application/json' \
  -d "{\"iface_id\":\"eth0\",\"host_dev_name\":\"$TAP\"}" \
  http://localhost/network-interfaces/eth0
curl --fail --silent --show-error --unix-socket "$SOCK" -X PUT \
  -H 'Content-Type: application/json' -d '{"action_type":"InstanceStart"}' \
  http://localhost/actions
```

Require actual guest readiness and bidirectional packets before samples.
Current `guest_mac` API input is not applied by the backend; keep the TAP name/
derived MAC and MMIO slot order fixed. No disk/vsock is needed for this isolated
fixture. For future A′/B, use only the implemented/validated selector, retain
effective-mode diagnostics, and keep this setup unchanged.

The current API/CLI can also exercise the baseline lifecycle with the peer's
sequence traffic active. Snapshot basenames below are relative to the VMM's
artifact-directory cwd, as required by API path validation:

```bash
curl --fail --silent --show-error --unix-socket "$SOCK" -X PATCH \
  -H 'Content-Type: application/json' -d '{"state":"Paused"}' http://localhost/vm
curl --fail --silent --show-error --unix-socket "$SOCK" -X PUT \
  -H 'Content-Type: application/json' \
  -d '{"snapshot_path":"traffic.vmstate","mem_file_path":"traffic.mem"}' \
  http://localhost/snapshot/create
curl --fail --silent --show-error --unix-socket "$SOCK" -X PATCH \
  -H 'Content-Type: application/json' -d '{"state":"Resumed"}' http://localhost/vm
```

Validate original resume, then stop the **recorded original VMM PID** and its
traffic clients before restoring, never two readers of the same TAP. With the
same TAP/MMIO slot order, start a new process and peer connection:

```bash
(
  cd "$RUN"
  sudo ip netns exec "$NS" runuser -u "$RUN_USER" -- taskset -c "$VMM_CPUS" \
    "$ROOT/vmm/zig-out/bin/flint" --restore --vmstate-path traffic.vmstate \
    --mem-path traffic.mem --tap "$TAP" --api-sock "$ROOT/$RUN/restored.sock"
)
```

S6 adds explicit traffic sequence/cursor/canary assertions and both backend
restore choices; these baseline commands alone do not establish vhost safety.
Record pause, snapshot, resume and restored-first-response timestamps, with
the declared reconnect/retry policy and paused-memory stability checks.

### 3. Workload commands and collector contract

In the namespace, run host-to-guest bulk and reverse guest-to-host bulk:

```bash
sudo ip netns exec "$NS" runuser -u "$RUN_USER" -- taskset -c "$CLIENT_CPUS" \
  iperf3 -c 192.0.2.2 -p 5201 -P 1 -O 10 -t 60 -J > "$RUN/h2g.json"
sudo ip netns exec "$NS" runuser -u "$RUN_USER" -- taskset -c "$CLIENT_CPUS" \
  iperf3 -c 192.0.2.2 -p 5201 -P 1 -O 10 -t 60 -R -J > "$RUN/g2h.json"
sudo ip netns exec "$NS" runuser -u "$RUN_USER" -- taskset -c "$CLIENT_CPUS" \
  iperf3 -c 192.0.2.2 -p 5201 -u -l 64 -b "$UDP_RATE" -O 10 -t 60 -J \
  > "$RUN/udp.json"
```

Freeze `UDP_RATE` from baseline loss-free capacity, not from the faster arm;
record both directions, loss/out-of-order/errors and TCP retransmissions.
Capture `ip -s link`, guest interface counters, `/proc/net/softnet_stat` and
`nstat` before/after. Keep packets/bytes separate from payload goodput.

S2's **future** `benchmarks/vhost-net/tcp-rr.py` must use fixed 64-byte framed
TCP requests/responses with sequence/payload validation, handle partial reads,
use monotonic timestamps, warm up, retain every measured RTT and count
timeouts/errors. No disk logging in the timed request loop. A raw TCP connection
is used, not HTTP CONNECT/vsock. Required invocation contract:

```bash
sudo ip netns exec "$NS" runuser -u "$RUN_USER" -- taskset -c "$CLIENT_CPUS" \
  python3 benchmarks/vhost-net/tcp-rr.py --host 192.0.2.2 --port 7000 \
  --bytes 64 --connections 1 --warmup-seconds 10 --seconds 60 \
  --output "$RUN/rpc"
sudo ip netns exec "$NS" runuser -u "$RUN_USER" -- taskset -c "$CLIENT_CPUS" \
  python3 benchmarks/vhost-net/tcp-rr.py --host 192.0.2.2 --port 7000 \
  --bytes 64 --connections 1 --idle-seconds 1 --samples 1000 \
  --output "$RUN/idle-wakeup"
```

Record client CPU/saturation; if Python limits rate, replace it with a pinned
native collector **before** freezing baseline and repeat baseline, not just B.
For RPC add fixed offered-load tests at 50%/80% of baseline capacity so tail
latencies are compared at equal load as well as equal connections.

Run 1/4/8 VMs with separate TAPs/subnets and synchronized host clients. Freeze
per-VM memory/vCPU/affinity and load; report aggregate and per-VM fairness/tails.
Disclose unavailable capacity instead of silently lowering one arm's concurrency.
Measure 60 s truly idle windows separately and cold first request after 1 s
quiescence without artificial guest activity. Preserve any baseline wakeup
timeout as a result; do not invent a p99 for timed-out requests.

### 4. Actual host-wide perf for baseline and every prototype

Repeat the **same** active command under both profiling passes; retain command,
exit status, timestamps and tool output. For example, host-to-guest bulk:

```bash
cat /proc/stat > "$RUN/proc-stat.begin"
sudo perf stat -a -x, \
  -e task-clock,context-switches,cpu-migrations,page-faults \
  -o "$RUN/h2g.stat.csv" -- \
  sudo ip netns exec "$NS" runuser -u "$RUN_USER" -- taskset -c "$CLIENT_CPUS" \
  iperf3 -c 192.0.2.2 -p 5201 -P 1 -O 10 -t 60 -J \
  > "$RUN/h2g-stat-workload.json"
cat /proc/stat > "$RUN/proc-stat.end"
sudo perf record -a -e cpu-clock -F 199 -g --call-graph dwarf \
  -o "$RUN/h2g.perf.data" -- \
  sudo ip netns exec "$NS" runuser -u "$RUN_USER" -- taskset -c "$CLIENT_CPUS" \
  iperf3 -c 192.0.2.2 -p 5201 -P 1 -O 10 -t 60 -J \
  > "$RUN/h2g-record-workload.json"
sudo perf report --stdio -i "$RUN/h2g.perf.data" \
  --sort comm,dso,symbol > "$RUN/h2g.perf-report.txt"
sudo perf script -i "$RUN/h2g.perf.data" --show-lost-events \
  > "$RUN/h2g.perf-stacks.txt"
```

When available, add `cycles,instructions` and `kvm:kvm_entry,kvm:kvm_exit` to
stat events, then separately record/report KVM tracepoint stacks or collect
`perf kvm stat`. Repeat for reverse bulk, RPC, UDP, idle, wakeup and concurrent
VMs in A, A′, B and each optional notification variant. Check lost samples,
symbol/unwind quality and profiler overhead. Keep unprofiled paired latency/
throughput repetitions separate; never compare a profiled arm to an unprofiled
one. An unavailable optional hardware event is not permission to omit software
stat/record/report.

Account across **all CPUs doing the work**, not only Flint's PID or cpuset.
Retain process/TID/worker inventories (`ps -eLo pid,tid,psr,comm,cgroup`), cgroup
`cpu.stat`, softirq deltas and system-wide stacks identifying Flint/KVM, TAP/
network processing, softirq/ksoftirqd and vhost workers. Host peer/client CPU
is included and separately attributed; moving work into kernel threads is not
saving it.

Compute visible-host busy CPU seconds from `/proc/stat` deltas
`user + nice + system + irq + softirq` divided by `getconf CLK_TCK`, with Linux
guest time already included in user/nice (do not add it twice). Preserve raw
totals and matched quiet-host idle controls. Do not assume system-wide
task-clock equals non-idle CPU without checking its semantics. Report total
CPU/successful payload byte and CPU/completed validated request, alongside
Flint-only diagnostic CPU, context switches and KVM exits/request or byte.
Use measured-window denominators and include/reconcile the 10 s warmup in
perf counters; S2 must mark boundaries so active-window and whole-command
metrics are not mixed.

### 5. External path and repetition discipline

External TAP testing is a **separate** fixture: deliberate opt-in route/NAT in
an experiment-owned namespace to a controlled Azure peer running the same
tools. Record its topology, peer placement, routing/NAT, NIC/MTU/offloads,
bandwidth limits and VF binding. Keep state fixed and distinguish Azure path/
peer bottlenecks from queue cost. No broad host firewall edits. Never blend
external results with isolated TAP results.

Use a local controlled HTTP CONNECT target through
`Sandbox.enableInternet()` as a no-TAP negative/control-plane regression case
where the baseline supports it. Label baseline SDK forwarding/tar CONNECT
coverage blocked as documented in `completed/zig-017-ci.md`; do not use them
as fabricated TAP workloads or claim fixing them here.

For each mandatory case/arm: 10 paired repetitions over ≥3 fresh boots,
10 s warmup/60 s active windows, ≥100,000 RPC observations and ≥1,000 idle
wakeups/arm. Alternate/randomize A′/B order (retain seed/order), include A
repetitions, and report median, p50/p95/p99, MAD/stddev, paired confidence
intervals, counts/timeouts and variance. Freeze warm versus freshly restored
CoW-memory cache conditions separately. Never globally drop caches on a shared
host. Repeat lifecycle latency under traffic and measure RSS/pinning effects.
Retain raw profiles/samples/manifests with hashes in the experiment artifacts.

Cleanup only experiment-owned resources: stop specific recorded VMM/client
PIDs, join workers, remove the experiment TAPs/network namespace and fixture
files as appropriate. Preserve raw evidence for review. Never kill by process
name, delete shared SDK base snapshots or alter external NIC driver binding.

## Correctness tests and validation commands

Existing evidence is limited: `tests.zig` covers memory bounds/queue snapshot
round-trip, not RX/TX; `integration_tests.zig` boots a serial-heartbeat guest
without TAP. `sandbox.test.ts` uses vsock and skips when `/dev/kvm` is absent.
Do not count those as kernel networking acceptance.

| Focused test | Required assertion |
|--------------|--------------------|
| RX/TX and framing | Exact payload/sequence in both directions, partial/chained descriptors, small/MTU-sized packets, used lengths, 12-byte headers, no unsupported offloads/features. Backpressure/replenishment does not lose committed completions or corrupt data. |
| Queue validation | Invalid size/zero/oversize/alignment/overflow/out-of-RAM rings, bad notify width/index, cyclic/out-of-range chains, bad RX/TX directions, unadvertised indirect/mergeable features and queue memory mutations fail safely. No host crash, out-of-map access or neighbor-VM effects. |
| Activation/reset/IRQ | No consumption before validated negotiated `DRIVER_OK`; queue disable/reconfigure and status-zero reset fence workers. ACK/repeated call-eventfd races preserve pending status without duplicate/lost completions or interrupt storms. |
| Idle wakeup | After true guest idle/blocking KVM_RUN, host RX and guest TX complete without an unrelated serial/timer stimulus; first-response tails and idle CPU are recorded. Test descriptor replenishment plus readiness races. |
| Capability/failure | Missing/denied device, missing features, header mismatch and injected failure at every setup step produce strict errors or explained `auto` fallback before activation. Check FD counts/worker cleanup and equivalent userspace traffic. |
| Pause/snapshot/restore under traffic | Bidirectional sequence/checksum traffic; memory/ring hashes stable throughout pause; consistent cursors and IRQs; original resume and restored traffic continue/reconnect according to policy. Cover userspace→vhost, vhost→userspace, vhost→vhost, repeated snapshots and restore without vhost. CoW snapshot files remain unchanged. |
| Reset/teardown and isolation | Repeated attach/reset/stop/restore cycles, shutdown and setup failure return FDs/workers to baseline. Poison/canary old memory before reuse: no late writes/IRQs. Independent VMs/TAP namespaces cannot access each other's packets or memory. Jailless and production jailed UID paths preserve confinement/cgroup behavior. |
| SDK negative controls | Installed-image proxy/control and checkpoint semantics are no worse where runnable. Report pre-existing CONNECT/installed-image gaps explicitly, never “passed by skip.” |

Future targeted commands, following S6 additions:

```bash
(cd vmm && zig build test -Dtarget=x86_64-linux -Doptimize=debug)
(cd vmm && zig build test -Dtarget=x86_64-linux -Doptimize=safe)
(cd vmm && zig build integration-test-build -Dtarget=x86_64-linux -Doptimize=safe)
```

The current integration fixture hardcodes a kernel in a host temporary path;
S6 must introduce a project-relative configured kernel input before prescribing
the runnable network suite. Then run the existing `integration-test` target with
that documented override, provisioned TAP/vhost prerequisites and a required
executed-test summary. No all-skipped suite counts as success. Run debug/safe
net correctness; use safe builds for performance.

For supported installed images, select only related SDK controls:

```bash
npx vitest run src/sandbox/sandbox.test.ts \
  -t 'internet|snapshot and restore|checkpoint|clean up after destroy'
```

Retain prerequisite diagnoses, actual executed/failed/skipped counts, kernel/
tool versions and logs. Tools/images unavailable are `blocked` prerequisites;
unavailable optional vhost capability is `unsupported`; data/correctness failure
is `failed`. Neither is measured success. These recipes were unrun in the
original planning task; the execution findings above distinguish actual
baseline/fixture validation from unrun vhost acceptance.

## Decision, risks and rollback

Apply the spec's **proposed** 10% CPU/unit or 15% goodput benefit gate, 5% active
regression bounds, idle ≤0.01-core/VM increase and lifecycle/wakeup
≤max(5%, 1 ms) bounds. Freeze numeric baseline-derived gates before B analysis;
require benefit above 2× baseline MAD/median and a paired 95% interval excluding
zero. If noise obscures gates, improve controls/repeat or report inconclusive.
Document any pre-comparison baseline noise adjustment, never retrofit it to
pass B. Correctness has zero tolerance for corruption/stale writes/leaks.

Open decisions for S0/S1: actual TAP consumer; exact kernel worker flush/cursor
authority; header ownership and unchanged negotiated VERSION_1 support; jail
selection before preboot configuration; resource accounting/cgroup confinement;
#3 primitive availability; snapshot format compatibility if v2 is insufficient.
Record resolutions before activation/default selection.

Bulk improvement alone may lose to CPU shifted into vhost/softirq, worse
small RPC tails, worker proliferation under concurrent VMs or demand-paged RAM
pinning. Those are reject/inconclusive outcomes, not reasons to omit cases.
Missing non-nested hardware is an explicit optional comparison gap; missing
nested Azure evidence prohibits adoption but does not block documentation.

Possible dispositions: **reject/defer** (no relevance, unsupported/unsafe, no
benefit), **retain experimental opt-in** (relevant gated benefit, limited
operational audience), or **propose default** only after all spec gates and an
explicit maintenance decision. No default change merely because a module loads.
Rollback selects userspace for new/restarted VMs and restores compatible
snapshots through a proven quiesced handoff; do not live-switch active workers.

## Completion checklist

- [x] Write the product spec first and this issue-linked executable plan.
- [x] Ground applicability, lifecycle and coverage gaps in existing source.
- [x] Identify a real TAP workload or record no-current-consumer rejection.
- [ ] Retain unchanged nested-Azure baseline stat/record/report, KVM availability,
  full manifest/raw samples and frozen numerical/noise gates.
- [ ] Resolve kernel/header/feature/cursor/jail and dispatcher contracts.
- [ ] If prototyped, implement actual kernel queues/eventfds/TAP binding plus
  worker fences, tested fallback and reconstructed restored-memory state.
- [ ] Execute RX/TX, validation, reset, idle, failure, traffic-snapshot and
  isolation tests with explicit unsupported/blocked coverage.
- [ ] Retain host-wide profiles for each runnable control/prototype, fixed-mode
  comparisons, concurrency/idle/lifecycle results and optional-host disclosure.
- [ ] Publish reproducible keep/reject evidence, limitations and rollback;
  leave default unchanged without relevant benefit and every acceptance gate.
- [ ] Update experiment status/results and move the finished execution plan to
  completed; preserve unresolved baseline SDK coverage rather than claiming it.
