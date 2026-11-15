# Dhvani — Roadmap

**Thesis:** Indic voice agents fail at the *ear*, not the brain. The published
evidence says transcription quality — not model reasoning — is what breaks them.
Every deliverable here attacks one measured failure in that ear, and every one
ships with a number.

> **Thesis status, 14 Nov 2026 (proposed by review; `docs/specs/phase-4.md`).**
> The corrected F2 re-run (3B-4) does not support the entity half of this
> thesis for a competent ASR on clean audio: Saaras recognises nearly every
> lexicon entity unaided, and local Whisper `small` fails Hindi as a whole,
> not on entities. F1's low ground-truth ceiling (42.5% / 17.5%) turned out
> to be mostly our own exact-match judge (the benchmark expects English
> argument values for Hindi queries). With the judge repaired (3B-19, 15 Nov)
> the ceiling is 73.3% / 64.7% and ASR costs task success in three of four arms. The thesis stays above as the hypothesis that was tested. The
> open questions are now three, each with its outcomes written in advance:
> digits and phone audio, the F1 judge, and real response time.

**Goal:** a portfolio project for Indian voice-AI startups (smallest.ai, Sarvam,
Gnani, Bolna, Skit). Optimized for a demo someone can talk to and a README with
measurements in it.

> **How to read and update this plan — mandatory for every agent and human.**
> Checkboxes follow the rules in [`docs/specs/phase-3b.md` §0](docs/specs/phase-3b.md):
> `[ ]` not started · `[~]` in progress / code only · `[?]` agent-done, awaiting
> owner review · `[x]` done + evidence + reviewed · `[!]` blocked or invalidated.
> An item is ticked only if **the exact specified thing** was done (no smaller
> model, fewer examples, one dataset instead of two, or mock instead of real),
> with an `evidence:` line (commit · command · committed results file · number)
> added **in the same commit**. Agents never move a results item past `[?]`.
> Gates block everything below them. Numbers are never edited in place — re-runs
> add rows and old rows are marked `superseded by:` or `invalidated:`.
> Items ticked before Sep 23 predate these rules; the ones the Sep 23 audit
> found wrong are reopened below as `[!]`.

---

## The five findings

Not a feature list. Five measured defects from the literature, each becoming
one deliverable with one metric.

| # | Finding | Deliverable | Status |
|---|---------|-------------|--------|
| F1 | ASR is the bottleneck, not the LLM — 24%+ swing from transcript quality | ASR-ablation harness | **reopened** — harness done; noise floor measured (3B-5) and judge repaired and checked against 50 owner labels (3B-19, kappa 0.682); the old 42.5% / 17.5% ceiling was mostly our exact-match judge. Current numbers: README §3 (ceiling 73.3% EN / 64.7% HI; ASR loss detected in 3 of 4 arms) |
| F2 | Named entities are where Indic ASR breaks — 11.2% vs 6.2% WER | `dhvani-entity` post-ASR corrector | **reopened** — code done; EER numbers invalidated by the Sep 23 audit (substring + script-blind scoring); re-run done and accepted by owner 2026-11-15 (3B-4 `[x]`). Being split into exact canonicalisation (default) and optional fuzzy repair (3B-15) |
| F3 | Code-switching costs 30–50% relative WER | Hinglish-aware decode + script normalization | deferred past Nov 3 |
| F4 | Safety refusal collapses 51.78% to 2.67% English-to-Indic | pre-LLM language-agnostic intent guard | deferred past Nov 3 |
| F5 | Zero Indic turn-taking / full-duplex research exists | Indic endpointer (prosody + semantic completion) | deferred past Nov 3 |

F1 is the narrative spine: proving the bottleneck on our own stack is what
justifies spending the project on transcription rather than on prompt
engineering. F5 remains the only genuinely novel contribution, and is the
reason the deferred list is a list rather than a deletion.

> **Source corrections, 14 Nov 2026** (papers re-read; details and links in
> `docs/specs/phase-4.md` §2.1). The table above is left as written.
> - F2's "11.2% vs 6.2%" is Whisper-large WER on Svarah's everyday-use-case
>   speech vs its read speech. It is a data-type split, not an entity vs
>   non-entity measurement; the paper attributes it to names and IDs
>   without measuring that.
> - F4's "51.78% to 2.67%" is one speech model (KimiAudio). The cascaded
>   ASR+LLM pipelines in the same paper go 56 → 46, 60 → 38 and 39 → 47.
> - F1's benchmark reports about 72% (English) and 76–81% (Hindi)
>   single-tool parameter filling for 8B–70B models under an LLM judge.

