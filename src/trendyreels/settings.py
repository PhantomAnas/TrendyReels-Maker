"""Project settings and their JSON persistence.

`ProjectSettings` describes how every short looks and sounds; the stories are
passed separately so one settings object can render a whole queue.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields

from platformdirs import user_config_dir

APP_NAME = "TrendyReelsMaker"

ASPECT_PRESETS: dict[str, tuple[int, int]] = {
    "9:16 Portrait (1080x1920)": (1080, 1920),
    "1:1 Square (1080x1080)": (1080, 1080),
    "16:9 Landscape (1920x1080)": (1920, 1080),
    "4:5 Portrait (1080x1350)": (1080, 1350),
}

TTS_PROVIDERS = ("edge", "elevenlabs", "file", "silent")
CAPTION_TIMINGS = ("auto", "whisper", "estimate")
FIT_MODES = ("crop", "blur")
PICK_MODES = ("random", "sequential")
TITLE_CARD_MODES = ("title", "fixed", "off")

RGB = tuple[int, int, int]


def config_path() -> str:
    return os.path.join(user_config_dir(APP_NAME, appauthor=False), "settings.json")


def cache_dir() -> str:
    return os.path.join(user_config_dir(APP_NAME, appauthor=False), "cache")


@dataclass
class ProjectSettings:
    # Canvas
    width: int = 1080
    height: int = 1920
    fps: int = 30

    # Voice
    tts_provider: str = "edge"              # edge | elevenlabs | file | silent
    voice: str = "en-US-ChristopherNeural"  # Edge voice short name, or an ElevenLabs voice id
    elevenlabs_model: str = "eleven_multilingual_v2"
    narration_file: str = ""                # provider "file": your own recorded narration
    speed: float = 1.0                      # 0.5 .. 2.0
    voice_volume: float = 1.0
    read_title: bool = True
    expand_abbreviations: bool = True

    # Captions
    captions: bool = True
    caption_timing: str = "auto"            # auto | whisper | estimate
    whisper_model: str = "base"
    font_path: str = ""                     # empty = a bold system font
    font_size: float = 0.075                # fraction of the canvas width
    words_per_caption: int = 3
    max_chars_per_caption: int = 22
    uppercase: bool = True
    text_color: RGB = (255, 255, 255)
    highlight: bool = True
    highlight_color: RGB = (255, 214, 10)
    highlight_scale: float = 1.12           # the spoken word pops a little
    outline_color: RGB = (0, 0, 0)
    outline: float = 0.10                   # fraction of the font size
    shadow: bool = True
    box: bool = False
    box_color: RGB = (0, 0, 0)
    box_opacity: float = 0.55
    caption_y: float = 0.5                  # vertical centre as a fraction of the height
    caption_width: float = 0.88             # fraction of the canvas width the text may use

    # Title card
    title_card: str = "title"               # title (while the title is read) | fixed | off
    title_card_seconds: float = 2.5         # for "fixed", or when the title is not read aloud
    channel_name: str = "Your Channel"

    # Background footage
    background: str = ""                    # a video file or a folder of videos; empty = soft gradient
    background_pick: str = "random"         # random | sequential
    random_start: bool = True
    fit: str = "crop"                       # crop | blur
    background_audio_volume: float = 0.0    # footage sound, 0 = muted
    background_rgb: RGB = (22, 20, 36)

    # Music
    music_path: str = ""                    # file, or folder to pick a random track from
    music_volume: float = 0.12

    # Timing
    lead_in: float = 0.5                    # silence before the voice starts
    title_gap: float = 0.35                 # pause between the title and the story
    tail: float = 1.0                       # silence after the voice ends

    # Output
    output_folder: str = ""
    crf: int = 20
    preset: str = "medium"
    skip_existing: bool = True
    timestamp_names: bool = False

    # Sources (GUI + CLI convenience)
    stories_path: str = ""                  # a .txt file or a folder of .txt files
    extra: dict = field(default_factory=dict)

    # ------------------------------------------------------------ helpers
    def validate(self) -> list[str]:
        problems = []
        if self.width < 64 or self.height < 64:
            problems.append("canvas must be at least 64x64")
        if self.fps < 1 or self.fps > 120:
            problems.append("fps must be between 1 and 120")
        if self.tts_provider not in TTS_PROVIDERS:
            problems.append(f"unknown voice provider '{self.tts_provider}'")
        if self.tts_provider == "file" and not os.path.isfile(self.narration_file):
            problems.append("narration audio file does not exist")
        if not 0.5 <= self.speed <= 2.0:
            problems.append("speed must be between 0.5x and 2x")
        if self.caption_timing not in CAPTION_TIMINGS:
            problems.append(f"unknown caption timing '{self.caption_timing}'")
        if self.words_per_caption < 1:
            problems.append("words per caption must be at least 1")
        if not 0.02 <= self.font_size <= 0.3:
            problems.append("font size must be between 2% and 30% of the width")
        if self.font_path and not os.path.isfile(self.font_path):
            problems.append("font file does not exist")
        if self.title_card not in TITLE_CARD_MODES:
            problems.append(f"unknown title card mode '{self.title_card}'")
        if self.background and not os.path.exists(self.background):
            problems.append("background footage file or folder does not exist")
        if self.background_pick not in PICK_MODES:
            problems.append(f"unknown pick mode '{self.background_pick}'")
        if self.fit not in FIT_MODES:
            problems.append(f"unknown fit mode '{self.fit}'")
        if self.music_path and not os.path.exists(self.music_path):
            problems.append("music file or folder does not exist")
        if self.lead_in < 0 or self.tail < 0 or self.title_gap < 0:
            problems.append("lead-in, title gap and tail cannot be negative")
        if not 0 <= self.crf <= 51:
            problems.append("crf must be between 0 and 51")
        return problems

    @property
    def even_size(self) -> tuple[int, int]:
        """H.264 needs even dimensions."""
        return (self.width // 2) * 2, (self.height // 2) * 2

    def default_output_folder(self) -> str:
        return self.output_folder or os.path.join(os.path.expanduser("~"), "Videos", "TrendyReels Maker")

    # -------------------------------------------------------- persistence
    @classmethod
    def from_dict(cls, data: dict) -> "ProjectSettings":
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in data.items() if k in known}
        for key in ("text_color", "highlight_color", "outline_color", "box_color", "background_rgb"):
            if key in clean and isinstance(clean[key], (list, tuple)):
                try:
                    clean[key] = tuple(max(0, min(255, int(c))) for c in clean[key][:3])
                except (TypeError, ValueError):
                    clean.pop(key)
        try:
            return cls(**clean)
        except TypeError:
            return cls()

    @classmethod
    def load(cls, path: str | None = None) -> "ProjectSettings":
        path = path or config_path()
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return cls()
        return cls.from_dict(data) if isinstance(data, dict) else cls()

    def save(self, path: str | None = None) -> None:
        path = path or config_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(asdict(self), fh, indent=2)
        os.replace(tmp, path)
