"""Command line: `trendyreels --cli ...`.

    trendyreels --cli --stories stories.txt --background ./footage --out ./shorts
    trendyreels --cli --title "My title" --text story.txt --voice en-GB-RyanNeural --speed 1.1
    trendyreels --cli --list-voices
"""

from __future__ import annotations

import argparse
import os
import sys

from . import batch, ffmpeg
from .render import RenderCancelled, RenderError
from .settings import ASPECT_PRESETS, CAPTION_TIMINGS, FIT_MODES, PICK_MODES, TITLE_CARD_MODES, TTS_PROVIDERS, ProjectSettings
from .text import Story, load_stories, parse_stories
from .tts import EDGE_VOICES, TTSError, list_edge_voices


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="trendyreels --cli", description="Render captioned story shorts.")
    src = p.add_argument_group("story")
    src.add_argument("--stories", metavar="PATH", help="a .txt (first line = title) or a folder of .txt files; "
                     "'Title -- Story' lines also work")
    src.add_argument("--title", help="title for a single story")
    src.add_argument("--text", metavar="TEXT_OR_FILE", help="story text, or a path to a text file with the story")
    src.add_argument("--out", help="output folder (default: ~/Videos/TrendyReels Maker)")

    voice = p.add_argument_group("voice")
    voice.add_argument("--provider", choices=TTS_PROVIDERS)
    voice.add_argument("--voice", help="Edge voice short name or ElevenLabs voice id")
    voice.add_argument("--narration", help="your own narration audio (provider 'file')")
    voice.add_argument("--speed", type=float, help="0.5 .. 2.0")
    voice.add_argument("--read-title", choices=["yes", "no"])
    voice.add_argument("--expand", choices=["yes", "no"], help="expand AITA, TL;DR etc. for the voice")

    cap = p.add_argument_group("captions")
    cap.add_argument("--captions", choices=["on", "off"])
    cap.add_argument("--timing", choices=CAPTION_TIMINGS)
    cap.add_argument("--font", help="path to a .ttf/.otf")
    cap.add_argument("--font-size", type=float, help="fraction of the width, e.g. 0.075")
    cap.add_argument("--words", type=int, help="words per caption")
    cap.add_argument("--caption-y", type=float, help="0 = top, 0.5 = centre, 1 = bottom")
    cap.add_argument("--uppercase", choices=["yes", "no"])
    cap.add_argument("--highlight", choices=["yes", "no"])
    cap.add_argument("--title-card", choices=TITLE_CARD_MODES)
    cap.add_argument("--channel", help="name shown on the title card")

    look = p.add_argument_group("look")
    look.add_argument("--background", help="video file or folder of videos")
    look.add_argument("--pick", choices=PICK_MODES)
    look.add_argument("--fit", choices=FIT_MODES)
    look.add_argument("--footage-volume", type=float)
    look.add_argument("--music", help="audio file or folder (random track)")
    look.add_argument("--music-volume", type=float)
    look.add_argument("--aspect", choices=["9:16", "1:1", "16:9", "4:5"])
    look.add_argument("--size", metavar="WxH")
    look.add_argument("--fps", type=int)
    look.add_argument("--crf", type=int)
    look.add_argument("--no-skip", action="store_true", help="re-render even if the output exists")

    p.add_argument("--no-saved-settings", action="store_true", help="start from defaults instead of the GUI's saved settings")
    p.add_argument("--check", action="store_true", help="only report whether FFmpeg was found")
    p.add_argument("--list-voices", action="store_true", help="list Edge voices (fetches the full list when online)")
    return p


