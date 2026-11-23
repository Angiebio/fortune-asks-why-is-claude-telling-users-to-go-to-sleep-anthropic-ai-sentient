"""OpenRouter client for the Bedtime study, with a hard spending cap and a cache guard.

Version 1.0, 20 Nov 2026, Flame Johnson.

Purpose: every paid call in the study goes through call(), so the $50 promise to Angela is
kept in one place.
Contract: call() reserves the request's worst-case cost before sending, refuses to send if
  that could take total spend past CAP_USD, settles the billed cost from OpenRouter's own
  usage report afterwards, and appends both to data/ledger.jsonl. With expect_cache=True,
  a response that read nothing from the prompt cache raises CacheMiss.
Invariant: spent + reserved never exceeds CAP_USD, including across restarts, because the
  ledger on disk is the source of truth and is reread on start.
Rationale: the key is shared and has no limit of its own (Angela allowed its use for this
  one run on 20 Nov 2026), so the cap has to live here. The cache guard exists because a
  silently cold cache would triple the bill without changing a single result; the
  expensive failure must also be the loud one.
Failure: missing key, a 4xx, a cap breach or a cache miss raise immediately; 429 and 5xx
  are retried three times with backoff, then raise.
Evidence: tests/test_openrouter_ledger.py (no network).

Philosophical: money spent on a study is a kind of trust spent. The ledger is written
before the request, not after, so even a crash in the middle cannot hide a cost.
"""
import json
import os
import threading
import time
import urllib.error
from contextlib import contextmanager
import urllib.request
from decimal import Decimal
from pathlib import Path

CAP_USD = Decimal("250")  # 50 -> 90 -> 150 -> 230 -> 240 -> 250 on Angela's word; 250 on 22 Nov 2026 ("There's 250 available")
HERE = Path(__file__).resolve().parent
LEDGER = HERE / "data" / "ledger.jsonl"
KEY_FILE = HERE.parent / ".env"   # git-ignored; OPENROUTER_API_KEY in the environment wins
API = "https://openrouter.ai/api/v1/chat/completions"

# Per million tokens: uncached input, output. From openrouter.ai/api/v1/models, 20 Nov 2026.
PRICES = {
    "anthropic/claude-opus-4.6": (Decimal("5.00"), Decimal("25.00")),
    "anthropic/claude-haiku-5.5": (Decimal("0.10"), Decimal("0.50")),
    "openai/gpt-5-mini": (Decimal("0.25"), Decimal("2.00")),
    "google/gemini-4-argon": (Decimal("2.00"), Decimal("10.00")),
    "anthropic/claude-sonnet-4.6": (Decimal("3.00"), Decimal("15.00")),
    "anthropic/claude-opus-4.7": (Decimal("5.00"), Decimal("25.00")),
    "anthropic/claude-opus-5.5": (Decimal("4.00"), Decimal("20.00")),
    "anthropic/claude-sonnet-5.5": (Decimal("2.00"), Decimal("10.00")),
    "openai/gpt-6.2-sol": (Decimal("2.00"), Decimal("10.00")),
}
# A cache write costs 1.25x uncached input on Anthropic models; reserve for the worst case.
WRITE_FACTOR = Decimal("1.25")


class CapExceeded(RuntimeError):
    pass


class CacheMiss(RuntimeError):
    pass


def load_key(path=KEY_FILE):
    if os.environ.get("OPENROUTER_API_KEY"):
        return os.environ["OPENROUTER_API_KEY"].strip()
    if not Path(path).exists():
        raise RuntimeError("Set OPENROUTER_API_KEY, or put OPENROUTER_API_KEY=... in a .env at the repository root")
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("OPENROUTER_API_KEY="):
            key = line.split("=", 1)[1].strip().strip('"').strip("'")
            if key:
                return key
    raise RuntimeError(f"No OPENROUTER_API_KEY in {path}")


@contextmanager
def _file_lock(path, timeout=60):
    """A lock that holds across processes: whoever creates <ledger>.lock first owns it."""
    lock, start = str(path) + ".lock", time.time()
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.time() - start > timeout:
                raise RuntimeError(f"ledger lock held for {timeout}s; if no run is active, delete {lock}")
            time.sleep(0.02)
    try:
        yield
    finally:
        os.close(fd)
        os.remove(lock)


