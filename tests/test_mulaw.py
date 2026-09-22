"""G.711 mu-law codec -- phase-3 spec section 8: known vectors, round-trip
within quantization error, odd-length input raises."""

from __future__ import annotations

from array import array

import pytest

from dhvani.audio import mulaw


def _pcm(*samples: int) -> bytes:
    return array("h", samples).tobytes()


def test_linear_zero_encodes_to_0xff() -> None:
    assert mulaw.encode(_pcm(0)) == bytes([0xFF])


def test_0xff_decodes_to_linear_zero() -> None:
    decoded = mulaw.decode(bytes([0xFF]))
    assert array("h", decoded).tolist() == [0]


def test_round_trip_stays_within_quantization_error() -> None:
    # mu-law is lossy by design; a full-scale tone should still survive a
    # round trip within a few percent of full scale.
    samples = list(range(-32000, 32000, 137))
    pcm = _pcm(*samples)

    round_tripped = mulaw.decode(mulaw.encode(pcm))
    recovered = array("h", round_tripped).tolist()

    assert len(recovered) == len(samples)
    for original, back in zip(samples, recovered, strict=True):
        assert abs(original - back) <= 0.05 * 32768


def test_round_trip_preserves_sign() -> None:
    pcm = _pcm(1000, -1000, 20000, -20000)
    recovered = array("h", mulaw.decode(mulaw.encode(pcm))).tolist()
    for original, back in zip([1000, -1000, 20000, -20000], recovered, strict=True):
        assert (original > 0) == (back > 0)


def test_encode_odd_length_input_raises() -> None:
    with pytest.raises(ValueError, match="whole number of int16 samples"):
        mulaw.encode(b"\x01\x00\x02")


def test_encode_output_is_one_byte_per_sample() -> None:
    pcm = _pcm(1, 2, 3, 4, 5)
    assert len(mulaw.encode(pcm)) == 5


def test_decode_output_is_two_bytes_per_byte_in() -> None:
    ulaw = mulaw.encode(_pcm(1, 2, 3))
    assert len(mulaw.decode(ulaw)) == 6
