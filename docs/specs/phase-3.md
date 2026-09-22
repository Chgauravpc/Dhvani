# Phase 3 — Twilio Reframe

**Status:** in progress — Phase 2B merged, its carry-overs run, audio
codec/resampler/channel simulator, Media Streams transport + mock server,
and the degradation sweep all built and tested. See section 2 and section
9 for the item-by-item status.
**Depends on:** Phase 2B (`worktree-phase-2b`, now fast-forward merged into
`main`)
**Blocks:** Phase 4 (ship)
**Window:** Sep 28 – Oct 9, 2026

---

## 1. Objective

Retarget the agent from browser audio (16 kHz, clean, wideband) to the audio
a phone call actually delivers (8 kHz, mu-law companded, lossy), and produce
a **degradation curve** — WER and latency as a function of impairment —
rather than a single clean-audio number.

This is the differentiator for a telephony company. It is also the honest
test: every number the project has published so far was measured on audio no
real caller will ever produce.

---

## 2. Carried over from Phase 2B — do these first

Phase 2B built all three workstreams and ran two. What it could not finish
lands here, and the first item is not optional.

### 2.1 Run the Sarvam baseline (Workstream A, built but never executed)

`SarvamSTT`, its unit tests and its integration test are written and green.
`SARVAM_API_KEY` was absent from the build environment, so **no real Sarvam
result exists.** The Indic ASR baseline — the thing `phase-2b.md` §9 said to
never cut — still has zero numbers behind it, and every Phase 2 F2 figure
remains contestable as fixing a problem the Whisper choice created.

- [x] Export `SARVAM_API_KEY` -- present in the local `.env`
- [x] Run the three re-runs in `phase-2b.md` §A.3 (Svarah EER, LAHAJA EER,
      F1 ablation) -- see `phase-2.md` §18 for the real numbers
- [x] Record whichever of §17's three preregistered outcomes occurred --
      Svarah lands closest to "Saaras helps but doesn't replace the
      corrector"; LAHAJA lands on "Saaras still misses them," identically
      to Whisper (both 100% `eer_before`) -- see `phase-2.md` §18

**This has been promoted in importance by what the model sweep found.** See
§3: Sarvam is hosted, so it may fix the accuracy question and the latency
problem in the same stroke. It is now the single highest-value unrun
experiment in the project.

### 2.2 Finish the LAHAJA model sweep

Killed partway by host memory pressure, not by a code fault. Re-run with
headroom:

```
uv run python scripts/run_model_sweep.py --dataset lahaja --n-examples 20 \
    --model-sizes tiny,small --compute-types int8,float32 --seed 0
```

**Re-attempted under Phase 3, killed a second time by the same host-level
memory-pressure safeguard** (this time it was the harness's own background-
shell reaper: the run was moved to the background after exceeding a
foreground timeout, then stopped because the machine was critically low on
memory while idle -- confirmed via `Get-Process`: the interpreter was
genuinely still computing, ~30 CPU-minutes in, not hung). No partial output
reached the point of printing a table before the kill, same as the first
attempt -- nothing to report from this run beyond "still blocked by the
same constraint." Per the reaper's own guidance, it is not re-run
automatically a third time; whoever has a machine with more headroom should
run the command above. This is the one item in section 2 that stays
undone, and it is being recorded honestly rather than worked around, the
same ethos `phase-2b.md` §11 applied to the (then-)missing Sarvam key.

### 2.3 Decide the live-demo operating point

The sweep stated a reasoned pick (`tiny`/`float32`) but deliberately did not
change `dhvani.live`'s shipped default (`small`/`int8`). That decision is
owed before the demo is recorded in Phase 4. Decide it, write down why, and
if Sarvam lands per 2.1 it may make the whole question moot.

**Decision, made from what §2.1 actually found (§2.2's re-run blocked, so
this is decided on the Svarah grid alone, same as the original sweep):**
Sarvam does **not** make this question moot -- it improves entity
handling (§18) but was never measured for latency in this pass (both F2
re-runs used it purely for its EER/WER numbers; no timing sweep was run
against it, and running one risks the same memory-pressure kill §2.2 just
hit twice).

