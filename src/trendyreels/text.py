"""Stories: loading them from text, cleaning them for the voice, and naming the
output files.

Supported inputs
- pasted text (title + body)
- a .txt file: first line is the title, the rest is the story; several stories
  can be separated by a line of `---`
- the legacy batch format `Title -- Story` with one story per line
- a folder of .txt files (one or more stories each)
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass

TEXT_EXTENSIONS = {".txt", ".md"}

# Spoken expansions for common internet shorthand.  Keys match whole words,
# case-sensitively, so "so" and "op" in normal prose are left alone.
ABBREVIATIONS: dict[str, str] = {
    "AITA": "Am I the a-hole",
    "AITAH": "Am I the a-hole",
    "WIBTA": "Would I be the a-hole",
    "WIBTAH": "Would I be the a-hole",
    "NTA": "not the a-hole",
    "YTA": "you're the a-hole",
    "ESH": "everyone sucks here",
    "NAH": "no a-holes here",
    "TIFU": "today I messed up",
    "TL;DR": "too long, didn't read",
    "TLDR": "too long, didn't read",
    "OP": "the original poster",
    "GF": "girlfriend",
    "BF": "boyfriend",
    "SO": "significant other",
    "MIL": "mother-in-law",
    "FIL": "father-in-law",
    "SIL": "sister-in-law",
    "BIL": "brother-in-law",
    "DH": "my husband",
    "DW": "my wife",
    "BFF": "best friend",
    "ETA": "edit to add",
    "TIL": "today I learned",
    "AMA": "ask me anything",
    "ELI5": "explain it like I'm five",
    "IMO": "in my opinion",
    "IMHO": "in my humble opinion",
    "IIRC": "if I recall correctly",
    "AFAIK": "as far as I know",
    "FWIW": "for what it's worth",
    "TBH": "to be honest",
    "NGL": "not gonna lie",
    "IDK": "I don't know",
    "IDC": "I don't care",
    "IRL": "in real life",
    "FOMO": "fear of missing out",
    "SMH": "shaking my head",
    "LOL": "laughing out loud",
    "ROFL": "rolling on the floor laughing",
    "OMG": "oh my god",
    "WTF": "what the heck",
    "BRB": "be right back",
    "AFK": "away from keyboard",
    "DIY": "do it yourself",
    "PSA": "public service announcement",
    "FYI": "for your information",
    "ASAP": "as soon as possible",
    "DM": "direct message",
    "PM": "private message",
    "NSFW": "not safe for work",
    "POV": "point of view",
    "JK": "just kidding",
    "ICYMI": "in case you missed it",
    "TBA": "to be announced",
    "TBD": "to be decided",
    "LPT": "life pro tip",
    "YMMV": "your mileage may vary",
    "IANAL": "I am not a lawyer",
    "DAE": "does anyone else",
    "MRW": "my reaction when",
    "MFW": "my face when",
    "CMV": "change my view",
    "OOTL": "out of the loop",
    "HMB": "hold my beer",
    "WIP": "work in progress",
    "FTFY": "fixed that for you",
    "FIFY": "fixed it for you",
    "INB4": "in before",
    "RIP": "rest in peace",
    "QOL": "quality of life",
    "BTW": "by the way",
    "AKA": "also known as",
    "ATM": "at the moment",
    "ETC": "et cetera",
    "FAQ": "frequently asked questions",
    "Q&A": "questions and answers",
}

_ABBR_RE = re.compile(
    r"(?<![A-Za-z0-9])(" + "|".join(re.escape(k) for k in sorted(ABBREVIATIONS, key=len, reverse=True)) + r")(?![A-Za-z0-9])"
)


@dataclass
class Story:
    title: str
    body: str
    source: str = ""        # where it came from, for logs

    @property
    def label(self) -> str:
        return self.title.strip() or (self.body.strip()[:40] + "...") or "untitled"

    def is_empty(self) -> bool:
        return not (self.title.strip() or self.body.strip())


# ------------------------------------------------------------------ cleaning

def expand_abbreviations(text: str) -> str:
    return _ABBR_RE.sub(lambda m: ABBREVIATIONS[m.group(1)], text)


_WS_RE = re.compile(r"[ \t\r\f\v]+")
_NL_RE = re.compile(r"\n\s*\n+")
_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_MD_RE = re.compile(r"[*_`~>#]+")


def clean_text(text: str, strip_markdown: bool = True) -> str:
    """Normalise a story for speech: unicode normalised, urls and markdown
    decorations dropped, paragraphs joined into sentences, whitespace collapsed."""
    text = unicodedata.normalize("NFKC", text or "")
    text = "".join(ch for ch in text if ch == "\n" or unicodedata.category(ch)[0] != "C")
    text = _URL_RE.sub("", text)
    if strip_markdown:
        text = _MD_RE.sub("", text)
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    paragraphs = [_WS_RE.sub(" ", p).strip() for p in _NL_RE.split(text.replace("\r", ""))]
    paragraphs = [p.replace("\n", " ") for p in paragraphs if p]
    # Make sure every paragraph ends a sentence so the voice pauses.
    fixed = []
    for p in paragraphs:
        p = _WS_RE.sub(" ", p).strip()
        if p and p[-1] not in ".!?\"')":
            p += "."
        fixed.append(p)
    return " ".join(fixed)


def prepare_speech(text: str, expand: bool = True) -> str:
    text = clean_text(text)
    return expand_abbreviations(text) if expand else text


_WORD_SPLIT_RE = re.compile(r"\S+")


def split_words(text: str) -> list[str]:
    """Tokens for captions: whitespace separated, punctuation kept attached."""
    return _WORD_SPLIT_RE.findall(text or "")


_NORM_RE = re.compile(r"[^0-9a-z]+")


def normalize_token(word: str) -> str:
    """Lower-case letters and digits only: used to match script words against
    what the voice engine or whisper reports."""
    return _NORM_RE.sub("", unicodedata.normalize("NFKD", word).lower())


# ------------------------------------------------------------------- parsing

_STORY_SEP_RE = re.compile(r"^[ \t]*(?:-{3,}|={3,}|\*{3,})[ \t]*$", re.MULTILINE)


def _legacy_line(line: str) -> tuple[str, str] | None:
    """`Title -- Story` (the format of the original app's batch files)."""
    if "--" not in line:
        return None
    title, body = line.split("--", 1)
    title, body = title.strip(" -\t"), body.strip(" -\t")
    return (title, body) if title and body else None


def parse_stories(text: str, source: str = "") -> list[Story]:
    """Turn the contents of a text file into stories (see the module docstring)."""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿")
    lines = [ln for ln in text.split("\n") if ln.strip()]
    legacy = [_legacy_line(ln) for ln in lines]
    if lines and all(legacy):
        return [Story(t, b, source) for t, b in legacy]  # type: ignore[misc]
    stories = []
    for chunk in _STORY_SEP_RE.split(text):
        chunk = (chunk or "").strip()
        if not chunk:
            continue
        parts = chunk.split("\n", 1)
        title = parts[0].strip()
        body = parts[1].strip() if len(parts) > 1 else ""
        if not body:
            # One block of text: the first sentence becomes the title.
            body = title
            title = first_sentence(body)
        stories.append(Story(title, body, source))
    return stories


def first_sentence(text: str, limit: int = 90) -> str:
    text = _WS_RE.sub(" ", (text or "").strip())
    m = re.search(r"[.!?](\s|$)", text)
    sent = text[: m.end()].strip() if m else text
    if len(sent) > limit:
        cut = sent[:limit].rfind(" ")
        sent = sent[: cut if cut > 20 else limit].rstrip(",;:") + "..."
    return sent


def load_stories(path: str) -> list[Story]:
    """A .txt file, or a folder of .txt files (sorted by name)."""
    if os.path.isdir(path):
        out: list[Story] = []
        for name in sorted(os.listdir(path)):
            if os.path.splitext(name)[1].lower() in TEXT_EXTENSIONS:
                out.extend(load_stories(os.path.join(path, name)))
        return out
    with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
        return parse_stories(fh.read(), source=path)


# ---------------------------------------------------------------- filenames

_UNSAFE_RE = re.compile(r"[^A-Za-z0-9 _\-]+")


def safe_filename(title: str, limit: int = 60, fallback: str = "story") -> str:
    name = unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode()
    name = _UNSAFE_RE.sub("", name)
    name = _WS_RE.sub(" ", name).strip(" .-_")
    if len(name) > limit:
        cut = name[:limit].rfind(" ")
        name = name[: cut if cut > 10 else limit].strip()
    return name or fallback