def apply_args(s: ProjectSettings, a: argparse.Namespace) -> ProjectSettings:
    yn = {"yes": True, "no": False, "on": True, "off": False, None: None}
    if a.stories: s.stories_path = a.stories
    if a.out: s.output_folder = a.out
    if a.provider: s.tts_provider = a.provider
    if a.voice: s.voice = a.voice
    if a.narration: s.narration_file, s.tts_provider = a.narration, "file"
    if a.speed: s.speed = a.speed
    if yn[a.read_title] is not None: s.read_title = yn[a.read_title]
    if yn[a.expand] is not None: s.expand_abbreviations = yn[a.expand]
    if yn[a.captions] is not None: s.captions = yn[a.captions]
    if a.timing: s.caption_timing = a.timing
    if a.font is not None: s.font_path = a.font
    if a.font_size: s.font_size = a.font_size
    if a.words: s.words_per_caption = a.words
    if a.caption_y is not None: s.caption_y = a.caption_y
    if yn[a.uppercase] is not None: s.uppercase = yn[a.uppercase]
    if yn[a.highlight] is not None: s.highlight = yn[a.highlight]
    if a.title_card: s.title_card = a.title_card
    if a.channel is not None: s.channel_name = a.channel
    if a.background is not None: s.background = a.background
    if a.pick: s.background_pick = a.pick
    if a.fit: s.fit = a.fit
    if a.footage_volume is not None: s.background_audio_volume = a.footage_volume
    if a.music is not None: s.music_path = a.music
    if a.music_volume is not None: s.music_volume = a.music_volume
    if a.aspect:
        key = next(k for k in ASPECT_PRESETS if k.startswith(a.aspect + " "))
        s.width, s.height = ASPECT_PRESETS[key]
    if a.size:
        w, h = a.size.lower().split("x")
        s.width, s.height = int(w), int(h)
    if a.fps: s.fps = a.fps
    if a.crf is not None: s.crf = a.crf
    if a.no_skip: s.skip_existing = False
    return s


def stories_from_args(s: ProjectSettings, a: argparse.Namespace) -> list[Story]:
    if a.text is not None:
        text = a.text
        if os.path.isfile(text):
            with open(text, "r", encoding="utf-8-sig", errors="replace") as fh:
                text = fh.read()
        if a.title:
            return [Story(a.title, text, "cli")]
        return parse_stories(text, "cli")
    if a.title:
        return [Story(a.title, "", "cli")]
    if s.stories_path:
        if not os.path.exists(s.stories_path):
            raise RenderError(f"stories path not found: {s.stories_path}")
        return load_stories(s.stories_path)
    return []


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    if a.check:
        v = ffmpeg.ffmpeg_version()
        print(v or f"FFmpeg not found. Install it from {ffmpeg.FFMPEG_DOWNLOAD_URL}")
        return 0 if v else 1
    if a.list_voices:
        try:
            voices = list_edge_voices()
        except TTSError as exc:
            print(f"(offline: showing the built-in list; {exc})", file=sys.stderr)
            voices = EDGE_VOICES
        for short, label in voices:
            print(f"{short:40} {label}")
        return 0
    s = ProjectSettings() if a.no_saved_settings else ProjectSettings.load()
    s = apply_args(s, a)
    try:
        stories = stories_from_args(s, a)
    except RenderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not stories:
        print("error: give --stories PATH, or --title/--text", file=sys.stderr)
        return 2
    problems = s.validate()
    if problems:
        print("error: " + "; ".join(problems), file=sys.stderr)
        return 2

    last = [-1]

    def progress(done: int, total: int) -> None:
        pct = int(done * 100 / max(1, total))
        if pct != last[0]:
            last[0] = pct
            print(f"\r  {pct:3d}%", end="", flush=True)

    try:
        outputs = batch.run_job(stories, s, log=lambda m: print(m), stage=lambda st: print(f"\n== {st}"),
                                progress=progress)
    except RenderError as exc:
        print(f"\nerror: {exc}", file=sys.stderr)
        return 1
    except (RenderCancelled, KeyboardInterrupt):
        print("\ncancelled", file=sys.stderr)
        return 130
    print("\n" + "\n".join(outputs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
