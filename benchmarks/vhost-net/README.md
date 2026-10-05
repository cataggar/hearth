# Opt-in net prototype correctness and diagnostic fixture

This is issue #2 instrumentation and an **unfinished experimental prototype**,
not a shipped TAP consumer, SDK networking mode or performance improvement.
SDK internet/proxy/forward/transfer still use vsock. The original unrequested
Flint userspace path remains default; `--net-backend userspace` is the common
blocking A′ adapter, `vhost` is strict B, and explicit `auto` permits fully
unwound early capability fallback. Existing guest features/header remain fixed.

All builds/tests/VMs/profiles must use exclusive
`/d/hearth/.perf/fleet/host.lock`, bounded commands, this dedicated worktree and
umask077. `run.sh` already acquires/releases that lock; never nest a lock around
it. Its root supervisor creates private network/mount namespaces and an owned
TAP, without uplink/NAT/default route or host node/ACL changes. Flint and peers
run UID1000 on CPUs8/9; only setup/collection is root. **Unjailed diagnostics are
not production-jail acceptance.** Artifact directories are private and cannot
be overwritten; use short boot IDs (UNIX socket paths must fit108bytes).

Existing baseline fixture/image hashes and failures are retained unchanged.
Existing Zig integration tests accept`FLINT_TEST_KERNEL=<verified project kernel>`;
set it explicitly so validation does not access the legacy kernel location.
The override is test-only, not a Flint/kernel/compiler option or a common
prerequisite runtime change.
`prepare` creates a new current fixture only if none exists; `prepare-reset`
builds a separately pinned control fixture without rewriting the baseline:

```sh
bash benchmarks/vhost-net/run.sh test
bash benchmarks/vhost-net/run.sh selftest --control-id native-new
bash benchmarks/vhost-net/run.sh boot --boot-id b-new --net-backend vhost \
  --repetitions 1 --seconds 2 --warmup .2 --modes rpc h2g g2h wake \
  --traffic-snapshot --restore-backend userspace --concurrent --malformed --profiles
bash benchmarks/vhost-net/run.sh prepare-reset
bash benchmarks/vhost-net/run.sh boot --boot-id reset-new --net-backend vhost \
  --fixture-id fixture-reset --reset --repetitions 1 --seconds 1 --warmup 0 \
  --modes rpc h2g g2h wake --snapshot
bash benchmarks/vhost-net/run.sh boot --boot-id auto-new --net-backend auto \
  --vhost-unavailable permission --repetitions 1 --seconds 1 --warmup 0
bash benchmarks/vhost-net/run.sh strict --boot-id strict-new --vhost-unavailable uapi
bash benchmarks/vhost-net/run.sh resource --boot-id resource-new
```

The native C peer validates64-byte numbered RPCs and exact0x5a bulk streams
with byte/error ACKs. Guest init has no heartbeat/timer workaround. `wake`
withholds host requests for1s; `idle` performs no traffic. Successful quantiles
never erase connect/warmup/active failures. These are not iperf-equivalent
UDP/loss/retransmission tests or deciding performance samples.

`--traffic-snapshot` withholds a reader during an8MiB download, pauses before
ACK, saves RAM twice and requires identical full-file hashes, resumes and checks
all bytes/ACK plus fresh RPC. `--restore-backend` uses format-v2 snapshot/new
RAM mapping, checks RPC/bulk/wake and unchanged MAP_PRIVATE backing. It is not
simultaneous independent-restore isolation by itself. `cow_isolation.py` separately
starts two real KVM vhost restores of one backing file in distinct owned namespaces,
pauses B, drives checked bulk into A and requires B's full RAM and shared backing
to remain unchanged while A's RAM differs. Run it under one exclusive bounded
fleet lock with a root supervisor; it never acquires a nested lock.
For example, after a retained `--snapshot` boot:

```sh
flock -x -w 600 /d/hearth/.perf/fleet/host.lock timeout 180 bash -c '
  cd /d/hearth/.perf/worktrees/vhost-net && umask 077 &&
  sudo -n python3 benchmarks/vhost-net/cow_isolation.py \
    --source .perf/vhost-net/20261004/final-b3 --output .perf/vhost-net/cow-new
'
```

`--concurrent` checks eight clients
in one VM, not four/eight-VM scaling. `--reset` defaults to three real guest driver
unbind/rebind cycles with new payload checks and owned FD/task observations.
`--reset-count` selects1–256 cycles; a requested100-cycle run that fails after30
is a failed whole phase, not100 passing tests.
`--malformed` restores deliberately patched RAM/state into real KVM for
flags/direction/cycle/GPA/header/head/alignment rejection, including `auto`
not silently falling back. Capability controls bind an owned regular file over
vhost **only in the private mount namespace**; shared device permissions remain
unchanged.
`resource` deliberately caps the owned process's FD limit at12/14/15 to force
partial eventfd setup failures in strict/auto; these must be fatal, not fallback.
The initial16-FD calibration unexpectedly allowed setup and timed out after20s;
its raw failure remains retained, not reclassified as a successful rejection.

