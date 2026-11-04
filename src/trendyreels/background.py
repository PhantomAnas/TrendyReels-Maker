"""Background footage: choosing a clip, fitting it to the canvas, and reading
its frames through an FFmpeg pipe.  No footage ships with the app; without
any the canvas is a soft gradient."""

from __future__ import annotations

import os
import random
import subprocess
from dataclasses import dataclass

import numpy as np

from . import ffmpeg as ff

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mpg", ".mpeg", ".wmv", ".ts"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus", ".wma"}


class BackgroundError(Exception):
    pass


def list_videos(folder: str) -> list[str]:
    out = []
    for name in sorted(os.listdir(folder)):
        p = os.path.join(folder, name)
        if os.path.isfile(p) and os.path.splitext(name)[1].lower() in VIDEO_EXTENSIONS:
            out.append(p)
    return out


def list_audio(folder: str) -> list[str]:
    out = []
    for name in sorted(os.listdir(folder)):
        p = os.path.join(folder, name)
        if os.path.isfile(p) and os.path.splitext(name)[1].lower() in AUDIO_EXTENSIONS:
            out.append(p)
    return out


def choose_file(path: str, index: int, mode: str, exts: set[str], rng: random.Random | None = None) -> str | None:
    """A file from `path` (a file, or a folder picked from by `mode`), or None."""
    if not path:
        return None
    if os.path.isfile(path):
        return path
    if not os.path.isdir(path):
        return None
    files = [os.path.join(path, n) for n in sorted(os.listdir(path))
             if os.path.splitext(n)[1].lower() in exts and os.path.isfile(os.path.join(path, n))]
    if not files:
        return None
    if mode == "sequential":
        return files[index % len(files)]
    return (rng or random).choice(files)


@dataclass
class BackgroundPlan:
    path: str | None            # None = generated gradient
    start: float = 0.0          # seek into the clip
    loops: int = 0              # extra -stream_loop iterations needed
    src_duration: float = 0.0
    src_width: int = 0
    src_height: int = 0
    has_audio: bool = False


def plan_background(path: str | None, needed: float, random_start: bool = True,
                    rng: random.Random | None = None) -> BackgroundPlan:
    if not path:
        return BackgroundPlan(None)
    info = ff.video_info(path)
    if not info:
        raise BackgroundError(f"could not read the background video: {path}")
    duration, w, h, has_audio = info
    plan = BackgroundPlan(path, 0.0, 0, duration, w, h, has_audio)
    if duration <= 0:
        return plan
    if duration >= needed + 0.5:
        if random_start:
            plan.start = round((rng or random).uniform(0.0, duration - needed - 0.25), 2)
    else:
        plan.loops = int(needed // duration) + 1
    return plan


def fit_filter(fit: str, width: int, height: int) -> str:
    """FFmpeg filter string that maps any source onto a width x height canvas."""
    if fit == "blur":
        return (f"split[a][b];[a]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},"
                f"boxblur=luma_radius=min(h\\,w)/20:luma_power=1,eq=brightness=-0.08[bg];"
                f"[b]scale={width}:{height}:force_original_aspect_ratio=decrease[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2,format=rgb24")
    return f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},format=rgb24"


def _input_args(plan: BackgroundPlan) -> list[str]:
    args: list[str] = []
    if plan.loops:
        args += ["-stream_loop", str(plan.loops)]
    if plan.start > 0:
        args += ["-ss", f"{plan.start:.3f}"]
    args += ["-i", plan.path or ""]
    return args


def gradient_frame(width: int, height: int, rgb: tuple[int, int, int]) -> np.ndarray:
    """A soft dark gradient with a lighter glow near the top: the no-footage canvas."""
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    t = (yy / max(1, height - 1)) * 0.65 + (xx / max(1, width - 1)) * 0.35
    base = np.array(rgb, dtype=np.float32)
    top = np.clip(base * 1.9 + 28, 0, 255)
    frame = top[None, None, :] * (1 - t[..., None]) + base[None, None, :] * t[..., None]
    glow = np.exp(-(((xx - width * 0.3) / (width * 0.6)) ** 2 + ((yy - height * 0.2) / (height * 0.5)) ** 2))
    frame = frame + glow[..., None] * np.array([60, 40, 90], dtype=np.float32)
    return np.clip(frame, 0, 255).astype(np.uint8)


class FrameReader:
    """Iterates RGB frames of the fitted background for `seconds` at `fps`.
    Short clips loop; a missing clip yields the gradient frame."""

    def __init__(self, plan: BackgroundPlan, width: int, height: int, fps: int, seconds: float, fit: str = "crop",
                 background_rgb: tuple[int, int, int] = (22, 20, 36)) -> None:
        self.plan, self.width, self.height, self.fps, self.fit = plan, width, height, fps, fit
        self.total = max(1, int(round(seconds * fps)))
        self.frame_bytes = width * height * 3
        self.proc: subprocess.Popen | None = None
        self._last: np.ndarray | None = None
        self._count = 0
        self._gradient = gradient_frame(width, height, background_rgb) if plan.path is None else None

    def __enter__(self) -> "FrameReader":
        if self.plan.path is not None:
            cmd = [ff.require_ffmpeg(), "-hide_banner", "-loglevel", "error", "-nostdin",
                   *_input_args(self.plan), "-an", "-sn", "-dn",
                   "-t", f"{self.total / self.fps + 1.0:.3f}",
                   "-filter_complex", f"[0:v]fps={self.fps},{fit_filter(self.fit, self.width, self.height)}[out]",
                   "-map", "[out]", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                         bufsize=self.frame_bytes * 4, **ff._no_window())
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        if self.proc is not None:
            ff.kill_tree(self.proc)
            try:
                if self.proc.stdout:
                    self.proc.stdout.close()
            except OSError:
                pass
            self.proc = None

    def __len__(self) -> int:
        return self.total

    def __iter__(self):
        for _ in range(self.total):
            yield self.next_frame()

    def next_frame(self) -> np.ndarray:
        self._count += 1
        if self._gradient is not None:
            return self._gradient.copy()
        buf = b""
        if self.proc is not None and self.proc.stdout is not None:
            buf = self.proc.stdout.read(self.frame_bytes)
        if len(buf) == self.frame_bytes:
            self._last = np.frombuffer(buf, dtype=np.uint8).reshape(self.height, self.width, 3)
            return self._last.copy()
        if self._last is None:
            raise BackgroundError(f"could not decode frames from {self.plan.path}")
        return self._last.copy()     # clip ended a hair early: hold the last frame


def grab_frame(path: str, t: float, width: int, height: int, fit: str = "crop") -> np.ndarray | None:
    """One fitted RGB frame at time t (for previews)."""
    cmd = [ff.require_ffmpeg(), "-hide_banner", "-loglevel", "error", "-nostdin",
           "-ss", f"{max(0.0, t):.3f}", "-i", path, "-an", "-frames:v", "1",
           "-filter_complex", f"[0:v]{fit_filter(fit, width, height)}[out]", "-map", "[out]",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=60, **ff._no_window())
    except (OSError, subprocess.SubprocessError):
        return None
    if len(out.stdout) < width * height * 3:
        return None
    return np.frombuffer(out.stdout[: width * height * 3], dtype=np.uint8).reshape(height, width, 3).copy()
