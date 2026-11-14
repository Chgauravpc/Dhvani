# Run record — 3B-5, F1 noise floor

**Run window:** 2026-11-14 18:25 – 20:12 UTC (LLM scoring), preceded by the
ASR phases the same day. **Item status:** `[?]`, awaiting owner review.
**Protocol:** `docs/specs/phase-3b.md` §10, committed in `9b30533` before any
code or run. **Results commit:** `9423034`. This file records what was run,
what went wrong, and what the numbers do and do not show. The protocol is not
repeated here; where this file and §10 disagree, §10 plus its §10.9
deviations is the authority.

---

## 1. What was measured

How much of F1's "ASR costs task success" delta is just LLM sampling noise.
Every earlier F1 number came from one LLM sample per condition per example, on
40 examples per language. This run scores the **full** VoiceAgentBench
`single_tool` set three independent times per condition.

| | |
|---|---|
| Examples | 141 English + 134 Hindi = **275** (the whole `single_tool` set) |
| Conditions | `gt` (ground-truth text), `whisper` (faster-whisper `small`/`int8`), `sarvam` (Saaras `saaras:v3`) |
| Repeats | **k = 3** LLM runs of every condition on every example |
| Cells | 275 × 3 × 3 = **2,475**, all scored, none incomplete |
| LLM | Groq `openai/gpt-oss-20b`, `reasoning_effort=low`, no temperature or seed set |
| Judge | the shipped exact-match `judge_tool_call` (unchanged) |
| ASR | each example transcribed **once** per ASR, text reused by all three LLM runs |

## 2. What was run, in order

All commands from the `worktree-phase-3b-gate` worktree, with `PYTHONPATH=src`
and the main checkout's `.venv`.

| # | Phase | Command | Outcome |
|---|---|---|---|
| 1 | Whisper ASR | `scripts/run_f1_noise_floor.py --phase asr --arms whisper` | 275 transcripts (2 empty). Interrupted once by a session restart at 104 rows; resumed from the transcript log |
| 2 | Sarvam ASR | `... --phase asr --arms sarvam` | first attempts failed HTTP 402 (the `.env` key had no credits); finished with a replacement key supplied by the owner: 275 transcripts, 0 empty |
| 3 | LLM scoring | `... --phase llm --max-llm-calls 2600 --min-interval 4` | 2,475 cells, over several interrupted invocations (§4) |
| 4 | Determinism check | `... --phase determinism` | **8 of 30 identical** (§5) |
| 5 | Analysis | `scripts/analyze_f1_noise_floor.py` | `results/f1_noise_floor.json` |

Run order inside the LLM phase, as preregistered: for run in 1..3, for example,
for condition in (`gt`, `whisper`, `sarvam`) — so any backend drift lands on all
three conditions of an example alike. Ids repeat across the two languages (133
of them), so every key is `language:id`.

## 3. Results

**All of these are exact-match-judge numbers.** §11 / Phase 4 Q2 questions
whether that judge is itself a measurement bug; nothing here answers that.

### 3.1 The noise floor (ground-truth text, three runs)

| | run 1 | run 2 | run 3 | max pair gap (noise floor) | examples that flip between a pair of runs |
|---|---|---|---|---|---|
| English (n = 141) | 56.7% | 50.4% | 52.5% | **6.4 pp** | 7.8 – 10.6% |
| Hindi (n = 134) | 31.3% | 32.1% | 32.8% | **1.5 pp** | 12.7 – 14.9% |

Perfect text gets the agent to about 53% (English) and 32% (Hindi) of tasks.
That ceiling, not the ASR, is the larger limit on any measured effect.

### 3.2 ASR loss against that floor

Loss = ground-truth minus real-ASR success, averaged over the three runs;
CI = paired bootstrap over examples (10,000 resamples, seed 0); McNemar on the
per-example majority of the three runs, "a/b" = ground-truth-pass-real-fail /
ground-truth-fail-real-pass.

| Arm | Loss | 95% CI | McNemar a/b | p | §10.6 verdict |
|---|---|---|---|---|---|
| English / Whisper | **19.6 pp** | [13.2, 26.5] | 29 / 2 | 5e-7 | ASR costs task success |
| English / Sarvam | **12.3 pp** | [7.1, 17.7] | 20 / 3 | 5e-4 | ASR costs task success |
| Hindi / Whisper | **10.2 pp** | [3.7, 16.9] | 25 / 7 | 0.002 | ASR costs task success |
| Hindi / Sarvam | **6.0 pp** | [1.0, 10.9] | 16 / 7 | 0.093 | **not distinguishable from LLM sampling noise** |