**`dhvani.live`'s shipped default is changed to `tiny`/`float32`.** Not a
recommendation for someone else to apply later -- `src/dhvani/live.py`'s
`WHISPER_MODEL_SIZE`/`WHISPER_COMPUTE_TYPE` module constants (both still
overridable via `DHVANI_WHISPER_MODEL`/`DHVANI_WHISPER_COMPUTE_TYPE`) now
default to `tiny`/`float32`, and the module's own docstring records the
reasoning inline. `small`/`int8` measured p50=7.46s STT latency (phase-2b
§12), roughly **9x** Phase 0's 800ms end-to-end target from the STT stage
alone, before LLM/TTS latency is even added -- not viable for a live
conversation. `tiny`/`float32` (WER 27.9%, p50=1.55s) accepts a real
accuracy cost for latency a caller can actually sit through, which is the
honest tradeoff this phase's own measurements argue for.

**What was and wasn't re-verified.** `WhisperSTT("tiny", clock,
compute_type="float32")` was exercised repeatedly and successfully in this
phase's own real runs (the degradation sweep, §12 below, and the new
`test_degradation_integration.py`) -- constructing it, loading the model,
and transcribing real audio all work. What was **not** repeated is
phase-1 spec section 7's real-browser-and-microphone manual verification
of the full live WebRTC path end-to-end with this specific config; this
sandboxed environment has no browser or microphone, the same limitation
`dhvani.live`'s own module docstring already states. Whoever next runs
`dhvani.live` interactively is the first real check of this exact
default -- worth doing before Phase 4 records the demo from it, not
because the config is expected to fail, but because it hasn't been
watched succeed with a human on the other end yet.

---

## 3. What the model sweep changed about this phase

Phase 2B produced the most consequential number in the project so far:

| point | WER | STT p50 |
|---|---|---|
| `tiny` / `int8` | 33.7% | **1.16 s** |
| `tiny` / `float32` | 27.9% | **1.55 s** |
| `small` / `int8` (shipped default) | 14.6% | **7.46 s** |
| `small` / `float32` | 14.3% | **10.46 s** |

Phase 0's `LatencyBudget` allots **200 ms** to STT. The fastest point
measured is roughly 6x over it; the shipped default is roughly 37x over.

Three consequences for this phase:

1. **The "sub-800 ms p50" milestone is dead on real multi-second
   utterances**, and the README must say so rather than quietly dropping it.
   The 56% / 480 ms overlap figure is an *architecture* result measured
   under mock timings; it is not a claim about response time and must never
   be presented as one.
2. **Telephony makes this worse, not better.** Buffer-then-transcribe scales
   latency with utterance length, and phone callers speak in longer
   unbroken runs than browser testers do. A degradation sweep that reports
   only WER and hides a 7-second response time would be exactly the
   favourable reading this project has refused everywhere else.
3. **Hosted ASR is the plausible fix, and it is already built.** Sarvam runs
   on someone else's accelerator; a hosted call has a good chance of beating
   7.46 s CPU Whisper on both axes. That is why 2.1 moved to the front.

**Report latency alongside WER at every point of the degradation sweep.**
A curve with only accuracy on it would hide the bigger finding.

### 3.1 Where the sub-800ms milestone actually landed

Stated plainly, per section 9's definition of done: **it missed, and it
missed by a wide margin on real multi-second utterances.** Phase 1's
milestone ("first sub-800ms p50 conversation") was real and reproducible,
but it was measured with `MockSTT`/`MockLLM`/`MockTTS` on short scripted
turns, timing the *architecture* (overlapped stages, barge-in) rather than
a real ASR's wall-clock cost. Phase 2B's real model sweep (`phase-2b.md`
§12) put a number on the gap: real `faster-whisper` against real Svarah
audio measured **p50 STT latency of 1.16s at the fastest grid point**
(`tiny`/`int8`) and **7.46s at the shipped default** (`small`/`int8`) --
both already over the 800ms *end-to-end* target using only the STT stage,
before LLM or TTS latency is even added. The 56%/480ms overlap saving
`test_overlapped.py` gates in CI is real and still worth having, but it is
a saving *relative to sequential execution of the same slow stages*, not
a claim that the resulting total lands anywhere near 800ms -- it never
has, on real audio, and the milestone line in `ROADMAP.md`'s Phase 1
section should be read as "proved the architecture works," not "hit the
number," now that a real measurement exists.

Whether Sarvam changes this is exactly what `phase-2.md` §18 and the real
degradation sweep (once run) answer.

---

## 4. Scope

### In scope

- mu-law codec, resampler, telephony channel simulator
- Twilio Media Streams transport, and a protocol-faithful mock server
- The degradation sweep and its curve
- The Phase 2B carry-overs in §2

### Explicitly out of scope

- F3, F4, F5 — deferred past Nov 3 by the 21 Sep scope decision
- Streaming ASR. It is the real fix for §3 and it is a research project;
  the honest move here is to measure the problem and name it, not to solve
  it in a fortnight.
- A real Twilio account, a phone number, or any paid telephony
- Replacing the WebRTC transport. Media Streams is added alongside; the
  browser path stays working for the Phase 4 demo recording.
- Echo cancellation. Media Streams barge-in uses `clear`, which sidesteps it.

---

## 5. Ground rules

- **No new runtime dependency.** mu-law and resampling are hand-rolled
  (stdlib only); the transport uses `aiohttp`, already present for
  signaling. If something appears to need a new package, stop and flag it.
- `audioop` is **gone** from Python 3.13 (PEP 594). Do not reach for
  `audioop-lts`; the codec is a table lookup on the hot path of every 20 ms
  frame and is worth owning.
- **Verify the Media Streams message shapes against Twilio's published
  protocol before coding**, the way Phase 1 verified every provider API and
  Phase 2B verified the dataset loaders. Write what you find into §7.4.
- Sample-rate conversion happens at the transport boundary and nowhere else.
- Phase 0 protocols unchanged, again.

### Existing work to reuse

`worktree-twilio-reframe` (commit `2eeb5d7`) holds a first draft of
`audio/mulaw.py`, `audio/resample.py` and `audio/channel.py` — written
against this design, never reviewed, **no tests at all**. Treat it as a
starting point to read and test, not as code to trust. Rewrite anything
that does not survive scrutiny.

---

## 6. Repo layout additions

```
src/dhvani/
    audio/
        __init__.py
        mulaw.py              G.711 encode/decode, stdlib only
        resample.py           stateful linear resampler
        channel.py            TelephonyChannel, ChannelConfig, sweeps
    transport/
        mediastreams.py       Twilio Media Streams protocol + aiohttp binding
        mock_twilio.py        protocol-faithful mock server for tests
    eval/
        degradation.py        the sweep: WER and latency vs impairment
