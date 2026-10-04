const std = @import("std");
const linux = std.os.linux;

const Self = @This();
pub const CHUNK_SIZE = 64 * 1024;
const IDLE = 0;
const WORK = 1;
const READY = 2;
const STOP = 3;

pub const Kind = enum { read, write, flush };
pub const Ops = struct {
    context: ?*anyopaque = null,
    read: *const fn (?*anyopaque, i32, []u8, u64) isize = readFile,
    write: *const fn (?*anyopaque, i32, []const u8, u64) isize = writeFile,
    flush: *const fn (?*anyopaque, i32) isize = flushFile,
};
pub const Wake = struct {
    immediate_exit: *volatile u8,
    tid: i32,

    pub fn notify(self: Wake) void {
        @atomicStore(u8, self.immediate_exit, 1, .seq_cst);
        if (self.tid != 0) _ = linux.tkill(self.tid, linux.SIG.USR1);
    }
};
pub const Result = struct {
    failed: bool = false,
    short_read: bool = false,
};

fd: i32,
ops: Ops,
allocator: std.mem.Allocator,
thread: std.Thread = undefined,
state: std.atomic.Value(u32) = .init(IDLE),
started: std.atomic.Value(u32) = .init(0),
tid: i32 = 0,
notification: std.atomic.Value(u32) = .init(0),
wake: ?Wake = null,
buffer: [CHUNK_SIZE]u8 = undefined,
kind: Kind = .flush,
length: usize = 0,
offset: u64 = 0,
result: Result = .{},

pub fn create(fd: i32, ops: Ops) !*Self {
    return createWithAllocator(fd, ops, std.heap.page_allocator);
}

pub fn createWithAllocator(fd: i32, ops: Ops, allocator: std.mem.Allocator) !*Self {
    const self = try allocator.create(Self);
    errdefer allocator.destroy(self);
    self.* = .{ .fd = fd, .ops = ops, .allocator = allocator };
    self.thread = try std.Thread.spawn(.{}, run, .{self});
    while (self.started.load(.acquire) == 0) waitState(&self.started, 0);
    return self;
}

pub fn destroy(self: *Self) void {
    self.waitReady();
    self.state.store(STOP, .seq_cst);
    wakeState(&self.state);
    self.thread.join();
    self.allocator.destroy(self);
}

pub fn submit(self: *Self, kind: Kind, length: usize, offset: u64) void {
    std.debug.assert(self.state.load(.seq_cst) == IDLE);
    std.debug.assert(length <= CHUNK_SIZE);
    self.kind = kind;
    self.length = length;
    self.offset = offset;
    self.state.store(WORK, .seq_cst);
    wakeState(&self.state);
}

pub fn ready(self: *Self) bool {
    return self.state.load(.seq_cst) == READY;
}

pub fn waitReady(self: *Self) void {
    while (self.state.load(.seq_cst) == WORK) waitState(&self.state, WORK);
}

pub fn consume(self: *Self) void {
    std.debug.assert(self.ready());
    self.state.store(IDLE, .seq_cst);
    wakeState(&self.state);
}

pub fn clearBeforeEntry(immediate_exit: *volatile u8) void {
    @atomicStore(u8, immediate_exit, 0, .seq_cst);
}

pub fn waitState(value: *std.atomic.Value(u32), expected: u32) void {
    _ = linux.syscall6(.futex, @intFromPtr(&value.raw), 128, expected, 0, 0, 0);
}

pub fn wakeState(value: *std.atomic.Value(u32)) void {
    _ = linux.syscall6(.futex, @intFromPtr(&value.raw), 129, 1, 0, 0, 0);
}

fn run(self: *Self) void {
    self.tid = @intCast(linux.gettid());
    self.started.store(1, .release);
    wakeState(&self.started);
    while (true) {
        const state = self.state.load(.seq_cst);
        switch (state) {
            STOP => return,
            WORK => {
                self.result = .{};
                switch (self.kind) {
                    .read => {
                        const rc = self.ops.read(self.ops.context, self.fd, self.buffer[0..self.length], self.offset);
                        if (rc < 0 or @as(usize, @intCast(rc)) > self.length) {
                            self.result.failed = true;
                        } else {
                            const count: usize = @intCast(rc);
                            self.result.short_read = count < self.length;
                            @memset(self.buffer[count..self.length], 0);
                        }
                    },
                    .write => {
                        var written: usize = 0;
                        while (written < self.length) {
                            const rc = self.ops.write(self.ops.context, self.fd, self.buffer[written..self.length], self.offset + written);
                            if (rc <= 0 or @as(usize, @intCast(rc)) > self.length - written) {
                                self.result.failed = true;
                                break;
                            }
                            written += @intCast(rc);
                        }
                    },
                    .flush => self.result.failed = self.ops.flush(self.ops.context, self.fd) < 0,
                }
                // READY, immediate_exit and the owner's clear/check are one
                // sequentially consistent order. A pre-entry signal alone is insufficient.
                self.state.store(READY, .seq_cst);
                wakeState(&self.state);
                if (self.wake) |wake| wake.notify();
                if (@import("builtin").is_test) {
                    _ = self.notification.fetchAdd(1, .seq_cst);
                    wakeState(&self.notification);
                }
            },
            else => waitState(&self.state, state),
        }
    }
}

fn readFile(_: ?*anyopaque, fd: i32, bytes: []u8, offset: u64) isize {
    return @bitCast(linux.pread(fd, bytes.ptr, bytes.len, @bitCast(offset)));
}

fn writeFile(_: ?*anyopaque, fd: i32, bytes: []const u8, offset: u64) isize {
    return @bitCast(linux.pwrite(fd, bytes.ptr, bytes.len, @bitCast(offset)));
}

fn flushFile(_: ?*anyopaque, fd: i32) isize {
    return @bitCast(linux.fdatasync(fd));
}
