/* Scoped irqfd work CPU accounting; never emits task names, stacks or addresses. */
typedef unsigned int u32;
typedef unsigned long long u64;
#define SEC(name) __attribute__((section(name), used))
#define UINT(name, value) int (*name)[value]
#define TYPE(name, value) value *name

struct config { u64 inject, shutdown; u32 tgid; };
struct active { u64 on_cpu, accumulated, kind; };
struct total { u64 cpu_ns, jobs; };
struct { UINT(type, 2); UINT(max_entries, 1); TYPE(key, u32); TYPE(value, struct config); } config SEC(".maps");
struct { UINT(type, 1); UINT(max_entries, 256); TYPE(key, u64); TYPE(value, u64); } works SEC(".maps");
struct { UINT(type, 1); UINT(max_entries, 64); TYPE(key, u32); TYPE(value, struct active); } active SEC(".maps");
struct { UINT(type, 2); UINT(max_entries, 3); TYPE(key, u32); TYPE(value, struct total); } totals SEC(".maps");
static void *(*lookup)(void *, const void *) = (void *)1;
static long (*update)(void *, const void *, const void *, u64) = (void *)2;
static long (*remove_key)(void *, const void *) = (void *)3;
static u64 (*now)(void) = (void *)5;
static u64 (*pid_tgid)(void) = (void *)14;

struct work_ctx { u64 common, work, function; };
struct switch_ctx {
    u64 common; char prev_comm[16]; u32 prev_pid, prev_prio; u64 prev_state;
    char next_comm[16]; u32 next_pid, next_prio;
};
static void bad(void) {
    u32 zero = 0;
    struct total *total = lookup(&totals, &zero);
    if (total) __sync_fetch_and_add(&total->jobs, 1);
}

SEC("tracepoint/workqueue/workqueue_queue_work")
int queued(struct work_ctx *ctx) {
    u32 zero = 0;
    struct config *cfg = lookup(&config, &zero);
    if (!cfg || !cfg->tgid) return 0;
    u64 kind = ctx->function == cfg->inject ? 1 : ctx->function == cfg->shutdown ? 2 : 0;
    if (!kind) return 0;
    u64 key = ctx->work;
    if ((pid_tgid() >> 32) != cfg->tgid) {
        /* Invalidate a freed address reused by another VM; retain no foreign record. */
        remove_key(&works, &key);
        return 0;
    }
    if (update(&works, &key, &kind, 0)) bad();
    return 0;
}

SEC("tracepoint/workqueue/workqueue_execute_start")
int started(struct work_ctx *ctx) {
    u64 key = ctx->work;
    u64 *kind = lookup(&works, &key);
    if (!kind) return 0;
    u32 zero = 0;
    struct config *cfg = lookup(&config, &zero);
    if (!cfg || (*kind == 1 ? ctx->function != cfg->inject : ctx->function != cfg->shutdown)) return 0;
    u32 tid = (u32)pid_tgid();
    if (lookup(&active, &tid)) { bad(); return 0; }
    struct active value = { .on_cpu = now(), .kind = *kind };
    if (update(&active, &tid, &value, 0)) bad();
    return 0;
}

SEC("tracepoint/sched/sched_switch")
int switched(struct switch_ctx *ctx) {
    u64 stamp = now();
    u32 tid = ctx->prev_pid;
    struct active *value = lookup(&active, &tid);
    if (value && value->on_cpu) {
        value->accumulated += stamp - value->on_cpu;
        value->on_cpu = 0;
    }
    tid = ctx->next_pid;
    value = lookup(&active, &tid);
    if (value) value->on_cpu = stamp;
    return 0;
}

SEC("tracepoint/workqueue/workqueue_execute_end")
int ended(struct work_ctx *ctx) {
    u32 tid = (u32)pid_tgid();
    struct active *value = lookup(&active, &tid);
    if (!value) return 0;
    u64 cpu = value->accumulated;
    if (value->on_cpu) cpu += now() - value->on_cpu;
    else bad();
    u32 kind = value->kind;
    struct total *total = lookup(&totals, &kind);
    if (total) {
        __sync_fetch_and_add(&total->cpu_ns, cpu);
        __sync_fetch_and_add(&total->jobs, 1);
    }
    remove_key(&active, &tid);
    return 0;
}
char bpf_license[] SEC("license") = "Dual BSD/GPL";