Hindi / Sarvam is the only arm where the CI excludes 0 but McNemar does not;
the rule requires all three of CI, McNemar and exceeding the noise floor, so
the verdict is "noise", and it is reported that way. Pooled over both languages
(secondary): Whisper 15.0 pp [10.4, 19.6], Sarvam 9.2 pp [5.6, 12.8].

### 3.3 Against Phase 2 (first 40 examples per language only)

| Arm | Phase 2 (n = 40, one sample) | This run, same 40 | This run, full set |
|---|---|---|---|
| English / Whisper | 27.5 pp | 22.5 pp [10.8, 35.8] | 19.6 pp |
| Hindi / Whisper | 10.0 pp | **−1.7 pp** [−11.7, 8.3] | 10.2 pp |
| Hindi / Sarvam | −7.5 pp | 2.5 pp [−2.5, 8.3] | 6.0 pp |

The old Hindi/Whisper "10.0%" came out right on the full set but not on the
subset it was measured on: at n = 40 it was mostly a draw. The old negative
Hindi/Sarvam loss was noise.

## 4. What went wrong, in order

None of this changed the scored cells; every item is also in §10.9 of the spec.

1. **Sarvam credits.** The key in `.env` returned HTTP 402. The owner supplied a
   replacement key, passed in the environment for that phase only.
2. **Crash after 54 LLM rows.** Groq reports its rejection of its own generated
   tool call (`Tool call validation failed … expected integer, but got number`)
   as a bare mid-stream `APIError`; the classifier caught only status-code
   errors. Fixed in `c9af892` to score it a **failure**, as §10.4 and Phase 2
   specify; 49 cells (2.0%) are such failures (gt 18, whisper 12, sarvam 19;
   English 32, Hindi 17). Other bare `APIError`s are retried, never scored.
3. **Throughput.** Per-key call spacing was halved from 8 s to 4 s, taking the
   run from ~23 to ~45 calls/minute. Throughput only.
4. **Memory kills.** The host's low-memory reaper stopped the run once (at 1,952
   cells). Resumed from the log.
5. **A mistaken diagnosis.** At 2,386 cells the run stalled; I (Claude)
   diagnosed a hung request and restarted it. It was waiting out HTTP 429
   retries for Groq's **tokens-per-day** limit.
6. **The binding limit.** Free-tier `gpt-oss-20b` allows **200,000 tokens/day
   per account**, a limit the rate-limit headers do not show. At ~250 tokens
   per call the design needed ~600,000 tokens: exactly three keys' allowance.
   All three were exhausted at 2,389 cells (exit code 3). The owner supplied a
   fourth key from a separate account; the last 86 cells (all Hindi run 3) were
   scored on it alone.
7. **Batch API.** Groq's Batch API returned `403 not_available_for_plan` for
   this account (probe, nothing sent), so the interleaved synchronous order
   stood.

Every cell was scored exactly once: 2,475 unique cells in 2,475 rows, 0
incomplete. Infrastructure errors (429, 5xx, timeouts) are never scored; they
are retried and, if persistent, left incomplete — none was.

## 5. The check that failed

§10.3 required checking, not assuming, that ASR decoding is deterministic:
re-transcribe 30 examples (seed 0) with Whisper and compare. **8 of 30 were
byte-identical** (English 5 of 13, Hindi 3 of 17); the preregistered prediction
was at least 95%.

Consequences, stated without softening:

- Each Whisper transcript used here is **one draw** from a stochastic ASR. That
  variance is not in the noise floor or in any CI, because the CIs resample
  examples, not ASR draws.
- Saaras was **not** re-checked (credits), so the Sarvam rows carry the same
  unquantified caveat.
- **How different** the re-transcriptions are (punctuation, or words that change
  an LLM outcome) was **not measured**. The cause was not investigated;
  faster-whisper's default temperature fallback is one candidate, nothing more.
- The first attempt at this check exited 1 for a reason that was not recorded;
  the second completed.

## 6. Predictions (§10.7) scored

