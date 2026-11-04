"""Inline SVG icons (simple 24x24 line icons) rendered to tinted QIcons.

Keeping them as strings means no asset files to ship and any colour at any
DPI.  Paths are hand-drawn, stroke based, in the Feather style.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_SVG = {
    "folder": '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>',
    "trash": '<path d="M3 6h18"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>',
    "play": '<path d="M6 4l14 8-14 8z"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    "music": '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
    "film": '<rect x="2" y="2" width="20" height="20" rx="2.2"/><path d="M7 2v20"/><path d="M17 2v20"/><path d="M2 12h20"/><path d="M2 7h5"/><path d="M2 17h5"/><path d="M17 17h5"/><path d="M17 7h5"/>',
    "refresh": '<path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10"/><path d="M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>',
    "open": '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><path d="M15 3h6v6"/><path d="M10 14L21 3"/>',
    "x": '<path d="M18 6L6 18"/><path d="M6 6l12 12"/>',
    "check": '<path d="M20 6L9 17l-5-5"/>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 16l5-5 4 4 3-3 6 6"/><circle cx="16" cy="8" r="1.5"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
    "wand": '<path d="M15 4V2"/><path d="M15 16v-2"/><path d="M8 9h2"/><path d="M20 9h2"/><path d="M17.8 11.8L19 13"/><path d="M15 9h0"/><path d="M17.8 6.2L19 5"/><path d="M3 21l9-9"/><path d="M12.2 6.2L11 5"/>',
    "mic": '<path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><path d="M12 19v4"/><path d="M8 23h8"/>',
    "type": '<path d="M4 7V4h16v3"/><path d="M9 20h6"/><path d="M12 4v16"/>',
    "list": '<path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M3 6h.01"/><path d="M3 12h.01"/><path d="M3 18h.01"/>',
    "captions": '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="M6 15h4"/><path d="M14 15h4"/><path d="M6 11h2"/><path d="M12 11h6"/>',
    "card": '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="8" cy="10" r="1.6"/><path d="M12 10h5"/><path d="M7 15h10"/>',
    "volume": '<path d="M11 5L6 9H2v6h4l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M19 5a9 9 0 0 1 0 14"/>',
    "plus": '<path d="M12 5v14"/><path d="M5 12h14"/>',
    "edit": '<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4z"/>',
    "sparkle": '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 17l.7 2.3L22 20l-2.3.7L19 23l-.7-2.3L16 20l2.3-.7z"/>',
}

_TEMPLATE = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="{fill}" '
             'stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')

_cache: dict[tuple, QIcon] = {}


def svg_bytes(name: str, color: str = "#ffffff", filled: bool = False) -> bytes:
    body = _SVG[name]
    return _TEMPLATE.format(body=body, color=color, fill=color if filled else "none").encode()


def pixmap(name: str, size: int = 20, color: str = "#ffffff", filled: bool = False, dpr: float = 1.0) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(svg_bytes(name, color, filled)))
    px_size = int(size * dpr)
    img = QImage(px_size, px_size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p, QRectF(0, 0, px_size, px_size))
    p.end()
    pm = QPixmap.fromImage(img)
    pm.setDevicePixelRatio(dpr)
    return pm


def icon(name: str, color: str = "#ffffff", filled: bool = False) -> QIcon:
    key = (name, color, filled)
    if key not in _cache:
        ic = QIcon()
        for size in (16, 20, 24, 32, 48):
            for dpr in (1.0, 2.0):
                ic.addPixmap(pixmap(name, size, color, filled, dpr))
        _cache[key] = ic
    return _cache[key]


def names() -> list[str]:
    return sorted(_SVG)


def tinted(color: QColor | str) -> str:
    return color.name() if isinstance(color, QColor) else color


ICON_SIZE = QSize(18, 18)
