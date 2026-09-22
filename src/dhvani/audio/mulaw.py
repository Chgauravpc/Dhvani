"""G.711 mu-law codec, hand-rolled and dependency-free.

Python 3.13 removed `audioop` (PEP 594), which is where `lin2ulaw` and
`ulaw2lin` used to live. The `audioop-lts` backport exists, but mu-law is a
table lookup and this conversion sits on the hot path of every single frame
Twilio sends or receives -- 50 frames per second per call -- so it is worth
owning outright rather than taking a dependency for it.

Encoding is 16-bit signed linear PCM to 8-bit mu-law, per ITU-T G.711. The
transform is lossy and deliberately so: it spends its 8 bits logarithmically,
giving quiet speech finer resolution than loud speech.
"""

from __future__ import annotations

from array import array

_BIAS = 0x84  # 132; added before encoding, removed after decoding
_CLIP = 32635  # max magnitude representable once _BIAS is added

# Segment (exponent) for each of the 256 possible values of (sample >> 7).
# G.711 publishes this as a literal 256-entry table; it is exactly
# floor(log2(i)), so it is computed here rather than transcribed -- a
# transcribed table is 256 chances to make a typo that only shows up as
# quiet distortion.
_EXP_LUT = [0] + [i.bit_length() - 1 for i in range(1, 256)]


def _encode_sample(sample: int) -> int:
    """Encode one 16-bit signed sample to one mu-law byte."""
    sign = 0x80 if sample < 0 else 0x00
    if sign:
        sample = -sample
    if sample > _CLIP:
        sample = _CLIP
    sample += _BIAS
    exponent = _EXP_LUT[(sample >> 7) & 0xFF]
    mantissa = (sample >> (exponent + 3)) & 0x0F
    return ~(sign | (exponent << 4) | mantissa) & 0xFF


def _decode_byte(value: int) -> int:
    """Decode one mu-law byte to one 16-bit signed sample."""
    value = ~value & 0xFF
    magnitude = ((value & 0x0F) << 3) + _BIAS
    magnitude <<= (value & 0x70) >> 4
    return _BIAS - magnitude if value & 0x80 else magnitude - _BIAS


# Built once at import. The encode table is 64K entries indexed by the
# unsigned reading of an int16, so encoding is a lookup rather than the
# branch-and-shift dance above.
_ENCODE_TABLE = bytes(
    _encode_sample(value - 0x10000 if value >= 0x8000 else value) for value in range(0x10000)
)
_DECODE_TABLE = array("h", (_decode_byte(value) for value in range(0x100)))

_BIG_ENDIAN = array("h", [1]).tobytes()[0] == 0
"""True on big-endian hosts, where `array.tobytes` emits the wrong byte order."""


def encode(pcm: bytes) -> bytes:
    """16-bit signed little-endian PCM to mu-law. One output byte per sample.

    Raises ValueError if `pcm` is not an even number of bytes, since a
    trailing half-sample means the caller has split a frame incorrectly.
    """
    if len(pcm) % 2:
        raise ValueError(f"pcm must be a whole number of int16 samples, got {len(pcm)} bytes")
    samples = array("h")
    samples.frombytes(pcm)
    if _BIG_ENDIAN:
        samples.byteswap()
    table = _ENCODE_TABLE
    return bytes(table[sample & 0xFFFF] for sample in samples)


def decode(ulaw: bytes) -> bytes:
    """mu-law to 16-bit signed little-endian PCM. Two output bytes per byte in."""
    table = _DECODE_TABLE
    samples = array("h", (table[byte] for byte in ulaw))
    if _BIG_ENDIAN:
        samples.byteswap()
    return samples.tobytes()
