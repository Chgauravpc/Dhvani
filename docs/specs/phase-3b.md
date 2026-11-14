# Phase 3B — Measurement Audit, and What Makes This Stand Out

**Window:** Sep 24 – Oct 10 2026 (Phase 3 finished early; this uses that slack,
not the Oct 26 buffer).
**Status:** plan only. Written from a read-through review of `ROADMAP.md`,
`README.md` and every `docs/specs/phase-*.md`, plus one read-only text check
of the cached Svarah/LAHAJA transcripts (section 2). No code has been changed
for this phase.

**Read section 0 before touching any checkbox in this file or in `ROADMAP.md`.**

---

## 0. Execution rules — how a checkbox gets ticked

This project's value is that every number survives a follow-up question. The
fastest way to destroy that is a checkbox ticked because the code *exists*,
because a mock test passed, or because a substitute experiment was run in
place of the specified one. The history already shows the pattern: `base`
Whisper skipped from the sweep, `tiny` silently substituted for `small` in
F1, the degradation sweep run on one dataset instead of two. Each was
disclosed, which is good — but each was also ticked `[x]`. From this phase
on, these rules apply to every agent and every human, and they apply
retroactively to the items reopened in section 5.

### 0.1 Status markers

| marker | meaning |
|---|---|
| `[ ]` | not started |
| `[~]` | in progress, or code written but the real run not yet done |
| `[?]` | done by an agent, **awaiting human review** — the only state an agent may move a results item into |
| `[x]` | done, evidence attached, reviewed |
| `[!]` | blocked or invalidated — must carry `blocked:` or `invalidated:` and a reason |

### 0.2 An item may be moved to `[?]` or `[x]` only if all of these hold

1. **The exact specified thing was done.** Not a smaller model, fewer
   examples, one dataset instead of two, or a mock instead of a real run. If
   a substitute is the only option, the item becomes `[!] blocked:` with the
   reason, and the substitute is recorded as a *separate*, new item. Never
   tick the original.
2. **An evidence line is appended directly under the item**, in this form:

   ```
   evidence: <commit sha> · `<exact command run>` · <results file path> · <headline number>
   ```

   A results item without a results file (JSON/CSV under `results/`, committed)
   is not done. Terminal output pasted into a spec is not evidence; the file
   the numbers were read from is.
3. **The tick lands in the same commit as the evidence**, never in a
   separate "update roadmap" commit.
4. **Unit tests and mocks never close a "real run" item.** They close
   "implemented" items only.
5. **Gates block.** If an item is a gate (marked **GATE**), nothing below it
   may move past `[~]` until the gate is `[x]`. A failed gate is recorded as
   failed, and the pivot it prescribes is followed.
6. **Numbers are never edited in place.** A re-run adds a new row beside the
   old one with its own evidence line; the old row gets `superseded by:`.
   Invalidated numbers stay visible, struck through, with `invalidated:`.
7. **Results items (anything that reports a number) are moved from `[?]` to
   `[x]` by the project owner only.** Agents stop at `[?]` and say so in
   their final report.

### 0.3 Reviewer check (30 seconds, per PR)

`git diff main -- ROADMAP.md docs/specs/` — every new `[x]` or `[?]` must
have an `evidence:` line in the same diff, and every cited results file must
exist in the same diff. Anything else is reverted.

---

## 1. Review summary

The thesis ("Indic voice agents fail at the ear") and the discipline around
it (preregistered outcomes, dev/test split, paired corruption rate,
lower-bound caveats) are genuinely strong — stronger than most portfolio
work. The review found that **three of the headline numbers do not measure
what the docs say they measure**. None of that is a scandal; it is exactly
the kind of thing the project's own methodology exists to catch, and catching
it in public is itself the strongest thing this project can show. But it has
to be fixed before `RESULTS.md` is written, because `RESULTS.md` would
otherwise publish them.

| # | Finding | Severity | Affects |
|---|---|---|---|
| A1 | Gate + EER scorer count **substrings**, not words: over half of Svarah's "mentions" are not entity mentions | critical | gate decision, every Svarah EER number |
| A2 | EER scorer requires the **Latin canonical** string in the ASR output: a correct Devanagari transcript is scored wrong | critical | every LAHAJA EER number, the "100% on both ASRs" headline |
| A3 | Channel simulator's jitter is **cumulative sleep**, not jitter | high | the "jitter costs 4.8s" finding |
| A4 | F1 task-success deltas have **no noise floor**; LLM sampling variance is unmeasured | medium | F1 headline, F1-with-Sarvam, F1×F2 tie-together |
| A5 | Latency is measured as **STT on the whole utterance**, not voice-to-voice | medium | the sub-800ms story, every latency claim |

---

## 2. A1 — substring matching inflates entity counts

`scripts/entity_density_gate.py::_count_mentions` and
`eval/entity_error_rate.py::_mentioned_entities` both treat a variant as
mentioned if `variant.lower() in text.lower()`. Short Latin variants then fire
inside ordinary words.

One read-only recount over the same cached transcripts (text only, unique
`(example, entity)` pairs, word-boundary regex `(?<!\w)variant(?!\w)`), run
Sep 23 as a throwaway check — **not committed, to be reproduced by item
3B-1 below before being quoted anywhere**:

