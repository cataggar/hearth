const std = @import("std");
const Memory = @import("../../memory.zig");
const Queue = @import("queue.zig");

const Self = @This();
pub const RING_BYTES = 3 * 4096;
pub const DESC_OFFSET = 0;
pub const AVAIL_OFFSET = 4096;
pub const USED_OFFSET = 8192;
const MAX_CHAIN = 16;

pub const Chain = struct {
    head: u16,
    count: usize,
    indices: [MAX_CHAIN]u16,
    descs: [MAX_CHAIN]Queue.Desc,
    bytes: u32,
};

mapping: []align(std.heap.page_size_min) u8,
submitted: u16 = 0,
completed: u16 = 0,
owned: [32]u8 = @splat(0),
chains: [256]?Chain = @splat(null),

pub fn init() !Self {
    const mapping = try std.posix.mmap(null, RING_BYTES, .{ .READ = true, .WRITE = true }, .{
        .TYPE = .PRIVATE,
        .ANONYMOUS = true,
    }, -1, 0);
    @memset(mapping, 0);
    return .{ .mapping = mapping };
}

pub fn deinit(self: *Self) void {
    std.posix.munmap(self.mapping);
}

pub fn validateQueue(mem: *Memory, queue: *const Queue) !void {
    if (!queue.isReady() or queue.size > 256 or @popCount(queue.size) != 1)
        return error.InvalidNetQueue;
    if (queue.desc_addr % 16 != 0 or queue.avail_addr % 2 != 0 or queue.used_addr % 4 != 0)
        return error.InvalidNetQueueAlignment;
    _ = try mem.slice(@intCast(queue.desc_addr), @as(usize, queue.size) * 16);
    _ = try mem.slice(@intCast(queue.avail_addr), 4 + @as(usize, queue.size) * 2);
    _ = try mem.slice(@intCast(queue.used_addr), 4 + @as(usize, queue.size) * 8);
}

pub fn available(mem: *Memory, queue: *const Queue) !u16 {
    const bytes = try mem.slice(@intCast(queue.avail_addr + 2), 2);
    const pointer: *const u16 = @ptrCast(@alignCast(bytes.ptr));
    const index = @atomicLoad(u16, pointer, .acquire);
    const pending = index -% queue.last_avail_idx;
    if (pending > queue.size) return error.InvalidNetAvailableIndex;
    return pending;
}

pub fn collect(mem: *Memory, queue: *const Queue, rx: bool) !Chain {
    if (try available(mem, queue) == 0) return error.NoNetDescriptor;
    const slot = queue.last_avail_idx % queue.size;
    const entry = try mem.slice(@intCast(queue.avail_addr + 4 + @as(u64, slot) * 2), 2);
    const head = std.mem.readInt(u16, entry[0..2], .little);
    var chain: Chain = .{
        .head = head,
        .count = 0,
        .indices = undefined,
        .descs = undefined,
        .bytes = 0,
    };
    var visited: [32]u8 = @splat(0);
    var index = head;
    while (true) {
        if (index >= queue.size) return error.InvalidDescIndex;
        if (chain.count == MAX_CHAIN) return error.DescChainTooLong;
        const mask = @as(u8, 1) << @as(u3, @truncate(index));
        if (visited[index / 8] & mask != 0) return error.DescChainCycle;
        visited[index / 8] |= mask;
        const desc = try queue.getDesc(mem, index);
        if (desc.flags & ~@as(u16, 3) != 0) return error.UnadvertisedNetDescriptorFlags;
        if ((desc.flags & 2 != 0) != rx) return error.InvalidNetDescriptorDirection;
        _ = try mem.slice(@intCast(desc.addr), desc.len);
        chain.bytes = std.math.add(u32, chain.bytes, desc.len) catch return error.NetBufferLengthOverflow;
        chain.indices[chain.count] = index;
        chain.descs[chain.count] = desc;
        chain.count += 1;
        if (desc.flags & 1 == 0) break;
        index = desc.next;
    }
    if (chain.bytes < 12) return error.NetBufferMissingHeader;
    return chain;
}

pub fn publish(self: *Self, queue: *Queue, chain: Chain) !void {
    if (self.submitted -% self.completed >= queue.size) return error.NetShadowFull;
    for (chain.indices[0..chain.count]) |index| {
        const mask = @as(u8, 1) << @as(u3, @truncate(index));
        if (self.owned[index / 8] & mask != 0) return error.NetDescriptorAlreadyOwned;
    }
    for (chain.descs[0..chain.count], chain.indices[0..chain.count]) |desc, index| {
        self.owned[index / 8] |= @as(u8, 1) << @as(u3, @truncate(index));
        const bytes = self.mapping[@as(usize, index) * 16 ..][0..16];
        std.mem.writeInt(u64, bytes[0..8], desc.addr, .little);
        std.mem.writeInt(u32, bytes[8..12], desc.len, .little);
        std.mem.writeInt(u16, bytes[12..14], desc.flags, .little);
        std.mem.writeInt(u16, bytes[14..16], desc.next, .little);
    }
    self.chains[chain.head] = chain;
    const slot = self.submitted % queue.size;
    std.mem.writeInt(u16, self.mapping[AVAIL_OFFSET + 4 + @as(usize, slot) * 2 ..][0..2], chain.head, .little);
    self.submitted +%= 1;
    queue.last_avail_idx +%= 1;
    const pointer: *u16 = @ptrCast(@alignCast(&self.mapping[AVAIL_OFFSET + 2]));
    @atomicStore(u16, pointer, self.submitted, .release);
}

