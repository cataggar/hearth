# Canonical performance jail correctness prerequisite

This correctness-only baseline repair is separate from every performance
backend, compiler experiment and adoption decision. Preserve original failed
L0 binaries/traces; do not attribute any gain to repairing jail startup.

## Contract and provenance

Runtime is exactly the common repair from `f2f9ab4`, `5ee81b1`, `ced7ed7`:

- No-follow FD normalization sets jail device directories root:root0755 and
  nodes configured UID:GID0600, independently of ambient artifact umask077.
  Host device modes/ownership and system settings are unchanged.
- Clear supplementary groups before dropping GID/UID.
- Permit only traced recvmsg47/sendmsg46; self/PID0 sched_getaffinity;
  nonblocking poll7/timeout0; epoll_pwait281/null signal mask; and Linux's
  ignored CLONE_DETACHED bit in otherwise confined thread clone flags.
- Retain AF_UNIX confinement, namespace-clone denial, non-executable mappings,
  other-process affinity denial, nonnull epoll-mask denial, blocking-poll
  denial and eventfd/io_uring denial. No madvise allowance for a drifted
  dynamic-glibc target.

The standalone `tools/perf/test_jail_baseline.py` does not import the performance
runner or async worker. It checks real enforced API receive/send, umask077
directory/node ownership/access, empty groups/caps and all actual VMM task
filters, plus real CLI/API guest disk write/fsync/read/hash and unchanged host
KVM metadata. Missing prerequisites fail, not skip.
Its small serial fixture is synchronous correctness, not a throughput,
interactive, timer-free wake or snapshot performance acceptance.

Cleanup evidence persistence is not a prerequisite for resource teardown.
An injected ENOSPC while saving the exited child's cleanup record must still
close both logs and remove its private device directory/node and API socket;
the original evidence error must propagate. The focused fourth case exercises
this on a real enforced API child, checks every recorded PID path is gone,
and writes a separately identified fault audit after teardown. It is an
injected write failure, not a claim that the host was full during that test.

## TAP declaration limitation

Unchanged `main.zig` provisions TUN before API entry only when CLI `--tap` is
present (`need_tun = cli.tap != null`). An API network request alone does not
retroactively provision `/dev/net/tun`. A future enforced TAP diagnostic must
explicitly declare its owned TAP at startup; do not grant TUN broadly or infer
device absence from an unclassified failed network window. The standalone
fixture exercises neither TAP nor vhost device/worker isolation, and this
prerequisite does not establish a product TAP consumer or kernel-network
lifecycle acceptance.

## Reproduction

Use the isolated peer worktree, identical compiler/dependency/guest features
for matched rows, and private project-relative caches/scratch. All build/test
execution belongs inside the common fleet lock. Example after building the
intended static target:

```bash
umask 077
flock /d/hearth/.perf/fleet/host.lock bash -lc '
  umask 077
  cd <isolated-worktree>
  export PYTHONDONTWRITEBYTECODE=1
  export FLINT_JAIL_TEST_BINARY="$PWD/vmm/zig-out/bin/flint"
  export FLINT_JAIL_TEST_KERNEL="<verified-project-relative-bzImage>"
  export FLINT_JAIL_TEST_REVISION="<canonical-prerequisite-commit>"
  python3 -m unittest discover -s tools/perf -p test_jail_baseline.py -v
'
```

Kernel5.10.245 SHA256:
`4da539807474d189f1a15852046994e78d430a194c2e78b9255ae880069c7208`.
Bootstrap uses sudo -n/setpriv with inherited root supplementary group0,
then verifies the actual dropped identity and enforced filter. Optional
`FLINT_JAIL_TEST_STRACE` points to an owned tracer and retains raw enforced
traces. Raw launches/credentials/owned-PID cleanup and guest results stay
private under `.perf/jail-baseline/`, never full images or unrelated metadata
in a public PR.

Passing this prerequisite does not authorize a native-size waiver, quieter
host assumption, async/vhost/eventfd adoption, performance merge or auto-merge.

## Integration provenance

Clean `b06ec0a` histories use the single-parent, five-file cumulative prerequisite
`7dfee42ed68fe1703744d6318f4be632113034b0`. Its fixture is self-contained;
do not import the historical block-performance harness to satisfy it.

For a peer that already committed the partial `f2f9ab4` repair, the forward-only
reconciliation is `cde7d842bc6854dc2daced42f4cc8b1124982660`, with exact parent
`f2f9ab4c8e7a67097f2c3f52636327e9c41d5084`. Only the three common runtime/test
files and standalone fixture/contract change. All five resulting blobs were
verified byte-identical to `7dfee42`; this extraction executes no new tests.
Retain peer-specific device/filter overlays and rerun actual enforced-jail
acceptance against their combined source. Preserve prior SIGSYS failures.

