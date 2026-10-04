const linux = @import("std").os.linux;

fn futexWait(address: *u32, expected: u32, timeout: ?*const linux.timespec) isize {
    return @bitCast(linux.syscall6(.futex, @intFromPtr(address), 128, expected, if (timeout) |value| @intFromPtr(value) else 0, 0, 0));
}

fn notify(address: *u32, count: u32) void {
    _ = linux.syscall6(.futex, @intFromPtr(address), 129, count, 0, 0, 0);
}

pub const Mutex = struct {
    word: u32 = 0,

    pub fn lock(self: *Mutex) void {
        while (@cmpxchgStrong(u32, &self.word, 0, 1, .acquire, .monotonic) != null) {
            _ = futexWait(&self.word, 1, null);
        }
    }

    pub fn unlock(self: *Mutex) void {
        @atomicStore(u32, &self.word, 0, .release);
        notify(&self.word, 1);
    }
};

pub const Condition = struct {
    sequence: u32 = 0,

    pub fn wait(self: *Condition, mutex: *Mutex) void {
        const sequence = @atomicLoad(u32, &self.sequence, .monotonic);
        mutex.unlock();
        // The kernel checks the sequence before sleeping, including when a
        // broadcast raced with unlocking the associated mutex.
        _ = futexWait(&self.sequence, sequence, null);
        mutex.lock();
    }

    pub fn timedWait(self: *Condition, mutex: *Mutex, timeout_ns: u64) error{Timeout}!void {
        const sequence = @atomicLoad(u32, &self.sequence, .monotonic);
        const timeout = linux.timespec{ .sec = @intCast(timeout_ns / 1_000_000_000), .nsec = @intCast(timeout_ns % 1_000_000_000) };
        mutex.unlock();
        const rc = futexWait(&self.sequence, sequence, &timeout);
        mutex.lock();
        if (rc == -@as(isize, @backingInt(linux.E.TIMEDOUT))) return error.Timeout;
    }

    pub fn broadcast(self: *Condition) void {
        _ = @atomicRmw(u32, &self.sequence, .Add, 1, .release);
        notify(&self.sequence, 0x7fffffff);
    }
};
