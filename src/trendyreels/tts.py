"""Voices.  Every provider returns a `Narration`: an audio file plus, when the
engine reports them, the moment each word is spoken.

- edge        Microsoft Edge neural voices via `edge-tts` (free, needs internet, word timings)
- elevenlabs  ElevenLabs via its REST API (API key from ELEVENLABS_API_KEY or the settings, word timings)
- file        your own recorded narration (timings from whisper or an estimate)
- silent      no voice: silence of an estimated length (offline previews, tests)
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from . import ffmpeg as ff
from .settings import ProjectSettings, cache_dir
from .timing import Word, estimate_words, estimated_duration, scale, tidy

ELEVENLABS_URL = "https://api.elevenlabs.io/v1"
ELEVENLABS_KEY_ENV = "ELEVENLABS_API_KEY"


class TTSError(Exception):
    pass


@dataclass
class Narration:
    audio_path: str                 # mono wav
    duration: float
    words: list[Word] | None        # None when the provider gives no timings


# A curated set of English Edge voices so the app is usable offline-first; the
# full list (300+) can be fetched with `list_edge_voices`.
EDGE_VOICES: list[tuple[str, str]] = [
    ("en-US-ChristopherNeural", "Christopher (US, male, calm)"),
    ("en-US-GuyNeural", "Guy (US, male, upbeat)"),
    ("en-US-AndrewMultilingualNeural", "Andrew (US, male, warm)"),
    ("en-US-BrianMultilingualNeural", "Brian (US, male, casual)"),
    ("en-US-EricNeural", "Eric (US, male)"),
    ("en-US-RogerNeural", "Roger (US, male)"),
    ("en-US-SteffanNeural", "Steffan (US, male)"),
    ("en-US-AriaNeural", "Aria (US, female, expressive)"),
    ("en-US-JennyNeural", "Jenny (US, female, friendly)"),
    ("en-US-AvaMultilingualNeural", "Ava (US, female, bright)"),
    ("en-US-EmmaMultilingualNeural", "Emma (US, female, clear)"),
    ("en-US-MichelleNeural", "Michelle (US, female)"),
    ("en-US-AnaNeural", "Ana (US, child)"),
    ("en-GB-RyanNeural", "Ryan (UK, male)"),
    ("en-GB-ThomasNeural", "Thomas (UK, male)"),
    ("en-GB-SoniaNeural", "Sonia (UK, female)"),
    ("en-GB-LibbyNeural", "Libby (UK, female)"),
    ("en-AU-WilliamNeural", "William (AU, male)"),
    ("en-AU-NatashaNeural", "Natasha (AU, female)"),
    ("en-CA-LiamNeural", "Liam (CA, male)"),
    ("en-CA-ClaraNeural", "Clara (CA, female)"),
    ("en-IN-PrabhatNeural", "Prabhat (IN, male)"),
    ("en-IN-NeerjaNeural", "Neerja (IN, female)"),
    ("en-IE-ConnorNeural", "Connor (IE, male)"),
    ("en-NZ-MitchellNeural", "Mitchell (NZ, male)"),
    ("en-ZA-LukeNeural", "Luke (ZA, male)"),
]

# A few well-known ElevenLabs premade voices; "Refresh" in the app fetches your account's list.
ELEVENLABS_VOICES: list[tuple[str, str]] = [
    ("pNInz6obpgDQGcFmaJgB", "Adam"),
    ("ErXwobaYiN019PkySvjV", "Antoni"),
    ("21m00Tcm4TlvDq8ikWAM", "Rachel"),
    ("EXAVITQu4vr4xnSDxMaL", "Sarah"),
    ("XrExE9yKIg1WjnnlVkGX", "Matilda"),
    ("TxGEqnHWrfWFTfGW9XjX", "Josh"),
    ("onwK4e9ZLuTAKqWW03F9", "Daniel"),
    ("pFZP5JQG7iQjIQuC4Bku", "Lily"),
]


def edge_rate(speed: float) -> str:
    return f"{int(round((float(speed) - 1.0) * 100)):+d}%"


def elevenlabs_api_key(settings: ProjectSettings | None = None) -> str:
    key = os.environ.get(ELEVENLABS_KEY_ENV, "").strip()
    if not key and settings is not None:
        key = str(settings.extra.get("elevenlabs_api_key", "") or "").strip()
    return key


# ----------------------------------------------------------------- edge-tts

def _edge_voices_cache() -> str:
    return os.path.join(cache_dir(), "edge_voices.json")


def list_edge_voices(refresh: bool = False) -> list[tuple[str, str]]:
    """[(short name, label)] of every Edge voice, cached on disk after the first fetch."""
    path = _edge_voices_cache()
    if not refresh and os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return [(d["short"], d["label"]) for d in data]
        except (OSError, ValueError, KeyError, TypeError):
            pass
    try:
        import edge_tts
    except Exception as exc:  # noqa: BLE001
        raise TTSError("edge-tts is not installed: pip install edge-tts") from exc
    try:
        voices = asyncio.run(edge_tts.list_voices())
    except Exception as exc:  # noqa: BLE001
        raise TTSError(f"could not fetch the Edge voice list: {exc}") from exc
    out = []
    for v in voices:
        short = v.get("ShortName", "")
        name = short.split("-")[-1].replace("Neural", "").replace("Multilingual", " (multilingual)")
        locale = v.get("LocaleName") or v.get("Locale", "")
        gender = (v.get("Gender") or "").lower()
        out.append((short, f"{name} ({locale}, {gender})"))
    out.sort(key=lambda kv: (not kv[0].startswith("en-"), kv[1]))
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump([{"short": s, "label": lb} for s, lb in out], fh)
    except OSError:
        pass
    return out


def synthesize_edge(text: str, voice: str, speed: float, out_wav: str, log=None) -> Narration:
    try:
        import edge_tts
    except Exception as exc:  # noqa: BLE001
        raise TTSError("edge-tts is not installed: pip install edge-tts") from exc
    mp3 = os.path.splitext(out_wav)[0] + ".mp3"
    words: list[Word] = []
    comm = edge_tts.Communicate(text, voice or "en-US-ChristopherNeural", rate=edge_rate(speed), boundary="WordBoundary")
    try:
        with open(mp3, "wb") as fh:
            for chunk in comm.stream_sync():
                if chunk["type"] == "audio":
                    fh.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    start = chunk["offset"] / 1e7
                    words.append(Word(str(chunk["text"]), start, start + chunk["duration"] / 1e7))
    except Exception as exc:  # noqa: BLE001
        raise TTSError(f"Edge TTS failed ({type(exc).__name__}: {exc}). Check your internet connection and the voice name.") from exc
    if not os.path.getsize(mp3):
        raise TTSError("Edge TTS returned no audio (is the voice name valid?)")
    ff.to_wav(mp3, out_wav)
    duration = ff.media_duration(out_wav) or (words[-1].end if words else 0.0)
    if log:
        log(f"edge-tts: {voice}, {duration:.1f}s, {len(words)} word timings")
    return Narration(out_wav, duration, tidy(words) if words else None)


# --------------------------------------------------------------- elevenlabs

def _el_request(path: str, api_key: str, body: dict | None = None, timeout: float = 120) -> dict:
    req = urllib.request.Request(
        ELEVENLABS_URL + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"xi-api-key": api_key, "Content-Type": "application/json", "Accept": "application/json"},
        method="POST" if body is not None else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:300]
        except Exception:  # noqa: BLE001
            pass
        raise TTSError(f"ElevenLabs returned HTTP {exc.code}: {detail or exc.reason}") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise TTSError(f"ElevenLabs request failed: {exc}") from exc


def list_elevenlabs_voices(api_key: str) -> list[tuple[str, str]]:
    data = _el_request("/voices", api_key, timeout=30)
    return [(v["voice_id"], v.get("name", v["voice_id"])) for v in data.get("voices", []) if "voice_id" in v]


def words_from_alignment(alignment: dict) -> list[Word]:
    """ElevenLabs returns per-character times; join characters into words."""
    chars = alignment.get("characters") or []
    starts = alignment.get("character_start_times_seconds") or []
    ends = alignment.get("character_end_times_seconds") or []
    words: list[Word] = []
    buf: list[str] = []
    w_start = 0.0
    w_end = 0.0
    for ch, s, e in zip(chars, starts, ends):
        if ch.isspace():
            if buf:
                words.append(Word("".join(buf), w_start, w_end))
                buf = []
            continue
        if not buf:
            w_start = float(s)
        buf.append(ch)
        w_end = float(e)
    if buf:
        words.append(Word("".join(buf), w_start, w_end))
    return tidy(words)


def synthesize_elevenlabs(text: str, voice_id: str, api_key: str, model: str, speed: float, out_wav: str, log=None) -> Narration:
    if not api_key:
        raise TTSError(f"No ElevenLabs API key. Set the {ELEVENLABS_KEY_ENV} environment variable or paste the key in the Voice card.")
    body = {"text": text, "model_id": model or "eleven_multilingual_v2"}
    data = _el_request(f"/text-to-speech/{voice_id}/with-timestamps", api_key, body)
    audio_b64 = data.get("audio_base64")
    if not audio_b64:
        raise TTSError("ElevenLabs returned no audio")
    mp3 = os.path.splitext(out_wav)[0] + ".mp3"
    with open(mp3, "wb") as fh:
        fh.write(base64.b64decode(audio_b64))
    words = words_from_alignment(data.get("alignment") or {})
    ff.to_wav(mp3, out_wav, speed=speed)
    if abs(speed - 1.0) > 1e-3:
        words = scale(words, 1.0 / speed)
    duration = ff.media_duration(out_wav) or (words[-1].end if words else 0.0)
    if log:
        log(f"elevenlabs: voice {voice_id}, {duration:.1f}s, {len(words)} word timings")
    return Narration(out_wav, duration, words or None)


# ---------------------------------------------------------- file & silence

def narration_from_file(path: str, speed: float, out_wav: str, log=None) -> Narration:
    if not os.path.isfile(path):
        raise TTSError(f"narration file not found: {path}")
    ff.to_wav(path, out_wav, speed=speed)
    duration = ff.media_duration(out_wav)
    if not duration:
        raise TTSError(f"could not read the narration audio: {path}")
    if log:
        log(f"narration: {os.path.basename(path)}, {duration:.1f}s")
    return Narration(out_wav, duration, None)


def synthesize_silent(text: str, speed: float, out_wav: str, log=None) -> Narration:
    duration = estimated_duration(text) / max(0.25, speed)
    ff.make_silence(out_wav, duration)
    if log:
        log(f"silent voice: {duration:.1f}s of silence")
    return Narration(out_wav, duration, estimate_words(text, duration))


# ----------------------------------------------------------------- dispatch

def synthesize(text: str, settings: ProjectSettings, out_wav: str, log=None) -> Narration:
    p = settings.tts_provider
    if p == "edge":
        return synthesize_edge(text, settings.voice, settings.speed, out_wav, log)
    if p == "elevenlabs":
        return synthesize_elevenlabs(text, settings.voice, elevenlabs_api_key(settings), settings.elevenlabs_model,
                                     settings.speed, out_wav, log)
    if p == "file":
        return narration_from_file(settings.narration_file, settings.speed, out_wav, log)
    if p == "silent":
        return synthesize_silent(text, settings.speed, out_wav, log)
    raise TTSError(f"unknown voice provider '{p}'")