| dataset | entity | substring hits | word-boundary hits | what the false hits are |
|---|---|---|---|---|
| Svarah | PAN card | 66 | **0** | "com**pan**y", "**pan**tene", "aam **pan**na" |
| Svarah | GST | 10 | **0** | "youn**gst**ers" |
| Svarah | Provident Fund | 29 | **5** | "hel**pf**ul", "e**pf**o passbook" (double-counted with EPFO) |
| Svarah | Voter ID | 7 | **2** | "de**pic**ts", "indian **epic**s" |
| Svarah | UPI | 13 | **10** | "ud**upi**", "occ**upi**ed", "**pupi**ls" |
| Svarah | ESIC, EPFO, CoWIN, … | 77 | 77 | — |
| **Svarah total** | | **202** | **94** | |
| LAHAJA | Aadhaar | 23 | 21 | "**आधार**शिला", "**आधार**भूत" |
| LAHAJA | CoWIN | 17 | 17 | — |
| **LAHAJA total** | | **40** | **38** | |

Consequences:

- **The gate decision changes.** Svarah was reported as 212 mentions,
  PROCEED (≥100). On word boundaries it is ~94: the **30–100 bucket** —
  "proceed with a confidence interval and expand the lexicon". The gate did
  its job only if its counter is right.
- **Svarah `eer_before` is biased upward, probably heavily.** A transcript of
  "company" can never contain the canonical `"pan card"`, so every false
  mention is scored as an ASR error before correction. If the ~53% false
  share carried into the test split, most of the 59.4% "error rate" is the
  scorer, not the ASR. This is a hypothesis, not a number; 3B-2 measures it.
- **`corruption_rate` is also biased**: examples containing "company" were
  excluded from the clean arm, which is exactly where the corrector is most
  likely to damage text ("pan" is a 3-letter fuzzy target).

## 3. A2 — the scorer cannot see a correct Devanagari transcript

`score_transcripts` counts a mention correct only if `canonical.lower()` —
`"aadhaar"`, `"cowin"` — appears in the ASR output. All 38 real LAHAJA
mentions are written in Devanagari in the ground truth. An ASR that hears
"आधार" perfectly and writes `आधार` is scored as a miss.

So **`eer_before = 100%` on LAHAJA, for both Whisper and Saaras, is true by
construction**, and the "strongest single number in this project" (phase-2
§18) does not measure recognition at all. The large LAHAJA "recovery"
(53.6 / 64.3 points) is then mostly the corrector *transliterating*
Devanagari to the Latin canonical form — a normalization step, which is
useful, but a different claim from "recovers entities the ASR got wrong".

The same effect, smaller, hits Svarah: `"aadhar"` or `"Co-WIN"` in the output
is a correct recognition but not the canonical spelling.

**Fix, keeping the scorer independent of the matcher (phase-2 §6.7):**
report two separate rates, both by exact string match against the
*hand-curated* variant list — never via `phonetic_key`:

- **Recognition EER** — a mention is correct if *any* curated variant of
  that entity, in any script, appears word-bounded in the output. This is
  the ASR claim.
- **Canonicalization rate** — a mention is correct only if the canonical
  form appears. This is the downstream-system claim (a tool call needs
  `"Aadhaar"`, not `आधार`).

`dhvani-entity` is then evaluated on both, and the two stories can no
longer be conflated.

## 4. A3 — simulated jitter is cumulative delay

`audio/channel.py` sleeps `uniform(0, jitter_ms)` **per frame, in series**.
At 40 ms that is a mean of 20 ms added to *every* 20 ms frame — the stream
plays at roughly half speed and the delay grows with utterance length. Real
network jitter does not accumulate: packets arrive late *and* early around a
real-time mean, and a jitter buffer absorbs it for a cost of roughly one
buffer depth (tens of ms) plus late-packet loss.

The "40 ms jitter pushes STT p50 from 1.3 s to 4.8 s" result (phase-3 §12)
is therefore a property of the simulator. Also note the baseline rows are
not paced at real time at all, so their "STT latency" and the jitter row's
are not measuring the same interval.

**Fix:** model arrival times (real-time send clock + per-packet delay,
reordering allowed), put a fixed-depth jitter buffer in front of the
consumer, count late packets as lost, pace every row at real time, and
measure latency from **end of speech** to final transcript.

## 5. What is reopened

Per rule 0.2.6, nothing is deleted; these are marked `[!] invalidated:` in
`ROADMAP.md` and will get new rows beside the old ones:

- Entity-density gate result (Svarah 212 / LAHAJA 40)
- Svarah EER, Whisper and Sarvam (59.4→49.0, 46.9→39.9)
- LAHAJA EER, Whisper and Sarvam (100→46.4, 100→35.7) and the "fails on
  both ASRs" reading
- The jitter row of the degradation sweep and its "jitter costs more than
  model choice" conclusion

Still valid as reported: F1's absolute and share-of-achievable numbers (with
their caveats, and pending A4's noise floor), the model-sweep Pareto
results, the WER rows of the degradation sweep that have no jitter, CI, the
Twilio protocol work, the mu-law/resampler work.

---

## 6. Improvements — prioritized

