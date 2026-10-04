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
in one VM, not four/eight-VM scaling. `--reset` performs three real guest driver
unbind/rebind cycles with new payload checks and owned FD/task observations.
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
report and stacks. SIGINT after peer completion is an explicit normal collector
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
CPU quota delegation was absent. `jail_probe.py` separately reproduces the
still-unrepaired common `/dev`/KVM ownership failure rather than bypassing it.

See [actual results](../../docs/perf-results/vhost-net-20261004.md),
[spec](../../docs/product-specs/perf-vhost-net.md) and
[active plan](../../docs/exec-plans/active/perf-vhost-net.md) for exact commands,
counts, pins and mandatory remaining gates. Full enforced VMM jail, independent
jailed restore isolation, arbitrary injected ioctl/allocator failures, UDP/external/scaling cells and quiet
A/A/performance qualification are not passed. No default or merge is justified.