scripts/
    run_degradation_sweep.py
```

---

## 7. Design per module

### 7.1 `audio/mulaw.py`

```python
def encode(pcm: bytes) -> bytes:
    """16-bit signed little-endian PCM to mu-law, one byte per sample."""

def decode(ulaw: bytes) -> bytes:
    """mu-law to 16-bit signed little-endian PCM, two bytes per byte in."""
```

Precompute both tables at import. The G.711 segment table is exactly
`floor(log2(i))`, so compute it rather than transcribing 256 literals — a
transcribed table is 256 chances to introduce quiet distortion.

Known vector to pin in a test: linear `0` encodes to `0xFF`, and `0xFF`
decodes back to `0`.

### 7.2 `audio/resample.py`

```python
class Resampler:
    """Streaming linear resampler for 16-bit mono PCM, stateful across frames."""
    def __init__(self, src_rate_hz: int, dst_rate_hz: int) -> None: ...
    def process(self, pcm: bytes) -> bytes: ...
    def reset(self) -> None: ...
```

**Stateful on purpose.** A stateless converter restarts interpolation every
frame, and at 50 frames per second that discontinuity is an audible click on
every one. Carry the previous tail sample and the fractional read position.

Downsampling applies a box pre-filter of width `round(src/dst)` to suppress
aliasing. Linear interpolation is honest but not high-fidelity; say so in
the docstring rather than implying otherwise.

### 7.3 `audio/channel.py`

```python
class LossFill(StrEnum):
    SILENCE = "silence"   # preserves duration, keeps transcripts time-aligned
    DROP    = "drop"      # shortens the stream


