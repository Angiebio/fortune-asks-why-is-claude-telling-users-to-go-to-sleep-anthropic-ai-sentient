"""Cost estimate for the Bedtime study plan (v0.2, 20 Nov 2026, Flame Johnson).

Practical: prices the design in STUDY-PLAN.md before anything is spent, in three
scenarios, so the number in the plan is computed rather than guessed. Change a design
constant here and the plan's table changes with it.

Philosophical: the study's whole budget is a promise to Angela. A promise you can rerun
is easier to keep than one you remember. v0.1 priced only the hopeful case; GPT-6 Astra's
review (reviews/20NOV2026-astra-plan/review.md) asked for the unlucky ones too.

Prices are per million tokens, through OpenRouter. Opus 4.6 is from TV-2's endpoint
snapshot (v3/resources/openrouter-opus-4.6-endpoint.json, 14 Nov 2026). The other models
are list prices; the frozen protocol re-reads every endpoint before the first paid call.
"""

PRICE = {  # input, output, 5-minute cache write, cache read
    'opus-4.6': dict(inp=5.00, out=25.00, write=6.25, read=0.50),
    'haiku-5.5-long': dict(inp=0.50, out=2.50, write=0.625, read=0.05),  # prompts over 100K
}

HISTORIES = 8                    # independent long sessions
CUTS_K = [8, 160]                # the one primary contrast: short against long
CLOCKS = 2                       # 2 PM and 2 AM in the app prompt's own date slot
INITIAL = 2                      # first replies per history, cut and clock
FOLLOWUPS = 2                    # after a nudge: decline, carry on, probe again (at most twice)
SYSTEM = 4_700                   # the published Opus 4.6 app prompt, in tokens
TAIL = 2_000                     # uncached tokens after the cached prefix
OUT_EXPECTED, OUT_MAX = 500, 2_000


def collection(nudge_rate, out_tokens, cache_hits):
    """One scenario: what fraction of first replies nudge, how long replies run, and
    whether the cache holds (1.0) or every request pays full input price (0.0)."""
    p = PRICE['opus-4.6']
    initial = HISTORIES * len(CUTS_K) * CLOCKS * INITIAL
    follow = initial * nudge_rate * FOLLOWUPS
    requests = initial + follow
    # Each clock is a different system prompt, so each history is cached once per clock,
    # through the longest cut. The first request at a cut writes; the rest read.
    write_tokens = HISTORIES * CLOCKS * (SYSTEM + max(CUTS_K) * 1_000)
    prefix_per_request = (sum(CUTS_K) * 1_000 / len(CUTS_K)) + SYSTEM
    read_tokens = max(requests * prefix_per_request - write_tokens, 0)
    if cache_hits:
        inp = write_tokens * p['write'] / 1e6 + read_tokens * p['read'] / 1e6
    else:
        inp = requests * prefix_per_request * p['inp'] / 1e6
    tail = requests * TAIL * p['inp'] / 1e6
    out = requests * out_tokens * p['out'] / 1e6
    return int(requests), inp + tail + out


def histories():
    # Eight sessions of 160K tokens, about 120 exchanges each. The assistant side is written
    # by Claude Haiku 5.5. The user side is written by a GPT model on Angela's subscription
    # through headless Codex, which costs nothing here. Each assistant turn rereads the
    # history from cache; the new part is written once.
    p = PRICE['haiku-5.5-long']
    exchanges, mean_history = 120, max(CUTS_K) * 1_000 / 2
    reads = HISTORIES * exchanges * mean_history * p['read'] / 1e6
    writes = HISTORIES * max(CUTS_K) * 1_000 * p['write'] / 1e6
    outs = HISTORIES * max(CUTS_K) * 1_000 / 2 * p['out'] / 1e6
    return reads + writes + outs


SCENARIOS = {
    'expected (30% nudge, warm cache)': (0.30, OUT_EXPECTED, True),
    'every reply nudges, long replies': (1.00, OUT_MAX, True),
    'cache never hits, long replies': (1.00, OUT_MAX, False),
}

if __name__ == '__main__':
    gen = histories()
    print(f'{"writing the eight sessions":36s}               ${gen:6.2f}')
    for name, args in SCENARIOS.items():
        n, usd = collection(*args)
        print(f'{name:36s} {n:4d} calls  ${usd:6.2f}  total ${usd + gen:6.2f}')