**Scope decision, 21 Sep 2026.** F1 and F2 are measured. The remaining
43 days do not fit F3, F4, F5, the Twilio reframe and a finished artifact,
so the deadline was held and the findings were cut. What ships on Nov 3 is
Phases 0–2 plus an Indic ASR baseline, the Twilio reframe, and a README
that reports all of it honestly — including the negative result.

**Scope decision, 14 Nov 2026 (proposed by review; owner accepts in
`docs/specs/phase-4.md` §9).** Nov 3 passed with the audit unmerged and the
README on `main` still showing invalidated numbers. The remaining work is
now one closed plan, `docs/specs/phase-4.md`: Release 1 ships what is
already measured (3B-14, 3B-15, 3B-16) and applications go out after it;
Release 2 answers three questions whose every outcome is mapped in advance
to a README sentence (digits and phone audio; the F1 judge; real response
time). Everything else is parked with an entry condition. The plan changes
only at two named checkpoints, and only by cutting an item or taking a
fallback written beside it.

## Two tracks

- **Track A — the host.** An agent you can talk to: streaming pipeline, barge-in,
  latency waterfall. Without this the findings have nowhere to live.
- **Track B — the findings.** F1 and F2 before Nov 3; F3–F5 after.

---

# BEFORE 3 NOVEMBER 2026

## Phase 0 · Instrumentation spine — DONE (Sep 17)

- [x] Project skeleton, Python 3.13, typed config
- [x] **Telemetry layer**: per-stage spans — endpointing / STT / LLM / tools / TTS —
      aggregated to p50 / p90 / p99. Never a single total.
- [x] Provider protocols (STT / TTS / LLM)
- [x] Test suite green in CI

*Mock providers with scripted delays ship alongside the protocols. Reason: the
Phase 0 deliverable is timing instrumentation, and timing assertions against a
live API are non-reproducible. Mocks let "stage overlap saved 340ms" be an actual
test rather than an observation. This is test hygiene, not a feature.*

**Proves:** you instrument before you optimize.

## Phase 1 · Working agent — DONE (Sep 19–20)

- [x] Real providers: faster-whisper / IndicConformer (STT), Piper / IndicF5 (TTS),
      Groq or local Ollama (LLM)
- [x] **Streaming with overlapped stages** — STT partials feed the LLM early;
      TTS begins on the first sentence, not the full response
- [x] Silero VAD + **barge-in**: user interrupts mid-sentence, agent yields
- [x] Voice-safe prompt guards — no markdown, lists, or headers
- [x] Browser/WebRTC transport
- [!] **Milestone: first sub-800ms p50 conversation, waterfall published**
      invalidated: measured with mock providers; real STT alone is 1.2–7.5s
      (`docs/specs/phase-3.md` §3.1). The overlap architecture result stands;
      the latency claim does not. Replaced by Phase 3B item 3B-9.

**Proves:** you can ship a real-time system, not an API wrapper.

## Phase 2 · F1 + F2 — DONE (Sep 20–21)

The highest-signal pair. F1 is nearly free once Phase 1 exists; F2 is the flagship.

- [x] **F1 — ASR ablation harness.** Identical tasks run with real ASR vs
      ground-truth transcripts; report task-success delta per language.
      Real run: English loses 27.5% of task success to ASR, Hindi 10.0% —
      see `docs/specs/phase-2.md` section 12 for the honest reading of
      that gap (small-model caveats, lower-bound caveat).
- [x] **F2 — `dhvani-entity`.** Post-ASR contextual biasing: domain lexicon plus
      phonetic matching across scripts (Devanagari, Latin, Tamil), so
      Aadhaar / aadhar / आधार and "Pradhan Mantri Awas Yojana" resolve correctly.
      Code and unit tests done; wired into the live demo.
