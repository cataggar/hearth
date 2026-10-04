const std = @import("std");
const Translator = @import("translate_c").Translator;

pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});
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

    b.installArtifact(exe);

    const eventfd_preflight = b.addExecutable(.{
        .name = "eventfd-preflight",
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/eventfd_preflight.zig"),
            .target = target,
            .optimize = optimize,
            .link_libc = true,
        }),
    });
    eventfd_preflight.root_module.addImport("kvm_abi", kvm.mod);
    const preflight_step = b.step("eventfd-preflight", "Probe real KVM eventfd capabilities without enabling acceleration");
    preflight_step.dependOn(&b.addRunArtifact(eventfd_preflight).step);

    const guest_probe = b.addExecutable(.{
        .name = "eventfd-guest-probe",
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/eventfd_guest_probe.zig"),
            .target = target,
            .optimize = optimize,
        }),
    });
    b.step("eventfd-guest-probe", "Build the blocking, heartbeat-free guest-initiated vsock probe")
        .dependOn(&b.addInstallArtifact(guest_probe, .{}).step);

    const tcp_probe = b.addExecutable(.{
        .name = "eventfd-tcp-probe",
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/eventfd_tcp_probe.zig"),
            .target = target,
            .optimize = optimize,
        }),
    });
    b.step("eventfd-tcp-probe", "Build the blocking, heartbeat-free native TCP guest probe")
        .dependOn(&b.addInstallArtifact(tcp_probe, .{}).step);

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

    const run_tests = b.addRunArtifact(tests);
    const test_step = b.step("test", "Run tests");
    test_step.dependOn(&run_tests.step);

    // Integration tests: spawn flint binary and test end-to-end behavior.
    // Requires /dev/kvm and a configured Linux kernel fixture.
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
    const integration_options = b.addOptions();
    const integration_kernel = b.option([]const u8, "integration-kernel", "Path to the integration kernel (resolved from vmm/)") orelse "/tmp/vmlinuz-minimal";
    integration_options.addOption([]const u8, "kernel", integration_kernel);
    integration_tests.root_module.addOptions("integration_options", integration_options);

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
