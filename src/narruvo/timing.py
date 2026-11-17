"""Map model phoneme durations to source words without another AI model."""

import re
from difflib import SequenceMatcher
from typing import Protocol, Sequence

from narruvo.domain import SpeechCue


class PhonemeTiming(Protocol):
    phoneme: str
    start: float
    end: float


def estimated_cues(text: str, duration_ms: int) -> tuple[SpeechCue, ...]:
    words = list(re.finditer(r"\S+", text))
    weights = [max(1, len(word[0])) for word in words]
    total = sum(weights) or 1
    offset = 0
    cues = []
    for word, weight in zip(words, weights):
        start = round(duration_ms * offset / total)
        offset += weight
        cues.append(SpeechCue(start, round(duration_ms * offset / total), word.start(), word.end()))
    return tuple(cues)


def align_cues(
    text: str, timings: Sequence[PhonemeTiming], word_phonemes: Sequence[str], duration_ms: int,
) -> tuple[tuple[SpeechCue, ...], bool]:
    """Align isolated-word pronunciations to contextual, timed phonemes.

    Pronunciations can change in context ("the", numbers, contractions). A
    monotonic sequence alignment keeps those differences from shifting every
    following word. Only unmatched words need interpolated timings.
    """
    words = list(re.finditer(r"\S+", text))
    if not timings or len(word_phonemes) != len(words):
        return estimated_cues(text, duration_ms), True
    expected, owners = [], []
    for index, phonemes in enumerate(word_phonemes):
        if index:
            expected.append(" ")
            owners.append(None)
        value = phonemes.strip()
        expected.extend(value)
        owners.extend([index] * len(value))
    actual = "".join(timing.phoneme for timing in timings)
    actual_times = [timing for timing in timings for _ in timing.phoneme]
    anchors: list[list[int] | None] = [None] * len(words)
    matched = 0
    for a, b, size in SequenceMatcher(None, "".join(expected), actual, autojunk=False).get_matching_blocks():
        for offset in range(size):
            owner = owners[a + offset]
            if owner is None:
                continue
            matched += 1
            timing = actual_times[b + offset]
            start = max(0, min(duration_ms, round(timing.start * 1000)))
            end = max(start, min(duration_ms, round(timing.end * 1000)))
            if anchors[owner] is None:
                anchors[owner] = [start, end]
            else:
                anchors[owner][1] = end
    expected_count = sum(owner is not None for owner in owners)
    if not expected_count or matched < expected_count * 0.5:
        return estimated_cues(text, duration_ms), True
    interpolated = any(anchor is None for anchor in anchors)
    index = 0
    while index < len(anchors):
        if anchors[index] is not None:
            index += 1
            continue
        first = index
        while index < len(anchors) and anchors[index] is None:
            index += 1
        left = anchors[first - 1][1] if first else 0
        right = anchors[index][0] if index < len(anchors) else duration_ms
        weights = [max(1, len(word[0])) for word in words[first:index]]
        total, offset = sum(weights), 0
        for current, weight in zip(range(first, index), weights):
            start = left + round(max(0, right - left) * offset / total)
            offset += weight
            anchors[current] = [start, left + round(max(0, right - left) * offset / total)]
    result, previous_end = [], 0
    for word, anchor in zip(words, anchors):
        start = max(previous_end, anchor[0])
        end = max(start, anchor[1])
        result.append(SpeechCue(start, end, word.start(), word.end()))
        previous_end = end
    return tuple(result), interpolated
