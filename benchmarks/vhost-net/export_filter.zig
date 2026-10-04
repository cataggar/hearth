const std = @import("std");
const seccomp = @import("seccomp");

pub fn main() !void {
    const bytes = std.mem.asBytes(&seccomp.net_kill_filter);
    const rc: isize = @bitCast(std.os.linux.write(1, bytes.ptr, bytes.len));
    if (rc != bytes.len) return error.FilterExportFailed;
}
