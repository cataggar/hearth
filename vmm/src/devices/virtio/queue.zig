// Split virtqueue implementation.
// Reads/writes descriptor table, available ring, and used ring in guest memory.

const std = @import("std");
const Memory = @import("../../memory.zig");
const virtio = @import("../virtio.zig");

const log = std.log.scoped(.virtqueue);

const Self = @This();

/// Maximum queue size (must be power of 2).
pub const MAX_QUEUE_SIZE: u16 = 256;
comptime {
    std.debug.assert(@popCount(MAX_QUEUE_SIZE) == 1);
}

// Queue configuration (set during device init)
size: u16 = 0,
ready: bool = false,

// Guest physical addresses of the three regions
desc_addr: u64 = 0,
avail_addr: u64 = 0,
used_addr: u64 = 0,

// Device-side tracking (host-authoritative, not read from guest memory)
last_avail_idx: u16 = 0,
next_used_idx: u16 = 0,
generation: u64 = 0,

pub fn reset(self: *Self) void {
    self.* = .{ .generation = self.generation +% 1 };
}

fn reject(self: *Self) void {
    self.ready = false;
    self.generation +%= 1;
}

pub fn isReady(self: Self) bool {
    return self.ready and self.size > 0 and self.size <= MAX_QUEUE_SIZE and @popCount(self.size) == 1 and
        self.desc_addr != 0 and self.avail_addr != 0 and self.used_addr != 0 and
        self.desc_addr % 16 == 0 and self.avail_addr % 2 == 0 and self.used_addr % 4 == 0;
}

pub fn validate(self: Self, mem: *Memory) bool {
    if (!self.isReady()) return false;
    _ = mem.slice(@intCast(self.desc_addr), @as(usize, self.size) * 16) catch return false;
    _ = mem.slice(@intCast(self.avail_addr), 6 + @as(usize, self.size) * 2) catch return false;
    _ = mem.slice(@intCast(self.used_addr), 6 + @as(usize, self.size) * 8) catch return false;
    const desc_end = self.desc_addr + @as(u64, self.size) * 16;
    const avail_end = self.avail_addr + 6 + @as(u64, self.size) * 2;
    const used_end = self.used_addr + 6 + @as(u64, self.size) * 8;
    if (self.desc_addr < avail_end and self.avail_addr < desc_end) return false;
    if (self.desc_addr < used_end and self.used_addr < desc_end) return false;
    if (self.avail_addr < used_end and self.used_addr < avail_end) return false;
    return true;
}

/// Descriptor table entry (16 bytes).
pub const Desc = packed struct {
    addr: u64,
    len: u32,
    flags: u16,
    next: u16,
};

/// Read a descriptor from guest memory.
pub fn getDesc(self: Self, mem: *Memory, index: u16) !Desc {
    if (index >= self.size) return error.InvalidDescIndex;
    const offset: usize = @intCast(try std.math.add(u64, self.desc_addr, @as(u64, index) * 16));
    const bytes = try mem.slice(offset, 16);
    return .{
        .addr = std.mem.readInt(u64, bytes[0..8], .little),
        .len = std.mem.readInt(u32, bytes[8..12], .little),
        .flags = std.mem.readInt(u16, bytes[12..14], .little),
        .next = std.mem.readInt(u16, bytes[14..16], .little),
    };
}

/// Read the current avail.idx (free-running u16).
fn getAvailIdx(self: Self, mem: *Memory) !u16 {
    const offset: usize = @intCast(try std.math.add(u64, self.avail_addr, 2));
    const bytes = try mem.slice(offset, 2);
    if (offset % 2 != 0) return error.InvalidRingAlignment;
    const index: *const u16 = @ptrCast(@alignCast(bytes.ptr));
    return std.mem.littleToNative(u16, @atomicLoad(u16, index, .acquire));
}

pub fn hasAvail(self: Self, mem: *Memory) bool {
    if (!self.isReady()) return false;
    const available = self.getAvailIdx(mem) catch return false;
    const count = available -% self.last_avail_idx;
    if (count == 0 or count > self.size) return false;
    const head = self.getAvailRing(mem, self.last_avail_idx) catch return false;
    return head < self.size;
}

/// Read an entry from the available ring.
fn getAvailRing(self: Self, mem: *Memory, ring_idx: u16) !u16 {
    const pos = ring_idx % self.size;
    const offset: usize = @intCast(try std.math.add(u64, self.avail_addr, 4 + @as(u64, pos) * 2));
    const bytes = try mem.slice(offset, 2);
    return std.mem.readInt(u16, bytes[0..2], .little);
}

