# Async block I/O: baseline capability results

**Date:** 2026-10-04

**Issue:** #1

**Decision:** **Blocked at G0; keep synchronous. Not eligible for performance merge.**

**Branch:** `copilot/perf-async-block-20261004`

This issue-1 record is imported with the separately authorized shared correctness
prerequisite `f2f9ab4`; its historical paths and integration/harness claims refer
to that branch. Issue-2's actual controls and remaining gates are recorded in
[its own execution evidence](../perf-results/vhost-net-20261004.md).

**Spec:** [perf-async-block-io](perf-async-block-io.md)

**Plan:** [active execution plan](../exec-plans/active/perf-async-block-io.md)

## What was implemented

The integration suite now accepts `-Dintegration-kernel=<path>` relative to
`vmm/`, resolving it before child tests change working directories. The default
and CI fixture use `../.ci/guest/bzImage`; CI no longer installs a kernel outside
the project. README and plan recipes use this implemented option.

`tools/perf/blk-io.py` implements an owned, bounded baseline **capability**
harness: private project-local initramfs/ext4 construction, exact binary/kernel
and dependency manifests, existing HTTP and guest-initiated port-1024 framing,
CLI/API jail probes, startup stat/stack collectors, reports, and offline
analysis. It rejects reused run directories, diagnoses failed commands rather
than counting collector exit status as acceptance, and cleans its recorded
processes and socket paths. Its protocol/cleanup tests are adjacent.

This is **not** the complete workload runner or an asynchronous backend. No
worker, io_uring, experimental VMM selector, force-sync flag, new feature,
notification optimization, snapshot format change, or jail allowance was
introduced in the original diagnostic commit. Those untouched L0 executions
use runtime sources from `b07f73b26b8ae876928d9c515b94bba1e9945870`.
The separately authorized correctness prerequisite below changes only jail
permissions and trace-proven Unix API syscall compatibility, not a backend.

## Frozen source and assets

Execution started at documentation-only base
`b06ec0a6c19b4977bfb602c2daa1d94acf3eacf7`. Zig **0.17.0**, safe optimization,
`x86_64-linux` VMM and static `x86_64-linux-musl` agent were used. The unchanged
safe binary was copied before test harness edits; its hash still matched the
subsequent safe build. Debug tests are validation, not a second perf variant.

| Asset | SHA-256 |
|---|---|
| Unchanged safe Flint | `05e8308cf5eb7243aa0bffecb2b2f91c91c6afcb244d489653f3c7eed4e1210a` |
| Unchanged safe agent | `ebf85c7132bc1ead32e48dc1f066630763fa6524a4d5e515f66ad789072b58d1` |
| CI kernel 5.10.245 | `4da539807474d189f1a15852046994e78d430a194c2e78b9255ae880069c7208` |
| Capability initramfs | `ee9f34a1eaf6b80ce02018e4eed1c3fe39ceeaef820e8bf7f2a0baabed328727` |

The resolved translate-c pin remains
`62d06a5d3e93c82727544e8113e4762a315ca0ed`,
`translate_c-2.0.0-Q_BUWlpOBwBWvgGBM20tJq-GXgPio3v3UD39rXEn70KN`;
Aro remains `d0c8c4d9c55daa7ef6e40cf0f630a5b5e900989b`,
`aro-0.0.0-JSD1QtuBNwCASyBtNF3pqTl_W3oAJQGEVyFAtrBSE_Pa`.
Actual dependency archive/manifest hashes and manifests are retained. No
dependency/compiler/guest feature settings or another optimization's runtime
patches were adopted.

Host: nested Azure `Standard_D16ds_v5`, 16 logical Intel Xeon Platinum 8370C
CPUs, Linux `6.18.31-1.3.azl4.x86_64`, UID/GID 1000, `kvm` membership.
Probes pin to CPU 8, one vCPU, 512 MiB RAM, one 8 GiB ext4 image. The capability
image has **no prefilled 1 GiB fio data**. The verified Ubuntu base download is
retained as a provisioning input, not a provisioned package/build fixture.
Filesystem/mount details, tool versions, source diff and full commands are in
the manifest. Zig caches and scratch are private and project-local.

