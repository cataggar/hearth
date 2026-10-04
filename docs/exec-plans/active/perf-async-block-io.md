# Execution Plan: Profile and Evaluate Async VirtIO Block I/O

**Status**: Blocked at G0 — baseline capabilities diagnosed, backend not selected
**Last updated**: 2026-10-04
**Issue**: [#1](https://github.com/cataggar/hearth/issues/1)
**Spec**: [Asynchronous VirtIO Block I/O](../../product-specs/perf-async-block-io.md)
**Actual results**: [baseline capability execution](../../product-specs/perf-async-block-io-results.md)

## Execution checkpoint — 2026-10-04

The project-local integration kernel option and capability/diagnostic tooling
are implemented and executed. Debug/safe unit suites each execute 31 tests;
debug/safe existing integration suites each execute seven, including actual
guest execution after restore. These unjailed cases do not establish async
acceptance. Thirteen enforced-jail startup attempts fail before guest execution:
API `recvmsg` is killed by seccomp, CLI device paths have root-only permissions
under required umask 077. Actual stat/stack data and a saturated-host idle
control are retained. See the results for exact counts, commands and limits.

G0 is **partial/blocked**; G1 matrix, A/A noise and frozen numeric gates do not
exist. G2–G5 must not start from these startup diagnostics. Keep the synchronous
default. No worker/selector/force-sync implementation, performance gain, default
promotion or merge eligibility is claimed. This plan remains active rather than
being moved to completed.

### Post-provisioning checkpoint — 16:01 UTC

The parent subsequently provisioned Node/npm, iproute, fio with host libaio
support, and iperf3. A short locked inventory records actual versions and
glibc/libaio/liburing packages. All earlier startup/stat/stack/idle captures
remain **pre-provisioning capability diagnostics**, not a controlled baseline.
No workload was rerun or gate frozen from them. The unchanged jail failures
and incomplete guest fixture still block G0; new mandatory sampling must
establish complete fixture/environment controls after provisioning.

## Outcome and controls

Produce a reproducible baseline, a correctness-qualified experiment if warranted,
and a measured keep/reject decision. Execution has started in the isolated
`copilot/perf-async-block-20261004` worktree. Completion of implementation remains
governed by the checklist below; a baseline-only diagnostic is not backend
acceptance.

Use the spec's compatibility and numeric gates rather than duplicating them.
Hold compiler, guest image, backing storage and legacy MMIO/IRQ notification
path fixed. Do not combine #3 notification changes with the primary experiment.
#2/#3/#6 planning or implementation is not a prerequisite. Coordinate only if
their changes overlap the exact execution revision or completion integration;
use isolated worktrees for prototypes and integrate at a declared gate.

## Sequential gates

### G0 — Verify capabilities and construct a repeatable baseline fixture

1. Recheck the spec's source facts at the chosen commit. Record any drift, dirty
   changes and selected notification/backend path. Inventory all VMM/runtime
   threads, KVM accessibility, tracepoints, profiling permissions and storage.
   Host PMU unavailability is expected on some nested Azure SKUs; it is not
   an excuse to omit software perf profiles.
2. Freeze Zig **0.17.0**, safe optimization, binary hashes, translate-c
   `62d06a5d3e93c82727544e8113e4762a315ca0ed` and its manifest hash
   `translate_c-2.0.0-Q_BUWlpOBwBWvgGBM20tJq-GXgPio3v3UD39rXEn70KN`.
   Record the transitive Aro pin/content hash as actually resolved, headers,
   libc, fio, build/package tools and Python/Node/perf versions. Use the same
   agent binary on both sides; no repeat of the 0.16/0.17 compiler comparison.
3. Build a private, **project-relative** fixture and capture its construction
   script/manifest. Start with one vCPU, 512 MiB RAM, an 8 GiB ext4 backing
   image and a prefilled 1 GiB test file; a representative package/build image
   may require 2 GiB RAM or a larger disk. Freeze each sizing separately before
   baseline and keep it identical across candidates. Use an initramfs mounting
   a data image for fio and a verified disk-root image for package installation,
   so package writes hit VirtIO rather than the initramfs. No unsupported SMP
   or extra-disk assumption: Flint currently has one disk backend.
4. Validate guest kernel 5.10.245 with the exact CI release checksum below,
   VirtIO block/flush, filesystem, guest-initiated control/exec and PTY. Provision
   fio and its actual dependencies (including a supported higher-QD engine),
   offline package closure, build source and tools into the image/initramfs.
   Do not rely on busybox-only fixtures containing fio/apt/make or on network
   access/host-initiated CONNECT. Verify achieved fio depth, not just the
   requested `iodepth`.
5. Implement the experiment runner/collectors (proposed location
   `tools/perf/blk-io.py`, **not an existing tool**) with the API/protocol and
   perf primitives below. It owns PIDs, bounded waits, separate fixture copies,
   cleanup, full output/exit status, timestamps and durable artifact manifests.
   Add common avail-to-used timestamps/counters only if needed to distinguish
   VMM requests from fio operations; apply identical instrumentation to sync
   and candidates, and quantify overhead against an uninstrumented baseline.

Prior art is the [completed compiler plan](../completed/zig-017-ci.md) and its
[published runner](https://github.com/cataggar/hearth/pull/5#issuecomment-5973822154).
Reuse its API/control framing, not its temporary-path handling or limited
write/fsync workload. At the source baseline the KVM suite hardcoded a kernel outside the project.
Execution now implements `-Dintegration-kernel=<path-relative-to-vmm>`; the
default and CI path are `../.ci/guest/bzImage`. The verified #1 fixture uses
`../.perf/blk-io/fixture/bzImage`. No external kernel file is created or used.

**Gate evidence:** verified manifest and smoke results, working raw software
perf capture, supported workload rows and explicitly blocked rows. Missing
mandatory fixture/profiling capabilities block the default decision; the
compiler fixture cannot substitute for the missing workload.

### G1 — Profile synchronous I/O; freeze criteria before selecting a prototype

- Run the full workload matrix and matched idle controls below. Collect
  unprofiled latency/throughput repeats, then separate reproducible profiled
  repeats so trace overhead does not masquerade as an optimization.
- Collect stat, stacked CPU record/report, syscall/I/O latency, scheduler wait
  and available KVM entry/exit attribution **before** proposing implementation.
  Establish whether pread/pwrite/fdatasync hold the vCPU loop and how much time
  is disk wait versus guest work, MMIO exits, CPU scheduling or vsock polling.
- Perform baseline/baseline paired repeats; fill the spec's `B`, `N`, absolute
  benefit/regression limits and resource budget in a retained criteria file.
  Predeclare primary workload/metric, run count and cache/affinity strata.
  Register the confidence/noise policy before seeing a candidate.

**Gate decision:** keep synchronous and write a negative report if disk stalls
are not material or measured noise cannot support an actionable experiment.
Otherwise approve the smallest **bounded FIFO worker** contract at G2.
io_uring is not the starting assumption.

### G2 — Agree ownership/lifecycle contract; implement an opt-in worker

Document a small state machine and invariants before code: admission credits,
captured request/generation, worker ownership, ready completion, owner
publication, flush barrier, quiescing, reset and shutdown. Select a bounded
staging/chunk size that handles existing valid large requests without changing
feature negotiation. Start with one ordered I/O worker, not a speculative pool.

Resolve these coupling points explicitly:

- **Completion wake:** existing SIGUSR1/tkill is a narrow candidate. Register an
  owner/TID for both CLI and API modes; separate pause/exit/completion reasons.
  Publish completion before notifying; service pending completions before
  entering KVM and on EINTR, not only after ordinary exits. Prove the race where
  a kick lands between the last pending check and `KVM_RUN`; decide a verified
  pending/immediate-exit or KVM signal-mask handshake, not “signal probably
  wakes it.” A completion FD with post-exit epoll alone is insufficient.
- **Admission/publication:** workers operate on captured metadata/staged bytes;
  one owner serializes guest-memory, used-index and IRQ updates. Reserve before
  `popAvail`, check generation on publication, retain unadmitted work and refill
  when credits return even without a second doorbell. Distinguish submission
  from completion: MMIO must not raise an interrupt just for accepted work.
- **Ordering:** initially execute in FIFO order; chunked transfers still obey
  whole-request ordering and exactly-once completion. Flush blocks later writes
  until earlier writes and the sync operation settle; preserve errors and
  supported used-length behavior through the common completion path.
- **Pause/snapshot:** stop admission and the vCPU, drain and publish outstanding
  work, settle IRQ/queue state, then set `ack_paused`. The paused loop must
  permit drain progress without timer-driven completion polling. Settle the
  disk before SDK artifact copy/move; resolve additional snapshot `fdatasync`
  policy separately and include its cost. Apply the same rules to CLI
  save-on-halt, API snapshot, resume and restore.
- **Reset/teardown:** increment generations, suppress old memory/IRQ writes and
  drain old disk mutations before new-generation I/O. Join workers before
  backing FD close, guest-memory unmap and VMM resource destruction. Repair
  the coupled restore cleanup order, not unrelated lifecycle behavior.
  Include queue-disable/reconfiguration races and rescan retained avail entries
  on resume/restore without waiting for another guest notification.
  Specify a quiesce deadline and fail-closed state; blocking filesystem I/O
  cannot be assumed cancellable. Do not report success or free live resources
  after deadline expiration.
- **Selection/fallback:** choose a build-local experiment or developer-only
  selector usable in every boot/restore mode. Neither exists today. Preserve
  synchronous default and force-sync rollback; log initialization/capability
  errno and effective backend. Unwind partial worker/FD creation. Do not
  switch/replay already accepted writes on runtime failure.
- **Jail:** choose only required synchronization primitives. Current filtered
  clone/futex/tkill may suffice; eventfd would need a reviewed narrow allowance.
  Verify syscalls emitted by Zig 0.17 thread creation under the **kill** filter.
  Never probe an unlisted syscall expecting recoverable failure, create workers
  outside the jail to bypass restrictions, or broaden clone/socket/mprotect.

**Gate evidence:** reviewed invariants, race/wakeup proof, agreed resource caps,
experimental selector and lifecycle failure policy. No default change.

### G3 — Integrate and pass focused correctness plus real KVM acceptance

Use deterministic host-I/O fault/delay hooks in the existing test surface, not
unreliable real-disk timing. Verify both synchronous and experimental paths.

| Focused test | Required assertions |
|--------------|---------------------|
| Request contract | Multidescriptor read/write, GET_ID, unsupported type, sector boundary/overflow, invalid direction/status/buffer, cycle/overlong chain; data, status and used length, once only. |
| Faults and flush | Short read with zero-fill, repeated short writes, zero return, error before/after partial transfer, sync failure; delayed write → flush → later write demonstrates no crossed barrier or false durable success. |
| Guest mutation | Change captured descriptor/header/address/length while I/O is delayed; metadata is not reread by workers, no out-of-bounds host access or redirected publication. Test reset/reused heads, queue reconfiguration/disable and ring wrap too. |
| Saturation | Fill request/byte/completion budgets, leave excess avail entries pending, then drain/refill without a new notify. Large requests make bounded progress and no duplicate/drop/spin occurs. |
| Wake races | Completion before KVM entry, at entry, inside blocked KVM/HLT, during pause and around resume/reset. It makes progress with **no new heartbeat or periodic polling** in CLI and API modes. |
| Lifecycle | Pause/snapshot with delayed read/write/flush, deadline failure, resume and restore: no post-ack mutation, consistent image/memory/indices/IRQ, data observed after actual guest execution. Old-generation completions cannot affect restored memory. |
| Cleanup/isolation | Reset/shutdown/partial init/fallback/restore failure: old writes drained, workers joined before unmap/FD close, FD/thread counts return to baseline. Run jailed with enforced seccomp and CPU/memory/I/O limits; no filter bypass. |

Use unit tests for exact error/ordering interleavings; extend
`vmm/src/integration_tests.zig` with disk+agent fixtures for real guest acceptance.
Test idle-KVM wake without the compiler fixture's heartbeat, and terminal
HLT/save-on-halt drain independently. Existing seven integration tests primarily
cover boot/API/lifecycle and do not establish async block correctness.

Keep snapshot format v2, with drained host work. Restore old synchronous
snapshots in the candidate and candidate snapshots in force-sync; reopen
backends and assert disk content, resumed workload, queue/IRQ progress and
agent reconnection, not just a `Running` response. Also exercise SDK snapshot/
checkpoint disk copying when its provisioned fixture is actually supported.
Document unavailable CONNECT/forward/transfer or installed-image coverage as
blocked, never passing or repaired incidentally.

Proposed validation commands, **for implementation time**, after G0 removes
the hardcoded external kernel prerequisite:

```bash
zig fmt --check vmm/build.zig vmm/build.zig.zon vmm/src
(cd vmm && zig build test -Dtarget=x86_64-linux -Doptimize=debug --summary all)
(cd vmm && zig build test -Dtarget=x86_64-linux -Doptimize=safe --summary all)
(cd vmm && zig build install integration-test-build -Dtarget=x86_64-linux -Doptimize=safe -Dintegration-kernel=../.perf/blk-io/fixture/bzImage --summary all)
(cd vmm && zig build integration-test -Dtarget=x86_64-linux -Doptimize=safe -Dintegration-kernel=../.perf/blk-io/fixture/bzImage --summary all --color off)
```

Preflight real `/dev/kvm` open/VM creation and kernel/fixture tools under the same
non-root identity used by the tests. Require every required KVM case to execute,
successful guest markers and passed/expected test counts. Reuse the CI
skip/incomplete-summary rejection pattern; a compile-only or skipped suite is
not acceptance. Run directly affected TypeScript fixture tests only if SDK/
runner integration changes; do not use the unrelated full suite as a substitute.

### G4 — Reprofile and decide whether another prototype is justified

Repeat G1's exact profiles, matrix and frozen gates for the correctness-qualified
worker, including total worker/kernel CPU and final writeback drain. Compare
unprofiled paired confidence intervals; retain failures and outliers.

Only if worker results reveal a specific remaining bottleneck worth attacking,
consider io_uring. Record host/kernel/policy and supported operations, ring/
buffer/FD limits, completion wake, ordering/cancellation and kernel io-wq
accounting. Existing seccomp kills its unlisted syscalls: approve a narrowly
scoped mechanism or declare it unavailable, not disable the filter. Avoid
SQPOLL by default. Repeat G2/G3 and **all** measurement/rollback gates for a
ring candidate; do not transfer worker correctness results to it.

Optionally repeat on a non-nested KVM host with its own manifest. Report absence
explicitly; do not normalize away Azure steal time/nesting or compare unlike
storage/cache conditions as proof of a backend improvement.

### G5 — Keep/reject, default gate and rollback

Write a report linking raw artifacts, capability omissions, gate values,
confidence intervals and the profiled mechanism. Choose keep synchronous,
experimental opt-in only, or enable a proved backend by default. Any unmet
correctness/isolation gate, mandatory blocked workload, unaccounted kernel cost,
noise failure or regression keeps the synchronous default.

Test force-sync across fresh boot, CLI/API restore and snapshot/checkpoint.
Rollback quiesces/shuts down the experimental VM and starts force-sync from a
consistent compatible snapshot/image; it is not a live mid-request backend
switch. Retain the synchronous implementation and diagnosed capability fallback.
Update this spec/plan with actual results only then; move the implementation plan
to completed when its acceptance/decision evidence is complete.

## Proposed measurement recipe

All commands below are **future measurement proposals**, not actions taken by
this planning change. Store fixture/scratch/output under `.perf/blk-io/` in the
checkout, with private permissions; copy the final scripts/raw profiles to a
durable private artifact store and retain checksums/build symbols. Do not run
benchmarks concurrently with other agents' experiments on a shared host.

### Fixture, boot and supported interfaces

```bash
umask 077
mkdir -p .perf/blk-io/fixture
curl --fail --location --retry 3 --max-time 120 \
  https://github.com/joshuaisaact/hearth/releases/download/kernel-5.10.245/bzImage \
  --output .perf/blk-io/fixture/bzImage
echo '4da539807474d189f1a15852046994e78d430a194c2e78b9255ae880069c7208  .perf/blk-io/fixture/bzImage' | sha256sum --check
(cd vmm && zig build -Dtarget=x86_64-linux -Doptimize=safe --summary all)
```

Capture the baseline binary before building a candidate in an isolated worktree.
Build the verified initramfs/image at G0; generate its lock manifest, prefill
test data and make a fresh private disk copy for each paired run using the same
copy/reflink policy. Do not time provisioning as I/O throughput.

The runner launches the selected binary with existing
`taskset -c <allowed-cpu-set> <flint> --api-sock <short-project-socket-path>`
from its run directory. Configure via `curl --unix-socket "$API"` with checked
HTTP status, in this order:

| Endpoint | Body |
|----------|------|
| `PUT /machine-config` | `{"mem_size_mib":512}` (or the separately frozen package/build sizing) |
| `PUT /boot-source` | Verified kernel/initrd paths; `boot_args` set to `console=ttyS0 reboot=k panic=1 pci=off rdinit=/init` for the initramfs fixture, or `console=ttyS0 reboot=k panic=1 pci=off init=/sbin/init root=/dev/vda rw` for the verified disk-root image |
| `PUT /drives/disk` | `{"drive_id":"disk","path_on_host":"disk.ext4","is_root_device":false,"is_read_only":false}` |
| `PUT /vsock` | `{"guest_cid":100,"uds_path":"<short-run-vsock-path>"}` |
| `PUT /actions` | `{"action_type":"InstanceStart"}` |

For jailed acceptance, stage the same verified files under a project-local jail
root and rebase all paths to that namespace; do not bypass the jail for profiling.
Bind/listen at `<uds_path>_1024` **before** start: the guest connects to that
listener. Messages are little-endian u32-length-prefixed JSON. Verify `ping`;
use existing `exec` (`cmd`, timeout in seconds) or `spawn` (`cmd`, `interactive`)
and base64 stdout/stdin frames. No CONNECT command is needed or supported for
this control path. Avoid concurrent commands on its single dispatch channel.

The minimal fixture mounts `/dev/vda` at `/mnt`. The representative fixture
boots `/dev/vda` as its root and stages inputs at `/mnt/packages` and
`/mnt/build-src`. Verify filesystem/device mappings for fio data and package
installation destinations: installing into an initramfs is not a block workload.
Launch disk/package/build load in the guest background with stdin detached and
output/status redirected to fixture files, then probe exec. For a separate PTY
window, spawn an echo-disabled shell read/reply loop that returns `ACK:<unique
token>`; measure the reply, not the terminal's own echo. Send keepalive at the
existing supported interval while the PTY is open. Use independent measurement
windows for exec and PTY, not unsupported command multiplexing.

### Workload matrix and sampling

The following are guest commands, after G0 verifies fio's `libaio` engine and
`/mnt/perf/data` has been fully written (not a sparse/unwritten extent).
Run each case with isolated output names and the same arguments on both sides:

```bash
fio --name=randread-qd1 --filename=/mnt/perf/data --size=1G \
  --rw=randread --bs=4k --ioengine=libaio --direct=1 --iodepth=1 --numjobs=1 \
  --time_based=1 --ramp_time=10 --runtime=60 --randrepeat=1 --randseed=12345 \
  --lat_percentiles=1 --percentile_list=50:95:99 --output-format=json+
```

- Repeat random **read and write** at QD1, QD8 and QD32 with separate case names,
  `--rw=randwrite` for writes and actual depth distribution retained. If the
  verified image needs another engine, freeze/document its equivalent before
  baseline; do not silently substitute a QD1 engine for higher-depth tests.
- Sequential read/write: `--rw=read`/`write`, `--bs=128k`, QD1 and QD16.
- Flush-heavy: `--rw=randwrite --bs=4k --ioengine=sync --iodepth=1 --fdatasync=1
  --end_fsync=1`, retaining fio sync latency and host flush counts as well as
  write latency. Check actual VirtIO FLUSH activity.
- Compare guest direct and buffered/cache strata. `--direct=1` bypasses the
  **guest** cache, not Flint's buffered host FD. Use a working set exceeding
  guest RAM and a separately sized host-cache-pressure case when storage
  permits. Record host page-cache/writeback behavior.
- Package/build: preloaded pinned `.deb` closure with a verified offline
  `dpkg -i <explicit-package-list>` command; fixed source/toolchain with
  `make -C /mnt/build-src -j1 clean all` or a predeclared representative
  equivalent. Freeze exact input hashes/commands at G0. Reset image state each
  run; report command elapsed time, bytes/I/O and interactive load probes.
- Concurrent VMs: repeat the declared random/flush and representative cases
  with 1, 2 and 4 independent VMMs/disks, explicit CID/socket/CPU assignments.
  Include both fixed-total-CPU and per-VM-pinned strata where the host permits;
  compare like for like, report aggregate and per-VM fairness/tails.

Start with ten paired fresh-run repetitions per cell, alternating seeded
baseline/candidate order, 10 s warmup and 60 s measured load. Run baseline/
baseline pairs first to estimate noise; increase duration/repetitions equally
if needed. Collect at least 10,000 request/interactive observations for each
reported tail metric across repetitions. Collect at least 100 lifecycle samples
across ten independent boots for median/p95 confidence; package/build elapsed
time has at least ten independent samples. Increase samples if gate confidence
is inconclusive; do not invent precise p99 for low-rate package/lifecycle cases.
Probe exec/PTY at a predeclared jittered target of 20 requests/s with at most
one outstanding request; extend equal windows if slow replies reduce samples.
Use monotonic host timestamps and retain individual interactive observations,
timeouts and complete fio JSON+ distributions/operation counts.

Report no-load, loaded, idle-after-load and lifecycle cases. For each load,
pause while work is demonstrably in flight, time PATCH acknowledgement and
snapshot separately, then disk artifact copy, resume/reconnect and restore.
Use existing `PATCH /vm` Paused/Resumed and `PUT /snapshot/create` with **relative
basenames**, and CLI `--restore --vmstate-path ... --mem-path ... --disk ...
--vsock-cid ... --vsock-uds ... --api-sock ...`. No invented pause/snapshot API.

Warm-cache runs precondition identically. Cold runs require a documented
per-image eviction/reboot strategy or an authorized **dedicated-host** cache
reset before a run; never drop global caches on a shared host. A fresh guest/
disk copy alone is not proof of cold host cache. Flush/drain before stopping CPU
accounting so buffered writeback cannot move cost outside the measured window.

### Host perf and attribution

Set `OUT` to the current private run directory, `PIDS` to all workload VMM PIDs
(comma-separated), and `MEASURE_SECONDS=60`. Attach after all expected userspace workers
are created; retain before/after TID inventories and cgroup CPU/I/O counters to
verify coverage, including API/runtime threads. Record `perf list --details`,
PMU probe output, `perf_event_paranoid`, tracepoint formats and permissions.
These are representative supported perf commands; select only **verified**
events and retain explicit diagnostics for unavailable ones:

```bash
perf stat -x, -o "$OUT/perf-stat.csv" \
  -e task-clock,context-switches,cpu-migrations,page-faults \
  -p "$PIDS" -- sleep "$MEASURE_SECONDS"
perf record -q -e cpu-clock -F 199 -g --call-graph dwarf \
  -p "$PIDS" -o "$OUT/perf.data" -- sleep "$MEASURE_SECONDS"
perf report --stdio --percent-limit 0.5 -i "$OUT/perf.data" > "$OUT/perf-report.txt"
perf buildid-list -i "$OUT/perf.data" > "$OUT/buildids.txt"
```

Add cycles/instructions only after successful host PMU probing; otherwise retain
software events above. Preserve binary/debug information and symbol resolution/
lost-sample diagnostics. Do not try guest hardware counters: CPUID hides PMU.
Use separately profiled repeats for the following captures:

```bash
perf sched record -a -o "$OUT/sched.data" -- sleep "$MEASURE_SECONDS"
perf sched timehist -i "$OUT/sched.data" -p "$PIDS" > "$OUT/sched-timehist.txt"
perf record -a -o "$OUT/io.data" \
  -e syscalls:sys_enter_pread64 -e syscalls:sys_exit_pread64 \
  -e syscalls:sys_enter_pwrite64 -e syscalls:sys_exit_pwrite64 \
  -e syscalls:sys_enter_fdatasync -e syscalls:sys_exit_fdatasync \
  -e block:block_rq_issue -e block:block_rq_complete -- sleep "$MEASURE_SECONDS"
perf script -i "$OUT/io.data" > "$OUT/io-events.txt"
perf record -a -o "$OUT/kvm.data" \
  -e kvm:kvm_exit -e kvm:kvm_entry -- sleep "$MEASURE_SECONDS"
perf script -i "$OUT/kvm.data" > "$OUT/kvm-events.txt"
perf record -q -a -e cpu-clock -F 199 -g --call-graph dwarf \
  -o "$OUT/system.data" -- sleep "$MEASURE_SECONDS"
perf report --stdio -i "$OUT/system.data" > "$OUT/system-report.txt"
```

If one listed tracepoint is absent, construct the capture from the available
set and record the missing row; do not fail all software profiling or label a
missing event as zero. Use `perf kvm stat record/report` additionally only where
its expected tracepoint set/tool support is verified. Pair entries/exits by
vCPU TID/reason and distinguish guest execution, ioctl/exit handling and HLT
wait. Pair syscall enter/exit by TID; combine scheduler captures for on/off-CPU
and runqueue wait. Block events may be merged, cached, remapped or uncorrelatable
to individual guest requests; retain backing major/minor/mapping and describe
what can actually be attributed.
Include ioctl and candidate synchronization/submit syscall tracepoints in the
verified set when available; report counts and measured overhead per completion,
not just syscall duration or KVM exit totals.

Process attachment **does not include all kernel workers**. Capture system-wide
stacks/scheduling on every CPU kernel I/O may use, including io-wq/kworker/IRQ/
writeback, plus matched idle windows and `/proc/stat`/cgroup deltas. Correlate
device, process, time interval and completion/drain counts; separate unrelated
host work. Do not count total per-CPU cpu-clock as busy CPU or double-count
process system time and kernel-worker time. Report process/cgroup CPU and total
attributable CPU/completion; bound ambiguous kernel cost with whole-window busy
CPU above the matched idle control. If that bound could fail the frozen CPU
gate, repeat on a quieter reserved host or declare the result inconclusive.

## Parallelizable subwork and likely files

These are execution-time work units, not a request to spawn agents now.

| Unit | Real prerequisites | Likely files / responsibility |
|------|--------------------|-------------------------------|
| Inventory | None | Read `main.zig`, `blk.zig`, `mmio.zig`, lifecycle/jail; record source/environment manifest. |
| Fixture/protocol runner | Inventory | Proposed `tools/perf/blk-io.py` and fixture manifest/scripts; pinned offline inputs and control/PTY probes. |
| Perf collector/analysis | Inventory | Proposed `tools/perf/` collectors; raw events, scheduling/kernel accounting and criteria calculations. Can run in parallel with fixture work; baseline execution needs both. |
| Baseline + criteria | Verified fixture and collectors | G1 artifacts and predeclared gates; prerequisite for **all** backend implementation. |
| Bounded I/O core | G2 agreed contract after baseline | `vmm/src/devices/virtio/blk.zig`, optional adjacent worker/request module; staged request execution, barriers and bounded storage. |
| Wake/lifecycle owner | Same G2 contract | `vmm/src/main.zig`, `devices/virtio/mmio.zig`, `queue.zig`, `api.zig`, `snapshot.zig`; submission/publication, kick races, reset/quiescence and cleanup order. |
| Fault tests + isolation preparation | Same G2 contract | `vmm/src/tests.zig`, adjacent fault harness, `seccomp.zig` tests; prepare in parallel with core/owner work. Runtime validation waits for integration; `jail.zig` changes only if narrowly necessary. |
| Integration/acceptance | Core + owner + test/isolation integration | `vmm/src/integration_tests.zig`, `vmm/build.zig` for project kernel selection; `.github/workflows/ci.yml` only for coupled fixture/coverage enforcement. SDK `src/sandbox/sandbox.ts` and `src/vm/snapshot.ts` are inspection/fixture surfaces, not presumed production changes. |
| Comparison/decision | G3 correctness acceptance | Repeat collectors, optional conditional ring work, results/spec/plan update and rollback evidence. |

Core, owner and tests share interfaces: agree them at G2, work in isolated
worktrees and integrate together before KVM acceptance. Avoid treating test
execution as independent of the implementation it validates. Do not edit
shared indexes as part of this issue's isolated planning work.

## Risks and completion checklist

Principal risks: notification/idle-vsock confounding, guest/host caching and
deferred writeback hiding stalls; lost wake or starvation while KVM blocks;
untrusted mutable request state; flush reordering; disk mutation after pause;
uncancellable host I/O delaying quiescence; restore use-after-unmap; jail-killed
capability probes; extra worker/kernel CPU and oversubscription across VMs.
Mitigate through the controlled baseline, explicit ownership/generations,
fail-closed lifecycle, fault tests and total-system profiles above.

- [ ] G0 fixture/capabilities, exact toolchain/source/environment manifest and durable raw-artifact recipe verified.
- [ ] Synchronous baseline stat, stacked record/report, syscall/I/O/scheduler and available KVM attribution retained.
- [ ] Baseline-derived numeric gates, noise bounds, budget and primary metric frozen **before** prototype selection.
- [ ] G1 keep/reject recorded; worker chosen only on evidence; io_uring considered only conditionally.
- [ ] Bounded admission/staging, correct completion wake without polling, ordered flush and request/error semantics proven.
- [ ] Reset/restore generations, quiesce/drain and all cleanup paths tested without stale completion or leaks.
- [ ] Enforced jail/capability diagnostics/synchronous fallback accepted with no broadened isolation.
- [ ] Required real KVM tests execute; old/new snapshots and actual resumed guest data/IRQ/control progress verified; no skipped-as-passing coverage.
- [ ] Required disk, package/build, interactive, concurrent, idle and lifecycle matrix compared with total CPU/kernel cost and repeated variance.
- [ ] Nested Azure evidence retained; optional non-nested comparison or explicit unavailability documented.
- [ ] Measured final decision and limitations published in artifacts/docs; default stays sync unless all gates pass.
- [ ] Force-sync rollback verified and implementation plan moved to completed only after its decision/acceptance evidence exists.
