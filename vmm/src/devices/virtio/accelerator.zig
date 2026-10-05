const std = @import("std");
const builtin = @import("builtin");
const linux = std.os.linux;
const abi = @import("../../kvm/abi.zig");
const c = abi.c;
const Vm = @import("../../kvm/vm.zig");

const log = std.log.scoped(.virtio_accelerator);
pub const EVENT_FLAGS: u32 = 0x80800;

pub const TestIoctlTiming = struct {
    operation: []const u8,
    request: u32,
    identity: u64,
    elapsed_ns: u64,
};

pub var test_ioctl_observer: ?*const fn (TestIoctlTiming) void = null;

fn monotonic() u64 {
    var stamp: linux.timespec = undefined;
    if (linux.clock_gettime(.MONOTONIC, &stamp) != 0) return 0;
    return @as(u64, @intCast(stamp.sec)) * 1_000_000_000 + @as(u64, @intCast(stamp.nsec));
}

pub fn eventfd() !i32 {
    const rc: isize = @bitCast(linux.syscall2(.eventfd2, 0, EVENT_FLAGS));
    if (rc < 0) return error.EventfdCreateFailed;
    return @intCast(rc);
}

pub fn wake(fd: i32) !void {
    var value: u64 = 1;
    while (true) {
        const rc: isize = @bitCast(linux.write(fd, std.mem.asBytes(&value).ptr, 8));
        if (rc == -@as(isize, @backingInt(linux.E.INTR))) continue;
        if (rc == 8 or rc == -@as(isize, @backingInt(linux.E.AGAIN))) return;
        return error.EventfdWriteFailed;
    }
}

pub fn drain(fd: i32) !void {
    var value: u64 = 0;
    var budget: u32 = 0;
    // A continuously kicking guest must not starve the control mailbox.
    // Level-triggered epoll retains readiness if another batch remains.
    while (budget < 32) : (budget += 1) {
        const rc: isize = @bitCast(linux.read(fd, std.mem.asBytes(&value).ptr, 8));
        if (rc == 8 or rc == -@as(isize, @backingInt(linux.E.INTR))) continue;
        if (rc == -@as(isize, @backingInt(linux.E.AGAIN))) return;
        return error.EventfdReadFailed;
    }
}

fn ioctl(vm: *const Vm, request: u32, argument: usize, operation: []const u8, identity: u64) !void {
    const started = if (builtin.is_test and test_ioctl_observer != null) monotonic() else 0;
    defer if (builtin.is_test) {
        if (test_ioctl_observer) |observe| {
            observe(.{ .operation = operation, .request = request, .identity = identity, .elapsed_ns = monotonic() - started });
        }
    };
    while (true) {
        const rc: isize = @bitCast(linux.ioctl(vm.fd, request, argument));
        if (rc == -@as(isize, @backingInt(linux.E.INTR))) continue;
        if (rc >= 0) return;
        log.err("{s}: vm_fd={} ioctl=0x{x} identity=0x{x} errno={}", .{ operation, vm.fd, request, identity, -rc });
        return error.EventfdRegistrationFailed;
    }
}

pub fn require(vm: *const Vm, capability: u32) !void {
    const rc: isize = @bitCast(linux.ioctl(vm.fd, c.KVM_CHECK_EXTENSION, capability));
    if (rc <= 0) {
        log.err("KVM capability={} result={} vm_fd={}; requested mode is not downgraded", .{ capability, rc, vm.fd });
        return error.EventfdCapabilityUnavailable;
    }
}

pub fn kick(vm: *const Vm, fd: i32, address: u64, queue: u32, remove: bool) !void {
    var registration = std.mem.zeroes(c.kvm_ioeventfd);
    registration.fd = fd;
    registration.addr = address;
    registration.len = 4;
    registration.datamatch = queue;
    registration.flags = @intCast(c.KVM_IOEVENTFD_FLAG_DATAMATCH |
        (if (remove) c.KVM_IOEVENTFD_FLAG_DEASSIGN else @as(c_int, 0)));
    ioctl(vm, c.KVM_IOEVENTFD, @intFromPtr(&registration), if (remove) "ioeventfd deassign" else "ioeventfd assign", address) catch |err| {
        log.err("queue={} eventfd={} length=4 DATAMATCH={}", .{ queue, fd, queue });
        return err;
    };
}

