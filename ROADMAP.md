# Dhvani — Roadmap

**Goal:** an internship-grade portfolio project for Indian voice-AI startups
(smallest.ai, Sarvam, Gnani, Bolna, Skit, SuperKalam).

**Thesis:** Indic voice agents fail at the *ear*, not the brain. Every deliverable
below attacks one measured failure in that ear, and every one ships with a number.

**Constraints:** ₹0 budget. No telephony spend. All models free/local or on free
credits. All evaluation data is publicly downloadable.

---

## The five findings

These are not features. They are measured defects reported in the literature,
and each becomes one deliverable with one metric.

| # | Finding | Source | Deliverable | Metric |
|---|---------|--------|-------------|--------|
| F1 | ASR is the bottleneck, not the LLM — 24%+ swing from transcript quality | VoiceAgentBench 2025 | ASR-ablation harness | task success: real ASR vs ground-truth transcript |
| F2 | Named entities are where Indic ASR breaks — 11.2% vs 6.2% WER | Svarah, LAHAJA | `dhvani-entity` post-ASR corrector | Entity Error Rate before/after |
| F3 | Code-switching costs 30–50% relative WER | CS-ASR review, HiACC | Hinglish-aware decode + script normalization | WER on CS vs monolingual segments |
| F4 | Safety refusal collapses 51.78% → 2.67% English→Indic | VoiceAgentBench 2025 | pre-LLM language-agnostic intent guard | refusal-rate parity across languages |
| F5 | Zero Indic turn-taking / full-duplex research exists | gap in literature | Indic endpointer (prosody + semantic completion) | false-interruption rate, yield latency p90/p99 |

F1 is the narrative spine — it justifies why F2 and F3 matter. F5 is the research
capstone and the only genuinely novel contribution.

---

## Two tracks

- **Track A — the host.** A voice agent you can actually talk to. This is what makes
  the work *hireable*: a demo, a latency waterfall, working barge-in.
- **Track B — the findings.** F1–F5. This is what makes the work *interesting*.

Track A must exist first; F1–F5 have nowhere to live without it.

---

# SHORT TERM — 7 weeks to an application (15 Sep → 3 Nov 2026)

## Phase 0 · Foundation — Week 1 (Sep 15–21)

The spine everything else reports into.

- [ ] Project skeleton, Python 3.13, typed config
- [ ] **Telemetry layer**: per-stage spans → endpointing / STT / LLM / tools / TTS,
      aggregated to p50 / p90 / p99. Never a single total.
- [ ] Provider protocols (STT / TTS / LLM) + **mock implementations**
- [ ] Runs end-to-end offline with zero API keys and zero model downloads
- [ ] Test suite green

**Proves:** you instrument before you optimize.

## Phase 1 · Working agent — Weeks 2–3 (Sep 22 – Oct 5)

- [ ] Real providers: faster-whisper / IndicConformer (STT), Piper / IndicF5 (TTS),
      Groq or local Ollama (LLM)
- [ ] **Streaming with overlapped stages** — STT partials feed the LLM early;
      TTS starts on first sentence, not full response
- [ ] Silero VAD + **barge-in** (interrupt mid-sentence, agent yields)
- [ ] Voice-safe prompt guards — no markdown, no lists, no headers
- [ ] Browser/WebRTC transport
- [ ] **Milestone: first sub-800ms p50 conversation, latency waterfall published**

**Proves:** you can ship a real-time system, not an API wrapper.

## Phase 2 · F1 + F2 — Weeks 4–5 (Oct 6–19)

The highest-signal pair. F1 is cheap once Phase 1 exists; F2 is the flagship.

- [ ] **F1 — ASR ablation harness.** Run identical tasks with real ASR vs
      ground-truth transcripts. Report the task-success delta per language.
      Replicates VoiceAgentBench's finding on your own stack.
