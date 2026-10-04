#define _GNU_SOURCE
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static uint64_t stamp(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts)) exit(2);
    return (uint64_t)ts.tv_sec * 1000000000 + ts.tv_nsec;
}

int main(int argc, char **argv) {
    if (argc != 4) return 2;
    size_t size = strtoul(argv[2], NULL, 10);
    unsigned count = strtoul(argv[3], NULL, 10);
    if ((size != 4096 && size != 1048576) || count == 0 || count > 1024) return 2;
    int reading = strcmp(argv[1], "read") == 0;
    int flushing = strcmp(argv[1], "flush") == 0;
    if (!reading && !flushing && strcmp(argv[1], "write") != 0) return 2;
    unsigned char *data, *check;
    if (posix_memalign((void **)&data, 4096, size) ||
        posix_memalign((void **)&check, 4096, size)) return 2;
    int fd = open("/dev/vda", O_RDWR | O_DIRECT | O_CLOEXEC);
    if (fd < 0) return 2;
    uint32_t seed = 0x31415926;
    printf("{\"block_size\":%zu,\"operations\":%u,\"direct\":true,\"queue_depth\":1,\"latency_ns\":[", size, count);
    for (unsigned i = 0; i < count; i++) {
        seed = seed * 1664525u + 1013904223u;
        off_t offset = 1048576 + (off_t)(seed % (8 * 1048576 / size)) * size;
        for (size_t j = 0; j < size; j++) data[j] = (unsigned char)(i * 31u + j * 7u);
        uint64_t before = stamp();
        if (reading) {
            if (pread(fd, check, size, offset) != (ssize_t)size) return 3;
        } else {
            if (pwrite(fd, data, size, offset) != (ssize_t)size) return 3;
            if (flushing && fdatasync(fd)) return 3;
        }
        uint64_t latency = stamp() - before;
        if (!reading && (pread(fd, check, size, offset) != (ssize_t)size || memcmp(data, check, size))) return 4;
        printf("%s%llu", i ? "," : "", (unsigned long long)latency);
    }
    if (fdatasync(fd)) return 3;
    puts("],\"write_readback_verified\":true,\"read_integrity_oracle\":\"reads are timed; writes additionally require exact direct readback\"}");
    close(fd);
    free(data);
    free(check);
    return 0;
}
