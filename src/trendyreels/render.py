"""From a story to a finished short.

`build_plan` does the slow, fallible parts (voice, timings, picking footage)
and returns a `Plan`; `FrameComposer` draws any moment of that plan onto a
background frame (the preview uses it too); `render` streams composed frames
into FFmpeg together with the voice, music and footage audio.
"""

from __future__ import annotations

import os
import random
import subprocess
import tempfile
import time
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from . import background as bgmod
from . import ffmpeg as ff
from .captions import CaptionStyle, paste_center, render_caption
from .settings import ProjectSettings
from .text import Story, prepare_speech
from .timing import (Caption, TimingError, Word, caption_at, estimate_words, estimated_duration, group_captions,
                     merge_script_timings, shift, whisper_available, whisper_words)
from .titlecard import card_duration_hint, render_title_card
from .tts import Narration, TTSError, synthesize


class RenderError(Exception):
    pass


class RenderCancelled(Exception):
    pass


@dataclass
class AudioSegment:
    path: str
    offset: float = 0.0         # seconds of delay before it starts
    volume: float = 1.0
    loop: bool = False          # repeat to fill the video (music, footage sound)
    seek: float = 0.0           # -ss into the file (footage sound follows the picture)
    fade_out: float = 0.0
    src_duration: float = 0.0   # length of the file, to make the loop count finite


@dataclass
class Plan:
    story: Story
    settings: ProjectSettings
    total: float
    captions: list[Caption]
    title_until: float
    background: bgmod.BackgroundPlan
    audio: list[AudioSegment] = field(default_factory=list)
    words: list[Word] = field(default_factory=list)
    estimated: bool = False     # timings are a guess (preview without a voice)


def story_rng(story: Story, index: int) -> random.Random:
    """Deterministic per story, so the preview shows the clip and offset the render will use."""
    return random.Random(f"{index}:{story.title}:{len(story.body)}")


def _timings_for(narr: Narration, text: str, s: ProjectSettings, log=None) -> list[Word]:
    mode = s.caption_timing
    if mode == "auto":
        if narr.words:
            return merge_script_timings(text, narr.words)
        mode = "whisper" if whisper_available() else "estimate"
    if mode == "whisper":
        try:
            recognised = whisper_words(narr.audio_path, s.whisper_model, log=log)
            if recognised:
                return merge_script_timings(text, recognised)
        except TimingError as exc:
            if log:
                log(f"whisper unavailable ({exc}); using estimated timings")
    return estimate_words(text, narr.duration)


def _caption_words(title_words: list[Word], body_words: list[Word], s: ProjectSettings) -> list[Word]:
    words = list(body_words)
    if s.title_card == "off":
        words = list(title_words) + words
    return words


def build_plan(story: Story, s: ProjectSettings, workdir: str, index: int = 0, log=None, cancelled=None) -> Plan:
    """Synthesize the voice, work out every timing and choose the footage."""
    rng = story_rng(story, index)
    title_text = prepare_speech(story.title, s.expand_abbreviations)
    body_text = prepare_speech(story.body, s.expand_abbreviations)
    if not body_text and not title_text:
        raise RenderError("the story is empty")
    os.makedirs(workdir, exist_ok=True)
    audio: list[AudioSegment] = []
    title_words: list[Word] = []
    body_words: list[Word] = []
    t = s.lead_in
    title_until = 0.0
    try:
        if s.tts_provider == "file":
            narr = synthesize(body_text, s, os.path.join(workdir, "voice.wav"), log)
            body_words = shift(_timings_for(narr, body_text or title_text, s, log), t)
            audio.append(AudioSegment(narr.audio_path, t, s.voice_volume))
            t += narr.duration
            if s.title_card != "off":
                title_until = s.title_card_seconds or card_duration_hint(story.title)
        else:
            if s.read_title and title_text:
                if cancelled and cancelled():
                    raise RenderCancelled()
                n1 = synthesize(title_text, s, os.path.join(workdir, "title.wav"), log)
                title_words = shift(_timings_for(n1, title_text, s, log), t)
                audio.append(AudioSegment(n1.audio_path, t, s.voice_volume))
                t += n1.duration + s.title_gap
                if s.title_card == "title":
                    title_until = t - s.title_gap * 0.5
            if s.title_card == "fixed" or (s.title_card == "title" and not (s.read_title and title_text)):
                title_until = s.title_card_seconds or card_duration_hint(story.title)
                if not (s.read_title and title_text):
                    t = max(t, title_until + 0.15)
            if body_text:
                if cancelled and cancelled():
                    raise RenderCancelled()
                n2 = synthesize(body_text, s, os.path.join(workdir, "body.wav"), log)
                body_words = shift(_timings_for(n2, body_text, s, log), t)
                audio.append(AudioSegment(n2.audio_path, t, s.voice_volume))
                t += n2.duration
    except TTSError as exc:
        raise RenderError(str(exc)) from exc
    except ff.FFmpegError as exc:
        raise RenderError(f"ffmpeg failed while preparing audio: {exc}") from exc
    total = round(t + s.tail, 3)
    captions = group_captions(_caption_words(title_words, body_words, s), s.words_per_caption,
                              s.max_chars_per_caption) if s.captions else []
    bg, extra_audio = _footage_and_music(s, index, total, rng)
    return Plan(story, s, total, captions, title_until, bg, audio + extra_audio, words=title_words + body_words)


