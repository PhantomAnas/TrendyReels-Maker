from __future__ import annotations

import os

import pytest

from conftest import needs_ffmpeg
from trendyreels import tts
from trendyreels.settings import ProjectSettings


def test_edge_rate_formatting():
    assert tts.edge_rate(1.0) == "+0%"
    assert tts.edge_rate(1.25) == "+25%"
    assert tts.edge_rate(0.8) == "-20%"


def test_words_from_alignment():
    alignment = {
        "characters": list("hi there!"),
        "character_start_times_seconds": [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
        "character_end_times_seconds": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
    }
    words = tts.words_from_alignment(alignment)
    assert [w.text for w in words] == ["hi", "there!"]
    assert words[0].start == 0.0 and words[0].end == pytest.approx(0.2)
    assert words[1].start == pytest.approx(0.3) and words[1].end == pytest.approx(0.9)
    assert tts.words_from_alignment({}) == []


def test_api_key_sources(monkeypatch):
    s = ProjectSettings()
    assert tts.elevenlabs_api_key(s) == ""
    s.extra["elevenlabs_api_key"] = " abc "
    assert tts.elevenlabs_api_key(s) == "abc"
    monkeypatch.setenv("ELEVENLABS_API_KEY", "env-key")
    assert tts.elevenlabs_api_key(s) == "env-key"


def test_elevenlabs_without_key_raises(tmp_path):
    with pytest.raises(tts.TTSError):
        tts.synthesize_elevenlabs("hi", "voice", "", "model", 1.0, str(tmp_path / "x.wav"))


@needs_ffmpeg
def test_silent_provider_makes_audio_and_estimates(tmp_path):
    s = ProjectSettings(tts_provider="silent", speed=2.0)
    n = tts.synthesize("one two three four five six", s, str(tmp_path / "v.wav"))
    assert os.path.getsize(n.audio_path) > 1000
    assert n.words and len(n.words) == 6
    assert n.words[-1].end == pytest.approx(n.duration, abs=0.05)
    slow = tts.synthesize("one two three four five six", ProjectSettings(tts_provider="silent", speed=1.0), str(tmp_path / "w.wav"))
    assert slow.duration > n.duration * 1.8


@needs_ffmpeg
def test_file_provider_and_speed(tmp_path):
    src = str(tmp_path / "src.wav")
    from trendyreels import ffmpeg as ff
    ff.make_silence(src, 2.0)
    n = tts.narration_from_file(src, 1.0, str(tmp_path / "a.wav"))
    assert n.words is None and n.duration == pytest.approx(2.0, abs=0.1)
    fast = tts.narration_from_file(src, 2.0, str(tmp_path / "b.wav"))
    assert fast.duration == pytest.approx(1.0, abs=0.1)
    with pytest.raises(tts.TTSError):
        tts.narration_from_file(str(tmp_path / "missing.mp3"), 1.0, str(tmp_path / "c.wav"))


def test_unknown_provider(tmp_path):
    with pytest.raises(tts.TTSError):
        tts.synthesize("x", ProjectSettings(tts_provider="nope"), str(tmp_path / "x.wav"))


@pytest.mark.skipif(not os.environ.get("TRENDYREELS_NETWORK_TESTS"), reason="set TRENDYREELS_NETWORK_TESTS=1 to call Edge TTS")
@needs_ffmpeg
def test_edge_tts_live(tmp_path):
    n = tts.synthesize_edge("Hello there, this is a test.", "en-US-ChristopherNeural", 1.1, str(tmp_path / "e.wav"))
    assert n.duration > 1.0 and n.words and len(n.words) == 6
    voices = tts.list_edge_voices(refresh=True)
    assert any(v[0] == "en-US-ChristopherNeural" for v in voices)
