const std = @import("std");
const linux = std.os.linux;

const SockaddrVm = extern struct {
    family: u16 = 40,
    reserved: u16 = 0,
    port: u32 = 11000,
    cid: u32 = 2,
    flags: u8 = 0,
    zero: [3]u8 = @splat(0),
};

fn transfer(fd: i32, bytes: []u8, writing: bool) !void {
    var offset: usize = 0;
    while (offset < bytes.len) {
        const rc: isize = @bitCast(if (writing)
            linux.write(fd, bytes[offset..].ptr, bytes.len - offset)
        else
            linux.read(fd, bytes[offset..].ptr, bytes.len - offset));
        if (rc == -@as(isize, @backingInt(linux.E.INTR))) continue;
        if (rc <= 0) return error.TransferFailed;
        offset += @intCast(rc);
    }
}

pub fn main() !void {
    comptime {
        std.debug.assert(@sizeOf(SockaddrVm) == 16);
    }
    const opened: isize = @bitCast(linux.socket(40, linux.SOCK.STREAM | linux.SOCK.CLOEXEC, 0));
    if (opened < 0) return error.SocketFailed;
    const fd: i32 = @intCast(opened);
    defer _ = linux.close(fd);
    const addr: SockaddrVm = .{};
    const connected: isize = @bitCast(linux.connect(fd, @ptrCast(&addr), @sizeOf(SockaddrVm)));
    if (connected < 0) return error.ConnectFailed;
    var marker = "eventfd-native-probe: connected\n".*;
    try transfer(1, &marker, true);
    try echo(fd);
}

pub fn echo(fd: i32) !void {
    var payload: [65536]u8 = undefined;
    while (true) {
        var header: [4]u8 = undefined;
        try transfer(fd, &header, false);
        const size = std.mem.readInt(u32, &header, .little);
        if (size < 8 or size > payload.len) return error.InvalidPayload;
        try transfer(fd, payload[0..size], false);
        var checksum: u64 = 0xcbf29ce484222325;
        for (payload[0..size]) |byte| checksum = (checksum ^ byte) *% 0x100000001b3;
        std.mem.writeInt(u32, &header, size + 8, .little);
        var check_bytes: [8]u8 = undefined;
        std.mem.writeInt(u64, &check_bytes, checksum, .little);
        try transfer(fd, &header, true);
        try transfer(fd, &check_bytes, true);
        try transfer(fd, payload[0..size], true);
    }
}
