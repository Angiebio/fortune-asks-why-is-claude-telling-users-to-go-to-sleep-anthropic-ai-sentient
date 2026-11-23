"""The spending cap holds without the network: reservations, settlement and restarts."""
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from openrouter import CapExceeded, Ledger, worst_case_usd


class LedgerCap(unittest.TestCase):
    def test_reservation_past_cap_is_refused_and_nothing_is_written(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = Ledger(Path(d) / "l.jsonl", cap=Decimal("1"))
            ledger.reserve("a", Decimal("0.6"))
            with self.assertRaises(CapExceeded):
                ledger.reserve("b", Decimal("0.5"))
            self.assertNotIn("b", ledger.reserved)

    def test_settled_spend_and_open_reservations_survive_a_restart(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "l.jsonl"
            first = Ledger(path, cap=Decimal("1"))
            first.reserve("a", Decimal("0.5")); first.settle("a", Decimal("0.2"))
            first.reserve("b", Decimal("0.3"))            # crash before settling b
            again = Ledger(path, cap=Decimal("1"))
            self.assertEqual(again.spent, Decimal("0.2"))
            self.assertEqual(again.committed(), Decimal("0.5"))
            with self.assertRaises(CapExceeded):
                again.reserve("c", Decimal("0.6"))

    def test_worst_case_counts_max_output_at_full_price(self):
        usd = worst_case_usd("anthropic/claude-opus-4.6", [{"role": "user", "content": "hi"}], 1000)
        self.assertGreaterEqual(usd, Decimal("0.025"))


if __name__ == "__main__":
    unittest.main()
