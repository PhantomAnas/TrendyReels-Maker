"""Caption rendering with Pillow: a few words at a time, the spoken word
highlighted, thick outline, optional shadow and backing box.  Rendered images
are cached, so a 30 fps render only draws a caption when it changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import fonts as fontlib
from .settings import ProjectSettings

RGB = tuple[int, int, int]


@dataclass(frozen=True)
class CaptionStyle:
    font_path: str
    font_px: int
    max_width: int
    text_color: RGB = (255, 255, 255)
    highlight: bool = True
    highlight_color: RGB = (255, 214, 10)
    highlight_scale: float = 1.12
    outline_color: RGB = (0, 0, 0)
    outline_px: int = 6
    shadow: bool = True
    box: bool = False
    box_color: RGB = (0, 0, 0)
    box_opacity: float = 0.55
    uppercase: bool = True
    line_spacing: float = 1.15

    @classmethod
    def from_settings(cls, s: ProjectSettings, width: int) -> "CaptionStyle":
        font_px = max(8, int(round(width * s.font_size)))
        return cls(
            font_path=s.font_path or fontlib.default_font(),
            font_px=font_px,
            max_width=max(32, int(width * s.caption_width)),
            text_color=tuple(s.text_color), highlight=s.highlight, highlight_color=tuple(s.highlight_color),
            highlight_scale=s.highlight_scale, outline_color=tuple(s.outline_color),
            outline_px=int(round(font_px * s.outline)), shadow=s.shadow, box=s.box, box_color=tuple(s.box_color),
            box_opacity=s.box_opacity, uppercase=s.uppercase,
        )


@lru_cache(maxsize=64)
def load_font(path: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    size = max(4, int(size))
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def _text_width(font, text: str) -> float:
    try:
        return font.getlength(text)
    except AttributeError:
        return font.getbbox(text)[2]


def _font_height(font) -> int:
    try:
        asc, desc = font.getmetrics()
        return asc + desc
    except AttributeError:
        return font.getbbox("Hg")[3]


def wrap_words(words: list[str], font, max_width: int, space: float) -> list[list[int]]:
    """Indices of the words on each line, wrapped to `max_width`."""
    lines: list[list[int]] = []
    cur: list[int] = []
    cur_w = 0.0
    for i, w in enumerate(words):
        ww = _text_width(font, w)
        if cur and cur_w + space + ww > max_width:
            lines.append(cur)
            cur, cur_w = [i], ww
        else:
            cur_w = ww if not cur else cur_w + space + ww
            cur.append(i)
    if cur:
        lines.append(cur)
    return lines


@lru_cache(maxsize=256)
def render_caption(words: tuple[str, ...], active: int | None, style: CaptionStyle) -> Image.Image:
    """An RGBA image of the caption, tightly cropped with room for the outline."""
    if style.uppercase:
        words = tuple(w.upper() for w in words)
    font = load_font(style.font_path, style.font_px)
    big = load_font(style.font_path, int(round(style.font_px * style.highlight_scale))) if style.highlight and active is not None else font
    space = _text_width(font, " ")
    lines = wrap_words(list(words), font, style.max_width, space)
    line_h = int(_font_height(font) * style.line_spacing)
    pad = style.outline_px + (6 if style.shadow else 2) + int(style.font_px * 0.25)
    widths = []
    for line in lines:
        w = 0.0
        for n, i in enumerate(line):
            f = big if i == active else font
            w += _text_width(f, words[i]) + (space if n else 0)
        widths.append(w)
    width = int(max(widths) if widths else 1) + 2 * pad
    height = line_h * max(1, len(lines)) + 2 * pad
    img = Image.new("RGBA", (max(1, width), max(1, height)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if style.box:
        alpha = int(255 * max(0.0, min(1.0, style.box_opacity)))
        r = max(6, style.font_px // 3)
        draw.rounded_rectangle((pad // 2, pad // 2, width - pad // 2, height - pad // 2), radius=r,
                               fill=(*style.box_color, alpha))
    if style.shadow:
        shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow)
        _draw_lines(sd, lines, words, active, font, big, space, widths, width, pad, line_h,
                    fill=(0, 0, 0, 170), outline=(0, 0, 0, 170), outline_px=style.outline_px,
                    offset=(int(style.font_px * 0.06), int(style.font_px * 0.08)))
        shadow = shadow.filter(ImageFilter.GaussianBlur(max(1, style.font_px // 14)))
        img = Image.alpha_composite(img, shadow)
        draw = ImageDraw.Draw(img)
    _draw_lines(draw, lines, words, active, font, big, space, widths, width, pad, line_h,
                fill=(*style.text_color, 255), outline=(*style.outline_color, 255), outline_px=style.outline_px,
                highlight=(*style.highlight_color, 255) if style.highlight else None)
    return img


def _draw_lines(draw, lines, words, active, font, big, space, widths, width, pad, line_h, fill, outline, outline_px,
                offset=(0, 0), highlight=None) -> None:
    base_h = _font_height(font)
    for row, line in enumerate(lines):
        x = (width - widths[row]) / 2 + offset[0]
        y = pad + row * line_h + offset[1]
        for n, i in enumerate(line):
            if n:
                x += space
            is_active = i == active
            f = big if is_active else font
            dy = (base_h - _font_height(f)) / 2 if is_active else 0
            color = highlight if (is_active and highlight) else fill
            draw.text((x, y + dy), words[i], font=f, fill=color, stroke_width=outline_px, stroke_fill=outline)
            x += _text_width(f, words[i])


def paste_center(frame: np.ndarray, overlay: Image.Image, cx: int, cy: int) -> np.ndarray:
    """Alpha-composite `overlay` onto an RGB frame (H, W, 3) centred at (cx, cy), in place."""
    h, w = frame.shape[:2]
    ow, oh = overlay.size
    x0, y0 = int(cx - ow / 2), int(cy - oh / 2)
    sx0, sy0 = max(0, -x0), max(0, -y0)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x0 + ow - sx0), min(h, y0 + oh - sy0)
    if x1 <= x0 or y1 <= y0:
        return frame
    region = np.asarray(overlay, dtype=np.float32)[sy0: sy0 + (y1 - y0), sx0: sx0 + (x1 - x0)]
    alpha = region[:, :, 3:4] / 255.0
    dst = frame[y0:y1, x0:x1].astype(np.float32)
    frame[y0:y1, x0:x1] = (region[:, :, :3] * alpha + dst * (1.0 - alpha)).astype(np.uint8)
    return frame
