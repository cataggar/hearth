import unittest

from analyze_trace import analyze


class AttributionTests(unittest.TestCase):
    def test_kernel_handled_exits_and_serial_irqs_are_not_virtio_savings(self):
        def line(timestamp, event, detail):
            return f"flint 123 [008] {timestamp:.6f}: {event}: {detail}"

        data = [
            line(1, "kvm:kvm_exit", "reason IO_INSTRUCTION rip 0x1"),
            line(1.1, "kvm:kvm_exit", "reason EPT_VIOLATION rip 0x1"),
            line(1.11, "kvm:kvm_userspace_exit", "reason KVM_EXIT_MMIO (6)"),
            line(1.12, "kvm:kvm_mmio", "mmio unsatisfied-read len 4 gpa 0xd0000060 val 0x0"),
            line(1.13, "kvm:kvm_mmio", "mmio read len 4 gpa 0xd0000060 val 0x1"),
            line(1.14, "kvm:kvm_mmio", "mmio write len 4 gpa 0xd0000050 val 0x1"),
            line(1.15, "kvm:kvm_mmio", "mmio write len 2 gpa 0xd0000050 val 0x1"),
            line(1.20, "syscalls:sys_enter_ioctl", "fd: 0x4, cmd: 0x4008ae61, arg: 0x1234"),
            line(1.21, "kvm:kvm_set_irq", "gsi 5 level 1 source 0"),
            line(1.22, "syscalls:sys_exit_ioctl", "0x0"),
            line(1.30, "syscalls:sys_enter_ioctl", "fd: 0x4, cmd: 0x4008ae61, arg: 0x1234"),
            line(1.31, "kvm:kvm_set_irq", "gsi 4 level 1 source 0"),
            line(1.32, "syscalls:sys_exit_ioctl", "0x0"),
        ]
        result = analyze(data, [{"kind": "vsock", "mmio_base": 0xD0000000, "gsi": 5}])
        self.assertEqual(sum(result["kernel_exit_reasons"].values()), 2)
        self.assertEqual(result["userspace_exit_reasons"], {"KVM_EXIT_MMIO": 1})
        self.assertEqual(result["observed_four_byte_notify_writes"], {"vsock:queue1": 1})
        self.assertEqual(result["completed_irq_line_ioctl_calls"], {
            "vsock": 1, "non-virtio-or-unattributed": 1,
        })
        self.assertAlmostEqual(result["eligible_irq_line_ioctl_profiled_us"]["p50"], 20000)

    def test_clipped_irq_ioctls_do_not_become_complete_latency_samples(self):
        result = analyze([
            "flint 123 [008] 1.000000: syscalls:sys_exit_ioctl: 0x0",
            "flint 123 [008] 1.001000: syscalls:sys_enter_ioctl: fd: 0x4, cmd: 0x4008ae61, arg: 0x1234",
            "flint 123 [008] 1.002000: kvm:kvm_set_irq: gsi 5 level 1 source 0",
        ], [{"kind": "vsock", "mmio_base": 0xD0000000, "gsi": 5}])
        self.assertEqual(result["unpaired_ioctl_exits_at_window_boundary"], 1)
        self.assertEqual(result["pending_ioctl_entries_at_window_boundary"], 1)
        self.assertEqual(result["completed_irq_line_ioctl_calls"], {})
        self.assertIsNone(result["eligible_irq_line_ioctl_profiled_us"]["p50"])


if __name__ == "__main__":
    unittest.main()
