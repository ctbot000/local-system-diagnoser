import unittest

from diagnoser import memory

VM_STAT = """\
Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                                     8238.
Pages speculative:                                47.
Pages wired down:                             155625.
Pages purgeable:                                1329.
"Translation faults":                     1606768271.
File-backed pages:                            228301.
Anonymous pages:                              390882.
Pages stored in compressor:                   399270.
Pages occupied by compressor:                 225960.
Swapouts:                                    1245185.
"""

TOP = """\
Processes: 812 total, 3 running, 809 sleeping, 4210 threads
Networks: packets: 60770246/87G in, 59022968/84G out.

PID    MEM   CMPRS PURG
32134  1375M 441M  0B
416    436M+ 130M  12M
32108  344M  26M-  7552K
"""

PS = """\
32134 izeye    /Applications/Claude.app/Contents/Frameworks/Claude Helper (Renderer).app/Contents/MacOS/Claude Helper (Renderer)
  416 _windowserver /System/Library/PrivateFrameworks/SkyLight.framework/Resources/WindowServer
"""


class ParseTest(unittest.TestCase):
    def test_parse_size(self):
        self.assertEqual(memory.parse_size("0B"), 0)
        self.assertEqual(memory.parse_size("7552K"), 7552 * 1024)
        self.assertEqual(memory.parse_size("436M+"), 436 * 1024**2)
        self.assertEqual(memory.parse_size("4096.00M"), 4096 * 1024**2)
        with self.assertRaises(ValueError):
            memory.parse_size("lots")

    def test_parse_vm_stat(self):
        page, vm = memory.parse_vm_stat(VM_STAT)
        self.assertEqual(page, 16384)
        self.assertEqual(vm["Pages wired down"], 155625)
        self.assertEqual(vm["Translation faults"], 1606768271)

    def test_parse_swapusage(self):
        swap = memory.parse_swapusage(
            "vm.swapusage: total = 4096.00M  used = 2595.50M  free = 1500.50M  (encrypted)")
        self.assertEqual(swap["total"], 4096 * 1024**2)
        self.assertEqual(swap["used"], int(2595.5 * 1024**2))

    def test_parse_top(self):
        rows = memory.parse_top(TOP)
        self.assertEqual(sorted(rows), [416, 32108, 32134])
        self.assertEqual(rows[32108]["compressed"], 26 * 1024**2)
        self.assertEqual(rows[416]["purgeable"], 12 * 1024**2)

    def test_parse_ps_and_app_name(self):
        procs = memory.parse_ps(PS)
        self.assertEqual(procs[416]["user"], "_windowserver")
        self.assertEqual(memory.app_name(procs[32134]["path"]), "Claude")
        self.assertEqual(memory.app_name(procs[416]["path"]), "WindowServer")

    def test_breakdown_sums_to_total(self):
        page, vm = memory.parse_vm_stat(VM_STAT)
        vm["pageable_internal"] = 389473
        total = 1048576 * page
        parts = memory.breakdown(total, page, vm)
        self.assertEqual(sum(parts.values()), total)
        self.assertEqual(parts["app"], (389473 - 1329) * page)
        self.assertEqual(parts["cached"], (228301 + 1329) * page)


class SnapshotTest(unittest.TestCase):
    def test_snapshot_on_this_machine(self):
        snap = memory.snapshot()
        self.assertEqual(sum(snap["breakdown"].values()), snap["total"])
        self.assertTrue(snap["processes"])
        self.assertIn(snap["pressure"], {"normal", "warning", "critical"})


if __name__ == "__main__":
    unittest.main()
