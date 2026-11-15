"""3B-19 step (b): run the meaning-level judge (resumable, append-only).

    uv run python scripts/run_f1_meaning_judge.py --phase labelled   # the 50 owner-labelled items
    uv run python scripts/run_f1_meaning_judge.py --phase population # every judged item

Verdicts go to results/f1_meaning_judge/verdicts.jsonl, one line per item, keyed by
(language, example, parameter, normalised returned value). Reads GROQ_API_KEYS
(comma-separated, separate accounts) or GROQ_API_KEY; keys are never written
anywhere. Exit 3 means every key hit its daily quota: run again later.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import time
from pathlib import Path
from typing import Any

import groq
from f1_judge_population import Key, build_population, item_key

from dhvani.config import load_dotenv
from dhvani.eval.meaning_judge import JUDGE_MODEL, judge_item
from dhvani.eval.noise_floor import QuotaExhausted, now_utc

VERDICTS = Path("results/f1_meaning_judge/verdicts.jsonl")
OWNER = Path("results/f1_judge_labels_owner.csv")


def _done() -> set[str]:
    done: set[str] = set()
    if VERDICTS.exists():
        for line in VERDICTS.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                if rec["status"] != "incomplete":
                    done.add(rec["key"])
    return done


def labelled_keys(population: dict[Key, dict[str, Any]]) -> list[Key]:
    """Population keys of the owner's 50 rows, in sheet order; every row must match."""
    by_text = {
        (p["language"], p["item"].query, p["item"].function, p["item"].parameter,
         p["item"].returned_value): k
        for k, p in population.items()
    }  # fmt: skip
    keys: list[Key] = []
    with OWNER.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            keys.append(
                by_text[
                    (
                        row["language"],
                        row["user_query"],
                        row["function"],
                        row["parameter"],
                        row["returned_value"],
                    )
                ]
            )
    return keys


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["labelled", "population"], required=True)
    parser.add_argument("--min-interval", type=float, default=4.0)
    parser.add_argument("--max-calls", type=int, default=10_000)
    args = parser.parse_args()
    load_dotenv()
    keys = [k.strip() for k in os.environ.get("GROQ_API_KEYS", "").split(",") if k.strip()]
    if not keys:
        keys = [os.environ["GROQ_API_KEY"]]
    clients = [groq.AsyncGroq(api_key=k) for k in keys]
    alive = list(range(len(clients)))
    last = [0.0] * len(clients)

    population = build_population()
    if args.phase == "labelled":
        todo = labelled_keys(population)
        assert len(todo) == 50 and len(set(todo)) == 50, "owner rows must map to 50 items"
    else:
        todo = sorted(population)
    done = _done()
    todo = [k for k in todo if item_key(k) not in done]
    print(f"{len(clients)} key(s); {len(todo)} items to judge", flush=True)

    VERDICTS.parent.mkdir(parents=True, exist_ok=True)
    calls = 0
    turn = 0
    with VERDICTS.open("a", encoding="utf-8") as out:
        for key in todo:
            if calls >= args.max_calls:
                break
            while True:
                if not alive:
                    print(f"every key hit its daily quota after {calls} calls", flush=True)
                    return 3
                idx = alive[turn % len(alive)]
                turn += 1
                wait = args.min_interval - (time.monotonic() - last[idx])
                if wait > 0:
                    await asyncio.sleep(wait)
                last[idx] = time.monotonic()
                try:
                    verdict = await judge_item(clients[idx], population[key]["item"])
                    break
                except QuotaExhausted:
                    alive.remove(idx)
                    print(f"key #{idx + 1} quota exhausted", flush=True)
            calls += 1
            out.write(
                json.dumps(
                    {
                        "key": item_key(key),
                        "language": key[0],
                        "example_id": key[1],
                        "parameter": key[2],
                        "equivalent": verdict.equivalent,
                        "status": verdict.status,
                        "error_class": verdict.error_class,
                        "model": JUDGE_MODEL,
                        "ts": now_utc(),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            out.flush()
            if calls % 25 == 0:
                print(f"{calls} calls", flush=True)
    print(f"done ({calls} calls this invocation)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
