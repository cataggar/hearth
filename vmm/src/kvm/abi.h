#include <linux/kvm.h>

/* Resolve opaque translated unions through the C ABI, not guessed Zig layouts. */
enum {
    HEARTH_IRQCHIP_DATA_OFFSET = __builtin_offsetof(struct kvm_irqchip, chip),
    HEARTH_IOAPIC_REDIR_OFFSET = __builtin_offsetof(struct kvm_ioapic_state, redirtbl),
    HEARTH_IOAPIC_IRR_OFFSET = __builtin_offsetof(struct kvm_ioapic_state, irr),
    HEARTH_PIC_ELCR_OFFSET = __builtin_offsetof(struct kvm_pic_state, elcr),
    HEARTH_PIC_IMR_OFFSET = __builtin_offsetof(struct kvm_pic_state, imr),
    HEARTH_PIC_IRR_OFFSET = __builtin_offsetof(struct kvm_pic_state, irr),
};
