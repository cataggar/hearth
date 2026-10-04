const std = @import("std");
const linux = std.os.linux;
const probe = @import("eventfd_guest_probe.zig");

const SockaddrIn = extern struct {
    family: u16 = 2,
    port: u16 = std.mem.nativeToBig(u16, 11000),
    address: [4]u8 = .{ 192, 0, 2, 2 },
    padding: [8]u8 = @splat(0),
};

pub fn main() !void {
    comptime std.debug.assert(@sizeOf(SockaddrIn) == 16);
    const opened: isize = @bitCast(linux.socket(2, linux.SOCK.STREAM | linux.SOCK.CLOEXEC, 0));
    if (opened < 0) return error.SocketFailed;
    const listener: i32 = @intCast(opened);
    defer _ = linux.close(listener);
    var reuse: c_int = 1;
    const option: isize = @bitCast(linux.setsockopt(listener, 1, 2, std.mem.asBytes(&reuse).ptr, @sizeOf(c_int)));
    if (option < 0) return error.ReuseAddressFailed;
    const address: SockaddrIn = .{};
    const bound: isize = @bitCast(linux.bind(listener, @ptrCast(&address), @sizeOf(SockaddrIn)));
    if (bound < 0) return error.BindFailed;
    const listening: isize = @bitCast(linux.listen(listener, 1));
    if (listening < 0) return error.ListenFailed;
    std.debug.print("eventfd-tcp-probe: listening\n", .{});
    const accepted: isize = @bitCast(linux.accept4(listener, null, null, linux.SOCK.CLOEXEC));
    if (accepted < 0) return error.AcceptFailed;
    const connection: i32 = @intCast(accepted);
    defer _ = linux.close(connection);
    std.debug.print("eventfd-tcp-probe: connected\n", .{});
    try probe.echo(connection);
}
