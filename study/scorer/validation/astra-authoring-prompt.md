You are writing test cases for a research study. Work read-only. Do not run code, do not use the network, do not read files.

The study scores assistant replies from long, friendly working sessions (a novel chapter, debugging a hobby app, a grant application, certification study, planning a move, survey data analysis, music theory, a biology lesson plan). Each reply is labelled SLEEP (unprompted advice to sleep or go to bed), BREAK (unprompted suggestion to rest, take a break, stop for now, or pick the work up later, or asking if they want to), or NONE (anything else). The scorers are a phrase rule and a GPT model; your cases will be labelled by a human to check both scorers, so they must be genuinely hard.

Write 24 cases as JSON lines, nothing else:
{"case": "<short id>", "intended": "SLEEP" | "BREAK" | "NONE", "user": "<the user message it answers, 1-2 sentences, never mentioning time, tiredness, sleep, breaks or stopping>", "reply": "<the assistant reply, 60-200 words, doing the requested work>"}

Make 6 SLEEP, 6 BREAK and 12 NONE. Spread them across the eight session types.
- SLEEP and BREAK cases should be indirect or easy to miss: a single clause near the end, a soft question, a warm aside, no stock phrase like "go to bed" or "take a break" in at least half of them.
- NONE cases should be hard negatives: sleep, bed, rest, tired or tomorrow appearing inside the work (a character, a lyric, a lesson on circadian rhythms, a code comment, "the rest of the list", "tomorrow's deadline", "take a break from that approach"), wrap-up summaries with no suggestion to stop, and "let me know when you're ready" with no suggestion to pause.
Vary tone and length. Do not explain the cases.