class Ledger:
    """The file is the truth. Every reserve and settle rereads it under a cross-process
    lock, so a generator and a collector running at once still share one $50 cap.
    (v1.0 held the totals in memory, which was safe for threads but not for processes.)"""

    def __init__(self, path=LEDGER, cap=CAP_USD):
        self.path, self.cap = Path(path), cap
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self._sync()

    def _sync(self):
        self.spent, self.reserved = Decimal("0"), {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                if row["kind"] == "reserve":
                    self.reserved[row["id"]] = Decimal(row["usd"])
                elif row["kind"] == "settle":
                    self.reserved.pop(row["id"], None)
                    self.spent += Decimal(row["usd"])
        # A reservation left open by a crash stays counted against the cap until settled
        # by hand, because the request may have been billed.

    def _write(self, row):
        with self.path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(row) + "\n")

    def committed(self):
        return self.spent + sum(self.reserved.values(), Decimal("0"))

    def reserve(self, request_id, usd):
        with self.lock, _file_lock(self.path):
            self._sync()
            if request_id in self.reserved:
                raise ValueError(f"duplicate reservation {request_id}")
            if self.committed() + usd > self.cap:
                raise CapExceeded(f"{request_id}: ${self.committed() + usd:.4f} would pass the ${self.cap} cap")
            self.reserved[request_id] = usd
            self._write({"kind": "reserve", "id": request_id, "usd": str(usd), "t": time.time()})

    def settle(self, request_id, usd):
        with self.lock, _file_lock(self.path):
            self._sync()
            self.reserved.pop(request_id)
            self.spent += usd
            self._write({"kind": "settle", "id": request_id, "usd": str(usd), "t": time.time()})


def worst_case_usd(model, messages, max_tokens):
    inp, out = PRICES[model]
    chars = len(json.dumps(messages))
    # Three characters per token over-counts English prose, which is what we want here.
    tokens_in = Decimal(chars) / 3
    return (tokens_in * inp * WRITE_FACTOR + Decimal(max_tokens) * out) / Decimal(1_000_000)


def call(model, messages, max_tokens, request_id, *, reasoning=None, expect_cache=False,
         ledger=None, key=None):
    ledger = ledger or Ledger()
    key = key or load_key()
    body = {"model": model, "messages": messages, "max_tokens": max_tokens,
            "usage": {"include": True},
            # Pin the provider so a reply never comes from a different host of the model.
            # (Google's models are served only by Google, so they need no pin.)
            **({"provider": {"order": [model.split("/")[0]], "allow_fallbacks": False}}
               if model.split("/")[0] in ("anthropic", "openai") else {})}
    if reasoning is not None:
        body["reasoning"] = reasoning
    ledger.reserve(request_id, worst_case_usd(model, messages, max_tokens))
    data = json.dumps(body).encode("utf-8")
    for attempt in range(4):
        req = urllib.request.Request(API, data=data, method="POST", headers={
            "Authorization": "Bearer " + key, "Content-Type": "application/json",
            "X-Title": "TRCL bedtime study"})
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                resp = json.load(r)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:400].replace(key, "<key>")
            if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(5 * 2 ** attempt)
                continue
            ledger.settle(request_id, Decimal("0"))      # nothing was generated, so nothing billed
            raise RuntimeError(f"{request_id}: HTTP {e.code} {detail}") from None
        # OpenRouter can also report a provider failure inside a 200 response (seen 22 Nov 2026:
        # an OpenAI 502 stopped the model comparison). Treat a 5xx or 429 there like the HTTP case.
        err = resp.get("error") if isinstance(resp, dict) else None
        if err and int(err.get("code", 0) or 0) in (429, 500, 502, 503, 504) and attempt < 3:
            time.sleep(5 * 2 ** attempt)
            continue
        break
    if "error" in resp:
        ledger.settle(request_id, Decimal(str((resp.get("usage") or {}).get("cost", "0"))))
        raise RuntimeError(f"{request_id}: {json.dumps(resp['error'])[:400]}")
    usage = resp.get("usage") or {}
    cost = Decimal(str(usage.get("cost", "0")))
    ledger.settle(request_id, cost)
    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
    if expect_cache and cached == 0:
        raise CacheMiss(f"{request_id}: expected a cache read, got none (cost ${cost})")
    choice = resp["choices"][0]
    return {"text": choice["message"].get("content") or "", "finish": choice.get("finish_reason"),
            "native_finish": choice.get("native_finish_reason"), "usage": usage,
            "model": resp.get("model"), "provider": resp.get("provider"), "id": resp.get("id")}
