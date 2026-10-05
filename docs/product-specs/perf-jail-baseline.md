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
KVM metadata. There are three cases; missing prerequisites fail, not skip.
Its small serial fixture is synchronous correctness, not a throughput,
interactive, timer-free wake or snapshot performance acceptance.

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
