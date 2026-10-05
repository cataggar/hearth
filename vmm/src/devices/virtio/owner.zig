const std = @import("std");
const builtin = @import("builtin");
const linux = std.os.linux;
const Device = @import("mmio.zig");
const Vsock = @import("vsock.zig");
const Memory = @import("../../memory.zig");
const Vm = @import("../../kvm/vm.zig");
const Vcpu = @import("../../kvm/vcpu.zig");
const abi = @import("../../kvm/abi.zig");
const virtio = @import("../virtio.zig");
const sync = @import("../../sync.zig");
const Accelerator = @import("accelerator.zig");

const log = std.log.scoped(.virtio_owner);
pub const Mode = enum {
    L0,
    C00,
    C10,
    C01,
    C11,

    fn usesKick(self: Mode) bool {
        return self == .C10 or self == .C11;
    }

    fn usesIrq(self: Mode) bool {
        return self == .C01 or self == .C11;
    }
};
pub const EVENT_FLAGS = Accelerator.EVENT_FLAGS;
const CONTROL: u64 = std.math.maxInt(u64);
const TAP: u64 = CONTROL - 1;
const KICK: u64 = @as(u64, 1) << 63;
const RESAMPLE: u64 = @as(u64, 1) << 62;
pub const eventfd = Accelerator.eventfd;
pub const wake = Accelerator.wake;
pub const drain = Accelerator.drain;

const Kick = struct {
    fd: i32 = -1,
    queue_generation: u64 = 0,
    epoch: u64 = 0,
};

const Kind = enum { read, write, pause, unpause, stop, test_failure };
pub const FailureWait = struct {
    mutex: *sync.Mutex,
    condition: *sync.Condition,
};
const Request = struct {
    kind: Kind,
    offset: u64 = 0,
    data: [8]u8 = @splat(0),
    len: u32 = 0,
};

