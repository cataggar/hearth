const std = @import("std");
const linux = std.os.linux;
const Worker = @import("blk_worker.zig");
const Kvm = @import("../../kvm/system.zig");
const Memory = @import("../../memory.zig");
const abi = @import("../../kvm/abi.zig");

const Gate = struct {
    ready: std.atomic.Value(u32) = .init(0),
    entered: std.atomic.Value(u32) = .init(0),
    tid: i32,
    blocked: std.atomic.Value(bool) = .init(false),

    fn write(context: ?*anyopaque, _: i32, bytes: []const u8, _: u64) isize {
        const self: *Gate = @ptrCast(@alignCast(context.?));
        self.entered.store(1, .seq_cst);
        Worker.wakeState(&self.entered);
        while (self.ready.load(.seq_cst) == 0) Worker.waitState(&self.ready, 0);
        return @intCast(bytes.len);
    }

    fn release(self: *Gate) void {
        self.ready.store(1, .seq_cst);
        Worker.wakeState(&self.ready);
    }

    fn nanos() u64 {
        var ts: linux.timespec = undefined;
        _ = linux.syscall2(.clock_gettime, 1, @intFromPtr(&ts));
        return @as(u64, @intCast(ts.sec)) * 1_000_000_000 + @as(u64, @intCast(ts.nsec));
    }

    fn observe(self: *Gate) void {
        var path_buf: [80]u8 = undefined;
        const path = std.fmt.bufPrint(path_buf[0 .. path_buf.len - 1], "/proc/self/task/{d}/wchan", .{self.tid}) catch unreachable;
        path_buf[path.len] = 0;
        const rc: isize = @bitCast(linux.open(@ptrCast(&path_buf), .{ .ACCMODE = .RDONLY, .CLOEXEC = true }, 0));
        if (rc < 0) {
            self.release();
            return;
        }
        const fd: i32 = @intCast(rc);
        defer _ = linux.close(fd);
        const end = nanos() + 5_000_000_000;
        while (nanos() < end) {
            var bytes: [128]u8 = undefined;
            const count: isize = @bitCast(linux.pread(fd, &bytes, bytes.len, 0));
            if (count > 0 and std.mem.indexOf(u8, bytes[0..@intCast(count)], "kvm_vcpu_block") != null) {
                self.blocked.store(true, .seq_cst);
                break;
            }
            _ = linux.sched_yield();
        }
        // Bounded external observation of our owner, not a guest heartbeat
        // or completion polling in the runtime.
        self.release();
    }
};

fn kickHandler(_: linux.SIG) callconv(.c) void {}

test "block worker: real KVM blocked HLT and handled pre-entry signal" {
    var action = linux.Sigaction{
        .handler = .{ .handler = &kickHandler },
        .mask = linux.sigemptyset(),
        .flags = 0,
    };
    var previous: linux.Sigaction = undefined;
    try std.testing.expectEqual(@as(isize, 0), @as(isize, @bitCast(linux.sigaction(linux.SIG.USR1, &action, &previous))));
    defer _ = linux.sigaction(linux.SIG.USR1, &previous, null);
    const kvm = try Kvm.open();
    defer kvm.deinit();
    const vm = try kvm.createVm();
    defer vm.deinit();
    try vm.createIrqChip();
    var mem = try Memory.init(1024 * 1024);
    defer mem.deinit();
    try vm.setMemoryRegion(0, 0, mem.alignedMem());
    var vcpu = try vm.createVcpu(0, try kvm.getVcpuMmapSize());
    defer vcpu.deinit();
    var sregs = try vcpu.getSregs();
    sregs.cs.base = 0;
    sregs.cs.selector = 0;
    try vcpu.setSregs(&sregs);
    var regs = std.mem.zeroes(abi.c.kvm_regs);
    regs.rip = 0x1000;
    regs.rflags = 2;
    try vcpu.setRegs(&regs);
    try mem.write(0x1000, &.{ 0xfa, 0xf4, 0xeb, 0xfd });
    const tid: i32 = @intCast(linux.gettid());
    for ([_]bool{ false, true }) |blocked_run| {
        var gate = Gate{ .tid = tid };
        const worker = try Worker.create(-1, .{ .context = &gate, .write = Gate.write });
        defer worker.destroy();
        defer gate.release();
        worker.wake = .{ .immediate_exit = &vcpu.kvm_run.immediate_exit, .tid = tid };
        @memset(worker.buffer[0..512], 0x5a);
        worker.submit(.write, 512, 0);
        while (gate.entered.load(.seq_cst) == 0) Worker.waitState(&gate.entered, 0);
        Worker.clearBeforeEntry(&vcpu.kvm_run.immediate_exit);
        try std.testing.expect(!worker.ready());
        if (blocked_run) {
            const observer = try std.Thread.spawn(.{}, Gate.observe, .{&gate});
            defer observer.join();
            try std.testing.expectError(error.Interrupted, vcpu.run());
            try std.testing.expect(gate.blocked.load(.seq_cst));
        } else {
            gate.release();
            while (worker.notification.load(.seq_cst) == 0) Worker.waitState(&worker.notification, 0);
            try std.testing.expectError(error.Interrupted, vcpu.run());
        }
        try std.testing.expect(worker.ready());
        try std.testing.expect(!worker.result.failed);
        worker.consume();
    }
    Worker.clearBeforeEntry(&vcpu.kvm_run.immediate_exit);
    regs.rip = 0x1000;
    try vcpu.setRegs(&regs);
    try vcpu.setMpState(&.{ .mp_state = abi.c.KVM_MP_STATE_RUNNABLE });
    try mem.write(0x1000, &.{ 0xba, 0xf8, 0x03, 0xec, 0xf4 });
    try std.testing.expectEqual(@as(u32, abi.c.KVM_EXIT_IO), try vcpu.run());
    const io = vcpu.getIoData().?;
    io.data[0] = 0x5a;
    try std.testing.expectEqual(@as(u64, 0), (try vcpu.getRegs()).rax & 0xff);
    try vcpu.completePendingExit();
    const completed = try vcpu.getRegs();
    try std.testing.expectEqual(@as(u64, 0x5a), completed.rax & 0xff);
    try std.testing.expectEqual(@as(u64, 0x1004), completed.rip);
}