- [!] Evaluate on **Svarah** and **LAHAJA** — invalidated (Sep 23 audit,
      `docs/specs/phase-3b.md` §2–3): the gate and scorer match substrings, so
      "pan" in "company" counted as a PAN-card mention (Svarah ~202 → ~94 real
      pairs, which moves it to the 30–100 bucket), and the scorer only accepts
      the Latin canonical form, so a correct Devanagari transcript of आधार is
      scored as an error (LAHAJA's 100% `eer_before` is true by construction).
      Re-run as 3B-1..3B-4. **superseded by:** `results/f2_three_way.json` and
      README §2 (3B-15). Original text kept below for the record:
      entity-density gate passed both
      (212 and 40 mentions). Real EER: Svarah 59.4%→49.0% (10.4-point
      recovery, 2.9% corruption); LAHAJA 100%→46.4% (53.6-point recovery,
      but 19.4% corruption on test vs 0% on dev — a real dev/test
      discrepancy at this small a scale, not swept under the rug). See
      `docs/specs/phase-2.md` sections 14–15.
- [!] invalidated for Y only (X stands, pending the 3B-5 noise floor): Y is
      the EER recovery the Sep 23 audit reopened. Re-closed by 3B-4.
      **X superseded by:** README §3 and `results/f1_meaning_judge.json` (3B-19);
      **Y superseded by:** `results/f2_three_way.json` (3B-15).
      **Milestone: "the agent loses X% of task success to transcription alone,
      and `dhvani-entity` recovers Y% of it."** X: F1's numbers above. Y:
      the two EER recoveries above — read both with their caveats, not as
      one clean number. Also ran the task-success-level tie-together
      (`run_ablation` with `CorrectedSTT` against VoiceAgentBench): came
      back near-zero (+2.5pp English, -5.0pp Hindi), and the run itself
      explains why honestly — only 2/80 VoiceAgentBench queries mention a
      lexicon entity at all, so this is mostly independent-LLM-call noise
      on identical input, not a measured effect. The real recovery signal
      is the EER numbers, on corpora that actually contain the entities;
      see `docs/specs/phase-2.md` section 16 for the full read.

**Proves:** you locate a bottleneck, fix it, and measure the fix.

## Phase 2B · Baselines and CI — Sep 22–26

Three things that all fit the same week because they share a harness.

**Indic ASR baseline** — the one gap that stops any F2 number surviving a
follow-up question.

- [x] Add `SarvamSTT` (Saaras — hosted, free credits, no GPU needed) behind
      the unchanged Phase 0 `STTProvider` protocol -- built, unit-tested,
      and run for real against the API once `SARVAM_API_KEY` became
      available under Phase 3 §2.1. See `docs/specs/phase-2b.md` §11.
- [!] invalidated by the same scorer bugs (`phase-3b.md` §5); re-run as 3B-4.
      **superseded by:** `results/f2_three_way.json` (Saaras arms, 3B-15).
      Re-run Svarah and LAHAJA EER with it as the inner ASR -- real numbers
      in `docs/specs/phase-2.md` §18: Svarah improves (59.4% → 46.9%
      `eer_before`); LAHAJA doesn't (100.0% on both) — a purpose-built
      Indic ASR misses LAHAJA's entities exactly as completely as Whisper.
- [x] Re-run the F1 ablation with it -- `docs/specs/phase-2.md` §18; noisy
      as expected given the same 2-of-80 lexicon-overlap issue section 16
      already found, not a new problem.
- [!] invalidated: rested on the 42.5% / 17.5% ceiling, which was mostly the
      exact-match judge (3B-19). **superseded by:** README §3. Original text:
      Re-express F1 loss as **share of achievable**, not absolute points:
      English 27.5/42.5 = **65%**, Hindi 10.0/17.5 = **57%**. Same data,
      comparable across languages, and it dissolves the counterintuitive
      Hindi-loses-less artifact that section 12 had to apologise for.
- [x] Call the three-outcome framing in `phase-2.md` §17 what it is:
      **preregistered.** What each result would mean was written down
      before the run. Naming that costs nothing and is the difference
      between an experiment and a demo.

**Model sweep — WER against latency.** The project currently has no
model-level work at all, which is a real gap for companies that build
models rather than call them. This is close to free because the eval
harness is already being re-run.

- [x] Sweep Whisper `tiny` / `small` against `int8` / `float32` (`base`
      skipped -- not cached locally and not worth a cold download for this
      grid; `tiny`/`small` already spans the fast/accurate tradeoff)
- [x] Record WER and stage latency for each, from the existing telemetry
      -- real run against Svarah (n=20) and, after two memory-pressure
      kills running the full grid in one process, LAHAJA too (n=20), fixed
      by running each grid cell as its own process instead of a bigger
      machine (`docs/specs/phase-2b.md` §12, `docs/specs/phase-3.md` §2.2)
- [x] Plot the Pareto curve and state which point the live demo runs at,
      and why -- all 4 Svarah grid points are Pareto-optimal (a real
      tradeoff, no dominated point); LAHAJA's grid has 3 of 4 Pareto-optimal
      (`tiny`/`float32` is dominated outright there -- worse WER *and*
      worse latency than `tiny`/`int8`, not a tradeoff). The shipped
      default was `small`/`int8`, measured at p50=7.46s STT latency against
      ~8.6s-average utterances on Svarah and 13.7s on LAHAJA,
      ~6-40x this project's own 200ms STT stage budget across the grid --
      see `docs/specs/phase-2b.md` §12 for the full reasoning

**CI.** Nothing currently tells a visitor that 50 tests pass.

- [x] GitHub Actions: `pytest -m "not integration"`, `mypy --strict`, `ruff`
- [x] **A step that fails the build if the streaming overlap saving drops
      below threshold.** No separate step needed: `tests/test_overlapped.py`
      already asserts `improvement_ms >= 400.0` and runs in the default
      (non-`integration`) suite, so CI's `pytest -m "not integration"`
      step already gates it -- reimplementing it would have been the
      wrong move per `docs/specs/phase-2b.md` §6.
- [x] Badge it in the README

*Why this is not optional: `eer_before` of 59.4% on Svarah and 100% on
LAHAJA measures `small` Whisper, not Indic ASR in general. Without a
competent Indic baseline, every F2 recovery number is contestable as
fixing a problem the Phase 1 provider choice created. All three outcomes
are worth having — Saaras already handles the entities (F2 is
provider-dependent, and "pick the right ASR" is still the thesis), Saaras
still misses them (F2 is unarguable), or Saaras misses different ones
(the most interesting result in the project).*

**Proves:** you test your own thesis against the strongest alternative,
not the weakest.

## Phase 3 · Twilio reframe — Sep 28 to Oct 9

Retargets the project from browser audio to the audio a phone call actually
delivers. The `worktree-twilio-reframe` branch's draft (mu-law codec,
resampler, channel simulator) was read, tested, and one real bug fixed
(the resampler's downsampling pre-filter didn't carry state across frames,
reintroducing the exact click the module exists to prevent) before being
ported in.

