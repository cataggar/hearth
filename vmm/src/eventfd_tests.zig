const std = @import("std");
const linux = std.os.linux;
const abi = @import("kvm/abi.zig");
const c = abi.c;
const Kvm = @import("kvm/system.zig");
const Vm = @import("kvm/vm.zig");
const Vcpu = @import("kvm/vcpu.zig");
const Memory = @import("memory.zig");
const Accelerator = @import("devices/virtio/accelerator.zig");
const seccomp = @import("seccomp.zig");
const Owner = @import("devices/virtio/owner.zig");
const Device = @import("devices/virtio/mmio.zig");
const virtio = @import("devices/virtio.zig");

const Fixture = struct {
    kvm: Kvm,
    vm: Vm,
    mem: Memory,
    vcpu: Vcpu,

    fn init(code: []const u8) !Fixture {
        const kvm = try Kvm.open();
        errdefer kvm.deinit();
        const vm = try kvm.createVm();
        errdefer vm.deinit();
        try vm.createIrqChip();
        const mem = try Memory.init(4096);
        errdefer mem.deinit();
        try vm.setMemoryRegion(0, 0, mem.mem);
        try vm.setTssAddr(0xfffbd000);
        try vm.setIdentityMapAddr(0xfffbc000);
        const vcpu = try vm.createVcpu(0, try kvm.getVcpuMmapSize());
        errdefer vcpu.deinit();
        var cpuid = try kvm.getSupportedCpuid();
        try vcpu.setCpuid(&cpuid);
        var sregs = try vcpu.getSregs();
        sregs.cs.base = 0;
        sregs.cs.selector = 0;
        try vcpu.setSregs(&sregs);
        var regs = std.mem.zeroes(c.kvm_regs);
        regs.rip = 0x100;
        regs.rsp = 0xf00;
        regs.rflags = 2;
        try vcpu.setRegs(&regs);
        @memcpy(mem.mem[0x100..][0..code.len], code);
        return .{ .kvm = kvm, .vm = vm, .mem = mem, .vcpu = vcpu };
    }

    fn deinit(self: *Fixture) void {
        self.vcpu.deinit();
        self.mem.deinit();
        self.vm.deinit();
        self.kvm.deinit();
    }
};

fn isolated(comptime scenario: fn () anyerror!void) !void {
    const pid: isize = @bitCast(linux.syscall0(.fork));
    if (pid < 0) return error.ForkFailed;
    if (pid == 0) {
        seccomp.install(false) catch linux.exit_group(91);
        scenario() catch |err| {
            std.debug.print("real enforced KVM scenario failed: {}\n", .{err});
            linux.exit_group(92);
        };
        linux.exit_group(0);
    }
    var status: i32 = 0;
    const waited: isize = @bitCast(linux.wait4(@intCast(pid), &status, 0, null));
    try std.testing.expectEqual(pid, waited);
    try std.testing.expectEqual(@as(i32, 0), status);
}

fn notifyScenario(value: u8, narrow: bool, remove: bool) !void {
    var code = [_]u8{
        0x66, 0xb8, value, 0, 0, 0, // eax
        0x66, 0xa3, 0x50, 0x80, // DWORD DS:8050
        0xb0, 0x7e, 0xe6, 0xe9,
    };
    if (narrow) {
        code[6] = 0x90; // word store instead of operand-size override
    }

    var fixture = try Fixture.init(&code);
    defer fixture.deinit();
    try Accelerator.require(&fixture.vm, c.KVM_CAP_IOEVENTFD);
    const fd = try Accelerator.eventfd();
    defer abi.close(fd);
    try Accelerator.kick(&fixture.vm, fd, 0x8050, 1, false);
    var assigned = true;
    defer if (assigned) Accelerator.kick(&fixture.vm, fd, 0x8050, 1, true) catch {};
    if (remove) {
        try Accelerator.kick(&fixture.vm, fd, 0x8050, 1, true);
        assigned = false;
    }
    const expected: u32 = if (value == 1 and !narrow and !remove) c.KVM_EXIT_IO else c.KVM_EXIT_MMIO;
    try std.testing.expectEqual(expected, try fixture.vcpu.run());
    var counter: u64 = 0;
    const received: isize = @bitCast(linux.read(fd, std.mem.asBytes(&counter).ptr, 8));
    if (expected == c.KVM_EXIT_IO) {
        try std.testing.expectEqual(@as(isize, 8), received);
        try std.testing.expectEqual(@as(u64, 1), counter);
    } else {
        try std.testing.expectEqual(-@as(isize, @backingInt(linux.E.AGAIN)), received);
        try std.testing.expectEqual(@as(u64, 0x8050), fixture.vcpu.getMmioData().phys_addr);
        try std.testing.expectEqual(@as(u32, if (narrow) 2 else 4), fixture.vcpu.getMmioData().len);
    }
}

