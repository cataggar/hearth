// Virtio block device backend.
// Handles read/write/flush requests against a backing file.

const std = @import("std");
const linux = std.os.linux;
const Memory = @import("../../memory.zig");
const Queue = @import("queue.zig");
const virtio = @import("../virtio.zig");
const Worker = @import("blk_worker.zig");

const log = std.log.scoped(.virtio_blk);

const Self = @This();

// Block request types
pub const T_IN: u32 = 0; // read
pub const T_OUT: u32 = 1; // write
pub const T_FLUSH: u32 = 4;
pub const T_GET_ID: u32 = 8;

// Status values
pub const S_OK: u8 = 0;
pub const S_IOERR: u8 = 1;
pub const S_UNSUPP: u8 = 2;

// Feature bits
pub const F_FLUSH: u64 = 1 << 9;

const SECTOR_SIZE: u64 = 512;
const REQ_HDR_SIZE: u32 = 16; // type: u32, reserved: u32, sector: u64

pub const Backend = enum { sync, worker };

fd: i32,
capacity: u64, // in 512-byte sectors
requested_backend: Backend = .sync,
worker: ?*Worker = null,
pending: ?Pending = null,
generation: u64 = 0,

const Pending = struct {
    descs: [Queue.MAX_QUEUE_SIZE]Queue.Desc,
    count: usize,
    head: u16,
    kind: u32,
    status: u8 = S_OK,
    status_addr: u64,
    used_len: u32 = 1,
    generation: u64,
    queue_state: Queue,
    descriptor: usize = 1,
    descriptor_offset: usize = 0,
    file_offset: u64 = 0,
    chunk_len: usize = 0,
    flush_submitted: bool = false,
};

pub fn init(path: [*:0]const u8) !Self {
    const open_rc: isize = @bitCast(linux.open(path, .{ .ACCMODE = .RDWR, .CLOEXEC = true }, 0));
    if (open_rc < 0) return error.OpenFailed;
    const fd: i32 = @intCast(open_rc);
    errdefer _ = linux.close(fd);

    // Get file size
    var stx: linux.Statx = undefined;
    const stat_rc: isize = @bitCast(linux.statx(fd, "", @as(u32, linux.AT.EMPTY_PATH), .{}, &stx));
    if (stat_rc < 0) return error.StatFailed;

    const file_size: u64 = @intCast(stx.size);
    const capacity = file_size / SECTOR_SIZE;

    log.info("block device: {s}, {} sectors ({} MB)", .{ path, capacity, file_size / (1024 * 1024) });

    return .{ .fd = fd, .capacity = capacity };
}

pub fn deinit(self: *Self) void {
    self.stopWorker();
    _ = linux.close(self.fd);
}

pub fn startWorker(self: *Self, wake: Worker.Wake) void {
    self.startWorkerWithAllocator(wake, std.heap.page_allocator);
}

pub fn startWorkerWithAllocator(self: *Self, wake: Worker.Wake, allocator: std.mem.Allocator) void {
    if (self.requested_backend != .worker) return;
    std.debug.assert(self.pending == null and self.worker == null);
    self.worker = Worker.createWithAllocator(self.fd, .{}, allocator) catch |err| {
        log.warn("requested=worker effective=sync before admission: {}", .{err});
        return;
    };
    self.worker.?.wake = wake;
    log.info("requested=worker effective=worker tid={} requests=1 staging={} bytes", .{ self.worker.?.tid, Worker.CHUNK_SIZE });
}

pub fn stopWorker(self: *Self) void {
    if (self.worker) |worker| {
        worker.destroy();
        self.worker = null;
    }
    self.pending = null;
    self.generation +%= 1;
}

fn sameQueue(a: Queue, b: Queue) bool {
    return a.ready == b.ready and a.size == b.size and a.desc_addr == b.desc_addr and
        a.avail_addr == b.avail_addr and a.used_addr == b.used_addr and
        a.last_avail_idx == b.last_avail_idx and a.next_used_idx == b.next_used_idx;
}

fn validateQueue(mem: *Memory, queue: Queue) !void {
    if (!queue.isReady() or queue.size > Queue.MAX_QUEUE_SIZE or @popCount(queue.size) != 1) return error.InvalidQueue;
    _ = try mem.slice(@intCast(queue.desc_addr), @as(usize, queue.size) * 16);
    _ = try mem.slice(@intCast(queue.avail_addr), 4 + @as(usize, queue.size) * 2);
    _ = try mem.slice(@intCast(queue.used_addr), 4 + @as(usize, queue.size) * 8);
}