pub const Trigger = enum { edge, level };
pub const Policy = struct {
    pic_level: bool,
    pic_masked: bool,
    ioapic_level: bool,
    ioapic_masked: bool,

    pub fn trigger(self: Policy) !Trigger {
        if (!self.pic_masked and !self.ioapic_masked and self.pic_level != self.ioapic_level)
            return error.MixedActiveIRQTrigger;
        // A masked level route still needs an assertion, not a discarded pulse.
        const level = if (!self.pic_masked) self.pic_level else if (!self.ioapic_masked) self.ioapic_level else self.pic_level or self.ioapic_level;
        return if (level) .level else .edge;
    }
};

pub fn policy(vm: *const Vm, gsi: u32) !Policy {
    if (gsi >= 16) return error.UnsupportedVirtioGsi;
    const pic = try vm.getIrqChip(if (gsi < 8) c.KVM_IRQCHIP_PIC_MASTER else c.KVM_IRQCHIP_PIC_SLAVE);
    const ioapic = try vm.getIrqChip(c.KVM_IRQCHIP_IOAPIC);
    const offset = c.HEARTH_IRQCHIP_DATA_OFFSET + c.HEARTH_IOAPIC_REDIR_OFFSET + @as(usize, gsi) * 8;
    const entry = std.mem.readInt(u64, ioapic[offset..][0..8], .little);
    const bit = @as(u8, 1) << @as(u3, @intCast(gsi % 8));
    return .{
        .pic_level = pic[c.HEARTH_IRQCHIP_DATA_OFFSET + c.HEARTH_PIC_ELCR_OFFSET] & bit != 0,
        .pic_masked = pic[c.HEARTH_IRQCHIP_DATA_OFFSET + c.HEARTH_PIC_IMR_OFFSET] & bit != 0,
        .ioapic_level = entry & (@as(u64, 1) << 15) != 0,
        .ioapic_masked = entry & (@as(u64, 1) << 16) != 0,
    };
}