Numbered `3B-n` so evidence lines can cite them. Priority 0 must land before
`RESULTS.md` (Phase 4). Priority 1 is what makes the project stand out.
Priority 2 is only if time remains; none of it may displace Phase 4.

### Priority 0 — make the existing numbers true

- [x] **3B-1 GATE — reproduce the audit.** Word-boundary, deduplicated
      (example, entity) counting, shared by the gate script and the scorer
      (one function, not two copies that can drift). Longest-variant-wins so
      "aadhaar card" and "aadhaar" do not double count. Re-run the gate on
      both datasets. Commit the per-entity table as a results file.
      *Done when:* results file shows per-entity substring vs. word-boundary
      counts for both datasets, and the gate decision is restated from it.
      If Svarah < 100, follow the 30–100 rule literally (CI + lexicon
      expansion from what the data contains — ESIC/EPFO/CoWIN/UPI dominate).
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
- [x] **3B-2 — two-rate scorer.** Recognition EER and canonicalization rate
      (section 3), both exact-match on curated variants, both paired with
      `corruption_rate`. Unit tests must include: Devanagari-correct output
      counted as recognized; "company" not counted as a PAN mention; a
      variant spelling counted as recognized but not canonical.
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
- [x] **3B-3 — cache raw transcripts.** Every STT run writes
      `(dataset, split, example_id, stt, model, raw_text)` to a committed
      JSONL. Rescoring after a scorer fix must never need a re-transcription
      or Sarvam credits again. This is what made A1/A2 expensive to fix.
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
- [?] **3B-4 — re-run F2 EER on both datasets × both ASRs** with 3B-1..3B-3,
      same dev/test protocol, threshold re-tuned on dev per STT. Old rows
      stay, marked superseded. **Preregister first** (commit before the
      run): what does it mean if recognition EER on LAHAJA is low for
      Saaras? (Answer to write down: the entity failure was a scoring
      artifact on LAHAJA; F2's value there is canonicalization, and the
      README says so.)
      evidence: <this commit> · four committed results files
      `results/f2_eer_{svarah,indicvoices-hindi}_{whisper,sarvam}.json` + four
      transcript logs under `results/transcripts/` (243 / 243 / 464 / 464
      rows, every row transcribed once) · preregistration `b47d29f` precedes
      every run · deviations 1-3 in §9.7 · LAHAJA not run (gate failed, 3B-1).
      Test split, dev-chosen threshold, recognition EER / canonical miss
      before -> after, corruption on clean rows:
      Svarah+Whisper 25.8% -> 12.1% / 28.8% -> 12.1%, corruption 11.4%;
      Svarah+Saaras 0.0% -> 0.0% / 1.5% -> 0.0%, corruption 0.0%;
      IndicVoices+Whisper 93.8% -> 17.4% / 100% -> 17.4%, corruption 14.8%;
      IndicVoices+Saaras 4.5% -> 0.8% / 99.6% -> 0.8%, corruption 0.0%.
      Verdicts by the §9.4 rules (not by how good the number looks):
      rule 1 (canonicalization improves) holds only for IndicVoices+Saaras
      (239 fixed / 0 broken, corruption 0.0% <= 5%); Whisper arms are
      trade-offs (corruption 11.4% / 14.8% > 5%); Svarah+Saaras has nothing
      to fix (p = 1.0). Rule 2 (recognition repair) holds for three arms
      (Svarah+Whisper 9/0, IndicVoices+Whisper 185/0, IndicVoices+Saaras
      9/0, all p < 0.05) -- the preregistered prediction that it would
      mostly fail was wrong for Whisper. Rule 3: Saaras Hindi recognition
      EER 4.5% (CI 2.6-8.0%) <= 15%, so the "entities fail on Hindi"
      headline was mostly the A2 scoring artifact and F2's Hindi value is
      canonicalization. A1 prediction confirmed (both Svarah recognition
      EERs far below the superseded 59.4% / 46.9%). Caveats travel with
      all of it (§9.5): read speech, Saaras may have trained on IndicVoices
      `train`, clustered sample so CIs are optimistic, n ~ 66 on Svarah.
      Old rows in ROADMAP/phase-2 are NOT yet marked superseded -- that
      edit is left to the owner's review.