test "real enforced owners start reset fence and join all four delivery modes" {
    try isolated(struct {
        fn write(owner: *Owner.Owner, offset: u64, value: u32) !void {
            var data: [8]u8 = @splat(0);
            std.mem.writeInt(u32, data[0..4], value, .little);
            try owner.write(offset, data, 4);
        }

        fn run() !void {
            var fixture = try Fixture.init(&.{0xf4});
            defer fixture.deinit();
            for ([_]Owner.Mode{ .C00, .C10, .C01, .C11 }) |mode| {
                var devices: [virtio.MAX_DEVICES]?Device = @splat(null);
                devices[0] = try Device.initVsock(0x8000, 5, 43, "/unused-owned-fixture");
                defer devices[0].?.deinit();
                var owners: Owner.Set = .{};
                try owners.start(&devices, 1, &fixture.vm, &fixture.mem, mode);
                defer owners.stop();
                const owner = &owners.owners[0];
                const magic = try owner.read(virtio.MMIO_MAGIC_VALUE, 4);
                try std.testing.expectEqual(virtio.MAGIC_VALUE, std.mem.readInt(u32, magic[0..4], .little));
                for (0..100) |iteration| {
                    try write(owner, virtio.MMIO_STATUS, virtio.STATUS_DRIVER_OK);
                    try write(owner, virtio.MMIO_QUEUE_SEL, 1);
                    try write(owner, virtio.MMIO_QUEUE_NUM, 8);
                    const ring_shift: u32 = if (iteration % 2 == 0) 0 else 0x300;
                    try write(owner, virtio.MMIO_QUEUE_DESC_LOW, 0x200 + ring_shift);
                    try write(owner, virtio.MMIO_QUEUE_DRIVER_LOW, 0x300 + ring_shift);
                    try write(owner, virtio.MMIO_QUEUE_DEVICE_LOW, 0x400 + ring_shift);
                    try write(owner, virtio.MMIO_QUEUE_READY, 1);
                    const accelerated = mode == .C10 or mode == .C11;
                    try std.testing.expectEqual(accelerated, owner.kicks[1].fd >= 0);
                    try std.testing.expectEqual(mode == .C01 or mode == .C11, owner.irq.assigned);
                    const generation = devices[0].?.queues[1].generation;
                    if (accelerated) try Accelerator.wake(owner.kicks[1].fd);
                    try write(owner, virtio.MMIO_QUEUE_READY, 0);
                    try std.testing.expectEqual(@as(i32, -1), owner.kicks[1].fd);
                    try std.testing.expect(devices[0].?.queues[1].generation != generation);
                    try owners.pause();
                    try std.testing.expect(!owner.irq.assigned);
                    try owners.unpause();
                    try write(owner, virtio.MMIO_STATUS, 0);
                }
                try owners.finish();
                try std.testing.expectEqual(@as(usize, 0), owners.count);
            }
        }
    }.run);
}

