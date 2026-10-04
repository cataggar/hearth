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
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});
    const codegen = b.option(Codegen, "vmm-codegen", "Artifact code generator (default: auto)") orelse .auto;
    const linker = b.option(Linker, "vmm-linker", "Artifact linker (default: auto)") orelse .auto;
    const force_test_run = b.option(bool, "perf-force-test-run", "Execute unit tests even when cached") orelse false;
    const kernel_override = b.option([]const u8, "perf-test-kernel", "Integration kernel path relative to vmm/");
    const integration_options = b.addOptions();
    if (kernel_override) |path| {
        if (std.fs.path.isAbsolute(path) or path.len == 0) @panic("perf-test-kernel must be a nonempty project-relative path");
        var parts = std.mem.tokenizeAny(u8, path, "/\\");
        while (parts.next()) |part| {
            if (std.mem.eql(u8, part, "..")) @panic("perf-test-kernel must not traverse outside vmm/");
        }
    }
    const kernel_path = if (kernel_override) |path| resolved: {
        const cwd = std.process.currentPathAlloc(b.graph.io, b.graph.arena) catch @panic("cannot resolve integration kernel working directory");
        const relative = b.root.joinString(b.graph.arena, path) catch @panic("OOM");
        break :resolved b.pathResolve(&.{ cwd, relative });
    } else "/tmp/vmlinuz-minimal";
    integration_options.addOption([]const u8, "kernel", kernel_path);
    const translate_c = b.dependency("translate_c", .{});
    const kvm: Translator = .init(translate_c, .{
        .c_source_file = b.path("src/kvm/abi.h"),
        .target = target,
        .optimize = optimize,
        .default_init = true,
    });

    const exe = b.addExecutable(.{
        .name = "flint",
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/main.zig"),
            .target = target,
            .optimize = optimize,
        }),
    });
    exe.root_module.link_libc = true;
    exe.root_module.addImport("kvm_abi", kvm.mod);
    artifactOptions(exe, codegen, linker);

    b.installArtifact(exe);

    const run_cmd = b.addRunArtifact(exe);
    run_cmd.step.dependOn(b.getInstallStep());
    run_cmd.addPassthruArgs();

    const run_step = b.step("run", "Run flint");
    run_step.dependOn(&run_cmd.step);

    const tests = b.addTest(.{
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/tests.zig"),
            .target = target,
            .optimize = optimize,
        }),
    });
    tests.root_module.link_libc = true;
    tests.root_module.addImport("kvm_abi", kvm.mod);
    artifactOptions(tests, codegen, linker);

    const run_tests = b.addRunArtifact(tests);
    run_tests.has_side_effects = force_test_run;
    const test_step = b.step("test", "Run tests");
    test_step.dependOn(&run_tests.step);

    // Integration tests: spawn flint binary and test end-to-end behavior.
    // Requires /dev/kvm and a kernel (override with -Dperf-test-kernel).
    // Run with: zig build integration-test
    // Compile without prerequisites: zig build integration-test-build
    const integration_tests = b.addTest(.{
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/integration_tests.zig"),
            .target = target,
            .optimize = optimize,
        }),
    });
    integration_tests.root_module.link_libc = true;
    integration_tests.root_module.addImport("kvm_abi", kvm.mod);
    integration_tests.root_module.addOptions("integration_options", integration_options);
    artifactOptions(integration_tests, codegen, linker);

    const integration_build_step = b.step("integration-test-build", "Build integration tests without running them");
    integration_build_step.dependOn(&integration_tests.step);

    const run_integration = b.addRunArtifact(integration_tests);
    // KVM, the kernel, and fixture tools are runtime prerequisites, not cache inputs.
    run_integration.has_side_effects = true;
    // Integration tests depend on the flint binary being built
    run_integration.step.dependOn(b.getInstallStep());

    const integration_step = b.step("integration-test", "Run integration tests (requires /dev/kvm + kernel)");
    integration_step.dependOn(&run_integration.step);
}