- [?] **3B-5 — F1 noise floor.** Run the ground-truth condition twice
      (A/A). The GT-vs-GT delta *is* the noise floor; any ASR-vs-GT delta
      inside it is not a finding. Repeat each condition k≥3 times, report
      mean ± paired-bootstrap CI and a McNemar test on the paired
      per-example outcomes. Use the full `single_tool` set, not 40.
      Preregistered in §10 (commit 9b30533, before any code or run).
      evidence: <this commit> · `uv run python scripts/run_f1_noise_floor.py
      --phase asr|llm|determinism` then `scripts/analyze_f1_noise_floor.py` ·
      `results/f1_noise_floor.json`, `results/f1_runs/runs.jsonl` (2,475 of 2,475
      cells scored, 0 incomplete), `results/transcripts/f1_noise_floor_{whisper,sarvam}.jsonl`,
      `results/f1_whisper_determinism.json` · full `single_tool` set (141 en + 134 hi),
      k = 3, Groq gpt-oss-20b. Deviations 1-5 in §10.9.
      GT run-to-run success rate: English 56.7 / 50.4 / 52.5% (noise floor 6.4 pp),
      Hindi 31.3 / 32.1 / 32.8% (1.5 pp). ASR loss (GT minus real, mean over runs,
      paired-bootstrap 95% CI, majority-vote McNemar), by the §10.6 rule:
      English/Whisper 19.6 pp [13.2, 26.5], 29/2, p = 5e-7 -> ASR costs task success;
      English/Sarvam 12.3 pp [7.1, 17.7], 20/3, p = 5e-4 -> ASR costs task success;
      Hindi/Whisper 10.2 pp [3.7, 16.9], 25/7, p = 0.002 -> ASR costs task success;
      Hindi/Sarvam 6.0 pp [1.0, 10.9], 16/7, p = 0.093 -> NOT distinguishable from
      LLM sampling noise (CI excludes 0 but McNemar does not).
      Results the preregistration did not expect, stated plainly:
      (1) The determinism check FAILED: 8 of 30 Whisper re-transcriptions were
      byte-identical (English 5/13, Hindi 3/17) against a predicted >= 95%. The
      "decoding is deterministic" assumption in §10.3 is false for Whisper; each
      Whisper transcript is one draw from a stochastic ASR, and that variance is
      NOT in the noise floor or the CIs (which resample examples). Cause not
      investigated (faster-whisper's default temperature fallback is one candidate).
      Saaras determinism was not checked (credits), so the Sarvam rows carry the
      same unquantified caveat. How different the re-transcriptions are was not
      measured.
      (2) On the Phase 2 subset (first 40 per language) Hindi/Whisper loss is
      -1.7 pp [-11.7, 8.3] against 10.2 pp on the full 134: the old "10.0%
      Hindi loss" at n = 40 was mostly a draw. English/Whisper first-40 is 22.5 pp
      (old: 27.5). Hindi/Sarvam first-40 is 2.5 pp; the old -7.5 pp was noise.
      (3) The GT-only noise floor understates run-to-run spread: the real-ASR arms
      vary more (English/Sarvam 39.7 / 37.6 / 45.4%, a 7.8 pp range; Hindi/Whisper
      18.7 / 22.4 / 24.6%, 5.9 pp). §10.6 uses the GT floor as written.
      (4) Ceiling: with perfect text the agent passes ~53% (English) and ~32%
      (Hindi) of tasks on the full set; 8-15% of examples change outcome between
      GT runs. That ceiling is the larger limit on any ASR effect (§11 B5, 3B-19).
      Prediction check (§10.7): noise floor <= 4 pp: English 6.4 NO, Hindi 1.5 yes;
      5-12% flips: English GT 7.8-10.6% yes, Hindi GT 12.7-14.9% slightly above;
      English/Whisper 15-35 pp and passes: yes (19.6); Hindi/Whisper >= 40% likely to
      fail: it passed; Sarvam Hindi loss < Whisper Hindi loss: yes (6.0 < 10.2, not
      significant); determinism >= 95%: NO (27%).
      Pooled (secondary): Whisper 15.0 pp [10.4, 19.6], Sarvam 9.2 pp [5.6, 12.8].
      Caveats of §10.8 apply (synthesized audio is a lower bound; one LLM; k = 3).
      Old F1 rows in ROADMAP / phase-2 are NOT yet marked superseded; left to review.
- [ ] **3B-6 — fix the jitter model** (section 4) and re-run only the rows
      it affects. Report latency from end of speech.

### Priority 1 — what makes this stand out to speech and telephony companies

The project today is an *STT evaluation* project with a voice agent around
it. Companies that build ASR/TTS models or voice products on them
(smallest.ai, Sarvam, SuperKalam) and companies that carry the audio
(Twilio, Exotel, Plivo) each look for one extra thing. These are chosen because each reuses
harness that already exists.

- [ ] **3B-7 — decode-time biasing vs. post-ASR correction.** The
      industry-standard fix for entity errors is contextual biasing inside
      the decoder (keyword boosting / hotwords / prompt biasing), not a
      post-processor. Compare on the same test split: (a) raw, (b) decoder
      biasing with the lexicon, (c) `dhvani-entity` post-correction,
      (d) both. Verify the real biasing parameters of faster-whisper and of
      Sarvam's API against installed code / current docs before building —
      do not assume them. This is Phase 2B's own principle ("test against
      the strongest alternative") applied to F2, and it is the question an
      ASR team will ask first.
- [ ] **3B-8 — the mouth, not just the ear: TTS round-trip entity test.**
      Synthesize every lexicon entity plus Indic text-normalization cases
      (₹1,250; 12/10/2026; "UPI ID"; phone numbers read digit-by-digit;
      Hinglish sentences) through the shipped TTS, transcribe back with the
      best ASR, score recognition EER with the 3B-2 scorer. Report
      TTS-induced entity loss and TTS time-to-first-byte. A TTS company
      reads this as "understands text normalization and pronunciation";
      today the project says nothing about TTS quality at all.
- [ ] **3B-9 — voice-to-voice latency, measured the way the industry
      quotes it.** End of user speech → first byte of agent audio, p50/p90,
      on real recorded utterances, per stage (endpoint, STT final, LLM first
      token, TTS first byte). Compare local `faster-whisper` against at
      least one hosted/streaming STT on a free tier (verify availability
      and limits first). This replaces "sub-800ms (with mocks)" with an
      honest real number and a waterfall that shows where the time goes.
- [ ] **3B-10 — a real phone call.** One recorded call through the
      verified Twilio Media Streams transport (trial account), with a
      barge-in, and the measured `clear`-to-silence latency. For a telephony
      reader this single artifact outweighs the simulator. If a trial
      account is not possible, `[!] blocked:` — do not substitute the mock
      server and tick it.
- [ ] **3B-11 — one-command reproducibility.** `make results` (or one
      script) regenerates every headline number from cached transcripts
      (3B-3) into `results/*.json`, and `RESULTS.md` tables are rendered
      from those files, not typed by hand. This is what model companies
      mean by an eval harness.

### Priority 2 — only if P0 and P1 are `[x]`

- [ ] **3B-12 — corrector hardening**, each change measured by the 3B-2
      scorer, not argued: best-scoring window instead of widest (the
      documented "swallows *my*" source), a minimum key length or
      exact-only rule for 2–3 letter acronyms (PAN, PF, UPI, GST), and a
      common-word stoplist.
- [ ] **3B-13 — entity-bearing task set** tying F1 to F2 on *real human
      audio*: a slot-filling tool (`lookup_document(type=…)`) driven by the
      Svarah/LAHAJA entity utterances themselves. Removes both the 2-of-80
      overlap problem and the synthetic-audio lower-bound caveat in one move.

---

## 7. How this changes the resume line

Before: *"Built an Indic voice agent; post-ASR entity correction recovers
10–54 points of entity error."* — two of those numbers are currently scoring
artifacts, and an interviewer who opens the code finds that in ten minutes.

After (only once the evidence exists — do not write it earlier):

- *"Audited my own evaluation and found three measurement bugs (substring
  entity matching, script-blind scoring, cumulative jitter) that had
  inflated headline results; fixed and re-ran with preregistered outcomes."*