test "real enforced partial owner setup unwinds ten failures without fd leaks" {
    try isolated(struct {
        fn descriptors() usize {
            var count: usize = 0;
            for (0..128) |fd| {
                const rc: isize = @bitCast(linux.fcntl(@intCast(fd), 1, 0));
                if (rc >= 0) count += 1;
            }
            return count;
        }

        fn run() !void {
            var fixture = try Fixture.init(&.{0xf4});
            defer fixture.deinit();
            for ([_]Owner.Mode{ .C00, .C10, .C01, .C11 }) |mode| {
                for (0..10) |_| {
                    var devices: [virtio.MAX_DEVICES]?Device = @splat(null);
                    devices[0] = try Device.initVsock(0x8000, 5, 43, "/unused-owned-fixture");
                    devices[1] = try Device.initVsock(0x9000, 6, 44, "/unused-owned-fixture");
                    defer {
                        devices[1].?.deinit();
                        devices[0].?.deinit();
                    }
                    devices[1].?.queues[0].ready = true;
                    devices[1].?.queues[0].desc_addr = std.math.maxInt(u64) - 15;
                    const before = descriptors();
                    var owners: Owner.Set = .{};
                    try std.testing.expectError(error.InvalidRestoredQueue, owners.start(&devices, 2, &fixture.vm, &fixture.mem, mode));
                    try std.testing.expectEqual(@as(usize, 0), owners.count);
                    try std.testing.expectEqual(before, descriptors());
                }
            }
        }
    }.run);
}

test "real enforced late owner failure unwinds live kick and IRQ registrations" {
    try isolated(struct {
        fn descriptors() usize {
            var count: usize = 0;
            for (0..128) |fd| {
                const rc: isize = @bitCast(linux.fcntl(@intCast(fd), 1, 0));
                if (rc >= 0) count += 1;
            }
            return count;
        }

        fn run() !void {
            var action: linux.Sigaction = .{
                .handler = .{ .handler = &signalHandler },
                .mask = linux.sigemptyset(),
                .flags = 0,
            };
            if (linux.sigaction(linux.SIG.USR1, &action, null) != 0) return error.SignalHandlerFailed;
            var fixture = try Fixture.init(&.{0xf4});
            defer fixture.deinit();
            for ([_]Owner.Mode{ .C00, .C10, .C01, .C11 }) |mode| {
                for (0..10) |_| {
                    var devices: [virtio.MAX_DEVICES]?Device = @splat(null);
                    devices[0] = try Device.initVsock(0x8000, 5, 43, "/unused-owned-fixture");
                    devices[1] = try Device.initVsock(0x9000, 32, 44, "/unused-owned-fixture");
                    defer {
                        devices[1].?.deinit();
                        devices[0].?.deinit();
                    }
                    for (devices[0..2]) |*optional| {
                        const device = &optional.*.?;
                        device.status = virtio.STATUS_DRIVER_OK;
                        device.queues[1].size = 8;
                        device.queues[1].desc_addr = 0x200;
                        device.queues[1].avail_addr = 0x300;
                        device.queues[1].used_addr = 0x400;
                        device.queues[1].ready = true;
                    }
                    const before = descriptors();
                    var owners: Owner.Set = .{};
                    // GSI32 fails policy only after both owners start and the
                    // first one's live resources have reconciled successfully.
                    try std.testing.expectError(error.BackendOwnerFailed, owners.start(&devices, 2, &fixture.vm, &fixture.mem, mode));
                    try std.testing.expect(owners.failed.load(.acquire));
                    try std.testing.expectEqual(@as(usize, 0), owners.count);
                    try std.testing.expectEqual(before, descriptors());
                }
            }
        }
    }.run);
}

test "real pause quiescence completes pending MMIO without executing guest code" {
    try isolated(struct {
        fn run() !void {
            var fixture = try Fixture.init(&.{ 0x66, 0xa1, 0x50, 0x80, 0xb0, 0x7e, 0xe6, 0xe9 });
            defer fixture.deinit();
            try std.testing.expectEqual(@as(u32, c.KVM_EXIT_MMIO), try fixture.vcpu.run());
            var response: [8]u8 = @splat(0);
            std.mem.writeInt(u32, response[0..4], 0x12345678, .little);
            fixture.vcpu.kvm_run.unnamed_0.mmio.data = response;
            @atomicStore(u8, &fixture.vcpu.kvm_run.immediate_exit, 1, .release);
            try std.testing.expectError(error.Interrupted, fixture.vcpu.run());
            const state = try fixture.vcpu.getRegs();
            try std.testing.expectEqual(@as(u64, 0x104), state.rip);
            try std.testing.expectEqual(@as(u64, 0x12345678), state.rax);
        }
    }.run);
}

