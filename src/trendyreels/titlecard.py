"""The story card shown while the title is read: a rounded white card with an
avatar, the channel name and the title, drawn with Pillow (no image assets)."""

from __future__ import annotations

from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter

from .captions import load_font, wrap_words, _text_width
from . import fonts as fontlib

AVATAR_COLORS = [(99, 102, 241), (14, 165, 233), (236, 72, 153), (34, 197, 94), (249, 115, 22), (168, 85, 247)]


def _avatar(size: int, letter: str, seed: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c0 = AVATAR_COLORS[seed % len(AVATAR_COLORS)]
    c1 = AVATAR_COLORS[(seed + 2) % len(AVATAR_COLORS)]
    # Simple diagonal gradient inside a circle.
    grad = Image.new("RGBA", (size, size))
    gd = ImageDraw.Draw(grad)
    for y in range(size):
        t = y / max(1, size - 1)
        col = tuple(int(c0[i] + (c1[i] - c0[i]) * t) for i in range(3))
        gd.line((0, y, size, y), fill=(*col, 255))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    img.paste(grad, (0, 0), mask)
    font = load_font(fontlib.default_font(), int(size * 0.52))
    w = _text_width(font, letter)
    bbox = font.getbbox(letter)
    h = bbox[3] - bbox[1]
    d.text(((size - w) / 2, (size - h) / 2 - bbox[1]), letter, font=font, fill=(255, 255, 255, 255))
    return img


@lru_cache(maxsize=16)
def render_title_card(title: str, channel: str, width: int, font_path: str = "", scale: float = 1.0) -> Image.Image:
    """RGBA card about `width * 0.86` wide.  `scale` shrinks everything for previews."""
    card_w = int(width * 0.86)
    pad = int(width * 0.045)
    font_path = font_path or fontlib.default_font()
    name_font = load_font(font_path, int(width * 0.036))
    title_font = load_font(font_path, int(width * 0.052))
    small_font = load_font(font_path, int(width * 0.028))
    avatar_px = int(width * 0.085)
    inner_w = card_w - 2 * pad

    words = title.split()
    lines = wrap_words(words, title_font, inner_w, _text_width(title_font, " ")) if words else [[]]
    asc, desc = title_font.getmetrics()
    line_h = int((asc + desc) * 1.12)
    header_h = avatar_px
    text_h = line_h * len(lines)
    footer_h = int(width * 0.05)
    card_h = pad + header_h + int(pad * 0.7) + text_h + int(pad * 0.6) + footer_h + pad

    shadow_pad = int(width * 0.03)
    img = Image.new("RGBA", (card_w + 2 * shadow_pad, card_h + 2 * shadow_pad), (0, 0, 0, 0))
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        (shadow_pad, shadow_pad + int(width * 0.012), shadow_pad + card_w, shadow_pad + card_h + int(width * 0.012)),
        radius=int(width * 0.035), fill=(0, 0, 0, 120))
    shadow = shadow.filter(ImageFilter.GaussianBlur(int(width * 0.015)))
    img = Image.alpha_composite(img, shadow)
    d = ImageDraw.Draw(img)
    ox, oy = shadow_pad, shadow_pad
    d.rounded_rectangle((ox, oy, ox + card_w, oy + card_h), radius=int(width * 0.035), fill=(255, 255, 255, 255))

    # Header: avatar + channel name + a small "verified" tick.
    letter = (channel.strip()[:1] or "T").upper()
    avatar = _avatar(avatar_px, letter, sum(map(ord, channel)) if channel else 0)
    img.paste(avatar, (ox + pad, oy + pad), avatar)
    name_y = oy + pad + (avatar_px - (name_font.getmetrics()[0] + name_font.getmetrics()[1])) // 2
    name_x = ox + pad + avatar_px + int(pad * 0.5)
    d.text((name_x, name_y), channel or "Your Channel", font=name_font, fill=(20, 22, 30, 255))
    tick_x = name_x + _text_width(name_font, channel or "Your Channel") + int(width * 0.015)
    tick_r = int(width * 0.014)
    tick_cy = name_y + (name_font.getmetrics()[0] + name_font.getmetrics()[1]) // 2
    d.ellipse((tick_x, tick_cy - tick_r, tick_x + 2 * tick_r, tick_cy + tick_r), fill=(10, 132, 255, 255))
    d.line((tick_x + tick_r * 0.55, tick_cy, tick_x + tick_r * 0.9, tick_cy + tick_r * 0.4,
            tick_x + tick_r * 1.5, tick_cy - tick_r * 0.45), fill=(255, 255, 255, 255), width=max(1, int(width * 0.004)))
    sub_y = tick_cy + tick_r + int(width * 0.004)
    d.text((name_x, sub_y), "story time", font=small_font, fill=(120, 124, 140, 255))

    # Title
    y = oy + pad + header_h + int(pad * 0.7)
    for line in lines:
        text = " ".join(words[i] for i in line)
        d.text((ox + pad, y), text, font=title_font, fill=(18, 20, 28, 255))
        y += line_h

    # Footer: three soft "reaction" chips, no numbers.
    y = oy + card_h - pad - footer_h
    chip_w = int(width * 0.11)
    chip_h = footer_h
    x = ox + pad
    for k in range(3):
        d.rounded_rectangle((x, y, x + chip_w, y + chip_h), radius=chip_h // 2, fill=(240, 241, 246, 255))
        cx, cy = x + chip_w // 2, y + chip_h // 2
        r = int(chip_h * 0.22)
        col = (90, 94, 110, 255)
        if k == 0:    # up arrow
            d.polygon([(cx, cy - r), (cx + r, cy + r * 0.2), (cx + r * 0.45, cy + r * 0.2), (cx + r * 0.45, cy + r),
                       (cx - r * 0.45, cy + r), (cx - r * 0.45, cy + r * 0.2), (cx - r, cy + r * 0.2)], fill=col)
        elif k == 1:  # speech bubble
            d.rounded_rectangle((cx - r * 1.2, cy - r * 0.9, cx + r * 1.2, cy + r * 0.6), radius=r // 2, fill=col)
            d.polygon([(cx - r * 0.6, cy + r * 0.5), (cx - r * 0.2, cy + r * 1.1), (cx + r * 0.1, cy + r * 0.5)], fill=col)
        else:         # share arrow
            w_ = max(1, int(width * 0.004))
            d.line((cx - r, cy + r * 0.6, cx - r, cy + r, cx + r, cy + r, cx + r, cy + r * 0.6), fill=col, width=w_)
            d.line((cx, cy + r * 0.5, cx, cy - r), fill=col, width=w_)
            d.polygon([(cx - r * 0.7, cy - r * 0.3), (cx, cy - r * 1.1), (cx + r * 0.7, cy - r * 0.3)], fill=col)
        x += chip_w + int(width * 0.02)

    if scale != 1.0:
        img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.Resampling.LANCZOS)
    return img


def card_duration_hint(title: str) -> float:
    """How long a reader needs for the title when it is not read aloud."""
    return max(2.0, min(6.0, 1.0 + 0.35 * len(title.split())))
