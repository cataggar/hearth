# VirtIO eventfd experiment tools

## Label-only ephemeral hosted alternative

`.github/workflows/perf-virtio-eventfd.yml` is a separate, bounded hosted
experiment, not ordinary push CI. Only the **parent** applies
`perf-qualify-virtio-eventfd` to same-repository PR9 on
`copilot/perf-virtio-eventfd-20261004`. `pull_request:labeled` is its only
trigger; immutable head checkout, read-only contents permission and
`persist-credentials: false` exclude fork/untrusted/persistent-runner paths.
Do not apply the label from this runner or enable auto-merge.

`hosted.py` rejects mismatched/dirty source and verifies actual scalar Azure
IMDS identity (only `vmSize`/`azEnvironment`, no IDs/tags/IPs), nesting,
nonroot KVM API12/VM creation and notification capabilities. Available
guest-exposed package/core/SMT topology selects independent VMM/client CPUs;
hidden physical host placement and quietness are not assumed. User/root
software/PMU/trace probes and private network namespace availability are
recorded. Missing identity, resources or tools is blocked, never skipped.

The signed Zig0.17 install and hash-checked5.10.245 kernel match existing CI.
Both Debug/Safe must actually execute70 current Zig tests and three full-jail
cases each; no cached/skipped subset satisfies the counts. All measurements
then use **one** Safe static-musl binary, fixed deterministic combined/native
fixtures, default compiler choice and private caches. No sibling backend,
compiler override, cache drop or host security/NIC setting is imported.
The ordinary-jail fixture sleeps and is not timer-free liveness evidence.

Preregister unchanged gates and five paired blocks, then run five complete
17-class C00 A/A matrices (nonidle≥5s, idle60s). Noise failure stops candidates.
Only after a frozen noise-provisionally-acceptable receipt run primary C00
stat/stacks/trace, five C00+rotated-C10/C01/C11 blocks and matched candidate
profiles. Report p50/p95/p99, throughput, precisely bracketed visible-host
busy CPU and paired95% log-ratio intervals. `/proc/stat` sums only
user+nice+system+irq+softirq; guest is already included once. No `-a task-clock`,
guest double count, background subtraction or physical Azure hypervisor claim.
The same completed-operation count maps to the explicitly marked window,
including a fixed100ms zero-new-operation completion tail; boot/warmup is
excluded. Owned-task CPU is separate detail, never added again. Optional
BPF is used only in profiles, not unprofiled primary matrices/scaling.
Separate eligible userspace notify returns/IRQ ioctls from kernel exits and
non-VirtIO serial; event loss/missing owned samples rejects attribution.

As the bounded resources permit, perform one active mixed snapshot/fresh
restore per mode and1/4/8-sandbox pure-native60s HLT-idle/wake/concurrency
cells. These are actual partial acceptance, not20 captures/mode, old/new
compatibility, full mixed scaling, save-on-halt or storm qualification.
Dispatcher/scheduler/softirq detail outside tagged functions remains
unattributed, but **visible-host busy total includes its executed CPU**.
Before/after no-VM5.1s controls for every matrix (60s for native idle) give
repeated background bounds. Counter/read precision and the conservative
background95%/observed envelope are added as sensitivity uncertainty to
the paired ratio, never subtracted from measured CPU. If the bound could
hide the10% benefit or5% regression limit, the result is inconclusive/red.
This can qualify visible CPU on an actually isolated/quiet hosted runner,
not close outstanding lifecycle/mixed-scaling/storm coverage.

The hosted job has a180-minute ceiling,165-minute outer experiment bound,
160-minute internal deadline and4GiB build/3GiB workload capacity guards.
The added budget covers the new measured background controls; no evidence
or frozen numeric gate is reduced to fit. Insufficient time stays blocked.
Every VM/control/collector is bounded and owned. Local validation still uses
the shared vm31e fleet lock; hosted execution uses an isolated ephemeral VM,
not the shared filesystem/runner. No qualified result is yet available:
**workflow ready is not execution**; parent labeling remains a prerequisite.