pub const Irq = struct {
    vm: *const Vm,
    gsi: u32,
    accelerated: bool,
    fd: i32 = -1,
    resample_fd: i32 = -1,
    assigned: bool = false,
    active: bool = false,
    trigger: Trigger = .edge,
    high: bool = false,
    generation: u64 = 0,

    pub fn init(vm: *const Vm, gsi: u32, accelerated: bool) !Irq {
        var self = Irq{ .vm = vm, .gsi = gsi, .accelerated = accelerated };
        if (accelerated) {
            try require(vm, c.KVM_CAP_IRQFD);
            try require(vm, c.KVM_CAP_IRQFD_RESAMPLE);
            self.fd = try eventfd();
            errdefer abi.close(self.fd);
            self.resample_fd = try eventfd();
        }
        return self;
    }

    fn assign(self: *Irq) !void {
        var registration = std.mem.zeroes(c.kvm_irqfd);
        registration.fd = @intCast(self.fd);
        registration.gsi = self.gsi;
        registration.flags = @intCast(if (self.trigger == .level) c.KVM_IRQFD_FLAG_RESAMPLE else @as(c_int, 0));
        registration.resamplefd = if (self.trigger == .level) @intCast(self.resample_fd) else 0;
        try ioctl(self.vm, c.KVM_IRQFD, @intFromPtr(&registration), "irqfd assign", self.gsi);
        self.assigned = true;
        self.generation +%= 1;
    }

    fn unassign(self: *Irq) !void {
        if (!self.assigned) return;
        var registration = std.mem.zeroes(c.kvm_irqfd);
        registration.fd = @intCast(self.fd);
        registration.gsi = self.gsi;
        registration.flags = c.KVM_IRQFD_FLAG_DEASSIGN;
        // DEASSIGN synchronizes kernel injection and drops the resampler's
        // assertion source. IRQ_LINE(0) alone cannot clear that source.
        try ioctl(self.vm, c.KVM_IRQFD, @intFromPtr(&registration), "irqfd deassign", self.gsi);
        self.assigned = false;
        try drain(self.fd);
        try drain(self.resample_fd);
        self.high = false;
        self.generation +%= 1;
    }

    pub fn quiesce(self: *Irq) !void {
        if (self.accelerated) {
            try self.unassign();
        } else if (self.high) {
            try self.vm.setIrqLine(self.gsi, 0);
        }
        self.high = false;
        self.active = false;
    }

    pub fn reconcile(self: *Irq, ready: bool, status: u32) !void {
        if (!ready) return self.quiesce();
        const current = try policy(self.vm, self.gsi);
        const selected = try current.trigger();
        if (!self.active or selected != self.trigger) {
            try self.quiesce();
            self.trigger = selected;
            log.info("GSI{} trigger={s} PIC(level={},masked={}) IOAPIC(level={},masked={}) irqfd={} eventfd={} resamplefd={}", .{
                self.gsi,             @tagName(selected),    current.pic_level, current.pic_masked,
                current.ioapic_level, current.ioapic_masked, self.accelerated,  self.fd,
                self.resample_fd,
            });
            if (self.accelerated) try self.assign();
            self.active = true;
        }
        if (selected == .level) {
            if (status == 0 and self.high) {
                if (self.accelerated) {
                    // ACK can precede EOI. Drain the old generation only after
                    // synchronous deassignment, then arm a clean registration.
                    try self.unassign();
                    try self.assign();
                } else {
                    try self.vm.setIrqLine(self.gsi, 0);
                }
                self.high = false;
            } else if (status != 0 and !self.high) {
                if (self.accelerated) try wake(self.fd) else try self.vm.setIrqLine(self.gsi, 1);
                self.high = true;
            }
        }
    }

    pub fn notify(self: *Irq, status: u32) !void {
        try self.reconcile(true, status);
        if (self.trigger == .edge) {
            if (self.accelerated) {
                try wake(self.fd);
            } else {
                try self.vm.setIrqLine(self.gsi, 1);
                self.high = true;
                try self.vm.setIrqLine(self.gsi, 0);
                self.high = false;
            }
        }
    }

    pub fn resampled(self: *Irq, ready: bool, status: u32) !void {
        try drain(self.resample_fd);
        self.high = false;
        try self.reconcile(ready, status);
    }

    pub fn deinit(self: *Irq) !void {
        defer {
            if (self.fd >= 0) abi.close(self.fd);
            if (self.resample_fd >= 0) abi.close(self.resample_fd);
            self.fd = -1;
            self.resample_fd = -1;
        }
        try self.quiesce();
    }
};

test "IRQ policy follows the active chip and rejects incompatible active routing" {
    try std.testing.expectEqual(Trigger.edge, try (Policy{
        .pic_level = false,
        .pic_masked = false,
        .ioapic_level = true,
        .ioapic_masked = true,
    }).trigger());
    try std.testing.expectEqual(Trigger.level, try (Policy{
        .pic_level = false,
        .pic_masked = true,
        .ioapic_level = true,
        .ioapic_masked = false,
    }).trigger());
    try std.testing.expectEqual(Trigger.level, try (Policy{
        .pic_level = false,
        .pic_masked = true,
        .ioapic_level = true,
        .ioapic_masked = true,
    }).trigger());
    try std.testing.expectError(error.MixedActiveIRQTrigger, (Policy{
        .pic_level = false,
        .pic_masked = false,
        .ioapic_level = true,
        .ioapic_masked = false,
    }).trigger());
}
