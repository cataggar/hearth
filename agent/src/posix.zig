//! Blocking, allocation-free wrappers for POSIX operations removed from std.posix.
const std = @import("std");
const posix = std.posix;
const c = std.c;

pub const fd_t = posix.fd_t;
pub const pid_t = posix.pid_t;
pub const pollfd = posix.pollfd;
pub const POLL = posix.POLL;
pub const SIG = posix.SIG;
pub const W = posix.W;
pub const read = posix.read;
pub const poll = posix.poll;
pub const kill = posix.kill;

pub fn close(fd: fd_t) void {
    // On Linux, EINTR still closes the descriptor; retrying could close a reused fd.
    _ = c.close(fd);
}

pub fn write(fd: fd_t, buf: []const u8) !usize {
    if (buf.len == 0) return 0;
    while (true) {
        const rc = c.write(fd, buf.ptr, @min(buf.len, 0x7ffff000));
        switch (posix.errno(rc)) {
            .SUCCESS => return @intCast(rc),
            .INTR => continue,
            .AGAIN => return error.WouldBlock,
            .PIPE => return error.BrokenPipe,
            .IO => return error.InputOutput,
            .NOSPC => return error.NoSpaceLeft,
            .DQUOT => return error.DiskQuota,
            .FBIG => return error.FileTooBig,
            .NOMEM, .NOBUFS => return error.SystemResources,
            else => |err| return posix.unexpectedErrno(err),
        }
    }
}

pub fn pipe() ![2]fd_t {
    var fds: [2]fd_t = undefined;
    switch (posix.errno(c.pipe(&fds))) {
        .SUCCESS => return fds,
        .MFILE => return error.ProcessFdQuotaExceeded,
        .NFILE => return error.SystemFdQuotaExceeded,
        else => |err| return posix.unexpectedErrno(err),
    }
}

pub fn fork() !pid_t {
    const rc = c.fork();
    switch (posix.errno(rc)) {
        .SUCCESS => return rc,
        .AGAIN, .NOMEM => return error.SystemResources,
        else => |err| return posix.unexpectedErrno(err),
    }
}

pub fn dup2(old_fd: fd_t, new_fd: fd_t) !void {
    while (true) {
        switch (posix.errno(c.dup2(old_fd, new_fd))) {
            .SUCCESS => return,
            .INTR, .BUSY => continue,
            .MFILE => return error.ProcessFdQuotaExceeded,
            else => |err| return posix.unexpectedErrno(err),
        }
    }
}

pub fn setsid() !pid_t {
    const rc = c.setsid();
    switch (posix.errno(rc)) {
        .SUCCESS => return rc,
        .PERM => return error.PermissionDenied,
        else => |err| return posix.unexpectedErrno(err),
    }
}

pub const WaitPidResult = struct {
    pid: pid_t,
    status: u32,
};

pub fn waitpid(pid: pid_t, flags: u32) WaitPidResult {
    var status: c_int = 0;
    while (true) {
        const rc = c.waitpid(pid, &status, @intCast(flags));
        switch (posix.errno(rc)) {
            .SUCCESS => return .{ .pid = rc, .status = @bitCast(status) },
            .INTR => continue,
            else => unreachable,
        }
    }
}

pub fn openZ(path: [*:0]const u8, flags: posix.O, mode: posix.mode_t) posix.OpenError!fd_t {
    return posix.openatZ(posix.AT.FDCWD, path, flags, mode);
}

pub fn mkdirZ(path: [*:0]const u8, mode: posix.mode_t) !void {
    switch (posix.errno(c.mkdir(path, mode))) {
        .SUCCESS => return,
        .EXIST => return error.PathAlreadyExists,
        .ACCES => return error.AccessDenied,
        .NOENT => return error.FileNotFound,
        .NOTDIR => return error.NotDir,
        .NOSPC => return error.NoSpaceLeft,
        .NOMEM => return error.SystemResources,
        .NAMETOOLONG => return error.NameTooLong,
        .LOOP => return error.SymLinkLoop,
        .ROFS => return error.ReadOnlyFileSystem,
        else => |err| return posix.unexpectedErrno(err),
    }
}

pub fn nanosleep(seconds: u64, nanoseconds: u64) void {
    var req: posix.timespec = .{
        .sec = @intCast(seconds + nanoseconds / std.time.ns_per_s),
        .nsec = @intCast(nanoseconds % std.time.ns_per_s),
    };
    var remaining: posix.timespec = undefined;
    while (true) {
        switch (posix.errno(c.nanosleep(&req, &remaining))) {
            .SUCCESS => return,
            .INTR => req = remaining,
            else => unreachable,
        }
    }
}