@dataclass(frozen=True, slots=True)
class ChannelConfig:
    narrowband_hz: int = 8_000
    mulaw: bool = True
    packet_loss: float = 0.0
    loss_fill: LossFill = LossFill.SILENCE
    jitter_ms: float = 0.0
    delay_ms: float = 0.0
    seed: int = 0


class TelephonyChannel:
    def __init__(self, config: ChannelConfig, source_rate_hz: int, clock: Clock) -> None: ...
    def degrade(self, chunk: AudioChunk) -> AudioChunk | None: ...
    async def stream(self, audio: AsyncIterator[AudioChunk]) -> AsyncIterator[AudioChunk]: ...
    @property
    def stats(self) -> ChannelStats: ...
```

Order of operations, matching a real call: downsample, compand, lose
packets, then jitter and delay. Output returns to the source sample rate —
the damage is baked into the samples rather than left as a rate change for
callers to handle.

**Deterministic given `seed`.** That determinism is the entire argument for
simulating rather than renting a phone line: a real call gives one
uncontrolled sample, a seeded sweep gives the function.

`default_sweep()` returns configs mildest to worst, each step isolating one
cost: wideband baseline, then narrowband, then companding, then loss at 1%,
3%, 5%, then loss plus jitter.

### 7.4 `transport/mediastreams.py`

**Verified against Twilio's own published reference**
(https://www.twilio.com/docs/voice/media-streams/websocket-messages),
fetched and read directly rather than assumed from memory, per this
section's own ground rule and the same practice phase-1 and phase-2b used
for their own provider APIs. The real message shapes, quoted from that
page:

- A bidirectional WebSocket, opened by TwiML `<Connect><Stream>`.
- Inbound `connected`: `{"event": "connected", "protocol": "Call",
  "version": "1.0.0"}` -- the first message, before `start`.
- Inbound `start`: carries `streamSid`/`accountSid`/`callSid`, `tracks`
  (e.g. `["inbound"]`), `mediaFormat` (`{"encoding": "audio/x-mulaw",
  "sampleRate": 8000, "channels": 1}`), and `customParameters`.
- Inbound `media`: base64 `audio/x-mulaw` at 8000Hz, no file header --
  confirmed. Also carries `track`/`chunk`/`timestamp`, which the spec draft
  above didn't anticipate.
- Inbound `stop`: sent when the stream ends or the call ends; carries
  `accountSid`/`callSid`, no media.
- Inbound `dtmf`: not in the original draft above, but real and worth
  modeling since it's cheap to parse and ignore rather than crash on.
- Inbound `mark` -- **the one real surprise**: Twilio echoes a `mark`
  message *back* once that named chunk of audio finishes playing
  (bidirectional streaming only). The spec draft above only listed `mark`
  as something the server sends; it's bidirectional, and the echo is how
  "track outstanding marks to know what actually played" (below) is
  actually implemented -- there is no other signal for it.
- Outbound `media`/`mark` share their event names with the inbound shapes
  above but **drop the `track`/`chunk`/`timestamp` fields** -- confirmed
  by the same page's outbound examples. One parser has to handle both
  shapes (optional fields), not two.
- Outbound `clear`: `{"event": "clear", "streamSid": ...}` -- Twilio never
  sends this to a server; it only ever flows server-to-Twilio, to flush
  the platform's own playback buffer for barge-in.

No protocol surprise big enough to change the design in §5/§6; the
surprises above are field-level (mark is bidirectional; media/mark differ
by direction) and are handled inside `MediaMessage`/`parse_inbound` rather
than by splitting the message model further.

Split it the way `vad/endpointer.py` was split, for the same reason:

```python
# Pure, no I/O, fully unit-testable
def parse_inbound(raw: str) -> InboundMessage: ...
def media_message(stream_sid: str, pcm: bytes, src_rate_hz: int) -> str: ...
def mark_message(stream_sid: str, name: str) -> str: ...
def clear_message(stream_sid: str) -> str: ...

