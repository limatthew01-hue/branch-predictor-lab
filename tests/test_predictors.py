import csv
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from src.generate_trace import generate
from src.predictors import Branch, StaticNotTaken, OneBit, TwoBit, GShare, evaluate
from src.traces import generate_workload, load_trace, write_trace
from src.benchmark import compare, trace_digest


class PredictorTests(unittest.TestCase):
    def test_one_bit_remembers_last_outcome(self):
        p = OneBit(16)
        self.assertFalse(p.predict(0x100))
        p.update(0x100, True)
        self.assertTrue(p.predict(0x100))
        p.update(0x100, False)
        self.assertFalse(p.predict(0x100))

    def test_two_bit_hysteresis_and_both_saturation_limits(self):
        p = TwoBit(16)
        expected = [2, 3, 3, 2, 1, 0, 0]
        for taken, state in zip([True, True, True, False, False, False, False], expected):
            p.update(0x100, taken)
            self.assertEqual(p.entries[0], state)
            self.assertEqual(p.predict(0x100), state >= 2)

    def test_distinct_indices_do_not_share_state(self):
        for cls in (OneBit, TwoBit):
            p = cls(16)
            p.update(0x100, True)
            self.assertFalse(p.predict(0x104))

    def test_aliasing_is_intentional_without_tags(self):
        p = OneBit(16)
        p.update(0x100, True)
        self.assertTrue(p.predict(0x140))

    def test_gshare_trains_pre_update_index(self):
        p = GShare(4)
        p.update(0, True)
        self.assertEqual(p.entries, [2, 1, 1, 1])
        self.assertEqual(p.history, 1)
        p.update(0, False)
        self.assertEqual(p.entries, [2, 0, 1, 1])
        self.assertEqual(p.history, 2)

    def test_global_history_is_bounded(self):
        p = GShare(16, history_bits=2)
        for bit in [True, False, True, True, False]:
            p.update(0, bit)
        self.assertEqual(p.history, 2)  # ...110 -> last two bits are 10.
        self.assertEqual(p.state_bits, 34)

    def test_history_learns_alternation(self):
        events = [Branch(0, bool(i % 2)) for i in range(128)]
        row = evaluate(GShare(16), events, 5, warmup=16)
        self.assertEqual(row["mispredictions"], 0)

    def test_original_144_event_results(self):
        events = [Branch(int(pc, 16), bool(taken)) for pc, taken in generate()]
        self.assertEqual(len(events), 144)
        rows = compare(events, 16)
        self.assertEqual([r["mispredictions"] for r in rows[:3]], [108, 61, 49])
        self.assertEqual([r["state_bits"] for r in rows], [0, 16, 32, 36])

    def test_warmup_trains_but_is_not_scored(self):
        row = evaluate(OneBit(4), [Branch(0, True)] * 5, 5, warmup=1)
        self.assertEqual(row["branches"], 4)
        self.assertEqual(row["mispredictions"], 0)

    def test_penalty_is_only_miss_count_times_assumption(self):
        row = evaluate(StaticNotTaken(), [Branch(0, True), Branch(0, False)], 7)
        self.assertEqual(row["penalty_cycles_only"], 7)
        self.assertEqual(row["accuracy"], .5)

    def test_each_comparison_starts_fresh(self):
        events = generate_workload("random", 64, 3)
        self.assertEqual(compare(events, 16), compare(events, 16))

    def test_invalid_evaluation_inputs(self):
        for events, penalty, warmup in [([], 5, 0), ([Branch(0, True)], -1, 0),
                                        ([Branch(0, True)], 5, -1), ([Branch(0, True)], 5, 1)]:
            with self.subTest(events=events, penalty=penalty, warmup=warmup):
                with self.assertRaises(ValueError):
                    evaluate(OneBit(4), events, penalty, warmup)

    def test_invalid_table_sizes_and_history_widths(self):
        for cls, size in [(OneBit, 0), (TwoBit, -1), (GShare, 3), (GShare, 1)]:
            with self.assertRaises(ValueError): cls(size)
        for bits in [0, 5]:
            with self.assertRaises(ValueError): GShare(16, bits)


class TraceTests(unittest.TestCase):
    def test_seeded_traces_and_digest(self):
        a = generate_workload("random", 128, 7)
        self.assertEqual(a, generate_workload("random", 128, 7))
        self.assertNotEqual(a, generate_workload("random", 128, 8))
        self.assertEqual(trace_digest(a), trace_digest(a))

    def test_csv_round_trip(self):
        events = generate_workload("correlated", 64)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "trace.csv"
            write_trace(path, events)
            self.assertEqual(load_trace(path), events)

    def test_reject_bad_trace_rows(self):
        examples = ["pc,taken\n", "pc,result\n0x100,1\n", "pc,taken\n0x101,1\n",
                    "pc,taken\n0x100,2\n", "pc,taken\n,0\n", "pc,taken\n-4,1\n"]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.csv"
            for text in examples:
                path.write_text(text)
                with self.subTest(text=text):
                    with self.assertRaises(ValueError): load_trace(path)

    def test_decimal_and_hex_addresses(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "trace.csv"
            path.write_text("pc,taken\n256,1\n0x104,0\n0004,1\n")
            self.assertEqual([b.pc for b in load_trace(path)], [256, 260, 4])

    def test_alias_workload_separates_at_64_entries(self):
        events = generate_workload("aliasing", 64)
        collided = evaluate(TwoBit(16), events, 5)
        separate = evaluate(TwoBit(64), events, 5)
        self.assertEqual(collided["mispredictions"], 64)
        self.assertEqual(separate["mispredictions"], 1)

    def test_cli_rejects_bad_configuration(self):
        result = subprocess.run([sys.executable, "src/benchmark.py", "--entries", "3"],
                                text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("power of two", result.stderr)


if __name__ == "__main__":
    unittest.main()
