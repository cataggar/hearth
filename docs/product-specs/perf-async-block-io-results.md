# Async block I/O: baseline capabilities and opt-in worker experiment

**Date:** 2026-10-04–05

**Issue:** #1

**Decision:** **Default-disabled worker implemented and correctness-exercised; G0/G1/performance qualification blocked. Keep synchronous; not eligible for performance merge.**

**Branch:** `copilot/perf-async-block-20261004`

**Spec:** [perf-async-block-io](perf-async-block-io.md)

**Plan:** [active execution plan](../exec-plans/active/perf-async-block-io.md)

## Fresh epoch after owner-approved orphan cleanup

At22:13 the user authorized the parent to stop fifteen specifically revalidated
old orphan busy-loop shells. This agent signaled none of them. Earlier saturated
controls and exploratory worker points remain historical; they do not describe
the current host or provide fresh gates.

An independently executed new locked five-second no-owned-VM control measures
**8.2busyCPU-s/5.000076232s =1.639975 busy cores**, with0.01iowaitCPU-s and
zero steal. That is reduced load, not proof of a reserved quiet host. Fresh
sysfs records CPU8siblings`8-9` and clientCPU1siblings`0-1`; this epoch uses
those actual disjoint placements, not earlier asserted topology.

Three fresh canonical `7dfee42` Safe enforced API/CLI/API boots immediately
execute successfully (response1.067358/0.729085/1.072184ms respectively).
All three requests after five seconds idle still **time out at two seconds**.
These are actual new legacy readiness failures, not recycled saturation or
the repaired recvmsg/node problem. All recorded owned VMMs are gone and their
private device nodes removed; no host helper busy-loop was created.

Storage before that phase has22,421,225,472free bytes. The earlier actual
ENOSPC and narrowly named owned-intermediate cleanup remain distinct.
Private new recipe/raw control/rosters/cleanup:
`.perf/blk-io/quiet-1/{fresh-control.py,executed-control.log,control-before.json,fresh-summary.json}`.
Fresh repaired-sync full-window profiles and20A/A samples now precede any new
candidate observations. Their numeric`B/N` are frozen below, but tail noise
is inadmissible; no gain/default/merge is inferred. Mandatory
control/lifecycle/matrix/total-cost requirements remain.

### Fresh full-window baseline profiles

Canonical prerequisite-only source`7dfee42`/Safe ELF
`6b6dad24ca2c6f17d372b0c35934f1ea44aee7ee27154c2c18cf977d305bee85`
uses the unchanged kernel, agent, fio3.40/libaio closure, fully written1GiB,
8GiB ext4 image,512MiB, legacy MMIO/IRQ and one vCPU. Constant`/job.fio`
is placed in the initrd; all dataset/output I/O is VirtIO-backed. The first
offline debugfs job insertion is retained as a failed zero-I/O recipe
(guest job unavailable after filesystem recovery), not accepted as a profile.
Neither new accepted run needs a host reply or heartbeat to complete fio.

Both accepted runs use10s ramp/60s measured fio plus process-scoped80s stat
and199Hz/8192-byte DWARF record. All three actual listed owned VMM TIDs,
including the kernel-created VM task, are attached. Scoped root collectors
and decoders retain exact argv/cache/scratch and raw reports.

| One **profiled** baseline point | 4KiB random read, libaio QD8 | 4KiB write + fdatasync, sync QD1 |
|---|---:|---:|
| fio error | 0 | 0 |
| Measured writes/reads | 962,715 | 302,560 |
| IOPS | 16,044.982584 | 5,042.498583 |
| Bytes/s | 65,720,794 | 20,654,074 |
| Guest fio write/read p50/p95/p99 (ns) | 456,704 /708,608 /815,104 | 60,160 /89,600 /115,200 |
| Guest fsync p50/p95/p99 (ns) | n/a | 124,416 /173,056 /234,496 |
| Owned task-clock,80s collector (s) | 70.223265763 | 51.030919961 |
| Context switches | 519 | 352,738 |
| KVM entries/exits | 8,092,933 each | 5,119,868 each |
| Host pread /pwrite /fdatasync calls | 1,128,086 /24 /4 | 1 /352,177 /352,138 |
| Raw CPU-clock samples /lost | 13,974 /0 | 10,081 /0 |

Actual QD8 accounting is100% at8. Fio's sync+fdatasync JSON reports roughly
200% in its depth1 field and`sync.total_ios=0`, while its fsync latency
distribution has302,559 observations and the owned host tracepoints count
352,138fdatasync calls over the longer warmup-inclusive window. These fields
are preserved, not normalized into invented probabilities or zero-flush claims.
The synchronous engine serializes writes and explicit flushes; write and fsync
quantiles are separate and cannot be summed into a joint request quantile.

Flush stacks show inclusive fdatasync6.88% and pwrite2.01%; read stacks show
pread about2.03%, with substantial KVM ioctl/exit work. The active flush owner
records51.230724976runtime seconds,27.188598ms runqueue wait and352,347slices
over the72.417786496s observation/drain window; the other two owned tasks
record zero runtime there. This is meaningful blocking-work characterization,
not an isolated syscall wall-duration/off-CPU attribution or a promised gain.
Deferred kernel writeback CPU is still not fully attributable.

**n=1 per profiled case, no variance or candidate comparison.** Stat includes
warmup while fio operations exclude it: do not divide the table's task-clock
by measured fio operations or claim aligned total CPU/completion. Profiler
overhead and host-cache effects are not removed. Guest direct I/O does not
bypass the buffered host backing FD.

Raw recipes/manifests/JSON/stat/stacks/control/rosters/cleanup:
`.perf/blk-io/quiet-1/e2/{randread-qd8,flush}/profile-1/`.
Both accepted profile VMs/collectors are gone. A separate single bounded locked
series of ten **unprofiled** paired fresh flush A/A runs completed20/20; its
registration defines`B=mean(all20)` and the95% paired relative noise bound
before results. The frozen outcomes follow. Successful redundant A/A
disk copies alone are deleted after exact-name/output-hash inventories;
canonical inputs, all outputs and failed/profile inputs remain.

### Fresh canonical A/A: completed, tail noise does not qualify

Twenty independently booted unprofiled10s-ramp/60s flush runs, ten pairs,
all return fio error0 and all owned VM identities disappear afterward. The
twenty exact-name redundant runtime images are gone; all JSON/distributions,
before/after controls, manifests and cleanup evidence remain. No candidate
outcome has been used to tune these gates.

| Frozen metric | B | Sample SD /CV | 95% paired relative N | Frozen margin /absolute gate |
|---|---:|---:|---:|---:|
| IOPS benefit | 5,023.310445 |143.614571 /2.858963% |3.502016% |15% /5,776.807012 minimum |
| IOPS regression | same |same |same |7.004032% /4,671.476152 minimum |
| Guest write p50(ns) |58,240 |281.661 /0.483622% |0.772765% |5% /61,152 maximum |
| Guest write p95(ns) |87,705.6 |5,728.189 /6.531155% |8.721112% |17.442224% /103,003.407 maximum |
| Guest write p99(ns) |130,457.6 |12,685.337 /9.723724% |17.020706% |**34.041412%**, inadmissible |
| Guest fsync p50(ns) |119,603.2 |1,413.440 /1.181775% |1.161125% |5% /125,583.36 maximum |
| Guest fsync p95(ns) |176,025.6 |8,851.905 /5.028760% |6.331245% |12.662489% /198,314.822 maximum |
| Guest fsync p99(ns) |293,836.8 |35,869.207 /12.207187% |24.938210% |**49.876421%**, inadmissible |

`N=max(abs(endpoints))` of the paired ratio-difference t95% interval
(upward-rounded t2.263/df9) is registered before sampling. All outliers remain,
including first-pair fsync p99 changing224,256→362,496ns. The tail margins
exceed the prescribed20% cap: **do not approve a candidate/default from these
gates**. More controls/data are required, not margin relaxation or trimming.
This is fresh evidence, not the historical orphan-saturation condition.