# Thin aiohttp binding over the above
class MediaStreamsTransport:
    def __init__(self, session: ConversationSession, clock: Clock) -> None: ...
    async def handle(self, ws: web.WebSocketResponse) -> None: ...
```

**`media_message` is deliberately one-shot** (a fresh `Resampler` per
call) -- fine for a single self-contained buffer, wrong for a live stream
of many small TTS chunks, which would reintroduce the exact frame-boundary
discontinuity `audio.resample.Resampler` exists to avoid. Found while
implementing: `MediaStreamsTransport`'s real outbound hot path does not
call `media_message` at all -- it holds one persistent `Resampler` across
a call's chunks instead, and `media_message` stays as the pure,
one-shot-testable reference for the outbound shape.

**Barge-in is `clear`, not local cancellation.** When the endpointer detects
speech during playback, send `clear` to flush Twilio's buffer and cancel the
in-flight turn. Track outstanding `mark` names to know what actually played
(using the inbound `mark` echo above). Implementing this needed one small
additive hook on `ConversationSession` -- an optional `on_barge_in`
callback, fired the instant a barge-in is detected, before
`OverlappedRunner` unwinds and raises `BargeInError` -- since the `clear`
has to go out immediately, not after the turn finishes cancelling. Default
`None`; the browser transport is unaffected.

### 7.5 `transport/mock_twilio.py`

A server that speaks the protocol well enough to test against with no Twilio
account: replays a WAV as `media` frames at 20 ms cadence, accepts outbound
frames, and records every `mark` and `clear` it receives so tests can assert
on them.

### 7.6 `eval/degradation.py`

```python
@dataclass(frozen=True, slots=True)
class DegradationPoint:
    label: str            # ChannelConfig.label
    wer: float
    stt_p50_ms: float
    stt_p90_ms: float
    frames_lost: int
    n_utterances: int