fn capture(self: *Self, mem: *Memory, queue: *Queue, head: u16) !Pending {
    var request: Pending = undefined;
    request = .{
        .descs = undefined,
        .count = 0,
        .head = head,
        .kind = 0,
        .status_addr = 0,
        .generation = self.generation,
        .queue_state = queue.*,
    };
    request.count = try queue.collectChain(mem, head, &request.descs);
    if (request.count < 2) return error.MalformedRequest;
    const header = request.descs[0];
    const status = request.descs[request.count - 1];
    if (header.len < REQ_HDR_SIZE or header.flags & virtio.DESC_F_WRITE != 0 or
        status.len < 1 or status.flags & virtio.DESC_F_WRITE == 0) return error.MalformedRequest;
    const bytes = try mem.slice(@intCast(header.addr), header.len);
    request.kind = std.mem.readInt(u32, bytes[0..4], .little);
    const sector = std.mem.readInt(u64, bytes[8..16], .little);
    request.status_addr = status.addr;
    _ = try mem.slice(@intCast(status.addr), status.len);
    var total: u64 = 0;
    for (request.descs[1 .. request.count - 1]) |desc| {
        _ = try mem.slice(@intCast(desc.addr), desc.len);
        total = try std.math.add(u64, total, desc.len);
        if ((request.kind == T_IN and desc.flags & virtio.DESC_F_WRITE == 0) or
            (request.kind == T_OUT and desc.flags & virtio.DESC_F_WRITE != 0))
            request.status = S_IOERR;
    }
    if (request.kind == T_IN or request.kind == T_OUT) {
        request.file_offset = std.math.mul(u64, sector, SECTOR_SIZE) catch value: {
            request.status = S_IOERR;
            break :value 0;
        };
        const end = std.math.add(u64, request.file_offset, total) catch value: {
            request.status = S_IOERR;
            break :value std.math.maxInt(u64);
        };
        if (!self.validateSectorRange(sector, total) or end > std.math.maxInt(i64))
            request.status = S_IOERR;
        if (request.kind == T_IN and request.status == S_OK)
            request.used_len = @intCast(@min(total + 1, std.math.maxInt(u32)));
    } else if (request.kind != T_FLUSH and request.kind != T_GET_ID) {
        request.status = S_UNSUPP;
    }
    return request;
}

fn finish(self: *Self, mem: *Memory, queue: *Queue, publish: bool) !bool {
    const request = &self.pending.?;
    const applicable = publish and request.generation == self.generation and sameQueue(request.queue_state, queue.*);
    if (applicable) {
        const status = try mem.slice(@intCast(request.status_addr), 1);
        status[0] = request.status;
        try queue.pushUsed(mem, request.head, request.used_len);
    }
    self.pending = null;
    return applicable;
}

fn submitNext(self: *Self, mem: *Memory, queue: *Queue, publish: bool) !bool {
    const request = &self.pending.?;
    const worker = self.worker.?;
    if (request.status != S_OK) {
        return self.finish(mem, queue, publish);
    }
    if (request.kind == T_GET_ID) {
        if (request.count >= 3) {
            const desc = request.descs[1];
            const bytes = try mem.slice(@intCast(desc.addr), @min(desc.len, 20));
            const id = "flint-virtio-blk";
            const count = @min(bytes.len, id.len);
            if (publish) {
                @memcpy(bytes[0..count], id[0..count]);
                @memset(bytes[count..], 0);
            }
            request.used_len = @intCast(@min(@as(u64, desc.len) + 1, std.math.maxInt(u32)));
        }
        return self.finish(mem, queue, publish);
    }
    if (request.kind == T_FLUSH) {
        if (!request.flush_submitted) {
            request.flush_submitted = true;
            worker.submit(.flush, 0, 0);
            return false;
        }
        return self.finish(mem, queue, publish);
    }
    while (request.descriptor < request.count - 1) {
        const desc = request.descs[request.descriptor];
        if (request.descriptor_offset == desc.len) {
            request.descriptor += 1;
            request.descriptor_offset = 0;
            continue;
        }
        const length = @min(desc.len - request.descriptor_offset, Worker.CHUNK_SIZE);
        request.chunk_len = length;
        if (request.kind == T_OUT) {
            const bytes = try mem.slice(@intCast(desc.addr + request.descriptor_offset), length);
            @memcpy(worker.buffer[0..length], bytes);
        }
        worker.submit(if (request.kind == T_IN) .read else .write, length, request.file_offset);
        return false;
    }
    return self.finish(mem, queue, publish);
}

