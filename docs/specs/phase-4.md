# Phase 4 — the closing plan

**Written:** 2026-11-14. **Status:** proposed; the owner accepts it by
filling in §9. Once accepted, this file is the only place open work is
defined. `ROADMAP.md` lists the items in one line each and points here;
`phase-3b.md` §0 (checkbox and evidence rules) still governs every tick.

This plan is built so that **no result can force a rewrite of it**. Section
1 says why earlier plans kept changing and what rule removes each cause.
Read §1 and §2 before touching an item.

---

## 1. Why the plan kept changing, and the rule that stops each cause

| What happened | Root cause | Rule from now on |
|---|---|---|
| F2 was built on "entities are where Indic ASR breaks"; the data said otherwise, twice | Items were written as **claims to confirm** | **R1 — questions, not claims.** Every experiment is a question. Each possible answer is mapped *in advance* to the README sentence it produces and the next step it triggers (§5). No answer changes the plan. |
| Substring gate, script-blind scorer, 66%-WER baseline, a Twilio trial that cannot stream — all found after the work | Assumptions were checked after building | **R2 — pre-flight before build.** Five checks (§3), written to a committed file, before any code or paid call. A failed check takes the item's pre-listed fallback; nothing is redesigned. |
| Credits, RAM, quota and disk ran out mid-run | Resources were discovered, not budgeted | **R3 — fixed budget** (§4). An item that would exceed it is cut or takes its fallback. The budget is not raised mid-run. |
| Nov 3 passed with nothing public | Shipping sat behind findings | **R4 — ship first.** Release 1 (§5.1) uses only what is already measured. Applications go out after Release 1, not after Release 2. |
| Each review added and reordered items | No boundary on scope | **R5 — frozen scope.** The active list is §5 and nothing else. New ideas go to the parking lot (§7). The plan may change only at the two checkpoints in §6, and only by the two allowed moves: cut an item, or take a pre-listed fallback. |
| Items renumbered and re-prioritised between passes | Unstable identifiers | **R6 — IDs are permanent.** An item keeps its `3B-n` for life. Cut items stay listed as cut. |
| Work expanded to fill the time | No end condition | **R7 — time boxes.** Each item has a size in working sessions (§5). At twice its size it is stopped and written up as far as it got. |

---

## 2. Ground facts this plan is built on (checked 2026-11-14)

**Measured on this machine** (throwaway scripts unless a results file is
named; 3B-14 turns the F2 ones into committed evidence):

| Fact | Value |
|---|---|
| Machine | 7.3 GB RAM (0.7 GB free during the check), Ryzen 5 5500U, integrated GPU only; C: 6.3 GB free, D: 149 GB free |
| Installed | faster-whisper 1.2.1 (`hotwords`, `initial_prompt` present); `sarvamai` 0.1.34 (`transcribe` has `mode`, `input_audio_codec`, `keyterms`; streaming and realtime-streaming clients exist) |
| Sarvam balance | 89 credits stated by the owner; the 3B-5 Saaras pass (26.6 min of audio, about Rs 13) was running during this check |
| Cached audio | Svarah 3B-4 rows 26.6 min; IndicVoices Hindi 3B-4 rows 93.5 min (longest row 30 s); VoiceAgentBench `single_tool` 275 files, 26.6 min |
| Test-split entity rows | 225 Hindi (55.4 min) + 65 Svarah (9.6 min) = 65.0 min |
| Digit-string density | rows whose reference has a run of four or more digits: about 60 Svarah, about 132 Hindi (rough matcher) |
| Whisper `small`/`int8` | WER 66.5% on the Hindi rows; 41 of 464 outputs not in Devanagari |
| Saaras `saaras:v3` | recognises 66/66 Svarah and 231/242 Hindi test mentions unaided |

**Read on provider pages** (through a summarising fetcher on 2026-11-14;
re-read the page before relying on any single line):