async def run_degradation_sweep(
    examples: Sequence[TranscriptExample],
    configs: Sequence[ChannelConfig],
    stt: STTProvider,
    clock: Clock,
) -> list[DegradationPoint]: ...
```

Reuse `eval/wer.py` from Phase 2B and the existing telemetry for latency.
Do not add a second timing mechanism.

**Both axes, every point.** Per §3, a curve showing only WER would hide the
larger finding.

---

## 8. Testing

**Unit (CI, fast, no network):**

| Test | Asserts |
|---|---|
| `test_mulaw.py` | known vectors (0 ↔ 0xFF); round-trip within quantization error; odd-length input raises |
| `test_resample.py` | 8k↔16k length ratios; no discontinuity across frame boundaries; `reset` clears state |
| `test_channel.py` | same seed gives byte-identical output; `packet_loss=0` drops nothing; `1.0` loses every frame; SILENCE preserves duration, DROP shortens |
| `test_mediastreams.py` | parse a real-shaped inbound `media` frame to PCM; serialize outbound `media`/`mark`/`clear`; round-trip through mu-law |
| `test_mediastreams.py` | barge-in emits `clear` and cancels the turn |
| `test_mock_twilio.py` | full loopback over a localhost WebSocket, no external service |

**Integration (opt-in):**

| Test | Asserts |
|---|---|
| `test_degradation_integration.py` | the degradation sweep against real Svarah audio and a real (`tiny`) `WhisperSTT`, bounded small given the host's memory constraints |
| `test_degradation_integration.py` | same, against real LAHAJA audio |

---

## 9. Definition of done

- [x] `uv run pytest -m "not integration"` green (195 passed) locally; **and**
      pushed to `origin/main` and watched via `gh run watch` -- run
      [35762078976](https://github.com/Chgauravpc/Dhvani/actions/runs/35762078976),
      all three jobs green: `Test (ubuntu-latest)` 17s, `Lint and
      type-check` 21s, `Test (windows-latest)` 37s. Genuinely observed,
      not assumed -- an earlier draft of this checklist marked this done
      before main had ever been pushed, which was wrong and was corrected.
- [x] `uv run mypy --strict src/dhvani` clean; `ruff check`/`ruff format
      --check` clean, across the whole package, not just the new files
- [ ] `src/dhvani/audio/` imports nothing outside the standard library --
      **not literally true**, and left unchecked rather than rationalized
      into a pass. `mulaw.py` and `resample.py` satisfy it exactly.
      `channel.py` imports `dhvani.clock.Clock` and `dhvani.types.AudioChunk`
      (both themselves stdlib-only, so no third-party runtime dependency is
      added -- that much matches §5's ground rule). But those two imports
      are real, are outside the standard library, and this bullet says what
      it says. Removing them would mean either duplicating `Clock`/
      `AudioChunk` inside `audio/` (worse: two definitions of the same
      concept drifting apart) or not having `TelephonyChannel` take a
      `Clock` at all (breaks the deterministic-under-`FakeClock` testing
      this whole project is built around). No change made; flagged as an
      unresolved spec/design tension for whoever owns this tradeoff, not
      quietly marked done.
- [x] Sarvam baseline (§2.1) **run**, with whichever preregistered outcome
      occurred written down -- `docs/specs/phase-2.md` §18
- [ ] LAHAJA sweep (§2.2) -- **blocked**, killed twice now by the host's
      own memory-pressure safeguard; not re-run a third time automatically,
      per that safeguard's own guidance. See §2.2.
- [x] Live-demo operating point (§2.3) decided and justified -- `dhvani.live`'s
      shipped default is changed in code to `tiny`/`float32` (was
      `small`/`int8`), not left as a recommendation. Decided from the
      already-real Svarah grid rather than blocked on §2.2, since §2.2's
      numbers wouldn't have changed the STT-latency argument, only added a
      second dataset's confirmation of it. The one thing not re-verified:
      a real-browser-and-microphone manual check of the live path with
      this exact config -- see §2.3's own note on that.
- [x] `eval/degradation.py` and `scripts/run_degradation_sweep.py` built,
      unit-tested, and run for real against Svarah audio (§12): both axes
      reported at every point. WER is noisy at this n (honestly flagged in
      §12); the latency finding (jitter alone costs more than the STT
      model choice) is real and robust. LAHAJA is not covered, same
      memory-pressure block as §2.2.
- [x] A recorded statement of where the sub-800 ms milestone actually
      landed, per §3.1 — stated as a miss, not quietly dropped

---

## 10. If the window slips — cut in this order

1. **Cut the mock Twilio server and the live Media Streams path.** The
   channel simulator alone produces the degradation curve, which is the
   result; the transport is what makes it a Twilio story.
2. **Cut jitter and delay** from the sweep, keeping narrowband, companding
   and loss. Those three carry most of the effect.
3. **Never cut §2.1.** The Sarvam run is one command once the key exists,
   and it is the highest-value unrun experiment in the project.

---

## 11. Open questions for review

1. **Does Sarvam fix the latency problem too?** §3 argues it plausibly does.
   If a hosted call lands near 500 ms against Whisper's 7.46 s, that is the
   headline result of the whole project and reframes Phase 4's README.
   Unknown until §2.1 runs.
2. **Which STT to run the degradation sweep against** — Whisper, for
   continuity with every prior number, or Sarvam, for relevance to a
   production stack. Proposal: Whisper first for comparability, and Sarvam
   as a second series if §2.1 lands early.
3. **Whether to attempt a local SIP path** (Asterisk plus a softphone) for
   the demo recording. Adds real RTP and jitter buffers at zero cost, but
   it is a day of setup and the mock server already proves the protocol.
   Default: no.

---

## 12. Real degradation sweep results

`uv run python scripts/run_degradation_sweep.py --dataset svarah --n-examples 20`,
`DHVANI_WHISPER_MODEL=tiny` (this run predates the §2.3 default change
below -- at the time this ran, `tiny` still had to be requested explicitly;
it is `dhvani.live`'s default as of §2.3). Chosen deliberately light either
way: the host has already killed the LAHAJA model sweep twice under memory
pressure (§2.2), and `tiny`'s footprint is small enough to run this safely
rather than risk a third kill on a heavier model. This is the real sweep
the unit tests (`test_degradation.py`) don't and can't cover -- they use a
synthetic draining STT precisely so they don't need a real model or real
audio; `test_degradation_integration.py` (new, opt-in) covers that gap
with a small real run against real Svarah and LAHAJA audio.

| config | wer | stt_p50_ms | stt_p90_ms | frames_lost | n |
|---|---|---|---|---|---|
| 16k (wideband baseline) | 33.7% | 1262.9 | 1877.6 | 0 | 20 |
| 8k (narrowband) | 36.4% | 1396.3 | 2264.1 | 0 | 20 |
| 8k-ulaw | 30.3% | 1260.6 | 2017.3 | 0 | 20 |
| 8k-ulaw-loss1% | 36.4% | 1315.0 | 1891.0 | 33 | 20 |
| 8k-ulaw-loss3% | 35.4% | 1288.5 | 2098.4 | 87 | 20 |
| 8k-ulaw-loss5% | 33.7% | 1282.6 | 2919.7 | 139 | 20 |
| 8k-ulaw-loss3%-jit40ms | 35.4% | **4802.3** | **11013.0** | 92 | 20 |

**Read honestly:**

- **The WER column is not a clean monotonic curve, and n=20 on `tiny` is
  why.** 8k-ulaw scoring *better* than the wideband baseline (30.3% vs.
  33.7%), and 5% loss scoring as well as no loss at all (33.7% vs. 33.7%),
  are both consistent with sampling noise on a 20-utterance sample, not
  evidence that companding or packet loss improve recognition. A larger
  `n` (the LAHAJA model sweep's own convention, and blocked here for the
  same memory reason) would be needed before reading anything into the
  WER ordering beyond "narrowband alone costs a few points, and nothing
  here contradicts that."
- **The latency column is the real, robust finding, and it needed no
  large `n` to show up.** Every impairment costs a little on latency
  (bandwidth-limiting and companding add tens of milliseconds), but
  jitter is categorically different: p50 jumps from ~1.3s to **4.8s**,
  and p90 to **11.0s**, the moment 40ms of per-frame jitter is added on
  top of 3% loss. This is not a WER effect at all -- it is real wall-clock
  delay from `TelephonyChannel.stream()`'s own per-frame jitter sleep,
  which serializes *in front of* STT's own (already slow, per §3.1)
  transcription time rather than overlapping with it. **Jitter alone can
  cost more end-to-end latency than the STT model choice does.** This is
  exactly the "telephony makes this worse, not better" argument §3
  predicted, now with a real number behind it rather than an argument
  from first principles.
- Open question 1 (does Sarvam fix the latency problem too?) **remains
  open** -- this sweep ran Whisper only, per open question 2's own
  proposal ("Whisper first for comparability"). §2.1's Sarvam runs
  measured EER/WER, not latency; no timing sweep was run against Sarvam
  in this pass, and running one carries the same memory-pressure risk
  §2.2 already hit twice. Left for whoever has more headroom.
