const std = @import("std");
const abi = @import("kvm/abi.zig");
const c = abi.c;
const linux = std.os.linux;

fn call(fd: i32, request: u32, argument: usize, name: []const u8) !usize {
    const rc: isize = @bitCast(linux.ioctl(fd, request, argument));
    if (rc < 0) {
        std.debug.print("{s}: request=0x{x} errno={d}\n", .{ name, request, -rc });
        return error.PreflightIoctlFailed;
    }
    std.debug.print("{s}: request=0x{x} result={d}\n", .{ name, request, rc });
    return @intCast(rc);
}

pub fn main() !void {
    std.debug.print("uid={d} gid={d}\n", .{ linux.getuid(), linux.getgid() });
    const opened: isize = @bitCast(linux.open("/dev/kvm", .{
        .ACCMODE = .RDWR,
        .CLOEXEC = true,
    }, 0));
    if (opened < 0) {
        std.debug.print("open /dev/kvm: errno={d}\n", .{-opened});
        return error.KvmUnavailable;
    }
    const fd: i32 = @intCast(opened);
    defer _ = linux.close(fd);
    if (try call(fd, c.KVM_GET_API_VERSION, 0, "KVM_GET_API_VERSION") != 12)
        return error.UnsupportedApiVersion;

    inline for (.{
        .{ c.KVM_CAP_IOEVENTFD, "KVM_CAP_IOEVENTFD" },
        .{ c.KVM_CAP_IRQFD, "KVM_CAP_IRQFD" },
        .{ c.KVM_CAP_IRQFD_RESAMPLE, "KVM_CAP_IRQFD_RESAMPLE" },
    }) |capability| {
        _ = try call(fd, c.KVM_CHECK_EXTENSION, capability[0], capability[1]);
    }
    const vm_fd: i32 = @intCast(try call(fd, c.KVM_CREATE_VM, 0, "KVM_CREATE_VM"));
    defer _ = linux.close(vm_fd);
    _ = try call(vm_fd, c.KVM_CREATE_IRQCHIP, 0, "KVM_CREATE_IRQCHIP");
}
