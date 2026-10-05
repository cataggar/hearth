// Integration tests for flint.
// Spawn the flint binary and test end-to-end behavior.
// Requires /dev/kvm, /tmp/vmlinuz-minimal, bsdcpio, gzip, and static /usr/bin/busybox.
//
// Run with: zig build integration-test

const std = @import("std");
const linux = std.os.linux;
const process = std.process;

const FLINT_BIN = "zig-out/bin/flint";
const FIXTURE_FLINT_BIN = "../../zig-out/bin/flint";
const DEFAULT_KERNEL = "/tmp/vmlinuz-minimal";

extern "c" fn getenv(name: [*:0]const u8) ?[*:0]const u8;

fn kernelPath() [:0]const u8 {
    return if (getenv("FLINT_TEST_KERNEL")) |path| std.mem.span(path) else DEFAULT_KERNEL;
}
const INIT_SCRIPT =
    \\#!/bin/sh
    \\set -eu
    \\if [ ! -c /dev/console ]; then /bin/busybox mknod /dev/console c 5 1; fi
    \\exec </dev/console >/dev/console 2>&1
    \\while true; do
    \\    echo FLINT_BOOT_OK
    \\    /bin/busybox sleep 1
    \\done
    \\
;

var threaded_io: ?std.Io.Threaded = null;
var fixture_counter: u32 = 0;

fn io() std.Io {
    if (threaded_io == null) {
        threaded_io = std.Io.Threaded.init(std.testing.allocator, .{});
    }
    return threaded_io.?.io();
}

fn deinitIo() void {
    if (threaded_io) |*threaded| threaded.deinit();
    threaded_io = null;
}

fn requireKernel() !void {
    const rc: isize = @bitCast(linux.open(kernelPath(), .{ .ACCMODE = .RDONLY }, 0));
    if (rc < 0) {
        std.debug.print("integration requires a kernel at {s}\n", .{kernelPath()});
        return error.KernelUnavailable;
    }
    _ = linux.close(@intCast(rc));
}

const Fixture = struct {
    root: [64]u8 = undefined,
    root_len: usize,

    fn dir(self: *const Fixture) []const u8 {
        return self.root[0..self.root_len];
    }

    fn path(self: *const Fixture, name: []const u8, buf: []u8) ![:0]u8 {
        return std.fmt.bufPrintSentinel(buf, "{s}/{s}", .{ self.dir(), name }, 0);
    }

    fn deinit(self: *const Fixture) !void {
        try std.Io.Dir.cwd().deleteTree(io(), self.dir());
    }
};

/// Build an executable BusyBox initramfs in a private, project-relative fixture directory.
fn buildInitrd() !Fixture {
    var fixture: Fixture = .{ .root_len = 0 };
    fixture_counter += 1;
    const root = try std.fmt.bufPrint(&fixture.root, ".zig-cache/flint-integration-{d}-{d}", .{ linux.getpid(), fixture_counter });
    fixture.root_len = root.len;
    try std.Io.Dir.cwd().createDir(io(), fixture.dir(), .fromMode(0o700));
    errdefer fixture.deinit() catch |err| std.debug.panic("fixture cleanup failed: {s}", .{@errorName(err)});

    var init_buf: [256]u8 = undefined;
    const init_path = try fixture.path("init", &init_buf);
    try std.Io.Dir.cwd().writeFile(io(), .{ .sub_path = init_path, .data = INIT_SCRIPT });

    const allocator = std.testing.allocator;
    const result = try process.run(allocator, io(), .{
        .cwd = .{ .path = fixture.dir() },
        .argv = &.{
            "/bin/sh", "-ec",
            "mkdir bin dev; cp /usr/bin/busybox bin/busybox; ln -s busybox bin/sh; chmod +x init; " ++
                "printf '%s\\n' bin bin/busybox bin/sh dev init | bsdcpio -o -H newc > initrd.cpio; " ++
                "gzip initrd.cpio",
        },
    });
    defer allocator.free(result.stdout);
    defer allocator.free(result.stderr);

    if (result.term != .exited or result.term.exited != 0) {
        std.debug.print("initrd build failed: {s}\n", .{result.stderr});
        return error.InitrdBuildFailed;
    }

    return fixture;
}