pub const Owner = struct {
    device: *Device,
    mem: *Memory,
    vm: *const Vm,
    failure: *std.atomic.Value(bool),
    vcpu: *Vcpu,
    failure_wait: ?FailureWait,
    vcpu_tid: i32,
    mode: Mode,
    irq: Accelerator.Irq = undefined,
    thread: ?std.Thread = null,
    control_fd: i32 = -1,
    epoll_fd: i32 = -1,
    mutex: sync.Mutex = .{},
    condition: sync.Condition = .{},
    request: Request = .{ .kind = .pause },
    in_flight: bool = false,
    submitted: bool = false,
    done: bool = false,
    failed: bool = false,
    paused: bool = true,
    stopping: bool = false,
    pending: u32 = 0,
    tracked: [Vsock.MAX_CONNECTIONS]Vsock.Interest = @splat(.{}),
    tap_events: u32 = 0,
    kicks: [3]Kick = @splat(.{}),
    kick_epoch: u64 = 0,
    resample_epoch: ?u64 = null,

    pub fn start(self: *Owner) !void {
        for (self.device.queues) |queue| {
            if (queue.ready and !queue.validate(self.mem)) return error.InvalidRestoredQueue;
        }
        if (self.mode.usesKick()) try Accelerator.require(self.vm, abi.c.KVM_CAP_IOEVENTFD);
        self.irq = try Accelerator.Irq.init(self.vm, self.device.irq, self.mode.usesIrq());
        errdefer self.irq.deinit() catch {};
        self.control_fd = try eventfd();
        errdefer abi.close(self.control_fd);
        const rc: isize = @bitCast(linux.epoll_create1(linux.EPOLL.CLOEXEC));
        if (rc < 0) return error.EpollCreateFailed;
        self.epoll_fd = @intCast(rc);
        errdefer abi.close(self.epoll_fd);
        try self.registration(linux.EPOLL.CTL_ADD, self.control_fd, linux.EPOLL.IN, CONTROL);
        self.thread = try std.Thread.spawn(.{}, entry, .{self});
    }

    fn registration(self: *Owner, operation: u32, fd: i32, events: u32, token: u64) !void {
        var event = linux.epoll_event{ .events = events, .data = .{ .u64 = token } };
        const rc: isize = @bitCast(linux.epoll_ctl(self.epoll_fd, operation, fd, &event));
        if (rc < 0) {
            log.err("epoll op={} fd={} token={} errno={}", .{ operation, fd, token, -rc });
            return error.EpollRegistrationFailed;
        }
    }

    fn call(self: *Owner, request: Request) ![8]u8 {
        self.mutex.lock();
        defer self.mutex.unlock();
        while (self.in_flight and !self.failed) self.condition.wait(&self.mutex);
        if (self.failed) return error.BackendOwnerFailed;
        self.in_flight = true;
        self.submitted = true;
        self.done = false;
        self.request = request;
        wake(self.control_fd) catch |err| {
            self.in_flight = false;
            self.submitted = false;
            return err;
        };
        while (!self.done and !self.failed) self.condition.wait(&self.mutex);
        const data = self.request.data;
        self.in_flight = false;
        self.condition.broadcast();
        if (self.failed) return error.BackendOwnerFailed;
        return data;
    }

    pub fn read(self: *Owner, offset: u64, len: u32) ![8]u8 {
        return self.call(.{ .kind = .read, .offset = offset, .len = len });
    }

    pub fn write(self: *Owner, offset: u64, data: [8]u8, len: u32) !void {
        _ = try self.call(.{ .kind = .write, .offset = offset, .data = data, .len = len });
    }

    pub fn pause(self: *Owner) !void {
        _ = try self.call(.{ .kind = .pause });
    }

    pub fn unpause(self: *Owner) !void {
        _ = try self.call(.{ .kind = .unpause });
    }

    pub fn failForTest(self: *Owner) !void {
        if (!builtin.is_test) @compileError("owner failure injection is test-only");
        _ = try self.call(.{ .kind = .test_failure });
    }

    fn publishFailure(self: *Owner) void {
        self.failure.store(true, .seq_cst);
        @atomicStore(u8, &self.vcpu.kvm_run.immediate_exit, 1, .seq_cst);
        _ = linux.tkill(self.vcpu_tid, linux.SIG.USR1);
        if (self.failure_wait) |wait| {
            wait.mutex.lock();
            wait.condition.broadcast();
            wait.mutex.unlock();
        }
    }

    pub fn stop(self: *Owner) void {
        if (self.thread) |thread| {
            _ = self.call(.{ .kind = .stop }) catch {};
            thread.join();
            self.thread = null;
            abi.close(self.epoll_fd);
            abi.close(self.control_fd);
        }
    }

    fn control(self: *Owner) !void {
        self.mutex.lock();
        if (!self.submitted) {
            self.mutex.unlock();
            return;
        }
        var request = self.request;
        self.submitted = false;
        self.mutex.unlock();
        switch (request.kind) {
            .read => self.device.handleRead(request.offset, request.data[0..request.len]),
            .write => {
                if (request.offset == virtio.MMIO_QUEUE_NOTIFY) {
                    if (self.device.decodeNotify(request.data[0..request.len])) |queue| self.pending |= @as(u32, 1) << @intCast(queue);
                } else {
                    self.device.handleWrite(request.offset, request.data[0..request.len]);
                    for (&self.device.queues) |*queue| {
                        if (queue.ready and !queue.validate(self.mem)) {
                            queue.ready = false;
                            queue.generation +%= 1;
                        }
                    }
                    if (request.offset == virtio.MMIO_STATUS or request.offset == virtio.MMIO_QUEUE_READY) {
                        self.pending |= 7;
                    }
                }
            },
            .pause => self.paused = true,
            .unpause => {
                self.paused = false;
                self.pending |= 7;
            },
            .stop => self.stopping = true,
            .test_failure => if (builtin.is_test) return error.InjectedOwnerFailure else unreachable,
        }
        try self.refresh();
        if (request.kind == .unpause) try self.service();
        self.mutex.lock();
        self.request.data = request.data;
        self.done = true;
        self.condition.broadcast();
        self.mutex.unlock();
    }

    fn refresh(self: *Owner) !void {
        const ready = !self.paused and !self.stopping and self.device.status & virtio.STATUS_DRIVER_OK != 0 and self.device.status & virtio.STATUS_FAILED == 0;
        const receive = ready and self.device.queues[0].hasAvail(self.mem);
        const tap = self.device.getPollFd();
        var tap_events: u32 = if (receive) linux.EPOLL.IN else 0;
        switch (self.device.backend) {
            .net => |net| if (ready and net.tx_blocked and self.device.queues[1].hasAvail(self.mem)) {
                tap_events |= linux.EPOLL.OUT;
            },
            else => {},
        }
        if (tap >= 0 and self.tap_events != tap_events) {
            const operation: u32 = if (tap_events == 0) linux.EPOLL.CTL_DEL else if (self.tap_events == 0) linux.EPOLL.CTL_ADD else linux.EPOLL.CTL_MOD;
            try self.registration(operation, tap, tap_events, TAP);
            self.tap_events = tap_events;
        }
        var wanted: [Vsock.MAX_CONNECTIONS]Vsock.Interest = @splat(.{});
        switch (self.device.backend) {
            .vsock => |*vsock| if (ready) {
                wanted = vsock.interests(receive);
            },
            else => {},
        }
        // Delete all old generations before adding any: a closed fd number can
        // be reused by a different connection slot in the same batch.
        for (&self.tracked, wanted) |*old, current| {
            if (old.fd >= 0 and (old.fd != current.fd or old.generation != current.generation or old.events != current.events)) {
                const rc: isize = @bitCast(linux.epoll_ctl(self.epoll_fd, linux.EPOLL.CTL_DEL, old.fd, null));
                if (rc < 0 and rc != -@as(isize, @backingInt(linux.E.NOENT)) and rc != -@as(isize, @backingInt(linux.E.BADF))) return error.EpollRegistrationFailed;
                old.* = .{};
            }
        }
        try self.refreshKicks(ready);
        try self.irq.reconcile(ready, self.device.interrupt_status);
        const resample = if (self.irq.assigned and self.irq.trigger == .level) self.irq.generation else null;
        if (self.resample_epoch != resample) {
            if (self.resample_epoch != null) try self.registration(linux.EPOLL.CTL_DEL, self.irq.resample_fd, 0, 0);
            self.resample_epoch = null;
            if (resample) |epoch| {
                if (epoch >= RESAMPLE) return error.GenerationExhausted;
                try self.registration(linux.EPOLL.CTL_ADD, self.irq.resample_fd, linux.EPOLL.IN, RESAMPLE | epoch);
                self.resample_epoch = epoch;
            }
        }
        for (&self.tracked, wanted, 0..) |*old, current, index| {
            if (old.fd < 0 and current.fd >= 0) {
                if (current.generation >= (@as(u64, 1) << 54)) return error.GenerationExhausted;
                const token = (current.generation << 8) | index;
                try self.registration(linux.EPOLL.CTL_ADD, current.fd, current.events, token);
                old.* = current;
            }
        }
    }

    fn removeKick(self: *Owner, index: usize) !void {
        const old = self.kicks[index];
        if (old.fd < 0) return;
        try Accelerator.kick(self.vm, old.fd, self.device.mmio_base + virtio.MMIO_QUEUE_NOTIFY, @intCast(index), true);
        try self.registration(linux.EPOLL.CTL_DEL, old.fd, 0, 0);
        try drain(old.fd);
        abi.close(old.fd);
        self.kicks[index] = .{};
    }

    fn refreshKicks(self: *Owner, ready: bool) !void {
        for (&self.kicks, 0..) |*registered, index| {
            const queue = &self.device.queues[index];
            const wanted = self.mode.usesKick() and ready and index < self.device.numQueues() and queue.isReady();
            if (registered.fd >= 0 and (!wanted or registered.queue_generation != queue.generation))
                try self.removeKick(index);
            if (!wanted or registered.fd >= 0) continue;
            if (self.kick_epoch >= (@as(u64, 1) << 54) - 1) return error.GenerationExhausted;
            self.kick_epoch += 1;
            const fd = try eventfd();
            errdefer abi.close(fd);
            try self.registration(linux.EPOLL.CTL_ADD, fd, linux.EPOLL.IN, KICK | (self.kick_epoch << 8) | index);
            errdefer _ = linux.epoll_ctl(self.epoll_fd, linux.EPOLL.CTL_DEL, fd, null);
            try Accelerator.kick(self.vm, fd, self.device.mmio_base + virtio.MMIO_QUEUE_NOTIFY, @intCast(index), false);
            registered.* = .{ .fd = fd, .queue_generation = queue.generation, .epoch = self.kick_epoch };
            log.info("GSI{} queue{} kickfd={} epoch={} GPA=0x{x} len=4 DATAMATCH={}", .{
                self.device.irq, index, fd, self.kick_epoch, self.device.mmio_base + virtio.MMIO_QUEUE_NOTIFY, index,
            });
        }
    }

    fn service(self: *Owner) !void {
        if (self.paused or self.stopping) return;
        if (self.device.status & virtio.STATUS_DRIVER_OK == 0 or self.device.status & virtio.STATUS_FAILED != 0) {
            self.pending = 0;
            return;
        }
        self.device.flushPendingWrites();
        var again: u32 = 0;
        var irq = false;
        const pending = self.pending;
        self.pending = 0;
        for (0..self.device.numQueues()) |index| {
            if (pending & (@as(u32, 1) << @intCast(index)) == 0) continue;
            const work = self.device.processQueue(self.mem, @intCast(index));
            irq = work or irq;
            if (work and self.device.queues[index].hasAvail(self.mem)) again |= @as(u32, 1) << @intCast(index);
        }
        switch (self.device.backend) {
            .vsock => |*vsock| {
                if (self.device.queues[0].isReady() and vsock.deliverPending(self.mem, &self.device.queues[0])) {
                    self.device.interrupt_status |= virtio.INT_USED_RING;
                    irq = true;
                }
                if (irq and self.device.queues[1].hasAvail(self.mem)) again |= 2;
            },
            else => {},
        }
        if (irq) {
            try self.irq.notify(self.device.interrupt_status);
        }
        self.pending |= again;
        try self.refresh();
    }

    fn entry(self: *Owner) void {
        defer {
            for (0..self.kicks.len) |index| self.removeKick(index) catch |err| {
                log.err("GSI{} queue{} cleanup failed: {}", .{ self.device.irq, index, err });
                self.publishFailure();
            };
            self.irq.deinit() catch |err| {
                log.err("GSI{} IRQ cleanup failed: {}", .{ self.device.irq, err });
                self.publishFailure();
            };
        }
        self.run() catch |err| {
            log.err("device GSI{} owner failed: {}", .{ self.device.irq, err });
            self.publishFailure();
            self.mutex.lock();
            self.failed = true;
            self.condition.broadcast();
            self.mutex.unlock();
        };
    }

    fn run(self: *Owner) !void {
        log.info("GSI{} mode={s} owner_tid={} controlfd={} epollfd={}", .{
            self.device.irq, @tagName(self.mode), linux.gettid(), self.control_fd, self.epoll_fd,
        });
        self.pending = 7;
        try self.refresh();
        while (!self.stopping) {
            var events: [16]linux.epoll_event = undefined;
            const count: isize = @bitCast(linux.epoll_wait(self.epoll_fd, &events, events.len, if (self.pending == 0 or self.paused) -1 else 0));
            if (count == -@as(isize, @backingInt(linux.E.INTR))) continue;
            if (count < 0) return error.EpollWaitFailed;
            // Control precedes data even if epoll returns it last.
            for (events[0..@intCast(count)]) |event| {
                if (event.data.u64 == CONTROL) {
                    try drain(self.control_fd);
                    try self.control();
                }
            }
            for (events[0..@intCast(count)]) |event| {
                const token = event.data.u64;
                if (token == CONTROL) continue;
                if (token == TAP) {
                    if (event.events & linux.EPOLL.IN != 0) self.pending |= 1;
                    if (event.events & linux.EPOLL.OUT != 0) self.pending |= 2;
                } else if (token & KICK != 0) {
                    const index = token & 255;
                    const epoch = (token & ~KICK) >> 8;
                    if (index < self.kicks.len and self.kicks[index].fd >= 0 and self.kicks[index].epoch == epoch) {
                        try drain(self.kicks[index].fd);
                        self.pending |= @as(u32, 1) << @intCast(index);
                    }
                } else if (token & RESAMPLE != 0) {
                    if (self.resample_epoch == (token & ~RESAMPLE)) {
                        const ready = !self.paused and !self.stopping and self.device.status & virtio.STATUS_DRIVER_OK != 0 and self.device.status & virtio.STATUS_FAILED == 0;
                        try self.irq.resampled(ready, self.device.interrupt_status);
                    }
                } else {
                    const index = token & 255;
                    if (index < self.tracked.len and self.tracked[index].generation == token >> 8 and self.tracked[index].fd >= 0) {
                        switch (self.device.backend) {
                            .vsock => |*vsock| vsock.readable(@intCast(index), token >> 8),
                            else => {},
                        }
                        self.pending |= 1;
                    }
                }
            }
            try self.service();
        }
    }
};

