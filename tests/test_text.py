from __future__ import annotations

import os

from trendyreels.text import (clean_text, expand_abbreviations, first_sentence, load_stories, normalize_token, parse_stories,
                              prepare_speech, safe_filename, split_words)


def test_abbreviations_expand_whole_words_only():
    assert expand_abbreviations("AITA for leaving? My GF says NTA.") == "Am I the a-hole for leaving? My girlfriend says not the a-hole."
    # lower-case prose is untouched, and letters inside words are untouched
    assert expand_abbreviations("so I went to the shop") == "so I went to the shop"
    assert expand_abbreviations("TOPIC") == "TOPIC"
    assert expand_abbreviations("TL;DR it worked") == "too long, didn't read it worked"


def test_clean_text_joins_paragraphs_and_drops_junk():
    raw = "First para\nstill first\n\n\nSecond **bold** para http://x.y/z\n\n*third*"
    assert clean_text(raw) == "First para still first. Second bold para. third."
    assert clean_text("Done!") == "Done!"
    assert clean_text("") == ""


def test_prepare_speech_can_skip_expansion():
    assert prepare_speech("AITA?", expand=False) == "AITA?"
    assert prepare_speech("AITA?") == "Am I the a-hole?"


def test_split_and_normalize():
    assert split_words("Hello,  world! it's  me") == ["Hello,", "world!", "it's", "me"]
    assert normalize_token("It's!") == "its"
    assert normalize_token("Café") == "cafe"


def test_parse_legacy_batch_lines():
    text = "First title -- Once upon a time.\n\nSecond -- Another story here.\n"
    stories = parse_stories(text, "f")
    assert [s.title for s in stories] == ["First title", "Second"]
    assert stories[1].body == "Another story here."
    assert stories[0].source == "f"


def test_parse_title_then_body():
    stories = parse_stories("My title\nLine one.\nLine two.")
    assert len(stories) == 1
    assert stories[0].title == "My title"
    assert stories[0].body == "Line one.\nLine two."


def test_parse_separated_stories_and_single_block():
    text = "A\nbody a\n---\nB\nbody b\n===\nJust one block of text. With two sentences."
    stories = parse_stories(text)
    assert [s.title for s in stories] == ["A", "B", "Just one block of text."]
    assert stories[2].body.startswith("Just one block")


def test_first_sentence_truncates():
    assert first_sentence("Short one. Then more.") == "Short one."
    long = "word " * 40
    fs = first_sentence(long)
    assert fs.endswith("...") and len(fs) <= 95


def test_load_stories_file_and_folder(tmp_path):
    (tmp_path / "b.txt").write_text("T2 -- body two", encoding="utf-8")
    (tmp_path / "a.txt").write_text("﻿T1\nbody one", encoding="utf-8")
    (tmp_path / "skip.jpg").write_bytes(b"x")
    stories = load_stories(str(tmp_path))
    assert [s.title for s in stories] == ["T1", "T2"]
    assert os.path.basename(stories[0].source) == "a.txt"
    assert load_stories(str(tmp_path / "b.txt"))[0].body == "body two"


def test_safe_filename():
    assert safe_filename("My neighbour's cat: a story?!") == "My neighbours cat a story"
    assert safe_filename("") == "story"
    assert safe_filename("   ...   ", fallback="x") == "x"
    long = "word " * 30
    assert len(safe_filename(long)) <= 60
    assert not safe_filename(long).endswith(" ")
