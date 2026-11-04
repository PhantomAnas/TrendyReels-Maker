from __future__ import annotations

import os

from trendyreels import cli
from trendyreels import settings as settings_mod
from trendyreels.settings import ProjectSettings


def test_settings_roundtrip_and_defaults(tmp_path):
    s = ProjectSettings(voice="en-GB-RyanNeural", text_color=(1, 2, 3), speed=1.3)
    s.extra["elevenlabs_api_key"] = "k"
    s.save()
    assert os.path.exists(settings_mod.config_path())
    assert str(tmp_path) in settings_mod.config_path()      # tests never touch the real config
    loaded = ProjectSettings.load()
    assert loaded.voice == "en-GB-RyanNeural" and loaded.text_color == (1, 2, 3) and loaded.speed == 1.3
    assert loaded.extra["elevenlabs_api_key"] == "k"
    assert ProjectSettings.from_dict({"bogus": 1, "fps": 25, "highlight_color": [300, -5, "7"]}).highlight_color == (255, 0, 7)
    assert ProjectSettings.from_dict({"fps": "not an int"}).fps in (30, "not an int")
    assert ProjectSettings.load(str(tmp_path / "nope.json")).fps == 30


def test_validate_reports_problems(tmp_path):
    s = ProjectSettings(fps=0, speed=3, tts_provider="file", narration_file="x", font_path=str(tmp_path / "f.ttf"),
                        background=str(tmp_path / "none"), crf=99)
    problems = s.validate()
    assert len(problems) >= 6
    assert ProjectSettings().validate() == []
    assert ProjectSettings().even_size == (1080, 1920)
    assert ProjectSettings(width=181, height=321).even_size == (180, 320)


def test_cli_args_apply(tmp_path):
    p = cli.build_parser()
    a = p.parse_args(["--aspect", "16:9", "--provider", "silent", "--speed", "1.2", "--read-title", "no", "--captions", "off",
                      "--words", "2", "--background", str(tmp_path), "--fit", "blur", "--channel", "Me", "--no-skip",
                      "--title-card", "fixed", "--font-size", "0.09", "--out", str(tmp_path / "o")])
    s = cli.apply_args(ProjectSettings(), a)
    assert (s.width, s.height) == (1920, 1080) and s.tts_provider == "silent" and s.speed == 1.2
    assert s.read_title is False and s.captions is False and s.words_per_caption == 2
    assert s.background == str(tmp_path) and s.fit == "blur" and s.channel_name == "Me"
    assert s.skip_existing is False and s.title_card == "fixed" and s.font_size == 0.09
    assert cli.apply_args(ProjectSettings(), p.parse_args(["--size", "720x1280"])).height == 1280


def test_cli_story_sources(tmp_path):
    p = cli.build_parser()
    f = tmp_path / "s.txt"
    f.write_text("T\nbody", encoding="utf-8")
    st = cli.stories_from_args(ProjectSettings(), p.parse_args(["--text", str(f)]))
    assert st[0].title == "T" and st[0].body == "body"
    st = cli.stories_from_args(ProjectSettings(), p.parse_args(["--title", "X", "--text", "hello there"]))
    assert st[0].title == "X" and st[0].body == "hello there"
    a = p.parse_args(["--stories", str(f)])
    st = cli.stories_from_args(cli.apply_args(ProjectSettings(), a), a)
    assert len(st) == 1
    assert cli.stories_from_args(ProjectSettings(), p.parse_args([])) == []


def test_cli_errors_and_check(capsys):
    assert cli.main(["--no-saved-settings"]) == 2
    rc = cli.main(["--check"])
    out = capsys.readouterr().out.lower()
    assert ("ffmpeg" in out) and rc in (0, 1)
    assert cli.main(["--list-voices"]) == 0
    assert "Neural" in capsys.readouterr().out
