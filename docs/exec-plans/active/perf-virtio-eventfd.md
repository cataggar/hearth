# Execution Plan: Profile VirtIO ioeventfd/irqfd

**Status**: Blocked after partial W0; W1–W8 not executed

**Date**: 2026-10-04

**Issue**: [#3](https://github.com/cataggar/hearth/issues/3)

**Spec**: [VirtIO eventfd experiment](../../product-specs/perf-virtio-eventfd.md)

## Outcome and boundaries

Produce a reproducible keep/reject decision for queue-kick ioeventfd and
completion-interrupt irqfd, independently and combined, on **nested Azure
KVM**. Preserve correctness, snapshot/lifecycle semantics and isolation.
W0 verification and baseline collection have produced reproducible failures
and profiles. No accelerated mode or
default decision has occurred. Completing W0 does not complete this experiment.

### Current execution

The dedicated branch is `copilot/perf-virtio-eventfd-20261004`, based on the
docs-only `b06ec0a`; VMM and agent sources initially match `b07f73b`.
All compilation, VM execution, profiling and fixture preparation use the shared
exclusive `/d/hearth/.perf/fleet/host.lock`, bounded commands and private
project-relative artifacts under `.perf/eventfd/`. Provisioning and profiling
tools added during W0 are not C00 servicing changes or performance gains.

The [actual W0 results](../../../benchmarks/virtio-eventfd/results/20261004/README.md)
record all failures, tests, software profiles and raw evidence. Native
no-heartbeat liveness fails; eight 64 KiB slow-reader messages stall even with
the diagnostic heartbeat. Private jail ownership and missing ordinary
readiness syscalls were corrected and actual enforced boot/connect verified
separately. Earlier CPU8/client0 samples share an SMT core and remain
supplementary; repeated CPU8/client1 L0 profiles are retained separately.
No numeric gates are frozen, and no controlled candidate exists.

**Hold / not eligible for performance merge.** Required remaining work is the
baseline backpressure/credit correctness prerequisite, W1–W6 ownership,
validation, IRQ/lifecycle and controlled modes, plus TAP/concurrency/active-I/O
and cross-mode restore coverage and W3/W7 matched gates/matrix. The plan stays
active/blocked, not completed. Existing benchmark commands below that describe
future selectors/matrix runners remain proposals; only the W0 tool README
documents implemented options.

Keep userspace TAP and synchronous block I/O throughout the attributed
experiment. Coordinate reusable control/readiness plumbing with [#2
vhost-net](https://github.com/cataggar/hearth/issues/2) and [#1 async
block](https://github.com/cataggar/hearth/issues/1), but neither feature nor its
implementation is a dependency. Do not merge their patches into these
measurement variants. Any later cross-feature series needs separate controls.

## Evidence that shapes the work

Inspected source: `b07f73b26b8ae876928d9c515b94bba1e9945870`.
The spec contains the source-backed inventory; the critical constraints are:

- `main.zig:runLoop` checks TAP epoll with timeout zero and polls dynamic vsock
  fds/partial writes only after `KVM_RUN` returns. A queue eventfd registration
  without an independently live backend owner can make progress worse.
- `injectIrq` uses high/low `KVM_IRQ_LINE`; slot order is block, net, vsock when
  present, with `MMIO_BASE + slot * 0x1000` and GSI `5 + slot`. Do not hardcode
  net/vsock at one address when a backend is absent. Verify the actual guest
  irqchip trigger mode instead of assuming level resampling or pulse delivery.
- The MMIO caller ignores notification payload and still processes queues for
  a malformed notification width. A shared notification decoder is a narrowly
  coupled correctness prerequisite, not an existing property or an attributed
  eventfd gain.
- Backend state, memory and transport state currently have one run-loop owner.
  API pause only acknowledges the stopped vCPU. An added worker requires a
  whole-VM barrier and an explicit guest-memory publication/ownership contract.
- Block remains synchronous; moving it off the vCPU changes scheduling even
  without eventfds. Shared-reactor head-of-line blocking must be measured,
  especially net/vsock tails during a slow `fdatasync`.
- Vsock has dynamic guest-initiated UDS connections, credits and partial-write
  buffers. `getPollFd()` returns no vsock fd; a readiness implementation must
  register connections and conditional write interest, not periodically scan
  them. The advertised third event queue has no new event protocol implemented
  here; retain its validated existing behavior rather than claiming new coverage.
- Snapshot v2 saves logical transport/ring state, not backend connections.
  Restored vsock deliberately discards stale connection descriptors and relies
  on agent reconnect. Preserve this, while recreating event registrations.
- Jail closes inherited fds before KVM initialization; seccomp is installed
  before guest interaction and does not currently permit `eventfd2`.

Read [completed zig-017-ci](../completed/zig-017-ci.md) before provisioning.
Its compiler-only Azure fixture used a 10 ms serial heartbeat for idle vsock,
had no host hardware cycles/instructions, and did not support host-initiated
CONNECT for SDK port-forward/tar. Its reported measurements are not eventfd
baselines. Existing KVM tests use a BusyBox heartbeat and a hardcoded external
kernel path; they do not prove no-heartbeat liveness or active device snapshots.
The existing interactive agent retains a separate 50 ms polling workaround.

For ABI behavior, use the target-translated headers and Linux documentation:
[KVM_IOEVENTFD](https://docs.kernel.org/virt/kvm/api.html#kvm-ioeventfd),
[KVM_IRQFD](https://docs.kernel.org/virt/kvm/api.html#kvm-irqfd) and
[eventfd](https://man7.org/linux/man-pages/man2/eventfd.2.html). In particular,
DATAMATCH preserves notification discrimination; irqfd resampling deasserts
on EOI and requires userspace to requeue still-pending device interrupts.

## Workstreams and real dependencies

W0 is partially executed; the remaining workstreams below are proposed, not
completed. Seven integration cases pass per optimization mode, but only five
boot a real guest; two exercise CLI errors. Their serial heartbeat does not
satisfy no-heartbeat or active-device lifecycle coverage.

| ID | Workstream / deliverable | Prerequisites |
|---|---|---|
| W0 | Verify environment/fixtures; profile untouched L0; publish baseline exit, IRQ/syscall, idle and liveness findings before designing acceleration | None; functioning mandatory Azure KVM and pinned fixtures are execution prerequisites |
| W1 | Decide ownership topology, guest IRQ semantics, lifecycle boundary, internal mode selectors and diagnostic/counter contract from W0; design focused tests | W0 |
| W2 | Implement shared servicing/validation/ownership/quiescence controls with ordinary MMIO and IRQ-line delivery; prove C00 correctness and no-heartbeat liveness | W1 |
| W3 | Profile C00 versus L0; repeat legacy-versus-legacy runs; freeze numeric gates, primary workloads and sample policy before prototype measurements | W0, W2 |
| W4 | Add per-queue ioeventfd assignment/draining/deassignment and fallback; validate C10 | W1, W2, W3 |
| W5 | Add per-device irqfd, routing/ACK/resampling policy and fallback; validate C01 | W1, W2, W3; **not W4** |
| W6 | Compose C11; stress reset, pause, snapshot/restore and teardown across all modes and mixed devices; enforce jail tests | W4, W5 |
| W7 | Run frozen four-mode nested-Azure benchmark/profile matrix, optional non-nested comparison, paired analysis and mechanism attribution | W3, W4, W5, W6 |
| W8 | Record evidence, keep/reject/default/rollback decision; update spec/results and move plan to completed only after actual investigation | W7 |

W4 and W5 are independent prototypes once controls are stable. Shared capability
and registration helpers can be defined in W1/W2 without enabling either path.
Failure to provision TAP or a guest-initiated vsock fixture blocks that required
coverage, not the documentation or unrelated prototype exploration. No skip
counts as a passing experiment; no default promotion with unfulfilled gates.

### W0 — Establish an honest baseline

1. Confirm `/dev/kvm` access and actual child VM creation as the intended
   unprivileged identity, not merely file existence or one successful preflight.
   Preserve group/ACL/identity diagnostics; the completed CI plan records a
   prior disappearing-ACL problem. Use `kvm` group membership, never a
   world-writable host KVM node or a root VMM.
2. Identify actual host/SKU/nesting, available perf events and stack unwinding,
   tracepoint permissions and guest drivers. The previous D16ds_v5/8370C,
   host 6.18.31 and guest 5.10.245 fixture is a starting recipe, not an assertion
   about the next host. Mandatory nesting must be evidenced in the manifest.
3. Provision immutable kernel/initrd/rootfs/agent/tool fixtures inside the
   project. Validate boot, disk, TAP and guest-initiated vsock payload round trips
   on L0. Maintain an explicit unsupported-interface list. Avoid depending on
   a prior session-only workload runner or a clean Docker image setup that was
   not previously verified.
4. Capture L0 unprofiled runs, `perf stat`, stack profiles/reports and available
   KVM trace data on all workload classes. Use diagnostic external tracing
   and a separately labelled counters-only L0 build if source-level exit/kick
   classification is needed. Verify instrumentation overhead with unchanged
   uninstrumented L0; do not smuggle servicing changes into the baseline.
5. Run no-heartbeat halted-vCPU probes; retain observed baseline stalls as
   failures/limitations. A heartbeat-assisted L0 comparison may be supplementary
   only. Never claim a finite speedup against a non-completing baseline.
6. Review where CPU and notification/interrupt costs actually reside before
   selecting reactor topology or IRQ policy. If the alleged overhead is not
   significant, a small negative prototype may be sufficient; record it.

### W1/W2 — Common controls, not eventfd-attributed gains

Proposed surfaces:

| Surface | Proposed responsibility |
|---|---|
| `vmm/src/main.zig` | Replace after-exit-only device polling with independently live servicing; internal selectors; construct/stop owners in all boot/restore variants; keep vCPU and serial handling separate |
| `vmm/src/events.zig` (proposed; topology/name decided in W1) | Blocking epoll readiness, tagged device/queue/generation tokens, control wakeups, work budgets, ownership/quiescence barrier and fd lifetimes |
| `vmm/src/devices/virtio/mmio.zig`, `queue.zig` | Shared notification validation and queue-specific dispatch; serialized MMIO configuration/ACK/reset; explicit guest-memory ordering; logical IRQ state |
| `vmm/src/devices/virtio/{blk,net,vsock}.zig` | Retain synchronous block operations; integrate TAP RX and dynamic vsock IN/OUT/HUP/ERR, pending packets and credit/buffer rearming without changing protocols |
| `vmm/src/api.zig`, `snapshot.zig` | Whole-VM pause acknowledgement before returning success/saving; bounded failure; stable logical snapshot boundary and resume/restore reconciliation |
| `vmm/src/kvm/{abi,system,vm}.zig` | Translated capability/assignment helpers, errno context, resource-safe cleanup; no new architecture-specific hardcoded ABI struct layouts |
| `vmm/src/seccomp.zig`, `jail.zig` | Justified eventfd/control syscall permission, inherited enforced filter, retained privilege/namespace restrictions and cleanup order |
| `vmm/src/tests.zig`, `integration_tests.zig`, `build.zig` | Focused unit cases and real KVM microguest/Linux cases; project-relative configurable kernel fixture and explicit runtime prerequisites |
| `benchmarks/virtio-eventfd/` (proposed) | Pinned guest probes, host orchestration, counter/trace parsing, manifest and paired-run reports; no existing benchmark CLI is assumed |

Choose one mutation owner per device, including transport state and vsock
connections. One reactor or per-device owners are open alternatives: decide
from baseline and slow-block contention, not borrowed async-block code.
Specify MMIO request/response serialization, which locks may be held during
synchronous I/O, and the guest ring acquire/release publication sequence.
Lifecycle waits must not hold locks the worker needs to acknowledge pause.

Provide the same runtime binary and owner topology for C00/C10/C01/C11.
Experimental selectors are **proposed internal VMM controls**, for example
`--virtio-kicks mmio|ioeventfd` and `--virtio-irqs line|irqfd`; these flags do
not exist now. Do not add SDK configuration modes. Emit requested and effective
per-device modes/reasons, capabilities, registration generations and counters.
L0 is a separate unchanged binary and is invoked without new flags.

Common owner notifications must work without ioeventfd: valid MMIO writes enqueue
work and wake the owner; status/queue enable/RX replenishment/credit changes also
reconcile readiness. Use a blocking wait, with no periodic scan or heartbeat.
When an fd stays readable without buffers/credits, suspend that readiness
interest until replenishment; retain pending logical work. Continue locally
when a queue budget expires. Dynamic vsock fds must be removed before close
and tagged against reuse; EPOLLOUT must cease when buffers drain.

Normalize four-byte notification decoding, queue ID bounds and status/readiness
rules before accelerating. In every controlled mode, malformed widths/values
must cause no unrelated processing. Record the baseline gap and use paired C00
to isolate any validation/interrupt semantic correction from eventfd benefit.
Do not expand the advertised VirtIO features.

Define a state machine such as configuring → running → quiescing → paused →
running/stopping; reset invalidates the relevant generation. A pause request
stops admission, kicks `KVM_RUN`, wakes owners, waits for in-flight synchronous
I/O and stable ring/IRQ state, then acknowledges **all** participants. A bounded
timeout must fail without serializing inconsistent state or falsely reporting
Paused. Resume reconciles pending work before allowing new guest execution.
Eventfd lifecycle itself is tested in W4/W5/W6.

### W3 — Freeze controls and gates

Preserve four explicit variants:

| Label | ioeventfd | irqfd | Common owner/validation/lifecycle controls |
|---|---|---|---|
| L0 | Off | Off | Original source behavior |
| C00 | Off | Off | On |
| C10 | On | Off | Identical to C00 |
| C01 | Off | On | Identical to C00 |
| C11 | On | On | Identical to C00 |

Show both L0→C00 common-control effects and the controlled 2×2 contrasts.
Select primary notification-heavy cases and freeze the spec's provisional
benefit/regression/idle gates from repeated baseline noise. Record thresholds,
confidence method, sample count and allowed noise adjustments **before**
prototype results. Suggested starting design: 10 paired repetitions, 5 s
warmup then 30 s measurement per bulk case, at least 1,000 latency samples per
variant spread across repetitions, and 60 s no-traffic idle windows. Increase
counts if p99/confidence is unstable, using the same rule for every variant.

### W4 — ioeventfd-only

- Check `KVM_CAP_IOEVENTFD`; register one CLOEXEC/nonblocking eventfd per
  supported ready queue with exact MMIO address, **length 4** and DATAMATCH
  queue ID. Do not use `ANY_LENGTH` or payload-blind matching. Track all fields
  needed for DEASSIGN, including the same match flags/tuple.
- MMIO fallback still validates unmatched values/widths and all configuration
  registers. Cover valid queues when `QUEUE_SEL` differs from the notified ID.
  Decide explicitly whether the currently inactive vsock event queue stays on
  the validated legacy path; do not invent an event-queue consumer.
- Drain accumulated eight-byte counters correctly, handle EINTR/EAGAIN, and
  use ring state—not counter value—as work quantity. Reconcile post-drain
  arrivals and readiness/disable races. Preserve budgets and no-lost-work
  behavior when one kick covers many descriptors or kicks carry no new work.
- Gate queue activation/reset on owner acknowledgement; remove assignments/
  epoll interests, invalidate generations and settle stale wakeups before
  queue reuse. C10 completes through the **ordinary IRQ-line path**, which
  must be safe from its backend owner while `KVM_RUN` is blocked.
- Report unsupported capability and assignment failure context; roll back
  partial registrations. Unexpected errors fail the sample even if a safe
  fallback VM continues. A silently downgraded C10 is not C10 performance.

### W5 — irqfd-only

- Verify default GSI routing and guest PIC/IOAPIC trigger state with actual
  interrupt delivery; do not change routes merely to make irqfd convenient.
  Check `KVM_CAP_IRQFD` and, for level mode, `KVM_CAP_IRQFD_RESAMPLE`.
- One interrupt eventfd per device/GSI, separate from each queue's kick fd.
  Preserve interrupt status and ACK semantics under the chosen compatible
  pulse/level policy. Publish used state before signalling; distinguish
  logical pending status, notification batches and kernel injection.
- For level mode, integrate resamplefd into blocking readiness. KVM deasserts
  the irqfd source on EOI; drain resamples and reassert only while device
  status needs service. Cover both ACK/EOI orders and completion concurrent
  with ACK. Avoid a reassertion storm or a dropped still-pending interrupt.
- Prove mask/unmask, reset and deassignment behavior for an asserted source.
  Closing resamplefd alone does not remove irqfd; writing zero does not lower
  a line. Do not assume legacy low clears an independently tracked irqfd
  source. If compatible semantics are unavailable, diagnose and use legacy.
- C01 retains validated MMIO queue kicks. Keep serial on its existing path
  and exclude its ioctls from attributed VirtIO savings.

### W6 — Integration, lifecycle and isolation

Compose only after the independent modes pass. For pause/snapshot:

1. Stop admission and vCPU execution; control-wake all owners.
2. Finish or consistently reconcile accepted requests, drain/reconcile kicks,
   stop resample/interrupt mutations and synchronously deassign registrations
   where required. Establish the documented logical pending-work/IRQ boundary.
3. Acknowledge quiescence before API success and before `snapshot.save`. Review
   deassignment versus irqchip save order: capturing while KVM's irqfd work
   can still alter a line is unsafe. Snapshot save must not race a worker.
4. Persist only guest-visible/logical state. Determine whether existing v2 is
   sufficient; prefer no format change. If additional logical state is truly
   necessary, design/version compatibility explicitly before writing it.
5. Resume or fresh restore rebuilds registrations after memory, backends and
   restored transport/irqchip state exist; reconcile pending rings/status and
   avoid replaying an already saved interrupt. Start owners before guest run.

Reset/queue disable uses per-device/queue generation barriers. Teardown and
error unwinding remove KVM and epoll registrations, join owners and only then
close fds/devices/VM and unmap memory. Include CLI/API boot, both CLI/API restore,
save-on-halt, API shutdown and partial setup/failed restore. Check an actual
`KVM_EXIT_HLT` shutdown separately from a guest HLT sleeping inside `KVM_RUN`.

Keep jail initialization order. Add only demonstrated required syscalls/flags,
principally `eventfd2` plus existing read/write/epoll operations; inspect the
actual Zig thread/control syscall path before expanding the whitelist.
Preserve AF_UNIX/clone/no-PROT_EXEC restrictions and non-root device ownership.
Run enforced seccomp cases and verify blocked forbidden operations still
terminate a disposable child; audit mode is diagnostic, not acceptance.

## Focused tests to implement

Use existing Zig test roots rather than a new testing framework. Unit tests
support reasoning; the required transitions also execute on real KVM.

| Test group | Action and oracle |
|---|---|
| Notification decoder/registration | Tiny KVM microguest issues valid four-byte queue IDs, wrong width/alignment/address, out-of-range/high-bit IDs, pre-`DRIVER_OK`, queue-disabled/reset notifications and differing `QUEUE_SEL`. Confirm unmatched writes reach validation, no unrelated queue indices move, and exact per-queue assignment/detachment works. Exercise production dispatch/owner helpers, not an unrelated mock. |
| Kick draining/rings | Submit multiple descriptors per kick, multiple kicks before wakeup, empty/spurious kicks, u16 index wrap and kick-at-sleep-boundary; compare unique descriptor/request IDs, used lengths/status, checksums and completion totals. Controlled modes use identical feature masks. |
| Completion/IRQ | Observe guest interrupts/status, ACK bits, EOI, mask/unmask, simultaneous completion/ACK, level resampling and pending status across pause/restore. Required delivery is not inferred merely from an incremented host write counter; no unexpected post-reset IRQs or duplicate completions. |
| Halted/blocked-vCPU | Guest posts queues and sleeps/HLTs with fixture heartbeat off; host supplies TAP/UDS data and backend completions. Verify receipt/IRQ wakes within the frozen bound without serial/API traffic/periodic worker timers. C10 exercises backend legacy IRQs; C01 exercises MMIO work submission. |
| Device integrity/backpressure | Block read/write/FLUSH and ordered checksums; TAP RX/TX and no-buffer rearm; vsock guest-initiated RX/TX, pending responses/RST, credit exhaustion, slow readers/partial writes and HUP/fd reuse. Expose baseline corruption/unsupported behavior rather than hide it in timing results. |
| Reset/reconfigure | Reset/status zero and queue-ready off/on during kicks, pending completions and asserted interrupts; change ring addresses, reuse queue IDs/fd integers, restore `DRIVER_OK`, submit new work. Old-generation events cannot mutate the new ring or another device. |
| Pause/snapshot/restore under active I/O | Quiesce while block writes/flushes and bidirectional TAP/vsock traffic are active. Compare stable paused rings/memory, acknowledged disk contents, completion IDs/status and IRQ state; restore with fresh backends and deliberately different host fd numbers. Disk state is cloned consistently with the paused memory, not independently while writes continue. Vsock reconnect follows existing policy; no promise to preserve live host streams. |
| Shutdown/failure/isolation | Pause→teardown, active→teardown, save-on-halt, partial assignment, exhausted fd/resource error, permission error and missing-capability fallback. Check child exit, fd/thread/registration cleanup and no memory access after unmap; enforced jail/seccomp retains forbidden syscall boundaries. |

Starting stress counts are the spec's provisional 100 pause/resume/reset
transitions, 20 active snapshot/restore cycles per controlled mode/device mix,
and 10 teardown/error cycles. Establish old→new, new→legacy and all controlled
mode-to-mode snapshot restores, with disk/TAP/vsock recreated and execution
observed. Inject deterministic races around drain/reset/quiescence with test
barriers rather than probabilistic sleeps alone.

Missing KVM, kernel/tools, TAP rights, drivers, irqfd/resample capabilities or
fixture integrity are explicitly blocked/unavailable results. Collect
per-case execution counts and guest markers; a successful build or entirely
skipped suite is not passing coverage. Optional non-nested absence is not
equivalent to missing the required nested host.

## Proposed commands and reproducible fixtures

**Do not run these as part of planning.** Paths/commands under
`benchmarks/virtio-eventfd/`, `-Dintegration-kernel`, and mode selectors below
are future interfaces to implement in W1/W2, not existing tools. Store all
fixtures and raw output project-relative; avoid external temporary locations.
The runner must log the expanded commands actually executed, not only this
template.

### Build and prerequisites

Use Zig **0.17.0** for both L0 and controls; `safe` is the installed-performance
configuration, `debug` additionally exercises correctness. Both manifests pin
translate-c fork `62d06a5d3e93c82727544e8113e4762a315ca0ed` and hash
`translate_c-2.0.0-Q_BUWlpOBwBWvgGBM20tJq-GXgPio3v3UD39rXEn70KN`.
Record transitive Aro `d0c8c4d9c55daa7ef6e40cf0f630a5b5e900989b` and its locked
content hash as resolved; hash manifests, lockfiles, compiler and binaries.
Do not compare a compiler transition with eventfd changes.

```bash
mkdir -p .perf/eventfd/fixtures .perf/eventfd/results
test "$(zig version)" = 0.17.0
git --no-pager rev-parse HEAD
uname -a
lscpu
id
getfacl -n /dev/kvm
perf --version
perf list
sha256sum vmm/build.zig.zon agent/build.zig.zon package-lock.json
```

Add a real KVM-open/API-version/VM-create/capability preflight to the runner,
with translated header constants, raw failure diagnostics and immediate checks
before child execution. Record nesting evidence and perf permission settings.
The existing pinned guest kernel recipe can be reproduced project-relative:

```bash
curl --fail --location --retry 3 --max-time 120 \
  https://github.com/joshuaisaact/hearth/releases/download/kernel-5.10.245/bzImage \
  --output .perf/eventfd/fixtures/bzImage
echo "4da539807474d189f1a15852046994e78d430a194c2e78b9255ae880069c7208  .perf/eventfd/fixtures/bzImage" \
  | sha256sum --check
(cd vmm && zig build -Dtarget=x86_64-linux -Doptimize=safe --summary all)
(cd agent && zig build -Dtarget=x86_64-linux -Doptimize=safe --summary all)
```

The kernel/hash above is verified by repository CI, not proof all benchmark
drivers/tools exist. Record CONFIG_VIRTIO_MMIO, block/net/vsock, guest IRQ
configuration, mounted filesystems and helper versions. Build/check pinned
guest probes/fio/iperf tools in the fixture, or explicitly provision and hash a
known working image; do not silently replace the kernel/agent between modes.
Use read-only fixture bases and a per-run writable disk clone. Do not write
to an existing user disk or globally flush host caches on a shared machine.

Future focused validation commands after the configurable kernel option exists:

```bash
zig fmt --check vmm/build.zig vmm/src
(cd vmm && zig build test -Dtarget=x86_64-linux -Doptimize=debug --summary all)
(cd vmm && zig build test -Dtarget=x86_64-linux -Doptimize=safe --summary all)
(cd vmm && zig build integration-test \
  -Dtarget=x86_64-linux -Doptimize=safe \
  -Dintegration-kernel=../.perf/eventfd/fixtures/bzImage --summary all)
```

Run the expanded matrix with fail-on-missing/fail-on-skip and real guest
markers; use the existing CI result-count checking pattern. No TypeScript
runtime test is mandatory for an untouched SDK, but drive the real agent
protocol rather than assuming skipped SDK suites have verified it.

### Runner contract and workload recipes

Implement proposed `benchmarks/virtio-eventfd/run.py` with phase commands
`preflight`, `run`, and `summarize`. It must:

- Start host UDS listeners before the guest connects, provision an isolated
  TAP/host-peer fixture with unique names/addresses and narrowly privileged
  setup, then run Flint without root; destroy only resources created by it.
- Launch direct CLI or the existing preboot API; await an actual boot/agent
  protocol marker and record every VMM thread PID/TID/affinity. Separate warmup,
  measurement and lifecycle phases, and keep readiness markers out of timed I/O.
- Map L0 to an unchanged binary with no new flags. Map the controlled modes to
  one prototype binary with independent selectors, and fail if effective mode
  differs from requested mode. Disable vhost/async-block integration explicitly.
- Emit sample counters, operation/byte counts, checksums, per-op latency arrays,
  perf artifacts, mode diagnostics and manifest; never summarize errors/skips
  as zero-latency success.

Example **future** invocations, repeated with the frozen seeds/order/sample
policy for every workload and variant:

```bash
python3 benchmarks/virtio-eventfd/run.py preflight \
  --kernel .perf/eventfd/fixtures/bzImage \
  --fixture .perf/eventfd/fixtures/guest.json \
  --out .perf/eventfd/results/preflight
python3 benchmarks/virtio-eventfd/run.py run \
  --binary .perf/eventfd/fixtures/legacy/flint --variant legacy-original \
  --kernel .perf/eventfd/fixtures/bzImage \
  --fixture .perf/eventfd/fixtures/guest.json --workload disk-4k \
  --sandboxes 1 --warmup-seconds 5 --seconds 30 --samples 10 \
  --vmm-cpus 8-9 --client-cpus 10-11 \
  --out .perf/eventfd/results/l0-disk
python3 benchmarks/virtio-eventfd/run.py run \
  --binary .perf/eventfd/fixtures/controlled/flint --variant ioeventfd \
  --kernel .perf/eventfd/fixtures/bzImage \
  --fixture .perf/eventfd/fixtures/guest.json --workload disk-4k \
  --sandboxes 1 --warmup-seconds 5 --seconds 30 --samples 10 \
  --vmm-cpus 8-9 --client-cpus 10-11 \
  --out .perf/eventfd/results/c10-disk
```

Use `legacy-control`, `irqfd`, `combined` for C00/C01/C11. CPU numbers above
are illustrative assignments, not assumed availability. Hold the same VMM
cpuset in every variant, pin each actual vCPU/backend owner deliberately,
place clients/peer servers separately, and record SMT/NUMA layout. Repeat
with 1, 4 and 8 sandboxes (or record a baseline-derived resource bound) and
mixed disk/net/vsock traffic; test both active and idle concurrency.

| Workload | Concrete proposed guest/host operation and controls |
|---|---|
| Notification-heavy disk | In guest, `fio --name=reads --filename=/bench/data --size=32m --rw=randread --bs=4k --ioengine=psync --direct=1 --numjobs=1 --iodepth=1 --time_based=1 --runtime=30 --ramp_time=5 --group_reporting=1 --output-format=json+`; repeat randwrite and `numjobs=4` with fixed seed/offset policy. Synchronous `psync` does not provide effective depth 16, so do not label it such. |
| FLUSH/latency and bulk disk | Guest `fio --name=flush --filename=/bench/flush --size=32m --rw=write --bs=4k --ioengine=psync --direct=0 --fsync=1 --time_based=1 --runtime=30 --ramp_time=5 --output-format=json+`; separately 1 MiB sequential read/write, and bounded write/read verification using checksums. Log filesystem/mount/cache state, guest block scheduler and FLUSH feature; distinguish file I/O from underlying virtqueue operation counts. |
| Userspace TAP | Isolated host peer runs `iperf3 -s -B 192.0.2.1`; guest uses `iperf3 -c 192.0.2.1 -t 30 -O 5 -P 1 --json`, reverse `-R`, then `-P 4`. Addresses are dedicated fixture examples, not shared-host changes. Add pinned sequence-number/checksum echo probes with 64-byte and 1,400-byte messages for packet/RTT tails, loss and guest-HLT wakeup; no vhost, offload or MTU changes between modes. |
| Supported vsock bulk | Proposed pinned native guest probe connects `AF_VSOCK` to CID 2/port 11000; host listens on the **existing supported** `<uds-prefix>_11000`. Transfer fixed seeded payloads both ways, e.g. 64 MiB with 64 B/4 KiB/64 KiB chunks, verify byte counts/checksums, exercise 1/16/64 connections, credit exhaustion and a slow-reader backpressure case. No host CONNECT request or tar-stream SDK helper. |
| Exec/interactive | Real `AgentClient` control listener on `<uds-prefix>_1024`, guest-initiated agent connection, repeated exec request for `printf x` and PTY spawn/echo with first-byte, completion and round-trip timestamps. Keep agent/PTY workaround unchanged and label 50 ms quantization. A lower-level native vsock probe, not a periodic agent read, establishes reactor liveness. |
| Idle/idle→active | Heartbeat off; 60 s no-work guest-HLT and agent-connected idle cases, then one disk request/TAP packet/UDS message. Include baseline stalled cases explicitly. Measure aggregate CPU, scheduler wakeups, context switches and response bound, not only an empty main thread. |

For disk reads prepopulate immutable content once, then clone identically.
Choose warm host/guest cache as a separate named series from fresh boot/guest
cache; direct guest I/O does **not** imply uncached host backing-file I/O.
Document the bounded cache preparation method and backing filesystem/storage.
Do not equate `fsync=1` user operations with one VirtIO flush/kick or use different
cache policies to manufacture an apparent notification gain.

### Host profiling commands

The runner provides actual `VMM_PID`, `TIDS`, `OUT` and `MEASURE_SECONDS`
after all owners are running and warmup is complete. Explicitly enumerate
**every VMM/backend thread**, including API/IO threads; verify the roster again
after the window. If threads appear during a window, include them through a
verified process/cgroup-wide collection method or invalidate/repeat the
sample. CPU attribution must not omit a worker because it replaced vCPU work.

Example attachment commands, with separate profiling repetitions:

```bash
perf stat -t "$TIDS" \
  -e task-clock,context-switches,cpu-migrations,page-faults \
  -o "$OUT/perf-stat.txt" -- sleep "$MEASURE_SECONDS"
perf record -t "$TIDS" -e cpu-clock -F 199 -g --call-graph dwarf \
  -o "$OUT/cpu.data" -- sleep "$MEASURE_SECONDS"
perf report --stdio -i "$OUT/cpu.data" > "$OUT/cpu-report.txt"
perf script -i "$OUT/cpu.data" > "$OUT/cpu-stacks.txt"
```

If listed/permitted, add:

```bash
perf stat -t "$TIDS" -e kvm:kvm_entry,kvm:kvm_exit \
  -o "$OUT/kvm-stat.txt" -- sleep "$MEASURE_SECONDS"
perf record -t "$TIDS" \
  -e kvm:kvm_entry -e kvm:kvm_exit \
  -e syscalls:sys_enter_ioctl -e syscalls:sys_exit_ioctl \
  -o "$OUT/kvm-ioctl.data" -- sleep "$MEASURE_SECONDS"
perf script -i "$OUT/kvm-ioctl.data" > "$OUT/kvm-ioctl.txt"
```

Probe `perf kvm stat` support if exit tracepoints are absent or as a second
view; use the host perf version's `record/report` syntax and retain exact
commands/output. Capture cycles/instructions only when genuinely supported;
on Azure refusal/zero/unsupported events, retain the diagnostic and use
software profiles. Guest PMU is hidden; do not request guest PMU statistics.
Verify stacks/symbols, sampling loss and throttling. Retain failed traces too.
Trace/profile overhead must not be mixed with unprofiled primary throughput/
latency repetitions; compare overhead symmetrically if tracing all modes.

Instrument counters at the shared dispatch/owner and KVM boundaries, with
identical counter settings across modes:

- Valid/malformed guest notifications by device/queue, accumulated kick
  eventfd counts, wake/drain syscalls, resamples, budget reschedules and work
  left at sleep. Reset-generation discard counts are not lost current work.
- Descriptors accepted/completed, used-index deltas, payload bytes, completion
  batches, logical IRQ signals, `KVM_IRQ_LINE` calls and eventfd writes/errors.
- `KVM_RUN` calls/userspace returns by `exit_reason`, plus EINTR/control exits.
  KVM tracepoints include kernel-handled exits even with ioeventfd and must not
  be called userspace exits. Count eligible MMIO notifications separately.
- Decode ioctl request fields from tracepoints/source counters to distinguish
  `KVM_RUN`, IRQ-line, registration and snapshot ioctls. Pair enter/exit by TID
  for IRQ-ioctl latency; `KVM_RUN` residency is not interrupt-delivery cost.
  Charge eventfd reads/writes, resample handling, context switches and backend
  CPU in addition to removed ioctls.

Define operation denominators per workload (fio data I/O, verified bytes/
messages, exec requests) and show both per-op and per-completion/kick metrics.
Report total user+system/task-clock across VMM threads per completed operation,
vCPU-versus-backend CPU breakdown, and separate client/peer CPU. Concurrent
runs sum all sandbox owners; idle CPU uses core-percentage and CPU seconds,
not per-op division by zero. If a dedicated measurement cgroup adds insight,
record kernel CPU/softirq accounting separately without silently changing the
primary scope.

### Manifest, retention and analysis

Each run manifest must include:

- UTC date, source/patch SHA and dirty diff hashes, L0/control/prototype binary
  hashes, optimization, Zig/compiler provenance, translated-header version,
  dependency/lockfile pins and hashes, agent/helper/tool versions.
- Host kernel, perf version, CPU model/SKU, microcode, nesting evidence, Azure
  VM SKU, allowed cpuset/affinity/SMT/NUMA, CPU governor/throttling/load and
  privilege/perf limitations; non-nested host metadata or explicit absence.
- Guest kernel/config/image hashes, one actual vCPU (not an assumed multi-vCPU
  API setting), RAM, VirtIO features/driver/queue/IRQ routing and trigger state,
  guest agent state, TAP settings and storage/rootfs layout.
- Exact launch/API/guest/perf commands, requested/effective modes/capabilities,
  thread roster, fixture/cache policy, seeds, warmup/duration/sample count,
  concurrency, operation counts, timeout/failure rules and instrumentation.

Retain raw baseline/prototype `.data`, stat/trace/stacks/reports, guest/host
logs, integrity markers, unaggregated latency samples and manifests in
`.perf/eventfd/results/<run-id>/`; preserve artifact hashes and retention
location in the final results. Do not retain only a summary table or replace
failed runs. Share/upload only through the eventual authorized result workflow;
this planning task does not change GitHub.

Alternate/randomize variant order within paired blocks, preserving machine/
fixture conditions. Report all repetitions, medians, p50/p95/p99, standard
deviation/CV and paired 95% intervals; explain sample exclusions predefined
for host interference or fixture failure. Compute C10/C00, C01/C00,
C11/C01 and C11/C10 plus interaction; report L0/C00 separately. Slow flush,
vsock agent polling or missing PMU may make an effect inconclusive; disclose
that instead of selecting only favourable profiles.

## Gates, risks and unresolved decisions

Ratify the [spec's numeric gates](../../product-specs/perf-virtio-eventfd.md#measurement-and-acceptance)
in W3. Starting suggestions: ≥10% CPU/op or p95 benefit with a paired interval
excluding no benefit; ≥90% reduction in the corresponding eligible exits/
IRQ-line calls; ≤3% throughput loss; ≤5% CPU/percentile/lifecycle regression;
≤0.1 percentage-point aggregate idle-core increase per sandbox. Mechanism
reductions alone do not qualify as a performance win. Freeze justified
baseline-noise changes before evaluation, capped at 5% throughput/10% other
relative regression; noisy idle or larger noise means inconclusive, not a
post-hoc relaxed pass. Synthetic liveness has a provisional 1 s bound and
correctness has zero-error tolerance.

| Risk / open decision | Resolution required before claiming success |
|---|---|
| Kernel avoids userspace notify exits, but worker waits for another exit | No-heartbeat microguest/Linux wakeup proof with independent blocking readiness |
| Datamatch misses negotiated notification-data payload or consumes malformed data | Keep present feature mask; exact four-byte match; shared malformed-notify KVM tests |
| Worker races ACK/reset/guest publication or unmapping | Single mutation ownership, barriers, generations and deterministic race tests |
| Resampling loops, ACK loses completion, or wrong GSI is signalled | Verify actual route/trigger; test both ACK/EOI orders and unsupported fallback |
| IRQ source/deassign changes snapshot's irqchip state | Decide coherent quiescence/capture/re-registration ordering and cross-mode restores; v2 compatibility question explicit |
| Sync block stalls all owners or pause indefinitely | Choose topology from W0; mixed-load tails and bounded pause failure; no hidden #1 dependency |
| Level-ready TAP/UDS with no buffers/credits burns idle CPU | Disable/rearm interests from real guest state changes; idle/backpressure profiling |
| Existing net/vsock integrity, CONNECT absence or agent 50 ms polling contaminates results | L0 fixture validation and supported paths only; isolate blockers, report separate native and agent latencies |
| Missing Azure PMU/trace permissions or unstable host noise | Software stack fallback, exact limitations, retained raw data; no default on inconclusive attribution |
| Broadened jail or inherited unfiltered worker | Enforced child tests, minimum syscall flags, unchanged privilege/namespace boundary |

Open choices remain: owner topology; compatible pulse/level IRQ policy and
resample availability; bounded quiescence timeout/error contract; snapshot v2
sufficiency; treatment of inactive vsock event queue; actual provisioned
TAP/vsock fixtures; experimental mode/counter interface; final primary
workloads, affinity and noise-derived gates. These are execution questions,
not reasons to invent an implementation or measurement in a planning-only task.

## Decision, rollback and completion checklist

Legacy remains the default. Promote only the simplest **measured** passing
mode; combined is not presumed best. Keep independent runtime legacy kick/
IRQ selection and unsupported-host fallback with detected-mode diagnostics.
Rollback quiesces, removes registrations, recreates legacy servicing and
preserves logical rings/interrupts; never switch a live queue unsafely.
If acceleration is rejected, retain its result and assess common correctness
controls independently, without calling them an eventfd speedup.

- [ ] W0 untouched baseline, perf stacks/exit/ioctl breakdown and limitations retained.
- [ ] W1 ownership/route/lifecycle decisions documented from baseline evidence.
- [ ] W2 controlled legacy passes actual no-heartbeat and integrity tests.
- [ ] W3 C00/L0 effects and legacy noise measured; numeric gates frozen.
- [ ] W4 ioeventfd-only and W5 irqfd-only independently execute/diagnose capabilities.
- [ ] W6 combined and all pause/reset/snapshot/restore/teardown/race/jail cases pass on real KVM; no skipped-as-passing coverage.
- [ ] W7 required nested-Azure workload/concurrency/idle matrix, all-thread CPU and raw profiles retained; optional non-nested comparison or absence stated.
- [ ] W8 benefit/regression/variance analysis and explicit keep/reject/inconclusive/default decision recorded, including negative results.
- [ ] Legacy rollback and cross-mode snapshot compatibility verified; directly related implementation docs updated.
- [ ] Move this plan to completed only after the investigation, not merely after this plan is written.