fn expectHttpStatus(response: []const u8, expected: []const u8) !void {
    try std.testing.expect(response.len >= 12);
    if (!std.mem.eql(u8, response[9..12], expected)) {
        std.debug.print("unexpected HTTP response: {s}\n", .{response});
    }
    try std.testing.expectEqualStrings(expected, response[9..12]);
}

fn checkedRequest(sock_path: []const u8, method: []const u8, target: []const u8, body: ?[]const u8, expected: []const u8) ![]u8 {
    const response = try httpRequest(sock_path, method, target, body);
    errdefer std.testing.allocator.free(response);
    try expectHttpStatus(response, expected);
    return response;
}

fn waitForGuestMarker(child: *process.Child) !void {
    const stdout = child.stdout orelse return error.MissingStdout;
    var buf: [8192]u8 = undefined;
    var total: usize = 0;
    var start_ts: linux.timespec = undefined;
    if (linux.clock_gettime(.MONOTONIC, &start_ts) != 0) return error.ClockFailed;
    while (true) {
        var now_ts: linux.timespec = undefined;
        if (linux.clock_gettime(.MONOTONIC, &now_ts) != 0) return error.ClockFailed;
        if (now_ts.sec - start_ts.sec >= 10) break;
        var pfd = [_]linux.pollfd{.{ .fd = stdout.handle, .events = linux.POLL.IN, .revents = 0 }};
        const poll_rc: isize = @bitCast(linux.poll(&pfd, 1, 100));
        if (poll_rc < 0) return error.PollFailed;
        if (poll_rc == 0) continue;
        const rc: isize = @bitCast(linux.read(stdout.handle, buf[total..].ptr, buf.len - total));
        if (rc < 0) return error.ReadFailed;
        if (rc == 0) break;
        total += @intCast(rc);
        if (std.mem.indexOf(u8, buf[0..total], "FLINT_BOOT_OK") != null) return;
        if (total == buf.len) {
            std.mem.copyForwards(u8, buf[0 .. buf.len / 2], buf[buf.len / 2 ..]);
            total = buf.len / 2;
        }
    }
    std.debug.print("guest did not reach userspace; final serial output:\n{s}\n", .{buf[0..total]});
    return error.GuestBootFailed;
}

/// Connect to a Unix socket, send an HTTP request, return the full response.
fn httpRequest(sock_path: []const u8, method: []const u8, target: []const u8, body: ?[]const u8) ![]u8 {
    const allocator = std.testing.allocator;

    const sock_rc: isize = @bitCast(linux.socket(linux.AF.UNIX, linux.SOCK.STREAM | linux.SOCK.CLOEXEC, 0));
    if (sock_rc < 0) return error.SocketFailed;
    const fd: linux.fd_t = @intCast(sock_rc);
    defer _ = linux.close(fd);

    var addr: linux.sockaddr.un = .{ .family = linux.AF.UNIX, .path = undefined };
    @memset(&addr.path, 0);
    for (0..sock_path.len) |i| {
        addr.path[i] = @intCast(sock_path[i]);
    }

    const connect_rc: isize = @bitCast(linux.connect(fd, @ptrCast(&addr), @intCast(@sizeOf(linux.sockaddr.un))));
    if (connect_rc < 0) return error.ConnectFailed;

    var req_buf: [2048]u8 = undefined;
    const req = if (body) |b|
        std.fmt.bufPrint(&req_buf, "{s} {s} HTTP/1.1\r\nHost: localhost\r\nContent-Length: {d}\r\nConnection: close\r\n\r\n{s}", .{ method, target, b.len, b }) catch return error.RequestTooLarge
    else
        std.fmt.bufPrint(&req_buf, "{s} {s} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n", .{ method, target }) catch return error.RequestTooLarge;

    var written: usize = 0;
    while (written < req.len) {
        const rc: isize = @bitCast(linux.write(fd, req[written..].ptr, req.len - written));
        if (rc <= 0) return error.WriteFailed;
        written += @intCast(rc);
    }

    // Read response into allocated buffer
    var buf: [8192]u8 = undefined;
    var total: usize = 0;
    while (total < buf.len) {
        const rc: isize = @bitCast(linux.read(fd, buf[total..].ptr, buf.len - total));
        if (rc <= 0) break;
        total += @intCast(rc);
    }

    const result = try allocator.alloc(u8, total);
    @memcpy(result, buf[0..total]);
    return result;
}

