"""Word timings and caption grouping.

A `Word` is a caption token with the moment it is spoken.  Timings come from
the voice engine (Edge TTS word boundaries, ElevenLabs alignment), from
whisper, or from an estimate based on word length when nothing better exists.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, replace

from .text import normalize_token, split_words

SENTENCE_END = ".!?"
CLAUSE_END = ",;:"


class TimingError(Exception):
    pass


@dataclass(frozen=True)
class Word:
    text: str
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass(frozen=True)
class Caption:
    words: tuple[Word, ...]
    start: float
    end: float

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    def active_index(self, t: float) -> int:
        """Index of the word being spoken at t (the last one that has started)."""
        idx = 0
        for i, w in enumerate(self.words):
            if t >= w.start:
                idx = i
        return idx


# ---------------------------------------------------------------- estimates

def _weight(word: str) -> float:
    core = re.sub(r"[^\w]", "", word)
    w = 0.6 + 0.09 * max(1, len(core))
    if word and word[-1] in SENTENCE_END:
        w += 0.9
    elif word and word[-1] in CLAUSE_END:
        w += 0.35
    return w


def estimate_words(text: str, duration: float | None = None, wpm: float = 165.0, start: float = 0.0) -> list[Word]:
    """Spread the words of `text` over `duration` seconds (or over a duration
    derived from `wpm`) in proportion to their length and punctuation."""
    tokens = split_words(text)
    if not tokens:
        return []
    weights = [_weight(t) for t in tokens]
    total_w = sum(weights)
    if duration is None:
        duration = len(tokens) * 60.0 / max(30.0, wpm)
    duration = max(0.05 * len(tokens), float(duration))
    out: list[Word] = []
    t = start
    for tok, w in zip(tokens, weights):
        d = duration * w / total_w
        out.append(Word(tok, t, t + d))
        t += d
    return out


def estimated_duration(text: str, wpm: float = 165.0) -> float:
    return sum(w.duration for w in estimate_words(text, None, wpm))


# ------------------------------------------------------------- adjustments

def shift(words: list[Word], offset: float) -> list[Word]:
    return [replace(w, start=w.start + offset, end=w.end + offset) for w in words]


def scale(words: list[Word], factor: float) -> list[Word]:
    """Multiply all timings by `factor` (e.g. 1/speed after an atempo)."""
    return [replace(w, start=w.start * factor, end=w.end * factor) for w in words]


def fit_to_duration(words: list[Word], duration: float) -> list[Word]:
    """Stretch or squeeze timings (which start at 0) so the last word ends at `duration`."""
    if not words:
        return []
    last = max(w.end for w in words)
    if last <= 0:
        return estimate_words(" ".join(w.text for w in words), duration)
    return scale(words, duration / last)


def tidy(words: list[Word], min_duration: float = 0.04) -> list[Word]:
    """Monotonic, non-overlapping, each word at least `min_duration` long."""
    out: list[Word] = []
    t = 0.0
    for w in words:
        start = max(w.start, t)
        end = max(w.end, start + min_duration)
        out.append(Word(w.text, start, end))
        t = end
    return out


# ------------------------------------------------------- script alignment

def merge_script_timings(script_text: str, timed: list[Word]) -> list[Word]:
    """Give the script's own tokens (with punctuation and casing) the timings
    reported by the voice engine or whisper, whose tokens may differ a little.
    Matched tokens take their timing; the rest are interpolated between them."""
    tokens = split_words(script_text)
    if not tokens:
        return []
    if not timed:
        return estimate_words(script_text)
    a = [normalize_token(t) for t in tokens]
    b = [normalize_token(w.text) for w in timed]
    if a == b:
        return [Word(tok, w.start, w.end) for tok, w in zip(tokens, timed)]
    matched: dict[int, Word] = {}
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                matched[i1 + k] = timed[j1 + k]
        elif tag == "replace":
            # Same number of tokens that merely differ in spelling: pair them up.
            n = min(i2 - i1, j2 - j1)
            if n and (i2 - i1) == (j2 - j1):
                for k in range(n):
                    matched[i1 + k] = timed[j1 + k]
    if not matched:
        return fit_to_duration(estimate_words(script_text), max(w.end for w in timed))
    out: list[Word | None] = [None] * len(tokens)
    for i, w in matched.items():
        out[i] = Word(tokens[i], w.start, w.end)
    # Interpolate runs of unmatched tokens between their matched neighbours.
    i = 0
    first_start = min(w.start for w in matched.values())
    last_end = max(w.end for w in matched.values())
    while i < len(out):
        if out[i] is not None:
            i += 1
            continue
        j = i
        while j < len(out) and out[j] is None:
            j += 1
        left_end = out[i - 1].end if i > 0 else max(0.0, first_start - 0.3 * (j - i))  # type: ignore[union-attr]
        right_start = out[j].start if j < len(out) else last_end + 0.3 * (j - i)  # type: ignore[union-attr]
        span = max(0.05 * (j - i), right_start - left_end)
        est = estimate_words(" ".join(tokens[i:j]), span, start=left_end)
        for k, w in enumerate(est):
            out[i + k] = w
        i = j
    return tidy([w for w in out if w is not None])


# ---------------------------------------------------------------- grouping

def group_captions(words: list[Word], max_words: int = 3, max_chars: int = 22, gap_split: float = 0.7,
                   hold: float = 0.0) -> list[Caption]:
    """Chunk words into captions.  A new caption starts when the word count or
    character budget is reached, after sentence punctuation, or after a pause.
    Each caption stays on screen until the next one starts (plus `hold` for the
    last one)."""
    captions: list[Caption] = []
    group: list[Word] = []

    def flush() -> None:
        if group:
            captions.append(Caption(tuple(group), group[0].start, group[-1].end))
            group.clear()

    for w in words:
        if group:
            chars = len(" ".join(x.text for x in group)) + 1 + len(w.text)
            if len(group) >= max(1, max_words) or chars > max_chars and len(group) >= 1 and len(w.text) <= max_chars:
                flush()
            elif w.start - group[-1].end > gap_split:
                flush()
        group.append(w)
        if w.text and w.text[-1] in SENTENCE_END:
            flush()
    flush()
    # Extend each caption to the start of the next so the screen is never empty mid-sentence.
    out: list[Caption] = []
    for i, c in enumerate(captions):
        nxt = captions[i + 1].start if i + 1 < len(captions) else c.end + hold
        gap = nxt - c.end
        end = nxt if gap <= gap_split else c.end + min(gap_split, gap) * 0.5
        out.append(Caption(c.words, c.start, max(c.end, end)))
    return out


def caption_at(captions: list[Caption], t: float) -> Caption | None:
    for c in captions:
        if c.start <= t < c.end:
            return c
    return None


# ------------------------------------------------------------------ whisper

def whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def whisper_words(audio_path: str, model_size: str = "base", language: str | None = None, log=None) -> list[Word]:
    """Word timings from faster-whisper (optional dependency; models download on first use)."""
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:  # noqa: BLE001
        raise TimingError("faster-whisper is not installed: pip install faster-whisper") from exc
    if log:
        log(f"whisper: loading '{model_size}' model (downloads on first use)")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(audio_path, word_timestamps=True, language=language, vad_filter=False)
    out: list[Word] = []
    for seg in segments:
        for w in seg.words or []:
            text = (w.word or "").strip()
            if text:
                out.append(Word(text, float(w.start), float(w.end)))
    if log:
        log(f"whisper: {len(out)} words recognised")
    return tidy(out)