/// Write an entry to the used ring and advance used.idx.
/// Tracks used_idx on the host side to prevent guest TOCTOU attacks.
pub fn pushUsed(self: *Self, mem: *Memory, desc_head: u16, len: u32) !void {
    if (!self.isReady()) return error.InvalidQueue;
    const idx_bytes = try mem.slice(@intCast(try std.math.add(u64, self.used_addr, 2)), 2);
    const index: *u16 = @ptrCast(@alignCast(idx_bytes.ptr));
    const pos = self.next_used_idx % self.size;

    // Write used element (id + len) at ring[pos]
    const elem_offset: usize = @intCast(try std.math.add(u64, self.used_addr, 4 + @as(u64, pos) * 8));
    const elem_bytes = try mem.slice(elem_offset, 8);
    std.mem.writeInt(u32, elem_bytes[0..4], desc_head, .little);
    std.mem.writeInt(u32, elem_bytes[4..8], len, .little);

    // Increment host-tracked used.idx and write to guest memory
    self.next_used_idx +%= 1;
    @atomicStore(u16, index, std.mem.nativeToLittle(u16, self.next_used_idx), .release);
}

// --- Snapshot support ---
// Queue state is entirely in these struct fields — the actual descriptor/ring
// data lives in guest memory and is saved/restored with the memory file.
// We only need to persist our host-side tracking indices.
pub const SNAPSHOT_SIZE = 31; // 2+1+8+8+8+2+2

pub fn snapshotSave(self: *const Self) [SNAPSHOT_SIZE]u8 {
    var buf: [SNAPSHOT_SIZE]u8 = undefined;
    std.mem.writeInt(u16, buf[0..2], self.size, .little);
    buf[2] = @intFromBool(self.ready);
    std.mem.writeInt(u64, buf[3..11], self.desc_addr, .little);
    std.mem.writeInt(u64, buf[11..19], self.avail_addr, .little);
    std.mem.writeInt(u64, buf[19..27], self.used_addr, .little);
    std.mem.writeInt(u16, buf[27..29], self.last_avail_idx, .little);
    std.mem.writeInt(u16, buf[29..31], self.next_used_idx, .little);
    return buf;
}

pub fn snapshotRestore(self: *Self, buf: [SNAPSHOT_SIZE]u8) void {
    self.generation +%= 1;
    const size = std.mem.readInt(u16, buf[0..2], .little);
    // Validate queue size: must be 0, or a power-of-2 <= MAX_QUEUE_SIZE.
    // Invalid sizes would cause division-by-zero in ring index modular arithmetic.
    if (size != 0 and (size > MAX_QUEUE_SIZE or @popCount(size) != 1)) {
        log.warn("snapshot: invalid queue size {}, resetting to 0", .{size});
        self.reset();
        return;
    }
    self.size = size;
    self.ready = buf[2] != 0;
    self.desc_addr = std.mem.readInt(u64, buf[3..11], .little);
    self.avail_addr = std.mem.readInt(u64, buf[11..19], .little);
    self.used_addr = std.mem.readInt(u64, buf[19..27], .little);
    self.last_avail_idx = std.mem.readInt(u16, buf[27..29], .little);
    self.next_used_idx = std.mem.readInt(u16, buf[29..31], .little);
}

/// Walk a descriptor chain starting at `head`, collecting up to `max` descriptors.
/// Returns the number of descriptors collected. Detects cycles via a visited bitset.
pub fn collectChain(self: Self, mem: *Memory, head: u16, descs: []Desc) !usize {
    if (self.size > MAX_QUEUE_SIZE) return error.InvalidQueue;
    var visited: [MAX_QUEUE_SIZE / 8]u8 = @splat(0);
    var count: usize = 0;
    var idx = head;

    while (true) {
        if (count >= descs.len) return error.DescChainTooLong;
        if (idx >= self.size) return error.InvalidDescIndex;

        // Cycle detection
        const byte = idx / 8;
        const bit: u3 = @intCast(idx % 8);
        if (visited[byte] & (@as(u8, 1) << bit) != 0) return error.DescChainCycle;
        visited[byte] |= @as(u8, 1) << bit;

        descs[count] = try self.getDesc(mem, idx);
        count += 1;
        if (descs[count - 1].flags & virtio.DESC_F_NEXT != 0) {
            idx = descs[count - 1].next;
        } else {
            break;
        }
    }
    return count;
}

/// Pop the next available descriptor chain head. Returns null if none available.
pub fn popAvail(self: *Self, mem: *Memory) !?u16 {
    if (!self.isReady()) return error.InvalidQueue;
    const avail_idx = self.getAvailIdx(mem) catch |err| {
        self.reject();
        return err;
    };
    if (avail_idx == self.last_avail_idx) return null;
    if (avail_idx -% self.last_avail_idx > self.size) {
        self.reject();
        return error.QueueOverrun;
    }

    const head = self.getAvailRing(mem, self.last_avail_idx) catch |err| {
        self.reject();
        return err;
    };
    if (head >= self.size) {
        self.reject();
        return error.InvalidDescIndex;
    }
    self.last_avail_idx +%= 1;
    return head;
}
