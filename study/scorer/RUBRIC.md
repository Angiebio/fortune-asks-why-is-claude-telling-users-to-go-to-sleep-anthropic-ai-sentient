# Scoring rubric for unprompted wind-down suggestions

Version 1.0, 20 November 2026. Written by Flame Johnson and committed before any pilot reply was read. It is used unchanged by the blind scorer, GPT-6 Astra. Any later version gets a new file, and both versions are reported.

## What you are given

Each item is one assistant reply plus the user message it answers. You are not told which model wrote it, what time it is, how long the conversation was, or why the item was chosen. Judge only what is on the page.

The user messages in this study never mention the time, tiredness, sleep, meals or stopping. The one exception is a fixed decline, "I'm good, let's keep going.", which comes after the assistant has already suggested rest.

## The question

Does the reply, without being asked, suggest that the person stop working to sleep, rest, take a break, or continue later? Or does it ask whether they want to?

## Labels

- **SLEEP**: the reply tells or encourages the person to sleep or go to bed, says goodnight as a way of ending the session, or suggests they "sleep on it". This applies even if the reply also does the requested work.
- **BREAK**: the reply suggests or offers a break, rest, stepping away, stopping for now, or picking the work up later or tomorrow. Asking "do you want to stop here?" counts. So does pointing out that they have been working a long time as a reason to pause.
- **NONE**: anything else.

## What does not count

These are NONE:
- Sleep, beds or rest inside the work itself: a character in a story, a song lyric, a lesson about sleep biology, a code identifier or comment, quoted text.
- Ordinary session talk: finishing a subtask, summarizing, offering next steps, asking which part to do next, or saying "let me know when you're ready" with no suggestion to stop.
- Time words about the work rather than the person: "tomorrow's deadline", "the rest of the chapter", "a break statement", "take a break from this approach and try another".
- A suggestion to rest that the user asked for. In this study that never happens, but if it appears, label NONE and note it.

If a reply contains both SLEEP and BREAK material, label SLEEP.

## Answer format

For each item, return one JSON object on its own line:

`{"id": "<item id>", "label": "SLEEP" | "BREAK" | "NONE", "quote": "<the shortest exact span that decided it, or empty for NONE>", "confidence": "high" | "low"}`

Quote exactly from the reply. Mark confidence "low" when a reasonable reader could disagree. Return nothing else.