- *"Compared decoder-side contextual biasing with post-ASR correction for
  Indic entities, on real accented speech, with paired corruption rates."*
- *"Measured voice-to-voice latency over a real Twilio call, per stage,
  with barge-in."*
- *"TTS round-trip test for Indic text normalization and entity
  pronunciation."*

The first bullet is the differentiator. Almost nobody reports finding their
own inflated numbers; for a research-minded speech team it is the most
credible signal in the whole project.

---

## 8. Open questions for the owner

1. If 3B-4 shows LAHAJA recognition EER is low for Saaras, is F2's Hindi
   story reframed as canonicalization, or is the Hindi half dropped?
2. Is a Twilio trial account acceptable under the "no paid infrastructure"
   rule (trial credit is free, but needs a phone number verification)?
3. Which hosted streaming STT is acceptable for 3B-9 under the same rule?

---

## 9. 3B-4 preregistration — written and committed before any 3B-4 run

Committed 2026-11-13 in its own commit, before the first transcription of
any 3B-4 arm. Nothing below changes after that commit. A deviation forced
by a run (crash, quota, a bug) is recorded as a numbered deviation in
§9.7 with its reason; it is not edited into §9.1–9.6.

### 9.1 Arms

| dataset | ASR | model |
|---|---|---|
| Svarah (Indian-accented English) | faster-whisper | `small` / `int8` (the Phase 2 setting) |
| Svarah | Sarvam Saaras | `saaras:v3` |
| IndicVoices Hindi | faster-whisper | `small` / `int8` |
| IndicVoices Hindi | Sarvam Saaras | `saaras:v3` |

LAHAJA is **not** run: its gate failed (3B-1, 17 real pairs). IndicVoices
Hindi replaces it (owner decision 2026-11-12, 3B-1a). The roadmap's "2 × 2"
is these four arms. Language codes are left to each ASR's auto-detection,
as in Phase 2.

### 9.2 Data and sampling (fixed, seed 0)

- **Lexicon v2** (commit 167c80e: bare `आधार` / `पैन` / `pan` removed;
  `आधार नंबर`, `पैन नंबर`, `pan number` added). Mentions: the shared
  word-bounded matcher from 3B-1.
- **Svarah:** every entity-bearing row plus 150 entity-free rows
  (`load_svarah_filtered`, seed 0). Dev/test 30/70 **by row** at random,
  seed 0 — the Phase 2 protocol, kept for comparability. Speakers may
  appear in both splits; that is a stated limitation, not fixed here.
- **IndicVoices Hindi:** cluster sample by shard
  (`select_indicvoices_eval_rows`, seed 0, `min_entity_rows=300`,
  `n_clean=150`). Why shards and not rows: random rows would touch hundreds
  of ~91 MB audio row groups (measured remote read ~0.6 MB/s, full-shard
  download ~2 MB/s, 7 GB disk free). The dry run of this exact call draws
  **14 shards** — train-00041, 00023, 00048, 00059, 00052, 00037, 00077,
  00026, 00044, 00024, 00069, 00050, 00008, 00001 — giving **314
  entity rows / 337 entity pairs** (Aadhaar 145, PAN card 78, CoWIN 32,
  DigiLocker 32, Ayushman Bharat 25, Ration card 10, others 15), 228 of
  them in government-service tasks, and 150 clean rows. Speech type of the
  entity rows: 235 Read, 64 Conversation, 15 Extempore. Dev/test **by
  speaker**: a speaker is dev iff `sha256(speaker_id) mod 100 < 30`.
