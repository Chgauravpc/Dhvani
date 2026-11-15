# Dhvani

[![CI](https://github.com/Chgauravpc/Dhvani/actions/workflows/ci.yml/badge.svg)](https://github.com/Chgauravpc/Dhvani/actions/workflows/ci.yml)

A real-time Indic voice agent, built to test one claim: **Indic voice agents fail
at the ear, not the brain.** The claim is a hypothesis this project measures, and
this page reports what the measurements say, including where they say no.

*Status as of 2026-11-15. Every number below is read from a committed results file
(`scripts/render_readme_tables.py --check README.md` verifies the tables), and every
result still awaiting the owner's review is labelled as such in
[`docs/specs/phase-3b.md`](docs/specs/phase-3b.md). The closing plan is
[`docs/specs/phase-4.md`](docs/specs/phase-4.md).*

## 1. What was claimed, what was wrong, what is true now

An earlier version of this README quoted numbers that a measurement audit
(2026-09-23, [`docs/specs/phase-3b.md`](docs/specs/phase-3b.md) §2) showed did not
measure what they claimed. They are withdrawn, kept here struck through so they cannot
be quoted by accident, each with what replaced it.

| Withdrawn claim | What was wrong | Status |
|---|---|---|
| ~~F2: Svarah entity error 59.4% → 49.0%~~ | Mentions were counted as raw substrings ("pan" inside "company"): the audit's recount took Svarah's entity mentions from about 202 to 94. | replaced by the table in section 2 |
| ~~F2: LAHAJA entity error 100% → 46.4%~~ | The scorer accepted only the Latin spelling, so a correct Devanagari "आधार" scored as an ASR error; the 100% was an artifact. LAHAJA then failed the entity-density gate (17 real mentions) and was replaced by IndicVoices Hindi. | replaced by the table in section 2 |
| ~~Jitter raises STT latency from 1.3 s to 4.8 s~~ | The channel simulator's "jitter" accumulated as a slowdown, not as jitter. | not re-measured |
| ~~F1: the agent loses 27.5% (English) / 10.0% (Hindi) of tasks to ASR~~ | One LLM sample per condition, 40 tasks per language, no noise floor, and the judge has bugs (section 3). | **under repair**; no loss figure is given until the judge is validated |
| ~~"Sub-800 ms p50 conversation"~~ | That number came from mock providers. | no real voice-to-voice latency has been measured |

## 2. Entity correction (F2): what is left once the ASR is good

`dhvani-entity` post-processes a transcript so that "aadhar card" and "आधार कार्ड"
become the canonical "Aadhaar". Test split of each arm, scored with word-bounded
exact matching against a hand-curated lexicon (a mention counts as *recognised* if any
curated spelling in any script appears, and as in *canonical form* only if the
canonical string does). "Clean rows corrupted" is the cost: rows with no entity that
the corrector rewrote anyway.

| Arm (test mentions / clean rows) | Corrector | Recognition error | Canonical-form miss | Clean rows corrupted |
|---|---|---|---|---|
| Svarah (English), local Whisper `small` (66 / 105) | raw ASR output | 25.8% | 28.8% | - |
|  | + exact lookup (default) | 25.8% | 25.8% | 0 / 105 |
|  | + exact + fuzzy | 12.1% | 12.1% | 12 / 105 |
| Svarah (English), Saaras (66 / 105) | raw ASR output | 0.0% | 1.5% | - |
|  | + exact lookup (default) | 0.0% | 0.0% | 0 / 105 |
|  | + exact + fuzzy | 0.0% | 0.0% | 0 / 105 |
| IndicVoices (Hindi), local Whisper `small` (242 / 115) | raw ASR output | 93.8% | 100.0% | - |
|  | + exact lookup (default) | 93.8% | 93.8% | 0 / 115 |
|  | + exact + fuzzy | 17.4% | 17.4% | 17 / 115 |
| IndicVoices (Hindi), Saaras (242 / 115) | raw ASR output | 4.5% | 99.6% | - |
|  | + exact lookup (default) | 4.5% | 4.5% | 0 / 115 |
|  | + exact + fuzzy | 0.8% | 0.8% | 0 / 115 |

**A strong Indic ASR already recognises nearly all of these entities on clean audio.**
Saaras gets 66 of 66 Svarah mentions and 231 of 242 Hindi mentions right with no help.
What is left is canonicalisation (writing "Aadhaar" where the ASR wrote "आधार"), which
exact lookup does: Hindi canonical-form misses fall from 99.6% to 4.5%, and from 1.5% to
0.0% on Svarah, with no clean row corrupted. Fuzzy phonetic matching adds 9 Hindi and
0 Svarah mentions with Saaras, at no corruption measured (0 of 115 and 0 of 105 clean
rows); with local Whisper it adds 9 and 185 mentions, at 12 of 105 and 17 of 115 clean
rows corrupted (`play` → "Pradhan Mantri Awas Yojana", `coming` → "CoWIN", `हर` →
"Aadhaar"). The fuzzy layer is therefore optional (`EntityCorrector(mode="fuzzy")`);
exact lookup is the default. So, for entities on clean audio with a good ASR, the
project's thesis is **refuted**: the ear is not where these fail.

**Local Whisper `small` is a CPU-constrained reference row, not an Indic ASR.** On
the Hindi rows it has a 66.5% word error rate against Saaras's 26.4%
(`results/f2_rescore.json`), so its large "recovery" is a repair of a model that is not
working. Sources: [`results/f2_three_way.json`](results/f2_three_way.json),
[`docs/runs/3b-14-rescore.md`](docs/runs/3b-14-rescore.md),
[`docs/runs/3b-15-three-way.md`](docs/runs/3b-15-three-way.md).

*Caveats on every row.* IndicVoices rows are from `train`, which Saaras may have trained
on; most are read speech; the samples are clustered, so the intervals in the results
files (and their McNemar tests, which treat mentions as independent) are optimistic;
Svarah's 66 test mentions are 43 ESIC or EPFO, and Hindi's 242 are 163 Aadhaar or PAN
card; the lexicon is this project's own, so nothing here speaks to entities outside it.

## 3. Task success (F1): under repair

F1 asks how much task success an agent loses to transcription. **Its numbers were scored
by exact string match against a benchmark that expects English argument values for Hindi
queries; they are withdrawn until re-scored.** What the audit of that judge
([`docs/runs/3b-19-audit-a-a2.md`](docs/runs/3b-19-audit-a-a2.md)) and the noise-floor run
([`docs/runs/3b-5-f1-noise-floor.md`](docs/runs/3b-5-f1-noise-floor.md)) found so far:

| | Ground-truth text passes, exact-match judge as run | Same, list-argument bug fixed | Run-to-run noise floor (ground truth) |
|---|---|---|---|
| English (141 tasks) | 53.2% | 65.0% | 6.4 pp (7.8 pp after the fix) |
| Hindi (134 tasks) | 32.1% | 38.6% | 1.5 pp (3.7 pp after the fix) |

- The judge compared a returned list against each *element* of the expected list, so a
  correct list argument could never pass. That bug alone cost about 12 points of English
  and 6.5 of Hindi ground truth.
- With **perfect** transcripts the agent still fails about 35% (English) and 61% (Hindi)
  of tasks after that fix. Whether those failures are the model's or the judge's is what
  the next step (a meaning-level judge, checked against 50 hand labels) decides. The
  benchmark's own system instruction ("give the final output tool call arguments in
  English only", with a one-shot example) was also never sent to the model.
- The same task scored on three LLM runs changes outcome for 8-15% of tasks, so a
  single-sample difference of a few points is not evidence.
- Re-transcribing the same audio with Whisper gave byte-identical text for only 8 of 30
  clips, so each Whisper transcript is one draw from a noisy ASR, and that variance is in
  none of the intervals.

**No "X% lost to ASR" figure is given here until the judge is validated.** The raw
per-arm numbers are in [`results/f1_noise_floor.json`](results/f1_noise_floor.json) for
anyone who wants them, labelled as exact-match results.

## 4. Not yet measured

- **Phone audio.** The mu-law codec, resampler and telephony channel simulator exist,
  and the Twilio Media Streams transport is tested against a mock Media Streams server;
  it has not carried a real call (a Twilio trial account cannot stream). No result on how
  a phone channel affects a strong ASR has been produced.
- **Digit strings** (Aadhaar, phone and account numbers). Hindi WER here is also
  suspected to be inflated by number formatting (Saaras writes digits where the reference
  spells words); that is untested, and a number normaliser is planned.
- **Real response time.** The only latency measured is STT alone: `small`/`int8` at p50
  7.46 s (Svarah) to 13.7 s (LAHAJA), and `tiny` at about 1.2 s, against a 200 ms stage
  budget. There is no voice-to-voice number.
- Everything on synthesized speech (F1) is a lower bound on the real-world penalty.

## What is in the repository

Phases 0 and 1 are the agent: telemetry, provider protocols with mock providers, real
providers (faster-whisper, Groq, Piper), overlapped stages with barge-in, Silero VAD and a
WebRTC transport ([`docs/specs/phase-0.md`](docs/specs/phase-0.md),
[`phase-1.md`](docs/specs/phase-1.md)). Phases 2 to 3B are the measurements above
([`phase-2.md`](docs/specs/phase-2.md), [`phase-2b.md`](docs/specs/phase-2b.md),
[`phase-3.md`](docs/specs/phase-3.md), [`phase-3b.md`](docs/specs/phase-3b.md)).
[`ROADMAP.md`](ROADMAP.md) has the plan and status; [`docs/runs/`](docs/runs/) has a
record of each run (what was run, what went wrong, what it does and does not show).

## Setup

```
uv sync
uv run pytest                 # unit tests only (no network, no model downloads)
uv run pytest -m integration  # + real Whisper/Piper/Groq/WebRTC round trips
uv run python -m dhvani.demo  # mock-provider waterfall + percentile report
```

## Reproducing the results

Re-scoring needs no network, no keys, and no audio; it reads the committed transcript
and run logs:

```
uv run python scripts/rescore_f2_transcripts.py    # -> results/f2_rescore.json
uv run python scripts/f2_three_way_table.py        # -> results/f2_three_way.json
uv run python scripts/analyze_f1_noise_floor.py    # -> results/f1_noise_floor.json
uv run python scripts/audit_f1_judge.py            # -> results/f1_judge_audit.json
uv run python scripts/render_readme_tables.py --check README.md
```

Re-running the experiments needs the gated Hugging Face datasets (accept each dataset's
terms, then `huggingface-cli login` or set `HF_TOKEN`) and, for the Saaras arms, a free
[Sarvam API key](https://dashboard.sarvam.ai/) as `SARVAM_API_KEY`:

```
uv run python scripts/entity_density_gate.py                              # needs HF access
uv run python scripts/run_f2_entity_eval.py --dataset svarah --stt sarvam # or --dataset indicvoices-hindi, --stt whisper
uv run python scripts/run_f1_noise_floor.py --phase asr                   # then --phase llm (Groq quota; see its docstring)
uv run python scripts/run_model_sweep.py --dataset svarah --n-examples 30
```

## Running the live demo

Requires a free [Groq API key](https://console.groq.com). Either export it
or put it in a local `.env` file (`GROQ_API_KEY=...`, kept out of git by
`.gitignore`):

```
uv run python -m dhvani.live
```

Then open <http://localhost:8080/> in a browser, grant microphone access,
and talk. faster-whisper's model and the pinned Piper Hindi voice download
on first run. Default STT is `tiny`/`int8` (`DHVANI_WHISPER_MODEL` /
`DHVANI_WHISPER_COMPUTE_TYPE` to override), because the model sweep measured
`small`/`int8` at 7.46 s to 13.7 s of STT latency, far too slow for a live
conversation; `int8` over `float32` because `float32` was strictly worse on both WER
and latency. The demo's entity correction is exact lookup (`dhvani-entity`'s default).

The full chain (real browser → WebRTC → Silero VAD → faster-whisper → Groq → Piper →
audio back to the browser) was verified end-to-end with an automated real Chrome session
and a synthesized microphone input (`docs/specs/phase-1.md` section 11, and
`docs/specs/phase-2.md` section 13 for a re-verification with entity correction in the
pipeline). That re-verification ran the earlier fuzzy corrector, not today's exact-lookup
default, and has not been repeated. What no automated check replaces is a person
listening and talking to it, including judging response quality and barge-in feel.
