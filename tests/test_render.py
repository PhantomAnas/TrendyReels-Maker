from __future__ import annotations

import os
import threading

import numpy as np
import pytest

from conftest import needs_ffmpeg
from trendyreels import batch, ffmpeg as ff, render
from trendyreels.background import gradient_frame
from trendyreels.settings import ProjectSettings
from trendyreels.text import Story
from trendyreels.timing import Word

STORY = Story("A short title", "One two three four five six seven eight nine ten. Eleven twelve.")


def settings(**kw) -> ProjectSettings:
    base = dict(tts_provider="silent", width=180, height=320, fps=10, lead_in=0.2, tail=0.3, title_gap=0.1, skip_existing=False)
    base.update(kw)
    return ProjectSettings(**base)


def test_plan_preview_layout():
    plan = render.plan_preview(STORY, settings())
    assert plan.estimated and plan.audio == []
    assert plan.title_until > 0.2                       # card shown while the title is read
    assert plan.captions and plan.captions[0].start >= plan.title_until - 0.2
    assert plan.total > plan.captions[-1].end
    off = render.plan_preview(STORY, settings(title_card="off"))
    assert off.title_until == 0 and off.captions[0].text.startswith("A short")
    fixed = render.plan_preview(STORY, settings(title_card="fixed", title_card_seconds=1.5, read_title=False))
    assert fixed.title_until == 1.5 and fixed.captions[0].start >= 1.5
    none = render.plan_preview(STORY, settings(captions=False))
    assert none.captions == []


def test_frame_composer_draws_card_then_captions():
    plan = render.plan_preview(STORY, settings())
    comp = render.FrameComposer(plan)
    bg = gradient_frame(180, 320, (22, 20, 36))
    card = comp.frame_at(plan.title_until / 2, bg.copy())
    assert (card[int(320 * 0.42)] > 240).all(axis=1).any()       # white card pixels mid-height
    t = plan.captions[0].start + 0.3
    cap = comp.frame_at(t, bg.copy())
    assert not np.array_equal(cap, bg)
    assert np.array_equal(comp.frame_at(plan.total + 5, bg.copy()), bg)   # nothing after the end
    small = render.FrameComposer(plan, 90, 160)
    assert small.frame_at(t, gradient_frame(90, 160, (0, 0, 0))).shape == (160, 90, 3)


def test_mix_and_encoder_command_shapes():
    plan = render.plan_preview(STORY, settings())
    cmd = render.mix_command(plan, "mix.wav")
    assert "anullsrc" in " ".join(cmd) and cmd[-1] == "mix.wav"
    plan.audio = [render.AudioSegment("v.wav", 0.5),
                  render.AudioSegment("m.mp3", 0, 0.2, loop=True, fade_out=1.0, src_duration=plan.total / 3)]
    cmd = render.mix_command(plan, "mix.wav")
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "adelay=500|500" in graph and "amix=inputs=2" in graph and "afade=t=out" in graph
    assert "-stream_loop" not in cmd                          # looping happens in the filter graph
    assert f"aloop=loop=5:size={int(plan.total / 3 * 48000) + 48000}" in graph
    enc = render.encoder_command(plan, "mix.wav", "out.mp4")
    assert enc[enc.index("-i") + 1] == "pipe:0" and "mix.wav" in enc and enc[-1] == "out.mp4"
    assert enc.count("-i") == 2                               # only the frame pipe and the mixed wav


@needs_ffmpeg
def test_build_plan_with_silent_voice(tmp_path):
    s = settings()
    plan = render.build_plan(STORY, s, str(tmp_path / "work"))
    assert len(plan.audio) == 2 and plan.audio[0].offset == pytest.approx(0.2)
    assert plan.audio[1].offset > plan.audio[0].offset
    assert plan.words and plan.captions
    assert plan.total == pytest.approx(plan.audio[1].offset + ff.media_duration(plan.audio[1].path) + 0.3, abs=0.05)
    with pytest.raises(render.RenderError):
        render.build_plan(Story("", "   "), s, str(tmp_path / "w2"))