| Fact | Consequence |
|---|---|
| Sarvam REST: 30 s maximum per request; no sample-rate or mu-law parameter; raw PCM must be 16 kHz | degraded audio is sent as a WAV file; the 30 s row needs a pre-flight |
| Sarvam's default model is now `saaras:v4`; `keyterms` biasing works only on v4 | every call pins `saaras:v3` (the code default already does); a biasing arm would be a v4 arm |
| Sarvam `mode`: `transcribe` writes digits, `verbatim` keeps number words, `codemix` writes English words in Latin | references and hypotheses must be normalised to one form before any digit or WER score |
| Sarvam realtime WebSocket (beta): 8 kHz or 16 kHz, mu-law accepted, partial transcripts | real streaming latency on phone-format audio is measurable |
| Sarvam STT: Rs 0.49 per minute, billed per second, same for REST and streaming; training data not disclosed | budget in §4; contamination caveat stays on every IndicVoices number |
| Groq hosts `whisper-large-v3` and `-turbo`; limits listed as 20 requests/min, 7,200 audio-seconds/hour, 28,800/day (shown for the Developer plan; free-tier figure not confirmed) | a strong general-ASR reference arm with no RAM cost, if the pre-flight confirms the free tier |
| Groq chat: `openai/gpt-oss-20b` and `-120b` at 1,000 requests/day each | a stronger LLM is available for the F1 ceiling question |
| Twilio trial blocks `<Stream>` (Media Streams) | 3B-10 cannot be done on a Twilio trial; see its fallbacks |
| Plivo and Exotel offer bidirectional 8 kHz streaming; whether their trials include it was not confirmed | fallback candidates only, each needs its own pre-flight |

**Read on company pages** (their own claims):

- smallest.ai reports Hindi WER 8.3% on FLEURS against 29.1% on real
  Hindi-English collections calls, and recall for amounts and numbers below
  about 0.41 for all five vendors it tested.
- Sarvam argues plain WER is unfair for Indic text and publishes
  `llm_wer`, an entity-preservation score and `indic-numtowords`.
- smallest.ai, Gnani and others sell keyword boosting; Gnani benchmarks on
  Kathbath Noisy 8 kHz.
- What these companies publish numbers on: latency percentiles, real
  telephony audio, numerals and code-mixing.

### 2.1 Literature check (papers read in full text on 2026-11-14 unless marked)

| Finding | Source | Consequence here |
|---|---|---|
| VoiceAgentBench scores parameter filling with an **LLM judge for meaning** (GPT-4o-mini; 0.92 agreement, kappa 0.80 against humans), not exact match. Reported single-tool parameter filling for 8B–70B models: about 72% English, **76–81% Hindi** | arXiv 2510.07978 | our 42.5% / 17.5% ground-truth ceiling is far below the paper's and the Hindi gap is not in the paper at all |
| In the cached benchmark, **403 of 407 acceptable argument values for Hindi tasks are written in English** ("Delhi", "Varanasi, Uttar Pradesh", "open on Sunday") while the queries are Devanagari | local check of the cached manifests, 2026-11-14 | an exact-match judge demands an exact English rendering of a Hindi query. **F1's judge is a fourth measurement bug**; Q2 is rewritten around it |
| "11.2% vs 6.2%" is Whisper-large WER on Svarah's *everyday use-case* speech vs *read* speech — a data-type split, not entity vs non-entity. The authors attribute it to names and IDs without measuring that | arXiv 2305.15760, Table 2 | the F2 row in `ROADMAP.md` cites it as an entity result; corrected by a dated note there |
| The "51.78% → 2.67%" refusal collapse is **one speech model** (KimiAudio); cascaded ASR+LLM pipelines go 56 → 46, 60 → 38 and 39 → 47 | arXiv 2510.07978 | the F4 row overstates it; noted (F4 is parked) |
| Hindi number/date/name/place utterances: Google Chirp 63.2 WER vs 18.6 on read Wikipedia; best model 24.4 vs 12.9 | Lahaja, arXiv 2408.11440, Table 5 | published support for Q1's digit question |
| Real telephone-quality Hindi (Gram Vaani) vs clean read (Kathbath): 26.8 vs 10.3 (IndicWhisper), 59.9 vs 14.3 (Google). Confounds channel, dialect and spontaneity | Vistaar, arXiv 2305.15386, Table 3 | the telephony gap in the literature is real phone *speech*, not a clean recording passed through a codec |
| Band-limiting to 3.4 kHz alone stays close to 16 kHz performance; GSM-type codecs degrade; plain resampling to 16 kHz beats neural upsampling | arXiv 2606.09335 (numbers only in figures) | a simulated narrowband + G.711 channel will probably show **little** effect. Q1 therefore adds a real-telephone arm (3B-21) |
| Whisper `small` Hindi: 38.4 WER on FLEURS, 43.6 on Common Voice (read speech) | Whisper paper, arXiv 2212.04356, App. D | 66.5% on mostly-extempore IndicVoices is what this model size does; the baseline is unfit, not misconfigured |
| Three human transcribers disagree on 75.5% of Hindi utterances after normalisation; single-reference WER carries roughly 6–7 points of spelling noise | Vaani benchmark, arXiv 2606.21408 | small Hindi WER differences are not findings; this caveat goes with every Hindi WER |
| Whisper-style text normalisers strip Indic vowel signs; fair scoring transliterates to one script and normalises digits (SN-WER), or accepts English words in either script (MUCS T-WER) | arXiv 2605.20712, 2606.02548, 2104.00235 | constraint on 3B-17: no Whisper normaliser on Hindi |
| Isolated Hindi digit-string accuracy | not found in the literature | 3B-17 would be a number nobody has published |