New profiles attach only to the owned VMM (including its vhost worker) and
owned peer, using root software stat/KVM events and49Hz/4KiB DWARF record,
report and stacks. The peer waits on a private pipe until perf acknowledges
enabled capture; `--rpc-rate` applies to both ordinary and scoped RPC runs.
SIGINT after peer completion is an explicit normal collector
stop, with raw status retained. No new all-host process metadata/stacks are
captured. `probe`/`quiet` historical all-host capture entrypoints are disabled.
Work on unowned ksoftirqd CPUs is not captured/attributed; global aggregate
`/proc/stat`, softirq/softnet deltas retain whole-host context, not a complete
product CPU estimate. BusyCPU is user+nice+system+irq+softirq/SC_CLK_TCK, without
guest double count. All-system task-clock is not busyCPU. Nested physical Azure
hypervisor cost/hardware PMU remain unavailable. Keep historical all-host DWARF
and inventories private; never upload unrelated users' metadata/stack bytes.

## Exact-kernel shadow and confinement probes

`uapi_probe.py --private-rings` demonstrates kernel acceptance of immutable
private vring HVAs outside the GPA table, guest-index poisoning immunity,
trusted used progress, rejected INDIRECT publication, framing, malformed raw
kernel behavior, bounded fence, CoW and close/join/FD cleanup. Nine cases/eight
observations are characterization, not eight product gates. Its original
direct-ring mode deliberately preserves the rejected behavior.

`export_filter.zig` exports the prototype's exact enforced BPF;
`owner_probe.py` installs it after clearing groups/dropping UID/GID1000, creates
an owner-mode kernel worker in a unique memory/pids-limited cgroup, observes
NNP1/Seccomp2/CapEff0/affinity/inheritance and waits for synchronous close/join.
It removes only that owned empty cgroup. It never enables global controllers;
CPU quota delegation was absent. `jail_probe.py` retains original ownership
failure diagnostics and now checks the exact shared prerequisite without
relaxing enforcement: `--expect sigsys --trace` captures an explicitly waited
owned child's signal (a zero profiler exit is not acceptance). `--trace-all`
is still owned-child-only. Strict/auto root-rejection controls use
`--no-jail --uid 0 --expect privilege-drop` in a private namespace. They reject
before VM creation, not demonstrate a working root backend.
Real/effective owner identity is captured after privilege drop before seccomp;
unset/root fails closed without adding a getuid syscall allowance.
The exact shared thread/epoll/legacy-poll follow-up is also reused. Requested
net mode alone permits blocking poll−1 for exactly1,2 or5 readiness descriptors;
17 real enforced child cases check default blocking-poll denial, exact allowed
sets, invalid counts/positive timeouts and retained eventfd/socket/clone/mprotect
restrictions. A unit-only two-second watchdog bounds an accidentally allowed
zero-FD test; the runtime still has no readiness timer or heartbeat.

## Fresh controls and fault diagnostics

`--tap-name` freezes the MAC-derived experiment identity; `--host-controls`
records five-second no-owned-VM aggregate controls before/after join, and
`--sample-label` distinguishes correctness, historical and fresh populations.
`noise.py` validates only the three named fresh A/A boots, then freezes
MAD/median gates and50%/80% RPC rates without reading candidate files.
Global CPU/unit remains unattributed: no idle-floor subtraction or
Flint-only reduction is a product saving.

Run the following only inside a bounded exclusive fleet phase, with a fresh
output path and root private`unshare --mount --net` supervisor:

- `fault_probe.py --output <owned-path>` uses a restrictive notification filter
  for58 real setup faults. Shadow mmap counting starts after the verified owned
  vhost SET_MEM_TABLE marker and requires anonymous/private/fd−1; matching12KiB
  alone also intercepts allocator/KVM_RUN mappings and is invalid coverage.
- `lifecycle_fault.py --output <owned-path>` targets both queues' kick-unbind,
  backend-detach and GET_VRING_BASE after checked traffic in strict/auto modes.
  Pause/resume/snapshot must reject, workers join, no snapshot appears and
  supervisor FD count stays unchanged. A diagnosed fatal exit1 and disconnected
  API is a valid fail-closed rejection only after every recorded owned task
  disappears and the cgroup is empty; a timeout is not rejection proof.