test "real KVM exact DWORD DATAMATCH bypasses userspace MMIO" {
    try isolated(struct {
        fn run() !void {
            try notifyScenario(1, false, false);
        }
    }.run);
}

test "real KVM unmatched queue and malformed word remain userspace MMIO" {
    try isolated(struct {
        fn run() !void {
            try notifyScenario(2, false, false);
            try notifyScenario(1, true, false);
        }
    }.run);
}

test "real KVM explicit ioeventfd deassignment restores MMIO" {
    try isolated(struct {
        fn run() !void {
            try notifyScenario(1, false, true);
        }
    }.run);
}

test "real KVM batched kicks aggregate counters and drain eight-byte values" {
    try isolated(struct {
        fn run() !void {
            const write = [_]u8{ 0x66, 0xb8, 1, 0, 0, 0, 0x66, 0xa3, 0x50, 0x80 };
            var code: [324]u8 = undefined;
            for (0..32) |index| @memcpy(code[index * 10 ..][0..10], &write);
            @memcpy(code[320..], &[_]u8{ 0xb0, 0x7e, 0xe6, 0xe9 });
            var fixture = try Fixture.init(&code);
            defer fixture.deinit();
            const fd = try Accelerator.eventfd();
            defer abi.close(fd);
            try Accelerator.kick(&fixture.vm, fd, 0x8050, 1, false);
            defer Accelerator.kick(&fixture.vm, fd, 0x8050, 1, true) catch {};
            try std.testing.expectEqual(@as(u32, c.KVM_EXIT_IO), try fixture.vcpu.run());
            var count: u64 = 0;
            try std.testing.expectEqual(@as(isize, 8), @as(isize, @bitCast(linux.read(fd, std.mem.asBytes(&count).ptr, 8))));
            try std.testing.expectEqual(@as(u64, 32), count);
            try Accelerator.wake(fd);
            try Accelerator.wake(fd);
            try Accelerator.drain(fd);
            try std.testing.expectEqual(-@as(isize, @backingInt(linux.E.AGAIN)), @as(isize, @bitCast(linux.read(fd, std.mem.asBytes(&count).ptr, 8))));
        }
    }.run);
}

const Run = struct {
    vcpu: *Vcpu,
    tid: std.atomic.Value(i32) = std.atomic.Value(i32).init(0),
    exit: u32 = 0,
    failed: bool = false,

    fn entry(self: *Run) void {
        self.tid.store(@intCast(linux.gettid()), .release);
        self.exit = self.vcpu.run() catch {
            self.failed = true;
            return;
        };
    }
};

fn signalHandler(_: linux.SIG) callconv(.c) void {}

fn expectSleeping(tid: i32) !void {
    var path: [96]u8 = undefined;
    const name = try std.fmt.bufPrint(path[0 .. path.len - 1], "/proc/self/task/{}/status", .{tid});
    path[name.len] = 0;
    const opened: isize = @bitCast(linux.open(@ptrCast(&path), .{ .ACCMODE = .RDONLY, .CLOEXEC = true }, 0));
    if (opened < 0) return error.ThreadStatusUnavailable;
    const fd: i32 = @intCast(opened);
    defer abi.close(fd);
    var status: [2048]u8 = undefined;
    const length: isize = @bitCast(linux.read(fd, &status, status.len));
    if (length <= 0) return error.ThreadStatusUnavailable;
    try std.testing.expect(std.mem.indexOf(u8, status[0..@intCast(length)], "State:\tS (") != null);
}

const IrqOptions = struct {
    level: bool = false,
    eoi_first: bool = false,
    accelerated: bool = true,
    masked: bool = false,
    reset_pending: bool = false,
};