fn sleep_ms(ms: u64) void {
    const ts = linux.timespec{ .sec = @intCast(ms / 1000), .nsec = @intCast((ms % 1000) * 1_000_000) };
    _ = linux.nanosleep(&ts, null);
}

// ============================================================
// Tests
// ============================================================

test "flint prints usage with no args" {
    defer deinitIo();
    const allocator = std.testing.allocator;
    const result = try process.run(allocator, io(), .{
        .argv = &.{FLINT_BIN},
    });
    defer allocator.free(result.stdout);
    defer allocator.free(result.stderr);

    try std.testing.expectEqual(@as(u8, 1), result.term.exited);
    try std.testing.expect(std.mem.indexOf(u8, result.stderr, "usage: flint") != null);
}

test "flint fails with nonexistent kernel" {
    defer deinitIo();
    const allocator = std.testing.allocator;
    const result = try process.run(allocator, io(), .{
        .argv = &.{ FLINT_BIN, "/nonexistent/kernel" },
    });
    defer allocator.free(result.stdout);
    defer allocator.free(result.stderr);

    try std.testing.expect(result.term.exited != 0);
}

test "boot to userspace" {
    defer deinitIo();
    try requireKernel();
    const fixture = try buildInitrd();
    defer fixture.deinit() catch |err| std.debug.panic("fixture cleanup failed: {s}", .{@errorName(err)});

    // Use spawn+kill since the VM doesn't exit cleanly
    var child = try process.spawn(io(), .{
        .cwd = .{ .path = fixture.dir() },
        .argv = &.{ FIXTURE_FLINT_BIN, kernelPath(), "initrd.cpio.gz" },
        .stdout = .pipe,
        .stderr = .inherit,
    });
    defer {
        child.kill(io());
    }

    try waitForGuestMarker(&child);
}

test "API boot and VM status" {
    defer deinitIo();
    try requireKernel();

    const allocator = std.testing.allocator;
    const fixture = try buildInitrd();
    defer fixture.deinit() catch |err| std.debug.panic("fixture cleanup failed: {s}", .{@errorName(err)});
    var sock_buf: [256]u8 = undefined;
    const sock_path = try fixture.path("api.sock", &sock_buf);

    var child = try process.spawn(io(), .{
        .cwd = .{ .path = fixture.dir() },
        .argv = &.{ FIXTURE_FLINT_BIN, "--api-sock", "api.sock" },
        .stdout = .ignore,
        .stderr = .inherit,
    });
    defer {
        child.kill(io());
    }

    sleep_ms(500);

    // Configure and boot
    var boot_cmd_buf: [512]u8 = undefined;
    const boot_cmd = std.fmt.bufPrint(
        &boot_cmd_buf,
        "{{\"kernel_image_path\":\"{s}\",\"initrd_path\":\"{s}\"}}",
        .{ kernelPath(), "initrd.cpio.gz" },
    ) catch unreachable;

    var r = try checkedRequest(sock_path, "PUT", "/boot-source", boot_cmd, "204");
    allocator.free(r);

    r = try checkedRequest(sock_path, "PUT", "/actions", "{\"action_type\":\"InstanceStart\"}", "204");
    allocator.free(r);

    sleep_ms(2000);

    // Check VM status
    const status = try checkedRequest(sock_path, "GET", "/vm", null, "200");
    defer allocator.free(status);
    try std.testing.expect(std.mem.indexOf(u8, status, "Running") != null);
}