- `reset_diagnostic.py --boot-id <short-id> --backend userspace|vhost`
  samples only its owned cgroup's pids/memory current/peak/events during100
  resets. It does not relax limits or wake the guest.
- `prepare_iperf.py --fixture-id <fixture-iperf-name> --server-console` retains
  a separate installed-library guest closure and server diagnostics.
  `iperf_smoke.py --boot-id <id> --backend <mode> --fixture-id <name>` attempts
  both TCP/UDP directions at three seconds. Its idle collector holds the VM
  open during traffic, so it is **not idle or performance acceptance**.

Recipes are not completed gates. The chronological results retain every failed,
mis-scoped and unrun population, including the first100-reset resource failure
and guest iperf control-socket failures. Canonical common prerequisite
`7dfee42` is reused with standalone`tools/perf/test_jail_baseline.py`; its
three cases do not stand in for TAP/vhost/worker acceptance.

Fresh reset resource observations hit owned pids.max16 with pids.events max1,
without memory/OOM events. The common adapter now avoids spawning a dispatcher
until both queues/DRIVER_OK are ready, retaining any pending IRQ delivery.
This is a lifecycle correction only; old-ELF performance samples cannot be
pooled with rebuilt acceptance or credited as a speedup. Guest iperf state
uses a separate fixture-relative directory; host peers set TMPDIR to their
private artifact directory, never a shared scratch path.
The installed guest closure also includes libgcc_s.so.1, actually needed by
glibc pthread_cancel although omitted from ldd's direct dependency output.
TCP acceptance uses the named receiver summary, not a positive sender-only
counter; retransmissions remain recorded. Three-second smokes are not qualified
performance or an error-rate noninferiority test.

The prior shared5ee jailed credentials retained supplementary group0; the
preserved `jail_probe.py --expect inherited-groups` cases record fail-closed
rejection, not successful network. Exact authorized shared `ced7ed7` now clears
groups before identity drop. `boot --jail` exercises the enforced VMM from a
deliberate inherited-root-group bootstrap, configured private0600 nodes, empty
dropped groups and an owned memory1GiB/pids16 cgroup. It verifies every observed
VMM/dispatcher/vhost task and removes the empty cgroup after join. CPU quota is
not enabled globally. Snapshot files live inside the private jail; restores
use a fresh root and the same immutable backing with new MAP_PRIVATE mappings.
Use distinct short IDs, for example:

```sh
bash benchmarks/vhost-net/run.sh boot --boot-id j-new --jail --net-backend vhost \
  --repetitions 1 --seconds 1 --warmup 0 --modes rpc h2g g2h wake \
  --traffic-snapshot --restore-backend userspace --concurrent
```

Do not use the old diagnosed-failure probe to claim current successful jailed
traffic. Jailed malformed/capability injection uses fresh per-case resources;
unjailed controls are not substitutes. Correctness RAM copies omit verified
zero pages and require unchanged full-file hashes; this is not a new memory
backend or a performance variant. Artifact-write failure cannot prevent empty
cgroup/device cleanup. An explicit `--sparse-correctness-snapshots` reduces only
stored, completed snapshot outputs before the next fence, preserving full
hashes, identity and bytes on copy failure. It requires non-profiled snapshot
correctness; it is not a memory backend, snapshot-latency gain or performance
variant. Consult the results for actually run
populations; command support alone is not acceptance.

`cow_isolation.py --jail --source <snapshot-jail>` tests two simultaneous enforced
restores of that same backing. `capability_probe.py` injects permission/UAPI
faults into only the already-created private vhost node, or FD limits12/14/15
into a fresh jailed CLI. Run each under the bounded fleet lock and a fresh
private namespace. Strict must diagnose the failure without fallback; `auto`
may fall back only before activation and must pass real checked traffic.
All observed tasks are checked for UID/GID1000, empty groups, zero capabilities,
NNP1/Seccomp2, CPU8, owned cgroup and matching actual namespaces. Profiler cache/
scratch paths stay inside the owned artifact directory; debuginfod is disabled.

See [actual results](../../docs/perf-results/vhost-net-20261004.md),
[spec](../../docs/product-specs/perf-vhost-net.md) and
[active plan](../../docs/exec-plans/active/perf-vhost-net.md) for exact commands,
counts, pins and mandatory remaining gates. Basic enforced VMM traffic/lifecycle
and simultaneous jailed restore isolation now execute; these are not complete
production acceptance. CPU quota, arbitrary injected ioctl/allocator failures,
long sustained IRQ/reset/tail populations, UDP/external/scaling cells and quiet
A/A/performance qualification are not passed. No default or merge is justified.
