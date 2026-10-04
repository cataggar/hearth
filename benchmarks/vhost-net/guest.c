#include <arpa/inet.h>
#include <errno.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <unistd.h>

static int read_all(int fd, void *buffer, size_t size) {
    unsigned char *p = buffer;
    while (size) {
        ssize_t n = read(fd, p, size);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return -1;
        p += n;
        size -= (size_t)n;
    }
    return 0;
}

static int write_all(int fd, const void *buffer, size_t size) {
    const unsigned char *p = buffer;
    while (size) {
        ssize_t n = write(fd, p, size);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return -1;
        p += n;
        size -= (size_t)n;
    }
    return 0;
}

static void serve(int fd, unsigned port) {
    unsigned char buffer[65536];
    if (port == 7000) {
        while (read_all(fd, buffer, 64) == 0)
            if (write_all(fd, buffer, 64) < 0) return;
        return;
    }
    while (1) {
        uint64_t count, remaining, errors = 0;
        if (read_all(fd, &count, sizeof count) < 0) return;
        if (count == 0 || count > UINT64_C(1073741824)) return;
        remaining = count;
        memset(buffer, 0x5a, sizeof buffer);
        while (remaining) {
            size_t size = remaining < sizeof buffer ? (size_t)remaining : sizeof buffer;
            if (port == 7001) {
                if (read_all(fd, buffer, size) < 0) return;
                for (size_t i = 0; i < size; ++i)
                    errors += buffer[i] != 0x5a;
            } else {
                if (write_all(fd, buffer, size) < 0) return;
            }
            remaining -= size;
        }
        uint64_t response[] = {count, errors};
        if (write_all(fd, response, sizeof response) < 0) return;
    }
}

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    unsigned port = (unsigned)strtoul(argv[1], NULL, 10);
    if (port < 7000 || port > 7002) return 2;
    signal(SIGCHLD, SIG_IGN);
    signal(SIGPIPE, SIG_IGN);
    int listener = socket(AF_INET, SOCK_STREAM, 0);
    int enabled = 1;
    if (listener < 0 || setsockopt(listener, SOL_SOCKET, SO_REUSEADDR, &enabled, sizeof enabled))
        return 1;
    struct sockaddr_in address = {.sin_family = AF_INET, .sin_port = htons((uint16_t)port)};
    if (inet_pton(AF_INET, "192.0.2.2", &address.sin_addr) != 1 ||
        bind(listener, (struct sockaddr *)&address, sizeof address) || listen(listener, 16))
        return 1;
    printf("PERF_LISTEN %u\n", port);
    fflush(stdout);
    while (1) {
        int fd = accept(listener, NULL, NULL);
        if (fd < 0 && errno == EINTR) continue;
        if (fd < 0) return 1;
        pid_t pid = fork();
        if (pid == 0) {
            close(listener);
            serve(fd, port);
            close(fd);
            _exit(0);
        }
        close(fd);
        if (pid < 0) return 1;
    }
}