First-pair whole-host busy cores are1.779382/1.975681 including the VMM;
CPU8busy0.706891/0.691800 plus iowait0.265188/0.264255, SMT siblingCPU9
busy0.027347/0.025345; steal0. These aggregate/per-CPU controls neither inspect
other tasks nor establish total attributable kernel CPU. All20controls are in
`aa-host-controls-analysis.json`.5,531,467,776bytes are free after the series.

Frozen recipes/raw registration/series/gates:
`.perf/blk-io/quiet-1/e2/flush/{executed-aa-fio.py,aa-registration.json,aa-series.json,frozen-gates.json}`.
An alternate newly registered **matched current force-sync** regime will
fdatasync only its own copied run image and fsync its own directory before VMM
launch, keeping exact guest inputs/ramp/cache flags/compiler fixed. This
eliminates unaccounted copied-input writeback before attempting another
profile/A/A; it is not a global cache drop or VMM optimization. Preserve the
completed unfenced epoch separately. PID/start-time checked pidfd cleanup
also closes the helper's bare-PID check-to-signal race; it does not change
the guest or a measured workload window.

The helper revision executes **13/13** focused tests, including real owned
pidfd delivery and stale-start-time refusal. The intermediate read-fault
revision executes Debug/Safe **45/45units +8/8real KVM +7/7enforced-jail**
cases each, with explicit frozen kernel selection. At that checkpoint a
later Linux per-read transfer-cap edge added a46th unit awaiting validation; these
45-case results do not attest that newer source. The initial missing-kernel
fixture attempt (five errors) and rejected Zig frontend cache option
(zero tests) remain separate failed logs, not passing executions.

The final descriptor-read revision subsequently executes Debug/Safe
**46/46units +8/8real KVM +7/7enforced-jail** cases each and **13/13helper
tests once**, with no skips. The cap case checks both an already-transferred
prefix and the final4096-byte chunk, using a lazy2GiB virtual mapping
(unit runner peak RSS10/9MiB), not a physical2GiB disk-read acceptance claim.
Safe ELF`baadc7e85b83a7d5ae0b83ce6f666be8c26393d1d3c4246c878dfa841230c331`;
Debug ELF`adc4d569350842a6bfed532da780cfa44a832f9b369c999a0897b5cdfc118173`.
Exact commands/logs: `.perf/blk-io/quiet-1/validate-read-boundary.sh`,
`read-boundary-{debug,safe}-3.log`,
`read-boundary-jailed-{debug,safe}-3.log`, `read-boundary-helper-3.log`.
The Zig frontend uses project-local`ZIG_GLOBAL_CACHE_DIR` environment and
`--cache-dir`; its unsupported`--global-cache-dir` attempt is not repeated.

Before that bounded validation, four exact successful restored-side copies
are hash-compared with their retained originals and removed. Two identical
inactive immutable fixture templates are hash-compared and deduplicated by
hardlink; both full paths/bytes remain. Every actual VM still receives its
independent copy and unchanged backing-file mode. The manifest records
4,308,484,096named redundant allocated bytes reclaimed; it is artifact
storage housekeeping, not a workload/image optimization or a measured gain:
`.perf/blk-io/quiet-1/redundancy-reclaim-45.json`.

### Matched current-ELF fenced baseline profile

Source`c734b8ec9e53671b31827b4548aba8eb7c44cfab`, the Safe ELF above,
`--block-backend worker --force-sync`, executes an additional real enforced
profile on2026-10-05. Effective backend is checked`sync`; all three actual
owned TIDs are attached. Exact e2kernel/initrd/guest-job/dataset bytes, CPU8/
clientCPU1,10s ramp/60s measured, one vCPU/512MiB and guest-direct/host-buffered
flags remain. Only its copied run image/directory are fdatasync/fsync-fenced
before launch (observed605,648ns); no global cache drop occurs.

This **profiled n=1** returns error0,303,361measured writes and
**5,055.932401IOPS**. Guest write p50/p95/p99 are60,160/80,384/115,200ns;
separate fsync p50/p95/p99 are123,392/168,960/238,592ns, N303,360. Warmup-
inclusive80s stat records50.968212137ownedCPU-s,353,236context switches,
zero migrations/faults,5,128,865KVM entries/exits,1pread,352,890pwrite and
352,852fdatasync. Record has10,064CPU-clock samples/zero lost; inclusive
fdatasync/pwrite stacks are about6.99%/2.09%. Active owned TID schedstat
records51.160567010runtime seconds,18.330360ms runqueue wait and352,901slices
over72.442190843s; the other two TIDs have zero runtime in that window.

No variance, aligned CPU/completion, total kernel-writeback attribution,
force-sync-versus-worker gain or gate is inferred from this point. All
recorded identities are gone; private device nodes are removed. Four newly
verified exact successful restored-side duplicates are also removed after
hash comparison with retained originals (2,147,483,648allocated bytes), with
their own separate manifest. A newly registered ten-pair forced-sync A/A
series remains pending; no fresh worker outcome has been collected.

Raw executed drivers/source manifests/stat/stacks/distributions/custody:
`.perf/blk-io/quiet-1/e3/flush/profile-baseline-1/`,
`e3/flush/matched-source.json`, `matched-profile-baseline.log`,
`redundancy-reclaim-46.json`. This separate matched regime cannot erase or
replace the completed inadmissible canonical e2epoch.

### Matched fenced A/A: second complete series, still inadmissible

The same c734Safe source/flags and copied-input fence complete another
**20/20unprofiled runs, ten pairs**, all error0, actual effective-sync/all
three TIDs verified. Every run's recorded identities/device node disappear
and its exact-name redundant image is removed after retaining the output
hash inventory. These are a separate cohort, not replacements for e2.

| Frozen matched metric | B | Sample SD /CV | Paired95% N | Frozen margin /absolute gate |
|---|---:|---:|---:|---:|
| IOPS benefit |5,236.941884 |102.754095 /1.962101% |1.911219% |15% /6,022.483167 minimum |
| IOPS regression |same |same |same |5% /4,975.094790 minimum |
| Write p50(ns) |58,112 |234.921711 /0.404257% |0.576552% |5% /61,017.6 maximum |
| Write p95(ns) |81,753.6 |5,167.126275 /6.320365% |10.293344% |**20.586688%**, inadmissible |
| Write p99(ns) |113,920 |5,166.942698 /4.535589% |5.463037% |10.926073% /126,366.983 maximum |
| Fsync p50(ns) |117,964.8 |885.252839 /0.750438% |0.940709% |5% /123,863.04 maximum |
| Fsync p95(ns) |164,147.2 |4,164.148862 /2.536838% |2.555322% |10% /180,561.92 maximum |
| Fsync p99(ns) |235,315.2 |27,038.662365 /11.490402% |11.083335% |**22.166669%**, inadmissible |

No fresh worker result has yet been collected. Preserve every outlier,
including write p9562,720→81,408ns and fsync p99268,288→216,064ns.
Neither the higher mean than e2 nor the narrower noise is attributed as a
worker benefit: source/control preparation differ between those epochs.
Raw registration SHA`da85c2e4…`, series SHA`88098f7f…` and immutable
`frozen-gates.json` are under`.perf/blk-io/quiet-1/e3/flush/`.

Before any new worker output, register a **fixed ten additional A/A pairs**,
retaining **all original20 observations**. The combined40-run/20-pair
baseline uses the same source/recipe, Bmean(all40), and
`N=maxabs(mean(d)±2.094×sampleSD(d)/sqrt20)` (upward-rounded t95/df19).
The old frozen20-run gates remain unchanged; the extension has separate
registration/series/frozen files. Keep identical5%/10%/15% proposals and10%/
20% noise caps, with **no significance-based early stop or further extension**.
If still inadmissible, a clearly labelled all-worker diagnostic profile may
characterize overhead, never qualify a candidate/default. The mandatory
matrix/liveness/total-cost conditions remain regardless of primary noise.

### Fixed extension interrupted; no replacement gate or qualifying comparison

