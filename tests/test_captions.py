from __future__ import annotations

import numpy as np
from PIL import Image

from trendyreels import fonts
from trendyreels.captions import CaptionStyle, load_font, paste_center, render_caption, wrap_words
from trendyreels.settings import ProjectSettings
from trendyreels.titlecard import card_duration_hint, render_title_card


def style(**kw) -> CaptionStyle:
    base = dict(font_path=fonts.default_font(), font_px=40, max_width=400)
    base.update(kw)
    return CaptionStyle(**base)


def test_wrap_words_respects_width():
    font = load_font(fonts.default_font(), 40)
    lines = wrap_words(["one", "two", "three", "four", "five", "six"], font, 220, font.getlength(" "))
    assert len(lines) >= 2
    assert [i for line in lines for i in line] == list(range(6))


def test_render_caption_sizes_and_highlight():
    plain = render_caption(("hello", "world"), None, style(highlight=False))
    assert plain.mode == "RGBA" and plain.width > 60 and plain.height > 30
    hi = render_caption(("hello", "world"), 1, style())
    assert hi.size[0] >= plain.size[0]          # the active word is drawn a little bigger
    a, b = np.asarray(plain), np.asarray(hi)
    assert a.shape != b.shape or not np.array_equal(a, b)
    # yellow highlight pixels exist only in the highlighted render
    def has_yellow(img):
        arr = np.asarray(img)
        return bool(((arr[:, :, 0] > 200) & (arr[:, :, 1] > 180) & (arr[:, :, 2] < 80) & (arr[:, :, 3] > 200)).any())
    assert has_yellow(hi) and not has_yellow(plain)


def test_render_caption_uppercase_box_and_cache():
    s = style(uppercase=True, box=True, shadow=False)
    img1 = render_caption(("abc",), 0, s)
    img2 = render_caption(("abc",), 0, s)
    assert img1 is img2                           # cached
    arr = np.asarray(img1)
    row = arr[arr.shape[0] // 2]
    assert (row[: arr.shape[1] // 4, 3] > 0).any()   # the box extends past the glyphs into the padding
    no_box = np.asarray(render_caption(("abc",), 0, style(uppercase=True, box=False, shadow=False)))
    assert no_box[no_box.shape[0] // 2, 1, 3] == 0


def test_style_from_settings_scales_with_width():
    s = ProjectSettings(font_size=0.1, outline=0.1)
    st = CaptionStyle.from_settings(s, 1000)
    assert st.font_px == 100 and st.outline_px == 10 and st.max_width == 880


def test_paste_center_clips_at_edges():
    frame = np.zeros((50, 50, 3), dtype=np.uint8)
    overlay = Image.new("RGBA", (30, 30), (255, 0, 0, 255))
    paste_center(frame, overlay, 0, 0)            # mostly off-canvas top-left
    assert frame[0, 0].tolist() == [255, 0, 0]
    assert frame[20, 20].tolist() == [0, 0, 0]
    half = Image.new("RGBA", (10, 10), (0, 255, 0, 128))
    paste_center(frame, half, 40, 40)
    assert 120 <= frame[40, 40, 1] <= 136


def test_title_card_renders_and_wraps():
    short = render_title_card("Hi", "Chan", 540)
    long = render_title_card("A fairly long title that certainly needs to wrap onto several lines", "Chan", 540)
    assert short.mode == "RGBA" and long.height > short.height
    assert abs(short.width - 540 * 0.86) < 540 * 0.1
    half = render_title_card("Hi", "Chan", 540, scale=0.5)
    assert abs(half.width - short.width / 2) <= 1
    assert 2.0 <= card_duration_hint("x") <= card_duration_hint("many many many words in this title") <= 6.0


def test_default_font_is_a_file_or_empty():
    p = fonts.default_font()
    assert p == "" or p.lower().endswith((".ttf", ".otf", ".ttc"))
    assert fonts.display_name("") == "Built-in"