- [ ] **F2 — `dhvani-entity`.** Post-ASR contextual biasing: domain lexicon +
      phonetic matching across scripts (Devanagari ↔ Latin ↔ Tamil), so
      *Aadhaar / aadhar / आधार* and *Pradhan Mantri Awas Yojana* resolve correctly.
- [ ] Evaluate on **Svarah** and **LAHAJA** (free downloads)
- [ ] **Milestone: "my agent loses X% of task success to transcription alone,
      and `dhvani-entity` recovers Y% of it."**

**Proves:** you find the bottleneck, then fix it, then measure the fix.

## Phase 3 · F3 + robustness — Week 6 (Oct 20–26)

- [ ] **F3 — Hinglish handling.** Code-switch span detection on streaming
      transcripts, script normalization, dual-decode-and-merge where it pays.
      Data: IITG-HingCoS, HiACC.
- [ ] **Channel simulator** — the ₹0 substitute for telephony: 8kHz downsample,
      G.711 μ-law, jitter, 1–5% packet loss, +150–200ms delay
- [ ] Impairment sweep → **robustness curve** (WER and latency vs degradation)
- [ ] Optional: local Asterisk/FreeSWITCH + softphone for a genuine SIP demo

**Proves:** Indic competence, plus that you design for hostile channels.

## Phase 4 · F4 + ship — Week 7 (Oct 27 – Nov 2)

- [ ] **F4 — intent guard.** Language-agnostic harmful-intent classification on
      transcripts *before* the LLM. Small Indic red-team set derived from
      AgentHarmBench categories.
- [ ] Report **refusal-rate parity** English vs Indic — show the 2.67% gap closing
- [ ] README: demo recording (including an interruption), latency table,
      before/after numbers, honest "what still breaks"
- [ ] Deploy live demo (HF Spaces / Fly.io / Cloudflare Tunnel)

**Proves:** you think about safety in the languages you actually ship.

### → Apply: 3 November 2026

---

# LONG TERM — the research capstone (Nov 2026 → Feb 2027)

## Phase 5 · F5 — Indic turn-taking

The only item here that is genuinely new. No published work exists on endpointing
for Indian languages, and every deployed endpointer is tuned on English silence
distributions — so code-switch boundaries read as sentence boundaries and agents
interrupt mid-thought.

- [ ] Mine **IndicVoices** two-party conversational audio (17% of 7,348 hrs,
      already transcribed) for turn boundaries
- [ ] Characterise Indic pause distributions vs English baselines
- [ ] Fuse energy VAD + prosodic features + small semantic-completion classifier
- [ ] Evaluate: end-of-speech precision/recall, **false-interruption rate**,
      yield latency at p90/p99, vs fixed-threshold VAD
- [ ] Target a workshop paper (Interspeech / ICASSP / an ACL workshop)

**Proves:** you can do research, not only integration.

## Beyond

- Extend F2 beyond Hindi/English to Tamil, Telugu, Bengali, Marathi, Malayalam
- Three-tier memory (hot cache / background episodic / async writes) with the
  IndicVoices Level-1 vs Level-2 transcription split applied to fact extraction —
  extract from *normalized* text, never verbatim disfluent speech
- Sequential dependent tool calling — 4.3% in Indic today; largest open headroom
- Publish `dhvani-entity` to PyPI as a standalone library

---

## Risks

| Risk | Mitigation |
|------|-----------|
| Local models too slow for sub-800ms | Report the waterfall honestly; note hosted-provider deltas. Correct engineering still shows. |
| Free credits exhausted | Fully local path (faster-whisper + Ollama + Piper) has no quota |
| F5 needs more data/compute than available | Kaggle 30 hrs/week free T4; scope to 2–3 languages |
| Scope creep across 5 findings | Phases 0–2 alone are a strong application. F3–F5 are upside. |

## Non-goals

- Competing with Pipecat / LiveKit as a general framework
- A benchmark or survey with no live artifact
- Any deliverable whose README contains no numbers