The additional series accepts **8/20new runs** (combined28accepted rows),
then`aa-14-A0` actually hits host backing-write failure: guest logs show I/O
errors, journal abort, read-only remount and`BASELINE_FIO_ERROR`. Host evidence
persistence then fails with **ENOSPC**. The extension is terminal/incomplete,
not topped up, trimmed, relabelled or frozen as40passing samples. Its failed
disk input and all preceding outliers remain. No qualifying A′/B is executed.

Exit evidence ENOSPC also skips a stale owned API-socket unlink in the
experimental fixture. All recorded VM/TID paths and the device node are
already gone; the exact remaining current-UID socket is separately verified
as a socket and removed. The helper now unlinks owned socket paths in`finally`
even if exit-evidence saving fails. **14/14helper tests** pass, including the
new persistence-failure regression; **2/2additional actual Safe enforced
CLI/API worker disk/identity cases** pass. These are additional focused
executions, not claims that a failed performance workload passed.

Lossless archival retains all exact8GiB bytes of three inactive accepted
profile inputs (full decoded SHA/length verification): e3sync and e2flush
archives each about93.37MB, e2read1,075,850,038B. Immutable source templates/
ELFs, actual VM independent-copy/backing mode and failed input images are
unchanged. Despite those scoped alternatives, the shared filesystem again
reaches20,480free bytes. Even a remote branch push succeeds while its local
remote-tracking ref update fails ENOSPC; the remote head is independently
verified afterward. No unowned cleanup or storage/security setting change
is performed.

Raw failures/custody/archival recipes:
`.perf/blk-io/quiet-1/{matched-aa-extension.log,enospc-helper-tests.log,enospc-helper-jailed.log,lossless-*.log}`,
`e3/flush/{aa-extended-registration.json,aa-extended-series.json,extension-failure-custody.json}`,
and each profile's`lossless-input-archive.json`/`disk.ext4.raw.gz`.

### All-four-task worker diagnostic: slower observation, failed artifact phase

After the inadmissible gates, an explicitly **diagnostic-only** c734 worker
profile verifies effective-worker/no fallback and attaches **all four actual
owned TIDs** on CPU8. It uses the same exact guest inputs and copy fence.
Guest fio itself reports error0; the artifact/decoded-output phase runs out
of space and exits120, so **the overall run is not accepted or performance-
qualified**. Preserve the original truncated text decode losslessly; do not
hide the failure by calling the subsequent bounded raw-data decode a retry.

| Single profiled observation, not a paired confidence result | Forced-sync | Worker diagnostic |
|---|---:|---:|
| Guest measured write IOPS |5,055.932401 |2,924.919169 |
| Guest measured write operations |303,361 |175,501 |
| Write p50/p95/p99(ns) |60,160 /80,384 /115,200 |115,200 /160,768 /224,256 |
| Fsync p50/p95/p99(ns) |123,392 /168,960 /238,592 |218,112 /309,248 /432,128 |
| All-owned-task80s CPU(s) |50.968212137 |55.949737508 |
| Context switches |353,236 |1,541,418 |
| KVM entries/exits |5,128,865each |3,294,897each |
| Host pread/pwrite/fdatasync |1 /352,890 /352,852 |1 /206,259 /206,217 |
| Owned raw CPU-clock samples /lost |10,064 /0 |10,813 /0 |

Descriptive IOPS is42.148768%lower and warmup-inclusive all-task CPU9.773789%
higher, **n=1each/no variance/unaligned CPU and completion windows**, with
different observation times and real storage pressure. No statistically
qualified regression or total CPU/completion value is claimed. In particular,
do not present the lower active vCPU cost as total savings: worker schedstat
adds11.320360447runtime seconds/18.436386210s runqueue wait to the active
owner's47.111485799runtime seconds/5.775771468s runqueue wait. Deferred kernel
writeback CPU remains unattributed. Inclusive fdatasync/pwrite CPU stacks
are about6.08%/2.48%; lower KVM counts accompany fewer completed operations,
not proof of cheaper equivalent work.

The91,732,556-byte raw recording remains. A bounded re-decode of that same
recording succeeds and reports10,813samples; the earlier truncated421,498,880-
byte decode is exactly retained in a29,081,600allocated-byte gzip archive.
Only13named hashed reproducible owned LLVM`*_zcu.o` intermediates are removed
(106,209,280allocated bytes); all executed ELFs/raw source assets remain.
All recorded diagnostic VM/TID paths, device node and API socket are gone.
Raw stat/report/record/source/argv/credentials/custody are in
`.perf/blk-io/quiet-1/e3/flush/diagnostic-worker-1/`.

**Final decision:** retain the default-disabled prototype and reproducible
negative/inconclusive evidence; **keep synchronous default, no performance
merge or auto-merge recommendation**. The issue remains blocked/incomplete:
fresh noise caps, terminal storage-interrupted extension, timer-free legacy
post-idle0/3, full workload/control/lifecycle/SDK matrix and aligned all-worker
plus attributable deferred-kernel-I/O cost still require acceptance. The old
fifteen-core saturation is historical, not the current reason.

The stable private epoch is sealed as1,238files (1,236unique regular inputs)
in`.perf/blk-io/quiet-1/final-evidence-seal.json`, SHA256
`7436ade146601c62e62099878e1522dcc7b8f50d84c60a54df16546d599b46d7`.
It records c734runtime/9f39518source provenance and includes originals,
failed attempts, distributions, compressed raw bytes and executed drivers;
it is not a claim that incomplete rows pass.

### Current-head correctness continuation after residual-load report

At02:26UTC the parent reports a new locked aggregate`/proc/stat` control of
about8.733/16busy cores. That is **parent-reported background context**, not
this agent's measurement or attributable worker CPU. Own-UID task deltas
contain unrelated active workloads and are not a total-cost attribution
method. No jobs are killed/moved; old16-core saturation remains historical.
Do not compare pre/post-cleanup samples as an optimization or relax gates.

Current HEAD`fb76e92` has byte-identical VMM sources to validated c734 and
byte-identical helper sources to9f39518. A fresh locked Safe phase executes
**8/8real KVM integrations,14/14helper cases,1/1actual enforced-jail lifecycle
case** (three pause/resume cycles and fresh API+CLI restored guest counters),
all pass. **The46-unit runner is cached, not re-executed in this phase**;
retain its earlier actual source-proof counts without inventing new executions.
Fresh Safe ELF remains exactly`baadc7e8…`; no compiler/features/backend change.

The first post-phase custody write again encounters ENOSPC; its incomplete
file remains. Resource predicates already pass. Two exact successful restored-
side copies are SHA-compared with their retained original and removed
(1,073,778,688allocated bytes), never a failed/original input. Recovered custody
audits **all23latest-ELF launch records** with zero live PID paths/nodes/sockets.
The PR remains draft, the issue blocked and default synchronous.

Commands/raw addendum:
`.perf/blk-io/quiet-1/current-head-safe-proof-{zig,helper,lifecycle}.log`,
`current-head-restore-duplicates.json`,
`current-head-proof-custody-recovered.json` SHA256
`18d531eb47f69653b0338500aff920af2175e5d2120e864cdfed9750c30c9197`.
This addendum does not replace the earlier immutable1,238-file seal or turn
missing performance/liveness/matrix/attribution acceptance into a pass.

## What was implemented

The original diagnostic integration suite accepts `-Dintegration-kernel=<path>` relative to
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

## Parent-authorized ordered worker continuation

After `a401bf8`, parent independently verified15.961/16 visible cores busy
under the fleet lock and explicitly authorized safe opt-in implementation
despite blocked performance qualification. The backend is an experiment,
not a profile-qualified winner or permission to change adoption gates.

Implemented interfaces: CLI `--block-backend sync|worker` (default sync),
CLI `--force-sync` overriding CLI/REST requests before admission, REST
drive `io_backend` (default sync). Every boot/restore route applies the same
choice. There is no SDK option, runtime switch, io_uring, new guest feature,
eventfd/irqfd notification acceleration or borrowed sibling runtime patch.

