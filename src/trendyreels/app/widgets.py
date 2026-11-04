"""Reusable pieces: wallpaper backdrop, glass card, pill buttons, segmented
control, labelled slider, file picker row, colour swatch button."""

from __future__ import annotations

import os
import random

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPixmap, QRadialGradient
from PySide6.QtWidgets import (
    QButtonGroup,
    QColorDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from . import icons


# ----------------------------------------------------------------- backdrop

def generate_wallpaper(width: int, height: int, seed: int = 11) -> QPixmap:
    """A soft, dark 'aurora' wallpaper: gradient base plus blurred colour blobs."""
    pm = QPixmap(max(16, width), max(16, height))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    base = QLinearGradient(0, 0, width, height)
    base.setColorAt(0.0, QColor("#1a1230"))
    base.setColorAt(0.5, QColor("#141a33"))
    base.setColorAt(1.0, QColor("#2a0f2b"))
    p.fillRect(pm.rect(), QBrush(base))
    rng = random.Random(seed)
    palette = ["#ec4899", "#a855f7", "#0ea5e9", "#f59e0b", "#4f46e5", "#14b8a6"]
    for i in range(6):
        cx, cy = rng.uniform(0, width), rng.uniform(0, height)
        r = rng.uniform(0.25, 0.55) * max(width, height)
        g = QRadialGradient(cx, cy, r)
        c = QColor(palette[i % len(palette)])
        c.setAlphaF(0.32)
        g.setColorAt(0.0, c)
        c2 = QColor(c)
        c2.setAlphaF(0.0)
        g.setColorAt(1.0, c2)
        p.setBrush(QBrush(g))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(int(cx - r), int(cy - r), int(2 * r), int(2 * r))
    p.end()
    return pm


class Backdrop(QWidget):
    """Paints a wallpaper (user image or generated) scaled to cover; children sit on top."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._source: QPixmap | None = None
        self._scaled: QPixmap | None = None
        self._dim = 0.35
        self.setAutoFillBackground(False)

    def set_image(self, path: str | None) -> bool:
        if path and os.path.isfile(path):
            pm = QPixmap(path)
            if not pm.isNull():
                self._source = pm
                self._scaled = None
                self.update()
                return True
        self._source = None
        self._scaled = None
        self.update()
        return False

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        w, h = self.width(), self.height()
        if self._source is None:
            if self._scaled is None or self._scaled.size() != self.size():
                self._scaled = generate_wallpaper(w, h)
            p.drawPixmap(0, 0, self._scaled)
        else:
            if self._scaled is None or self._scaled.size() != self.size():
                scaled = self._source.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                             Qt.TransformationMode.SmoothTransformation)
                x = (scaled.width() - w) // 2
                y = (scaled.height() - h) // 2
                self._scaled = scaled.copy(x, y, w, h)
            p.drawPixmap(0, 0, self._scaled)
            p.fillRect(self.rect(), QColor(0, 0, 0, int(255 * self._dim)))
        p.end()


# ---------------------------------------------------------------------- card

class GlassCard(QFrame):
    def __init__(self, title: str | None = None, icon_name: str | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(18, 16, 18, 18)
        self.body.setSpacing(12)
        self.head = QHBoxLayout()
        if title:
            self.head.setSpacing(8)
            if icon_name:
                ic = QLabel()
                ic.setPixmap(icons.pixmap(icon_name, 18, "#ffffff", dpr=self.devicePixelRatioF()))
                self.head.addWidget(ic)
            lbl = QLabel(title)
            lbl.setObjectName("CardTitle")
            self.head.addWidget(lbl)
            self.head.addStretch(1)
            self.body.addLayout(self.head)


# ------------------------------------------------------------------- buttons

def pill(text: str, icon_name: str | None = None, kind: str = "", tooltip: str = "") -> QPushButton:
    b = QPushButton(text)
    if icon_name:
        color = "#06230f" if kind == "Go" else "#ffffff"
        b.setIcon(icons.icon(icon_name, color, filled=(icon_name == "play")))
        b.setIconSize(icons.ICON_SIZE)
    if kind:
        b.setObjectName(kind)
    if tooltip:
        b.setToolTip(tooltip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def round_button(icon_name: str, tooltip: str = "") -> QPushButton:
    b = QPushButton()
    b.setObjectName("Round")
    b.setIcon(icons.icon(icon_name))
    b.setIconSize(QSize(18, 18))
    b.setToolTip(tooltip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("Hint")
    lbl.setWordWrap(True)
    return lbl


class Segmented(QFrame):
    """iOS segmented control.  `changed(str)` emits the selected key."""

    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SegGroup")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        for key, label in options:
            b = QPushButton(label)
            b.setObjectName("Seg")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self.group.addButton(b)
            lay.addWidget(b)
            self._buttons[key] = b
            b.toggled.connect(lambda on, k=key: on and self.changed.emit(k))

    def set_value(self, key: str) -> None:
        if key in self._buttons:
            self._buttons[key].setChecked(True)

    def value(self) -> str:
        for k, b in self._buttons.items():
            if b.isChecked():
                return k
        return next(iter(self._buttons))


class LabeledSlider(QWidget):
    """Slider with a caption and a live value label.  Works in float units."""

    valueChanged = Signal(float)

    def __init__(self, caption: str, lo: float, hi: float, step: float, fmt: str = "{:.1f}",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.lo, self.step, self.fmt = lo, step, fmt
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        top = QHBoxLayout()
        self.caption = QLabel(caption)
        self.caption.setObjectName("Hint")
        self.value_lbl = QLabel()
        self.value_lbl.setObjectName("Hint")
        top.addWidget(self.caption)
        top.addStretch(1)
        top.addWidget(self.value_lbl)
        lay.addLayout(top)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, int(round((hi - lo) / step)))
        self.slider.valueChanged.connect(self._on_change)
        lay.addWidget(self.slider)

    def _on_change(self, raw: int) -> None:
        v = self.value()
        self.value_lbl.setText(self.fmt.format(v))
        self.valueChanged.emit(v)

    def value(self) -> float:
        return self.lo + self.slider.value() * self.step

    def set_value(self, v: float) -> None:
        self.slider.setValue(int(round((v - self.lo) / self.step)))
        self.value_lbl.setText(self.fmt.format(self.value()))


class FilePicker(QWidget):
    """[icon] caption / filename ........ (Choose) (x)"""

    changed = Signal(str)

    def __init__(self, caption: str, icon_name: str, mode: str = "file", filter_: str = "",
                 placeholder: str = "None", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.mode, self.filter_, self.placeholder = mode, filter_, placeholder
        self._path = ""
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(icon_name, 18, "#ffffff", dpr=self.devicePixelRatioF()))
        lay.addWidget(ic)
        text = QVBoxLayout()
        text.setSpacing(0)
        self.cap = QLabel(caption)
        self.cap.setObjectName("Hint")
        self.name = QLabel(placeholder)
        self.name.setObjectName("Faint")
        self.name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        text.addWidget(self.cap)
        text.addWidget(self.name)
        lay.addLayout(text, 1)
        self.choose = pill("Choose")
        self.clear_btn = round_button("x", "Clear")
        self.clear_btn.setVisible(False)
        lay.addWidget(self.choose)
        lay.addWidget(self.clear_btn)
        self.choose.clicked.connect(self._pick)
        self.clear_btn.clicked.connect(lambda: self.set_path(""))

    def _pick(self) -> None:
        start = os.path.dirname(self._path) if self._path else os.path.expanduser("~")
        if self.mode == "dir":
            path = QFileDialog.getExistingDirectory(self, self.cap.text(), start)
        else:
            path, _ = QFileDialog.getOpenFileName(self, self.cap.text(), start, self.filter_)
        if path:
            self.set_path(os.path.normpath(path))

    def set_path(self, path: str) -> None:
        self._path = path or ""
        if self._path:
            self.name.setText(os.path.basename(self._path) or self._path)
            self.name.setObjectName("Hint")
            self.name.setToolTip(self._path)
        else:
            self.name.setText(self.placeholder)
            self.name.setObjectName("Faint")
            self.name.setToolTip("")
        self.name.style().unpolish(self.name)
        self.name.style().polish(self.name)
        self.clear_btn.setVisible(bool(self._path))
        self.changed.emit(self._path)

    def path(self) -> str:
        return self._path


class ColorButton(QPushButton):
    """A small swatch that opens a colour dialog.  `changed(tuple)` emits (r, g, b)."""

    changed = Signal(tuple)

    def __init__(self, caption: str, parent: QWidget | None = None) -> None:
        super().__init__(caption, parent)
        self.setObjectName("Swatch")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rgb = (255, 255, 255)
        self.caption = caption
        self.clicked.connect(self._pick)
        self.set_rgb(self._rgb)

    def set_rgb(self, rgb) -> None:
        self._rgb = tuple(int(c) for c in rgb)
        r, g, b = self._rgb
        text = "#06070c" if (0.299 * r + 0.587 * g + 0.114 * b) > 140 else "#ffffff"
        self.setStyleSheet(f"QPushButton#Swatch {{ background: rgb({r},{g},{b}); color: {text}; border: 1px solid rgba(255,255,255,0.35); }}")

    def rgb(self) -> tuple[int, int, int]:
        return self._rgb

    def _pick(self) -> None:
        c = QColorDialog.getColor(QColor(*self._rgb), self, self.caption)
        if c.isValid():
            self.set_rgb((c.red(), c.green(), c.blue()))
            self.changed.emit(self._rgb)