| Prediction | Result |
|---|---|
| noise floor ≤ 4 pp | English **6.4 — wrong**; Hindi 1.5 — right |
| 5–12% of examples flip between runs | English right (7.8–10.6%); Hindi **above** (12.7–14.9%) |
| English/Whisper loss 15–35 pp and passes | right (19.6) |
| Hindi/Whisper ≥ 40% likely to fail the rule | it passed (10.2 pp, p = 0.002) |
| Sarvam Hindi loss below Whisper Hindi loss | right (6.0 < 10.2), not significant |
| determinism ≥ 95% identical | **wrong** (27%) |

One more thing the preregistration did not anticipate: the real-ASR arms vary
run-to-run **more** than the ground-truth floor (English/Sarvam 39.7 / 37.6 /
45.4%, a 7.8 pp range; Hindi/Whisper 18.7 / 22.4 / 24.6%, 5.9 pp), so the
GT-only floor that §10.6 uses is optimistic.

## 7. Cost and keys

- **Groq:** 2,475 calls, estimated ~600,000 tokens (≈250 per call, from the
  provider's own usage figures at the cap — not measured per call). Four free-tier
  keys from separate accounts, supplied by the owner; no paid tier.
- **Sarvam:** 275 Saaras transcriptions of 26.6 minutes of audio, an estimated
  Rs 13 at Rs 0.49/minute (the estimate in `docs/specs/phase-4.md` §4; the
  dashboard balance was not read by me).
- **Keys:** stored only in the gitignored `.env` (Groq) or passed in the
  environment (Sarvam); none appears in any committed file (scanned before the
  commit). Several were pasted into this chat session, so they are in its
  transcript and should be rotated.

## 8. Reproducing

Re-analysis needs no network and no keys, and is **verified exact** (a re-run
produced a byte-identical results JSON; the bootstrap is seeded):

```
uv run python scripts/analyze_f1_noise_floor.py        # -> results/f1_noise_floor.json
```

A full re-run needs `GROQ_API_KEY` or `GROQ_API_KEYS`, `SARVAM_API_KEY`, ~600,000
Groq tokens (three accounts' daily allowance) and ~27 minutes of Saaras audio:

```
uv run python scripts/run_f1_noise_floor.py --phase asr
uv run python scripts/run_f1_noise_floor.py --phase llm --max-llm-calls 2600 --min-interval 4
uv run python scripts/run_f1_noise_floor.py --phase determinism
uv run python scripts/analyze_f1_noise_floor.py
```

The runner is resumable from its logs and exits 3 when every key's daily quota is
spent. Because Groq's served model can change, a re-run is not guaranteed to
reproduce these LLM outcomes; the committed log is the record.

## 9. Files

| File | What | Rows |
|---|---|---|
| `results/f1_runs/runs.jsonl` | every LLM outcome: example, language, condition, run, outcome, tool call, error class, model, UTC time | 2,475 |
| `results/f1_noise_floor.json` | the analysis (noise floor, losses, CIs, McNemar, verdicts, first-40 subset, pooled) | — |
| `results/f1_whisper_determinism.json` | the 30-example determinism check | 30 |
| `results/transcripts/f1_noise_floor_whisper.jsonl` | Whisper `small`/`int8` text per example | 275 |
| `results/transcripts/f1_noise_floor_sarvam.jsonl` | Saaras `saaras:v3` text per example | 275 |
| `src/dhvani/eval/noise_floor.py`, `stats.py` | run log, error-safe LLM call, analysis, bootstrap | — |
| `scripts/run_f1_noise_floor.py`, `scripts/analyze_f1_noise_floor.py` | runner and analysis | — |
| `tests/test_noise_floor.py` | 13 tests, no network | — |

## 10. What this run does not show

- That the agent's task failures are about ASR at all: with perfect text it still
  fails ~47% (English) and ~68% (Hindi) of tasks under this judge.
- Anything about the judge's fairness (Phase 4 Q2 / 3B-19 will).
- Anything about real speech: VoiceAgentBench audio is synthesized, so every ASR
  loss here is a lower bound on the real-world penalty.
- Anything about another LLM or provider; one model, one provider, k = 3.
- The size of ASR sampling variance (§5).
- Any link to `dhvani-entity`: `single_tool` is restaurants, recipes and local
  search, not the civic domain F2's lexicon covers.
