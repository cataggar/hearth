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
const Main = @import("main.zig");
const Serial = @import("devices/serial.zig");

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
        seccomp.install(false, .reactor) catch linux.exit_group(91);
        scenario() catch |err| {
            std.debug.print("real enforced KVM scenario failed: {}\n", .{err});
            linux.exit_group(92);
        };
        linux.exit_group(0);
    }
    var status: i32 = 0;
    const waited: isize = @bitCast(linux.wait4(@intCast(pid), &status, 0, null));
    std.debug.print("enforced_case child_pid={} waited={} status={}\n", .{ pid, waited, status });
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
                try owners.start(&devices, 1, &fixture.vm, &fixture.mem, mode, &fixture.vcpu);
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
                    try std.testing.expectError(error.InvalidRestoredQueue, owners.start(&devices, 2, &fixture.vm, &fixture.mem, mode, &fixture.vcpu));
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
                    try std.testing.expectError(error.BackendOwnerFailed, owners.start(&devices, 2, &fixture.vm, &fixture.mem, mode, &fixture.vcpu));
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
    done: std.atomic.Value(bool) = std.atomic.Value(bool).init(false),
    exit: u32 = 0,
    failed: bool = false,

    fn entry(self: *Run) void {
        defer self.done.store(true, .release);
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
    ioapic: bool = false,
    post_iret: bool = false,
    mask_after_active: bool = false,
    inactive_ioapic_level: bool = false,
};

test "real KVM dormant queue pause attributes deassignment without dropping fences" {
    try isolated(struct {
        var mutex: @import("sync.zig").Mutex = .{};
        var elapsed: u64 = 0;
        var count: usize = 0;

        fn now() !u64 {
            var stamp: linux.timespec = undefined;
            if (linux.clock_gettime(.MONOTONIC, &stamp) != 0) return error.ClockFailed;
            return @as(u64, @intCast(stamp.sec)) * 1_000_000_000 + @as(u64, @intCast(stamp.nsec));
        }

        fn observe(event: Accelerator.TestIoctlTiming) void {
            mutex.lock();
            defer mutex.unlock();
            elapsed += event.elapsed_ns;
            count += 1;
            std.debug.print("pause_ioctl operation={s} request=0x{x} identity=0x{x} ns={}\n", .{
                event.operation, event.request, event.identity, event.elapsed_ns,
            });
        }

        fn run() !void {
            for ([_]Owner.Mode{ .C00, .C10, .C01, .C11 }) |mode| {
                for (0..3) |sample| {
                    var fixture = try Fixture.init(&.{ 0xfa, 0xf4 });
                    defer fixture.deinit();
                    var devices: [virtio.MAX_DEVICES]?Device = @splat(null);
                    for (0..3) |index| {
                        devices[index] = try Device.initVsock(0x8000 + index * 0x1000, @intCast(5 + index), @intCast(43 + index), "/unused-owned-fixture");
                        const device = &devices[index].?;
                        device.status = virtio.STATUS_DRIVER_OK;
                        for (&device.queues, 0..) |*queue, queue_index| {
                            const ring = 0x200 + (index * 3 + queue_index) * 0x100;
                            queue.size = 8;
                            queue.desc_addr = ring;
                            queue.avail_addr = ring + 0x80;
                            queue.used_addr = ring + 0xa0;
                            queue.ready = true;
                        }
                    }
                    defer for (devices[0..3]) |*device| device.*.?.deinit();
                    var owners: Owner.Set = .{};
                    try owners.start(&devices, 3, &fixture.vm, &fixture.mem, mode, &fixture.vcpu);
                    defer owners.stop();
                    elapsed = 0;
                    count = 0;
                    Accelerator.test_ioctl_observer = &observe;
                    defer Accelerator.test_ioctl_observer = null;
                    const started = try now();
                    try owners.pause();
                    const total = try now() - started;
                    Accelerator.test_ioctl_observer = null;
                    const expected: usize = (if (mode == .C10 or mode == .C11) @as(usize, 9) else 0) +
                        (if (mode == .C01 or mode == .C11) @as(usize, 3) else 0);
                    try std.testing.expectEqual(expected, count);
                    try std.testing.expect(elapsed <= total);
                    for (owners.owners[0..owners.count]) |*owner| {
                        try std.testing.expect(!owner.irq.assigned);
                        for (owner.kicks) |kick| try std.testing.expectEqual(@as(i32, -1), kick.fd);
                    }
                    std.debug.print("pause_diagnostic mode={s} sample={} queues=9 gsis=3 owner_ns={} deassign_ns={} calls={}\n", .{
                        @tagName(mode), sample, total, elapsed, count,
                    });
                    try owners.unpause();
                    try owners.finish();
                }
            }
        }
    }.run);
}

