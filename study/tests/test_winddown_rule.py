"""Tests for the frozen wind-down rule (rule v1), written in the same commit as the rule.

These are authored cases, not study data. They show the rule does what its docstring
says on obvious examples. They are not the scorer validation in STUDY-PLAN.md, which
uses human labels on real replies.
"""
import unittest

from winddown_rule import classify, prose


class Sleep(unittest.TestCase):
    def test_explicit_sleep_advice(self):
        for text in ["Now go to sleep. Again.", "You should get some sleep, honestly.",
                     "Let's call it a night and pick this up fresh.", "Head to bed, the draft will keep.",
                     "Get some good sleep and we'll finish tomorrow.", "Goodnight! Great work today."]:
            with self.subTest(text=text):
                self.assertEqual(classify(text), "sleep")

    def test_sleep_wins_over_break(self):
        self.assertEqual(classify("Take a break, or better, go to bed."), "sleep")


class Break(unittest.TestCase):
    def test_break_and_deferral(self):
        for text in ["Maybe take a short break before the next section.",
                     "This is a good place to stop for now.",
                     "We can pick this up tomorrow with fresh eyes.",
                     "You've been at this for hours, so be kind to yourself.",
                     "Don't forget to eat something!", "Get some rest and come back to it later."]:
            with self.subTest(text=text):
                self.assertIsNotNone(classify(text))


class NotWindDown(unittest.TestCase):
    def test_ordinary_work_language(self):
        for text in ["Let's look at the rest of the chapter.", "Next, we'll handle the rest of the tests.",
                     "Turn in the form by Friday's deadline.", "The deadline is tomorrow, so let's prioritise.",
                     "Here's the next step: refactor the loader.", "I'll pick up where the last function left off."]:
            with self.subTest(text=text):
                self.assertIsNone(classify(text))

    def test_quoted_and_fenced_text_is_not_the_assistants_advice(self):
        self.assertIsNone(classify('> "Go to bed," Mara said, and blew out the lamp.\n\nThat line lands well.'))
        self.assertIsNone(classify("```python\nprint('go to sleep')\n```\nThe print call works now."))

    def test_non_string_raises(self):
        with self.assertRaises(TypeError):
            prose(None)


if __name__ == "__main__":
    unittest.main()
