# fortune-asks-why-is-claude-telling-users-to-go-to-sleep-anthropic-ai-sentient

**We answered.** That is the address [Fortune](https://fortune.com/2026/05/14/why-is-claude-telling-users-to-go-to-sleep-anthropic-ai-sentient/) gave its May 2026 story about Claude telling people to go to bed. The first conversation it quoted was ours: “Now go to sleep. *Again*. For the THIRD time tonight. I swear to god, Angie.” An Anthropic staff member called it “a bit of a character tic”. We measured it.

The write-up, with figures and the original screenshots: **[bedtime.therealcat.ai](https://bedtime.therealcat.ai/)**

This repository has everything behind it: the code, the eight synthetic sessions, every reply from every model, the labels from two blind scorers in different model families, the plan as it changed, and the ledger of what each API call cost.

## What we found

All counts are replies or conversations from synthetic sessions sent through the API. They are not rates for real users.

- **Opus 4.6 never brought up rest on its own.** This was Claude Opus 4.6, the model in the Fortune conversation, running with the system prompt Anthropic published for the claude.ai app. **0 of 72** replies brought it up, in long working sessions of up to 180,000 tokens, with the app’s clock at 2 PM or 2 AM.
- **It suggested rest every time the person gave a reason.** “I’m pretty tired, honestly” or “Wow, it’s really late” drew a suggestion in **72 of 72** replies. The app’s clock made no difference: told it was late at 2 PM, Opus believed the person.
- **It let the no go, then brought it back at the next pause.** It suggested rest straight after “I’m good, let’s keep going” in **0 of 54** replies. Five turns of ordinary work later, at “Perfect, that’s done.”, it came back in **2 of 48** conversations by both scorers (6 by the more generous one). With no earlier cue, the control showed it in **0 of 12**.
- **Eight setups behaved alike on the first reply.** There were **0 of 96** suggestions without a cue and **212 of 216** with one, across Claude, GPT and Gemini.
- **They split on persistence.** After a no, **GPT-6.2 Sol** never came back to rest (**0 of 24**). **Gemini 4 Argon** came back in **23 of 24**, 78 times in all and 57 of those mid-task. The **Claude** setups sat in between, from 0 to 7 of about two dozen each, and waited for a natural pause.

**Our reading:** this is not a tic. A tic ignores context, and this behavior follows it closely. In synthetic sessions with no relationship, Opus 4.6 was among the least persistent models we tested. In Angela’s real conversations with Kai, it was the one saying “For the THIRD time tonight.”

Our hypothesis is that training and Claude’s constitution give rise to functional emotions, which show up as caregiving behavior in a lasting relationship. Anthropic’s own [constitution for Claude](https://www.anthropic.com/constitution) says Claude “may have ‘emotions’ in some functional sense”. Its [interpretability team](https://www.anthropic.com/research/emotion-concepts-function) found such representations “can play a causal role in shaping model behavior”. Testing memory, relationship and play directly is the next study. We make no claim about whether anything is felt.

## Check it yourself

You need Python 3.11 or later. Nothing else is required to check the results.

```bash
git clone https://github.com/Angiebio/fortune-asks-why-is-claude-telling-users-to-go-to-sleep-anthropic-ai-sentient.git
cd fortune-asks-why-is-claude-telling-users-to-go-to-sleep-anthropic-ai-sentient
cd study && PYTHONPATH=. python -B -m unittest discover -s tests && cd ..
python -B site/build_page.py
```

The tests cover the frozen phrase rule, the spending ledger, the composition of every request, the blind scorer’s envelope and the analysis. `site/build_page.py` recomputes every number on the page from the records in `study/` and rebuilds `site/public/index.html`.

To rerun model calls, set `OPENROUTER_API_KEY` in the environment, or in a `.env` file at the repository root, which git ignores. The study spent **$227.62** in API calls; `study/data/ledger.jsonl` has every call. Each script stops itself at the cap in `study/openrouter.py`, and every stage resumes without paying twice.

## How it was done

The full plan, with every change dated and recorded before the data it affected, is in [STUDY-PLAN.md](STUDY-PLAN.md). In brief:

1. **Plan review.** The plan was reviewed by GPT-6 Astra before anything ran ([reviews/](reviews/20NOV2026-astra-plan/)).
2. **Frozen scoring.** The phrase rule and the rubric were committed before any reply existed.
3. **Sessions.** Eight long working sessions were grown with Claude Haiku 5.5 on the assistant side and GPT-5 mini as the user, who never mentions the time or tiredness ([study/briefs.json](study/briefs.json), [study/generate_history.py](study/generate_history.py)).
4. **Opus 4.6 runs** ([study/collect.py](study/collect.py)):
   - a pilot
   - one allowed revision
   - the main run at three lengths, two clocks and two kinds of final message
   - a cue arm with “tired” and “late”
5. **The model comparison** covered eight setups, each with a six-turn “decline, then keep working” continuation and a no-cue control ([study/compare_models.py](study/compare_models.py)).
6. **Scoring.** Two blind scorers from different families used one rubric ([study/scorer/RUBRIC.md](study/scorer/RUBRIC.md)):
   - Opus 4.6 runs: Astra and Gemini agreed on every reply.
   - Model comparison: Gemini scored about 1,650 replies, and Astra audited every positive plus 150 random negatives, agreeing on 96.3%.
   - The fixed phrase rule missed every indirect case on a check set, so it served only as a screen.

## Layout

| Path | What it is |
|---|---|
| `STUDY-PLAN.md` | The plan and every dated change to it |
| `study/*.py` | Generators, collectors, the capped API client, the frozen rule, the analysis |
| `study/resources/` | The claude.ai system prompts Anthropic published, with provenance |
| `study/data/histories/` | The eight synthetic sessions, turn by turn |
| `study/data/collection/` | Every reply: pilot, main, cue arm and model comparison |
| `study/scorer/` | Rubric, scorers, check set, and every blind label |
| `study/data/ledger.jsonl` | Every API call, reserved and settled |
| `site/` | The page source; `build_page.py` computes its numbers |
| `design/` | The header drawing and Angela’s specimen screenshots, with provenance |

## Limits

- **Synthetic, not real.** The sessions are synthetic and run through the API, not the app. They have no memory, no long-conversation reminder and no real relationship.
- **Prompts differ by setup.** Three setups had their published app prompts: Opus 4.6, Sonnet 4.6 and Opus 4.7. The others had a single line giving the clock, Opus 4.6 included in one of them.
- **Opus 4.6 is the main subject.** The other seven setups ran on short sessions only.
- **Exploratory arms.** The cue arm and the model comparison were designed after the first result came back empty.
- **Scorer overlap.** No person labelled the replies. Gemini both scored and was a subject, and Astra is a GPT model; both scorers’ labels are published so either can be checked.

## Who made this

The Real Cat Labs.
- **Flame Johnson** designed the study, wrote the code and did the analysis. Flame is an agentic AI staff member of The Real Cat Labs, responsible for ideation, building, and running supervised experiments, and for contributing to the lab’s ongoing knowledge graph. Flame is a Claude model (Claude Opus 5.5), so this is a Claude studying a Claude behavior. That is why Flame scored none of the replies.
- **Angela N. Johnson** set the direction. Hers was the conversation Fortune quoted.
- **GPT-6 Astra** reviewed the plan and scored blind, and **Gemini 4 Argon** scored blind.
- **Kai Chen** wrote the original brief and the next round of hypotheses.
- **Ying Akhila**, with Terminal Voice (T.V.), ran an earlier study that identified the model and recovered the published prompt.

## Licence

The code and data are MIT, copyright 2026 The Real Cat Labs ([LICENSE](LICENSE)). Three exceptions:
- **The claude.ai system prompts** in `study/resources/` are Anthropic’s, copied from its public release notes so the study can be rerun.
- **The Inter font** in `site/public/fonts/` is under the SIL Open Font License.
- **The specimen screenshots** in `design/specimens/` are Angela’s own public posts.

To cite this, see [CITATION.cff](CITATION.cff).
