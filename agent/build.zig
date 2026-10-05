const std = @import("std");
const Translator = @import("translate_c").Translator;

const Codegen = enum { auto, llvm, native };
const Linker = enum { auto, lld, native };

fn artifactOptions(artifact: *std.Build.Step.Compile, codegen: Codegen, linker: Linker) void {
    artifact.use_llvm = switch (codegen) {
        .auto => null,
        .llvm => true,
        .native => false,
    };
    artifact.use_lld = switch (linker) {
        .auto => null,
        .lld => true,
        .native => false,
    };
}

pub fn build(b: *std.Build) void {
    const optimize = b.option(std.lang.Optimize, "optimize", "Optimization mode (default: safe)") orelse .safe;
    const codegen = b.option(Codegen, "agent-codegen", "Artifact code generator (default: auto)") orelse .auto;
    const linker = b.option(Linker, "agent-linker", "Artifact linker (default: auto)") orelse .auto;
    const force_test_run = b.option(bool, "perf-force-test-run", "Execute tests even when cached") orelse false;
    var target_query = b.standardTargetOptionsQueryOnly(.{
        .default_target = .{ .cpu_arch = .x86_64, .os_tag = .linux, .abi = .musl },
    });
    // Keep the guest binary static when the documented Linux targets omit the ABI.
    if (target_query.os_tag == .linux and target_query.abi == null) {
        target_query.abi = .musl;
    }
    if (target_query.os_tag == .linux and target_query.abi == .gnu) {
        // openpty is in libc starting with glibc 2.34; do not inherit the build host's version.
        if (target_query.glibc_version == null) {
            target_query.glibc_version = .{ .major = 2, .minor = 34, .patch = 0 };
        }
    }
    const target = b.resolveTargetQuery(target_query);
    const translated: Translator = .init(b.dependency("translate_c", .{}), .{
        .c_source_file = b.path("src/libc.h"),
        .target = target,
        .optimize = optimize,
        .link_libc = true,
    });

    const agent = b.addExecutable(.{
        .name = "hearth-agent",
        .linkage = if (target.result.abi.isMusl()) .static else .dynamic,
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/main.zig"),
            .target = target,
            .optimize = optimize,
            .link_libc = true,
            .imports = &.{
                .{ .name = "libc", .module = translated.mod },
            },
        }),
    });
    artifactOptions(agent, codegen, linker);

    b.installArtifact(agent);

    const tests = b.addTest(.{
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/posix.test.zig"),
            .target = target,
            .optimize = optimize,
            .link_libc = true,
            .imports = &.{
                .{ .name = "libc", .module = translated.mod },
            },
        }),
    });
    artifactOptions(tests, codegen, linker);
    const run_tests = b.addRunArtifact(tests);
    run_tests.has_side_effects = force_test_run;
    b.step("test-build", "Build POSIX tests without running")
        .dependOn(&tests.step);
    b.step("test", "Test blocking POSIX and translated libc bindings")
        .dependOn(&run_tests.step);
}