---

## 3. Pre-flight — five checks before any item starts (R2)

Written to `results/preflight_<item>.json` and committed before the item's
first code or paid call. Each check records what was run and the number.

1. **Density.** The thing being measured occurs often enough: at least 100
   scoreable units, or 30–100 with confidence intervals reported. Below 30
   the item takes its fallback.
2. **Baseline sanity.** Each system under test, on 20 rows of the real
   data, gives usable output: WER under 40% and the expected script. A
   system that fails is labelled a broken baseline and is not run as a
   comparison arm.
3. **Cost, measured.** Audio minutes and request counts taken from the
   actual rows, priced at the current rate, and compared with §4.
4. **Machine fit.** Peak memory and run time observed on 20 rows, then
   extrapolated. One model per process.
5. **API reality.** Every parameter the item relies on is exercised once
   against the installed SDK or the live endpoint (model name pinned, audio
   format accepted, limits observed). Documentation is not evidence.

---

## 4. Budget (R3)

| Resource | Available | Committed | Reserve |
|---|---|---|---|
| Sarvam credits | 89 | 3B-5 Saaras pass about 13 · 3B-18 `pstn` about 33 · 3B-21 at most 17 · 3B-9 about 3 | about 23 |
| Groq chat | 1,000 requests/day per key | 3B-5 (2,475 calls, in progress) · 3B-19 judge (at most 2,475 calls) · 3B-19 fallback (275 calls) | — |
| Groq audio | to be confirmed in pre-flight | 3B-20 and 3B-21 (about 220 min of audio in total) | — |
| Local compute | CPU only, about 1 GB free RAM | Whisper `tiny`/`small` only, one process per model | — |
| Owner time | — | 3B-4 review · 3B-16 review · 50 hand labels for 3B-19 (about 1 hour) | — |

**Spend order for Sarvam, with the stop rule:** 3B-18 `pstn` first. Read
the dashboard balance before and after it. If the drop is more than Rs 40
the rate assumption is wrong: stop, and re-cost the remaining items from
the observed rate before any further call. 3B-21 runs only if at least
Rs 23 remains (its 17 plus 3B-9 and a margin). A sample is never thinned
to fit; an item that does not fit is recorded `[!] blocked: credits`.

---

## 5. The active list

Sizes are working sessions of about half a day. Order within a release is
the order written.

### 5.1 Release 1 — ship what is already true

Uses cached transcripts only. No credits, no new transcription.

