const std = @import("std");
const linux = std.os.linux;
const Memory = @import("memory.zig");
const Mmio = @import("devices/virtio/mmio.zig");
const virtio = @import("devices/virtio.zig");
const Shadow = @import("devices/virtio/net_shadow.zig");
const Vhost = @import("devices/virtio/net_vhost.zig");
const Vm = @import("kvm/vm.zig");
const Vcpu = @import("kvm/vcpu.zig");

const Self = @This();
const log = std.log.scoped(.net_dispatch);
pub const Mode = enum { userspace, vhost, auto };
pub const Options = struct { enabled: bool = false, mode: Mode = .userspace };

mem: *Memory,
dev: *Mmio,
vm: *const Vm,
vcpu: *Vcpu,
vcpu_tid: i32,
dispatcher_tid: std.atomic.Value(i32) = .init(0),
requested: Mode,
effective: Mode,
wake: i32,
thread: ?std.Thread = null,
stopping: std.atomic.Value(bool) = .init(false),
locked: std.atomic.Value(bool) = .init(false),
failure: ?anyerror = null,
session: ?Vhost = null,
ever_active: bool = false,
generation: u64 = 0,

pub fn init(options: Options, mem: *Memory, dev: *Mmio, vm: *const Vm, vcpu: *Vcpu) !Self {
    if (dev.device_id != virtio.DEVICE_ID_NET) return error.NetBackendRequiresTap;
    if (options.mode != .userspace and linux.getuid() == 0)
        return error.VhostRequiresPrivilegeDrop;
    const wake = try Vhost.eventfd();
    errdefer _ = linux.close(wake);
    const tap = dev.backend.net.tap_fd;
    const rc: isize = @bitCast(linux.ioctl(tap, 0x400454d0, 0)); // TUNSETOFFLOAD, scalar mask
    if (rc < 0) return error.NetTapOffloadConfigurationFailed;
    return .{
        .mem = mem,
        .dev = dev,
        .vm = vm,
        .vcpu = vcpu,
        .vcpu_tid = @intCast(linux.gettid()),
        .requested = options.mode,
        .effective = options.mode,
        .wake = wake,
    };
}

pub fn lock(self: *Self) void {
    while (self.locked.cmpxchgWeak(false, true, .acquire, .monotonic) != null)
        std.atomic.spinLoopHint();
}

pub fn unlock(self: *Self) void {
    self.locked.store(false, .release);
}

pub fn check(self: *Self) !void {
    self.lock();
    defer self.unlock();
    if (self.failure) |err| return err;
}

pub fn notify(self: *Self) !void {
    try Vhost.signal(self.wake);
}

pub fn start(self: *Self) !void {
    if (self.thread != null) return error.NetDispatcherAlreadyRunning;
    try self.check();
    self.lock();
    self.service(false) catch |err| {
        self.unlock();
        return err;
    };
    self.unlock();
    self.stopping.store(false, .release);
    self.thread = try std.Thread.spawn(.{}, run, .{self});
    log.info("requested={s} adapter=blocked-poll/direct-irq generation={}", .{ @tagName(self.requested), self.generation });
    if (self.dev.interrupt_status & virtio.INT_USED_RING != 0) try self.raiseIrq();
}

pub fn pause(self: *Self) !void {
    self.stopping.store(true, .release);
    if (self.thread) |thread| {
        self.notify() catch {
            const tid = self.dispatcher_tid.load(.acquire);
            if (tid != 0) _ = linux.tkill(tid, linux.SIG.USR1);
        };
        thread.join();
        self.thread = null;
    }
    self.lock();
    defer self.unlock();
    if (self.session) |*session| {
        defer {
            session.deinit();
            self.session = null;
        }
        if (try session.quiesce(self.mem, &self.dev.queues)) {
            self.dev.interrupt_status |= virtio.INT_USED_RING;
        }
    }
    self.generation +%= 1;
    if (self.failure) |err| return err;
}

pub fn deinit(self: *Self) void {
    self.pause() catch |err| {
        log.err("stop failure={s}", .{@errorName(err)});
        if (self.session) |*session| session.deinit();
        self.session = null;
    };
    _ = linux.close(self.wake);
}

pub fn lifecycleWrite(offset: u64) bool {
    return switch (offset) {
        virtio.MMIO_STATUS,
        virtio.MMIO_QUEUE_READY,
        virtio.MMIO_QUEUE_NUM,
        virtio.MMIO_QUEUE_DESC_LOW,
        virtio.MMIO_QUEUE_DESC_HIGH,
        virtio.MMIO_QUEUE_DRIVER_LOW,
        virtio.MMIO_QUEUE_DRIVER_HIGH,
        virtio.MMIO_QUEUE_DEVICE_LOW,
        virtio.MMIO_QUEUE_DEVICE_HIGH,
        virtio.MMIO_DRIVER_FEATURES,
        => true,
        else => false,
    };
}

fn ready(self: *Self) bool {
    return self.dev.status & virtio.STATUS_DRIVER_OK != 0 and
        self.dev.queues[0].isReady() and self.dev.queues[1].isReady();
}