def _footage_and_music(s: ProjectSettings, index: int, total: float, rng: random.Random):
    clip = bgmod.choose_file(s.background, index, s.background_pick, bgmod.VIDEO_EXTENSIONS, rng)
    try:
        bg = bgmod.plan_background(clip, total, s.random_start, rng)
    except bgmod.BackgroundError as exc:
        raise RenderError(str(exc)) from exc
    audio: list[AudioSegment] = []
    if bg.path and bg.has_audio and s.background_audio_volume > 0:
        audio.append(AudioSegment(bg.path, 0.0, s.background_audio_volume, loop=bool(bg.loops), seek=bg.start,
                                  fade_out=1.0, src_duration=bg.src_duration))
    music = bgmod.choose_file(s.music_path, index, "random", bgmod.AUDIO_EXTENSIONS, rng)
    if music and s.music_volume > 0:
        dur = ff.media_duration(music) or 0.0
        audio.append(AudioSegment(music, 0.0, s.music_volume, loop=dur < total, fade_out=1.5, src_duration=dur))
    return bg, audio


def plan_preview(story: Story, s: ProjectSettings, index: int = 0) -> Plan:
    """A plan with estimated timings and no audio, for the live preview."""
    rng = story_rng(story, index)
    title_text = prepare_speech(story.title, s.expand_abbreviations)
    body_text = prepare_speech(story.body, s.expand_abbreviations)
    speed = max(0.25, s.speed)
    t = s.lead_in
    title_words: list[Word] = []
    title_until = 0.0
    if s.tts_provider != "file" and s.read_title and title_text:
        d = estimated_duration(title_text) / speed
        title_words = estimate_words(title_text, d, start=t)
        t += d + s.title_gap
        if s.title_card == "title":
            title_until = t - s.title_gap * 0.5
    if s.title_card == "fixed" or (s.title_card == "title" and not (s.tts_provider != "file" and s.read_title and title_text)):
        if s.title_card != "off":
            title_until = s.title_card_seconds or card_duration_hint(story.title)
            if not (s.read_title and title_text) or s.tts_provider == "file":
                t = max(t, title_until + 0.15)
    d = estimated_duration(body_text) / speed
    body_words = estimate_words(body_text, d, start=t)
    t += d
    total = round(t + s.tail, 3)
    captions = group_captions(_caption_words(title_words, body_words, s), s.words_per_caption,
                              s.max_chars_per_caption) if s.captions else []
    clip = bgmod.choose_file(s.background, index, s.background_pick, bgmod.VIDEO_EXTENSIONS, rng)
    try:
        bg = bgmod.plan_background(clip, total, s.random_start, rng) if ff.find_ffmpeg() else bgmod.BackgroundPlan(clip)
    except bgmod.BackgroundError:
        bg = bgmod.BackgroundPlan(None)
    return Plan(story, s, total, captions, title_until, bg, [], title_words + body_words, estimated=True)


# ---------------------------------------------------------------- composing