| ID | Item | Size | Done when |
|---|---|---|---|
| 3B-14 | Commit `scripts/rescore_f2_transcripts.py` → `results/f2_rescore.json` (per-arm WER, output scripts, per-entity recognition, exact-lookup baseline, false-rewrite list) | 1 | every number in `phase-3b.md` §11.1 B1–B4 is reproduced or corrected there |
| 3B-15 | `EntityCorrector(mode="exact")` as the shipped default, `mode="fuzzy"` optional; three-way table raw / exact / exact+fuzzy per arm | 2 | results file has recognition EER, canonical miss and corruption for all three, all four arms |
| 3B-16 | Owner moves 3B-4 to `[x]`; old F2 rows marked superseded; branch merged; README rewritten audit-first, every number read from a committed results file; tag `v0.1` | 1 | `main` shows no invalidated number without its supersession, and the README states the F2 result as it is |

**Release 1 README, fixed in advance** (R1 — it says this whatever 3B-14
and 3B-15 show, with their numbers filled in):

1. What was claimed, the three measurement bugs, before and after.
2. The corrected F2 table, four arms, with the §9.5 caveats.
3. "A strong Indic ASR already recognises nearly all of these entities on
   clean audio. What is left is canonicalisation, which exact lookup does;
   fuzzy matching adds *N* mentions at *M*% corruption."
4. "Local Whisper `small` is a CPU-constrained reference, not an Indic ASR."
5. "F1's task-success numbers were scored by exact string match against a
   benchmark that expects English argument values for Hindi queries; they
   are withdrawn until re-scored."
6. What is not yet measured: phone audio, digits, real latency.

**Applications go out after `v0.1`.**

### 5.2 Release 2 — three questions

Each question has its outcomes written first. Thresholds below are the
preregistration text; they are copied into a dated section of this file,
in their own commit, before the item's first run, and not edited after.

#### Q1 — Does a strong ASR lose digit strings and entities on phone audio?

Chosen because numbers are the one failure a vendor publishes as unsolved
and the literature supports (§2, §2.1), nobody has published a Hindi
digit-string number, the density pre-flight already passes, and the
channel simulator exists.

The question has two halves, because the literature says they differ
(§2.1): the **channel** (same utterances, with and without a phone codec)
and real phone **speech** (a different corpus, recorded over telephones).