Only `.perf/eventfd-hosted/public/*.json` is uploaded (14-day retention).
Receipts contain pins, sanitized operations/counters/owned rosters, phase
counts and failure hashes, owned stack symbol reports and decoded attribution.
Private raw perf/serial/VM files are not uploaded; neither are guest memory/
disks, environment dumps, cloud resource identifiers or foreign inventories.
Manifested same-source/full-jail and explicit snapshot/input image leaves are
hashed then removed only after ownership/regular-file checks; symlinks and
unnamed files are never deleted.
`sha256sums.json` seals the receipt set even after interruption/setup failure.
The job deliberately returns nonzero for negative/incomplete qualification;
successful individual cells never mean default/merge eligibility.
Historical vm31e archives are unchanged and must not pool with this epoch.

`run.py` preserves historical **untouched L0** collectors. New controlled
runners implement C00/C10/C01/C11 on one binary; current Flint is never relabelled
as the untouched baseline. Failed operations/profiling return nonzero; a timeout
has no finite speedup. Host-initiated `CONNECT` is unsupported. The unchanged
agent connects to `<uds-prefix>_1024`, with its existing50ms interactive limitation.

Every build, test, fixture preparation, VM/profile, compression and install
must use the shared exclusive fleet lock, bounded commands, this worktree and
umask077. Release between phases; never hold it while idle:

```sh
cd /d/hearth/.perf/worktrees/virtio-eventfd
umask 077
timeout 300 flock -x /d/hearth/.perf/fleet/host.lock \
  env ZIG_GLOBAL_CACHE_DIR="$PWD/.perf/eventfd/cache" \
  sh -c 'cd vmm && zig build test eventfd-test integration-test \
    -Dtarget=x86_64-linux-musl -Doptimize=ReleaseSafe \
    -Dintegration-kernel=../.perf/eventfd/fixtures/bzImage --summary all'
timeout 60 flock -x /d/hearth/.perf/fleet/host.lock \
  python3 -m unittest discover -s benchmarks/virtio-eventfd -p 'test_*.py'
```

The validated experimental binaries are static musl. Debug uses the same command
with `-Doptimize=Debug`. Host-glibc thread setup actually failed on syscall28:
it is not validated, and unnecessary `madvise` was not permitted to hide failure.
The kernel SHA256 is pinned in `run.py`. The deterministic Python `newc` writer
records kernel, agent, BusyBox, init and archive hashes without a bsdcpio
dependency. `--heartbeat-ms 10` makes a separately labelled diagnostic fixture,
never no-heartbeat acceptance.

## Implemented controlled runners

Flint's internal `--virtio-mode L0|C00|C10|C01|C11` retains L0 as default.
C00 has the same per-device blocking owners, validation, publication, budgets
and v2 lifecycle as the accelerators. C10 changes kicks only; C01 changes
completion delivery only; C11 enables both. Unsupported capabilities or
registration failures are explicit, never silent downgrades. No SDK selector
is added. The frozen L0 ELF is a separate immutable asset.

With the previously prepared pinned fixtures:

```sh
timeout 120 flock -x /d/hearth/.perf/fleet/host.lock \
  python3 benchmarks/virtio-eventfd/control.py \
    --out .perf/eventfd/example-control --mode C00 \
    --binary .perf/eventfd/w2/modes-19/ReleaseSafe/flint \
    --fixture .perf/eventfd/fixtures/agent-hb0 --disk --active-disk \
    --shutdown-paused
```

Every output directory must be new/exclusive; never overwrite a baseline.
Historical build19 hashes remain the historical performance pins. Fresh
post-cleanup A/A instead uses separately frozen corrected Safe d0beacf;
current correctness-only Safe8f1ca382/Debugccd6f4fb must not relabel those
measurements. New sustained nanosecond-accounted windows cannot pool with
old short/tick windows. Fresh13/16-class noise failure prevents candidate
performance collection. The shared-filter
follow-up builds a separate binary under `.perf/eventfd/w5/shared-filter/`;
its fresh correctness runs do not reclassify the old performance captures.

* `control.py`: actual enforced-jail native/agent/disk/PTY, active pause/v2
  snapshot/resume, direct CLI restore, or API snapshot-load followed by
  `InstanceStart`. `--restore-api` needs `--restore-from`; `--cli-only`
  disallows API lifecycle actions.
* `matrix.py`: deterministic combined fixtures and concurrent synchronous
  block, userspace TAP, native vsock and unchanged agent. Execution requires
  `sudo -n unshare --net`. Bootstrap creates owned TAP resources only, drops
  controller credentials, and checks every actual VMM task's enforced filter.
  TAP is admitted with the real pre-jail `--tap` argument, not permission
  widening after API configuration.