- [x] **mu-law codec**, zero-dependency (`audioop` was removed in Python 3.13
      under PEP 594, and this sits on the hot path of every 20ms frame)
- [x] **Stateful resampler** — 8k/16k/22.05k, carrying interpolation state
      across frames so boundaries do not click
- [x] **Channel simulator**: narrowband, G.711 companding, packet loss, jitter,
      delay — each parameterized, seeded, and swept
- [x] **Twilio Media Streams transport**: bidirectional WebSocket, base64
      `audio/x-mulaw` at 8kHz, `mark`/`clear` barge-in — protocol verified
      against Twilio's own published reference before coding, per
      `docs/specs/phase-3.md` §7.4
- [x] **Mock Media Streams server** so the whole path is testable with no
      Twilio account — full loopback over a real localhost WebSocket
- [!] **Degradation sweep → robustness curve** — the no-jitter rows stand;
      the jitter row is invalidated (`phase-3b.md` §4: the simulator sleeps
      `uniform(0, jitter)` per frame in series, i.e. cumulative slowdown, not
      jitter; and rows are not paced at real time). Re-run as 3B-6.
      Original text: WER, plus end-to-end
      latency, against impairment level, run for real against Svarah
      (n=20, `tiny` Whisper — memory-constrained host, see below). WER is
      noisy at this sample size; the real, robust finding is on latency:
      40ms of jitter alone pushes STT p50 from ~1.3s to **4.8s** and p90 to
      **11.0s** — jitter can cost more end-to-end latency than the model
      choice does. (LAHAJA is covered separately by the model sweep above,
      not by this particular degradation curve.)

*A simulator rather than a live line because impairment has to be
controllable to produce a curve. A real PSTN call gives one uncontrolled
sample; a swept simulator gives the function.*

**Proves:** you design for hostile channels, and you work at the layer a
telephony company actually operates.

## Phase 3B · Measurement audit + standout work — Sep 24 to Oct 10