@needs_ffmpeg
def test_timings_prefer_provider_then_estimate(tmp_path):
    from trendyreels.tts import Narration
    s = settings(caption_timing="auto")
    n = Narration(str(tmp_path / "x.wav"), 2.0, [Word("hello", 0.0, 0.5), Word("world", 0.6, 1.0)])
    words = render._timings_for(n, "Hello world!", s)
    assert [w.text for w in words] == ["Hello", "world!"] and words[1].start == 0.6
    n2 = Narration(str(tmp_path / "x.wav"), 2.0, None)
    est = render._timings_for(n2, "Hello world!", settings(caption_timing="estimate"))
    assert est[-1].end == pytest.approx(2.0)


@needs_ffmpeg
def test_render_without_footage(tmp_path):
    s = settings()
    plan = render.build_plan(STORY, s, str(tmp_path / "work"))
    out = str(tmp_path / "out" / "short.mp4")
    seen = []
    render.render(plan, out, progress=lambda d, t: seen.append((d, t)))
    info = ff.video_info(out)
    assert info and abs(info[0] - plan.total) < 0.25 and info[1:3] == (180, 320) and info[3]
    assert seen[-1][0] == seen[-1][1] == int(round(plan.total * 10))


@needs_ffmpeg
def test_render_with_footage_music_and_cancel(tmp_path, clip, clips_folder):
    music = str(tmp_path / "music.wav")
    ff.make_silence(music, 1.0)
    s = settings(background=clips_folder, background_pick="sequential", background_audio_volume=0.5,
                 music_path=music, music_volume=0.3, fit="blur")
    plan = render.build_plan(STORY, s, str(tmp_path / "work"), index=0)
    assert plan.background.path.endswith("a.mp4") and plan.background.loops >= 1
    assert len(plan.audio) == 4                       # title, body, footage sound, music
    assert all(seg.src_duration > 0 for seg in plan.audio[2:]) and plan.audio[3].loop
    out = str(tmp_path / "out.mp4")
    render.render(plan, out)
    assert ff.video_info(out)[3]
    # cancellation leaves no output behind
    cancel = threading.Event()
    calls = []

    def progress(done, total):
        calls.append(done)
        if done > 5:
            cancel.set()

    with pytest.raises(render.RenderCancelled):
        render.render(plan, str(tmp_path / "cancelled.mp4"), progress=progress, cancelled=cancel.is_set)
    assert not os.path.exists(str(tmp_path / "cancelled.mp4"))
    assert not [n for n in os.listdir(tmp_path) if n.endswith(".part.mp4")]


@needs_ffmpeg
def test_batch_skips_existing_and_continues_after_errors(tmp_path):
    s = settings(output_folder=str(tmp_path / "out"), skip_existing=True)
    stories = [STORY, Story("Second one", "Just a few words here."), Story("", "")]
    stages = []
    outs = batch.run_job(stories, s, stage=stages.append)
    assert len(outs) == 2 and all(os.path.exists(p) for p in outs)
    assert os.path.basename(outs[0]) == "A short title.mp4"
    mtime = os.path.getmtime(outs[0])
    outs2 = batch.run_job(stories[:1], s)
    assert outs2 == outs[:1] and os.path.getmtime(outs[0]) == mtime      # skipped, not re-rendered
    # a bad background for one story: the batch raises only if nothing rendered
    bad = settings(output_folder=str(tmp_path / "out2"), background=str(tmp_path / "missing.mp4"))
    with pytest.raises(render.RenderError):
        batch.run_job(stories[:1], bad, log=print)
    with pytest.raises(render.RenderError):
        batch.run_job([], s)


def test_output_path_dedup(tmp_path):
    s = settings(output_folder=str(tmp_path))
    taken: set[str] = set()
    a = batch.output_path(Story("Same", "x"), s, 0, taken)
    b = batch.output_path(Story("Same", "y"), s, 1, taken)
    assert a.endswith("Same.mp4") and b.endswith("Same (2).mp4")
    assert batch.output_path(Story("", ""), s, 4).endswith("story 5.mp4")