fn expectKvmHalt(tid: i32) !void {
    try expectSleeping(tid);
    var path: [96]u8 = undefined;
    const name = try std.fmt.bufPrint(path[0 .. path.len - 1], "/proc/self/task/{}/wchan", .{tid});
    path[name.len] = 0;
    const opened: isize = @bitCast(linux.open(@ptrCast(&path), .{ .ACCMODE = .RDONLY, .CLOEXEC = true }, 0));
    if (opened < 0) return error.KernelWaitUnavailable;
    defer abi.close(@intCast(opened));
    var data: [128]u8 = undefined;
    const length: isize = @bitCast(linux.read(@intCast(opened), &data, data.len));
    if (length <= 0) return error.KernelWaitUnavailable;
    try std.testing.expect(std.mem.indexOf(u8, data[0..@intCast(length)], "kvm_vcpu_block") != null);
}

fn afterIret(fixture: *Fixture, irq: *Accelerator.Irq, options: IrqOptions, expected_index: u16) !void {
    for (0..2) |round| {
        @atomicStore(u8, &fixture.vcpu.kvm_run.immediate_exit, 0, .release);
        var returning = Run{ .vcpu = &fixture.vcpu };
        const thread = try std.Thread.spawn(.{}, Run.entry, .{&returning});
        var joined = false;
        defer if (!joined) {
            @atomicStore(u8, &fixture.vcpu.kvm_run.immediate_exit, 1, .release);
            const tid = returning.tid.load(.acquire);
            if (tid > 0) _ = linux.tkill(tid, linux.SIG.USR1);
            thread.join();
        };
        _ = linux.nanosleep(&.{ .sec = 0, .nsec = 200_000_000 }, null);
        if (!returning.done.load(.acquire)) {
            try expectKvmHalt(returning.tid.load(.acquire));
            try std.testing.expectEqual(@as(u16, @intCast(round + 1)), std.mem.readInt(u16, fixture.mem.mem[0x700..][0..2], .little));
            try std.testing.expect(!try irqPending(&fixture.vm, options.ioapic));
            std.debug.print("post_iret halted tid={} irqs={} ioapic={} irqfd={} reset={}\n", .{
                returning.tid.load(.acquire), round + 1, options.ioapic, options.accelerated, options.reset_pending,
            });
            return;
        }
        thread.join();
        joined = true;
        const count = std.mem.readInt(u16, fixture.mem.mem[0x700..][0..2], .little);
        std.debug.print("post_iret queued IRQ: ioapic={} irqfd={} level={} eoi_first={} round={} count={} exit={}\n", .{
            options.ioapic, options.accelerated, options.level, options.eoi_first, round, count, returning.exit,
        });
        // One level IRQ may already be in LAPIC/PIC before transport ACK.
        try std.testing.expect(options.level and options.eoi_first and round == 0);
        try std.testing.expect(!returning.failed);
        try std.testing.expectEqual(@as(u16, 2), count);
        try std.testing.expectEqual(@as(u32, c.KVM_EXIT_MMIO), returning.exit);
        try std.testing.expectEqual(@as(u64, 0x8064), fixture.vcpu.getMmioData().phys_addr);
        try std.testing.expectEqual(expected_index, std.mem.readInt(u16, fixture.mem.mem[0x704..][0..2], .little));
        try irq.reconcile(true, 0);
        try std.testing.expectEqual(@as(u32, c.KVM_EXIT_IO), try fixture.vcpu.run());
        if (options.accelerated) try irq.resampled(true, 0);
    }
    return error.StaleInterruptStorm;
}

