const std = @import("std");
const linux = std.os.linux;
const Memory = @import("../../memory.zig");
const Queue = @import("queue.zig");
const Shadow = @import("net_shadow.zig");

const Self = @This();
const log = std.log.scoped(.vhost_net);
const VERSION_1: u64 = 1 << 32;
const VringState = extern struct { index: u32, num: u32 };
const VringFile = extern struct { index: u32, fd: i32 };
const VringAddr = extern struct {
    index: u32,
    flags: u32 = 0,
    desc: u64,
    used: u64,
    avail: u64,
    log: u64 = 0,
};
const MemoryTable = extern struct {
    regions: u32 = 1,
    padding: u32 = 0,
    gpa: u64 = 0,
    size: u64,
    hva: u64,
    flags: u64 = 0,
};

fd: i32 = -1,
rings: [2]?Shadow = .{ null, null },
kick: [2]i32 = .{ -1, -1 },
call: [2]i32 = .{ -1, -1 },
err: [2]i32 = .{ -1, -1 },
fatal: bool = false,

fn code(direction: u32, number: u32, size: u32) u32 {
    return (direction << 30) | (size << 16) | (0xaf << 8) | number;
}

fn ioctl(fd: i32, request: u32, pointer: usize, operation: []const u8) !void {
    const rc: isize = @bitCast(linux.ioctl(fd, request, pointer));
    if (rc < 0) {
        log.err("operation={s} errno={}", .{ operation, -rc });
        return switch (-rc) {
            @backingInt(linux.E.NOTTY), @backingInt(linux.E.OPNOTSUPP), @backingInt(linux.E.NOSYS) => error.VhostUapiUnsupported,
            else => error.VhostIoctlFailed,
        };
    }
}

pub fn eventfd() !i32 {
    const rc: isize = @bitCast(linux.eventfd(0, linux.EFD.CLOEXEC | linux.EFD.NONBLOCK));
    if (rc < 0) {
        log.err("operation=eventfd2 errno={}", .{-rc});
        return error.NetEventfdFailed;
    }
    return @intCast(rc);
}

pub fn signal(fd: i32) !void {
    while (true) {
        var value: u64 = 1;
        const rc: isize = @bitCast(linux.write(fd, std.mem.asBytes(&value).ptr, 8));
        if (rc == 8 or rc == -@as(isize, @backingInt(linux.E.AGAIN))) return;
        if (rc == -@as(isize, @backingInt(linux.E.INTR))) continue;
        return error.NetEventfdWriteFailed;
    }
}

pub fn drainEvent(fd: i32) !bool {
    var any = false;
    while (true) {
        var value: u64 = 0;
        const rc: isize = @bitCast(linux.read(fd, std.mem.asBytes(&value).ptr, 8));
        if (rc == 8) {
            any = true;
        } else if (rc == -@as(isize, @backingInt(linux.E.AGAIN))) {
            return any;
        } else if (rc == -@as(isize, @backingInt(linux.E.INTR))) {
            continue;
        } else {
            return error.NetEventfdReadFailed;
        }
    }
}

