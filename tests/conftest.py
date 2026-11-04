from __future__ import annotations

import os
import subprocess

import pytest

from trendyreels import ffmpeg as ff

HAVE_FFMPEG = ff.find_ffmpeg() is not None
needs_ffmpeg = pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg not installed")


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Never read or write the real user settings or cache during tests."""
    monkeypatch.setattr("trendyreels.settings.config_path", lambda: str(tmp_path / "cfg" / "settings.json"))
    monkeypatch.setattr("trendyreels.settings.cache_dir", lambda: str(tmp_path / "cfg" / "cache"))
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)


def make_clip(path: str, seconds: float = 3.0, size: str = "320x180", audio: bool = True, fps: int = 25) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cmd = [ff.require_ffmpeg(), "-y", "-loglevel", "error",
           "-f", "lavfi", "-i", f"testsrc2=size={size}:rate={fps}:duration={seconds}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
    if audio:
        cmd += ["-c:a", "aac", "-shortest"]
    cmd.append(path)
    subprocess.run(cmd, check=True)
    return path


@pytest.fixture(scope="session")
def clip(tmp_path_factory) -> str:
    if not HAVE_FFMPEG:
        pytest.skip("ffmpeg not installed")
    return make_clip(str(tmp_path_factory.mktemp("clips") / "clip.mp4"))


@pytest.fixture(scope="session")
def clips_folder(tmp_path_factory) -> str:
    if not HAVE_FFMPEG:
        pytest.skip("ffmpeg not installed")
    folder = tmp_path_factory.mktemp("footage")
    make_clip(str(folder / "a.mp4"), 2.0)
    make_clip(str(folder / "b.mp4"), 2.5, audio=False)
    (folder / "notes.txt").write_text("not a video")
    return str(folder)
