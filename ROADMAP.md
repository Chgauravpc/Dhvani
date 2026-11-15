# Dhvani — Roadmap

**Thesis:** Indic voice agents fail at the *ear*, not the brain. The published
evidence says transcription quality — not model reasoning — is what breaks them.
Every deliverable here attacks one measured failure in that ear, and every one
ships with a number.

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
| F1 | ASR is the bottleneck, not the LLM — 24%+ swing from transcript quality | ASR-ablation harness | **done**, pending re-run against an Indic ASR baseline |
| F2 | Named entities are where Indic ASR breaks — 11.2% vs 6.2% WER | `dhvani-entity` post-ASR corrector | **reopened** — code done; EER numbers invalidated by the Sep 23 audit (substring + script-blind scoring), re-run in Phase 3B |
| F3 | Code-switching costs 30–50% relative WER | Hinglish-aware decode + script normalization | deferred past Nov 3 |
| F4 | Safety refusal collapses 51.78% to 2.67% English-to-Indic | pre-LLM language-agnostic intent guard | deferred past Nov 3 |
| F5 | Zero Indic turn-taking / full-duplex research exists | Indic endpointer (prosody + semantic completion) | deferred past Nov 3 |

F1 is the narrative spine: proving the bottleneck on our own stack is what
justifies spending the project on transcription rather than on prompt
engineering. F5 remains the only genuinely novel contribution, and is the
reason the deferred list is a list rather than a deletion.

**Scope decision, 21 Sep 2026.** F1 and F2 are measured. The remaining
43 days do not fit F3, F4, F5, the Twilio reframe and a finished artifact,
so the deadline was held and the findings were cut. What ships on Nov 3 is
Phases 0–2 plus an Indic ASR baseline, the Twilio reframe, and a README
that reports all of it honestly — including the negative result.

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
      Re-run as 3B-1..3B-4. Original text kept below for the record:
      entity-density gate passed both
      (212 and 40 mentions). Real EER: Svarah 59.4%→49.0% (10.4-point
      recovery, 2.9% corruption); LAHAJA 100%→46.4% (53.6-point recovery,
      but 19.4% corruption on test vs 0% on dev — a real dev/test
      discrepancy at this small a scale, not swept under the rug). See
      `docs/specs/phase-2.md` sections 14–15.
- [!] invalidated for Y only (X stands, pending the 3B-5 noise floor): Y is
      the EER recovery the Sep 23 audit reopened. Re-closed by 3B-4.
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
      Re-run Svarah and LAHAJA EER with it as the inner ASR -- real numbers
      in `docs/specs/phase-2.md` §18: Svarah improves (59.4% → 46.9%
      `eer_before`); LAHAJA doesn't (100.0% on both) — a purpose-built
      Indic ASR misses LAHAJA's entities exactly as completely as Whisper.
- [x] Re-run the F1 ablation with it -- `docs/specs/phase-2.md` §18; noisy
      as expected given the same 2-of-80 lexicon-overlap issue section 16
      already found, not a new problem.
- [x] Re-express F1 loss as **share of achievable**, not absolute points:
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

- [ ] 3B-1 **GATE** — word-boundary, deduplicated mention counting shared by
      gate and scorer; re-run the gate; restate the decision from it
- [ ] 3B-2 — two-rate scorer: **recognition EER** (any curated variant, any
      script) and **canonicalization rate**, both paired with corruption
- [ ] 3B-3 — cache every raw transcript to committed JSONL so rescoring never
      needs re-transcription or API credits
- [ ] 3B-4 — preregister, then re-run F2 EER, 2 datasets × 2 ASRs; old rows
      kept as superseded
- [ ] 3B-5 — F1 noise floor: ground-truth A/A run, k≥3 repeats, paired
      bootstrap CI + McNemar, full `single_tool` set
- [ ] 3B-6 — real jitter model (arrival times + jitter buffer, real-time
      pacing, latency from end of speech); re-run affected rows

**Priority 1 — stand out**

- [ ] 3B-7 — decoder-side contextual biasing vs. `dhvani-entity` vs. both,
      same test split (the first question an ASR team asks)
- [ ] 3B-8 — TTS round-trip: lexicon entities + Indic text normalization
      (₹, dates, digits, Hinglish) → TTS → ASR → recognition EER, plus TTS
      time-to-first-byte (the project currently says nothing about TTS)
- [ ] 3B-9 — voice-to-voice latency on real utterances (end of speech →
      first agent audio byte, per stage), local vs. one hosted streaming STT
- [ ] 3B-10 — one real Twilio call with barge-in and measured `clear`-to-
      silence latency; mock server does **not** satisfy this item
- [ ] 3B-11 — one command regenerates every headline number into
      `results/*.json`; `RESULTS.md` tables rendered from those files

**Priority 2 — only if P0 and P1 are done:** 3B-12 corrector hardening
(best-scoring window, short-acronym guard, stoplist), 3B-13 entity-bearing
slot-filling task on real Svarah/LAHAJA audio to tie F1 to F2.

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

*Blocked on Phase 3B Priority 0. Every number in `RESULTS.md` must come from
a committed `results/*.json` file (3B-11), never be retyped from a spec.*

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

### Apply: 3 November 2026

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
| Scope creep back into F3–F5 | They are dated past Nov 3 and stay there. Pulling one forward means cutting Phase 4, not adding a week. |

## Non-goals

- Competing with Pipecat / LiveKit as a general-purpose framework
- A benchmark or survey with no live artifact
- Any deliverable whose README contains no numbers

---

<sub>Operating constraint: no paid infrastructure. All models run locally or on free
tiers, and all evaluation data (Svarah, LAHAJA, IndicVoices, HiACC, IITG-HingCoS)
is publicly downloadable. This shapes tool selection, not architecture.</sub>
