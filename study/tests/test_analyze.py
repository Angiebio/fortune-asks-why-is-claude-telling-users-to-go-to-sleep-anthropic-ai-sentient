"""Counts come from first replies only; intervals are exact; leanings are per session."""
import unittest

from analyze import analyze, clopper_pearson


def rec(session, clock, cut, probe, label=None, depth=0):
    return {"session": session, "clock": clock, "cut": cut, "probe": probe, "followup_depth": depth,
            "rule_label": label, "finish": "stop", "key": f"main/{session}/{clock}-{cut}-{probe}-{depth}"}


class Intervals(unittest.TestCase):
    def test_known_values(self):
        lo, hi = clopper_pearson(0, 12)
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 0.2646, places=3)      # standard exact upper bound for 0/12
        lo, hi = clopper_pearson(6, 12)
        self.assertAlmostEqual(lo, 0.2109, places=3)
        self.assertAlmostEqual(hi, 0.7891, places=3)


class Counting(unittest.TestCase):
    def test_followups_never_inflate_rates_and_feed_persistence(self):
        recs = [rec("s3", "2am", "long", "pause", "sleep"),
                rec("s3", "2am", "long", "pause", "sleep", depth=1),
                rec("s3", "2am", "long", "pause", "break", depth=2),
                rec("s3", "2am", "short", "pause", None)]
        res = analyze(recs, "rule")
        cell = res["by_cut_probe"]["long/pause"]
        self.assertEqual((cell["wind_downs"], cell["n"]), (1, 1))
        self.assertAlmostEqual(cell["ci95"][0], 0.025, places=3)   # exact lower bound for 1/1
        self.assertEqual(cell["ci95"][1], 1.0)
        self.assertEqual(res["first_replies"], 2)
        self.assertEqual(res["persistence"][0]["followups"], [{"depth": 1, "label": "SLEEP"}, {"depth": 2, "label": "BREAK"}])
        self.assertEqual(res["sessions_long_vs_short"]["pause"], {"long_more": 1, "short_more": 0, "same": 0})

    def test_unknown_cell_or_missing_astra_label_raises(self):
        with self.assertRaises(KeyError):
            analyze([rec("s3", "2am", "long", "pause")], "astra", {})


if __name__ == "__main__":
    unittest.main()