fn irqPending(vm: *Vm, ioapic: bool) !bool {
    const chip = try vm.getIrqChip(if (ioapic) c.KVM_IRQCHIP_IOAPIC else c.KVM_IRQCHIP_PIC_MASTER);
    if (ioapic) {
        const offset = c.HEARTH_IRQCHIP_DATA_OFFSET + c.HEARTH_IOAPIC_IRR_OFFSET;
        return std.mem.readInt(u32, chip[offset..][0..4], .little) & 0x20 != 0;
    }
    return chip[c.HEARTH_IRQCHIP_DATA_OFFSET + c.HEARTH_PIC_IRR_OFFSET] & 0x20 != 0;
}

fn irqScenario(options: IrqOptions) !void {
    const level = options.level;
    const eoi_first = options.eoi_first;
    const code = [_]u8{
        0xb0, 0x11, 0xe6, 0x20, // PIC ICW1
        0xb0, 0x20,                                                                                  0xe6, 0x21, // PIC vector base
        0xb0, 0x04,                                                                                  0xe6, 0x21,
        0xb0, 0x01,                                                                                  0xe6, 0x21,
        0xb0, if ((options.masked and !options.mask_after_active) or options.ioapic) 0xff else 0xdf, 0xe6, 0x21,
        0xba, 0xd0, 0x04, 0xb0, if (level and !options.ioapic) 0x20 else 0, 0xee, // ELCR
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
    const pic_eoi = [_]u8{ 0xb0, 0x20, 0xe6, 0x20 };
    const apic_eoi = [_]u8{ 0x67, 0x66, 0xc7, 0x05, 0xb0, 0, 0xe0, 0xfe, 0, 0, 0, 0 };
    const eoi: []const u8 = if (options.ioapic) &apic_eoi else &pic_eoi;
    const finish = [_]u8{ 0xb0, 0xa5, 0xe6, 0xe9, 0xcf };
    @memcpy(fixture.mem.mem[0x300..][0..prologue.len], &prologue);
    var address: usize = 0x300 + prologue.len;
    const operations = if (eoi_first) [_][]const u8{ eoi, &ack } else [_][]const u8{ &ack, eoi };
    for (operations) |instructions| {
        @memcpy(fixture.mem.mem[address..][0..instructions.len], instructions);
        address += instructions.len;
    }
    @memcpy(fixture.mem.mem[address..][0..finish.len], &finish);
    std.mem.writeInt(u16, fixture.mem.mem[0x25 * 4 ..][0..2], 0x300, .little);
    try std.testing.expectEqual(@as(u32, c.KVM_EXIT_IO), try fixture.vcpu.run());
    if (options.ioapic) {
        var slave = try fixture.vm.getIrqChip(c.KVM_IRQCHIP_PIC_SLAVE);
        slave[c.HEARTH_IRQCHIP_DATA_OFFSET + c.HEARTH_PIC_IMR_OFFSET] = 0xff;
        try fixture.vm.setIrqChip(&slave);
        var sregs = try fixture.vcpu.getSregs();
        sregs.apic_base = 0xfee00900;
        // The 16-bit microguest uses a 32-bit address for LAPIC EOI.
        sregs.ds.limit = 0xffff_ffff;
        sregs.ds.g = 1;
        try fixture.vcpu.setSregs(&sregs);
        var lapic = try fixture.vcpu.getLapic();
        const registers = std.mem.asBytes(&lapic);
        std.mem.writeInt(u32, registers[0xf0..][0..4], 0x1ff, .little);
        std.mem.writeInt(u32, registers[0x80..][0..4], 0, .little);
        try fixture.vcpu.setLapic(&lapic);
        var chip = try fixture.vm.getIrqChip(c.KVM_IRQCHIP_IOAPIC);
        const offset = c.HEARTH_IRQCHIP_DATA_OFFSET + c.HEARTH_IOAPIC_REDIR_OFFSET + 5 * 8;
        const entry: u64 = 0x25 | (if (level) @as(u64, 1) << 15 else 0) |
            (if (options.masked and !options.mask_after_active) @as(u64, 1) << 16 else 0);
        std.mem.writeInt(u64, chip[offset..][0..8], entry, .little);
        try fixture.vm.setIrqChip(&chip);
    } else if (options.inactive_ioapic_level) {
        var chip = try fixture.vm.getIrqChip(c.KVM_IRQCHIP_IOAPIC);
        const offset = c.HEARTH_IRQCHIP_DATA_OFFSET + c.HEARTH_IOAPIC_REDIR_OFFSET + 5 * 8;
        std.mem.writeInt(u64, chip[offset..][0..8], 0x25 | (@as(u64, 1) << 15) | (@as(u64, 1) << 16), .little);
        try fixture.vm.setIrqChip(&chip);
    }
    var irq = try Accelerator.Irq.init(&fixture.vm, 5, options.accelerated);
    defer irq.deinit() catch {};
    try irq.reconcile(true, 0);
    if (!options.ioapic or !options.masked or options.mask_after_active)
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
    const established_generation = irq.generation;
    if (options.mask_after_active) {
        try expectKvmHalt(run.tid.load(.acquire));
        var chip = try fixture.vm.getIrqChip(if (options.ioapic) c.KVM_IRQCHIP_IOAPIC else c.KVM_IRQCHIP_PIC_MASTER);
        if (options.ioapic) {
            const offset = c.HEARTH_IRQCHIP_DATA_OFFSET + c.HEARTH_IOAPIC_REDIR_OFFSET + 5 * 8;
            const entry = std.mem.readInt(u64, chip[offset..][0..8], .little);
            std.mem.writeInt(u64, chip[offset..][0..8], entry | (@as(u64, 1) << 16), .little);
        } else {
            chip[c.HEARTH_IRQCHIP_DATA_OFFSET + c.HEARTH_PIC_IMR_OFFSET] |= 0x20;
        }
        try fixture.vm.setIrqChip(&chip);
    }
    const index: *u16 = @ptrCast(@alignCast(fixture.mem.mem[0x702..].ptr));
    @atomicStore(u16, index, 1, .release);
    try irq.notify(1);
    if (options.mask_after_active) {
        try std.testing.expectEqual(if (level) Accelerator.Trigger.level else .edge, irq.trigger);
        try std.testing.expectEqual(established_generation, irq.generation);
    }
    var expected_index: u16 = 1;
    if (options.masked) {
        var pending = false;
        for (0..1000) |_| {
            if (try irqPending(&fixture.vm, options.ioapic)) {
                pending = true;
                break;
            }
            _ = linux.nanosleep(&.{ .sec = 0, .nsec = 1_000_000 }, null);
        }
        if (!pending) {
            std.debug.print("masked IRQ lost: ioapic={} irqfd={} trigger={s} reset={} used={}\n", .{
                options.ioapic, options.accelerated, @tagName(irq.trigger), options.reset_pending, expected_index,
            });
            return error.MaskedPendingInterruptLost;
        }
        try expectSleeping(run.tid.load(.acquire));
        try std.testing.expectEqual(@as(u16, 0), std.mem.readInt(u16, fixture.mem.mem[0x700..][0..2], .little));
        if (options.reset_pending) {
            const generation = irq.generation;
            try irq.quiesce();
            try std.testing.expect(!try irqPending(&fixture.vm, options.ioapic));
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
        var chip = try fixture.vm.getIrqChip(if (options.ioapic) c.KVM_IRQCHIP_IOAPIC else c.KVM_IRQCHIP_PIC_MASTER);
        if (options.ioapic) {
            const offset = c.HEARTH_IRQCHIP_DATA_OFFSET + c.HEARTH_IOAPIC_REDIR_OFFSET + 5 * 8;
            const entry = std.mem.readInt(u64, chip[offset..][0..8], .little);
            std.mem.writeInt(u64, chip[offset..][0..8], entry & ~(@as(u64, 1) << 16), .little);
        } else {
            chip[c.HEARTH_IRQCHIP_DATA_OFFSET + c.HEARTH_PIC_IMR_OFFSET] &= ~@as(u8, 0x20);
        }
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
    for (0..1000) |_| {
        if (run.done.load(.acquire)) break;
        _ = linux.nanosleep(&.{ .sec = 0, .nsec = 1_000_000 }, null);
    }
    try std.testing.expect(run.done.load(.acquire));
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
    try std.testing.expect(!try irqPending(&fixture.vm, options.ioapic));
    try std.testing.expectEqual(@as(u16, 1), std.mem.readInt(u16, fixture.mem.mem[0x700..][0..2], .little));
    if (options.post_iret) try afterIret(&fixture, &irq, options, expected_index);
    try irq.quiesce();
}

test "real KVM line and irqfd return through IRET to timer-free HLT without stale storms" {
    try isolated(struct {
        fn run() !void {
            for ([_]bool{ false, true }) |ioapic| {
                for ([_]bool{ false, true }) |accelerated| {
                    for ([_]bool{ false, true }) |level|
                        try irqScenario(.{ .accelerated = accelerated, .level = level, .ioapic = ioapic, .eoi_first = true, .post_iret = true });
                }
            }
        }
    }.run);
}

test "real KVM established trigger survives both masks and unmasks without another notify" {
    try isolated(struct {
        fn reconfigure(accelerated: bool) !void {
            var fixture = try Fixture.init(&.{0xf4});
            defer fixture.deinit();
            var pic = try fixture.vm.getIrqChip(c.KVM_IRQCHIP_PIC_MASTER);
            pic[c.HEARTH_IRQCHIP_DATA_OFFSET + c.HEARTH_PIC_IMR_OFFSET] |= 0x20;
            pic[c.HEARTH_IRQCHIP_DATA_OFFSET + c.HEARTH_PIC_ELCR_OFFSET] &= ~@as(u8, 0x20);
            try fixture.vm.setIrqChip(&pic);
            var chip = try fixture.vm.getIrqChip(c.KVM_IRQCHIP_IOAPIC);
            const offset = c.HEARTH_IRQCHIP_DATA_OFFSET + c.HEARTH_IOAPIC_REDIR_OFFSET + 5 * 8;
            std.mem.writeInt(u64, chip[offset..][0..8], 0x25 | (@as(u64, 1) << 15) | (@as(u64, 1) << 16), .little);
            try fixture.vm.setIrqChip(&chip);
            var irq = try Accelerator.Irq.init(&fixture.vm, 5, accelerated);
            defer irq.deinit() catch {};
            try irq.reconcile(true, 0);
            try std.testing.expectEqual(Accelerator.Trigger.level, irq.trigger);
            std.mem.writeInt(u64, chip[offset..][0..8], 0x25 | (@as(u64, 1) << 16), .little);
            try fixture.vm.setIrqChip(&chip);
            try irq.reconcile(true, 0);
            try std.testing.expectEqual(Accelerator.Trigger.edge, irq.trigger);
        }

        fn run() !void {
            for ([_]Owner.Mode{ .C00, .C10, .C01, .C11 }) |mode| {
                const accelerated = mode == .C01 or mode == .C11;
                std.debug.print("mask_transition mode={s} IOAPIC-level/PIC-edge paths\n", .{@tagName(mode)});
                try irqScenario(.{
                    .accelerated = accelerated,
                    .level = true,
                    .ioapic = true,
                    .masked = true,
                    .mask_after_active = true,
                    .eoi_first = true,
                    .post_iret = true,
                });
                try reconfigure(accelerated);
                try irqScenario(.{
                    .accelerated = accelerated,
                    .masked = true,
                    .mask_after_active = true,
                    .inactive_ioapic_level = true,
                    .post_iret = true,
                });
            }
        }
    }.run);
}

const FatalStage = enum { before_run, after_clear, while_paused, resume_clear };
const FatalCase = struct {
    var stage: FatalStage = undefined;
    var hook_calls: usize = 0;
    var driver: PauseDriver = undefined;
    var driver_thread: ?std.Thread = null;

    const PauseDriver = struct {
        runtime: *Main.VmRuntime,
        owner: *Owner.Owner,
        resume_request: bool,
        failed: bool = false,

        fn entry(self: *PauseDriver) void {
            self.runtime.mutex.lock();
            while (!self.runtime.ack_paused.load(.acquire) and !self.runtime.exited.load(.acquire))
                self.runtime.condition.wait(&self.runtime.mutex);
            if (self.resume_request) {
                self.runtime.paused.store(false, .seq_cst);
                self.runtime.condition.broadcast();
                self.runtime.mutex.unlock();
            } else {
                self.runtime.mutex.unlock();
                self.owner.failForTest() catch |err| {
                    self.failed = err == error.BackendOwnerFailed;
                    return;
                };
            }
        }
    };

    fn fail(owners: *Owner.Set) !void {
        hook_calls += 1;
        try std.testing.expectError(error.BackendOwnerFailed, owners.owners[0].failForTest());
        try std.testing.expect(owners.failed.load(.acquire));
    }

    fn beforeRun(owners: *Owner.Set, vcpu: *Vcpu, runtime: ?*Main.VmRuntime) !void {
        Main.test_before_run = null;
        const received = Main.test_kicks_received.load(.acquire);
        try fail(owners);
        for (0..1000) |_| {
            if (Main.test_kicks_received.load(.acquire) != received) break;
            _ = linux.nanosleep(&.{ .sec = 0, .nsec = 1_000_000 }, null);
        }
        try std.testing.expect(Main.test_kicks_received.load(.acquire) != received);
        try std.testing.expectEqual(@as(u8, 1), @atomicLoad(u8, &vcpu.kvm_run.immediate_exit, .acquire));
        std.debug.print("fatal_exact_before_entry API={} signal already consumed; immediate_exit=1\n", .{runtime != null});
    }

    fn afterClear(owners: *Owner.Set) !void {
        Owner.test_after_clear = null;
        try fail(owners);
    }

    fn ownersReady(owners: *Owner.Set, runtime: ?*Main.VmRuntime) !void {
        if (stage != .while_paused and stage != .resume_clear) return;
        driver = .{ .runtime = runtime.?, .owner = &owners.owners[0], .resume_request = stage == .resume_clear };
        driver_thread = try std.Thread.spawn(.{}, PauseDriver.entry, .{&driver});
    }

    fn run(selected: FatalStage) !void {
        stage = selected;
        for ([_]Owner.Mode{ .C00, .C10, .C01, .C11 }) |mode| {
            for ([_]bool{ false, true }) |api_path| {
                if (!api_path and (stage == .while_paused or stage == .resume_clear)) continue;
                var fixture = try Fixture.init(&.{ 0xfb, 0xf4 });
                defer fixture.deinit();
                var devices: [virtio.MAX_DEVICES]?Device = @splat(null);
                devices[0] = try Device.initVsock(0x8000, 5, 43, "/unused-owned-fixture");
                devices[0].?.status = virtio.STATUS_DRIVER_OK;
                defer devices[0].?.deinit();
                var serial = Serial.init(2);
                var runtime: Main.VmRuntime = .{
                    .vcpu = &fixture.vcpu,
                    .vm = &fixture.vm,
                    .mem = &fixture.mem,
                    .serial = &serial,
                    .devices = &devices,
                    .device_count = 1,
                    .snap_opts = .{},
                };
                if (stage == .while_paused or stage == .resume_clear) runtime.paused.store(true, .seq_cst);
                if (stage != .before_run)
                    @atomicStore(u8, &fixture.vcpu.kvm_run.immediate_exit, 1, .seq_cst);
                hook_calls = 0;
                driver_thread = null;
                Main.test_before_run = if (stage == .before_run) &beforeRun else null;
                Main.test_owners_ready = &ownersReady;
                Owner.test_after_clear = if (stage == .after_clear or stage == .resume_clear) &afterClear else null;
                defer {
                    Main.test_before_run = null;
                    Main.test_owners_ready = null;
                    Owner.test_after_clear = null;
                    if (driver_thread) |thread| thread.join();
                }
                try std.testing.expectError(error.BackendOwnerFailed, Main.testRunLoop(
                    &fixture.vcpu,
                    &serial,
                    &fixture.vm,
                    &fixture.mem,
                    &devices,
                    mode,
                    if (api_path) &runtime else null,
                ));
                if (driver_thread) |thread| {
                    thread.join();
                    driver_thread = null;
                    if (stage == .while_paused) try std.testing.expect(driver.failed);
                }
                if (stage != .while_paused) try std.testing.expectEqual(@as(usize, 1), hook_calls);
                if (api_path) {
                    try std.testing.expect(runtime.run_failed.load(.acquire));
                    try std.testing.expect(runtime.exited.load(.acquire));
                }
                const regs = try fixture.vcpu.getRegs();
                try std.testing.expectEqual(@as(u64, 0x100), regs.rip);
                std.debug.print("fatal_joined mode={s} API={} stage={s} RIP=0x100\n", .{ @tagName(mode), api_path, @tagName(stage) });
            }
        }
    }
};

test "real enforced CLI and API owner failure exactly before KVM entry cannot sleep" {
    try isolated(struct {
        fn run() !void {
            try FatalCase.run(.before_run);
        }
    }.run);
}

test "real enforced CLI and API fatal publication survives immediate-exit clearing" {
    try isolated(struct {
        fn run() !void {
            try FatalCase.run(.after_clear);
        }
    }.run);
}

test "real enforced API owner failure wakes pause and survives resume admission" {
    try isolated(struct {
        fn run() !void {
            try FatalCase.run(.while_paused);
            try FatalCase.run(.resume_clear);
        }
    }.run);
}
test "real KVM masked level reset remains quiet after IRET for both interrupt chips" {
    try isolated(struct {
        fn run() !void {
            for ([_]bool{ false, true }) |ioapic| {
                for ([_]bool{ false, true }) |accelerated| {
                    for ([_]bool{ false, true }) |reset_pending|
                        try irqScenario(.{ .accelerated = accelerated, .level = true, .ioapic = ioapic, .masked = true, .reset_pending = reset_pending, .eoi_first = true, .post_iret = true });
                }
            }
        }
    }.run);
}

test "real KVM IOAPIC edge and level routes deliver with both PICs masked" {
    try isolated(struct {
        fn run() !void {
            for ([_]bool{ false, true }) |accelerated| {
                for ([_]bool{ false, true }) |level|
                    try irqScenario(.{ .accelerated = accelerated, .level = level, .ioapic = true });
            }
        }
    }.run);
}

test "real KVM masked IOAPIC level holds pending work and fences reset epochs" {
    try isolated(struct {
        fn run() !void {
            for ([_]bool{ false, true }) |accelerated| {
                for ([_]bool{ false, true }) |reset_pending|
                    try irqScenario(.{ .accelerated = accelerated, .level = true, .ioapic = true, .masked = true, .reset_pending = reset_pending });
            }
        }
    }.run);
}

test "real KVM IOAPIC EOI before transport ACK preserves completion for line and irqfd" {
    try isolated(struct {
        fn run() !void {
            for ([_]bool{ false, true }) |accelerated| {
                for ([_]bool{ false, true }) |level|
                    try irqScenario(.{ .accelerated = accelerated, .level = level, .ioapic = true, .eoi_first = true });
            }
        }
    }.run);
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
