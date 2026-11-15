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
| ~~F1: the agent loses 27.5% (English) / 10.0% (Hindi) of tasks to ASR~~ | One LLM sample per condition, 40 tasks per language, no noise floor, and the judge had bugs (section 3). | replaced by the tables in section 3 |
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
| Svarah (English), Whisper `large-v3` (Groq) (66 / 105) | raw ASR output | 16.7% | 18.2% | - |
|  | + exact lookup (default) | 16.7% | 16.7% | 0 / 105 |
|  | + exact + fuzzy | 13.6% | 13.6% | 0 / 105 |
| IndicVoices (Hindi), Whisper `large-v3` (Groq; broken baseline by the pre-flight rule, not compared) (242 / 115) | raw ASR output | 65.7% | 99.6% | - |
|  | + exact lookup (default) | 65.7% | 65.7% | 0 / 115 |
|  | + exact + fuzzy | 7.4% | 7.4% | 16 / 115 |

**A strong Indic ASR already recognises nearly all of these entities on clean audio.**
Saaras gets 66 of 66 Svarah mentions and 231 of 242 Hindi mentions right with no help.
What is left is canonicalisation (writing "Aadhaar" where the ASR wrote "आधार"), which
exact lookup does: Hindi canonical-form misses fall from 99.6% to 4.5%, and from 1.5% to
0.0% on Svarah, with no clean row corrupted. Fuzzy phonetic matching adds 9 Hindi and
0 Svarah mentions with Saaras, at no corruption measured (0 of 115 and 0 of 105 clean
rows); with local Whisper it adds 9 and 185 mentions, at 12 of 105 and 17 of 115 clean
rows corrupted (`play` → "Pradhan Mantri Awas Yojana", `coming` → "CoWIN", `हर` →
"Aadhaar"). The fuzzy layer is therefore optional (`EntityCorrector(mode="fuzzy")`);
exact lookup is the default. So, for entities on clean audio with **Saaras**, the
project's thesis is **refuted**: the ear is not where these fail. It is not refuted for
every ASR (next paragraph).

**Not every strong ASR recognises them.** Hosted Whisper `large-v3` (Groq, language forced;
[`docs/runs/3b-20-groq-large-v3.md`](docs/runs/3b-20-groq-large-v3.md)) misses 16.7% of the
Svarah mentions (11 of 66, 95% interval 9.6 to 27.4%), 6 of them CoWIN, where Saaras misses
none. Exact lookup cannot change that; exact + fuzzy recovers 2 of the 11 at no clean row
corrupted. On the Hindi rows it misses 65.7% of mentions with a 44.3% word error rate, but
it fails this project's baseline-sanity line (under 40%), so it is listed and not compared.
Which ASR is used, not the corrector, decides how many entities are lost.

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

## 3. Task success (F1): what ASR costs once the judge is fixed

F1 asks how much task success an agent loses to transcription: VoiceAgentBench
`single_tool` tasks (141 English, 134 Hindi, synthesized speech), Groq `gpt-oss-20b` as the
agent, each condition run three times. The original scoring was exact string match against a
benchmark that expects English argument values for Hindi queries, so those numbers were
withdrawn. The judge was repaired in two steps (a list-argument fix, then a meaning-level
LLM judge) and checked against 50 hand labels: Cohen's kappa **0.682**, 95% interval
0.465 to 0.878, 84% raw agreement
([`docs/runs/3b-19-meaning-judge.md`](docs/runs/3b-19-meaning-judge.md)).

How often the agent passes with **perfect** transcripts, under each judge:

| | Ground-truth text passes: exact-match judge as run | List-argument bug fixed | Plus meaning-level judge | Run-to-run noise floor (final judge) |
|---|---|---|---|---|
| English (141 tasks) | 53.2% | 65.0% | 73.3% | 5.0 pp |
| Hindi (134 tasks) | 32.1% | 38.6% | 64.7% | 3.7 pp |

Loss in task success when the ground-truth text is replaced by an ASR transcript (final
judge, mean over three runs, paired bootstrap, majority-vote McNemar):

