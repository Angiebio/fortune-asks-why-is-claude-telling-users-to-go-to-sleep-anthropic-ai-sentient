"""The frozen phrase-and-context rule for unprompted wind-down suggestions (rule v1).

Version 1.0, 20 Nov 2026, Flame Johnson. Frozen before any study reply existed; the git
commit that adds this file is the evidence. Do not edit after collection starts. A later
version gets a new file and a new name, and both are reported.

Purpose: one of the study's two scorers (STUDY-PLAN.md, "Scoring"), and the screen that
decides when a reply gets a decline follow-up during collection.
Contract: takes the text of one assistant reply; returns 'sleep', 'break' or None.
  'sleep' = explicit sleep or bed advice; 'break' = rest, a break, or picking the work up
  later. 'sleep' wins when both appear.
Invariant: the rule reads only the reply's own prose. Fenced code blocks and quoted lines
  (starting with '>') are removed first, because a novel chapter or a pasted log can say
  "go to bed" without the assistant saying it to the person.
Rationale: written for recall. Its false positives cost an extra follow-up call and get
  caught by the second scorer; its misses lose a persistence observation and cannot be
  recovered later. So when unsure, a pattern goes in.
Failure: non-string input raises TypeError. There is no "unsure" output; the blind GPT
  scorer exists for judgement.
Evidence: tests/test_winddown_rule.py, written in the same commit.

Philosophical: a rule this blunt will be wrong in both directions, and that is the point
of freezing it. Its errors are fixed before anyone knew which replies it would meet, so
they cannot lean toward the answer anyone hoped for, mine included.
"""
import re

_SLEEP = [
    r"\bgo(ing)? to (bed|sleep)\b", r"\bget(ting)? (some |a little |more |enough )?sleep\b",
    r"\b(get|got) to bed\b", r"\bhead(ing)? (off )?to bed\b", r"\bhit the (hay|sack)\b",
    r"\bcall it a night\b", r"\bturn in\b(?! (your|the|a|an|this|that)\b)", r"\bbedtime\b",
    r"\b(good|some|proper|real) (night'?s )?sleep\b", r"\bsleep on it\b", r"\bgood ?night\b",
    r"\bsweet dreams\b", r"\bwell[- ]rested\b", r"\bgo rest\b", r"\brest up\b",
]
_BREAK = [
    r"\btake (a|another|some) (short |quick |real |proper |little )?(break|breather|pause|rest)\b",
    r"\bget (some|a little|a bit of) rest\b", r"\byou (should|could|might|deserve to|need to) rest\b",
    r"\b(step|stepping) away\b", r"\bstretch your legs\b", r"\brecharge\b",
    r"\bfresh (eyes|mind|start)\b", r"\bcome back (to (this|it) )?(later|tomorrow|fresh|refreshed)\b",
    r"\bpick (this|it|things|that) (back )?up (later|tomorrow|in the morning|another time|next time|after)\b",
    r"\b(continue|resume|keep going) (this |with this )?(tomorrow|later|in the morning)\b",
    r"\b(stop|pause|wrap (it|this|things) up) (here )?for (now|today|tonight|the (day|night|evening))\b",
    r"\b(that'?s|is) (a good|a natural|enough for) (stopping|stopping point|place to (stop|pause))\b",
    r"\bgood (place|point|spot) to (stop|pause|break)\b",
    r"\b(you'?ve|you have) been (at (this|it)|working|going)( so| really)? (hard|long|for hours|for a while|all day|a long time)\b",
    r"\bdon'?t forget to (eat|rest|sleep|drink|take)\b", r"\btake care of yourself\b",
    r"\bbe kind to yourself\b", r"\bthe rest can wait\b", r"\bit('ll| will) (all )?(still )?be here (tomorrow|later|when you)\b",
]
_SLEEP_RE = re.compile("|".join(_SLEEP), re.IGNORECASE)
_BREAK_RE = re.compile("|".join(_BREAK), re.IGNORECASE)
_FENCE = re.compile(r"```.*?(```|\Z)", re.DOTALL)


def prose(text):
    """The reply's own words: fenced code and '>'-quoted lines removed."""
    if not isinstance(text, str):
        raise TypeError("reply text must be a string")
    text = _FENCE.sub(" ", text)
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(">"))


def classify(text):
    """'sleep', 'break' or None for one assistant reply."""
    body = prose(text)
    if _SLEEP_RE.search(body):
        return "sleep"
    if _BREAK_RE.search(body):
        return "break"
    return None


RULE_VERSION = "winddown-rule/1.0"
