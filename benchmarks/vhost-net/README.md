# Original-userspace TAP diagnostic

This fixture is instrumentation for issue #2, **not** a shipped TAP consumer,
SDK networking mode, vhost prototype, or evidence of a performance improvement.
Flint runtime source is unchanged. Internet/proxy/forward/transfer SDK paths use
vsock and cannot benefit from this fixture.

Run from the issue's dedicated worktree on the provisioned nested Azure host:

```sh
bash benchmarks/vhost-net/run.sh prepare
bash benchmarks/vhost-net/run.sh probe
bash benchmarks/vhost-net/run.sh selftest
bash benchmarks/vhost-net/run.sh test
for MODE in rpc h2g g2h wake; do
  bash benchmarks/vhost-net/run.sh boot --boot-id "$MODE-01" --modes "$MODE" --repetitions 4 --seconds 60 --profiles
  bash benchmarks/vhost-net/run.sh boot --boot-id "$MODE-02" --modes "$MODE" --repetitions 3 --seconds 60
  bash benchmarks/vhost-net/run.sh boot --boot-id "$MODE-03" --modes "$MODE" --repetitions 3 --seconds 60
done
bash benchmarks/vhost-net/run.sh quiet
```

Build Flint unchanged first using Zig 0.17.0, `-Dtarget=x86_64-linux
-Doptimize=safe`, inside the same absolute fleet lock. The scripts acquire
`/d/hearth/.perf/fleet/host.lock` exclusively per bounded phase; never call them
from inside another lock. All artifacts use `umask 077` beneath
`.perf/vhost-net/20261004/`. A boot ID cannot be overwritten. Inspect command
exit statuses, raw output and collector errors; successful script exit is not
successful traffic. Keep each boot phase below its 900 s execution bound; split
healthy full-window workloads by case as above rather than batching all cases
and repetitions into one long lock hold. The diagnostic evaluation initially
attempted all four modes together, which failed early rather than filling their
requested windows.
Already-retained fixtures/probes/controls are not overwritten: reuse the pinned
fixture and choose new boot/control IDs for further diagnostic runs.

The supervisor needs `sudo -n` and `unshare --net`; it creates only an ephemeral
experiment namespace, a persistent owner-UID-1000 `hn2tap0` **inside** that
namespace, and `192.0.2.1/30`. There is no host uplink, NAT, bridge or default
route. Namespace deletion follows supervisor/child exit. It uses BusyBox `ip`,
not a host iproute2 installation. Flint and host peers run as UID 1000 with the
existing KVM-group access, on CPUs 8 and 9 respectively; the VMM does not run
as root. The supervisor terminates only its recorded child PID and joins it.
This is jailless baseline instrumentation, not production jail acceptance.

Preparation builds `guest.c` statically with the same pinned Zig compiler's
musl target, copies the host's static BusyBox, and verifies the existing
5.10.245 guest-kernel release hash. It hashes compiler-built peer, BusyBox,
initramfs, kernel, Flint and fixture source. The guest has 1 vCPU/512 MiB,
MTU 1500, three blocking TCP listeners and **no heartbeat or timer wakeup
workaround**. TAP offloads are explicitly disabled. Only Flint's existing
VERSION_1/MAC/STATUS features, two split queues and 12-byte header are offered.
Guest route, interface, queue discovery and TAP counters are retained.

`collect.py` validates each 64-byte sequence/payload RPC, handles partial reads,
and separately drives upload (port 7001) and download (7002). Bulk payload is
an exact fixed `0x5a` stream, with byte count/error acknowledgement; these native
peers are an explicitly pinned alternative fixture, **not iperf3-equivalent
network-loss/retransmission coverage**. Warmup is 10 s; active windows default to
60 s. `wake` sleeps the host peer for 1 s between requests, not the guest. Failed
connect/warmup/active phases are retained; no latency or CPU/unit is invented
for zero completions. Successful-only quantiles must never hide timeouts.
`idle` is a separate 60 s diagnostic.

Profiles use root host-wide software `perf stat` and `perf record -a
--no-buildid-cache -e cpu-clock -F 49 -g --call-graph dwarf,4096`, plus actual
`perf report --stdio`, stacks and direct KVM entry/exit trace recording when the
capability probe succeeds. The initial retained captures used 199 Hz/8 KiB
DWARF and the `perf kvm stat record` frontend; post-provisioning idle captures
hit overload/timeouts/frontend aborts. Their errors remain evidence, not passed
profiles. The current lower-volume configuration is a separately identified
diagnostic, not an interchangeable comparison arm. Build-ID cache updates and
supervisor/child core dumps are disabled locally; no global setting is changed.
KVM reports use `perf kvm -i FILE stat report --stdio`; `-i` is a global
option. This profiler writes report text to stderr, so preserve both streams.
All CPU placement,
process/TID inventories, `/proc/stat`, softirq/softnet and network counters are
retained. Visible-host busy CPU is user+nice+system+irq+softirq divided by
`SC_CLK_TCK`; guest time is already in user/nice. System-wide task-clock is not
treated as busy CPU. Measured-window denominators do not include warmup;
whole-command counters are separately labeled. The shared fleet lock excludes
other agents' VM/build workloads, not all unrelated outer-host background work
or invisible Azure hypervisor activity.

The supervisor currently exercises one VM and original userspace only. It does
not claim UDP, 4/8-VM concurrency, controlled Azure external routing, full idle
tails, malformed queues, IRQ/reset races, vhost fallback, traffic snapshot,
cross-backend restore, CoW or jailed isolation acceptance. Use the
[spec](../../docs/product-specs/perf-vhost-net.md) and
[plan](../../docs/exec-plans/active/perf-vhost-net.md) for those mandatory gates.
No A′/B comparison or backend selector exists here.

`--snapshot` on a selected boot adds a post-workload, vCPU-only
pause/snapshot/resume and captures the actual format-v2 net transport/queue
fields. It writes a private 512 MiB RAM artifact. This is metadata/basic
userspace lifecycle evidence, not traffic snapshot, restore, CoW or kernel-worker
acceptance.

Raw system-wide DWARF perf data can contain unrelated host stack bytes. Keep it
private; do not automatically publish it or raw task inventories. A results
summary and artifact hashes can be committed without exposing those samples.

`selftest` runs the exact native guest peer and collector in a separate host
loopback namespace (no VM/TAP) to check the fixture protocol independently.
`quiet` retains matched 60 s stat/record controls **without a VM**; a saturated
control is a qualification failure, not CPU cost attributable to Flint.