def _ease_out(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


class FrameComposer:
    """Draws the title card and captions of a plan onto background frames."""

    POP_SECONDS = 0.12
    CARD_FADE = 0.25

    def __init__(self, plan: Plan, width: int | None = None, height: int | None = None) -> None:
        self.plan = plan
        s = plan.settings
        full_w, full_h = s.even_size
        self.width = width or full_w
        self.height = height or full_h
        self.scale = self.width / max(1, full_w)
        self.style = CaptionStyle.from_settings(s, full_w)
        if self.scale != 1.0:
            self.style = CaptionStyle(
                font_path=self.style.font_path, font_px=max(6, int(self.style.font_px * self.scale)),
                max_width=max(16, int(self.style.max_width * self.scale)), text_color=self.style.text_color,
                highlight=self.style.highlight, highlight_color=self.style.highlight_color,
                highlight_scale=self.style.highlight_scale, outline_color=self.style.outline_color,
                outline_px=max(1 if self.style.outline_px else 0, int(self.style.outline_px * self.scale)),
                shadow=self.style.shadow, box=self.style.box, box_color=self.style.box_color,
                box_opacity=self.style.box_opacity, uppercase=self.style.uppercase)
        self.card: Image.Image | None = None
        if plan.title_until > 0 and s.title_card != "off":
            self.card = render_title_card(plan.story.title.strip() or "Untitled", s.channel_name, full_w,
                                          s.font_path, scale=self.scale)
        self.caption_cy = int(self.height * s.caption_y)
        self.card_cy = int(self.height * 0.42)

    def frame_at(self, t: float, background: np.ndarray) -> np.ndarray:
        frame = background if background.flags.writeable else background.copy()
        p = self.plan
        if self.card is not None and 0 <= t < p.title_until:
            fade_in = _ease_out(t / self.CARD_FADE) if t < self.CARD_FADE else 1.0
            fade_out = _ease_out((p.title_until - t) / self.CARD_FADE) if p.title_until - t < self.CARD_FADE else 1.0
            alpha = min(fade_in, fade_out)
            card = self.card
            if alpha < 1.0:
                arr = np.asarray(card).copy()
                arr[:, :, 3] = (arr[:, :, 3] * alpha).astype(np.uint8)
                card = Image.fromarray(arr, "RGBA")
                pop = 0.92 + 0.08 * fade_in
                if pop < 1.0:
                    card = card.resize((max(1, int(card.width * pop)), max(1, int(card.height * pop))), Image.Resampling.BILINEAR)
            paste_center(frame, card, self.width // 2, self.card_cy)
        cap = caption_at(p.captions, t)
        if cap is not None:
            active = cap.active_index(t) if self.style.highlight else None
            img = render_caption(tuple(w.text for w in cap.words), active, self.style)
            age = t - cap.start
            if age < self.POP_SECONDS:
                k = 0.86 + 0.14 * _ease_out(age / self.POP_SECONDS)
                img = img.resize((max(1, int(img.width * k)), max(1, int(img.height * k))), Image.Resampling.BILINEAR)
            paste_center(frame, img, self.width // 2, self.caption_cy)
        return frame


# ------------------------------------------------------------------ encoding

def mix_command(plan: Plan, out_wav: str) -> list[str]:
    """Mix the voice, footage sound and music into one stereo wav of exactly
    `plan.total` seconds.  Done as its own FFmpeg run, with no pipes, because
    several audio inputs next to the piped video deadlock FFmpeg 7/8 now and
    then (the scheduler throttles the slow video input and never resumes)."""
    cmd = [ff.require_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y"]
    chains: list[str] = []
    for i, seg in enumerate(plan.audio):
        if seg.seek > 0:
            cmd += ["-ss", f"{seg.seek:.3f}"]
        cmd += ["-i", seg.path]
        chain = [f"[{i}:a]aresample=48000", "aformat=channel_layouts=stereo"]
        if seg.loop:
            # Repeat inside the filter graph rather than with -stream_loop: a
            # looped demuxer next to the piped video deadlocks FFmpeg 7/8 now
            # and then (the pipe stalls after a few frames, ffmpeg never ends).
            if seg.src_duration > 0:
                loops = int(plan.total // seg.src_duration) + 2
                samples = int(seg.src_duration * 48000) + 48000
            else:
                loops, samples = -1, 2147483647
            chain.append(f"aloop=loop={loops}:size={samples}")
        if abs(seg.volume - 1.0) > 1e-3:
            chain.append(f"volume={seg.volume:.3f}")
        if seg.offset > 0:
            ms = int(round(seg.offset * 1000))
            chain.append(f"adelay={ms}|{ms}")
        chain.append(f"atrim=0:{plan.total:.3f}")
        if seg.fade_out > 0 and plan.total > seg.fade_out:
            chain.append(f"afade=t=out:st={plan.total - seg.fade_out:.3f}:d={seg.fade_out:.3f}")
        chains.append(",".join(chain) + f"[a{i}]")
    n = len(plan.audio)
    if n == 0:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        graph = f"[0:a]atrim=0:{plan.total:.3f}[aout]"
    elif n == 1:
        graph = chains[0].replace("[a0]", "") + f",apad=whole_dur={plan.total:.3f}[aout]"
    else:
        # Bounded padding on purpose: a plain `apad` (infinite) followed by
        # atrim hangs FFmpeg 7/8 about half the time.
        graph = ";".join(chains) + ";" + "".join(f"[a{i}]" for i in range(n)) + \
            f"amix=inputs={n}:duration=longest:normalize=0,apad=whole_dur={plan.total:.3f}[aout]"
    cmd += ["-filter_complex", graph, "-map", "[aout]", "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2",
            "-t", f"{plan.total:.3f}", out_wav]
    return cmd


def encoder_command(plan: Plan, mixed_wav: str, out_path: str) -> list[str]:
    """Encode piped RGB frames plus the mixed wav to H.264 + AAC."""
    s = plan.settings
    w, h = s.even_size
    return [ff.require_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(s.fps), "-i", "pipe:0",
            "-i", mixed_wav, "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", s.preset, "-crf", str(s.crf), "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            "-t", f"{plan.total:.3f}", out_path]


def render(plan: Plan, out_path: str, log=None, progress=None, cancelled=None) -> str:
    """Compose every frame and encode the short to `out_path`."""
    s = plan.settings
    w, h = s.even_size
    composer = FrameComposer(plan)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    tmp_out = os.path.join(os.path.dirname(os.path.abspath(out_path)), "." + os.path.basename(out_path) + ".part.mp4")
    mixed = tmp_out + ".audio.wav"
    if cancelled and cancelled():
        raise RenderCancelled()
    mix = mix_command(plan, mixed)
    if log:
        log("ffmpeg " + " ".join(f'"{a}"' if " " in a else a for a in mix[1:]))
    try:
        ff.run(mix[1:].copy()[mix[1:].index("-y") + 1:], timeout=max(120.0, plan.total * 4))
    except ff.FFmpegError as exc:
        _remove(mixed)
        raise RenderError(f"audio mix failed: {exc}") from exc
    cmd = encoder_command(plan, mixed, tmp_out)
    if log:
        log("ffmpeg " + " ".join(f'"{a}"' if " " in a else a for a in cmd[1:]))
    err_file = tempfile.TemporaryFile()
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=err_file,
                                bufsize=w * h * 3 * 2, **ff._no_window())
    except OSError as exc:
        _remove(mixed)
        raise RenderError(f"could not start ffmpeg: {exc}") from exc
    total_frames = max(1, int(round(plan.total * s.fps)))
    try:
        with bgmod.FrameReader(plan.background, w, h, s.fps, plan.total, s.fit, s.background_rgb) as reader:
            assert proc.stdin is not None
            for i in range(total_frames):
                if cancelled and cancelled():
                    raise RenderCancelled()
                frame = composer.frame_at(i / s.fps, reader.next_frame())
                try:
                    proc.stdin.write(frame.tobytes())
                except (BrokenPipeError, OSError) as exc:
                    raise RenderError("ffmpeg stopped accepting frames: " + _stderr_tail(err_file, proc)) from exc
                if progress and (i % 3 == 0 or i == total_frames - 1):
                    progress(i + 1, total_frames)
            proc.stdin.close()
            try:
                rc = proc.wait(timeout=float(os.environ.get("TRENDYREELS_ENCODE_TIMEOUT", 0) or max(120.0, plan.total * 2)))
            except subprocess.TimeoutExpired as exc:
                _kill(proc)
                raise RenderError("ffmpeg did not finish after the last frame: " + _stderr_tail(err_file, proc)) from exc
    except bgmod.BackgroundError as exc:
        _kill(proc)
        _remove(mixed)
        raise RenderError(str(exc)) from exc
    except BaseException:
        _kill(proc)
        _remove(tmp_out)
        _remove(mixed)
        raise
    _remove(mixed)
    if rc != 0:
        tail = _stderr_tail(err_file, proc)
        _remove(tmp_out)
        raise RenderError(f"ffmpeg exited with {rc}: {tail}")
    os.replace(tmp_out, out_path)
    if log:
        log(f"wrote {out_path}")
    return out_path


def _stderr_tail(err_file, proc) -> str:
    try:
        if proc.poll() is None:
            proc.wait(timeout=5)
    except subprocess.SubprocessError:
        pass
    try:
        err_file.seek(0)
        return err_file.read().decode("utf-8", "replace").strip()[-1500:]
    except (OSError, ValueError):
        return ""


def _kill(proc: subprocess.Popen) -> None:
    ff.kill_tree(proc)
    try:
        if proc.stdin:
            proc.stdin.close()
    except OSError:
        pass


def _remove(path: str) -> None:
    """Delete a partial output; on Windows a just-killed ffmpeg may hold it for a moment."""
    for _ in range(20):
        try:
            if os.path.exists(path):
                os.remove(path)
            return
        except OSError:
            time.sleep(0.1)