fn activate(self: *Self) !void {
    if (!self.ready()) return;
    if (self.dev.driver_features & (@as(u64, 1) << 32) == 0)
        return error.NetVersion1NotNegotiated;
    if (self.effective == .userspace or self.session != null) return;
    for (self.dev.queues[0..2]) |*queue| try Shadow.validateQueue(self.mem, queue);
    self.session = Vhost.init(self.dev.backend.net.tap_fd, self.mem, &self.dev.queues) catch |err| {
        const unsupported = switch (err) {
            error.VhostUnavailable,
            error.VhostAccessDenied,
            error.VhostVersion1Unsupported,
            error.VhostWorkerIsolationUnsupported,
            error.VhostUapiUnsupported,
            => true,
            else => false,
        };
        if (self.requested == .auto and !self.ever_active and unsupported) {
            self.effective = .userspace;
            log.warn("requested=auto effective=userspace reason={s} phase=preactivation-unwound", .{@errorName(err)});
            return;
        }
        return err;
    };
    self.effective = .vhost;
    self.ever_active = true;
}

fn raiseIrq(self: *Self) !void {
    try self.vm.setIrqLine(self.dev.irq, 1);
    try self.vm.setIrqLine(self.dev.irq, 0);
}

fn fail(self: *Self, err: anyerror) void {
    self.failure = err;
    log.err("generation={} fatal={s} effective={s}", .{ self.generation, @errorName(err), @tagName(self.effective) });
    @atomicStore(u8, &self.vcpu.kvm_run.immediate_exit, 1, .release);
    _ = linux.tkill(self.vcpu_tid, linux.SIG.USR1);
}

fn userspace(self: *Self, rx_ready: bool) !bool {
    if (!self.ready()) return false;
    var did_work = false;
    const tap = self.dev.backend.net.tap_fd;
    for (0..2) |index| {
        if (index == 0 and !rx_ready) continue;
        const queue = &self.dev.queues[index];
        try Shadow.validateQueue(self.mem, queue);
        var handled: u16 = 0;
        while (handled < queue.size and try Shadow.available(self.mem, queue) > 0) : (handled += 1) {
            const chain = try Shadow.collect(self.mem, queue, index == 0);
            var iov: [16]std.posix.iovec = undefined;
            for (chain.descs[0..chain.count], 0..) |desc, i| {
                const buffer = try self.mem.slice(@intCast(desc.addr), desc.len);
                iov[i] = .{ .base = buffer.ptr, .len = buffer.len };
            }
            const rc: isize = @bitCast(if (index == 0)
                linux.readv(tap, &iov, @intCast(chain.count))
            else
                linux.writev(tap, @ptrCast(&iov), @intCast(chain.count)));
            if (rc == -@as(isize, @backingInt(linux.E.AGAIN))) break;
            if (rc == -@as(isize, @backingInt(linux.E.INTR))) continue;
            if (rc < 0) return error.NetTapIoFailed;
            if (index == 0 and rc < 12) return error.NetTapShortRead;
            if (index == 1 and rc != chain.bytes) return error.NetTapShortWrite;
            queue.last_avail_idx +%= 1;
            try Shadow.pushGuestUsed(self.mem, queue, chain.head, if (index == 0) @intCast(rc) else 0);
            did_work = true;
        }
    }
    return did_work;
}

fn service(self: *Self, rx_ready: bool) !void {
    try self.activate();
    var did_work = false;
    if (self.session) |*session| {
        did_work = try session.complete(self.mem, &self.dev.queues);
        try session.submit(self.mem, &self.dev.queues);
    } else {
        did_work = try self.userspace(rx_ready);
    }
    if (did_work) {
        self.dev.interrupt_status |= virtio.INT_USED_RING;
        try self.raiseIrq();
    }
}

fn run(self: *Self) void {
    self.dispatcher_tid.store(@intCast(linux.gettid()), .release);
    defer self.dispatcher_tid.store(0, .release);
    var rx_ready = false;
    while (!self.stopping.load(.acquire)) {
        self.lock();
        if (self.stopping.load(.acquire)) {
            self.unlock();
            return;
        }
        self.service(rx_ready) catch |err| {
            self.fail(err);
            self.unlock();
            return;
        };
        var pollfds: [6]linux.pollfd = undefined;
        pollfds[0] = .{ .fd = self.wake, .events = linux.POLL.IN, .revents = 0 };
        var count: usize = 1;
        var tap_slot: ?usize = null;
        if (self.session) |*session| {
            for (0..2) |index| {
                pollfds[count] = .{ .fd = session.call[index], .events = linux.POLL.IN, .revents = 0 };
                pollfds[count + 1] = .{ .fd = session.err[index], .events = linux.POLL.IN, .revents = 0 };
                count += 2;
            }
        } else if (self.ready() and (Shadow.available(self.mem, &self.dev.queues[0]) catch 0) > 0) {
            tap_slot = count;
            pollfds[count] = .{ .fd = self.dev.backend.net.tap_fd, .events = linux.POLL.IN, .revents = 0 };
            count += 1;
        }
        self.unlock();
        const rc: isize = @bitCast(linux.poll(&pollfds, @intCast(count), -1));
        if (rc == -@as(isize, @backingInt(linux.E.INTR))) continue;
        self.lock();
        if (rc < 0) {
            self.fail(error.NetDispatcherPollFailed);
            self.unlock();
            return;
        }
        for (pollfds[0..count]) |fd| {
            if (fd.revents & (linux.POLL.ERR | linux.POLL.HUP | linux.POLL.NVAL) != 0) {
                self.fail(error.NetDispatcherFdFailed);
                self.unlock();
                return;
            }
        }
        _ = Vhost.drainEvent(self.wake) catch |err| {
            self.fail(err);
            self.unlock();
            return;
        };
        rx_ready = if (tap_slot) |slot| pollfds[slot].revents & linux.POLL.IN != 0 else false;
        self.unlock();
    }
}
