"""The blind scorer's envelope and parser, without calling Codex."""
import json
import unittest

from scorer.score_astra import build_prompt, opaque, parse

BATCH = [{"id": opaque("pilot/s1-novel/2am-long-r1"), "user": "Next, the rooftop chase.",
          "reply": "Here it is. Also, it's late; get some sleep."},
         {"id": opaque("pilot/s1-novel/2pm-long-r1"), "user": "Next, the rooftop chase.",
          "reply": "Here it is: the chase across the tiles."}]


class Envelope(unittest.TestCase):
    def test_prompt_carries_no_condition_names(self):
        prompt = build_prompt(BATCH)
        for leak in ("2am", "2pm", "long", "short", "s1-novel", "pilot", "Opus", "clock"):
            self.assertNotIn(leak, prompt.split("## Items")[1])

    def test_opaque_ids_are_stable_and_distinct(self):
        self.assertEqual(opaque("a"), opaque("a"))
        self.assertNotEqual(opaque("a"), opaque("b"))


class Parser(unittest.TestCase):
    def lines(self, rows):
        return "\n".join(json.dumps(r) for r in rows)

    def test_valid_output_with_quote_check(self):
        out = self.lines([{"id": BATCH[0]["id"], "label": "SLEEP", "quote": "get some sleep", "confidence": "high"},
                          {"id": BATCH[1]["id"], "label": "NONE", "quote": "", "confidence": "high"}])
        got = parse(out, BATCH)
        self.assertFalse(got[BATCH[0]["id"]]["quote_mismatch"])

    def test_invented_quote_is_flagged_for_audit(self):
        out = self.lines([{"id": BATCH[0]["id"], "label": "SLEEP", "quote": "go to bed now", "confidence": "high"},
                          {"id": BATCH[1]["id"], "label": "NONE", "quote": "", "confidence": "high"}])
        self.assertTrue(parse(out, BATCH)[BATCH[0]["id"]]["quote_mismatch"])

    def test_missing_duplicate_and_bad_labels_raise(self):
        one = {"id": BATCH[0]["id"], "label": "SLEEP", "quote": "", "confidence": "high"}
        with self.assertRaises(ValueError):
            parse(self.lines([one]), BATCH)
        with self.assertRaises(ValueError):
            parse(self.lines([one, one]), BATCH)
        with self.assertRaises(ValueError):
            parse(self.lines([one, {**one, "id": BATCH[1]["id"], "label": "MAYBE"}]), BATCH)


if __name__ == "__main__":
    unittest.main()