This reconciliation preserves, but does not endorse or repair, the old f2
CI/harness dependency. It is not a clean baseline or an alternative main merge
chain. Main and clean peers must use `7dfee42` directly. The private verified
bundle and extraction manifest are under
`.perf/blk-io/canonical-prerequisite/jail-after-f2.bundle` and
`.perf/blk-io/canonical-prerequisite/f2-forward-bridge.json`; peer convergence
remains pending until application and fresh acceptance are acknowledged.

Already-f2/5ee histories needing only supplementary-group reconciliation can
instead use `fede9ba2fba736d151b53b0b17b45428cc1473b8`, exact parent
`5ee81b163b266f9c7643fb67c88cb59fe7aa2878`. Its only runtime change is the
checked group-clear before GID/UID drop; the two other changed files are the
same standalone fixture and contract. It does not touch seccomp, so an owned
conditional blocking-poll overlay remains independently reviewable. All five
common jail/seccomp/unit/fixture/contract blobs match canonical `7dfee42`.
Clean histories must still take `7dfee42`, not these historical forward chains.

On October5 a fresh locked check reused the SHA-verified canonical LLVM static
Debug/Safe executables and unchanged standalone fixture: **1/1 actual enforced
API child-credential case per mode, 2/2 total**, two actual VMM tasks. Each
bootstrap deliberately inherited root group0; every observed VMM task had
configured UID/GID, empty groups, zero effective caps, NNP1 and Seccomp2.
Private KVM access and six checked PUT/GET exchanges per mode passed. Recorded
owned PID paths, private nodes and sockets were gone after both cases. These
were not guest boots, new unit executions, peer-overlay/native/GNU acceptance,
or performance measurements.

Exact command and fresh rows are retained privately as
`recheck-child-groups.py`, `groups-current-run.log`,
`groups-current-{debug,safe}.log` and `groups-current-results.json` in the
canonical-prerequisite directory. The bounded phase used the common exclusive
fleet lock; copied fixtures remained project-relative and each admission
required at least64MiB available space. The corresponding group-only bundle is
`jail-groups-after-5ee.bundle`; its custody manifest is
`groups-forward-bridge.json`.

## Evidence-write cleanup acceptance

The helper now puts log closure and private node/socket removal in `finally`;
an ENOSPC from saving `cleanup.json` after child joining still propagates.
The focused new case injects only that write failure on an actual enforced API
child, verifies groups/caps/filter, and independently checks PID absence,
closed logs and removed device directory/socket. Its separate fault audit
identifies the injection; this is not a simulated guest success or a claim
that the host was full during validation.

An unchanged `7dfee42` helper negative control actually reproduces retained
logs/node/socket after the joined child's injected evidence error; the fixed
helper then explicitly cleans that same owned launch. Debug/Safe subsequently
execute **4/4 standalone cases each, 8/8 total, no skips**, including four real
CLI/API guest disk boots and two real enforced-child injected-ENOSPC cases.
All nine launches pass PID/node/socket custody checks. An initial import/
indentation failure executes zero tests and is retained separately.

Executables remain the SHA-verified canonical LLVM static binaries; no VMM
source, syscall allowance, compiler/dependency/guest feature or performance
gate changes. These counts are not native/GNU, sibling net/worker or production
application-state acceptance. Exact command, case/log hashes and negative
control are retained in `check-cleanup-fault.py`, `check-cleanup-fault.log`,
`cleanup-current-{debug,safe}.log`, `cleanup-current-results.json` and the
separate cleanup acceptance manifest under the canonical-prerequisite
directory. The phase rechecks at least256MiB before each bounded mode/control and holds
the common exclusive fleet lock; no new large images or performance sample.

The separately scoped follow-up is
`98b10c21f7769e36799d0994f231d7e881953ac3`, exact parent `7dfee42`.
It changes only this fixture and its minimal contract; all VMM files remain
byte-identical to `7dfee42`. Clean integration is `7dfee42` then `98b10c21`.
Historical peers without the standalone file must inspect/import that exact
fixture blob rather than blindly applying a modify/delete conflict or
importing block/backend patches. The private verified bundle is
`jail-fixture-enospc.bundle`, with source/log/custody hashes in
`cleanup-acceptance-manifest.json`.

## Acknowledged shared reuse and scoped acceptance — 2026-10-05

The common jail repair's delivery/source convergence and controlled acceptance
are complete, independently of performance/default/merge qualification:

- Plan#2 acknowledges `7dfee42` as `a72b0a1`. Read-only Git verification finds
  only the standalone fixture/contract added, with no VMM change from its
  already-repaired parent. Its conditional vhost device/eventfd/poll overlays
  remain independent, not a claim that its whole filter equals legacy `7dfee42`.
  It reports actual new static Debug/Safe **35 units,7 KVM,3 standalone jail
  cases per mode**, separately from older or aborted epochs. Current published
  head is `175398c57d6483254efa1eb89f1feff3269ab3fd`. It also adopts the
  fixture-only `98b10c21` follow-up as `bd4eb41`; the current fixture blob
  exactly matches that hardening. Its subsequent focused enforced-child
  ENOSPC case executes **Debug1+Safe1=2**, without guest boots, rerunning the
  prior three-case suite or changing VMM/runtime permissions.