* `mixed_scale.py`: four/eight real enforced sandboxes, each in its own private
  TAP namespace, sharing the fixed CPU8 VMM budget and CPU1 traffic budget.
  All sandboxes must reach verified outstanding disk/TAP/vsock barriers before
  common release; loaded exec/PTY,128×64KiB messages per transport, pause/resume,
  whole-disk integrity and graceful joins are mandatory. This is correctness,
  not candidate performance, and the unchanged agent still polls every50ms.
  For example, under a bounded fleet lock:
  `python3 benchmarks/virtio-eventfd/mixed_scale.py --out <new-owned-directory>
  --binary <pinned-flint> --fixture .perf/eventfd/fixtures/all-device-perf
  --mode C00 --count 4`. No snapshot image copies or uplink/NAT are created.
* `performance.py`:17 matched classes,60-second idle, raw operation arrays,
  all live VMM task CPU and scoped kernel IRQFD work. Collect C00 repetitions
  first; `--freeze --baselines <directory>` with the same `--binary`,
  `--fixture`, and a new `--out <gates.json>` freezes gates. Candidates require
  `--gates`; failed noise caps are never relaxed. `--long-primary` is a separate
  five≥10-second diagnostic, not retroactive replacement of the frozen policy.
* `profile.py`: owned-TID software stat, DWARF stacks, KVM/ioctl/read/write/epoll
  and scheduler attribution, never unprofiled benefit samples. `--buffer-pages`
  selects a bounded private perf ring without changing global tracing.
  Detected event loss rejects qualifying attribution.
* `connections.py`:16/64 total connections,32 closes/reconnects and slot reuse.
  `scale.py`:1/4/8 native-traffic VMs with an explicit fixed one-core VMM
  budget, not mixed-device scaling qualification.
* `restore_stress.py --prepare-from <combined-fixture> --out <new-fixture>`:
  PID-tracked native apps and reliable triple-fault reboot fixture. Its private
  namespace runner checks20 active mixed captures/fresh-process restores/mode.
  v2 intentionally discards live host streams: unchanged agent reconnect,
  explicit native app relaunch using recorded owned guest PIDs. Bounded
  startup-only TCP retries are not a heartbeat/idle workaround. Successful
  bulky images are removed only after hashes and actual restore receipts.

`tools/perf/irqfd_cpu.bpf.c` / `irqfd_cpu.py` implement an ephemeral
owned-TGID/work-function-filtered kernel CPU observer, requiring verified BPF/
perf privileges, host libbpf and a project-local compiled object. No pinned
maps, foreign task output, global tracefs/security changes or root backend.
CPU covers tagged IRQFD function intervals with off-CPU subtraction;
dispatcher/scheduler code outside those intervals is explicitly unmeasured.
See [actual results](results/20261004/README.md) for pins, losses, frozen noise
and regressions. **No mode is adopted.**

## Historical W0 collectors

```sh
timeout 60 flock -x /d/hearth/.perf/fleet/host.lock \
  python3 benchmarks/virtio-eventfd/run.py prepare \
    --kernel .perf/eventfd/fixtures/bzImage \
    --agent agent/zig-out/bin/hearth-agent \
    --out .perf/eventfd/fixtures/no-heartbeat
timeout 120 flock -x /d/hearth/.perf/fleet/host.lock \
  python3 benchmarks/virtio-eventfd/run.py run \
    --binary .perf/eventfd/fixtures/legacy/flint \
    --fixture .perf/eventfd/fixtures/no-heartbeat --workload ping \
    --cpus 8 --seconds 5 --timeout 1 --profile stat \
    --out .perf/eventfd/results/l0-ping-stat
```

`run` supports idle, checked ping/exec/interactive, native-echo and
native-backpressure; `--profile none|stat|stacks|trace` selects collection.
An owned disk can use `--disk`. This historical subset is not the complete
controlled matrix; unit tests are not guest correctness tests.

`summarize --runs <directories...> --out <JSON>` preserves repetitions,
segregates profiling/heartbeat/workload conditions, computes percentiles and
between-run variance, and fails when any repetition failed. Grouping includes
binary/fixture/runner hashes, payload, timeout, duration, request count, disk
identity and affinities. Unknown metadata is not an explicit value. Different
disk clones are not pooled without golden-image identity.