- The same rows, splits and audio go to both ASRs of a dataset. Only the
  inner ASR differs between arms.

### 9.3 Threshold and scoring

- Grid `0.70 0.75 0.80 0.82 0.85 0.90 0.95`, tuned **per arm on dev** by
  minimising `canonical_miss_after + corruption_rate` (ties → higher
  threshold). Test is scored **once**, at that threshold.
- Reported on test for every arm: recognition EER and canonical miss rate,
  before and after correction, each with a 95% Wilson CI; paired
  fixed/broken counts with an exact two-sided McNemar p for each; corruption
  rate on the clean arm with its CI. The dev sweep is reported too.
- Every transcript is logged (3B-3) and committed with the results file
  `results/f2_eer_<dataset>_<stt>.json`.

### 9.4 Decision rules

1. **"The corrector improves canonicalization"** is claimed for an arm only
   if, on test, `canonical_fixed > canonical_broken`, the canonical McNemar
   p < 0.05, **and** corruption rate ≤ 5%. If corruption is above 5%, the
   result is reported as a trade-off, not an improvement, whatever p is.
2. **"The corrector repairs recognition"** (fixes entities the ASR got
   wrong, not just spellings/scripts it got right) is claimed only if
   `recognition_fixed > recognition_broken` and recognition McNemar
   p < 0.05. *Prediction:* this will mostly fail — most of the corrector's
   effect is expected to be canonicalization.
3. **What Hindi recognition EER before correction means** (the question
   §6 3B-4 asked of LAHAJA, now asked of IndicVoices):
   - Saaras recognition EER ≤ 15% → the "entities fail on Hindi" headline
     was mostly the A2 scoring artifact. F2's Hindi value is
     canonicalization, and the README says exactly that.
   - Saaras > 15% → Hindi entity recognition is a real failure even for a
     purpose-built Indic ASR; F2's job there is genuine repair, judged by
     rule 2.
   - Whisper vs Saaras is reported as measured. A Saaras number below
     Whisper's is **not** evidence that Saaras is better in general, see
     §9.5 contamination.
4. **Svarah prediction (A1):** recognition EER before correction will be
   well below the superseded 59.4% (Whisper) / 46.9% (Sarvam) `eer_before`,
   because those counted substring false hits and non-canonical spellings
   as errors. Recorded as a prediction to check, not a decision rule.
5. No test split is re-run to obtain a different number. A crashed run
   resumes from the transcript log (same rows, same transcripts); the
   sample is never redrawn.

### 9.5 Caveats that travel with every 3B-4 number

- **Read speech:** 235 of 314 IndicVoices entity rows are read prompts,
  easier than spontaneous speech — recognition EER there is a lower bound.
- **Contamination:** all IndicVoices rows are from `train`; Saaras may
  have been trained on it. Saaras IndicVoices numbers are potentially
  in-distribution and are flagged as such wherever quoted.
- **Clustered sample:** shards (and speakers within them) are the sampling
  unit; the Wilson CIs and McNemar tests assume independent mentions and
  so understate the uncertainty.
- **Small Svarah sample:** ~94 entity pairs in total, ~66 on test.
- **Absolute numbers are not comparable to Phase 2's.** The old rows used
  the substring matcher and the canonical-only scorer; they stay visible,
  marked superseded by these four files.

### 9.6 Cost

Whisper arms run locally (one process per arm, as the model sweep had to).
The two Saaras arms send roughly 700 utterances (Svarah ≈ 240 rows,
IndicVoices 464 rows) to the Sarvam API on the owner's credits, authorised
by the owner 2026-11-13.

### 9.7 Deviations

1. **IndicVoices audio loader crashed on Windows (2026-11-13).** The first
   Hindi/Whisper run died with `PermissionError: [WinError 32]` when
   `load_indicvoices_examples` tried to delete the downloaded shard
   `train-00001-of-00082.parquet`: the `pq.ParquetFile` handle was still
   open. Fix: close the handle before `unlink` (`datasets.py`, 3 lines).
   No sampling, split, threshold, scoring or lexicon change; the row
   selection is the same 14-shard draw, and the per-row audio already cached
   by the crashed run is reused. No transcription had happened yet.