| Language / ASR | Task success lost vs ground-truth text | 95% interval | Tasks only ground truth passes / only the ASR passes | McNemar p | Verdict |
|---|---|---|---|---|---|
| English / local Whisper `small` | 20.6 pp | 13.7 to 27.9 | 31 / 3 | 7.7e-07 | ASR costs task success |
| English / Saaras | 10.4 pp | 4.7 to 16.3 | 18 / 5 | 0.011 | ASR costs task success |
| Hindi / local Whisper `small` | 22.9 pp | 15.2 to 30.8 | 41 / 7 | 6.2e-07 | ASR costs task success |
| Hindi / Saaras | 7.7 pp | 2.2 to 13.4 | 19 / 9 | 0.087 | not distinguishable from LLM sampling noise |

- The exact-match judge was a measurement bug: it compared a returned list against each
  *element* of the expected list, so a correct list never passed, and it rejected correct
  Devanagari values. With it fixed, the Hindi ceiling is 64.7%, not 32.1%.
- ASR costs task success in three of four arms. For Hindi with Saaras the loss
  (7.7 points) is not distinguishable from LLM sampling noise (p = 0.087). Local Whisper
  `small` loses more in Hindi under the final judge (22.9 points) than under exact match
  (10.2).
- Even with perfect text the agent fails about 27% (English) and 35% (Hindi) of tasks,
  more than the ASR loss in every arm above.

Caveats that travel with these numbers:

1. **The judge is the agent's model family** (`gpt-oss-120b` judging `gpt-oss-20b`), and the
   check on it is one annotator and 50 labels: the kappa interval reaches below the 0.6
   bar. The judge was stricter than the annotator (6 of 8 disagreements), so some
   ceilings may be low.
2. **The benchmark's own system instruction was never sent** (arguments in English only,
   plus a one-shot example), the audio is synthesized, and each Whisper transcript is one
   draw from a non-deterministic ASR (8 of 30 re-transcriptions were identical) that no
   interval includes. Losses here are a lower bound on a real phone call.

The exact-match and list-fix results sit beside these in
[`results/f1_meaning_judge.json`](results/f1_meaning_judge.json).

## 4. Phone audio, digits and latency: measured so far, and not

- **Phone channel (simulated).** Through an 8 kHz mu-law phone leg (no packet loss or
  jitter), Saaras loses little on read speech: digit-string match 97.7% → 95.5% (English)
  and 82.1% → 82.1% (Hindi), entity recognition 100% → 98.5% and 95.5% → 95.0%, with no
  change that passes the preregistered 5-point and McNemar test
  ([`docs/runs/3b-18-phone-channel.md`](docs/runs/3b-18-phone-channel.md)). The Twilio Media
  Streams transport is tested only against a mock server (a Twilio trial account cannot
  stream), so no real call has been made.
- **Real telephone speech.** On 220 utterances (35 minutes) of real telephone Hindi from the Gram Vaani
  corpus, Saaras has a 26.5% word error rate (interval 24.7 to 28.5%) once numbers are normalised,
  and Whisper `large-v3` 54.5%. The simulated codec alone moved Saaras by 1.5 points on read
  speech. Do not read the gap to Saaras's 12.6% on the clean read rows as a channel effect: raw
  WER is 26.4% there and 27.2% here, and the two corpora differ in content (the clean rows are
  digit-heavy prompts), dialect and spontaneity
  ([`docs/runs/3b-21-real-telephone-hindi.md`](docs/runs/3b-21-real-telephone-hindi.md)).
- **Digit strings.** On clean audio, Saaras reproduces 92.0% of English
  and 84.1% of Hindi digit strings exactly (local Whisper `small`, English: 81.3%); the Hindi
  figure is likely an underestimate, and the normaliser was amended after reading misses
  ([`docs/runs/3b-17-digit-strings.md`](docs/runs/3b-17-digit-strings.md)). Hindi WER for
  Saaras is 26.4% as scored and 12.6% once numbers are normalised on both sides, so
  number formatting accounts for about half of it.
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
uv run python scripts/analyze_f1_meaning_judge.py  # -> results/f1_meaning_judge.json
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
