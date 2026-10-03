const std = @import("std");
const Translator = @import("translate_c").Translator;

pub fn build(b: *std.Build) void {
    var target_query = b.standardTargetOptionsQueryOnly(.{
        .default_target = .{ .cpu_arch = .x86_64, .os_tag = .linux },
    });
    if (target_query.os_tag == .linux and (target_query.abi == null or target_query.abi == .gnu)) {
        target_query.abi = .gnu;
        // openpty is in libc starting with glibc 2.34; do not inherit the build host's version.
        if (target_query.glibc_version == null) {
            target_query.glibc_version = .{ .major = 2, .minor = 34, .patch = 0 };
        }
    }
    const target = b.resolveTargetQuery(target_query);
    const translated: Translator = .init(b.dependency("translate_c", .{}), .{
        .c_source_file = b.path("src/libc.h"),
        .target = target,
        .optimize = .safe,
        .link_libc = true,
    });

    const agent = b.addExecutable(.{
        .name = "hearth-agent",
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/main.zig"),
            .target = target,
            .optimize = .safe,
            .link_libc = true,
            .imports = &.{
                .{ .name = "libc", .module = translated.mod },
            },
        }),
    });

    b.installArtifact(agent);

    const tests = b.addTest(.{
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/posix.test.zig"),
            .target = target,
            .optimize = .safe,
            .link_libc = true,
            .imports = &.{
                .{ .name = "libc", .module = translated.mod },
            },
        }),
    });
    b.step("test", "Test blocking POSIX and translated libc bindings")
        .dependOn(&b.addRunArtifact(tests).step);
}