test "API pause and resume" {
    defer deinitIo();
    try requireKernel();

    const allocator = std.testing.allocator;
    const fixture = try buildInitrd();
    defer fixture.deinit() catch |err| std.debug.panic("fixture cleanup failed: {s}", .{@errorName(err)});
    var sock_buf: [256]u8 = undefined;
    const sock_path = try fixture.path("api.sock", &sock_buf);

    var child = try process.spawn(io(), .{
        .cwd = .{ .path = fixture.dir() },
        .argv = &.{ FIXTURE_FLINT_BIN, "--api-sock", "api.sock" },
        .stdout = .ignore,
        .stderr = .inherit,
    });
    defer {
        child.kill(io());
    }

    sleep_ms(500);

    var boot_cmd_buf: [512]u8 = undefined;
    const boot_cmd = std.fmt.bufPrint(
        &boot_cmd_buf,
        "{{\"kernel_image_path\":\"{s}\",\"initrd_path\":\"{s}\"}}",
        .{ kernelPath(), "initrd.cpio.gz" },
    ) catch unreachable;

    var r = try checkedRequest(sock_path, "PUT", "/boot-source", boot_cmd, "204");
    allocator.free(r);
    r = try checkedRequest(sock_path, "PUT", "/actions", "{\"action_type\":\"InstanceStart\"}", "204");
    allocator.free(r);

    sleep_ms(2000);

    // Pause
    r = try checkedRequest(sock_path, "PATCH", "/vm", "{\"state\":\"Paused\"}", "204");
    allocator.free(r);

    const paused = try checkedRequest(sock_path, "GET", "/vm", null, "200");
    defer allocator.free(paused);
    try std.testing.expect(std.mem.indexOf(u8, paused, "Paused") != null);

    // Resume
    r = try checkedRequest(sock_path, "PATCH", "/vm", "{\"state\":\"Resumed\"}", "204");
    allocator.free(r);

    const resumed = try checkedRequest(sock_path, "GET", "/vm", null, "200");
    defer allocator.free(resumed);
    try std.testing.expect(std.mem.indexOf(u8, resumed, "Running") != null);
}

test "snapshot requires pause" {
    defer deinitIo();
    try requireKernel();

    const allocator = std.testing.allocator;
    const fixture = try buildInitrd();
    defer fixture.deinit() catch |err| std.debug.panic("fixture cleanup failed: {s}", .{@errorName(err)});
    var sock_buf: [256]u8 = undefined;
    const sock_path = try fixture.path("api.sock", &sock_buf);

    var child = try process.spawn(io(), .{
        .cwd = .{ .path = fixture.dir() },
        .argv = &.{ FIXTURE_FLINT_BIN, "--api-sock", "api.sock" },
        .stdout = .ignore,
        .stderr = .inherit,
    });
    defer {
        child.kill(io());
    }

    sleep_ms(500);

    var boot_cmd_buf: [512]u8 = undefined;
    const boot_cmd = std.fmt.bufPrint(
        &boot_cmd_buf,
        "{{\"kernel_image_path\":\"{s}\",\"initrd_path\":\"{s}\"}}",
        .{ kernelPath(), "initrd.cpio.gz" },
    ) catch unreachable;

    var r = try checkedRequest(sock_path, "PUT", "/boot-source", boot_cmd, "204");
    allocator.free(r);
    r = try checkedRequest(sock_path, "PUT", "/actions", "{\"action_type\":\"InstanceStart\"}", "204");
    allocator.free(r);

    sleep_ms(2000);

    // Snapshot without pausing should fail
    const snap_resp = try checkedRequest(
        sock_path,
        "PUT",
        "/snapshot/create",
        "{\"snapshot_path\":\"snapshot.vmstate\",\"mem_file_path\":\"snapshot.mem\"}",
        "400",
    );
    defer allocator.free(snap_resp);
    try std.testing.expect(std.mem.indexOf(u8, snap_resp, "must be paused") != null);
}