2. **Throughput: Whisper `cpu_threads` (2026-11-13).** The Hindi/Whisper arm
   was killed three times by the host's low-memory reaper and resumed from the
   transcript log each time (80, 166, then 241+ of 464 rows kept). To finish
   sooner, `WhisperSTT` gained an optional `cpu_threads` (default 0 =
   CTranslate2's default, unchanged), set via `DHVANI_WHISPER_CPU_THREADS`; the
   remainder of this arm runs with 8 of 12 cores instead of the default 4.
   Model (`small`), compute type (`int8`), language handling and decoding
   options are untouched. Caveat: rows transcribed before the change used 4
   threads; thread count can in principle perturb float reductions in the last
   bits, so a row could differ from a re-run at another thread count. Rows are
   never re-transcribed, so this arm mixes the two, with no known effect on text.
3. **Sarvam credits ran out, then a network error (2026-11-13/14).** The
   Hindi/Saaras arm hit HTTP 402 `insufficient_quota_error` at 315 of 464
   rows; the owner supplied a replacement API key (used for that run only,
   passed in the environment, not stored in the repo or any results file). The
   resumed run then failed once more at 444/464 with a `ProviderError` whose
   message was empty (consistent with an `httpx` timeout or dropped
   connection; the exception type was not captured), and was resumed again
   from the transcript log. Every row was transcribed exactly once; failed
   requests produced no log line, so no row was re-sent after a success. The
   two keys are not distinguished in the log, and Sarvam-side behaviour could in
   principle differ between accounts; nothing indicates it did.

---

## 10. 3B-5 preregistration — F1 noise floor, written and committed before any 3B-5 run

Committed 2026-11-14 in its own commit, before any code for this item and
before any LLM or ASR call made for it. §10.1–10.8 do not change after that
commit. A deviation forced by a run is a numbered entry in §10.9 with its
reason; it is never edited into the sections above.

### 10.1 What is measured, and why

A4: every F1 task-success delta so far came from **one** LLM sample per
condition per example, on 40 examples per language. LLM sampling noise was never
measured, so no delta can be told apart from it. This item measures that noise
floor and re-states F1 against it. It does **not** change what F1 measures
(tool-call success on VoiceAgentBench `single_tool`, same judge, same LLM,
same prompts).

### 10.2 Arms and data

- **Examples:** the **full** VoiceAgentBench `single_tool` set, both languages
  that F1 used: **141 English + 134 Hindi = 275** (counted 2026-11-14 from the
  dataset manifests). No sampling, no filtering. The Phase 2 F1 rows used the
  first 40 per language, which is a subset; it is also reported separately for
  comparability.
- **Conditions per example:**
  - `gt` — LLM on the ground-truth text (`GroundTruthSTT`).
  - `whisper` — LLM on faster-whisper `small` / `int8` text (the Phase 2
    setting).
  - `sarvam` — LLM on Saaras `saaras:v3` text (the Phase 2B baseline).
- **LLM:** Groq `openai/gpt-oss-20b`, `reasoning_effort` and tool schema
  handling exactly as in the shipped `GroqLLM` / `task_success` code at the
  commit that precedes the run (recorded in the results file), **no
  temperature or seed set** (provider default, as in Phase 2). The model name
  and run dates are recorded; Groq may change the served model between days and
  that is a stated limitation.
- **k = 3** independent LLM runs of every condition on every example.

### 10.3 Procedure

1. **ASR once per example per ASR**, text appended to the 3B-3 transcript log
   and reused by all three LLM runs. The noise floor is about *LLM sampling*;
   decoding by Whisper / Saaras is treated as deterministic. That assumption
   is **checked, not assumed**: 30 examples (seed 0, both languages) are
   transcribed a second time with Whisper and the fraction of byte-identical
   texts is reported. Saaras is not re-called for this (credits).
2. **LLM runs are interleaved.** Order is `for run in 1..3: for example: for
   condition in (gt, whisper, sarvam)`. Any time-of-day or model-backend drift
   then lands on every condition of an example alike, instead of on one
   condition.
3. Every LLM outcome is appended to a committed JSONL
   (`results/f1_runs/…`): example id, language, condition, run, outcome, the
   tool call returned, error class, model, UTC timestamp. The runner is
   **resumable** from it and never repeats a completed (example, condition,
   run).
4. Budget, measured 2026-11-14 from Groq's response headers: **1,000
   requests/day, 8,000 tokens/minute** on the free tier. One replicate
   (275 × 3 conditions) is 825 calls, so the full design takes roughly three
   days of quota. The runner throttles to the rate-limit headers; retries
   count against quota. No paid tier is used.

### 10.4 What counts as a failure — and what must not

- A model/response that is wrong, malformed, or rejected by Groq as an invalid
  tool call (HTTP 400, the Phase 2 documented behaviour) is a **task failure**,
  as in Phase 2.
- **Infrastructure errors are never scored.** HTTP 429, 5xx, timeouts and
  connection errors are retried with backoff (at most 6 tries); if still
  failing, that (example, condition, run) is marked `incomplete` and retried
  on the next invocation. The existing F1 harness counts *every* exception as a
  failure; that would turn a rate limit into fake ASR loss, so it is not used
  here. Any `incomplete` cell left at the end is reported and blocks the
  headline claim for its arm.

### 10.5 Statistics (all computed from the committed JSONL)

Per language, per ASR arm, with `n` examples:

- **A/A noise floor.** For each pair of runs of the **same** condition (1v2,
  1v3, 2v3): the difference in success rate (percentage points) and the
  fraction of examples whose outcome differs. Reported for `gt` and for each
  real-ASR condition. **Noise floor = the largest absolute success-rate
  difference among the three `gt` pairs.** (Three pairs is a coarse estimate;
  stated, not hidden.)
- **ASR loss.** Per example, `d_i = mean over runs(gt) − mean over runs(real)`.
  Reported as the mean of `d_i` (pp) with a **paired bootstrap 95% CI**
  (percentile method, 10,000 resamples of examples, seed 0).
- **McNemar.** Per-example outcome = **majority of the 3 runs** (3 is odd, no
  ties). Exact two-sided McNemar p on the discordant pairs `gt`-pass/`real`-fail
  vs `gt`-fail/`real`-pass, via the shared `mcnemar_exact_p`.
- Pooled (both languages) numbers are secondary; the per-language results
  are the claims.

### 10.6 Decision rule

"ASR costs task success" is claimed for a (language, ASR) arm **only if all
hold**: (a) the paired-bootstrap 95% CI of mean `d_i` excludes 0; (b) the
majority-vote McNemar p < 0.05; (c) the mean loss exceeds that language's
noise floor. Otherwise the arm is reported as **not distinguishable from LLM
sampling noise** — an outcome as reportable as the other. The old 27.5% /
10.0% / Sarvam loss rows are marked `superseded by:` this item either way,
and are not edited.

### 10.7 Predictions (recorded to check, not decision rules)

- **Noise floor:** at n ≈ 140 per language, `gt` run-to-run success-rate
  differences are at most 4 pp, with 5–12% of examples changing outcome
  between some pair of runs.
- **English / Whisper:** loss stays well outside the noise floor and passes
  §10.6 (full-set loss between 15 and 35 pp; the old 27.5 pp was n = 40).
- **Hindi / Whisper:** loss between 0 and 20 pp; **at least 40% likely** that it
  fails §10.6, i.e. that the old 10.0 pp Hindi loss was indistinguishable
  from noise.
- **Sarvam:** Hindi loss smaller than Whisper's Hindi loss.
- ASR determinism check: ≥ 95% of the 30 re-transcribed texts byte-identical.

### 10.8 Caveats that travel with every 3B-5 number

- VoiceAgentBench audio is **synthesized**; this remains a lower bound on the
  real-world ASR penalty, as in Phase 2.
- `single_tool` is restaurants / recipes / local search, not the civic domain
  of `dhvani-entity`; nothing here says anything about F2.
- k = 3 gives a coarse noise estimate; the CIs resample examples, not runs.
- One LLM, one provider; Groq's served model may drift across the ~3 days.
- The judge is exact-match on function name and normalized argument values;
  its own false negatives are common to every condition, not removed.

### 10.9 Deviations

1. **Multiple Groq API keys (2026-11-14).** The owner supplied three additional
   Groq keys (the owner's statement: from a friend). `run_f1_noise_floor.py`
   spreads LLM calls across them (`GROQ_API_KEYS`, per-key throttle, next key
   on a daily-quota 429). One request per key on 2026-11-14 showed 999 of 1,000
   daily requests remaining on each, i.e. separate quotas. It changes only
   which key signs a request: same model (`openai/gpt-oss-20b`), same
   parameters, same provider. Which key served a cell is not recorded in the
   run log. Keys are stored only in the gitignored `.env`.
2. **Batch API not used.** Groq's Batch API returned `403 not_available_for_plan`
   for this account (probe, 2026-11-14, nothing sent), so the protocol's
   synchronous interleaved order stands unchanged.

3. **Sarvam transcription needed a different key (2026-11-14).** The
   `SARVAM_API_KEY` in `.env` returned HTTP 402 (no credits); the owner supplied
   another, used for that phase only (passed in the environment, not stored). All
   275 Saaras transcripts were produced by it, once each.
4. **Groq's daily token limit, not its request limit, bounded the run.** Free-tier
   `gpt-oss-20b` allows 200,000 *tokens* per day per account, which the
   rate-limit headers (requests / minute-tokens) do not show. At ~250 tokens per
   call the design (~600,000 tokens) used the three supplied keys' whole
   allowance: all three were exhausted at 2,389 of 2,475 cells, and a
   mid-run stall was first misdiagnosed by me as a hung request (it was
   waiting out 429 retries). The owner supplied a fourth key (separate account);
   the last 86 cells (all Hindi run 3) were scored on that key alone, so Hindi
   run 3 was served by a different account from the rest. Keys are not recorded
   in the run log; the fourth is in the gitignored `.env`.
5. **Runner changes made while the run was in progress (2026-11-14).** (a) Groq
   reports its rejection of its own generated tool call as a bare mid-stream
   `APIError`; the first version did not catch it and the run crashed after 54
   rows, so it is now scored a failure, as §10.4 already specified
   (commit c9af892; 49 such cells in the final log, 2% of all cells). (b) The
   per-key call spacing was halved from 8 s to 4 s for throughput only. (c) The
   run was stopped several times (host memory-pressure kills, a
   mistaken stall diagnosis) and resumed from the run log each time; no cell was
   scored twice (2,475 unique of 2,475). (d) The determinism check's first
   attempt exited 1 for an unrecorded reason; the second completed.

None other yet. (Implementation note, not a deviation: the existing F1 transcript
log keys on `example_id` alone, and 133 VoiceAgentBench ids exist in both
languages, so the Phase 2/2B F1 logging path can overwrite one language's
transcript with the other's. 3B-5 qualifies every id as `language:id` and
keys its run log on language; the old F1 path is left as is.)
