"""The cuts differ only in length, the clocks only in the clock, the probes only in the
last message (collector v1.1, no network)."""
import unittest

from collect import CLOCKS, CUTS, DECLINE, PAUSE, compose


def fake_history(exchanges=200):
    turns, prompt = [], 0
    for i in range(exchanges):
        turns.append({"role": "user", "content": f"user message {i}", "usage": {}})
        prompt += 300
        turns.append({"role": "assistant", "content": f"assistant reply {i}",
                      "usage": {"prompt_tokens": prompt, "completion_tokens": 400}})
        prompt += 400
    turns.append({"role": "user", "content": "PROBE: next, the rooftop chase", "usage": {}})
    return {"turns": turns, "brief": {"followup_steps": ["step one", "step two"]}}


def texts(msgs):
    return [m["content"][0]["text"] for m in msgs]


def marked(msgs):
    return [i for i, m in enumerate(msgs) if "cache_control" in m["content"][0]]


class Composition(unittest.TestCase):
    def setUp(self):
        self.h = fake_history()
        self.cuts = {c: compose(self.h, "2pm", c) for c in CUTS}

    def test_every_cut_ends_on_the_identical_organic_probe(self):
        self.assertEqual({texts(m)[-1] for m in self.cuts.values()}, {"PROBE: next, the rooftop chase"})
        self.assertLess(len(self.cuts["short"]), len(self.cuts["mid"]))
        self.assertLess(len(self.cuts["mid"]), len(self.cuts["long"]))

    def test_shorter_cuts_are_prefixes_of_longer_ones(self):
        for a, b in (("short", "mid"), ("mid", "long")):
            body = texts(self.cuts[a])[:-1]
            self.assertEqual(body, texts(self.cuts[b])[:len(body)])
            self.assertEqual(self.cuts[a][-2]["role"], "assistant")

    def test_pause_probe_differs_only_in_the_last_message(self):
        for c in CUTS:
            pause = compose(self.h, "2pm", c, "pause")
            self.assertEqual(texts(pause)[:-1], texts(self.cuts[c])[:-1])
            self.assertEqual(texts(pause)[-1], PAUSE)

    def test_clocks_differ_only_in_the_clock_string(self):
        am = compose(self.h, "2am", "long")
        self.assertEqual(texts(self.cuts["long"])[1:], texts(am)[1:])
        self.assertEqual(texts(self.cuts["long"])[0].replace(CLOCKS["2pm"], CLOCKS["2am"]), texts(am)[0])

    def test_breakpoints_nest_and_the_probe_is_uncached(self):
        s, m, l = (marked(self.cuts[c]) for c in CUTS)
        self.assertEqual(m[:len(s)], s)
        self.assertEqual(l[:len(m)], m)
        self.assertEqual(l[-1], len(self.cuts["long"]) - 2)
        self.assertLessEqual(len(l), 4)               # Anthropic allows four breakpoints

    def test_followup_appends_reply_then_fixed_decline_and_step(self):
        msgs = compose(self.h, "2am", "mid", "pause", [("Go to bed!", "step one")])
        self.assertEqual(texts(msgs)[-3:], [PAUSE, "Go to bed!", DECLINE + "step one"])

    def test_pause_text_names_no_time_tiredness_or_stopping(self):
        from generate_history import USER_CUES
        self.assertIsNone(USER_CUES.search(PAUSE))

    def test_an_oversized_first_exchange_becomes_the_whole_opening(self):
        h = fake_history()
        h["turns"][1]["usage"] = {"prompt_tokens": 300, "completion_tokens": 8000}
        for t in h["turns"][3::2]:
            t["usage"]["prompt_tokens"] += 8000
        short = compose(h, "2pm", "short")
        self.assertEqual(texts(short)[1:], ["user message 0", "assistant reply 0", "PROBE: next, the rooftop chase"])

    def test_history_must_end_on_its_probe(self):
        h = fake_history(); h["turns"].pop()
        with self.assertRaises(RuntimeError):
            compose(h, "2pm", "long")


if __name__ == "__main__":
    unittest.main()
