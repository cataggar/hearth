# Execution Plan: Eventfd Harness Review Fixes

**Scope**: Corrective harness changes based on frozen PR9
`6c218b0a68a4d1bfd820852c56b39c501fb1ae4b`; no VMM, benchmark execution,
historical-result rewrite or performance qualification.

**Status**: Completed corrective helper; parent coordination/reruns remain.

## Contract

- Capture admits only a live continuous disk producer with recorded PID and
  start-time identity, alongside the existing real network backpressure checks.
  Markers alone are not liveness or exact in-flight disk-I/O evidence.
- Lifecycle preparation validates and preserves tracked native startup, or
  normalizes the single known older untracked form. Ambiguity fails explicitly.
- Frozen gates derive artifact and fixed execution identity from every recorded
  C00 control manifest. Supplied artifacts must agree; missing, stale or mixed
  provenance fails rather than being supplied from current arguments.
  Candidates must match the verified frozen execution identity.

## Steps

1. Update the harness contract and implement the three independent fixes.
2. Exercise lightweight owned shell/fixture/provenance cases in existing Python
   tests under the exclusive fleet host lock. Do not run VMs or performance work.
3. Inspect the surgical diff, record actual validation, and commit for parent
   coordination. Leave historical evidence downgrade and reruns to the parent.

## Validation

Executed in `/d/hearth/.perf/worktrees/eventfd-harness-review-fixes`, umask077:

```sh
timeout 600 flock -x /d/hearth/.perf/fleet/host.lock \
  env PYTHONDONTWRITEBYTECODE=1 \
  python3 -m unittest discover -s benchmarks/virtio-eventfd -p 'test_run.py'
git --no-pager diff --check
```

- Final focused suite: **24/24 passed in 1.239s**, including 13 existing tests
  and 11 new behavior tests with focused subcases. Real owned shell processes
  exercise RPC exit propagation, PID/start-time/command matching, stale and
  completion markers, and controller-stop lifetime. Fixtures are prepared by
  `matrix.prepare`; their archive startup is only parsed, never executed.
- Preparation covers current tracked/idempotent and older normalized forms,
  unknown/ambiguous startup rejection, lifecycle boot args and TCP replacement.
- Freezing/candidate checks cover matching controls, varying mode/time/location,
  stale binary/fixture/kernel/initrd, mixed source/compiler/affinity/cache/
  workload conditions, missing/empty provenance and unqualified old gates.
- Earlier locked runs passed 23 tests in 1.181s and, after adding positive
  producer-start coverage, 24 tests in 1.264s. The initial `timeout 120 flock`
  attempt exited124 waiting for the lock, before running tests; the longer
  bounded retry succeeded. Final whitespace validation passed.
- Owned fixture directories and processes were cleaned; no dependency changes,
  VMs, benchmark matrices, published archives/results, pushes or merges.

The execution manifest schema remains the recorded controlled-run schema.
Gates now include verified fixed `execution_identity` and baseline-manifest
hashes; the fixture digest identifies recorded content excluding its relocatable
kernel path. Old gates without provenance are explicitly incompatible, not
silently upgraded. Numerical/statistical policy is unchanged.

No historical active-restore count is revalidated or newly accepted here.
The parent retains ownership of claim downgrades, real reruns, qualification
and any cherry-pick/merge decisions.
