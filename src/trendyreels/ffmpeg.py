"""Locating FFmpeg and probing media.  FFmpeg is never bundled: it is found on
PATH, next to the executable, or via the TRENDYREELS_FFMPEG environment variable.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

FFMPEG_DOWNLOAD_URL = "https://ffmpeg.org/download.html"


class FFmpegError(Exception):
    pass


def _no_window() -> dict:
    """Keep console windows from flashing when launched from the GUI exe on Windows."""
    if sys.platform == "win32":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {}


def _candidates(name: str) -> list[str]:
    env = os.environ.get("TRENDYREELS_FFMPEG")
    out = []
    if env:
        out.append(env if name == "ffmpeg" else os.path.join(os.path.dirname(env), name))
    exe_dir = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(sys.argv[0] or "."))
    out.append(os.path.join(exe_dir, name))
    found = shutil.which(name)
    if found:
        out.append(found)
    return out


def find_tool(name: str = "ffmpeg") -> str | None:
    for cand in _candidates(name):
        exe = cand if cand.lower().endswith(".exe") or sys.platform != "win32" else cand + ".exe"
        for p in (cand, exe):
            if os.path.isfile(p):
                return p
    return None


def find_ffmpeg() -> str | None:
    return find_tool("ffmpeg")


def find_ffprobe() -> str | None:
    """ffprobe, preferring the one that ships next to the ffmpeg we use."""
    ffm = find_ffmpeg()
    if ffm:
        sibling = os.path.join(os.path.dirname(ffm), "ffprobe" + (".exe" if sys.platform == "win32" else ""))
        if os.path.isfile(sibling):
            return sibling
    return find_tool("ffprobe")


def require_ffmpeg() -> str:
    path = find_ffmpeg()
    if not path:
        raise FFmpegError(f"FFmpeg was not found. Install it from {FFMPEG_DOWNLOAD_URL} and make sure 'ffmpeg' runs in a terminal.")
    return path


def ffmpeg_version(path: str | None = None) -> str | None:
    path = path or find_ffmpeg()
    if not path:
        return None
    try:
        out = subprocess.run([path, "-version"], capture_output=True, text=True, timeout=10, **_no_window())
        return out.stdout.splitlines()[0] if out.stdout else None
    except (OSError, subprocess.SubprocessError):
        return None


def run(args: list[str], timeout: float | None = None, log=None) -> None:
    """Run ffmpeg with the given arguments (after the executable); raise FFmpegError with its stderr on failure."""
    cmd = [require_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *args]
    if log:
        log("ffmpeg " + " ".join(_quote(a) for a in args))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **_no_window())
    except (OSError, subprocess.SubprocessError) as exc:
        raise FFmpegError(f"ffmpeg could not run: {exc}") from exc
    if proc.returncode != 0:
        raise FFmpegError((proc.stderr or "").strip()[-2000:] or f"ffmpeg exited with {proc.returncode}")


def _quote(a: str) -> str:
    return f'"{a}"' if " " in a else a


def probe(path: str) -> dict | None:
    """ffprobe-style dict: {"format": {"duration"}, "streams": [{codec_type, width, height, r_frame_rate}]}.

    Uses ffprobe when available, otherwise parses `ffmpeg -i` output so a bare
    ffmpeg.exe is enough for the app to work.
    """
    ffprobe = find_ffprobe()
    if ffprobe:
        try:
            out = subprocess.run(
                [ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
                capture_output=True, text=True, timeout=30, **_no_window())
            if out.returncode == 0:
                return json.loads(out.stdout)
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    return _probe_with_ffmpeg(path)


_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_VIDEO_RE = re.compile(r"Stream #\d+:\d+.*?: Video:.*?,\s*(\d{2,5})x(\d{2,5})")
_FPS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*fps")
_AUDIO_RE = re.compile(r"Stream #\d+:\d+.*?: Audio:")


def _probe_with_ffmpeg(path: str) -> dict | None:
    ffm = find_ffmpeg()
    if not ffm or not os.path.isfile(path):
        return None
    try:
        out = subprocess.run([ffm, "-hide_banner", "-i", path], capture_output=True, text=True,
                             timeout=30, **_no_window())
    except (OSError, subprocess.SubprocessError):
        return None
    text = out.stderr or ""
    m = _DURATION_RE.search(text)
    if not m:
        return None
    duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    streams: list[dict] = []
    for line in text.splitlines():
        v = _VIDEO_RE.search(line)
        if v:
            st = {"codec_type": "video", "width": int(v.group(1)), "height": int(v.group(2))}
            f = _FPS_RE.search(line)
            if f:
                st["r_frame_rate"] = f"{f.group(1)}/1"
            streams.append(st)
        elif _AUDIO_RE.search(line):
            streams.append({"codec_type": "audio"})
    return {"format": {"duration": str(duration)}, "streams": streams}


def media_duration(path: str) -> float | None:
    info = probe(path)
    try:
        return float(info["format"]["duration"])  # type: ignore[index]
    except (TypeError, KeyError, ValueError):
        return None


def video_info(path: str) -> tuple[float, int, int, bool] | None:
    """(duration, width, height, has_audio) of a video file, or None."""
    info = probe(path)
    if not info:
        return None
    try:
        duration = float(info["format"]["duration"])
    except (TypeError, KeyError, ValueError):
        duration = 0.0
    width = height = 0
    has_audio = False
    for st in info.get("streams", []):
        if st.get("codec_type") == "video" and not width:
            width, height = int(st.get("width") or 0), int(st.get("height") or 0)
        elif st.get("codec_type") == "audio":
            has_audio = True
    if not width:
        return None
    return duration, width, height, has_audio


# ------------------------------------------------------------ audio helpers

def make_silence(path: str, seconds: float, rate: int = 24000) -> str:
    run(["-f", "lavfi", "-i", f"anullsrc=r={rate}:cl=mono", "-t", f"{max(0.05, seconds):.3f}", "-c:a", "pcm_s16le", path])
    return path


def to_wav(src: str, dst: str, speed: float = 1.0, rate: int = 24000) -> str:
    """Decode any audio to mono PCM wav, optionally time-stretched (pitch kept) by `speed`."""
    filters = []
    s = float(speed)
    # atempo accepts 0.5..100 per instance; chain for anything below 0.5.
    while s < 0.5:
        filters.append("atempo=0.5")
        s /= 0.5
    if abs(s - 1.0) > 1e-3:
        filters.append(f"atempo={s:.4f}")
    args = ["-i", src, "-vn", "-ac", "1", "-ar", str(rate)]
    if filters:
        args += ["-af", ",".join(filters)]
    run(args + ["-c:a", "pcm_s16le", dst])
    return dst