| ID | Item | Size | Cost |
|---|---|---|---|
| 3B-17 | (a) number normalisation for scoring: both sides reduced to digit strings, English words accepted in either script; try Sarvam's `indic-numtowords` first, hand-written table as fallback; unit tests; no Whisper-style normaliser on Hindi. (b) **digit-string exact match** and normalised WER from the cached clean transcripts | 2 | none |
| 3B-20 | Reference arm: Groq `whisper-large-v3`, `language` forced, on the 3B-4 rows (clean) and the 3B-18 rows (`pstn`). Fallback if the free tier refuses audio: item cut, Saaras is the only strong arm, and that is said | 1 | none |
| 3B-18 | Channel half. Saaras `saaras:v3`, `transcribe` mode, on the 290 test-split entity rows through `pstn` (8 kHz narrowband + G.711 mu-law, sent as WAV) | 2 | about Rs 33 |
| 3B-21 | Speech half. A fixed random sample (seed 0) of real telephone Hindi from Gram Vaani (the Vistaar benchmark's copy), at most 35 minutes, through Saaras and the 3B-20 Whisper arm. WER, plus digit-string match where the density check passes | 2 | at most Rs 17 |

Extra pre-flight for 3B-18: the 30 s row is accepted; an 8 kHz WAV is
accepted (if not, upsample to 16 kHz and say so); the model string in the
response is `saaras:v3`.

Extra pre-flight for 3B-21: the data is downloadable and its licence
allows this use; it fits on D: (C: has 6 GB); at least 100 utterances;
reference transcripts are usable. **Fallback if any of these fails:** the
credit slot goes to `pstn+loss5` on the 3B-18 rows (the condition this
item replaced), and the README says the speech half was not measured.

Metrics for the channel half, clean vs `pstn`, per ASR, paired by row:
digit-string exact match, recognition EER, normalised WER. "Degrades"
means an absolute drop of at least 5 points **and** exact McNemar
p < 0.05 against clean. *Recorded expectation:* little or no degradation
(§2.1).

The speech half is **not paired** and is never presented as a channel
effect: it is "the same ASR on real phone speech", with dialect and
spontaneity confounded, exactly as in the published comparison it
reproduces.

| Outcome | README sentence | Next step |
|---|---|---|
| Channel: neither degrades | "A phone codec alone does not hurt a strong Indic ASR on these utterances." | none |
| Channel: digits degrade, entities hold | "The phone channel costs *X* points of digit-string accuracy and leaves entities intact." | none; the remedy is a product one (read-back and confirmation), noted in one line |
| Channel: entities degrade | "The phone channel costs *X* points of entity recognition." | re-run the 3B-15 three-way table on the new transcripts (free, already coded). That is where fuzzy repair is finally judged |
| Clean digits already poor (3B-17) | "Digit strings are lost even on clean audio: *X*% exact." | 3B-18 still runs as planned |
| Speech: WER far above the clean rows | "On real telephone Hindi the same ASR goes from *A*% to *B*% WER; the codec accounts for *C* of that." | none |
| Speech: WER close to the clean rows | "Real telephone Hindi costs this ASR little on this sample." | none |

Caveats carried with every Q1 number: the channel is simulated (codec and
band limit only; no handset, network or noise), so it is a lower bound;
the speech half differs from the clean rows in more than the channel;
single-reference Hindi WER carries several points of spelling noise.

#### Q2 — Why does the agent fail with perfect transcripts?

| ID | Item | Size | Cost |
|---|---|---|---|
| 3B-5 | Noise floor, as preregistered in `phase-3b.md` §10 (in progress) | running | Groq quota, about Rs 13 Sarvam |
| 3B-19 | The judge. (a) From the 3B-5 run log, no new calls: classify every `gt` failure (wrong function / missing argument / value mismatch / provider-rejected call / no call). (a2) **Fix the list-argument bug** and re-score, no new calls: the benchmark stores a list-valued argument as its elements, and the judge compares the whole returned list against each element, so a correct list always fails (§5.2.1). (b) A **meaning-level judge** for the remaining argument-value mismatches, as the benchmark's authors use: an LLM call per mismatch, exact matches pass without a call; the rubric accepts the same value in another script or language. (c) Owner hand-labels 50 mismatches (seed 0, both languages) *before seeing the judge's verdicts*; agreement and kappa reported. (d) Re-score the whole log under both judges | 3 + owner hour | Groq quota |

The mechanism is already established (§2.1): the Hindi tasks expect
English argument values. What 3B-19 measures is how much of the ceiling
that explains. It starts as soon as the first replicate of the `gt`
condition is in the 3B-5 log; it does not wait for the whole run.

3B-5's preregistered analysis (exact-match judge) is reported exactly as
registered. The meaning-judge analysis is an addition, preregistered in
its own commit before step (b) runs, using the same decision rule as
`phase-3b.md` §10.6. Both tables appear side by side.

| Outcome | README sentence | Next step |
|---|---|---|
| Judge agrees with the owner's labels (kappa at least 0.6) and the `gt` ceiling rises to 60% or more in both languages | "Our exact-match judge was a fourth measurement bug: the benchmark expects English argument values for Hindi queries. Under a meaning-level judge the ceiling is *X*% / *Y*%." | F1's ASR loss is read from the meaning-judge table under the §10.6 rule, whatever it shows |
| Judge agrees, ceiling stays low | "Even with a meaning-level judge this LLM completes *X*% of Hindi tasks with perfect transcripts; at this model size the reasoning step fails more often than the ASR." | one re-run of the `gt` arm only with `openai/gpt-oss-120b` (275 calls) to show whether a stronger model lifts it |
| Judge does not agree with the owner's labels (kappa below 0.6) | "We could not build a reliable automatic judge; F1 is reported under exact match only, as a lower bound, with the mismatch breakdown." | none |
| ASR loss inside the noise floor, under either judge | "The ASR penalty on this benchmark is not distinguishable from LLM sampling noise." | none |

F1 is described as "judge under repair" everywhere until 3B-19 is `[x]`,
and no "X% lost to ASR" line appears before then.

##### 5.2.1 What the finished 3B-5 run showed (read 2026-11-15)

3B-5 completed (2,475 of 2,475 cells; `results/f1_noise_floor.json`,
item at `[?]`). Under the registered exact-match judge, ASR costs task
success in three of four arms; Hindi/Saaras is not distinguishable from
noise. A throwaway read of the committed run log (to be reproduced by
3B-19 before any of it is quoted) found:

| Finding | Number (unreproduced) |
|---|---|
| List-valued arguments always fail the judge | 19 of 141 English and 16 of 134 Hindi tasks have one; a list-aware re-score lifts the ground-truth rate from 53.2% to 65.0% (English) and 32.1% to 38.6% (Hindi) |
| The harness sends only the user message. The benchmark's own system instruction ("give the tool call arguments in English only", plus a one-shot example) is never sent | 103 of 402 Hindi ground-truth cells fail on a value returned in Devanagari |
| ASR loss barely moves under the list fix | Whisper 24.3 / 12.2 pp, Saaras 13.5 / 6.7 pp (English / Hindi) |
| Whisper `small` is not deterministic | 8 of 30 re-transcriptions byte-identical (`results/f1_whisper_determinism.json`) |

Consequences, all inside this plan: (a2) above is added; the judge rubric
in (b) accepts cross-script values, which covers the Devanagari cells
without a re-run; the missing system instruction is recorded as a
deviation from the benchmark's protocol on every F1 number. A full re-run
*with* the benchmark's instruction is parked (§7).

#### Q3 — What is the real response time, and where does it go?

| ID | Item | Size | Cost |
|---|---|---|---|
| 3B-9 | 50 recorded utterances replayed at real time through endpointer → STT → LLM → TTS. Two STT arms: Sarvam realtime streaming (8 kHz mu-law) and local Whisper `tiny`. Report end of speech → first agent audio byte, p50 and p90, split by stage | 3 | about Rs 3 |
| 3B-10 | One real phone call with barge-in and measured `clear`-to-silence time | 1 to pre-flight | — |

There is no pass mark for 3B-9; the number is reported whatever it is,
beside the mock-based figure it replaces. Fallbacks, in order, if the
realtime endpoint fails its pre-flight: the legacy streaming endpoint
(final transcripts only), then REST with the request time measured.

3B-10 is `[!] blocked:` as written (Twilio trials block Media Streams).
Its one session is spent pre-flighting, in order: a Plivo trial, then an
Exotel trial. If neither streams audio on a free trial, the item stays
blocked, the README says so, and paying for a Twilio upgrade is an owner
decision recorded in §9 — it is not taken silently.

### 5.3 Sizes

Release 1 is 4 sessions. Release 2 is about 14 plus the owner's hour.
Release 2 stops when its items are done or at 28 sessions, whichever comes
first; what is unfinished is written up as unfinished.

---

## 6. Checkpoints and change control (R5)

The plan is read and possibly changed at exactly two points:

- **Checkpoint 1 — after `v0.1`.** Allowed: cut a Release 2 item.
- **Checkpoint 2 — after Q1.** Allowed: cut Q2 or Q3 items; promote **one**
  parked item whose entry condition (§7) is met.

**Checkpoint 2 record (2026-11-15, after Q1, at the owner's instruction).** Q1 is closed
(3B-17, 3B-18, 3B-20, 3B-21 accepted `[x]`). Taken at this checkpoint: **nothing
promoted from the parking lot** (§7); **3B-9 kept**, uncut; **3B-10 kept** with its one
pre-flight session, a Plivo trial then an Exotel trial, to be cut and stated in the README
if neither streams audio on a free trial. No Q2 or Q3 item is cut.

**Update, same day:** neither trial route works (Plivo trials need a company account;
Exotel has no self-serve login). A self-hosted SIP gateway with a softphone was proposed
and **declined by the owner**. **3B-10 is therefore cut** (it stays listed, R6); the README
says no real phone call was made.

At any other time the only allowed moves are the fallbacks written beside
each item. A new idea, a new dataset, a better metric or a surprising
result is written into §7 and waits for a checkpoint. An agent that thinks
the plan is wrong says so in its report and continues with the plan.

---

## 7. Parking lot

Nothing here is worked on unless promoted at a checkpoint.

| ID | Item | Entry condition |
|---|---|---|
| 3B-6 | Real jitter model | Q1 shows loss matters and a jitter condition would add to it |
| 3B-7 | Keyword biasing (`saaras:v4` `keyterms`, Whisper `hotwords`) vs post-correction | Q1 outcome "entities degrade", and credits for one more 65-minute arm |
| 3B-8 | TTS round-trip for entities and number reading | Release 2 complete |
| 3B-11 | One command regenerates every number | Release 2 complete (mostly delivered by 3B-14, 3B-15, 3B-17) |
| 3B-12 | Fuzzy-matcher hardening, dev rows and a fresh draw only (`phase-3b.md` §11.5) | Q1 outcome "entities degrade" |
| 3B-13 | Entity-bearing task on real audio | Q2 complete and Q1 outcome "entities degrade" |
| — | `pstn+loss5` channel condition on the 3B-18 rows (about Rs 33) | only as the written fallback of 3B-21, or Release 2 complete with credits left |
| — | F1 re-run with the benchmark's own system instruction (2,475 calls, about two days of free quota) | Q2 complete, and the meaning-judge ceiling still below 60% in Hindi |
| — | Third ASR arm on a free credit (Deepgram, smallest.ai Pulse) | Release 2 complete |
| — | Sarvam's `llm_wer` / entity-preservation score beside our metrics | Release 2 complete |
| — | Contribution to an open-source voice-agent framework | owner's choice, outside this repo |
| F3, F4, F5 | Code-switching, safety, turn-taking | after Release 2 |

---

## 8. What this replaces

- `phase-3b.md` §11.2–11.4 and §11.6 (the first Nov 14 re-plan): item
  definitions and order now live here. §11.1 (findings) and §11.5 (the
  test-split constraint) stand.
- Changes from that re-plan, each forced by a check made the same day:
  3B-13 goes back to the parking lot (it needs Q1's answer first); 3B-20
  is new (a strong Whisper is available without local RAM); 3B-21 is new
  and takes the credit slot of `pstn+loss5` (the literature says the phone
  gap is in the speech, not the codec); 3B-19 becomes a judge repair, not
  only a breakdown (the benchmark expects English values for Hindi tasks).
- `ROADMAP.md` Phase 4 "Ship" items: the README and results work is 3B-16;
  the rest (demo recording, deployment, failure-mode write-up) is parked
  until Release 2 is complete.

---

## 9. Owner decisions

Fill in to accept. Defaults apply if left blank.

| # | Decision | Default |
|---|---|---|
| 1 | Accept this plan and its change-control rule | — |  <!-- accepted 2026-11-15 -->
| 2 | Sarvam spend: 3B-18 `pstn` (about Rs 33), then 3B-21 (at most Rs 17), then 3B-9 (about Rs 3) | yes, under the §4 stop rule |
| 3 | Pay for a Twilio upgrade if no free trial streams audio | no; 3B-10 stays blocked |
| 4 | Thesis line in `ROADMAP.md`: keep as the hypothesis tested, or rewrite | keep, with the dated status note |
| 5 | Send audio from the cached datasets to Groq for 3B-20 | yes (same data already sent to Sarvam) |
| 6 | One hour to hand-label 50 argument mismatches for 3B-19, before seeing the judge's verdicts | yes |

Decision 1 accepted; decisions 2-6 left blank, so their defaults apply.

Accepted by: Gaurav Chaudhari (Chgauravpc) on 2026-11-15
