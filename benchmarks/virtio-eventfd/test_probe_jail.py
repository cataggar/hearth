import importlib.util
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parent))
SPEC = importlib.util.spec_from_file_location("eventfd_jail_probe", Path(__file__).with_name("probe_jail.py"))
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


class IsolationEvidenceTests(unittest.TestCase):
    def test_kernel_named_userspace_helpers_cannot_bypass_credentials(self):
        owner = {
            "Kthread": "0", "Uid": "1000 1000 1000 1000", "Gid": "1000 1000 1000 1000",
            "Groups": "", "Seccomp": "2", "NoNewPrivs": "1", "CapEff": "0000000000000000",
        }
        helper = {**owner, "comm": "kvm-nx-lpage-re"}
        self.assertTrue(PROBE.enforced_roster([owner, helper], 1000, 1000))
        for field, bad in (
            ("Uid", "0 0 0 0"), ("Groups", "0"), ("Seccomp", "0"), ("NoNewPrivs", "0"),
            ("CapEff", "0000000000000001"), ("Kthread", "unknown"),
        ):
            with self.subTest(field=field):
                self.assertFalse(PROBE.enforced_roster([owner, {**helper, field: bad}], 1000, 1000))
        self.assertFalse(PROBE.enforced_roster([], 1000, 1000))


if __name__ == "__main__":
    unittest.main()