pub const Set = struct {
    owners: [virtio.MAX_DEVICES]Owner = undefined,
    count: usize = 0,
    failed: std.atomic.Value(bool) = std.atomic.Value(bool).init(false),
    vcpu: ?*Vcpu = null,
    failure_wait: ?FailureWait = null,

    pub fn start(self: *Set, devices: *[virtio.MAX_DEVICES]?Device, count: usize, vm: *const Vm, mem: *Memory, mode: Mode, vcpu: *Vcpu) !void {
        self.vcpu = vcpu;
        errdefer self.stop();
        for (devices[0..count]) |*optional| {
            const device = if (optional.*) |*value| value else return error.MissingDevice;
            const owner = &self.owners[self.count];
            owner.* = .{
                .device = device,
                .vm = vm,
                .mem = mem,
                .failure = &self.failed,
                .vcpu = vcpu,
                .failure_wait = self.failure_wait,
                .vcpu_tid = @intCast(linux.gettid()),
                .mode = mode,
            };
            try owner.start();
            self.count += 1;
        }
        // All owners and restored resources reconcile before the first KVM_RUN.
        try self.unpause();
    }

    pub fn pause(self: *Set) !void {
        for (self.owners[0..self.count]) |*owner| try owner.pause();
    }

    pub fn unpause(self: *Set) !void {
        for (self.owners[0..self.count]) |*owner| try owner.unpause();
    }

    pub fn beforeEntry(self: *Set, clear: bool) !void {
        const vcpu = self.vcpu orelse return error.MissingVcpu;
        // Ordered with publishFailure: a pre-clear failure is observed, or
        // its later immediate-exit assertion persists into KVM_RUN.
        if (clear and @atomicLoad(u8, &vcpu.kvm_run.immediate_exit, .seq_cst) != 0)
            @atomicStore(u8, &vcpu.kvm_run.immediate_exit, 0, .seq_cst);
        if (builtin.is_test) {
            if (test_after_clear) |hook| try hook(self);
        }
        if (self.failed.load(.seq_cst)) return error.BackendOwnerFailed;
    }

    pub fn stop(self: *Set) void {
        for (self.owners[0..self.count]) |*owner| owner.stop();
        self.count = 0;
    }

    pub fn finish(self: *Set) !void {
        self.stop();
        if (self.failed.load(.acquire)) return error.BackendOwnerFailed;
    }
};

pub var test_after_clear: ?*const fn (*Set) anyerror!void = null;
