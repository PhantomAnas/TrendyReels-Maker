"""Generate the app icon (PNG + ICO) with Qt only:  python scripts/make_icon.py"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath, QPen  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "trendyreels", "assets")


def draw(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size
    tile = QPainterPath()
    tile.addRoundedRect(QRectF(0, 0, s, s), s * 0.22, s * 0.22)
    g = QLinearGradient(0, 0, s, s)
    g.setColorAt(0, QColor("#ec4899"))
    g.setColorAt(1, QColor("#7c3aed"))
    p.fillPath(tile, g)
    # A phone-shaped frame
    phone = QPainterPath()
    phone.addRoundedRect(QRectF(s * 0.30, s * 0.14, s * 0.40, s * 0.72), s * 0.07, s * 0.07)
    p.setPen(QPen(QColor(255, 255, 255, 230), max(1.0, s * 0.035)))
    p.setBrush(QColor(255, 255, 255, 40))
    p.drawPath(phone)
    # Caption bars: a highlighted word and two white ones
    p.setPen(Qt.PenStyle.NoPen)
    bars = [(0.36, 0.44, 0.16, QColor("#ffd60a")), (0.54, 0.44, 0.10, QColor("white")), (0.36, 0.53, 0.28, QColor("white"))]
    for x, y, w, c in bars:
        bar = QPainterPath()
        bar.addRoundedRect(QRectF(s * x, s * y, s * w, s * 0.06), s * 0.03, s * 0.03)
        p.fillPath(bar, c)
    # Play triangle at the top of the screen
    tri = QPainterPath()
    tri.moveTo(QPointF(s * 0.45, s * 0.22))
    tri.lineTo(QPointF(s * 0.58, s * 0.30))
    tri.lineTo(QPointF(s * 0.45, s * 0.38))
    tri.closeSubpath()
    p.fillPath(tri, QColor(255, 255, 255, 235))
    p.end()
    return img


def main() -> None:
    QGuiApplication(sys.argv)
    os.makedirs(OUT, exist_ok=True)
    draw(256).save(os.path.join(OUT, "icon.png"))
    draw(256).save(os.path.join(OUT, "icon.ico"), "ICO")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
