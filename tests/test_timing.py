from __future__ import annotations

import pytest

from trendyreels.timing import (Caption, Word, caption_at, estimate_words, estimated_duration, fit_to_duration,
                                group_captions, merge_script_timings, scale, shift, tidy)


def test_estimate_fits_duration_and_is_monotonic():
    words = estimate_words("One two three. Four five, six seven!", duration=10.0)
    assert len(words) == 7
    assert words[0].start == 0.0
    assert words[-1].end == pytest.approx(10.0)
    for a, b in zip(words, words[1:]):
        assert b.start == pytest.approx(a.end)
    # sentence-ending words get extra time
    assert words[2].duration > words[1].duration


def test_estimate_without_duration_uses_wpm():
    words = estimate_words("a b c d e f g h i j", wpm=120)
    assert words[-1].end == pytest.approx(5.0, abs=0.01)
    assert estimated_duration("a b c d e f g h i j", wpm=120) == pytest.approx(5.0, abs=0.01)
    assert estimate_words("") == []


def test_shift_scale_fit_tidy():
    w = [Word("a", 0, 1), Word("b", 1, 2)]
    assert shift(w, 0.5)[0].start == 0.5
    assert scale(w, 2)[1].end == 4
    assert fit_to_duration(w, 4)[1].end == 4
    messy = [Word("a", 1.0, 0.5), Word("b", 0.8, 0.9)]
    t = tidy(messy)
    assert t[0].end > t[0].start and t[1].start >= t[0].end


def test_merge_exact_match_keeps_script_tokens():
    timed = [Word("hello", 0.1, 0.4), Word("world", 0.5, 0.9)]
    merged = merge_script_timings("Hello, world!", timed)
    assert [w.text for w in merged] == ["Hello,", "world!"]
    assert merged[1].start == 0.5


def test_merge_interpolates_unmatched_tokens():
    script = "I said hello to the whole wide world today"
    timed = [Word("I", 0.0, 0.2), Word("said", 0.2, 0.5), Word("hello", 0.5, 0.9),
             Word("too", 0.9, 1.0),  # mis-heard "to"
             Word("world", 2.0, 2.4), Word("today", 2.4, 2.9)]
    merged = merge_script_timings(script, timed)
    assert [w.text for w in merged] == script.split()
    assert merged[2].start == 0.5
    assert merged[7].start == 2.0 and merged[8].end == 2.9
    # the four unmatched words (to the whole wide) sit between hello and world, in order
    assert 0.9 <= merged[3].start < merged[4].start < merged[5].start < merged[6].start < merged[7].start
    for a, b in zip(merged, merged[1:]):
        assert b.start >= a.start


def test_merge_with_nothing_in_common_falls_back_to_estimate():
    merged = merge_script_timings("alpha beta gamma", [Word("x", 0, 1), Word("y", 1, 3)])
    assert len(merged) == 3
    assert merged[-1].end == pytest.approx(3.0)


def test_group_captions_rules():
    words = estimate_words("one two three four five. six seven eight nine ten eleven", duration=11)
    caps = group_captions(words, max_words=3, max_chars=40)
    texts = [c.text for c in caps]
    assert texts[0] == "one two three"
    assert texts[1] == "four five."          # sentence end flushes early
    assert texts[2] == "six seven eight"
    assert caps[0].end == pytest.approx(caps[1].start)   # held until the next caption


def test_group_captions_char_budget_and_gaps():
    words = [Word("supercalifragilistic", 0, 1), Word("short", 1, 1.5), Word("words", 1.5, 2.0),
             Word("after", 4.0, 4.5), Word("pause", 4.5, 5.0)]
    caps = group_captions(words, max_words=5, max_chars=12)
    assert [c.text for c in caps] == ["supercalifragilistic", "short words", "after pause"]
    # a long pause is not bridged entirely
    assert caps[1].end < caps[2].start


def test_caption_at_and_active_index():
    caps = group_captions(estimate_words("a b c d", 4.0), max_words=2)
    c = caption_at(caps, 0.5)
    assert c is not None and c.text == "a b"
    assert c.active_index(0.1) == 0
    assert c.active_index(1.5) == 1
    assert caption_at(caps, 99) is None
    assert Caption((Word("x", 0, 1),), 0, 1).text == "x"
