# Execution Plan: Zig 0.17.0 and ghr-based CI

**Status**: In progress
**Issue**: #4
**Spec**: [Zig Toolchain and CI](../../product-specs/zig-toolchain-ci.md)

## Parallel Workstreams

1. Port `vmm/`: build APIs, translated KVM bindings, language/library changes,
   debug/safe builds, and focused unit/integration behavior.
2. Port `agent/`: target-aware translated libc bindings and both Linux targets,
   preserving PTY, protocol, signal, and file-transfer behavior.
3. Add CI and source-build version checks: signed ghr installation, explicit KVM
   prerequisites, required-result gate, and focused setup tests.

Each implementation runs in an isolated worktree rooted at the spec commit.
The unchanged source is retained in another worktree for the 0.16 baseline.

## Integration and Acceptance

- Merge the workstreams into one integration branch and resolve only migration
  coupling, not unrelated pre-existing behavior.
- Validate TypeScript build/type checks, Zig formatting, debug/safe unit builds,
  both guest-agent targets, and real KVM integration.
- Exercise original/new snapshot compatibility and guest communication.
- Collect compiler-only perf comparisons with repeatable commands and disclose
  unavailable hardware, tools, or coverage rather than claiming success.
- Update directly related setup/build documentation and record actual results.
- Publish a PR, confirm actual CI execution, and enable auto-merge only after
  the required acceptance gates are satisfied.

## Results

Pending implementation and validation.