## Untouched L0 blockers and alternative probes

1. **Enforced-jail API fails before boot.** Jail entry and the kill filter
   succeed. The first `PUT /machine-config` resets its HTTP connection. Private
   strace 5.16 shows `accept4` followed by **`recvmsg`, syscall 47, killed by
   SIGSYS**. That syscall is absent from the unchanged filter. Higher-frequency
   stacked software profiles also capture `__seccomp_filter` /
   `force_sig_seccomp`. No guest or block queue was running.
2. **Enforced-jail CLI fails before VM creation.** Using the same verified
   assets and existing CLI instead of the API reaches
   `openat("/dev/kvm", O_RDWR|...) = -1 EACCES`. Required `umask 077` turns the
   unchanged jail's `mkdir(0755)` into root-owned **0700 `/dev`**, and
   `mknod(0666)` into root-owned **0600 `/dev/kvm`**. After dropping UID/GID,
   Flint cannot traverse/open them. Exact post-exit modes are retained. This
   is not lack of host KVM: non-root host preflight obtains API 12 and creates
   a VM, and the existing unjailed KVM tests execute.
3. **Historical host-load limitation.** A locked five-second idle capability control
   observes **99.938% whole-host busy CPU**, with 0% iowait/steal in that window.
   Previously running, unowned PPID-1 shells are in runnable state with roughly
   16-hour histories. They were not killed, rebound or otherwise modified.
   This control includes external work, not attributable kernel I/O CPU.

Neither disabling/auditing the filter, changing global security/cache settings,
weakening the required umask, nor borrowing a different runtime was used to
make the mandatory jail row pass. The root collector/tracer operates on owned
VM processes; guest/VMM startup still uses the enforced jail and drops to 1000.
No root or permission changes were applied to the host `/dev/kvm`.

There were **13 pre-provisioning jailed attempts**, all blocked before guest execution: two
initial API/CLI probes, an eight-probe traced/stat/record series, and three
higher-frequency record repeats. The repeated failures are capability evidence,
not successful baseline performance cells.
Two additional post-readiness attempts below bring the total to **15**; none
reached guest execution.

An additional **unjailed, unprofiled capability diagnostic** verifies that the
same fixture really boots kernel 5.10.245, mounts `/dev/vda` as ext4 at `/mnt`,
and executes through the actual guest agent. A marker write, guest `sync`, and
read/hash check passes with SHA-256
`a3191b34e8dc751b079d55ddfef835ec16c80c74e510376f7b46737c0528624e`.
Guest block stats change from 6 to 13 reads, 1 to 17 writes, and 1 to 3
completed flushes. After the VM exits, host `debugfs -R 'cat /probe.txt'` on
its backing image produces the same verified hash; the marker is not merely
observed from the guest cache. This isolates the mandatory jail failures from
fixture or host-KVM failure. It **does not bypass the jail for profiling** and does not
qualify disk throughput, durability under faults, loaded interaction, or
disk/agent snapshot restore. Its existing 10 ms serial heartbeat is recorded;
it proves no asynchronous idle-wake behavior.

## Post-provisioning boundary — 16:01 UTC

Common tooling was provisioned by the parent **after the capability captures
above**. A short, separately locked inventory at `2026-10-04T16:01:42Z` verifies:

| Tool/library | Observed version / package |
|---|---|
| Node / npm | `22.22.0` / `10.9.4` |
| iproute / libbpf | `6.14.0` / `1.6.1` |
| fio | `3.40`; host `--enghelp=libaio` succeeds |
| iperf3 | `3.19.1` |
| glibc | `2.42-10.azl4` |
| libaio | `0.3.111-23.azl4` |
| liburing | `2.12-2.azl4` |

Exact executable paths, RPM versions, engine-help output and library inventory
are retained in `.perf/blk-io/post-provisioning/tools-libraries.txt`. `ldd` reports
the preserved Flint executable is not dynamic. No additional tool installation,
VM workload or profiling run was performed by this inventory.