fn consumeChunk(self: *Self, mem: *Memory, queue: *Queue, publish: bool) !bool {
    const worker = self.worker.?;
    const request = &self.pending.?;
    if (worker.result.failed) {
        request.status = S_IOERR;
    } else if (request.kind == T_IN or request.kind == T_OUT) {
        const desc = request.descs[request.descriptor];
        if (request.kind == T_IN and publish) {
            const bytes = try mem.slice(@intCast(desc.addr + request.descriptor_offset), request.chunk_len);
            @memcpy(bytes, worker.buffer[0..request.chunk_len]);
        }
        request.descriptor_offset += request.chunk_len;
        request.file_offset += request.chunk_len;
        if (request.kind == T_IN and worker.result.short_read) {
            const remaining = desc.len - request.descriptor_offset;
            if (publish) {
                const bytes = try mem.slice(@intCast(desc.addr + request.descriptor_offset), remaining);
                @memset(bytes, 0);
            }
            request.descriptor_offset += remaining;
            request.file_offset += remaining;
        }
    }
    worker.consume();
    return self.submitNext(mem, queue, publish);
}

/// Drain only already admitted work. No avail consumption or extra disk sync.
pub fn quiesce(self: *Self, mem: *Memory, queue: *Queue, publish: bool) !bool {
    const worker = self.worker orelse return false;
    var completed = false;
    while (self.pending != null) {
        const request = self.pending.?;
        const applicable = publish and request.generation == self.generation and sameQueue(request.queue_state, queue.*);
        worker.waitReady();
        if (worker.ready()) {
            if (try self.consumeChunk(mem, queue, applicable)) completed = true;
        } else if (try self.submitNext(mem, queue, applicable)) completed = true;
    }
    return completed and publish;
}

pub fn invalidate(self: *Self, mem: *Memory, queue: *Queue) !void {
    _ = try self.quiesce(mem, queue, false);
    self.generation +%= 1;
}

/// One logical-request credit is reserved before popAvail. Completion refills
/// retained avail work without requiring another guest notification.
pub fn processAsync(self: *Self, mem: *Memory, queue: *Queue) !bool {
    const worker = self.worker.?;
    try validateQueue(mem, queue.*);
    var did_work = false;
    var count: usize = 0;
    while (count < queue.size) : (count += 1) {
        if (self.pending) |request| {
            if (request.generation != self.generation or !sameQueue(request.queue_state, queue.*))
                try self.invalidate(mem, queue);
        }
        if (self.pending != null) {
            if (!worker.ready()) return did_work;
            if (try self.consumeChunk(mem, queue, true)) did_work = true;
            if (self.pending != null) return did_work;
        }
        // The empty slot and its fixed staging buffer are the reserved credit.
        const head = try queue.popAvail(mem) orelse return did_work;
        self.pending = self.capture(mem, queue, head) catch |err| {
            log.warn("captured block request rejected: {}", .{err});
            try queue.pushUsed(mem, head, 0);
            did_work = true;
            continue;
        };
        if (try self.submitNext(mem, queue, true)) did_work = true;
        if (self.pending != null) return did_work;
    }
    return did_work;
}

/// Device features offered to the driver.
pub fn deviceFeatures() u64 {
    return virtio.F_VERSION_1 | F_FLUSH;
}

/// Read from device config space.
pub fn readConfig(self: Self, offset: u64, data: []u8) void {
    // Config space: le64 capacity at offset 0
    if (offset + data.len <= 8) {
        var cap_bytes: [8]u8 = undefined;
        std.mem.writeInt(u64, &cap_bytes, self.capacity, .little);
        const start: usize = @intCast(offset);
        @memcpy(data, cap_bytes[start..][0..data.len]);
    } else {
        @memset(data, 0);
    }
}

/// Validate that a sector range fits within the disk capacity.
fn validateSectorRange(self: Self, sector: u64, data_len: u64) bool {
    const end_sector = std.math.add(u64, sector, (data_len + SECTOR_SIZE - 1) / SECTOR_SIZE) catch return false;
    return end_sector <= self.capacity;
}

