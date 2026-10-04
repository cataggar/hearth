# VirtIO eventfd experiment: W0 tools

This directory currently collects **untouched L0** evidence, not C00/C10/C01/C11.
Neither eventfd mode selectors nor a reactor have been implemented. Missing
fixtures, failed operations and failed profiling return nonzero; a timeout has
no latency or CPU/op speedup. Existing host-initiated `CONNECT` interfaces are
not used. The unmodified agent connects to `<uds-prefix>_1024`.

Run every build, test, fixture preparation and VM/profile under the shared
exclusive lock. Commands must be bounded, start in this worktree, and use a
private umask/cache; never hold the lock while idle:

```sh
cd /d/hearth/.perf/worktrees/virtio-eventfd
umask 077
timeout 300 flock -x /d/hearth/.perf/fleet/host.lock \
  env ZIG_GLOBAL_CACHE_DIR="$PWD/.perf/eventfd/cache" \
  sh -c 'cd vmm && zig build eventfd-preflight -Dtarget=x86_64-linux -Doptimize=safe --summary all'
timeout 60 flock -x /d/hearth/.perf/fleet/host.lock \
  python3 -m unittest discover -s benchmarks/virtio-eventfd -p 'test_*.py'
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

The kernel SHA-256 is pinned in `run.py`. The Python `newc` writer removes the
host `bsdcpio` dependency without changing the Linux guest format. Preparation
records kernel, agent, BusyBox, init and archive hashes. `--heartbeat-ms 10`
creates a separately labelled **diagnostic**, never a no-heartbeat acceptance
fixture. Guest interactive polling remains 50 ms.

`run` supports `idle`, `ping`, and checked agent `exec`; `--profile` selects
`none`, software `stat`, DWARF `stacks`, or KVM/ioctl `trace`. An existing owned
disk can be passed with `--disk`. This is **not** the required complete disk/
TAP/native-vsock/concurrency/lifecycle benchmark matrix. Do not count the
runner's unit tests as guest correctness tests.

`summarize --runs <run directories...> --out <project-relative JSON>` preserves
all repetitions, segregates profiling/heartbeat/workload conditions, reports
latency percentiles and between-run median standard deviation, and returns
nonzero if any repetition failed. It never infers an acceleration benefit or
freezes gates from this incomplete W0 subset.
Grouping also distinguishes fixture/binary hashes, payload, timeout, duration,
request count, disk path, VM/client affinity and other recorded conditions.
Unknown metadata is not equivalent to an explicit recorded value. Different
disk-clone paths are deliberately not pooled without golden-image identity.

`--sudo-perf` elevates only the bounded diagnostic collector and symbol decoding,
never Flint or its backend. This permits kernel/software-event attribution when
the ordinary account is limited to `:u` events. It makes no tracefs, perf sysctl,
driver or global permission changes. Raw collector files are returned narrowly
to the invoking UID/GID, without widening their private permissions.
Future collectors/decoders explicitly scope the perf build-id directory to the
project as well.

Build `zig build eventfd-guest-probe` from `vmm/` under the same lock to produce
the native guest fixture. Add `--probe vmm/zig-out/bin/eventfd-guest-probe` to
`prepare`, then select `--workload native-echo`. The guest uses blocking
AF_VSOCK reads/writes on guest-initiated port 11000, echoes numbered payloads
with an independently checked FNV-1a checksum, and has no polling timer,
heartbeat, or SDK CONNECT dependency. A timeout is a real failed operation,
not a successful liveness test. `--payload-bytes` selects 8 through 65,536 bytes.

`native-backpressure` concurrently sends eight numbered messages and delays the
reader by 250 ms before validating every echo/checksum. Sending is joined or
shutdown on failure; the receiver never waits for the sender to finish first.
Use 65,536-byte messages to expose stream-buffer backpressure. `interactive`
checks real guest PTY stdout and exit frames, including first-byte timing,
without changing the existing agent's 50 ms polling workaround.

Every run retains expanded launch/perf/report commands, per-operation arrays,
responses/failures, all-thread CPU ticks and before/after thread/affinity
rosters. A changed roster invalidates CPU accounting. CPU tick resolution is
recorded: short samples that round to zero are not evidence of free I/O.
Future runs also retain raw aggregate `/proc/stat` controls around the measured
window and their separate interval. Conversion uses the first eight counters
only, avoiding guest-time double counting, and reports steal separately.
Host nonidle includes steal; it is a noise control, **not** backend CPU.
No unrelated PID/comm/stack data is inspected. A reset counter invalidates the
control. The runner's own hash is recorded and participates in grouping, so
old runs without controls cannot silently pool with new collector conditions.
Profiled and unprofiled repetitions must remain separate. The runner terminates
only its own VMM/profiler processes and removes only its owned listener.
Artifacts are private under `.perf/eventfd/`; preserve failed runs too.

`analyze_trace.py --run <trace run> --out <JSON>` derives device addresses/GSIs
from the actual VMM diagnostics. It separates kernel exits from
`kvm_userspace_exit`, counts four-byte notify writes per queue, and associates
completed IRQ-line ioctl intervals with VirtIO versus serial GSIs. Clipped
ioctl pairs are reported, not invented. Trace ioctl intervals include tracing
overhead; counters do not prove interrupt delivery or descriptor integrity.

`probe_jail.py --out <result> --jail <new private directory>` starts only a
bounded disposable jailed child, verifies the actual post-drop userspace
thread credentials/filter, and removes only its newly created jail. KVM-created
helper tasks such as `kvm-nx-lpage-re` remain included in CPU accounting and the
recorded task roster; do not equate their names with new userspace backend owners.
Use `--binary vmm/zig-out/bin/flint --label isolation-control` to validate the
private-node ownership prerequisite separately from frozen L0. No audit mode
or host permission relaxation is used.
`--trace-syscalls` records only the disposable command's syscall events to
identify actual SIGSYS failures; it does not change the enforced filter.
The post-connect roster is rechecked, and cleanup validates the current owned
PID/start-time tuple rather than signalling stale recorded PIDs.

The client cpuset must exclude the VMM and its SMT siblings, including when
explicitly supplied. Older CPU8/client0 artifacts are retained as confounded
diagnostics, not promotion evidence. See the [actual W0 report](results/20261004/README.md)
for corrected-affinity repetitions, limitations, blockers and durable evidence.