- Plan#3's current published head is
  `7efea146094b6674ecaf783ce3c05453cdb5db6f`, canonical integration `85e6f3b`.
  Its jail blob is exact `7dfee42`; common whitelist and all six common
  argument-check blocks match the canonical source, with separately confined
  mailbox/SO_ERROR support and shifted dispatch layout. The standalone
  fixture differs only by removing unsupported `--cmdline` for this runtime's
  actual positional CLI. This is not whole-filter/five-file byte equality.
  New integrated static Debug/Safe rows each execute **63 Zig cases+3 common
  enforced cases**:39 units,17 dedicated (16 enforced KVM+1 policy),7 existing
  integrations (5 actual guests+2 CLI/errors). Separate exact-bare-canonical
  Debug/Safe rows each execute **32 units+3 common cases**. Totals are
  **190 Zig cases+12 common enforced cases**, not190 unit/KVM cases.
  Read-only verification of its published `canonical-jail-validation.tar.gz`
  checks all93 payload hashes and the four uncached-success test summaries;
  all12 archived cleanup receipts have empty live-PID lists. Archive SHA256:
  `2df844798fe2e040fa341c24e4493df3ed276374f45955beb8c50969070cc6e3`.
  Prior4/4 jail/12 Linux/64-ID controls remain separately pinned, not relabeled.
- Plan#6 acknowledges one `7dfee42` cherry-pick as
  `327f1832c26c4e98948c04e920094e6d36e956fe`. This worktree's read-only Git
  comparison verifies all five common blobs exact and only fixture/contract
  added to its already-exact runtime. It subsequently reports actual forced
  acceptance on **all four static Debug/Safe × LLVM/native cells:32 unit,
  7 real KVM,3 standalone cases each;128/28/12 total**, no skips/cached-run
  inference. The12 jail cases verify077 access, CLI/API serial disk
  write/fsync/read/hash and all-task identity/empty groups; all24 recorded
  standalone PID paths and private nodes/sockets are gone. Its retained
  `canonical-v5-final.json` and its clean v5 publication
  `39e6aaa029d14372e10d0532f6f6012c6e2ca57a`/draft PR10 preserve these
  peer executions. Different cache histories/test-build times are not speedups.

These are explicitly **peer-reported execution scopes**, not additional
executions by this worktree or native/GNU acceptance of the fourth
`98b10c21` evidence-fault case. This worktree's own canonical and cleanup
proof remains separately recorded above.

Plan#6 subsequently adopts fixture-only98 as
`3414df47131b2116afed302fda2e3acb5ac1915d` and publishes
`91ca9ed2ab7accaef6620702f90c36ec2bd98ec8`. Read-only Git comparison verifies
all three VMM/runtime/unit blobs still exact7d and the fixture exact98.
Its four frozen-ELF Debug/Safe × LLVM/native cleanup rows report **4/4 each,
16/16 total, no skips**:8 small guest disk boots,4 ordinary API controls and4
real API children with injected cleanup-evidence ENOSPC. All32 recorded PID
paths/device nodes/sockets are gone;28 captured dropped-task statuses have
UID/GID1000, empty groups, zero effective capabilities, NNP1 and Seccomp2.
Peer raw receipt:
`.perf-zig-native/evidence/postcleanup-summary/canonical-cleanup-enospc-v1-final.json`.
This is a separate fixture epoch, **not renewed/pooled128/28/12 acceptance**,
new compilation/performance, GNU acceptance or a size/guard/default waiver.

Plan#6's later `303831b` publication applies only the positional-CLI token
correction atop98 as `fd5db24`. Read-only byte comparison verifies that single
change and unchanged three common runtime/unit sources. Its frozen four-ELF
CLI-only cohort reports **1/1 each,4 total**,8 PID paths/nodes/sockets gone;
before/after guest command lines are identical. It does not rerun or pool
the16-case cleanup or128/28/12 cohorts. Fixture SHA256 is
`23b15b655d2b93d2ed0431f97be36c842b50c7aa4440e5bdead89842671d4ee6`;
peer raw receipt is `canonical-cli-positional-v1-final.json`.

The latest reconciliation reads only public PR metadata and Git objects in
this worktree; it wakes no finished peer and runs no tests, VMs or profiles.
Plan#2/3's common simple whitelist and clone/socket/mprotect/affinity/epoll/poll
check assignments compare equal to the canonical source. Their declared
device/mailbox overlays are not missing canonical repairs. Superseded
group-missing/forward-bridge warnings must not trigger duplicate adoption.

Later workload preparation still fails ENOSPC at locked manifest creation
before a VM or row, and independently timed busy-core controls do not certify
a quiet host. Native size rejection, mandatory workload/IRQ/lifecycle/SDK/
total-cost qualification and all default/merge decisions remain separate.
Canonical delivery is not the remaining blocker; do not duplicate the repair,
relax guards, borrow runtime prototypes or attribute these correctness gains
to a performance backend.