pub fn init(tap: i32, mem: *Memory, queues: []Queue) !Self {
    for (queues[0..2]) |*queue| try Shadow.validateQueue(mem, queue);
    var self: Self = .{};
    errdefer self.deinit();
    const rc: isize = @bitCast(linux.open("/dev/vhost-net", .{ .ACCMODE = .RDWR, .CLOEXEC = true }, 0));
    if (rc < 0) {
        log.err("operation=open errno={}", .{-rc});
        return switch (-rc) {
            @backingInt(linux.E.NOENT), @backingInt(linux.E.NODEV) => error.VhostUnavailable,
            @backingInt(linux.E.ACCES), @backingInt(linux.E.PERM) => error.VhostAccessDenied,
            else => error.VhostOpenFailed,
        };
    }
    self.fd = @intCast(rc);
    var features: u64 = 0;
    try ioctl(self.fd, code(2, 0, 8), @intFromPtr(&features), "GET_FEATURES");
    if (features & VERSION_1 == 0) return error.VhostVersion1Unsupported;
    var owner_mode: u8 = 1;
    try ioctl(self.fd, code(1, 0x84, 1), @intFromPtr(&owner_mode), "SET_FORK_FROM_OWNER");
    try ioctl(self.fd, code(2, 0x85, 1), @intFromPtr(&owner_mode), "GET_FORK_FROM_OWNER");
    if (owner_mode != 1) return error.VhostWorkerIsolationUnsupported;
    try ioctl(self.fd, code(0, 1, 0), 0, "SET_OWNER");
    // Existing VNET_HDR TAP owns the 12-byte header; no private kernel header bit.
    features = VERSION_1;
    try ioctl(self.fd, code(1, 0, 8), @intFromPtr(&features), "SET_FEATURES");
    var table: MemoryTable = .{ .size = mem.size(), .hva = @intFromPtr(mem.mem.ptr) };
    try ioctl(self.fd, code(1, 3, 8), @intFromPtr(&table), "SET_MEM_TABLE");
    for (0..2) |index| {
        self.rings[index] = try Shadow.init();
        const ring = &self.rings[index].?;
        var state: VringState = .{ .index = @intCast(index), .num = queues[index].size };
        try ioctl(self.fd, code(1, 0x10, 8), @intFromPtr(&state), "SET_VRING_NUM");
        var address: VringAddr = .{
            .index = @intCast(index),
            .desc = @intFromPtr(ring.mapping.ptr),
            .used = @intFromPtr(ring.mapping.ptr) + Shadow.USED_OFFSET,
            .avail = @intFromPtr(ring.mapping.ptr) + Shadow.AVAIL_OFFSET,
        };
        try ioctl(self.fd, code(1, 0x11, 40), @intFromPtr(&address), "SET_VRING_ADDR");
        state.num = 0;
        try ioctl(self.fd, code(1, 0x12, 8), @intFromPtr(&state), "SET_VRING_BASE");
        self.kick[index] = try eventfd();
        self.call[index] = try eventfd();
        self.err[index] = try eventfd();
        for ([_]u32{ 0x20, 0x21, 0x22 }, [_]i32{ self.kick[index], self.call[index], self.err[index] }) |number, event| {
            var file: VringFile = .{ .index = @intCast(index), .fd = event };
            try ioctl(self.fd, code(1, number, 8), @intFromPtr(&file), "SET_VRING_EVENT");
        }
    }
    // Both queues are fully validated before either has published descriptors.
    for (0..2) |index| {
        var file: VringFile = .{ .index = @intCast(index), .fd = tap };
        try ioctl(self.fd, code(1, 0x30, 8), @intFromPtr(&file), "SET_BACKEND");
    }
    log.info("effective=vhost features=VERSION_1 header=socket:12 queues=private-split worker=owner", .{});
    return self;
}

fn checkErrors(self: *Self) !void {
    for (self.err) |fd| {
        if (try drainEvent(fd)) self.fatal = true;
    }
    if (self.fatal) return error.VhostQueueFatal;
}

pub fn complete(self: *Self, mem: *Memory, queues: []Queue) !bool {
    try self.checkErrors();
    var did_work = false;
    for (0..2) |index| {
        _ = try drainEvent(self.call[index]);
        did_work = (try self.rings[index].?.drain(mem, &queues[index], index == 0)) or did_work;
    }
    return did_work;
}

pub fn submit(self: *Self, mem: *Memory, queues: []Queue) !void {
    try self.checkErrors();
    for (0..2) |index| {
        const ring = &self.rings[index].?;
        const queue = &queues[index];
        var added = false;
        while (ring.submitted -% ring.completed < queue.size and try Shadow.available(mem, queue) > 0) {
            const chain = try Shadow.collect(mem, queue, index == 0);
            try ring.publish(queue, chain);
            added = true;
        }
        if (added) try signal(self.kick[index]);
    }
}

pub fn quiesce(self: *Self, mem: *Memory, queues: []Queue) !bool {
    // Caller has stopped guest execution and joined the common dispatcher.
    for (0..2) |index| {
        var file: VringFile = .{ .index = @intCast(index), .fd = -1 };
        try ioctl(self.fd, code(1, 0x20, 8), @intFromPtr(&file), "UNBIND_KICK");
        try ioctl(self.fd, code(1, 0x30, 8), @intFromPtr(&file), "DETACH_BACKEND");
    }
    const did_work = try self.complete(mem, queues);
    for (0..2) |index| {
        var state: VringState = .{ .index = @intCast(index), .num = 0 };
        try ioctl(self.fd, code(3, 0x12, 8), @intFromPtr(&state), "GET_VRING_BASE");
        if (state.num > std.math.maxInt(u16)) return error.InvalidNetShadowAvailableIndex;
        try self.rings[index].?.rollbackPending(&queues[index], @intCast(state.num));
    }
    try self.checkErrors();
    return did_work;
}

pub fn deinit(self: *Self) void {
    // release() synchronously stops/flushes/joins before any mapping is unmapped.
    if (self.fd >= 0) _ = linux.close(self.fd);
    self.fd = -1;
    for (0..2) |index| {
        for ([_]i32{ self.kick[index], self.call[index], self.err[index] }) |fd| {
            if (fd >= 0) _ = linux.close(fd);
        }
        self.kick[index] = -1;
        self.call[index] = -1;
        self.err[index] = -1;
        if (self.rings[index]) |*ring| ring.deinit();
        self.rings[index] = null;
    }
}