**The original captures are pre-provisioning capability evidence,
not a fully controlled comparison or frozen performance baseline.** The
99.938% busy control is a historical five-second window, not an assertion of
current host utilization. Neither that window nor the startup counters may
establish post-provisioning A/A noise, margins or a gain.

Host tools being available does not provision/verify them inside the guest,
prefill the required dataset, repair the unchanged jail failures, or satisfy
any missing workload row. G0 remains blocked. Future mandatory baseline
sampling must begin only after a new complete fixture/environment manifest
and controls are established **after common provisioning**; no numeric
baseline gates have yet been frozen.

### Fully verified host readiness: recheck — 16:11 UTC

After the parent declared host preparation fully verified, a new bounded
exclusive-lock phase ran at `2026-10-04T16:11:55Z`–`16:11:56Z`. Its own
UID1000 preflight obtained KVM API **12**, actually created and closed a VM,
and opened/closed `/dev/vhost-net` non-root. The preserved Flint SHA-256 still
matched the unchanged safe binary above. No runtime or security setting changed.

Two fresh traced enforced-jail probes nevertheless failed before guest execution:

- **API:** UID/GID1000 and the kill filter were active; after `accept4`,
  `recvmsg` was killed by **SIGSYS** on the first configuration request.
- **CLI:** `openat("/dev/kvm", O_RDWR|...)` returned **EACCES**. Both fresh
  jail directories again contained root-owned `/dev` **0700** and
  `/dev/kvm` **0600** under private umask077.

These are actual **post-provisioning startup diagnostics**, not workload
baseline samples. Common host prerequisites are no longer a blocker; the
unchanged jail failures remain. Numeric gates cannot be frozen from executions
that never admit a guest request. No mandatory performance row, candidate,
new idle control, or performance comparison was executed in this phase.

Raw traces, launch/exit and blocked-result manifests are in
`post-ready-api-trace/` and `post-ready-cli-trace/`; the preflight/source/time
manifest and exact retained wrapper are in
`post-provisioning/readiness-recheck.json` and `post-provisioning/recheck.py`.
The wrapper was executed with `timeout 90s python3
.perf/blk-io/post-provisioning/recheck.py` inside the common exclusive lock.
Recorded owned processes exited; only these probes' named device nodes and
socket paths were cleaned.

## Separate correctness prerequisite — authorized at 16:18 UTC

The parent required a minimal separate repair rather than stopping at the
initial failures. Jail device directories are now explicitly root:root **0755**;
new device nodes are explicitly configured UID:GID **0600**, through no-follow
opened FDs before privilege drop. Artifact umask remains **077**, and host
device ownership/mode is not changed. No directory or device is world-writable.

The first receive-only repair actually passes the ownership/access regression,
but a fresh kill-filter trace proves **`sendmsg`46 → SIGSYS** when emitting the
first HTTP204 response. Only demonstrated Unix stream **recvmsg47/sendmsg46**
are added; AF_UNIX socket, clone and mprotect filters remain intact. A new
generated-filter regression checks those argument restrictions and keeps
eventfd/io_uring denied. Real HTTP tests check the dropped UID/GID, NoNewPrivs1,
Seccomp2, installed non-audit filter, and six successful PUT/GET transactions.
These tests are added to the KVM CI job.

Executed validation of this repaired configuration:

| Coverage | Actual result |
|---|---|
| Debug/Safe VMM units | **32/32 each**, including confinement regression |
| Debug/Safe existing real KVM integration | **7/7 each**, actual guest restore |
| Debug/Safe Python framing + real jail/API regressions | **9/9 each**, no skips |

The initial new fixture exceeded AF_UNIX's path limit; its failed runner
execution is retained, then the project-local evidence names were shortened.
It is not represented as a kernel/filter failure or a passing test. The
receive-only stage is likewise a diagnostic failure, not final acceptance.

Repaired safe binary SHA-256:
`a134ea4b95b0002444c13fac3cee4507c0a5b1d9be3fdfac77108cfc0daeb8a0`.
Untouched L0 `05e8308c…` and all old inputs/logs remain preserved, not overwritten.
No performance benefit is attributed to the prerequisite.