test "snapshot create and restore" {
    defer deinitIo();
    try requireKernel();

    const allocator = std.testing.allocator;
    const fixture = try buildInitrd();
    defer fixture.deinit() catch |err| std.debug.panic("fixture cleanup failed: {s}", .{@errorName(err)});
    var sock_buf: [256]u8 = undefined;
    const sock_path = try fixture.path("api.sock", &sock_buf);
    var vmstate_buf: [256]u8 = undefined;
    const vmstate = try fixture.path("snapshot.vmstate", &vmstate_buf);
    var memfile_buf: [256]u8 = undefined;
    const memfile = try fixture.path("snapshot.mem", &memfile_buf);

    // Boot VM
    var child = try process.spawn(io(), .{
        .cwd = .{ .path = fixture.dir() },
        .argv = &.{ FIXTURE_FLINT_BIN, "--api-sock", "api.sock" },
        .stdout = .ignore,
        .stderr = .inherit,
    });
    defer child.kill(io());

    sleep_ms(500);

    var boot_cmd_buf: [512]u8 = undefined;
    const boot_cmd = std.fmt.bufPrint(
        &boot_cmd_buf,
        "{{\"kernel_image_path\":\"{s}\",\"initrd_path\":\"{s}\"}}",
        .{ kernelPath(), "initrd.cpio.gz" },
    ) catch unreachable;

    var r = try checkedRequest(sock_path, "PUT", "/boot-source", boot_cmd, "204");
    allocator.free(r);
    r = try checkedRequest(sock_path, "PUT", "/actions", "{\"action_type\":\"InstanceStart\"}", "204");
    allocator.free(r);

    sleep_ms(2000);

    // Pause and snapshot
    r = try checkedRequest(sock_path, "PATCH", "/vm", "{\"state\":\"Paused\"}", "204");
    allocator.free(r);

    var snap_cmd_buf: [512]u8 = undefined;
    const snap_cmd = std.fmt.bufPrint(
        &snap_cmd_buf,
        "{{\"snapshot_path\":\"{s}\",\"mem_file_path\":\"{s}\"}}",
        .{ "snapshot.vmstate", "snapshot.mem" },
    ) catch unreachable;

    r = try checkedRequest(sock_path, "PUT", "/snapshot/create", snap_cmd, "204");
    allocator.free(r);

    // Kill original VM
    child.kill(io());

    // Verify snapshot files exist
    const vm_rc: isize = @bitCast(linux.open(vmstate.ptr, .{ .ACCMODE = .RDONLY }, 0));
    try std.testing.expect(vm_rc >= 0);
    _ = linux.close(@intCast(vm_rc));

    const mem_rc: isize = @bitCast(linux.open(memfile.ptr, .{ .ACCMODE = .RDONLY }, 0));
    try std.testing.expect(mem_rc >= 0);
    _ = linux.close(@intCast(mem_rc));

    // Restore and verify it runs
    var restore_sock_buf: [256]u8 = undefined;
    const restore_sock = try fixture.path("restored.sock", &restore_sock_buf);

    var restored = try process.spawn(io(), .{
        .cwd = .{ .path = fixture.dir() },
        .argv = &.{ FIXTURE_FLINT_BIN, "--restore", "--vmstate-path", "snapshot.vmstate", "--mem-path", "snapshot.mem", "--api-sock", "restored.sock" },
        .stdout = .pipe,
        .stderr = .inherit,
    });
    defer {
        restored.kill(io());
    }

    try waitForGuestMarker(&restored);

    const status = try checkedRequest(restore_sock, "GET", "/vm", null, "200");
    defer allocator.free(status);
    try std.testing.expect(std.mem.indexOf(u8, status, "Running") != null);
}
