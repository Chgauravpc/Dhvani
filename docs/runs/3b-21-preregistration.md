# 3B-21 preregistration — real telephone Hindi

**Written:** 2026-11-15, committed before any transcription of the sample. **Plan:**
`docs/specs/phase-4.md` §5.2 Q1, item 3B-21. Nothing below is edited after this commit; a forced
change becomes a numbered entry in §8.

## 1. Question

What does the same ASR do on **real** telephone Hindi, compared with the clean read Hindi it was
measured on in 3B-4/3B-17? This half is **not paired** with the channel half: a different corpus,
with dialect and spontaneity confounded, and it is never presented as a channel effect.

## 2. Data, and two deviations from the plan's wording

- **Source:** OpenSLR 118, `GV_Dev_5h.tar.gz`, the labelled dev split of the Gram Vaani Hindi ASR
  challenge (1,885 utterances, MP3, telephone-quality, mixed rates). The plan said "the Vistaar
  benchmark's copy"; Vistaar's repository gives no benchmark download link, so the original
  OpenSLR release is used. **Deviation A.**
- **Licence:** free "for academic purposes"; commercial use needs permission
  (`openslr.org/118`). This is a research evaluation; the transcripts (Gram Vaani's) are **not**
  committed: only utterance ids, durations and rates (`results/gramvaani_sample.json`), the
  hypotheses, and scores. The references are re-read from the archive. **Deviation B** from the
  repo's practice of committing transcripts with the ground truth.
- **Eligible:** non-empty reference with no `<...>` tag (`<inaudible>`: 141 excluded), duration 1.0 to
  29.5 s: 1,743 of 1,885. **Sample:** seed-0 shuffle, taken in order until the next utterance would
  pass 35 minutes: **221 utterances, 34.96 minutes, 5,602 reference words**; 132 were recorded at
  8 kHz, 80 at 44.1 kHz, 4 at 16 kHz, 5 at 48 kHz. Audio is decoded to 16 kHz mono and sent as WAV.

## 3. Pre-flight (`results/preflight_3b-21.json`; plan §3)

| Check | Result |
|---|---|
| Downloadable, licence, disk | 98 MB archive downloaded to its own folder; licence as above; fits on D: |
| Density (utterances) | 221 ≥ 100: pass |
| Density (digit strings) | **14 digit strings in 11 rows (< 30): fails**, so digit-string match is **not run** here; only WER |
| References usable | Devanagari, numbers spelled out; tagged utterances excluded |
| Cost | 34.96 minutes at Rs 30/hour is **about Rs 17.5** (plan: at most 17; the sample is not thinned to fit) |
| Groq audio | 2,098 s: fits the free tier |

**Spend gate (plan §4):** 3B-21 runs the Saaras arm only if at least Rs 23 remains after 3B-18
(its 17 plus 3B-9 and a margin). The agent cannot read the balance, so the **owner confirms it
before the Saaras call**. The Groq arm is free and runs regardless. A sample is never thinned;
if the balance does not fit, the Saaras arm is `[!] blocked: credits`.

## 4. Measures

WER (`dhvani.eval.wer.corpus_wer`), raw and number-normalised (3B-17 normaliser; references spell
numbers, Saaras writes digits), per ASR on the 221 utterances, with a 95% bootstrap interval over
utterances (10,000 resamples, seed 0). Compared with the same ASR's WER on the 464 clean
IndicVoices Hindi rows (3B-17: Saaras 26.4% raw / 12.6% normalised; Whisper `large-v3` 44.3% /
34.7%, which is labelled a broken baseline there). The codec's share is the 3B-18 Hindi change
(Saaras normalised WER +1.5 points, simulated).

## 5. Predictions (recorded so they can be wrong)

1. Saaras number-normalised WER on this sample is between 15% and 35%.
2. Whisper `large-v3` is worse than Saaras on the same sample.
3. The telephone-minus-clean normalised-WER gap for Saaras is more than the 3B-18 codec change (1.5
   points): the corpus, not the codec, accounts for most of it.

## 6. Outcomes, written first

| Observation (per ASR) | README sentence |
|---|---|
| normalised telephone WER at least 10 points above that ASR's normalised clean-row WER | "On real telephone Hindi the same ASR goes from *A*% to *B*% WER; the codec accounts for *C* of that." |
| within 5 points of it | "Real telephone Hindi costs this ASR little on this sample." |
| between 5 and 10 points above | the same sentence as the first row, with *A*, *B*, *C* and the word "moderately" |

## 7. Caveats that travel with every number

Not paired; different speakers, dialects, topics and recording conditions from IndicVoices;
spontaneous speech and dialect are confounded with the channel; the dev split of a challenge set
that Saaras or Whisper may have seen; one 35-minute sample; one draw per clip; the 44.1 kHz
files are telephone-collected audio stored at a high rate, not a different channel; digit
strings were too few to measure.

## 8. Deviations

Deviations A and B are stated in §2.

1. **(2026-11-15, during the Saaras run, before its remaining utterances were sent; 205 of 221 were already logged.)** Saaras answered HTTP 400 "Audio duration exceeds the maximum limit of 30 seconds" for utterance `01-04866-01` (container duration 29.38 s, so it passed the 29.5 s eligibility filter; the decoded audio is evidently longer). That is a rejected request, not a credit error and not a transcript. The run script now logs such an utterance as rejected (no text) and continues; any other provider error, including HTTP 402, still stops the run. **Scoring uses only the utterances every arm transcribed**, so the two ASRs are compared on the same set; the number excluded is reported. The sample itself is not changed.