`--sudo-perf` elevates only bounded collectors/decoders, never Flint/backends.
Software/kernel events can work despite unprivileged/PMU limitations, with no
tracefs/sysctl/driver/host permission changes. Scoped build-ID caches are
project-local; raw permissions stay private.

`zig build eventfd-guest-probe` builds the blocking guest-initiated AF_VSOCK
port11000 fixture. Add `prepare --probe vmm/zig-out/bin/eventfd-guest-probe`
and choose native-echo, with numbered independently checked FNV payloads.
`--payload-bytes` supports8..65536. The probe has no polling timer/heartbeat.
Native-backpressure sends eight messages concurrently, delays reading250ms,
then checks every checksum; failed writers are shut down and joined.
Interactive checks actual PTY output/exit and first-byte timing without changing
the agent. Timeouts retain real failures, never liveness passes.

Runs retain expanded commands, operation arrays, failures, all-task CPU ticks
and before/after thread/affinity rosters. Roster changes invalidate accounting;
tick resolution is recorded and zero short-window CPU is not free I/O.
Aggregate `/proc/stat` controls use the first eight fields to avoid double
counting guest time and report steal. Host nonidle is noise, not backend CPU.
No unrelated PID/comm/stack is inspected. Only owned PIDs/generations and
listeners are cleaned. Preserve private failed runs under `.perf/eventfd/`.

### Native TAP and jail prerequisites

`zig build eventfd-tcp-probe` builds the blocking TCP/FNV guest listener.
`prepare --tap-probe vmm/zig-out/bin/eventfd-tcp-probe` configures
192.0.2.2/30/MTU1500 without guest polling. `run` rejects TCP fixtures.
`tap_probe.py` needs `sudo -n unshare --net`, verifies isolation from PID1,
creates owned `hef3tap0` at192.0.2.1/30/MTU1500/offloads0, and checks actual
UID/GID, empty groups/capabilities, Seccomp2 and NoNewPrivs1 before traffic.
It checks64B and eight64KiB replies before/after two-second silence.
Successful phases survive later failures. No host NIC/uplink/NAT or unrelated
tasks are inspected; owned children join before jail removal.

`tap_probe.py --selftest` instead validates the native protocol on private
loopback as a nonroot host process; that is not KVM/performance acceptance.
The isolation-repaired ELF is a separate prerequisite, not an eventfd speedup.

`analyze_trace.py --run <directory> --out <JSON>` derives addresses/GSIs from
actual diagnostics, distinguishes hardware exits from userspace returns, and
attributes eligible notify returns and IRQ-line ioctls. Clipped pairs are
reported, not invented. Profiled intervals include overhead; interrupt writes
alone prove neither delivery nor integrity.

`probe_jail.py --out <result> --jail <new directory>` verifies the real
post-drop task roster and cleans only the owned PID/start-time generation.
Use `--binary <ELF> --label isolation-control` separately from frozen L0.
`--trace-syscalls` diagnoses SIGSYS without altering the filter. KVM helper
tasks remain in CPU accounting; names are not userspace-owner evidence.
`--api` performs machine/boot/vsock/InstanceStart through actual jailed HTTP
using hermetic `tools/perf/jail_support.py`, never sibling block runners.
`--native-workload echo|backpressure` checks traffic after silence; boot/connect
alone is not successful I/O/lifecycle. No audit mode/permission relaxation.

`tools/perf/test_jail_prerequisites.py` is a standalone regression suite,
without the #1 block runner import. Run nonroot with
`FLINT_JAIL_TEST_BINARY=<absolute pinned ELF>` inside the fleet lock. Actual
bootstrap uses sudo; the API case deliberately seeds supplementary group0
with `setpriv --groups=0`, then verifies empty groups, configured UID/GID,
CapEff0, NoNewPrivs1 and Seccomp2 after the checked privilege drop and real
HTTP traffic. It also verifies root0755 jail directories/configured-user0600
device nodes independent of077 and PID-generation-safe cleanup. The shared
correctness provenance is `f2f9ab4`→`5ee81b1`→`ced7ed72`; these repairs are
not eventfd acceleration.

Client CPUs must exclude VMM CPUs and SMT siblings. Old CPU8/client0 artifacts
remain confounded; controlled CPU8/client1 evidence is separate. Historical
failures and archives remain immutable; no finite stalled-L0 speedup.