"""Finding fonts for captions: the system font folders plus any .ttf/.otf the user picks."""

from __future__ import annotations

import os
import sys
from functools import lru_cache

FONT_EXTENSIONS = {".ttf", ".otf", ".ttc"}

# Bold, punchy faces that work for captions, in order of preference.
PREFERRED = (
    "Montserrat-ExtraBold", "Montserrat-Black", "Montserrat-Bold", "Poppins-ExtraBold", "Poppins-Bold",
    "Bangers-Regular", "Impact", "arialbd", "Arial Bold", "segoeuib", "seguisb", "Roboto-Black", "Roboto-Bold",
    "calibrib", "verdanab", "bahnschrift", "DejaVuSans-Bold", "LiberationSans-Bold", "Helvetica-Bold",
)


def system_font_dirs() -> list[str]:
    dirs: list[str] = []
    if sys.platform == "win32":
        win = os.environ.get("WINDIR", r"C:\Windows")
        dirs.append(os.path.join(win, "Fonts"))
        local = os.environ.get("LOCALAPPDATA")
        if local:
            dirs.append(os.path.join(local, "Microsoft", "Windows", "Fonts"))
    elif sys.platform == "darwin":
        dirs += ["/System/Library/Fonts", "/Library/Fonts", os.path.expanduser("~/Library/Fonts")]
    else:
        dirs += ["/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.fonts"),
                 os.path.expanduser("~/.local/share/fonts")]
    return [d for d in dirs if os.path.isdir(d)]


@lru_cache(maxsize=1)
def list_fonts() -> list[tuple[str, str]]:
    """[(display name, path)] of every font file found, sorted by name."""
    found: dict[str, str] = {}
    for d in system_font_dirs():
        for root, _dirs, files in os.walk(d):
            for name in files:
                stem, ext = os.path.splitext(name)
                if ext.lower() in FONT_EXTENSIONS and stem not in found:
                    found[stem] = os.path.join(root, name)
    return sorted(found.items(), key=lambda kv: kv[0].lower())


def default_font() -> str:
    """The best caption font available on this machine ('' = Pillow's built-in)."""
    by_stem = {stem.lower(): path for stem, path in list_fonts()}
    for want in PREFERRED:
        p = by_stem.get(want.lower())
        if p:
            return p
    for stem, path in list_fonts():
        if "bold" in stem.lower() or "black" in stem.lower():
            return path
    return ""


def display_name(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0] if path else "Built-in"