fn irqScenario(options: IrqOptions) !void {
    const level = options.level;
    const eoi_first = options.eoi_first;
    const code = [_]u8{
        0xb0, 0x11, 0xe6, 0x20, // PIC ICW1
        0xb0, 0x20,                               0xe6, 0x21, // PIC vector base
        0xb0, 0x04,                               0xe6, 0x21,
        0xb0, 0x01,                               0xe6, 0x21,
        0xb0, if (options.masked) 0xff else 0xdf, 0xe6, 0x21,
        0xba, 0xd0, 0x04, 0xb0, if (level) 0x20 else 0, 0xee, // ELCR
        0xb0, 0x11, 0xe6, 0xe9, // ready barrier
        0xfb, 0xf4, 0xeb, 0xfd, // sti; hlt loop
    };
    var fixture = try Fixture.init(&code);
    defer fixture.deinit();
    const prologue = [_]u8{
        0xa1, 0x02, 0x07, 0xa3, 0x04, 0x07, // observe published used index
        0xff, 0x06, 0x00, 0x07, // count IRQ
    };
    const ack = [_]u8{ 0x66, 0xb8, 1, 0, 0, 0, 0x66, 0xa3, 0x64, 0x80 };
    const eoi = [_]u8{ 0xb0, 0x20, 0xe6, 0x20 };
    const finish = [_]u8{ 0xb0, 0xa5, 0xe6, 0xe9, 0xcf };
    @memcpy(fixture.mem.mem[0x300..][0..prologue.len], &prologue);
    if (eoi_first) {
        @memcpy(fixture.mem.mem[0x30a..][0..eoi.len], &eoi);
        @memcpy(fixture.mem.mem[0x30e..][0..ack.len], &ack);
    } else {
        @memcpy(fixture.mem.mem[0x30a..][0..ack.len], &ack);
        @memcpy(fixture.mem.mem[0x314..][0..eoi.len], &eoi);
    }
    @memcpy(fixture.mem.mem[0x318..][0..finish.len], &finish);
    std.mem.writeInt(u16, fixture.mem.mem[0x25 * 4 ..][0..2], 0x300, .little);
    try std.testing.expectEqual(@as(u32, c.KVM_EXIT_IO), try fixture.vcpu.run());
    var irq = try Accelerator.Irq.init(&fixture.vm, 5, options.accelerated);
    defer irq.deinit() catch {};
    try irq.reconcile(true, 0);
    try std.testing.expectEqual(if (level) Accelerator.Trigger.level else .edge, irq.trigger);
    var action = linux.Sigaction{
        .handler = .{ .handler = &signalHandler },
        .mask = linux.sigemptyset(),
        .flags = 0,
    };
    if (linux.sigaction(linux.SIG.USR1, &action, null) != 0) return error.SignalHandlerFailed;
    var run = Run{ .vcpu = &fixture.vcpu };
    const thread = try std.Thread.spawn(.{}, Run.entry, .{&run});
    var joined = false;
    defer if (!joined) {
        @atomicStore(u8, &fixture.vcpu.kvm_run.immediate_exit, 1, .release);
        const tid = run.tid.load(.acquire);
        if (tid > 0) _ = linux.tkill(tid, linux.SIG.USR1);
        thread.join();
    };
    // This host-only wait never injects guest IRQs; no PIT or heartbeat exists.
    _ = linux.nanosleep(&.{ .sec = 1, .nsec = 0 }, null);
    try expectSleeping(run.tid.load(.acquire));
    const index: *u16 = @ptrCast(@alignCast(fixture.mem.mem[0x702..].ptr));
    @atomicStore(u16, index, 1, .release);
    try irq.notify(1);
    var expected_index: u16 = 1;
    if (options.masked) {
        var pending = false;
        for (0..1000) |_| {
            const pic = try fixture.vm.getIrqChip(c.KVM_IRQCHIP_PIC_MASTER);
            if (pic[c.HEARTH_IRQCHIP_DATA_OFFSET + c.HEARTH_PIC_IRR_OFFSET] & 0x20 != 0) {
                pending = true;
                break;
            }
            _ = linux.nanosleep(&.{ .sec = 0, .nsec = 1_000_000 }, null);
        }
        try std.testing.expect(pending);
        try expectSleeping(run.tid.load(.acquire));
        try std.testing.expectEqual(@as(u16, 0), std.mem.readInt(u16, fixture.mem.mem[0x700..][0..2], .little));
        if (options.reset_pending) {
            const generation = irq.generation;
            try irq.quiesce();
            const pic = try fixture.vm.getIrqChip(c.KVM_IRQCHIP_PIC_MASTER);
            try std.testing.expectEqual(@as(u8, 0), pic[c.HEARTH_IRQCHIP_DATA_OFFSET + c.HEARTH_PIC_IRR_OFFSET] & 0x20);
            if (options.accelerated) {
                try std.testing.expect(!irq.assigned);
                try std.testing.expect(irq.generation != generation);
                for ([_]i32{ irq.fd, irq.resample_fd }) |fd| {
                    var counter: u64 = 0;
                    const read: isize = @bitCast(linux.read(fd, std.mem.asBytes(&counter).ptr, 8));
                    try std.testing.expectEqual(-@as(isize, @backingInt(linux.E.AGAIN)), read);
                }
            }
            try irq.reconcile(true, 0);
        }
        var chip = try fixture.vm.getIrqChip(c.KVM_IRQCHIP_PIC_MASTER);
        chip[c.HEARTH_IRQCHIP_DATA_OFFSET + c.HEARTH_PIC_IMR_OFFSET] &= ~@as(u8, 0x20);
        try fixture.vm.setIrqChip(&chip);
        if (options.reset_pending) {
            _ = linux.nanosleep(&.{ .sec = 0, .nsec = 100_000_000 }, null);
            try expectSleeping(run.tid.load(.acquire));
            try std.testing.expectEqual(@as(u16, 0), std.mem.readInt(u16, fixture.mem.mem[0x700..][0..2], .little));
            expected_index = 2;
            @atomicStore(u16, index, expected_index, .release);
            try irq.notify(1);
        }
    }
    thread.join();
    joined = true;
    try std.testing.expect(!run.failed);
    try std.testing.expectEqual(@as(u32, c.KVM_EXIT_MMIO), run.exit);
    try std.testing.expectEqual(@as(u64, 0x8064), fixture.vcpu.getMmioData().phys_addr);
    try std.testing.expectEqual(expected_index, std.mem.readInt(u16, fixture.mem.mem[0x704..][0..2], .little));
    if (level and options.accelerated) try irq.resampled(true, 1);
    try irq.reconcile(true, 0);
    try std.testing.expectEqual(@as(u32, c.KVM_EXIT_IO), try fixture.vcpu.run());
    if (level and options.accelerated) try irq.resampled(true, 0);
    const pic = try fixture.vm.getIrqChip(c.KVM_IRQCHIP_PIC_MASTER);
    const irr = pic[c.HEARTH_IRQCHIP_DATA_OFFSET + c.HEARTH_PIC_IRR_OFFSET];
    try std.testing.expectEqual(@as(u8, 0), irr & 0x20);
    try std.testing.expectEqual(@as(u16, 1), std.mem.readInt(u16, fixture.mem.mem[0x700..][0..2], .little));
    try irq.quiesce();
}