One ordered worker/device, one logical-request credit reserved before avail
consumption, fixed64KiB host staging and up to256 captured direct descriptors.
Header/sector, directions, ranges, status destination, queue identity and
generation are validated/captured before I/O. Valid larger payloads stream
in bounded chunks; later write chunks are staged when submitted, **not** an
atomic whole-payload snapshot. Worker never follows guest memory pointers.
Owner alone copies read data and publishes status/used/IRQ. EOF/short writes,
IOERR/no replay, used-length quirks and FIFO flush match the retained sync path.

READY publication precedes atomic immediate_exit and SIGUSR1. Owner clears
the byte before pause/completion checks and never afterward before entry.
Pause drains accepted work without taking retained avail before fresh epoch
acknowledgment; snapshot rejects an unacknowledged pause. Queue disable/reset/
reconfiguration drains/discards before mutation and invalidates generation.
Workers join before FD/vCPU/memory release; partial device init and restore
cleanup order were corrected. Initialization OOM has focused pre-admission
sync fallback coverage; there is no live fallback or write replay.

One later Safe full run exposed a real restored-application stall (15/16Python
cases). It is retained, not masked by a retry. The coupled quiescence repair
completes KVM's pending IO/MMIO emulation using KVM_RUN with immediate_exit
before acknowledging pause. The [KVM API contract](https://docs.kernel.org/virt/kvm/api.html)
explicitly says that pending operations are not in userspace-visible snapshot
state and must complete before migration. A real PIO-IN test supplies0x5a,
verifies RAX is still0 before completion, then verifies RAX0x5a/RIP advancement
without executing the following HLT. Current final source passes the full
Debug/Safe suites; **three additional Safe lifecycle cases** also pass
(each exercises three pause/resume cycles and fresh API+CLI application restore).
This correctness change is not a performance gain or#3 runtime dependency.

### Actual correctness, not compile-only or mocked acceptance

Frozen Zig0.17.0, `-Dtarget=x86_64-linux -Doptimize=debug|safe`, existing
dependency/guest feature settings. Each mode: **44/44units,8/8real KVM
integrations,16/16Python cases**; no skipped cases counted. Unit additions
cover metadata/status mutation, staged payloads, credit retention/refill,
larger chunks, flush ordering, partial write/no replay, read/flush faults,
invalid ranges/overflow, real memfd differential EOF/GET_ID, reset/disable/
ring reuse generation, quiescence admission and pre-entry notification windows.

The new actual KVM integration runs `cli;hlt` with IF clear and no PIT.
A bounded external observer of only its owned owner waits for
`wchan=kvm_vcpu_block` before releasing gated I/O. The production notification
then returns KVM_RUN/EINTR with completion ready. A second window handles the
signal before entry yet immediate_exit still prevents blocked entry. This
proves the shared notification mechanism, not ordinary Linux timer-assisted
boot and not legacy vsock readiness.

Real enforced-jail API **and CLI** worker guests write/flush/read/hash128KiB,
with host verification of the untouched remainder. Force-sync executes the
same guest without a worker. Actual worker rosters have UID/GID1000, no
supplementary groups, CapEff0, NoNewPrivs1, Seccomp2. Three rapid pause/resume
cycles leave the disk stable while paused. A populated quiescent snapshot
restored into **fresh API and CLI processes** continues a RAM application
counter and its backing-disk writes without repeating `APPLICATION_INITIAL_BOOT`.
This does not retroactively accept the earlier failed vsock-agent restore.

Initial compile errors, one changed error-text regression (fixed preserving
the original response), a reset fixture missing DRIVER_OK and CLI fixture/PID
startup races are retained. They are not passing trials. Final logs:
`lifecycle-debug-4.log`, `lifecycle-safe-1.log` (Zig52/52, initial Python
harness race), and `final-python-debug.log`/`final-python-safe.log` (16/16).
The subsequent pre-quiescence stall is `final-acceptance-safe.log`; final
repaired logs are `quiescent-safe-1.log` (52+16), `quiescent-debug-1.log`
(52), `quiescent-python-debug-1.log` (16), and
`quiescent-repeat-safe-{1,2,3}.log` (one lifecycle case each).

### Owned-only exploratory profiles and limits

Two RPC-controlled worker fio trials time out despite retained heartbeat and
actual I/O. No complete fio result/backing output is accepted from either;
failed commands and partial captures remain in `profile-1/`. Its all-four-TID
13s stat reports9.598386338CPU-s,326377context switches,556036KVM entry/exit,
82617pread64,9pwrite64,2fdatasync. These are **partial failure diagnostics**.
An initial small report-preview decode outside the fleet lock is not a
qualified observation; complete alternate collectors/decoders below ran
inside the common lock.

A practical alternate fixture retains the same kernel/compiler, block/vsock
devices, guest features, libaio closure and1GiB dataset, but starts fio
autonomously and reports by serial (no heartbeat or dependency on RPC reply).
Both complete, sync and independent backing-file JSON extraction verifies
error0. The same Safe ELF runs force-sync and worker under one bounded lock.
These are **single exploratory, saturated-host10s windows**, no warmup/full
matrix/repeated variance/qualification:
These profiles used the preserved earlier Safe ELF
`2f709685d2c70b37d32d9ec8f3eac0b23a1600171cf6059e0672ac77b305e0e5`,
before the final pending-emulation quiescence correction; they are not a
performance qualification of the final source.

| Variant | Read IOPS | Raw199Hz samples | Lost records | Listed owned tasks |
|---|---:|---:|---:|---:|
| Force-sync | 13465.453455 | 2023 | 0 | 3 |
| Worker | 10541.145885 | 1905 | 0 | 4 |

The raw worker point is lower, not evidence of a win. `n=1` each; SD/CV,
qualified delta and frozen `B/N` are **null**, not invented zeroes.
Software record estimated CPU-event counts10165827875/9572863125 are not a
savings claim: completed work differs and no quiet/noise gate exists.
All actual VMM workers plus the listed `kvm-nx-lpage-re` task are included;
its observed Kthread is0, so it is not mislabeled an unfiltered userspace
worker. Kernel CPU inside owned I/O syscalls is captured; deferred/background
filesystem/writeback attribution is incomplete. Guest/hypervisor symbolic
maps remain unavailable; hardware cycles/instructions remain unsupported.
Do not subtract unrelated saturation or publish unrelated task metadata.

Artifacts: private `.perf/blk-io/worker-correctness/` (executed recipes, logs,
ELFs, manifests, raw perf/data/dumps/reports) and `.perf/blk-io/jail-tests/`
(owned launches/credentials/guest results/actual snapshots). Existing original
L0 and repaired-sync artifacts remain distinct and preserved.
This active plan is **not completed**: full supported disk/cache/writeback,
loaded interactive/concurrent/idle/lifecycle matrix, quiet-host A/A/frozen
numeric gates, attributable kernel totals and legacy control readiness remain
mandatory. Shared prerequisite convergence with#3 is still pending. Keep
default sync, retain draftPR7, no auto-merge or performance merge recommendation.

### Standalone common prerequisite custody — follow-up

For peers needing an identical repaired synchronous baseline without borrowing
the async implementation or performance runner, canonical local commit
`7dfee42ed68fe1703744d6318f4be632113034b0` has **one parent, documentation base
`b06ec0a`**, and only five changed files: jail, seccomp, focused32-case unit
file, [standalone jail fixture](../../tools/perf/test_jail_baseline.py), and its
[contract/commands](perf-jail-baseline.md). Runtime blobs exactly match the
already validated `ced7ed7` common repairs; no main/VM/compiler/dependency/
worker/reactor changes are included.

The commit was archived inside this isolated worktree and actually built/
executed independently: frozen-target LLVM Debug/Safe each **32/32units and
3/3standalone real enforced-jail cases**. The fixture tests API receive/send,
umask077 root0755directories/configuredUID0600nodes/host device invariance,
empty inherited groups/caps and all actual task filters, and CLI/API guest
disk write/fsync/read/hash. It also passes3/3 against each current Debug/Safe
opt-in binary with the default sync selection. It does not claim Native-row,
snapshot, resource-budget or performance acceptance. An initial long AF_UNIX
address fixture error was fixed and retained; original untouched L0 executes
the same final fixture with **0/3accepted,3errors**, separately preserved.

The canonical commit is held by owned local ref
`refs/copilot/async-block/canonical-jail-baseline` and private verified bundle
`.perf/blk-io/canonical-prerequisite/jail-baseline-7dfee42.bundle` (requires
`b06ec0a`). No merge, main/peer branch push or alternate worktree was performed.
Peers in this shared repository can cherry-pick the exact local hash; the
bundle preserves portability without publishing a second branch or raw images.
Commands, initial/final logs, input ELFs, independent source archive and owned
PID cleanup are in `.perf/blk-io/canonical-prerequisite/`.
Local acceptance is verified; shared prerequisite convergence remains pending
peer adoption. Quiet-host/performance qualification and synchronous default
decisions are unchanged.

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

The minimal repair is commit `f2f9ab4c8e7a67097f2c3f52636327e9c41d5084`.

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

### Separate trace-proven compatibility follow-up

The next capture preserves the `204`/`281` repairs separately, then proves
API thread creation also emits **CLONE_DETACHED0x400000**, and the existing CLI
vsock loop emits **poll7 with timeout0**. Linux's actual installed UAPI
`/usr/include/linux/sched.h` declares CLONE_DETACHED **unused, ignored**.
Recognizing that bit permits no new active namespace/clone capability.

The follow-up therefore adds argument-filtered **self-only PID0 affinity
reads**, **null-mask epoll waits** (both pointer halves checked), and
**nonblocking timeout0 poll**. It recognizes only the ignored clone bit,
retaining the original active flag restriction. AF_INET/AF_INET6,
CLONE_NEWUSER/NEWNS, executable mprotect, other-process affinity, nonnull
signal masks, blocking poll, eventfd and io_uring remain denied by regression.
No new worker, completion wake mechanism or timer is introduced.

Final follow-up validation:

- **32/32 units each Debug/Safe**, including generated-filter confinement.
- **7/7 existing KVM integration each Debug/Safe**, actual resumed guest marker.
- **10/10 Python tests each Debug/Safe**, including three real-jail cases:
  private-umask ownership/access, six HTTP exchanges, and actual guest userspace
  after enforced API thread/epoll setup. No skips.
- **2/2 additional traced real jailed API/CLI disk+agent smokes pass**, with
  marker hash and guest sync. These still use the declared existing10ms
  heartbeat and are capability evidence, not async wake/performance acceptance.

An intermediate unit run exposed two stale layout assertions (30/32);
the assertions were corrected for the new filtered dispatch layout, then the
complete final suites passed. All failed runs remain retained, not passing.

Final repaired synchronous safe SHA-256:
`0f7b0d55937df5fa2945ef05aedaea7f046b94795be259469f87e89c16775f93`.
Distinct stages are `repaired-sync/`, `repaired-sync-compat/` and
`repaired-sync-usable/`; final raw evidence includes `compat-smoke.json`,
per-mode traces/launches/exits, and `prerequisite/usable-*.log`.
Untouched L0 remains unchanged. Prerequisite correctness is now established;
the package/build fixture, complete G0/G1 workload matrix, post-provisioning
A/A and total-host noise controls still require execution. No performance
benefit, frozen gate, prototype selection or promotion is inferred from repair.

## Actual repaired-sync guest fio and loaded profiles — 17:26–17:33 UTC

These executions use repaired synchronous source
`5ee81b163b266f9c7643fb67c88cb59fe7aa2878`, safe binary `0f7b0d55…`,
the same kernel and unchanged static agent. All VMs remain jailed and dropped
to UID/GID1000, with legacy MMIO/IRQ behavior. The original untouched L0 tree
is not overwritten or included in a comparison with this usable configuration.

### Verified guest engine, dataset and achieved depth

Host `fio --enghelp` and `ldd /usr/bin/fio` were insufficient: the first actual
guest run could print fio3.40 but could not load libaio. The installed
`fio-engine-libaio-3.40-3.azl4.x86_64` RPM supplies a **dlopened**
`/usr/lib64/fio/fio-libaio.so`, with an additional `libaio.so.1` dependency.
The corrected private fixture copies that exact installed plugin and dynamic
closure; no compiler, dependency manifest, guest feature or installed package
version changes.

An initial plugin-enabled trial completed fio commands but destroyed the VM
before its JSON was reliably persisted. The owned backing-image copy and
journal-recovery attempt did not recover depth JSON. It is preserved as a
failed evidence-capture trial, **not achieved-depth acceptance**. The corrected
run syncs and reads/parses each JSON through the actual agent before destruction,
checks every job's `error=0`, and uses distinct run/prefilled image names.

The fully checked guest run at **17:26:35–17:27:00 UTC** establishes:

| Actual guest operation | Checked result |
|---|---|
| Full refill-buffered file write with final fsync | **1,073,741,824 bytes written**, error0; not sparse sizing |
| Direct libaio random read, requested QD8 | Achieved depth band8 **99.964865%**, error0 |
| Direct libaio random read, requested QD32 | Achieved depth band32 **99.853698%**, error0 |

The verified prefilled image is
`fio-sync-libaio/fixture/disk.prefilled-guest-fio-verified.ext4`; raw guest JSON,
engine help, commands and executed wrapper are in
`fio-sync-libaio/guest-fio-verified/`. Original incomplete-plugin and
unpersisted-JSON trials remain separate. This resolves guest fio/higher-depth
and fully written dataset capability, not the entire G0 workload fixture.
The pinned offline package/build disk-root closure remains unprovisioned.

### Short warm-cache diagnostic A/A and actual host profiles

One exclusive-lock series makes fresh reflink image copies and uses CPU8,
one vCPU, 512MiB, and the declared existing10ms heartbeat. Six unprofiled
**10-second** direct libaio QD8 random-read trials form three short diagnostic
A/A pairs; separate repeated runs collect stat and stacked software profiles.

IOPS are **11738.826117 / 11112.388761 / 11107.789221 / 11041.695830 /
10341.665833 / 10348.565143**. Mean **10948.49**, sample SD **531.73**
(**4.857% CV**); pairwise relative deltas are **−5.336% / −0.595% / +0.067%**.
These are synchronous-only samples and drift/noise, not an optimization gain
or confidence-qualified A/A bound.

The separately matched five-second whole-host control measures **99.799875%
busy CPU** despite holding the fleet lock. External runnable work remains;
ownership is not established and no unowned PID, affinity, cache or security
setting was changed. This is new #1 post-repair evidence, distinct from the
historical99.938% window and peer-reported controls.

The stat collector explicitly attaches to all **three listed VMM TIDs**, not
just the vCPU, for approximately12 seconds:

| Actual counter | Observed total |
|---|---|
| task-clock | **10.254681329 CPU seconds**, 0.854 CPUs utilized |
| context switches / page faults | **5153 / 0** |
| KVM entry / exit | **795699 / 795699** |
| pread64 / pwrite64 / fdatasync | **103005 / 22 / 4** |
| Separately stat-profiled fio IOPS | **10299.370063** |

The separate199Hz cpu-clock/DWARF record contains **2036 raw sample records,
zero lost samples**; native `perf script` decodes730 event headers, while the
record/report also contains guest/hypervisor-mode samples without guest symbol
maps. Real native kernel/user stacks include KVM run/ioctl and buffered
`pread64`/`filemap_read` paths. The record-profiled fio IOPS are **10580.641936**.
Raw sample count is obtained from `perf report -D`, not rounded “2K” output.
Hardware cycles/instructions remain unsupported.

These are **not G1 acceptance**: no10s warmup/60s measured windows, only three
short pairs, incomplete workload/cache/writeback matrix, no independently
verified runtime thread-role/creation census, and no complete attributable
asynchronous kernel I/O/writeback CPU. No lower vCPU cost or total CPU saving
is claimed; no candidate or numeric performance/resource gates exist.

### Own no-heartbeat control liveness check

Fresh repaired jailed API boots without the heartbeat accept three immediate
startup exec requests (**3/3**, approximately1.88–1.94ms). That is not idle
progress: three further fresh boots wait **five seconds** before submitting
the same exec. **All3/3 time out at the two-second socket deadline**. No
heartbeat, polling workaround or peer notification optimization is added.

These are actual #1 controls, not assumed peer outcomes. Logs and launch/
exit manifests are under `g0-loaded-profile/idle-no-heartbeat-*` and
`idle-wait-no-heartbeat-*`; `idle-wait-control-summary.json` and the retained
executed wrapper describe the exact bounds. Required idle/interactive baseline
liveness is therefore genuinely blocked. An async block worker cannot be
qualified from heartbeat-masked control success or an unsupported mandatory
baseline row. This failure and the uncontrolled saturated-host condition
prevent G0/G1 qualification/backend selection; they do not prove a worker's
performance merits.

## Continued repaired-sync G0/G1 execution — 2026-10-04 UTC

The shared `repair-perf-jail-baseline` todo is **done**, from the actual enforced
API/CLI acceptance above. `impl-perf-block-1` remains **in_progress** as requested;
the complete experiment is not finished. The runtime is still `5ee81b1`, safe
SHA256 `0f7b0d55…`, with the same kernel/agent/compiler and legacy MMIO/IRQ.
No peer runtime optimization or async selector/backend was adopted.

### Actual offline disk-root package/build fixture

The verified Ubuntu22.04.5 base input now boots as **`/dev/vda` ext4 root**,
not an initramfs installation destination. A separate private fixture switches
root to that single disk, mounts devpts for PTY, and runs the same static agent.
Its sizing remains one vCPU,512MiB,8GiB. These are workload/tool provisioning
inputs, not changes to VMM compiler/dependency or advertised guest features.

The actual guest APT resolver first exposes an installed gcc-12-base version
newer than the release-only index; it fails dependency resolution rather than
being counted passing. The corrected closure uses **three signature-verified
Ubuntu archive indices** (jammy, updates, security), all SHA256 checked against
their signed releases. Actual guest `apt-get --print-uris --yes
--no-install-recommends install gcc make libc6-dev hello` yields **37 pinned
packages,53,853,458 bytes**. Every downloaded deb's SHA256/size is checked
against those verified indices before staging. No host package installation or
network inside the guest is required.

An explicit-list `dpkg -i` script executes offline inside the guest. **One real
installation passes in6.654472s**, including guest sync, hello and tool-version
checks. **One real SQLite3.46.1 build passes in44.749365s**, using pinned
GCC11.4/make4.3 and `make -C /mnt/build-src -j1 clean all`; scratch is on the
VirtIO-backed disk. The built executable reports3.46.1, inserts/reads **1337**
from a real database, and hashes to
`3bfd0d41645dcdd8f5034037e4114bbf26a83bd28dc9241871f043920352fd79`.
After guest sync and VM exit, an owned host `debugfs` dump of that database
also reads1337 through read-only SQLite. These are **single capability timings**,
not paired package/build performance distributions or gains.

Frozen input hashes:

- Ubuntu base archive:
  `242cd8898b33ea806ef5f13b1076ed7c76f9f989d18384452f7166692438ff1a`.
- Exact37-package closure JSON:
  `f7e1c4000d4f945d294ebb2d9cd01be1dd3a9ca9751fd2b00a10dd1ad461dc62`.
- Official SQLite3.46.1 amalgamation archive:
  `77823cb110929c2bcb0f5d48e4833b5c59a8a6e40cdea3936b99e199dbbe5784`.

Initial safe tar extraction rejects valid absolute guest-root symlinks; those
are rebased to equivalent relative in-image links without allowing host escape.
A later bootstrap fails because a renamed BusyBox chooses its basename as an
applet; the corrected fixture retains the `busybox` basename. Both failures
remain preserved. An initial metadata field accidentally hashes the agent
instead of the Ubuntu input because of a reused builder variable. The builder
is corrected; a separate **validated-capability-manifest** records the old
incorrect field, correct archive hash, three explicitly reverified signature
exit codes0 and accepted guest results. Preexecution manifests are not
silently overwritten. The private builder also now enforces collector exit
status rather than treating a logged signature command as sufficient.

Artifacts: `pkg-input/`, distinct `pkg-root-sync*` stages, and final
`pkg-root-sync-5/fixture/validated-capability-manifest.json`,
`install-build-1/`, `fixture/disk.packaged-built.ext4`. Exact source/Makefile/
toolchain/deb hashes, logs and retained executed scripts are private.

### Actual loaded exec, PTY and concurrent topology

Two separately retained short windows each check **100 unloaded and100
build-loaded exec replies** with exact tokens. The corrected PTY window checks
**32 echo-disabled `ACK:<token>` replies**, while actual background SQLite
compilation is still active; the build subsequently completes successfully.
Existing agent behavior forces a guest-initiated reconnect after interactive
kill. The first window verifies32 ACKs but then times out by trying to reuse the
old connection; it is retained as a failed overall trial. The corrected runner
accepts that existing reconnect and passes the complete window. No runtime
protocol, timer or notification repair is hidden in the harness.

Actual **1/2/4 simultaneous jailed VM topology checks all pass**: seven fresh
VMs total, distinct CPUs8..11 and explicit CIDs100..103, separate disks/sockets,
one vCPU512MiB each. Every guest writes, syncs and reads its own identified
disk marker while all VMs in the declared group are alive. These are topology/
integrity capabilities, not60s aggregate throughput/fairness or fixed-total-CPU
comparisons. Exec/PTy cases use the declared10ms diagnostic heartbeat, do not
meet10000-observation/tail-confidence requirements, and do not resolve the
no-heartbeat idle failures above.

Artifacts: `g0-interactive/`, `g0-interactive-2/`, `g0-concurrent/`.

### Actual jailed disk/agent snapshot lifecycle

A real guest writes/syncs an identified disk marker. **Pause, snapshot,
disk-copy while paused and resume pass**; the original guest then executes and
reads the same marker. One observed operation timing is pause1.552ms,
snapshot324.386ms, three-file copy381.978ms, resume1.635ms. These are single
capability samples, not100-sample lifecycle distributions.

The frozen memory/state/disk are then restored into fresh enforced jails.
The first API-mode restore loads real512MiB memory, block/vsock devices, runs
guest serial heartbeat and serves its API, but **no guest agent reconnect
arrives within30s**. After the storage cleanup below, separate API-mode and
CLI-mode repeats also time out30s: **3/3 actual restored-agent/state checks
blocked**, not passed from `Running`, heartbeat or file existence. Consequently
the restored guest application/disk acceptance remains unmet. The original
seven unjailed integrations' resumed serial marker is separate coverage.

Artifacts: `g0-disk-snapshot/original/`, `frozen/`, `restored/`,
`api-repeat-2/`, `cli/`, `capability.json`, `restore-repeats.json`.

### Actual full-window flush diagnostic and syscall latency

One corrected process-scoped profiled fio trial runs **10s ramp+60s measured**
4KiB direct random write, sync engine, QD1, fdatasync per write and final fsync.
All job errors are0; fio reports **2548.040866IOPS**,152885 measured writes.
An initial wrapper fails after fio because bare `sync` is absent from the
BusyBox-only fixture; it remains a failed capture. The accepted repeat uses
verified BusyBox paths, parses guest JSON before exit, and collects all three
listed VMM TIDs (unchanged before/after) with syscall entry/exit traces.

Trace duration includes warmup and final drain. It pairs **183862 pwrite64**
and **183826 fdatasync** calls, no unmatched entries/exits or reported lost
events. Timestamp resolution is1µs:

| Actual host syscall wall time | Mean / median / p95 / p99 / max |
|---|---|
| pwrite64 | **5.047 /4 /7 /10 /10737 µs** |
| fdatasync | **145.054 /60 /126 /2662 /205442 µs** |

Fio measured write-latency median/p95/p99 are91.648/112.128/284.672µs;
guest sync-latency median/p95/p99 are152.576/493.568/3194.880µs.
These process-scoped durations include external scheduling and I/O wait;
they do not isolate disk wait, provide complete asynchronous kernel/writeback
CPU accounting, or constitute unprofiled paired confidence. The long flush
outliers warrant preserving diagnosis, **not selecting a backend from one
confounded profile** while mandatory qualification is blocked.

Artifacts: `g1-flush-diagnostic/`, accepted `g1-flush-diagnostic-2/`, raw perf,
script, checked guest JSON and `syscall-duration-summary.json`.

### Current noise/storage controls and bounded cleanup

A new locked5s host control after package/capability work observes
**98.824118%busy**. Unowned load remains untouched; this is not attributable
VMM/kernel I/O CPU. The shared600GiB filesystem also reaches99% use and a
further restore-copy fails **ENOSPC**, before a VM starts. That failed repeat
is not an executed restore or a pass.

To avoid consuming other users' space, only **14 explicitly named, completed
read/idle run disk copies** are released after checking their recorded PIDs
absent:30,251,024,384 allocated bytes. All raw JSON/logs/perf/stat/exit data,
original unchanged baseline binaries/assets, canonical repaired fixtures and
frozen snapshots remain. The cleanup manifest lists every removed image and
retained input. Observed headroom rises from6.4GiB to37GiB (94%used); the later
restore repeats are separately declared post-cleanup. Do not compare this
storage regime with earlier profiles as an optimization gain.

Later independent shared-host changes leave120GiB available (81%used) at
18:26 UTC; that additional space is **not attributed to this task's cleanup**.
A fresh locked5s control at **18:27:40 UTC** nevertheless measures
**99.849962%busy**. Original baseline VMM/agent/kernel hashes still match;
`continued-g0-cleanup.json` checks **183 recorded owned PIDs absent**, no owned
device nodes or sockets. Storage capacity is no longer the immediate blocker,
but neither the noisy host nor required idle/restored-agent acceptance is
resolved.

**Remaining:** real no-heartbeat idle progress, restored-agent/disk acceptance,
controlled host/storage/cache strata, full ten-pair workload matrix,10000
interactive and100 lifecycle observations, all-worker/attributable kernel CPU,
frozen numeric gates and the conditional G2–G5 experiment. Prerequisite done
does not mean the async plan is done. No backend/default/performance merge.

## Explicit root perf cache/scratch confinement follow-up

Collector and decoder commands now put project-local `PERF_BUILDID_DIR` and
`TMPDIR` **inside `sudo -n env`**, with `DEBUGINFOD_URLS` empty. The harness
rejects symlink, foreign-owned or non0700 cache/scratch directories before
elevation. Root report/script use force-read for the deliberately exact-file
ownership-transferred private artifact, not overwrite an existing capture.
Future private profile wrappers use the same helper. No VMM runtime changes.

Historical collector argv did **not explicitly scope the root build-ID cache**;
their location must not be asserted private or used as a fully controlled
comparison. No global/root cache is inspected, modified or cleaned in this
follow-up. Existing raw commands/evidence remain unchanged.

Validation under the fleet lock:

- **9/9 focused framing/cache regressions pass**, including rejecting a
  symlink and an insecure existing directory without touching their targets.
- **12/12 Python cases each against Debug/Safe binaries pass**, including the
  three real enforced-jail regressions; no skips. Earlier32-unit/7-integration
  results remain separately executed coverage, not newly rerun here.
- A real owned jailed guest performs checked fio during scoped software/KVM
  stat and199Hz DWARF recording. Root report/script succeed after the single
  owned600-mode perf.data is deliberately chowned to UID1000 and decoded with
  force-read. Accepted record: **647 samples, zero lost**. Cache/scratch roots
  are0700; this capture creates **zero build-ID cache entries**, so no cache
  population claim is made. This is tooling acceptance, not a gain/noise gate.

The actual roster contains two `flint-safe` TIDs and one
`kvm-nx-lpage-re`-named TID; **all three report Kthread0, UID/GID1000,
CapEff0, NoNewPrivs1, Seccomp2** on this kernel. Do not relabel that kernel
helper as an unfiltered userspace I/O worker, or infer its precise role from
Kthread alone. All listed TIDs are collected; complete thread-creation/kernel
I/O attribution still is not established.

The roster also records **supplementary Groups0** retained by this synchronous
revision. Clearing inherited groups is not part of `5ee81b1`; any common
credential-hygiene follow-up must be coordinated and revalidated as a new
correctness revision, never silently mixed into these profiles or attributed
as an optimization. Divergent peer directory/filter patches are not this
identical corrected configuration.

Post-validation cleanup checks185 recorded VM/supervisor/collector PIDs:
none remains, with no owned device nodes/sockets. Original kernel/agent/VMM
and repaired safe binary hashes still match. This count uses the retained
launch/*pid manifests, not a whole-host process inventory.

Artifacts: `prerequisite/perf-cache-validation*.log`,
`prerequisite/perf-cache-all-tests.log`, `perf-cache-cleanup.json`,
distinct `perf-cache-check/` and final
`perf-cache-check-2/` with exact post-sudo argv, checked guest outputs,
thread roster, force-read reports/script and `acceptance.json`.

## Common supplementary-group correctness follow-up

The newly captured5ee roster retained bootstrap group0 after configured
UID/GID drop. Jail setup now performs checked `setgroups(0, NULL)` before
setgid/setuid and filter installation. Failure aborts admission. No syscall
allowlist, host device, guest feature, compiler/dependency, worker or
notification setting is changed.

The real API regression deliberately launches the child through
`sudo -n setpriv --groups=0 -- <flint ...>` before jail setup. Against retained
5ee safe ELF, the three real regressions execute **2pass/1expected failure**:
the dropped process still reports Groups0. New fixed-target Debug/Safe each
execute **32/32 unit,7/7 real KVM integration,12/12 Python cases** successfully;
no skips. Four additional actual jailed boot+disk controls (Debug/Safe×API/CLI)
pass guest marker write/sync/hash and independent backing readback. All their
listed tasks have configured UID/GID1000, empty supplementary groups,
CapEff0, NoNewPrivs1, Seccomp2. Directory0755root and device0600configured-user
policy remains unchanged and artifacts retain077.

The frozen build commands are
`zig build {test,integration-test} -Dtarget=x86_64-linux -Doptimize={debug,safe}`,
with project-local cache/scratch and
`-Dintegration-kernel=../.perf/blk-io/fixture/bzImage` for KVM tests. Real Python
tests use the matching named binary and verified kernel. Every executed phase
takes the absolute shared fleet lock.

One initial diagnostic omitted the frozen target and built dynamic native
glibc Debug. Its enforced guest case dies on **madvise66/SIGSYS** after
successful group clearing; a trace confirms syscall28. Its11/12 Python result
is preserved, not acceptance or baseline evidence. The first trace attempt
used nonexistent `/usr/bin/strace` and failed before admission; the subsequent
owned extracted tracer captures the actual kill. Restoring the unchanged
`x86_64-linux` target produces the intended static baseline and passes, with
**no madvise permission added**. The misbuilt binary/commands remain separate.

After all four controlled VMs close, a new five-second locked no-owned-VM
control records **79.94busyCPU-s/5.000297wall-s,99.937492%busy** (~15.987cores).
It establishes continued host saturation, not attribution to a particular
unowned task. No background CPU is subtracted into a saving, and no unowned
process is signalled. This prerequisite is not a performance result.

Raw evidence: `group-clear/old-safe-negative.log`,
`group-clear/validation.log`, `debug-guest-trace*.log`,
`frozen-validation.log`, `api-cli-validation.log`, `host-control.json`,
retained named ELFs and `control/{d,s}-{api,cli}/` with actual credential and
disk proof; the owned enforced trace is retained under `jail-tests/`.
Earlier5ee profiles and canonical assets remain distinct.

## Final common-revision G0 recheck and negative decision

Common runtime source is `ced7ed72b5b2f80286e37ba8c9d5eada0cb90236`;
frozen safe ELF SHA256
`8b1f575dfe60276f4b65a0d159756b5f1dbb6ec86bcfc2d8a3cc3a8f882395d7`.
Original5ee/untouched L0 binaries and all prior profiles remain separate.
Kernel/agent, signed package root and original target/dependencies/features
are unchanged; source, ELFs, snapshot memory/state/disk hashes are frozen in
`group-clear/frozen-manifest.json`.

### Actually executed fresh capability outcomes

| Capability | Actual result |
|---|---|
| No-heartbeat API exec, immediate startup | Trial1 passes1.621708ms; trial3 times out before idle |
| No-heartbeat CLI exec, immediate startup | Trial2 passes1.211796ms |
| Same connections after5s idle | **0/2 pass**, both2s socket deadlines expire; no third post-idle sample |
| Actual packaged SQLite pause/snapshot/copy/resume | **1/1 pass**, marker and DB1337 rechecked in resumed original guest |
| Fresh restored agent/application/disk state | **0/3 pass**, API/CLI/API each agent-accept deadline30s expires |
| Restored guest serial/API | Heartbeat bytes in all3; API Running for API cases is diagnostic only, not restored-state acceptance |

The first exact retained fresh-G0 runner stops on trial3's initial timeout.
Two already-written idle results and that actual exception are retained and
classified without pretending a third idle request ran. A separately saved
`probe-group-g0.py --lifecycle-only` continuation runs the real lifecycle.
No guest instrumentation, protocol or runtime patch is added to manufacture
control progress. Legacy vsock liveness is distinct from future block worker
wake correctness; no eventfd design/prerequisite is inferred.

### Host control, custody and qualification limits

Final locked no-owned-VM5s control: **80.01busy CPU-s /5.0075599998wall-s,
99.8377838782%busy** (~15.978busycores). Busy includes user/nice/system/IRQ/
softIRQ, excludes idle/iowait/steal and does not double-add guest. Independent
earlier control79.94CPU-s/5.0003s remains distinct. Neither establishes the
identity/cause of unowned work, nor is subtracted into normalized savings.
Only an owner-approved quiet condition can resolve this host qualification.
No unowned resource, security setting or global cache is changed.

Final custody scan checks **234** recorded VM/supervisor/collector PIDs:
none remains; no owned device nodes/sockets remain. Original kernel/agent/VMM
and prior5ee repaired ELF hashes still match. All raw measurements, signed
inputs, canonical assets and actual frozen snapshot are retained privately.

**Decision: keep existing synchronous default, do not select/implement G2.**
Required G0 capabilities and repeatable whole-system qualification fail.
Historical6×10s QD8 read diagnostics (mean10948.49IOPS,SD531.73,CV4.857%)
are not full10-pair/60s gates, and are a different correctness revision.
Single flush, install/build, short exec/PTY/concurrency and lifecycle windows
are capabilities/profiles, not missing distributions. `B/N`, numeric gates,
resource budget and before/after candidate remain **null/unqualified**.
Hardware cycles/instructions are unsupported; privileged software/KVM traces
work, so missing PMU is a limitation, not an invented profiling blocker.
Complete SMT-aware client/VM freeze, thread-creation census and attributable
kernel I/O CPU accounting remain outstanding.

There is **no measured before/after delta or performance gain**. The useful
jail prerequisite and collector repairs are complete; async implementation,
correctness/fault/wake/lifecycle qualification, G1 matrix and G2–G5 remain
blocked/incomplete. Draft PR#7 is not eligible for performance merge or
promotion. This is a reproducible negative baseline experiment, not a
compile-only prototype or a claim that an unbuilt worker regressed.

Reproduction/private evidence:
`group-clear/fresh-g0.log`, `fresh-g0-initial-executed.py`,
`control/fresh-idle-series.json`, `fresh-lifecycle.log`,
`life/{original,r-1,r-2,r-3}/`, `life/fresh-capability.json`,
`frozen-manifest.json`, `final-host-control.json`,
`final-artifact-validation.log`, and latest `perf-cache-cleanup.json`.
The exact executed scripts are retained. A rerun must choose a fresh
project-private variant rather than overwrite these run directories, take
the same absolute fleet lock, preserve077 and explicitly use this runtime
and fixed asset hashes. Parent/owner can then resolve capability and quiet
conditions, freeze gates, and only afterward authorize the bounded worker.

## Original diagnostic validation

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

**Before/after comparisons of throughput, IOPS, request/interactive tails, total attributable
CPU, idle VM cost, lifecycle distributions and confidence intervals: not
measured. No candidate exists.** The newer repaired synchronous-only diagnostic
numbers above do not establish a comparison. No numeric workload gate or A/A noise bound was
frozen from these startup counters. Proposed thresholds remain provisional.

## Required matrix and decision

| Acceptance row | Executed qualifying comparisons |
|---|---|
| Random read/write 4 KiB, QD1/8/32, achieved depth | **0; blocked** |
| Sequential read/write, QD1/16 | **0; blocked** |
| Flush-heavy and guest direct/buffered/host-cache strata | **0; blocked** |
| Offline package and representative build | **0 qualifying comparisons; one actual pinned offline install/build capability passes** |
| 1/2/4 concurrent VMs and fairness | **0 qualifying comparisons; seven actual topology/disk checks pass** |
| Loaded/no-load exec first-byte/response and identified PTY replies | **0 qualifying comparisons; short heartbeat-assisted capabilities pass** |
| Idle after load; pause/snapshot/disk copy/resume/restore distributions | **0 qualifying comparisons; pause/copy/resume pass; idle3/3 and restored-agent3/3 checks block** |
| Async faults/mutation/backpressure/wake/generation/drain/isolation | **0; no backend selected** |
| Non-nested comparison | Unavailable; no extrapolation |

**Keep synchronous pending an independently qualified repaired baseline.** This
does not demonstrate that a worker is slow or unwarranted. G0/G1 are incomplete,
so selecting/implementing a backend or freezing performance margins now would
violate the profile-first experiment. G2–G5 remain unexecuted; the plan stays
active/blocked. No default promotion, rollback claim, auto-merge or performance
merge recommendation is made.

Next work: use the declared repaired synchronous configuration identically on
both sides; reserve/control a host suitable for total CPU
attribution; establish real no-heartbeat idle control progress without treating
#3's optional notification optimization as a prerequisite; establish actual
restored-agent/disk acceptance; execute the full synchronous matrix/A/A profiles
and freeze gates. Guest fio/higher-QD/written dataset and the pinned disk-root
offline package/build capability are now verified.
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
- `prerequisite/`, `jail-tests/`, `repaired-sync*`: separate repair-stage
  binaries/traces, actual32/7/10 Debug/Safe counts, enforced guest/disk checks.
- `fio-sync/`, `fio-sync-libaio/`: exact dynamic/plugin closure and distinct
  failed/successful guest fio captures, checked1GiB prefill/depth JSON.
- `g0-loaded-profile/`: repaired source/binary/fixture copies, six short
  unprofiled trials, raw stat/perf/script/report events, host control,
  no-heartbeat startup/idle controls, retained executed scripts and summaries.
  `final-cleanup-evidence.json` checks **83 recorded owned PIDs absent** and
  no remaining owned device nodes/socket paths.
- `pkg-input/`, `pkg-root-sync*/`: signed/pinned offline inputs, failed and
  accepted disk-root stages, actual package/build and host backing DB checks.
- `g0-interactive*`, `g0-concurrent/`, `g0-disk-snapshot/`: actual loaded token
  integrity/topology/lifecycle evidence, including failed restored-agent cases.
- `g1-flush-diagnostic*`, `post-package-host-control/`: full-window single
  flush diagnostic/syscall wall-duration trace and later whole-host control.
- `redundant-image-cleanup.json`: exact14 owned redundant images released on
  ENOSPC, retained canonical inputs and raw measurements; no other tree touched.
- `post-cleanup-host-control/`, `continued-g0-cleanup.json`: separately timed
  current99.849962%busy control,183 recorded PID checks and original asset hashes.

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
