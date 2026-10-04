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
