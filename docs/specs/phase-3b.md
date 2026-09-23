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

- [ ] **3B-1 GATE — reproduce the audit.** Word-boundary, deduplicated
      (example, entity) counting, shared by the gate script and the scorer
      (one function, not two copies that can drift). Longest-variant-wins so
      "aadhaar card" and "aadhaar" do not double count. Re-run the gate on
      both datasets. Commit the per-entity table as a results file.
      *Done when:* results file shows per-entity substring vs. word-boundary
      counts for both datasets, and the gate decision is restated from it.
      If Svarah < 100, follow the 30–100 rule literally (CI + lexicon
      expansion from what the data contains — ESIC/EPFO/CoWIN/UPI dominate).
- [ ] **3B-2 — two-rate scorer.** Recognition EER and canonicalization rate
      (section 3), both exact-match on curated variants, both paired with
      `corruption_rate`. Unit tests must include: Devanagari-correct output
      counted as recognized; "company" not counted as a PAN mention; a
      variant spelling counted as recognized but not canonical.
- [ ] **3B-3 — cache raw transcripts.** Every STT run writes
      `(dataset, split, example_id, stt, model, raw_text)` to a committed
      JSONL. Rescoring after a scorer fix must never need a re-transcription
      or Sarvam credits again. This is what made A1/A2 expensive to fix.
- [ ] **3B-4 — re-run F2 EER on both datasets × both ASRs** with 3B-1..3B-3,
      same dev/test protocol, threshold re-tuned on dev per STT. Old rows
      stay, marked superseded. **Preregister first** (commit before the
      run): what does it mean if recognition EER on LAHAJA is low for
      Saaras? (Answer to write down: the entity failure was a scoring
      artifact on LAHAJA; F2's value there is canonicalization, and the
      README says so.)
- [ ] **3B-5 — F1 noise floor.** Run the ground-truth condition twice
      (A/A). The GT-vs-GT delta *is* the noise floor; any ASR-vs-GT delta
      inside it is not a finding. Repeat each condition k≥3 times, report
      mean ± paired-bootstrap CI and a McNemar test on the paired
      per-example outcomes. Use the full `single_tool` set, not 40.
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