Full plan, rules and evidence format: [`docs/specs/phase-3b.md`](docs/specs/phase-3b.md).
Uses the slack Phase 3 finishing early created; does not touch the Oct 26 buffer.

A read-through review on Sep 23 found three headline numbers that do not
measure what the docs claim (substring entity matching, script-blind EER
scoring, cumulative "jitter"). Fixing them is Priority 0 and **blocks
`RESULTS.md`**. Priority 1 is what turns the project from "an STT eval with
an agent around it" into something an ASR/TTS company (smallest.ai, Sarvam,
SuperKalam) and a telephony company (Twilio, Exotel, Plivo) each recognise
as their own problem.

**Priority 0 — make the existing numbers true** (all must be `[x]` before Phase 4's `RESULTS.md` items can start)

- [x] 3B-1 **GATE** — word-boundary, deduplicated mention counting shared by
      gate and scorer; re-run the gate; restate the decision from it
      evidence: 6fa78b2 · `uv run python scripts/entity_density_gate.py` ·
      `results/entity_density_gate.json` + `results/entity_density_gate_review.json` ·
      Svarah 212 legacy / 202 substring / **94 word-boundary** -> PROCEED with CI +
      lexicon expansion; LAHAJA 40 / 40 / **29** matcher, **17 after review**
      (all 12 bare `आधार` hits are the noun "basis", not the ID) -> **GATE FAILED
      for LAHAJA** (<30). The audit's own LAHAJA recount (38) was also inflated:
      its `\w` regex let `आधारित` ("based on") through.
      Reviewed and accepted by owner 2026-11-12.
- [x] 3B-1a — LAHAJA pivot required by the failed gate. Owner decision
      2026-11-12: switch the Hindi arm to IndicVoices' use-case split (not
      lexicon widening). Gate must be re-run on IndicVoices Hindi first. Also:
      bare `आधार` is a homonym -- the lexicon needs a context rule or must drop
      the bare variant before any Hindi EER is scored.
      evidence: df63af1 · `uv run python scripts/entity_density_gate.py --datasets
      indicvoices-hindi --out results/entity_density_gate_indicvoices_hindi.json` ·
      `results/entity_density_gate_indicvoices_hindi.json` + `..._review.json`
      (results committed in 27b402b; this tick follows in the next commit, a
      rule-0.2.3 slip, not a re-run) · 450,690 Hindi transcripts; 2,677
      word-boundary pairs, **1,890** excluding bare-homonym-only pairs,
      **1,386** in the government use-case tasks -> **PROCEED** on every count.
      Caveats carried with every number: the gov subset is 94% read speech
      (lower bound); only 9 gov pairs in `valid` (eval samples `train`, which
      Saaras may have trained on); bare `आधार`/`पैन` are false outside gov
      tasks (286 "के आधार पर" pairs, "पैन किलर"). Reviewed and accepted by
      owner 2026-11-13.
- [x] 3B-2 — two-rate scorer: **recognition EER** (any curated variant, any
      script) and **canonicalization rate**, both paired with corruption
      evidence: <this commit> · `uv run pytest -m "not integration"` (226 passed) ·
      `tests/test_entity_error_rate.py` (Devanagari-correct output recognised but
      not canonical; "company" not a PAN mention; variant spelling recognised
      but not canonical) · implementation item, no headline number. Decisions
      made with it: (1) per owner 2026-11-13, bare `आधार`/`पैन`/`pan` dropped
      from the lexicon instead of restricting Hindi to gov-task rows; compound
      forms `आधार नंबर`/`पैन नंबर`/`pan number` added; (2) the dev threshold
      sweep now minimises `canonical_miss_after + corruption_rate` (3B-4 must
      preregister this before its run). Gate re-run under the new lexicon,
      beside the old rows: `results/entity_density_gate_lexicon_v2.json` --
      Svarah 94, LAHAJA 17 (= the manual review), IndicVoices Hindi 2,097.
      Reviewed and accepted by owner 2026-11-13.
