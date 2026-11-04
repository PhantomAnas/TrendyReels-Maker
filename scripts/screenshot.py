"""Render the main window with the sample story and save docs/screenshot.png.

    python scripts/screenshot.py

Uses a throw-away settings file so the real user config is untouched.  On
Windows the real platform is used (offscreen has no system fonts), so the
window appears for a moment.
"""

from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
if sys.platform != "win32":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import trendyreels.settings as settings_mod  # noqa: E402

tmp = tempfile.mkdtemp(prefix="trendyreels-shot-")
settings_mod.config_path = lambda: os.path.join(tmp, "settings.json")  # type: ignore[assignment]
settings_mod.cache_dir = lambda: os.path.join(tmp, "cache")  # type: ignore[assignment]

import make_samples  # noqa: E402

make_samples.main(tmp)

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from trendyreels.app.main_window import MainWindow  # noqa: E402
from trendyreels.app.theme import STYLESHEET  # noqa: E402
from trendyreels.batch import SAMPLE_STORY  # noqa: E402
from trendyreels.text import Story  # noqa: E402

app = QApplication(sys.argv)
app.setStyleSheet(STYLESHEET)
s = settings_mod.ProjectSettings(background=os.path.join(tmp, "footage"), output_folder=os.path.join(tmp, "out"),
                                 channel_name="Story Time", background_pick="sequential", random_start=False)
s.extra["editor_title"] = SAMPLE_STORY.title
s.extra["editor_body"] = SAMPLE_STORY.body
s.extra["queue"] = [{"title": "I accidentally became the office plant whisperer", "body": "Nobody told me the plants were dying.", "source": ""}]
win = MainWindow(s)
win.resize(1440, 900)
win.scrub.setValue(260)
win._log("ready: sample story, Edge TTS, Pop captions, abstract footage")
win.show()


def shoot() -> None:
    out = os.path.join(ROOT, "docs", "screenshot.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    win.grab().save(out)
    print("wrote", out)
    app.quit()


QTimer.singleShot(3500, shoot)   # let the preview frame arrive
app.exec()
