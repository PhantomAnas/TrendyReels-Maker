from __future__ import annotations

import os
import random

import numpy as np
import pytest

from conftest import needs_ffmpeg
from trendyreels import background as bg
from trendyreels import ffmpeg as ff


def test_choose_file_modes(tmp_path):
    for n in ("b.mp4", "a.mp4", "c.MOV", "x.txt"):
        (tmp_path / n).write_bytes(b"")
    exts = bg.VIDEO_EXTENSIONS
    assert bg.choose_file("", 0, "random", exts) is None
    assert bg.choose_file(str(tmp_path / "nope"), 0, "random", exts) is None
    assert bg.choose_file(str(tmp_path / "a.mp4"), 3, "random", exts) == str(tmp_path / "a.mp4")
    seq = [os.path.basename(bg.choose_file(str(tmp_path), i, "sequential", exts)) for i in range(4)]
    assert seq == ["a.mp4", "b.mp4", "c.MOV", "a.mp4"]
    rnd = bg.choose_file(str(tmp_path), 0, "random", exts, random.Random(1))
    assert os.path.basename(rnd) in {"a.mp4", "b.mp4", "c.MOV"}
    assert bg.list_videos(str(tmp_path)) == [str(tmp_path / n) for n in ("a.mp4", "b.mp4", "c.MOV")]


def test_fit_filter_strings():
    assert bg.fit_filter("crop", 1080, 1920).startswith("scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920")
    blur = bg.fit_filter("blur", 1080, 1920)
    assert "boxblur" in blur and "overlay" in blur and blur.endswith("format=rgb24")


def test_gradient_frame_shape():
    f = bg.gradient_frame(64, 128, (22, 20, 36))
    assert f.shape == (128, 64, 3) and f.dtype == np.uint8
    assert f[0].mean() > f[-1].mean()             # lighter at the top


def test_frame_reader_without_footage():
    plan = bg.BackgroundPlan(None)
    with bg.FrameReader(plan, 32, 64, 10, 0.5) as r:
        frames = list(r)
    assert len(frames) == 5 and frames[0].shape == (64, 32, 3)
    frames[0][:] = 0                               # copies: mutating one does not affect the next
    assert frames[1].max() > 0


@needs_ffmpeg
def test_plan_background_offsets_and_loops(clip):
    short = bg.plan_background(clip, 10.0, True, random.Random(0))
    assert short.path == clip and short.loops >= 3 and short.start == 0.0
    assert short.src_width == 320 and short.has_audio
    fits = bg.plan_background(clip, 1.0, True, random.Random(0))
    assert fits.loops == 0 and 0.0 <= fits.start <= 2.0
    fixed = bg.plan_background(clip, 1.0, False)
    assert fixed.start == 0.0
    with pytest.raises(bg.BackgroundError):
        bg.plan_background(clip + ".missing.mp4", 1.0)


@needs_ffmpeg
def test_frame_reader_decodes_and_loops(clip):
    plan = bg.plan_background(clip, 7.0, False)
    with bg.FrameReader(plan, 90, 160, 10, 7.0, fit="crop") as r:
        frames = list(r)
    assert len(frames) == 70
    assert all(f.shape == (160, 90, 3) for f in frames)
    assert frames[0].std() > 5                     # real picture, not padding
    assert not np.array_equal(frames[0], frames[35])
    with bg.FrameReader(plan, 90, 160, 10, 1.0, fit="blur") as r:
        blurred = list(r)
    assert len(blurred) == 10 and blurred[0].std() > 5


@needs_ffmpeg
def test_grab_frame(clip):
    f = bg.grab_frame(clip, 1.0, 90, 160, "crop")
    assert f is not None and f.shape == (160, 90, 3)
    assert bg.grab_frame(clip, 1.0, 90, 160, "blur") is not None
    assert bg.grab_frame(clip + ".missing", 1.0, 90, 160) is None


@needs_ffmpeg
def test_probe_helpers(clip):
    d, w, h, audio = ff.video_info(clip)
    assert abs(d - 3.0) < 0.3 and (w, h) == (320, 180) and audio
    assert ff.media_duration(clip) == pytest.approx(d)
    assert ff.video_info(clip + ".missing") is None
    assert ff.ffmpeg_version().lower().startswith("ffmpeg")
    # the ffmpeg-only fallback parser agrees with ffprobe
    fb = ff._probe_with_ffmpeg(clip)
    assert fb and abs(float(fb["format"]["duration"]) - d) < 0.2
    assert any(s.get("codec_type") == "video" and s.get("width") == 320 for s in fb["streams"])
