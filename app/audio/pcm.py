from __future__ import annotations

import math
import sys


INT16_MIN = -(2**15)
INT16_MAX = 2**15 - 1


def rms(fragment: bytes | bytearray | memoryview, sample_width: int) -> int:
    samples = _int16_samples(fragment, sample_width)
    if not samples:
        return 0
    total = sum(sample * sample for sample in samples)
    return int(math.sqrt(total / len(samples)))


def peak_abs(fragment: bytes | bytearray | memoryview, sample_width: int) -> int:
    samples = _int16_samples(fragment, sample_width)
    return max((abs(sample) for sample in samples), default=0)


def multiply(fragment: bytes | bytearray | memoryview, sample_width: int, factor: float) -> bytes:
    samples = _int16_samples(fragment, sample_width)
    output = bytearray(len(samples) * sample_width)
    offset = 0
    for sample in samples:
        amplified = int(sample * factor)
        clipped = max(INT16_MIN, min(INT16_MAX, amplified))
        output[offset : offset + sample_width] = clipped.to_bytes(sample_width, "little", signed=True)
        offset += sample_width
    return bytes(output)


def _int16_samples(fragment: bytes | bytearray | memoryview, sample_width: int) -> list[int]:
    if sample_width != 2:
        raise ValueError("only 16-bit PCM samples are supported")
    data = bytes(fragment)
    if len(data) % sample_width:
        raise ValueError("PCM fragment length must be aligned to sample width")
    if sys.byteorder == "little":
        return list(memoryview(data).cast("h"))
    return [int.from_bytes(data[index : index + 2], "little", signed=True) for index in range(0, len(data), 2)]