/// Process a single request from the virtqueue.
pub fn processRequest(self: Self, mem: *Memory, queue: *Queue, head: u16) !void {
    // Walk the chain collecting descriptors (with cycle detection)
    var descs: [16]Queue.Desc = undefined;
    const desc_count = try queue.collectChain(mem, head, &descs);

    // Need at least header (desc 0) + status (last desc)
    if (desc_count < 2) {
        log.err("block request with only {} descriptors", .{desc_count});
        return error.MalformedRequest;
    }

    // Parse header (first descriptor)
    const hdr_desc = descs[0];
    if (hdr_desc.len < REQ_HDR_SIZE) {
        log.err("block request header too small: {}", .{hdr_desc.len});
        return error.MalformedRequest;
    }
    const hdr_bytes = try mem.slice(@intCast(hdr_desc.addr), REQ_HDR_SIZE);
    const req_type = std.mem.readInt(u32, hdr_bytes[0..4], .little);
    const sector = std.mem.readInt(u64, hdr_bytes[8..16], .little);

    // Status descriptor is always the last one — must be device-writable
    const status_desc = descs[desc_count - 1];
    if (status_desc.flags & virtio.DESC_F_WRITE == 0) {
        log.err("block status descriptor is not device-writable", .{});
        return error.MalformedRequest;
    }
    const status_ptr = try mem.slice(@intCast(status_desc.addr), 1);

    // Calculate total data length across all data descriptors
    var total_data_len: u64 = 0;
    for (descs[1 .. desc_count - 1]) |desc| {
        total_data_len += desc.len;
    }

    var status: u8 = S_OK;
    // Bytes written to device-writable descriptors (for used ring len).
    // T_IN: data buffers + status byte. T_OUT/T_FLUSH/others: status byte only.
    var device_written: u64 = 1; // always at least the status byte

    switch (req_type) {
        T_IN => {
            // Validate data descriptors are device-writable (VMM writes disk data into them)
            for (descs[1 .. desc_count - 1]) |desc| {
                if (desc.flags & virtio.DESC_F_WRITE == 0) {
                    log.err("T_IN data descriptor is not device-writable", .{});
                    status = S_IOERR;
                    break;
                }
            }
            // Validate sector range before any I/O
            if (status == S_OK and !self.validateSectorRange(sector, total_data_len)) {
                log.err("read past end of disk: sector={} len={}", .{ sector, total_data_len });
                status = S_IOERR;
            } else if (status == S_OK) {
                // Read from disk into guest buffers
                // sector is validated by validateSectorRange — multiplication is safe
                var file_offset: u64 = sector * SECTOR_SIZE;
                for (descs[1 .. desc_count - 1]) |desc| {
                    const buf = try mem.slice(@intCast(desc.addr), desc.len);
                    const rc: isize = @bitCast(linux.pread(self.fd, buf.ptr, buf.len, @bitCast(file_offset)));
                    if (rc < 0) {
                        status = S_IOERR;
                        break;
                    }
                    const bytes_read: u32 = @intCast(rc);
                    // Zero-fill remainder if short read
                    if (bytes_read < desc.len) {
                        @memset(buf[bytes_read..], 0);
                    }
                    file_offset = std.math.add(u64, file_offset, desc.len) catch {
                        status = S_IOERR;
                        break;
                    };
                }
                device_written += total_data_len;
            }
        },
        T_OUT => {
            // Validate data descriptors are device-readable (VMM reads guest data from them)
            for (descs[1 .. desc_count - 1]) |desc| {
                if (desc.flags & virtio.DESC_F_WRITE != 0) {
                    log.err("T_OUT data descriptor is device-writable (expected readable)", .{});
                    status = S_IOERR;
                    break;
                }
            }
            // Validate sector range before any I/O
            if (status == S_OK and !self.validateSectorRange(sector, total_data_len)) {
                log.err("write past end of disk: sector={} len={}", .{ sector, total_data_len });
                status = S_IOERR;
            } else if (status == S_OK) {
                // Write from guest buffers to disk
                // sector is validated by validateSectorRange — multiplication is safe
                var file_offset: u64 = sector * SECTOR_SIZE;
                for (descs[1 .. desc_count - 1]) |desc| {
                    const buf = try mem.slice(@intCast(desc.addr), desc.len);
                    // Retry short writes to prevent silent data loss
                    var written: u32 = 0;
                    while (written < desc.len) {
                        const rc: isize = @bitCast(linux.pwrite(self.fd, buf[written..].ptr, desc.len - written, @bitCast(file_offset + written)));
                        if (rc <= 0) {
                            status = S_IOERR;
                            break;
                        }
                        written += @intCast(rc);
                    }
                    if (status != S_OK) break;
                    file_offset = std.math.add(u64, file_offset, desc.len) catch {
                        status = S_IOERR;
                        break;
                    };
                }
            }
        },
        T_FLUSH => {
            const rc: isize = @bitCast(linux.fdatasync(self.fd));
            if (rc < 0) status = S_IOERR;
        },
        T_GET_ID => {
            // Write device ID string (up to 20 bytes)
            if (desc_count >= 3) {
                const id_desc = descs[1];
                const id_buf = try mem.slice(@intCast(id_desc.addr), @min(id_desc.len, 20));
                const id = "flint-virtio-blk";
                const copy_len = @min(id.len, id_buf.len);
                @memcpy(id_buf[0..copy_len], id[0..copy_len]);
                if (copy_len < id_buf.len) @memset(id_buf[copy_len..], 0);
                device_written += id_desc.len;
            }
        },
        else => {
            status = S_UNSUPP;
        },
    }

    // Write status byte
    status_ptr[0] = status;

    // Push to used ring with bytes written to device-writable descriptors
    const used_len: u32 = @intCast(@min(device_written, std.math.maxInt(u32)));
    try queue.pushUsed(mem, head, used_len);
}