Fresh traced API/CLI **full guest** smokes advance beyond KVM/device/kernel setup
but reveal additional compatibility denials: API `sched_getaffinity` **204**
while starting its run-loop thread, CLI `epoll_pwait` **281** after its first
actual KVM exit. Both are killed by the unchanged remaining filter. Real
configuration HTTP acceptance is therefore not full guest/performance
acceptance. This minimal prerequisite is complete, but the repaired synchronous
workload baseline is **not yet qualified**; no numeric gates or worker exist.

Artifacts: `prerequisite/` contains exact builds/tests, stage binaries and
retained wrapper; `jail-tests/` contains real process status, permission/access
evidence, six checked responses and the sendmsg denial trace. Earlier long-path
runner diagnostics are under `prerequisite-tests/`. The distinct
`repaired-sync/` tree contains the repaired binary, fresh full-boot traces and
`prerequisite-smoke.json`; its input symlinks point only to the preserved
project-local fixture/tools. All VM/test/build phases held the common lock.

## Executed validation

| Command / coverage | Actual result |
|---|---|
| `zig fmt --check vmm/build.zig vmm/build.zig.zon vmm/src` | Pass |
| VMM `zig build test ... -Doptimize=debug` | **31/31 executed, passed** |
| VMM `zig build test ... -Doptimize=safe` | **31/31 executed, passed** |
| `zig build integration-test ... -Doptimize=safe -Dintegration-kernel=../.perf/blk-io/fixture/bzImage` | **7/7 executed, passed** |
| Same integration command with `-Doptimize=debug` | **7/7 executed, passed** |
| `python3 -m unittest discover -s tools/perf -p test_blk_io.py -v` | **7/7 executed, passed**; framing, failed-command and cleanup |
| `python3 tools/perf/blk-io.py smoke --unjailed --disk-probe --name smoke-unjailed-capability` | **1 actual guest disk/agent capability smoke passed**, not acceptance |

The seven integration cases comprise two CLI argument/error cases and five
KVM-dependent cases. Restore observes `FLINT_BOOT_OK` from actual resumed guest
execution, not just a `Running` API response. These pre-existing, **unjailed,
no-block/no-agent** tests do not establish async queue, disk-copy snapshot,
loaded lifecycle, fault injection, mutation, backpressure, wake or jail
acceptance. No required test skip is represented as a pass.

## Measured numbers and their limits

The following numbers are the **pre-provisioning diagnostics** identified above.

Host cycles/instructions are unsupported even with the root collector. Software
events work; syscall, scheduler, block and KVM tracepoints are available to the
root collector but not the ordinary tracefs reader. No security setting was
changed to obtain them.

Three aborted-startup `perf stat` runs report task-clock
**1.771359 / 1.720593 / 1.660960 ms**, mean **1.717637 ms**, sample SD
**0.055259 ms**; context switches are **11 / 5 / 6**. These counters include
`taskset` and aborted Flint startup, not guest execution, total disk
CPU/completion, or baseline/baseline workload noise.

Three `cpu-clock`, DWARF-stack records at 199 Hz terminate too quickly to
collect samples. Their raw data and explicit “no samples” reports are preserved,
not counted as successful profiles. Retrying the same startup probe at
**9999 Hz** yields **21 / 19 / 22 samples, zero lost samples** and real stacked
reports of jail/setup/kill-filter execution. Sixty-two startup samples cannot
identify a disk bottleneck; they are not a substitute for G1's loaded profiles.

**Before/after throughput, IOPS, request/interactive tails, total attributable
CPU, idle VM cost, lifecycle distributions and confidence intervals: not
measured. No candidate exists.** No numeric workload gate or A/A noise bound was
frozen from these startup counters. Proposed thresholds remain provisional.

## Required matrix and decision