pub fn usedIndex(self: *const Self) u16 {
    const pointer: *const u16 = @ptrCast(@alignCast(&self.mapping[USED_OFFSET + 2]));
    return @atomicLoad(u16, pointer, .acquire);
}

pub fn pushGuestUsed(mem: *Memory, queue: *Queue, head: u16, length: u32) !void {
    const slot = queue.next_used_idx % queue.size;
    const entry = try mem.slice(@intCast(queue.used_addr + 4 + @as(u64, slot) * 8), 8);
    const index = try mem.slice(@intCast(queue.used_addr + 2), 2);
    std.mem.writeInt(u32, entry[0..4], head, .little);
    std.mem.writeInt(u32, entry[4..8], length, .little);
    queue.next_used_idx +%= 1;
    const pointer: *u16 = @ptrCast(@alignCast(index.ptr));
    @atomicStore(u16, pointer, queue.next_used_idx, .release);
}

pub fn drain(self: *Self, mem: *Memory, queue: *Queue, rx: bool) !bool {
    const used = self.usedIndex();
    if (used -% self.completed > self.submitted -% self.completed)
        return error.InvalidNetShadowUsedIndex;
    var did_work = false;
    while (self.completed != used) {
        const slot = self.completed % queue.size;
        const bytes = self.mapping[USED_OFFSET + 4 + @as(usize, slot) * 8 ..][0..8];
        const head = std.mem.readInt(u32, bytes[0..4], .little);
        const length = std.mem.readInt(u32, bytes[4..8], .little);
        if (head >= queue.size) return error.InvalidNetShadowHead;
        const chain = self.chains[head] orelse return error.InvalidNetShadowHead;
        if ((rx and (length < 12 or length > chain.bytes)) or (!rx and length != 0))
            return error.InvalidNetShadowLength;
        for (chain.indices[0..chain.count]) |index| {
            self.owned[index / 8] &= ~(@as(u8, 1) << @as(u3, @truncate(index)));
        }
        self.chains[head] = null;
        self.completed +%= 1;
        try pushGuestUsed(mem, queue, @intCast(head), length);
        did_work = true;
    }
    return did_work;
}

pub fn rollbackPending(self: *Self, queue: *Queue, consumed: u16) !void {
    // Called only after kernel detach/flush and completion mirroring.
    if (consumed != self.completed) return error.NetConsumedWithoutCompletion;
    const pending = self.submitted -% consumed;
    if (pending > queue.size) return error.InvalidNetShadowAvailableIndex;
    queue.last_avail_idx -%= pending;
}

test "private descriptor copy rejects unadvertised flags and guest mutation cannot alter it" {
    var mem = try Memory.init(65536);
    defer mem.deinit();
    var queue: Queue = .{ .ready = true, .size = 8, .desc_addr = 4096, .avail_addr = 8192, .used_addr = 12288 };
    try validateQueue(&mem, &queue);
    const desc = try mem.slice(4096, 16);
    std.mem.writeInt(u64, desc[0..8], 16384, .little);
    std.mem.writeInt(u32, desc[8..12], 64, .little);
    std.mem.writeInt(u16, desc[12..14], 4, .little);
    try mem.write(8194, &.{ 1, 0 });
    try std.testing.expectError(error.UnadvertisedNetDescriptorFlags, collect(&mem, &queue, false));
    std.mem.writeInt(u16, desc[12..14], 0, .little);
    const chain = try collect(&mem, &queue, false);
    var ring = try init();
    defer ring.deinit();
    try ring.publish(&queue, chain);
    std.mem.writeInt(u64, desc[0..8], 0xffffffffffffffff, .little);
    try std.testing.expectEqual(@as(u64, 16384), std.mem.readInt(u64, ring.mapping[0..8], .little));
}

test "private completion mirroring and pending rollback preserve format-v2 cursors" {
    var mem = try Memory.init(65536);
    defer mem.deinit();
    var queue: Queue = .{ .ready = true, .size = 8, .desc_addr = 4096, .avail_addr = 8192, .used_addr = 12288, .last_avail_idx = 65535, .next_used_idx = 65535 };
    var ring = try init();
    defer ring.deinit();
    var chain: Chain = .{ .head = 0, .count = 1, .indices = undefined, .descs = undefined, .bytes = 64 };
    chain.indices[0] = 0;
    chain.descs[0] = .{ .addr = 16384, .len = 64, .flags = 0, .next = 0 };
    try ring.publish(&queue, chain);
    try std.testing.expectError(error.NetDescriptorAlreadyOwned, ring.publish(&queue, chain));
    std.mem.writeInt(u16, ring.mapping[USED_OFFSET + 2 ..][0..2], 1, .little);
    try std.testing.expectError(error.InvalidNetShadowLength, ring.drain(&mem, &queue, true));
    try std.testing.expectEqual(@as(u16, 65535), queue.next_used_idx);
    try std.testing.expect(try ring.drain(&mem, &queue, false));
    try std.testing.expectEqual(@as(u16, 0), queue.next_used_idx);
    try ring.publish(&queue, chain);
    try ring.rollbackPending(&queue, 1);
    try std.testing.expectEqual(@as(u16, 0), queue.last_avail_idx);
    try std.testing.expectError(error.NetConsumedWithoutCompletion, ring.rollbackPending(&queue, 2));
}