test "real KVM irqfd wakes timer-free HLT with used-before-IRQ and edge ACK" {
    try isolated(struct {
        fn run() !void {
            try irqScenario(.{});
        }
    }.run);
}

test "real KVM level irqfd resamples and ACK-before-EOI really deasserts" {
    try isolated(struct {
        fn run() !void {
            try irqScenario(.{ .level = true });
        }

        test "real KVM level EOI-before-ACK reasserts pending work without a stale storm" {
            try isolated(struct {
                fn run() !void {
                    try irqScenario(.{ .level = true, .eoi_first = true });
                }

                test "real KVM masked edge and level IRQs wake only after unmask for line and irqfd" {
                    try isolated(struct {
                        fn run() !void {
                            for ([_]bool{ false, true }) |accelerated| {
                                for ([_]bool{ false, true }) |level| {
                                    try irqScenario(.{ .accelerated = accelerated, .level = level, .masked = true });
                                }
                            }
                        }
                    }.run);
                }

                test "real KVM masked level reset drains stale IRQ epoch before fresh publication" {
                    try isolated(struct {
                        fn run() !void {
                            for ([_]bool{ false, true }) |accelerated| {
                                try irqScenario(.{ .accelerated = accelerated, .level = true, .masked = true, .reset_pending = true });
                            }
                        }
                    }.run);
                }
            }.run);
        }
    }.run);
}