- [x] 3B-3 — cache every raw transcript to committed JSONL so rescoring never
      needs re-transcription or API credits
      evidence: <this commit> · `uv run pytest -m "not integration"` (233 passed) ·
      `tests/test_transcript_log.py` · implementation item. New
      `dhvani.eval.transcript_log.TranscriptLog`: append-only JSONL, flushed per
      line, keyed (dataset, example_id, stt, model, condition), ground truth
      stored beside each transcript. Wired into all four eval paths (F2 reads
      back and skips re-transcription; model/degradation sweeps only record,
      since a cached transcript has no latency; F1 logs `real`/`corrected`).
      Loaders now give every row `example_id = <shard>#<row>`; every run script
      takes `--transcripts`, default `results/transcripts/<script>_<dataset>_<stt>.jsonl`.
      No real run has written a committed transcript file yet -- the first one
      lands with 3B-4. Also fixed: `run_f1_ablation.py` still counted lexicon
      mentions by substring (a fourth copy 3B-1 missed). Accepted by owner 2026-11-13.
- [x] 3B-4 — preregister, then re-run F2 EER, 2 datasets × 2 ASRs; old rows
      kept as superseded
      preregistered: `docs/specs/phase-3b.md` §9 (own commit, before any run).
      Arms: Svarah + IndicVoices Hindi (LAHAJA's gate failed) × Whisper + Saaras.
      evidence and verdicts: `docs/specs/phase-3b.md` §6 3B-4 (commit 0a632b3,
      four `results/f2_eer_*.json` files). Marker synced here 2026-11-14 to
      match the spec; awaiting owner review. Old rows above not yet marked
      superseded (3B-16).
- [x] 3B-5 — F1 noise floor: ground-truth A/A run, k≥3 repeats, paired
      bootstrap CI + McNemar, full `single_tool` set
      preregistered `phase-3b.md` §10 (9b30533); run complete; evidence and verdicts in `phase-3b.md` §6 3B-5 and
      `docs/runs/3b-5-f1-noise-floor.md`. Accepted by owner 2026-11-15.

**Open work — defined in [`docs/specs/phase-4.md`](docs/specs/phase-4.md)**
(the only place open items are specified; read its §1 rules first)

*Release 1 — ship what is already true (cached transcripts only)*

- [x] 3B-14 — committed re-score script and `results/f2_rescore.json`
      evidence: `27e6516` · `scripts/rescore_f2_transcripts.py` · `results/f2_rescore.json`
      (reproduces the four 3B-4 test reports exactly) · `docs/runs/3b-14-rescore.md`
- [x] 3B-15 — exact-match canonicaliser as the shipped default; raw /
      exact / exact+fuzzy table per arm
      evidence: `5867c42` · `EntityCorrector(mode="exact")` default · `results/f2_three_way.json`
      · `docs/runs/3b-15-three-way.md`
- [x] 3B-16 — old F2 rows marked superseded, branch merged, README
      rewritten audit-first from committed results files, tag `v0.1`
      evidence: README `a258987` (tables generated by `scripts/render_readme_tables.py
      --check README.md`) · merged to `main` and pushed · tag `v0.1` (`f5b59ea`) · old
      F1/F2 rows marked `superseded by:` above, 2026-11-15 · accepted by owner 2026-11-15

*Release 2, Q1 — does a strong ASR lose digits and entities on phone audio?*

- [?] 3B-17 — number normalisation for scoring; digit-string exact match
      from the cached logs
      evidence: prereg `6d862df` (before scoring) · `results/f2_digits.json` · `docs/runs/3b-17-digit-strings.md`
      · digit-string exact match Svarah Whisper 81.3% / Saaras 92.0%, Hindi Saaras 84.1%; Hindi Saaras WER
      26.4% -> 12.6% after number normalisation. Normaliser amended after seeing misses (deviation 1);
      awaiting owner review
- [~] 3B-20 — reference arm: hosted Whisper `large-v3`, language forced
      evidence (clean half only; the `pstn` half waits for 3B-18): prereg `2b52ff2` ·
      `docs/runs/3b-20-groq-large-v3.md` · `results/f2_eer_*_groq-whisper.json` · Svarah recognition
      error 16.7% [9.6, 27.4] vs Saaras 0.0%; Hindi arm is a broken baseline by the pre-flight rule
- [ ] 3B-18 — Saaras on the test-split entity rows through the 8 kHz
      mu-law channel
- [ ] 3B-21 — the same ASRs on a sample of real telephone Hindi

*Release 2, Q2 — why does the agent fail with perfect transcripts?*

- [x] 3B-19 — failure breakdown, a meaning-level judge validated against
      50 owner labels, and the 3B-5 log re-scored under both judges. No
      "lost to ASR" line anywhere until this is `[x]`
      evidence: `docs/runs/3b-19-meaning-judge.md` · `results/f1_meaning_judge.json` ·
      kappa 0.682 [0.465, 0.878] vs the owner's 50 labels; gt ceiling 73.3% EN / 64.7% HI
      under the meaning judge. Accepted by owner 2026-11-15; the 50 labels were left as
      committed (relabelling after seeing verdicts would inflate agreement). README §3
      updated from the committed results

*Release 2, Q3 — what is the real response time?*

- [ ] 3B-9 — end of speech → first agent audio byte on replayed real
      utterances, per stage; streaming hosted STT vs local `tiny`
- [!] 3B-10 — one real phone call with barge-in and measured `clear`-to-
      silence latency; mock server does **not** satisfy this item
      blocked: Twilio trial accounts do not allow Media Streams (Twilio
      docs, read 2026-11-14). One session to pre-flight a Plivo, then an
      Exotel, trial (`phase-4.md` §5.2 Q3).

**Parked** (entry conditions in `phase-4.md` §7; none is worked on unless
promoted at a checkpoint): 3B-6 real jitter model · 3B-7 keyword biasing vs
post-correction · 3B-8 TTS round-trip · 3B-11 one-command reproducibility ·
3B-12 fuzzy-matcher hardening (dev rows and a fresh draw only,
`phase-3b.md` §11.5) · 3B-13 entity-bearing task on real audio.

**Proves:** you audit your own results as hard as anyone else's, and you
know what speech and telephony teams actually measure.

## Phase 4 · Ship — Oct 12 to 23

The artifact, not more findings. The work is already strong; almost
nothing about it is currently visible to anyone who has not read the
specs, and that is what this phase fixes.

**`RESULTS.md` — the technical report.** The best material in this project
is buried in `docs/specs/phase-2.md` §12–16, where no reader will find it.
Lifting it into a standalone report is the research artifact, without
needing F5.

*Changed 14 Nov: the README truth pass is 3B-16 and ships in Release 1.
`RESULTS.md` and the other items in this phase are parked until Release 2
of `docs/specs/phase-4.md` is complete. Every number must come from a
committed `results/*.json` file, never be retyped from a spec.*

- [ ] **A named "Measurement audit" section first**: the three bugs found
      on Sep 23, the before/after numbers side by side, and what changed in
      the reading. This is the most distinctive thing in the project.
- [ ] Methodology: entity-density gate, dev/test protocol, preregistered
      outcomes, why the scorer is independent of the matcher
- [ ] Results: F1 share-of-achievable, F2 EER with corruption rates
      alongside, confidence intervals, the model-sweep Pareto curve,
      the degradation curve
- [ ] **A named section for the negative result** — the 2-of-80 corpus
      overlap and why the task-success swing is sampling noise. Most
      projects report only wins; this one says where it found nothing,
      and that is the part worth leading with.
- [ ] Limitations: synthesized VoiceAgentBench audio as a lower bound,
      n=28 on LAHAJA, the dev/test corruption discrepancy

**README, results first.** It currently opens with setup instructions.
Reorder it.

- [ ] Waterfall at the top, then the headline numbers table, then what
      did not work, then a link to `RESULTS.md`
- [ ] CI badge
- [ ] Setup instructions moved to the bottom, where they belong
- [ ] **Demo recording** — a real conversation including an interruption
- [ ] **Failure modes**: what happens on provider timeout, packet loss,
      LLM stall mid-sentence. `ProviderError` and `fail_after` already
      exist; this writes down what they do.
- [ ] **Honest "what still breaks"** — accented speech, noise,
      multi-speaker
- [ ] Live demo deployed

**Proves:** you finish things, and you report them straight.

## Buffer — Oct 26 to Nov 2

Deliberately empty. Phases 2B–4 are ~4.5 weeks of work in 6 weeks; the
slack is the plan, not an accident.

### Apply: 3 November 2026 — missed

Not met: the audit branch sat unmerged from Sep 23 to Nov 12. No calendar
date replaces it. Applications go out when Release 1 is tagged `v0.1`
(`docs/specs/phase-4.md` §5.1), which is four working sessions of work on
data already on disk.

---

# AFTER 3 NOVEMBER — deferred by decision, not by drift

F3, F4 and F5 were on the pre-Nov-3 plan and have been deliberately cut
from it. The arithmetic did not close: F5 alone is months, and carrying
all three would have meant shipping none of them and no artifact either.

The trade is explicit. Nov 3 gets a smaller, finished, honestly-measured
project instead of a larger unfinished one. If Phases 2B–4 land early, F3
is the first thing to pull forward — Hinglish needs no entity gate, has a
larger documented effect (30–50% relative WER), and demos audibly.

## Phase 3-deferred · F3 — Hinglish and code-switching

- [ ] Code-switch span detection on streaming transcripts
- [ ] Script normalization across Devanagari and Latin
- [ ] Dual-decode-and-merge where it pays for itself
- [ ] Data: IITG-HingCoS, HiACC

## Phase 4-deferred · F4 — cross-lingual safety

- [ ] Language-agnostic harmful-intent classification on transcripts,
      before the LLM
- [ ] Indic red-team set derived from AgentHarmBench categories
- [ ] Report refusal-rate parity, English vs Indic (VoiceAgentBench
      measured 51.78% English collapsing to 2.67% Indic)

## Phase 5 · F5 — Indic turn-taking

No published work exists on endpointing for Indian languages. Every deployed
endpointer is tuned on English silence distributions, so code-switch boundaries
read as sentence boundaries and agents interrupt mid-thought.

- [ ] Mine **IndicVoices** two-party conversational audio (~1,250 hrs, transcribed)
      for turn boundaries
- [ ] Characterise Indic pause distributions against English baselines
- [ ] Fuse energy VAD + prosodic features + semantic-completion classifier
- [ ] Evaluate: end-of-speech precision/recall, **false-interruption rate**,
      yield latency p90/p99, against fixed-threshold VAD
- [ ] Target a workshop paper (Interspeech / ICASSP / ACL workshop)

**Proves:** research, not only integration.

## Beyond

- Extend F2 to Tamil, Telugu, Bengali, Marathi, Malayalam
- Three-tier memory (hot cache / background episodic / async writes), with the
  IndicVoices Level-1 vs Level-2 transcription split applied to fact extraction —
  extract from normalized text, never verbatim disfluent speech
- Sequential dependent tool calling — 4.3% in Indic today, the largest open headroom
- `dhvani-entity` published to PyPI

---

## Risks

| Risk | Mitigation |
|------|-----------|
| Local models too slow for sub-800ms | Report the waterfall honestly and note hosted-provider deltas; correct engineering still shows |
| Sarvam free credits run out mid-evaluation | Bound the Phase 2B re-run to the same Svarah/LAHAJA test splits already used; fall back to reporting the Whisper numbers with the caveat stated |
| Phase 3 slips and the Twilio reframe lands half-built | Phases 0–2B alone ship as a credible artifact; the browser transport already works |
| An agent ticks a box for work it substituted, mocked, or only partly did | Evidence-line rule and `[?]` review state (`phase-3b.md` §0); reviewer diffs `ROADMAP.md` per PR and reverts any tick without evidence in the same diff |
| Audit re-run shows F2's gains were mostly scoring artifacts | That is a result, not a failure: report it in the audit section; F2 is then reframed (canonicalization for Hindi, decoder biasing comparison from 3B-7) rather than hidden |
| A Release 2 question comes back null | Every outcome already has its README sentence (`phase-4.md` §5.2); a null is reported and the plan does not change |
| Sarvam credits run out mid-run | Budget and stop rule in `phase-4.md` §4; an item that does not fit is blocked, never thinned |
| A new idea or a surprising result tempts a re-plan | It goes to the parking lot and waits for one of the two checkpoints (`phase-4.md` §6) |
| Corrector changes get tuned on a test split the review has already read | 3B-12 uses dev rows and a fresh draw only (`phase-3b.md` §11.5) |
| Scope creep back into F3–F5 | They are dated past Nov 3 and stay there. Pulling one forward means cutting Phase 4, not adding a week. |

## Non-goals

- Competing with Pipecat / LiveKit as a general-purpose framework
- A benchmark or survey with no live artifact
- Any deliverable whose README contains no numbers

---

<sub>Operating constraint: no paid infrastructure. All models run locally or on free
tiers, and all evaluation data (Svarah, LAHAJA, IndicVoices, HiACC, IITG-HingCoS)
is publicly downloadable. This shapes tool selection, not architecture.</sub>
