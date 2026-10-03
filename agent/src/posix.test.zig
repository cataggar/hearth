const std = @import("std");
const posix = @import("posix.zig");
const linux = std.os.linux;
const c = @import("libc");

test "fork and exec preserve blocking pipes, nonblocking wait and dup2 redirection" {
    const output = try posix.pipe();
    defer posix.close(output[0]);
    const gate = posix.pipe() catch |err| {
        posix.close(output[1]);
        return err;
    };
    defer posix.close(gate[1]);

    const child = posix.fork() catch |err| {
        posix.close(output[1]);
        posix.close(gate[0]);
        return err;
    };
    if (child == 0) {
        posix.close(output[0]);
        posix.close(gate[1]);
        var start: [1]u8 = undefined;
        _ = posix.read(gate[0], &start) catch linux.exit_group(126);
        posix.close(gate[0]);
        _ = posix.setsid() catch linux.exit_group(126);
        posix.dup2(output[1], 1) catch linux.exit_group(126);
        posix.close(output[1]);
        var argv: [8:null]?[*:0]const u8 = @splat(null);
        argv[0] = "/bin/sh";
        argv[1] = "-c";
        argv[2] = "printf redirected; exit 7";
        const envp = [_:null]?[*:0]const u8{};
        _ = linux.execve("/bin/sh", @ptrCast(&argv), @ptrCast(&envp));
        linux.exit_group(126);
    }

    posix.close(output[1]);
    posix.close(gate[0]);
    const pending = posix.waitpid(child, posix.W.NOHANG);
    _ = try posix.write(gate[1], "x");
    var buf: [64]u8 = undefined;
    const n = try posix.read(output[0], &buf);
    const result = posix.waitpid(child, 0);

    try std.testing.expectEqual(@as(posix.pid_t, 0), pending.pid);
    try std.testing.expectEqualStrings("redirected", buf[0..n]);
    try std.testing.expectEqual(child, result.pid);
    try std.testing.expect(posix.W.IFEXITED(result.status));
    try std.testing.expectEqual(@as(u8, 7), posix.W.EXITSTATUS(result.status));
}

test "translated openpty and ioctl preserve terminal dimensions and output" {
    var master: posix.fd_t = -1;
    var slave: posix.fd_t = -1;
    var dimensions = c.winsize{
        .ws_row = 24,
        .ws_col = 80,
        .ws_xpixel = 0,
        .ws_ypixel = 0,
    };
    try std.testing.expectEqual(@as(c_int, 0), c.openpty(&master, &slave, null, null, &dimensions));
    defer posix.close(master);
    defer posix.close(slave);

    var actual: c.winsize = undefined;
    try std.testing.expectEqual(@as(c_int, 0), c.ioctl(master, c.TIOCGWINSZ, &actual));
    try std.testing.expectEqual(dimensions.ws_row, actual.ws_row);
    try std.testing.expectEqual(dimensions.ws_col, actual.ws_col);

    dimensions.ws_row = 40;
    dimensions.ws_col = 120;
    try std.testing.expectEqual(@as(c_int, 0), c.ioctl(master, c.TIOCSWINSZ, &dimensions));
    try std.testing.expectEqual(@as(c_int, 0), c.ioctl(slave, c.TIOCGWINSZ, &actual));
    try std.testing.expectEqual(dimensions.ws_row, actual.ws_row);
    try std.testing.expectEqual(dimensions.ws_col, actual.ws_col);

    _ = try posix.write(slave, "PTY");
    var buf: [64]u8 = undefined;
    const n = try posix.read(master, &buf);
    try std.testing.expectEqualStrings("PTY", buf[0..n]);
}

test "translated setitimer terminates a sleeping child with SIGALRM" {
    const child = try posix.fork();
    if (child == 0) {
        const timer = c.struct_itimerval{
            .it_interval = .{ .tv_sec = 0, .tv_usec = 0 },
            .it_value = .{ .tv_sec = 0, .tv_usec = 50_000 },
        };
        if (c.setitimer(c.ITIMER_REAL, &timer, null) < 0) linux.exit_group(126);
        posix.nanosleep(1, 0);
        linux.exit_group(127);
    }

    const result = posix.waitpid(child, 0);
    try std.testing.expectEqual(child, result.pid);
    try std.testing.expect(posix.W.IFSIGNALED(result.status));
    try std.testing.expectEqual(posix.SIG.ALRM, posix.W.TERMSIG(result.status));
}
