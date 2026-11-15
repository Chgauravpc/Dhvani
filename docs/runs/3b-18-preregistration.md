# 3B-18 preregistration — Saaras through an 8 kHz mu-law phone leg

**Written:** 2026-11-15, committed before any real-row phone-channel transcription.
**Plan:** `docs/specs/phase-4.md` §5.2 Q1, item 3B-18. Nothing below is edited after this
commit; a forced change becomes a numbered entry in §7.

## 1. Question

Does a phone codec alone hurt a strong Indic ASR on these utterances? The same 290 test-split
entity rows (65 Svarah, 225 IndicVoices Hindi), the same Saaras `saaras:v3` in `transcribe`
mode, clean vs `pstn`: 8 kHz narrowband plus G.711 mu-law, no packet loss, no jitter, sent as an
8 kHz mono WAV (`dhvani.eval.pstn.to_pstn`, 3 unit tests). The channel is **simulated** and the
audio is read speech; this is the channel half only, not real telephone speech (3B-21).

## 2. Pre-flight (`results/preflight_3b-18.json`; plan §3)

| Check | Result |
|---|---|
| Density | 44 Svarah and 179 Hindi digit strings (≥ 4 digits, 3B-17 normaliser) and 66 / 242 test entity mentions in these rows: 30–100 for Svarah digits (intervals reported), pass elsewhere |
| Baseline sanity | Saaras is a passing baseline in both corpora (3B-14, 3B-17); local Whisper is not used here |
| Cost, measured | 290 rows, 65.05 minutes of audio, **about Rs 32.5** at the plan's Rs 30/hour (plan: about 33) |
| Machine fit | string/array processing only; peak memory not a concern |
| API reality | an 8 kHz WAV of a `pstn` row is accepted (HTTP 200, `language_code`, `transcript`, `request_id`). The response does **not** echo a model string, so `saaras:v3` is pinned by the request, not verified from the response. The first key in `.env` returned HTTP 402 (no credit); the run uses the key the owner supplied later, passed in the environment and never stored |

**Stop rule (plan §4):** the SDK has no balance call, so the dashboard balance cannot be read by
the agent. The owner reads it before and after; if the drop exceeds Rs 40 the rate assumption is
wrong and nothing further is spent. The run touches exactly these 290 rows, once each, and stops
at the first HTTP 402; a partial run is recorded as `[!] blocked: credits`, not thinned or
extrapolated.

## 3. Measures (per corpus, clean vs `pstn`, paired by unit; Saaras only)

- **Digit-string exact match** (3B-17 rule: maximal run of ≥ 4 digits in the normalised
  reference, exact equality).
- **Recognition error** on the entity mentions (3B-2 scoring: any curated spelling in any script),
  raw ASR output.
- **WER**, raw and number-normalised (3B-17), over the 290 rows.
- Paired exact McNemar on units/mentions; Wilson 95% intervals. **"Degrades" means an absolute
  drop of at least 5 points and exact McNemar p < 0.05 against clean.**
- Clean transcripts are the committed ones from 3B-4 (same rows, same model); nothing is
  re-transcribed clean.

## 4. Predictions (recorded so they can be wrong)

The plan's recorded expectation, from the literature (§2.1): **little or no degradation.**
Specifically: digit-string exact match drops by under 5 points in both corpora; entity
recognition error rises by under 5 points; normalised WER rises by under 3 points.

## 5. Outcomes, written first

| Observation | README sentence |
|---|---|
| neither digits nor entities degrade | "A phone codec alone does not hurt a strong Indic ASR on these utterances." |
| digits degrade, entities hold | "The phone channel costs *X* points of digit-string accuracy and leaves entities intact." |
| entities degrade | "The phone channel costs *X* points of entity recognition." Next: the 3B-15 three-way table on the new transcripts (free) |

## 6. Caveats that travel with every number

Simulated codec (not a network), read speech, clean-to-`pstn` is one codec setting; clustered
samples make the intervals and McNemar tests optimistic; Saaras may have trained on IndicVoices
`train`; one draw per clip, and ASR non-determinism (found in local Whisper, not checked for
Saaras) is in no interval; Svarah's 44 digit strings give wide intervals.

## 7. Deviations

None yet.
