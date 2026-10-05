# Product Specs Index

## Core

| Spec | Status | Summary |
|------|--------|---------|
| [SDK API Design](sdk-api-design.md) | Draft | Public TypeScript API surface |
| [Sandbox Lifecycle](sandbox-lifecycle.md) | Draft | Create → use → snapshot → destroy |
| [Filesystem Operations](filesystem-operations.md) | Draft | File I/O between host and guest |
| [Zig Toolchain and CI](zig-toolchain-ci.md) | Implemented | Zig 0.17.0 migration, signed compiler installation, and actual VMM/agent CI |

## In Design

| Spec | Status | Summary |
|------|--------|---------|
| [Environments](environments.md) | Draft | Declarative repo+setup+start provisioning, snapshotted for instant restore |

## Performance Experiments

All open performance issues have a spec and an active execution plan. Isolated
prototype implementation is not accepted performance evidence or adoption;
see each experiment's actual status and results.

The shared [canonical jail correctness prerequisite](perf-jail-baseline.md)
is independent of backend performance/default adoption.

| Issue | Spec | Execution plan | Status |
|-------|------|----------------|--------|
| [#1](https://github.com/cataggar/hearth/issues/1) | [Asynchronous VirtIO Block I/O](perf-async-block-io.md) | [Plan](../exec-plans/active/perf-async-block-io.md) | Planned |
| [#2](https://github.com/cataggar/hearth/issues/2) | [vhost-net Evaluation](perf-vhost-net.md) | [Plan](../exec-plans/active/perf-vhost-net.md) | Planned |
| [#3](https://github.com/cataggar/hearth/issues/3) | [VirtIO Eventfd Acceleration](perf-virtio-eventfd.md) | [Plan](../exec-plans/active/perf-virtio-eventfd.md) | Implemented prototype; qualification blocked |
| [#6](https://github.com/cataggar/hearth/issues/6) | [Zig Native Backend and Linker](perf-zig-native.md) | [Plan](../exec-plans/active/perf-zig-native.md) | Planned |

Planning and isolated prototype work can proceed in parallel; benchmark runs on
a shared host must not overlap. Reuse fixtures and measurement tooling, but hold
the compiler, source, guest image, and unrelated backend settings constant for
each comparison. Freeze baseline-derived acceptance gates before comparing
prototypes. Each experiment must produce a keep/reject decision, including a
negative result when warranted, before changing defaults.

The eventfd plumbing needed by #2 may be shared with #3, but adopting #3 is not
a prerequisite for evaluating #2. Likewise, evaluate #1 without attributing
notification changes to asynchronous I/O, and keep #6 separate from all VirtIO
changes. The [completed compiler migration](../exec-plans/completed/zig-017-ci.md)
provides prior profiling work and known fixture/runtime coverage limitations;
unavailable workloads are not passing results.

## Future

| Spec | Status | Summary |
|------|--------|---------|
| Port Forwarding | Planned | Expose guest ports to host |
| VM Pool | Planned | Pre-warmed VM pool for instant creation |
| Templates | Planned | Pre-built environment templates (Python, Node, etc.) |
| Observability | Planned | Logs, metrics from guest exposed to host |
