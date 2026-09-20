# Dhvani — Roadmap

**Thesis:** Indic voice agents fail at the *ear*, not the brain. The published
evidence says transcription quality — not model reasoning — is what breaks them.
Every deliverable here attacks one measured failure in that ear, and every one
ships with a number.

**Goal:** a portfolio project for Indian voice-AI startups (smallest.ai, Sarvam,
Gnani, Bolna, Skit). Optimized for a demo someone can talk to and a README with
measurements in it.

---

## The five findings

Not a feature list. Five measured defects from the literature, each becoming
one deliverable with one metric.

| # | Finding | Source | Deliverable | Metric |
|---|---------|--------|-------------|--------|
| F1 | ASR is the bottleneck, not the LLM — 24%+ swing from transcript quality | VoiceAgentBench 2025 | ASR-ablation harness | task success: real ASR vs ground-truth transcript |
| F2 | Named entities are where Indic ASR breaks — 11.2% vs 6.2% WER | Svarah, LAHAJA | `dhvani-entity` post-ASR corrector | Entity Error Rate before/after |
| F3 | Code-switching costs 30–50% relative WER | CS-ASR review, HiACC | Hinglish-aware decode + script normalization | WER on CS vs monolingual segments |
| F4 | Safety refusal collapses 51.78% to 2.67% English-to-Indic | VoiceAgentBench 2025 | pre-LLM language-agnostic intent guard | refusal-rate parity across languages |
| F5 | Zero Indic turn-taking / full-duplex research exists | gap in literature | Indic endpointer (prosody + semantic completion) | false-interruption rate, yield latency p90/p99 |

F1 is the narrative spine: proving the bottleneck on our own stack is what
justifies spending the project on F2 and F3 rather than on prompt engineering.
F5 is the only genuinely novel contribution.

## Two tracks

- **Track A — the host.** An agent you can talk to: streaming pipeline, barge-in,
  latency waterfall. Without this the findings have nowhere to live.
- **Track B — the findings.** F1 through F5.

---

# SHORT TERM — 7 weeks (15 Sep to 3 Nov 2026)

## Phase 0 · Instrumentation spine — Week 1 (Sep 15–21)

- [ ] Project skeleton, Python 3.13, typed config
- [ ] **Telemetry layer**: per-stage spans — endpointing / STT / LLM / tools / TTS —
      aggregated to p50 / p90 / p99. Never a single total.
- [ ] Provider protocols (STT / TTS / LLM)
- [ ] Test suite green in CI

*Mock providers with scripted delays ship alongside the protocols. Reason: the
Phase 0 deliverable is timing instrumentation, and timing assertions against a
live API are non-reproducible. Mocks let "stage overlap saved 340ms" be an actual
test rather than an observation. This is test hygiene, not a feature.*

**Proves:** you instrument before you optimize.

## Phase 1 · Working agent — Weeks 2–3 (Sep 22 to Oct 5)

- [ ] Real providers: faster-whisper / IndicConformer (STT), Piper / IndicF5 (TTS),
      Groq or local Ollama (LLM)
- [ ] **Streaming with overlapped stages** — STT partials feed the LLM early;
      TTS begins on the first sentence, not the full response
- [ ] Silero VAD + **barge-in**: user interrupts mid-sentence, agent yields
- [ ] Voice-safe prompt guards — no markdown, lists, or headers
- [ ] Browser/WebRTC transport
- [ ] **Milestone: first sub-800ms p50 conversation, waterfall published**

**Proves:** you can ship a real-time system, not an API wrapper.

## Phase 2 · F1 + F2 — Weeks 4–5 (Oct 6–19)

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
- [ ] Evaluate on **Svarah** and **LAHAJA** — blocked on Hugging Face
      access (both turned out to be gated); code is ready
      (`scripts/entity_density_gate.py`, `scripts/run_f2_entity_eval.py`).
- [ ] **Milestone: "the agent loses X% of task success to transcription alone,
      and `dhvani-entity` recovers Y% of it."** X half-done (F1's number
      above); Y needs the Svarah/LAHAJA access above.

**Proves:** you locate a bottleneck, fix it, and measure the fix.

## Phase 3 · F3 + channel robustness — Week 6 (Oct 20–26)

- [ ] **F3 — Hinglish handling.** Code-switch span detection on streaming
      transcripts, script normalization, dual-decode-and-merge where it pays.
      Data: IITG-HingCoS, HiACC.
- [ ] **Channel simulator**: 8kHz downsample, G.711 mu-law, jitter, packet loss,
      added delay — each parameterized and swept.
- [ ] **Robustness curve**: WER and end-to-end latency vs degradation level

*A simulator is used instead of a live phone line because impairment has to be
controllable to produce a curve. A real PSTN call gives one uncontrolled sample;
a swept simulator gives the function. Optional: local Asterisk plus a softphone
adds a genuine SIP path for the demo recording.*

**Proves:** Indic competence, and that you design for hostile channels.

## Phase 4 · F4 + ship — Week 7 (Oct 27 to Nov 2)

- [ ] **F4 — intent guard.** Language-agnostic harmful-intent classification on
      transcripts *before* the LLM. Indic red-team set derived from AgentHarmBench
      categories.
- [ ] Report **refusal-rate parity**, English vs Indic
- [ ] README: demo recording including an interruption, latency table,
      before/after numbers, honest "what still breaks"
- [ ] Live demo deployed

**Proves:** you think about safety in the languages you actually ship.

### Apply: 3 November 2026

Phases 0–2 alone are a credible application. F3 and F4 are upside, so slipping
does not sink the timeline.

---

# LONG TERM — research capstone (Nov 2026 to Feb 2027)

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
| F5 needs more data or compute than available | Kaggle free T4; scope to 2–3 languages |
| Scope creep across five findings | Phases 0–2 are self-sufficient; F3–F5 are additive |

## Non-goals

- Competing with Pipecat / LiveKit as a general-purpose framework
- A benchmark or survey with no live artifact
- Any deliverable whose README contains no numbers

---

<sub>Operating constraint: no paid infrastructure. All models run locally or on free
tiers, and all evaluation data (Svarah, LAHAJA, IndicVoices, HiACC, IITG-HingCoS)
is publicly downloadable. This shapes tool selection, not architecture.</sub>