| Acceptance row | Executed qualifying comparisons |
|---|---|
| Random read/write 4 KiB, QD1/8/32, achieved depth | **0; blocked** |
| Sequential read/write, QD1/16 | **0; blocked** |
| Flush-heavy and guest direct/buffered/host-cache strata | **0; blocked** |
| Offline package and representative build | **0; fixture not provisioned** |
| 1/2/4 concurrent VMs and fairness | **0; blocked** |
| Loaded/no-load exec first-byte/response and identified PTY replies | **0; blocked** |
| Idle after load; pause/snapshot/disk copy/resume/restore distributions | **0; blocked** |
| Async faults/mutation/backpressure/wake/generation/drain/isolation | **0; no backend selected** |
| Non-nested comparison | Unavailable; no extrapolation |

**Keep synchronous pending a repaired, independently qualified baseline.** This
does not demonstrate that a worker is slow or unwarranted. G0/G1 are incomplete,
so selecting/implementing a backend or freezing performance margins now would
violate the profile-first experiment. G2–G5 remain unexecuted; the plan stays
active/blocked. No default promotion, rollback claim, auto-merge or performance
merge recommendation is made.

Next work: resolve the unchanged jail API/device-permission incompatibilities
without broadening isolation; reserve/control a host suitable for total CPU
attribution; provision the pinned fio/higher-QD and offline package/build
fixtures; execute the full synchronous matrix/A/A profiles and freeze gates.
Only then choose a bounded worker, implement the specified coupled ownership,
wake and lifecycle surfaces, and run all remaining acceptance/comparison gates.

## Reproduction and durable evidence

Raw evidence remains private in the isolated worktree:

`/d/hearth/.perf/worktrees/async-block/.perf/blk-io/`

- `baseline/`: unchanged binaries, source/toolchain/environment/dependency
  manifests, debug/safe unit and integration execution logs, probe diagnostics.
- `fixture/`: verified kernel/initramfs, construction manifest/script content,
  private base image and unused verified Ubuntu provisioning download.
- `smoke-jailed*`, `diag-api*`, `diag-cli*`: exact launch/PID/exit manifests,
  serial/VMM logs, strace, raw stat CSV/perf data, stacked reports/build IDs.
- `idle-capability-control/`, `diagnostic-series.json`, `analysis.json`:
  raw host controls, explicit blocked statuses, reproducible analysis.
- `post-provisioning/tools-libraries.txt`: subsequent tool/library boundary;
  no workload measurements or performance qualification.
- `post-provisioning/readiness-recheck*`, `post-ready-*-trace/`: actual
  post-readiness non-root KVM/vhost preflight and two blocked jailed startup
  probes; retained wrapper, traces, modes, source/binary identity and exits.
- `smoke-unjailed-capability/`: actual guest kernel/mount/memory output,
  successful disk marker/flush counters and hash, owned exit record; no profiles.

All compilation, test execution, installation/extraction, fixture generation
and VM/perf probe series take the **common absolute** exclusive fleet lock.
Download and light inspection/analysis do not hold it. For example:

```bash
umask 077
cd /d/hearth/.perf/worktrees/async-block
flock /d/hearth/.perf/fleet/host.lock bash -lc '
  umask 077
  cd /d/hearth/.perf/worktrees/async-block
  export ZIG_GLOBAL_CACHE_DIR="$PWD/.perf/blk-io/zig-global-cache"
  export TMPDIR="$PWD/.perf/blk-io/scratch" PYTHONDONTWRITEBYTECODE=1
  python3 tools/perf/blk-io.py smoke --name new-api-probe --trace-startup
'
```

The private strace input is Ubuntu's
`strace_5.16-0ubuntu3_amd64.deb`, SHA-256
`847a3535be015325f127f121d2ea5ac042b32bd20a5861a94cb7782b09857b1f`,
extracted under the lock into `.perf/blk-io/tools/strace/`; nothing is installed
globally. The implemented `diagnose` subcommand owns its complete eight-probe
series; use fresh names/workspace when repeating rather than overwriting
evidence. `analyze` is light offline analysis and needs no host lock.

Raw binaries/images/profiles are not committed or uploaded with this report.
Retain this private worktree/artifact directory for further qualification.
All recorded owned PIDs were checked absent after completion. Named failed-jail
device nodes and stale sockets are cleaned; logs/profiles/manifests and unchanged
baseline assets remain private.
