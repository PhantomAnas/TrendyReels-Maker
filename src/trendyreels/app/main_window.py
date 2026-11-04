"""The TrendyReels Maker window."""

from __future__ import annotations

import ctypes
import os
import sys

from .. import __version__
from ..settings import APP_NAME, ASPECT_PRESETS, ProjectSettings
from ..settings import cache_dir as settings_cache_dir


def enable_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    for attempt in (
        lambda: ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)),
        lambda: ctypes.windll.shcore.SetProcessDpiAwareness(2),
        lambda: ctypes.windll.user32.SetProcessDPIAware(),
    ):
        try:
            attempt()
            return
        except Exception:  # noqa: BLE001
            continue


enable_dpi_awareness()

from PySide6.QtCore import QThread, QThreadPool, QTimer, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QDesktopServices, QFont, QIcon, QPixmap  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import ffmpeg as ff  # noqa: E402
from .. import fonts as fontlib  # noqa: E402
from ..background import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS, list_videos  # noqa: E402
from ..batch import SAMPLE_STORY  # noqa: E402
from ..text import TEXT_EXTENSIONS, Story, load_stories  # noqa: E402
from ..timing import whisper_available  # noqa: E402
from ..tts import EDGE_VOICES, ELEVENLABS_KEY_ENV, ELEVENLABS_VOICES  # noqa: E402
from . import icons  # noqa: E402
from .theme import STYLESHEET  # noqa: E402
from .widgets import Backdrop, ColorButton, FilePicker, GlassCard, LabeledSlider, Segmented, hint, pill, round_button  # noqa: E402
from .worker import (PreviewJob, PreviewSignals, RenderWorker, VoiceListJob, VoiceListSignals, VoiceTestJob,  # noqa: E402
                     VoiceTestSignals)

VIDEO_FILTER = "Videos (" + " ".join(f"*{e}" for e in sorted(VIDEO_EXTENSIONS)) + ")"
AUDIO_FILTER = "Audio (" + " ".join(f"*{e}" for e in sorted(AUDIO_EXTENSIONS)) + ")"
FONT_FILTER = "Fonts (*.ttf *.otf *.ttc)"
TEXT_FILTER = "Text (*.txt *.md);;All files (*)"

# One-click caption looks.  Each sets the colour/shape fields of the settings.
STYLE_PRESETS: dict[str, dict] = {
    "pop": dict(uppercase=True, highlight=True, highlight_color=(255, 214, 10), text_color=(255, 255, 255),
                outline_color=(0, 0, 0), outline=0.10, shadow=True, box=False, font_size=0.075, words_per_caption=3),
    "clean": dict(uppercase=False, highlight=False, text_color=(255, 255, 255), outline_color=(0, 0, 0), outline=0.06,
                  shadow=True, box=False, font_size=0.058, words_per_caption=4),
    "boxed": dict(uppercase=True, highlight=True, highlight_color=(255, 214, 10), text_color=(255, 255, 255),
                  outline=0.0, shadow=False, box=True, box_color=(0, 0, 0), box_opacity=0.65, font_size=0.065, words_per_caption=3),
    "neon": dict(uppercase=True, highlight=True, highlight_color=(57, 255, 20), text_color=(255, 255, 255),
                 outline_color=(120, 0, 200), outline=0.12, shadow=True, box=False, font_size=0.08, words_per_caption=2),
}


def resource_path(name: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets"))
    return os.path.join(base, name)


def app_icon() -> QIcon:
    for name in ("icon.ico", "icon.png"):
        p = resource_path(name)
        if os.path.exists(p):
            return QIcon(p)
    return icons.icon("sparkle")


def fmt_seconds(s: float) -> str:
    m, sec = divmod(int(round(s)), 60)
    return f"{m}:{sec:02d}" if m else f"{sec}s"


class MainWindow(QMainWindow):
    def __init__(self, settings: ProjectSettings) -> None:
        super().__init__()
        self.s = settings
        self.setWindowTitle("TrendyReels Maker")
        self.setWindowIcon(app_icon())
        self.resize(1400, 880)
        self.setMinimumSize(1120, 700)
        self._loading = True
        self._preview_id = 0
        self._preview_total = 0.0
        self._outputs: list[str] = []
        self._voices: dict[str, list[tuple[str, str]]] = {"edge": list(EDGE_VOICES), "elevenlabs": list(ELEVENLABS_VOICES)}
        self._preview_signals = PreviewSignals()
        self._preview_signals.ready.connect(self._preview_ready)
        self._preview_signals.failed.connect(self._preview_failed)
        self._voice_signals = VoiceListSignals()
        self._voice_signals.ready.connect(self._voices_ready)
        self._voice_signals.failed.connect(self._voices_failed)
        self._test_signals = VoiceTestSignals()
        self._test_signals.ready.connect(self._voice_test_ready)
        self._test_signals.failed.connect(self._voice_test_failed)
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(220)
        self._preview_timer.timeout.connect(self._request_preview)

        self.backdrop = Backdrop()
        self.setCentralWidget(self.backdrop)
        self.setAcceptDrops(True)
        self.backdrop.set_image(self.s.extra.get("wallpaper"))
        self._build()
        self._build_worker()
        self._apply_settings()
        self._loading = False
        self._refresh_queue_label()
        self._check_ffmpeg()
        self._settings_edited()
        if os.path.isfile(os.path.join(settings_cache_dir(), "edge_voices.json")):
            QThreadPool.globalInstance().start(VoiceListJob("edge", self.s, self._voice_signals, refresh=False))

    # ------------------------------------------------------------- layout
    def _build(self) -> None:
        root = QHBoxLayout(self.backdrop)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(18)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        col = QWidget()
        left = QVBoxLayout(col)
        left.setContentsMargins(0, 0, 8, 0)
        left.setSpacing(14)
        scroll.setWidget(col)
        root.addWidget(scroll, 5)

        header = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(icons.pixmap("sparkle", 28, "#ffffff", dpr=self.devicePixelRatioF()))
        title = QLabel("TrendyReels Maker")
        title.setObjectName("Title")
        header.addWidget(logo)
        header.addSpacing(6)
        header.addWidget(title)
        header.addStretch(1)
        self.wallpaper_btn = round_button("settings", "Change wallpaper")
        self.wallpaper_btn.clicked.connect(self._pick_wallpaper)
        header.addWidget(self.wallpaper_btn)
        left.addLayout(header)

        left.addWidget(self._story_card())
        left.addWidget(self._queue_card())
        left.addWidget(self._voice_card())
        left.addWidget(self._captions_card())
        left.addWidget(self._title_card())
        left.addWidget(self._background_card())
        left.addWidget(self._output_card())
        left.addStretch(1)

        right = QVBoxLayout()
        right.setSpacing(14)
        right.addWidget(self._preview_card(), 1)
        right.addWidget(self._render_card())
        root.addLayout(right, 4)

    def _story_card(self) -> GlassCard:
        card = GlassCard("Story", "type")
        self.sample_btn = pill("Try the sample", "sparkle", tooltip="Fill in a short demo story")
        card.head.addWidget(self.sample_btn)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Title (read first, shown on the story card)")
        card.body.addWidget(self.title_edit)
        self.body_edit = QPlainTextEdit()
        self.body_edit.setObjectName("Editor")
        self.body_edit.setPlaceholderText("Paste or type the story here. Paragraphs become pauses. "
                                          "Shorthand like AITA or TL;DR is read out in full.")
        self.body_edit.setMinimumHeight(150)
        card.body.addWidget(self.body_edit)
        row = QHBoxLayout()
        self.story_stats = hint("")
        row.addWidget(self.story_stats, 1)
        self.import_btn = pill("Import .txt", "folder", tooltip="A text file (first line = title) or 'Title -- Story' lines; "
                               "several stories become a queue")
        self.import_folder_btn = pill("Import folder", "folder", tooltip="Every .txt in a folder, one video each")
        self.queue_btn = pill("Add to queue", "plus", "Primary", tooltip="Keep this story for a batch and start another")
        row.addWidget(self.import_btn)
        row.addWidget(self.import_folder_btn)
        row.addWidget(self.queue_btn)
        card.body.addLayout(row)
        self.sample_btn.clicked.connect(self._fill_sample)
        self.title_edit.textChanged.connect(self._story_edited)
        self.body_edit.textChanged.connect(self._story_edited)
        self.import_btn.clicked.connect(self._import_file)
        self.import_folder_btn.clicked.connect(self._import_folder)
        self.queue_btn.clicked.connect(self._add_to_queue)
        return card

    def _queue_card(self) -> GlassCard:
        card = GlassCard("Queue", "list")
        self.queue_count = hint("")
        card.head.addWidget(self.queue_count)
        self.queue = QListWidget()
        self.queue.setMaximumHeight(140)
        self.queue.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        card.body.addWidget(self.queue)
        row = QHBoxLayout()
        self.queue_edit_btn = pill("Edit selected", "edit", tooltip="Load the story into the editor above")
        self.queue_remove_btn = pill("Remove", "x")
        self.queue_clear_btn = pill("Clear queue", "trash")
        row.addWidget(self.queue_edit_btn)
        row.addWidget(self.queue_remove_btn)
        row.addWidget(self.queue_clear_btn)
        row.addStretch(1)
        card.body.addLayout(row)
        card.body.addWidget(hint("Render makes one video per queued story. With an empty queue it renders the story above."))
        self.queue_edit_btn.clicked.connect(self._edit_queued)
        self.queue_remove_btn.clicked.connect(self._remove_queued)
        self.queue_clear_btn.clicked.connect(self._clear_queue)
        self.queue.itemDoubleClicked.connect(lambda _i: self._edit_queued())
        self.queue.currentRowChanged.connect(lambda _r: self._preview_timer.start())
        return card

    def _voice_card(self) -> GlassCard:
        card = GlassCard("Voice", "mic")
        self.test_voice_btn = pill("Test voice", "play", tooltip="Make a short sample with these settings and play it")
        card.head.addWidget(self.test_voice_btn)
        self.provider = Segmented([("edge", "Edge TTS (free)"), ("elevenlabs", "ElevenLabs"), ("file", "My recording"), ("silent", "No voice")])
        card.body.addWidget(self.provider)

        self.voice_row = QWidget()
        vr = QHBoxLayout(self.voice_row)
        vr.setContentsMargins(0, 0, 0, 0)
        self.voice_combo = QComboBox()
        self.voice_combo.setMinimumWidth(240)
        self.voice_refresh = round_button("refresh", "Fetch the full voice list")
        vr.addWidget(hint("Voice"))
        vr.addWidget(self.voice_combo, 1)
        vr.addWidget(self.voice_refresh)
        card.body.addWidget(self.voice_row)

        self.key_row = QWidget()
        kr = QHBoxLayout(self.key_row)
        kr.setContentsMargins(0, 0, 0, 0)
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText(f"ElevenLabs API key (or set {ELEVENLABS_KEY_ENV})")
        self.remember_key = QCheckBox("Remember on this PC")
        kr.addWidget(self.api_key, 1)
        kr.addWidget(self.remember_key)
        card.body.addWidget(self.key_row)

        self.narration_pick = FilePicker("Your narration audio (captions come from whisper if installed, else estimated)", "music", "file", AUDIO_FILTER)
        card.body.addWidget(self.narration_pick)
        self.voice_hint = hint("")
        card.body.addWidget(self.voice_hint)

        row = QHBoxLayout()
        self.speed = LabeledSlider("Speed", 0.5, 2.0, 0.05, "{:.2f}x")
        self.voice_volume = LabeledSlider("Voice volume", 0.2, 2.0, 0.05, "{:.0%}")
        row.addWidget(self.speed, 1)
        row.addWidget(self.voice_volume, 1)
        card.body.addLayout(row)
        row2 = QHBoxLayout()
        self.read_title_chk = QCheckBox("Read the title aloud")
        self.expand_chk = QCheckBox("Expand shorthand (AITA, TL;DR...)")
        row2.addWidget(self.read_title_chk)
        row2.addWidget(self.expand_chk)
        row2.addStretch(1)
        card.body.addLayout(row2)

        self.provider.changed.connect(self._on_provider)
        self.voice_combo.currentIndexChanged.connect(self._settings_edited)
        self.voice_refresh.clicked.connect(self._refresh_voices)
        self.api_key.textChanged.connect(self._settings_edited)
        self.remember_key.toggled.connect(self._settings_edited)
        self.narration_pick.changed.connect(self._settings_edited)
        self.speed.valueChanged.connect(self._settings_edited)
        self.voice_volume.valueChanged.connect(self._settings_edited)
        self.read_title_chk.toggled.connect(self._settings_edited)
        self.expand_chk.toggled.connect(self._settings_edited)
        self.test_voice_btn.clicked.connect(self._test_voice)
        return card

    def _captions_card(self) -> GlassCard:
        card = GlassCard("Captions", "captions")
        self.captions_chk = QCheckBox("On")
        card.head.addWidget(self.captions_chk)
        row = QHBoxLayout()
        row.addWidget(hint("Look"))
        self.preset = Segmented([("pop", "Pop"), ("clean", "Clean"), ("boxed", "Boxed"), ("neon", "Neon")])
        row.addWidget(self.preset)
        row.addStretch(1)
        card.body.addLayout(row)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        grid.addWidget(hint("Font"), 0, 0)
        font_row = QHBoxLayout()
        self.font_combo = QComboBox()
        self.font_combo.setMinimumWidth(200)
        self.font_file_btn = pill("Font file", "folder", tooltip="Use any .ttf/.otf, e.g. a Google font you downloaded")
        font_row.addWidget(self.font_combo, 1)
        font_row.addWidget(self.font_file_btn)
        grid.addLayout(font_row, 1, 0)
        self.font_size = LabeledSlider("Size", 0.03, 0.16, 0.005, "{:.1%} of width")
        grid.addWidget(self.font_size, 1, 1)

        self.words_spin = QSpinBox(); self.words_spin.setRange(1, 8); self.words_spin.setSuffix(" words at a time")
        self.uppercase_chk = QCheckBox("UPPERCASE")
        self.highlight_chk = QCheckBox("Highlight the spoken word")
        r2 = QHBoxLayout()
        r2.addWidget(self.words_spin)
        r2.addSpacing(10)
        r2.addWidget(self.uppercase_chk)
        r2.addSpacing(10)
        r2.addWidget(self.highlight_chk)
        r2.addStretch(1)
        grid.addLayout(r2, 2, 0, 1, 2)

        colors = QHBoxLayout()
        self.text_color = ColorButton("Text")
        self.highlight_color = ColorButton("Highlight")
        self.outline_color = ColorButton("Outline")
        self.box_color = ColorButton("Box")
        for b in (self.text_color, self.highlight_color, self.outline_color, self.box_color):
            colors.addWidget(b)
        colors.addStretch(1)
        grid.addLayout(colors, 3, 0, 1, 2)

        self.outline = LabeledSlider("Outline", 0.0, 0.25, 0.01, "{:.0%}")
        grid.addWidget(self.outline, 4, 0)
        self.box_opacity = LabeledSlider("Box opacity", 0.1, 1.0, 0.05, "{:.0%}")
        grid.addWidget(self.box_opacity, 4, 1)
        r5 = QHBoxLayout()
        self.shadow_chk = QCheckBox("Shadow")
        self.box_chk = QCheckBox("Backing box")
        r5.addWidget(self.shadow_chk)
        r5.addWidget(self.box_chk)
        r5.addStretch(1)
        grid.addLayout(r5, 5, 0, 1, 2)
        self.caption_y = LabeledSlider("Position (top to bottom)", 0.1, 0.9, 0.01, "{:.0%}")
        grid.addWidget(self.caption_y, 6, 0)
        tr = QVBoxLayout()
        tr.setSpacing(4)
        tr.addWidget(hint("Timing source"))
        self.timing_combo = QComboBox()
        self.timing_combo.addItem("Automatic (voice engine, then whisper, then estimate)", "auto")
        self.timing_combo.addItem("Whisper (listen to the audio)", "whisper")
        self.timing_combo.addItem("Estimate from the text", "estimate")
        tr.addWidget(self.timing_combo)
        grid.addLayout(tr, 6, 1)
        card.body.addLayout(grid)
        self.timing_hint = hint("")
        card.body.addWidget(self.timing_hint)

        self.captions_chk.toggled.connect(self._settings_edited)
        self.preset.changed.connect(self._apply_preset)
        self.font_combo.currentIndexChanged.connect(self._settings_edited)
        self.font_file_btn.clicked.connect(self._pick_font_file)
        self.font_size.valueChanged.connect(self._settings_edited)
        self.words_spin.valueChanged.connect(self._settings_edited)
        self.uppercase_chk.toggled.connect(self._settings_edited)
        self.highlight_chk.toggled.connect(self._settings_edited)
        for b in (self.text_color, self.highlight_color, self.outline_color, self.box_color):
            b.changed.connect(self._settings_edited)
        self.outline.valueChanged.connect(self._settings_edited)
        self.box_opacity.valueChanged.connect(self._settings_edited)
        self.shadow_chk.toggled.connect(self._settings_edited)
        self.box_chk.toggled.connect(self._settings_edited)
        self.caption_y.valueChanged.connect(self._settings_edited)
        self.timing_combo.currentIndexChanged.connect(self._settings_edited)
        return card

    def _title_card(self) -> GlassCard:
        card = GlassCard("Story card", "card")
        row = QHBoxLayout()
        self.title_mode = Segmented([("title", "While the title is read"), ("fixed", "Fixed time"), ("off", "Off")])
        self.title_seconds = QDoubleSpinBox(); self.title_seconds.setRange(0.5, 15); self.title_seconds.setDecimals(1); self.title_seconds.setSuffix(" s")
        row.addWidget(self.title_mode)
        row.addWidget(self.title_seconds)
        row.addStretch(1)
        card.body.addLayout(row)
        row2 = QHBoxLayout()
        row2.addWidget(hint("Channel name"))
        self.channel_edit = QLineEdit()
        self.channel_edit.setPlaceholderText("Shown on the card")
        row2.addWidget(self.channel_edit, 1)
        card.body.addLayout(row2)
        self.title_mode.changed.connect(self._on_title_mode)
        self.title_seconds.valueChanged.connect(self._settings_edited)
        self.channel_edit.textChanged.connect(self._settings_edited)
        return card

    def _background_card(self) -> GlassCard:
        card = GlassCard("Background footage", "film")
        row = QHBoxLayout()
        self.bg_pick = FilePicker("A video, or a folder of videos (gameplay, satisfying clips...). Empty = soft gradient", "film", "file", VIDEO_FILTER)
        self.bg_folder_btn = pill("Folder", "folder", tooltip="Pick a folder: each video gets a clip from it")
        row.addWidget(self.bg_pick, 1)
        row.addWidget(self.bg_folder_btn)
        card.body.addLayout(row)
        self.bg_info = hint("")
        card.body.addWidget(self.bg_info)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.addWidget(hint("Fit any clip to the canvas"), 0, 0)
        self.fit = Segmented([("crop", "Crop to fill"), ("blur", "Blur fill")])
        grid.addWidget(self.fit, 1, 0)
        grid.addWidget(hint("From a folder, pick"), 0, 1)
        pick_row = QHBoxLayout()
        self.pick = Segmented([("random", "Random"), ("sequential", "In order")])
        self.random_start_chk = QCheckBox("Random start point")
        pick_row.addWidget(self.pick)
        pick_row.addWidget(self.random_start_chk)
        pick_row.addStretch(1)
        grid.addLayout(pick_row, 1, 1)
        self.bg_volume = LabeledSlider("Footage sound", 0.0, 1.0, 0.05, "{:.0%}")
        grid.addWidget(self.bg_volume, 2, 0)
        card.body.addLayout(grid)
        row3 = QHBoxLayout()
        self.music_pick = FilePicker("Background music: a track, or a folder to pick a random track from", "music", "file", AUDIO_FILTER)
        self.music_folder_btn = pill("Folder", "folder")
        row3.addWidget(self.music_pick, 1)
        row3.addWidget(self.music_folder_btn)
        card.body.addLayout(row3)
        self.music_volume = LabeledSlider("Music volume", 0.0, 1.0, 0.02, "{:.0%}")
        card.body.addWidget(self.music_volume)
        self.bg_pick.changed.connect(self._on_background_changed)
        self.bg_folder_btn.clicked.connect(self._pick_bg_folder)
        self.fit.changed.connect(self._settings_edited)
        self.pick.changed.connect(self._settings_edited)
        self.random_start_chk.toggled.connect(self._settings_edited)
        self.bg_volume.valueChanged.connect(self._settings_edited)
        self.music_pick.changed.connect(self._settings_edited)
        self.music_folder_btn.clicked.connect(self._pick_music_folder)
        self.music_volume.valueChanged.connect(self._settings_edited)
        return card

    def _output_card(self) -> GlassCard:
        card = GlassCard("Output", "folder")
        self.out_pick = FilePicker("Save videos to", "folder", "dir", placeholder="~/Videos/TrendyReels Maker")
        card.body.addWidget(self.out_pick)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.addWidget(hint("Canvas"), 0, 0)
        self.aspect = QComboBox()
        for k in ASPECT_PRESETS:
            self.aspect.addItem(k)
        self.aspect.addItem("Custom...")
        grid.addWidget(self.aspect, 1, 0)
        size_row = QHBoxLayout()
        self.width_spin = QSpinBox(); self.width_spin.setRange(64, 7680); self.width_spin.setSuffix(" px")
        self.height_spin = QSpinBox(); self.height_spin.setRange(64, 7680); self.height_spin.setSuffix(" px")
        self.fps_spin = QSpinBox(); self.fps_spin.setRange(1, 120); self.fps_spin.setSuffix(" fps")
        for w in (self.width_spin, self.height_spin, self.fps_spin):
            size_row.addWidget(w)
        grid.addLayout(size_row, 1, 1)
        grid.addWidget(hint("Quality"), 2, 0)
        self.quality = QComboBox()
        for label, crf in (("Best quality", 17), ("Balanced", 20), ("Small file", 26)):
            self.quality.addItem(label, crf)
        grid.addWidget(self.quality, 3, 0)
        pad_row = QHBoxLayout()
        self.lead_in = QDoubleSpinBox(); self.lead_in.setRange(0, 5); self.lead_in.setDecimals(1); self.lead_in.setPrefix("start pause "); self.lead_in.setSuffix(" s")
        self.tail = QDoubleSpinBox(); self.tail.setRange(0, 10); self.tail.setDecimals(1); self.tail.setPrefix("end pause "); self.tail.setSuffix(" s")
        pad_row.addWidget(self.lead_in)
        pad_row.addWidget(self.tail)
        grid.addLayout(pad_row, 3, 1)
        card.body.addLayout(grid)
        row = QHBoxLayout()
        self.skip_chk = QCheckBox("Skip stories whose video already exists")
        self.timestamp_chk = QCheckBox("Add date and time to file names")
        row.addWidget(self.skip_chk)
        row.addWidget(self.timestamp_chk)
        row.addStretch(1)
        card.body.addLayout(row)
        self.out_pick.changed.connect(self._settings_edited)
        self.aspect.currentIndexChanged.connect(self._on_aspect)
        for w in (self.width_spin, self.height_spin, self.fps_spin):
            w.valueChanged.connect(self._settings_edited)
        self.quality.currentIndexChanged.connect(self._settings_edited)
        self.lead_in.valueChanged.connect(self._settings_edited)
        self.tail.valueChanged.connect(self._settings_edited)
        self.skip_chk.toggled.connect(self._settings_edited)
        self.timestamp_chk.toggled.connect(self._settings_edited)
        return card

    def _preview_card(self) -> GlassCard:
        card = GlassCard("Preview", "image")
        self.refresh_btn = round_button("refresh", "Refresh preview")
        card.head.addWidget(self.refresh_btn)
        self.preview = QLabel("Type a story to see a preview")
        self.preview.setObjectName("Hint")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(300, 360)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        card.body.addWidget(self.preview, 1)
        row = QHBoxLayout()
        self.scrub = QSlider(Qt.Orientation.Horizontal)
        self.scrub.setRange(0, 1000)
        self.scrub.setValue(120)
        self.time_lbl = QLabel("0:00")
        self.time_lbl.setObjectName("Hint")
        self.time_lbl.setFixedWidth(90)
        self.time_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        row.addWidget(self.scrub, 1)
        row.addWidget(self.time_lbl)
        card.body.addLayout(row)
        self.summary = hint("")
        card.body.addWidget(self.summary)
        self.scrub.valueChanged.connect(self._on_scrub)
        self.refresh_btn.clicked.connect(self._request_preview)
        return card

    def _render_card(self) -> GlassCard:
        card = GlassCard()
        row = QHBoxLayout()
        self.render_btn = pill("Render video", "play", "Go")
        self.cancel_btn = pill("Cancel", "stop", "Danger")
        self.cancel_btn.setEnabled(False)
        self.open_btn = pill("Open output folder", "open")
        row.addWidget(self.render_btn)
        row.addWidget(self.cancel_btn)
        row.addStretch(1)
        row.addWidget(self.open_btn)
        card.body.addLayout(row)
        self.stage_lbl = QLabel("Ready")
        self.stage_lbl.setObjectName("Hint")
        card.body.addWidget(self.stage_lbl)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setFixedHeight(10)
        card.body.addWidget(self.progress)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(1000)
        self.log_view.setFixedHeight(110)
        card.body.addWidget(self.log_view)
        self.render_btn.clicked.connect(self._render)
        self.cancel_btn.clicked.connect(self._cancel)
        self.open_btn.clicked.connect(self._open_output)
        return card

    # ------------------------------------------------------------- worker
    def _build_worker(self) -> None:
        self.thread = QThread(self)
        self.worker = RenderWorker()
        self.worker.moveToThread(self.thread)
        self.worker.log.connect(self._log)
        self.worker.stage.connect(self._on_stage)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.cancelled.connect(self._on_cancelled)
        self.thread.started.connect(self.worker.run)

    # ------------------------------------------------------- settings I/O
    def _apply_settings(self) -> None:
        s = self.s
        self.title_edit.setText(str(s.extra.get("editor_title", "")))
        self.body_edit.setPlainText(str(s.extra.get("editor_body", "")))
        for d in s.extra.get("queue", []) or []:
            if isinstance(d, dict):
                self._queue_add(Story(str(d.get("title", "")), str(d.get("body", "")), str(d.get("source", ""))))
        self.provider.set_value(s.tts_provider)
        self._fill_voices()
        self.api_key.setText(str(s.extra.get("elevenlabs_api_key", "") or ""))
        self.remember_key.setChecked(bool(s.extra.get("elevenlabs_api_key")))
        self.narration_pick.set_path(s.narration_file)
        self.speed.set_value(s.speed)
        self.voice_volume.set_value(s.voice_volume)
        self.read_title_chk.setChecked(s.read_title)
        self.expand_chk.setChecked(s.expand_abbreviations)
        self._on_provider(s.tts_provider)

        self.captions_chk.setChecked(s.captions)
        self._fill_fonts(s.font_path)
        self.font_size.set_value(s.font_size)
        self.words_spin.setValue(s.words_per_caption)
        self.uppercase_chk.setChecked(s.uppercase)
        self.highlight_chk.setChecked(s.highlight)
        self.text_color.set_rgb(s.text_color)
        self.highlight_color.set_rgb(s.highlight_color)
        self.outline_color.set_rgb(s.outline_color)
        self.box_color.set_rgb(s.box_color)
        self.outline.set_value(s.outline)
        self.box_opacity.set_value(s.box_opacity)
        self.shadow_chk.setChecked(s.shadow)
        self.box_chk.setChecked(s.box)
        self.caption_y.set_value(s.caption_y)
        self.timing_combo.setCurrentIndex(max(0, self.timing_combo.findData(s.caption_timing)))
        self.preset.set_value(str(s.extra.get("preset", "pop")))

        self.title_mode.set_value(s.title_card)
        self.title_seconds.setValue(s.title_card_seconds or 2.5)
        self.channel_edit.setText(s.channel_name)
        self._on_title_mode(s.title_card)

        self.bg_pick.set_path(s.background)
        self.fit.set_value(s.fit)
        self.pick.set_value(s.background_pick)
        self.random_start_chk.setChecked(s.random_start)
        self.bg_volume.set_value(s.background_audio_volume)
        self.music_pick.set_path(s.music_path)
        self.music_volume.set_value(s.music_volume)

        self.out_pick.set_path(s.output_folder)
        preset = next((k for k, v in ASPECT_PRESETS.items() if v == (s.width, s.height)), "Custom...")
        self.aspect.setCurrentText(preset)
        self.width_spin.setValue(s.width)
        self.height_spin.setValue(s.height)
        self.fps_spin.setValue(s.fps)
        idx = self.quality.findData(s.crf)
        self.quality.setCurrentIndex(idx if idx >= 0 else 1)
        self.lead_in.setValue(s.lead_in)
        self.tail.setValue(s.tail)
        self.skip_chk.setChecked(s.skip_existing)
        self.timestamp_chk.setChecked(s.timestamp_names)
        self._on_aspect(0)

    def _collect_settings(self) -> ProjectSettings:
        s = self.s
        s.tts_provider = self.provider.value()
        voice = self.voice_combo.currentData()
        if voice:
            s.voice = voice
        key = self.api_key.text().strip()
        if self.remember_key.isChecked() and key:
            s.extra["elevenlabs_api_key"] = key
        else:
            s.extra.pop("elevenlabs_api_key", None)
        self._session_key = key
        s.narration_file = self.narration_pick.path()
        s.speed = round(self.speed.value(), 2)
        s.voice_volume = round(self.voice_volume.value(), 2)
        s.read_title = self.read_title_chk.isChecked()
        s.expand_abbreviations = self.expand_chk.isChecked()

        s.captions = self.captions_chk.isChecked()
        s.font_path = self.font_combo.currentData() or ""
        s.font_size = round(self.font_size.value(), 3)
        s.words_per_caption = self.words_spin.value()
        s.uppercase = self.uppercase_chk.isChecked()
        s.highlight = self.highlight_chk.isChecked()
        s.text_color = self.text_color.rgb()
        s.highlight_color = self.highlight_color.rgb()
        s.outline_color = self.outline_color.rgb()
        s.box_color = self.box_color.rgb()
        s.outline = round(self.outline.value(), 2)
        s.box_opacity = round(self.box_opacity.value(), 2)
        s.shadow = self.shadow_chk.isChecked()
        s.box = self.box_chk.isChecked()
        s.caption_y = round(self.caption_y.value(), 2)
        s.caption_timing = self.timing_combo.currentData() or "auto"
        s.extra["preset"] = self.preset.value()

        s.title_card = self.title_mode.value()
        s.title_card_seconds = self.title_seconds.value()
        s.channel_name = self.channel_edit.text().strip() or "Your Channel"

        s.background = self.bg_pick.path()
        s.fit = self.fit.value()
        s.background_pick = self.pick.value()
        s.random_start = self.random_start_chk.isChecked()
        s.background_audio_volume = round(self.bg_volume.value(), 2)
        s.music_path = self.music_pick.path()
        s.music_volume = round(self.music_volume.value(), 2)

        s.output_folder = self.out_pick.path()
        s.width, s.height, s.fps = self.width_spin.value(), self.height_spin.value(), self.fps_spin.value()
        s.crf = self.quality.currentData() or 20
        s.lead_in = self.lead_in.value()
        s.tail = self.tail.value()
        s.skip_existing = self.skip_chk.isChecked()
        s.timestamp_names = self.timestamp_chk.isChecked()

        s.extra["editor_title"] = self.title_edit.text()
        s.extra["editor_body"] = self.body_edit.toPlainText()
        s.extra["queue"] = [{"title": st.title, "body": st.body, "source": st.source} for st in self._queued()]
        return s

    def _render_settings(self) -> ProjectSettings:
        """Settings for a job: the typed API key is used even when not remembered."""
        import copy
        s = copy.deepcopy(self._collect_settings())
        key = self.api_key.text().strip()
        if key:
            s.extra["elevenlabs_api_key"] = key
        return s

    def _save_settings(self) -> None:
        try:
            self._collect_settings().save()
        except OSError as exc:
            self._log(f"could not save settings: {exc}")

    # ----------------------------------------------------------- handlers
    def _settings_edited(self, *_args) -> None:
        if self._loading:
            return
        self._collect_settings()
        self._refresh_hints()
        self._preview_timer.start()

    def _story_edited(self) -> None:
        text = self.body_edit.toPlainText()
        n = len(text.split())
        est = n / 165 * 60 / max(0.5, self.speed.value()) if n else 0
        self.story_stats.setText(f"{n} words, about {fmt_seconds(est)} of speech" if n else "")
        self._settings_edited()

    def _refresh_hints(self) -> None:
        s = self.s
        if s.tts_provider == "edge":
            self.voice_hint.setText("Free Microsoft neural voices with exact word timings. Needs an internet connection while rendering.")
        elif s.tts_provider == "elevenlabs":
            self.voice_hint.setText("Uses your ElevenLabs account (paid). Word timings come from the API.")
        elif s.tts_provider == "file":
            self.voice_hint.setText("Record the story yourself. Install faster-whisper for word-accurate captions, otherwise they are estimated from the text.")
        else:
            self.voice_hint.setText("No narration: music and footage only, captions timed from the text. Good for quick tests.")
        if s.caption_timing == "whisper" or (s.caption_timing == "auto" and s.tts_provider == "file"):
            self.timing_hint.setText("faster-whisper is installed." if whisper_available()
                                     else "faster-whisper is not installed (pip install faster-whisper), so timings will be estimated.")
        else:
            self.timing_hint.setText("")
        self.box_opacity.setEnabled(s.box)
        self.box_color.setEnabled(s.box)
        self.highlight_color.setEnabled(s.highlight)
        self.title_seconds.setEnabled(s.title_card == "fixed" or (s.title_card == "title" and not s.read_title))

    def _on_provider(self, key: str) -> None:
        self.voice_row.setVisible(key in ("edge", "elevenlabs"))
        self.key_row.setVisible(key == "elevenlabs")
        self.narration_pick.setVisible(key == "file")
        self.speed.setEnabled(key != "silent")
        self.read_title_chk.setEnabled(key != "file")
        self.test_voice_btn.setEnabled(key not in ("file", "silent"))
        if not self._loading:
            self._fill_voices()
        self._settings_edited()

    def _fill_voices(self) -> None:
        provider = self.provider.value()
        was = self._loading
        self._loading = True
        self.voice_combo.clear()
        for vid, label in self._voices.get(provider, []):
            self.voice_combo.addItem(label, vid)
        idx = self.voice_combo.findData(self.s.voice)
        if idx < 0 and self.s.voice and provider == "elevenlabs" and self.s.tts_provider == "elevenlabs":
            self.voice_combo.addItem(f"{self.s.voice} (custom id)", self.s.voice)
            idx = self.voice_combo.count() - 1
        self.voice_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._loading = was

    def _refresh_voices(self) -> None:
        provider = self.provider.value()
        if provider == "elevenlabs" and not (self.api_key.text().strip() or os.environ.get(ELEVENLABS_KEY_ENV)):
            QMessageBox.information(self, "TrendyReels Maker", "Enter your ElevenLabs API key first.")
            return
        self.voice_refresh.setEnabled(False)
        self._log(f"fetching {provider} voices...")
        QThreadPool.globalInstance().start(VoiceListJob(provider, self._render_settings(), self._voice_signals, refresh=True))

    def _voices_ready(self, provider: str, voices: list) -> None:
        self.voice_refresh.setEnabled(True)
        if voices:
            self._voices[provider] = [tuple(v) for v in voices]
            if self.provider.value() == provider:
                self._fill_voices()
            self._log(f"{len(voices)} {provider} voices available")

    def _voices_failed(self, provider: str, msg: str) -> None:
        self.voice_refresh.setEnabled(True)
        self._log(f"could not fetch {provider} voices: {msg}")

    def _test_voice(self) -> None:
        s = self._render_settings()
        if s.tts_provider in ("file", "silent"):
            return
        if not ff.find_ffmpeg():
            self._warn_ffmpeg()
            return
        self.test_voice_btn.setEnabled(False)
        self._log("making a voice sample...")
        text = None
        title = self.title_edit.text().strip()
        if title:
            text = title
        QThreadPool.globalInstance().start(VoiceTestJob(s, self._test_signals, text))

    def _voice_test_ready(self, path: str) -> None:
        self.test_voice_btn.setEnabled(True)
        self._log("playing the sample in your default audio player")
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _voice_test_failed(self, msg: str) -> None:
        self.test_voice_btn.setEnabled(True)
        self._log("voice test failed: " + msg)
        QMessageBox.warning(self, "Voice test failed", msg)

    def _apply_preset(self, key: str) -> None:
        if self._loading or key not in STYLE_PRESETS:
            return
        self._loading = True
        p = STYLE_PRESETS[key]
        self.uppercase_chk.setChecked(p["uppercase"])
        self.highlight_chk.setChecked(p["highlight"])
        if "highlight_color" in p:
            self.highlight_color.set_rgb(p["highlight_color"])
        self.text_color.set_rgb(p["text_color"])
        if "outline_color" in p:
            self.outline_color.set_rgb(p["outline_color"])
        self.outline.set_value(p["outline"])
        self.shadow_chk.setChecked(p["shadow"])
        self.box_chk.setChecked(p["box"])
        if "box_color" in p:
            self.box_color.set_rgb(p["box_color"])
        if "box_opacity" in p:
            self.box_opacity.set_value(p["box_opacity"])
        self.font_size.set_value(p["font_size"])
        self.words_spin.setValue(p["words_per_caption"])
        self._loading = False
        self._settings_edited()

    def _fill_fonts(self, current: str) -> None:
        self.font_combo.clear()
        default = fontlib.default_font()
        self.font_combo.addItem(f"Default ({fontlib.display_name(default)})" if default else "Default (built-in)", "")
        seen = set()
        if current and os.path.isfile(current):
            self.font_combo.addItem(fontlib.display_name(current) + "  (file)", current)
            seen.add(current.lower())
        for name, path in fontlib.list_fonts():
            if path.lower() not in seen:
                self.font_combo.addItem(name, path)
        idx = self.font_combo.findData(current) if current else 0
        self.font_combo.setCurrentIndex(idx if idx >= 0 else 0)

    def _pick_font_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Font file", os.path.expanduser("~"), FONT_FILTER)
        if path:
            self._set_font_file(os.path.normpath(path))

    def _set_font_file(self, path: str) -> None:
        idx = self.font_combo.findData(path)
        if idx < 0:
            self.font_combo.insertItem(1, fontlib.display_name(path) + "  (file)", path)
            idx = 1
        self.font_combo.setCurrentIndex(idx)

    def _on_title_mode(self, key: str) -> None:
        self.title_seconds.setVisible(key != "off")
        self._settings_edited()

    def _on_aspect(self, _idx: int) -> None:
        key = self.aspect.currentText()
        custom = key == "Custom..."
        if not custom and key in ASPECT_PRESETS:
            w, h = ASPECT_PRESETS[key]
            was = self._loading
            self._loading = True
            self.width_spin.setValue(w)
            self.height_spin.setValue(h)
            self._loading = was
        self.width_spin.setEnabled(custom)
        self.height_spin.setEnabled(custom)
        self._settings_edited()

    def _on_background_changed(self, path: str) -> None:
        if path and os.path.isdir(path):
            n = len(list_videos(path))
            self.bg_info.setText(f"{n} video(s) in the folder" if n else "No videos found in that folder")
        elif path and os.path.isfile(path) and ff.find_ffmpeg():
            info = ff.video_info(path)
            self.bg_info.setText(f"{info[1]}x{info[2]}, {fmt_seconds(info[0])}" + ("" if info[3] else ", no sound")
                                 if info else "Could not read this video")
        else:
            self.bg_info.setText("")
        self._settings_edited()

    def _pick_bg_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Folder of background videos", os.path.expanduser("~"))
        if folder:
            self.bg_pick.set_path(os.path.normpath(folder))

    def _pick_music_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Folder of music tracks", os.path.expanduser("~"))
        if folder:
            self.music_pick.set_path(os.path.normpath(folder))

    def _pick_wallpaper(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Wallpaper image (Cancel to reset)", os.path.expanduser("~"),
                                              "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        self.s.extra["wallpaper"] = path or ""
        self.backdrop.set_image(path)
        self._save_settings()

    def _check_ffmpeg(self) -> None:
        v = ff.ffmpeg_version()
        if v:
            self._log(v)
        else:
            self._log(f"FFmpeg was not found on PATH. Install it from {ff.FFMPEG_DOWNLOAD_URL} and restart.")
            self.stage_lbl.setText("FFmpeg not found - rendering is disabled until it is installed")

    def _warn_ffmpeg(self) -> None:
        QMessageBox.warning(self, "TrendyReels Maker",
                            f"FFmpeg was not found.\n\nInstall it from {ff.FFMPEG_DOWNLOAD_URL} (on Windows: winget install Gyan.FFmpeg) "
                            "and make sure 'ffmpeg' works in a terminal, then restart the app.")

    # ------------------------------------------------------------ stories
    def _editor_story(self) -> Story:
        return Story(self.title_edit.text().strip(), self.body_edit.toPlainText().strip(), "editor")

    def _fill_sample(self) -> None:
        if self._editor_story().body and QMessageBox.question(
                self, "TrendyReels Maker", "Replace the story in the editor with the sample?") != QMessageBox.StandardButton.Yes:
            return
        self.title_edit.setText(SAMPLE_STORY.title)
        self.body_edit.setPlainText(SAMPLE_STORY.body)

    def _queued(self) -> list[Story]:
        return [self.queue.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.queue.count())]

    def _queue_add(self, story: Story) -> None:
        if story.is_empty():
            return
        item = QListWidgetItem(f"{self.queue.count() + 1}. {story.label[:70]}")
        item.setData(Qt.ItemDataRole.UserRole, story)
        item.setToolTip(story.body[:400])
        self.queue.addItem(item)

    def _renumber_queue(self) -> None:
        for i in range(self.queue.count()):
            it = self.queue.item(i)
            it.setText(f"{i + 1}. {it.data(Qt.ItemDataRole.UserRole).label[:70]}")

    def _refresh_queue_label(self) -> None:
        n = self.queue.count()
        self.queue_count.setText(f"{n} queued" if n else "empty")
        self.render_btn.setText(f"Render {n} videos" if n > 1 else ("Render queued video" if n == 1 else "Render video"))

    def _add_to_queue(self) -> None:
        story = self._editor_story()
        if story.is_empty():
            QMessageBox.information(self, "TrendyReels Maker", "Type or paste a story first.")
            return
        self._queue_add(story)
        self.title_edit.clear()
        self.body_edit.clear()
        self._refresh_queue_label()
        self._settings_edited()

    def _import_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Story text file", os.path.expanduser("~"), TEXT_FILTER)
        if path:
            self._import_path(os.path.normpath(path))

    def _import_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Folder of .txt stories", os.path.expanduser("~"))
        if folder:
            self._import_path(os.path.normpath(folder))

    def _import_path(self, path: str) -> None:
        try:
            stories = load_stories(path)
        except OSError as exc:
            QMessageBox.warning(self, "TrendyReels Maker", f"Could not read {path}:\n{exc}")
            return
        stories = [st for st in stories if not st.is_empty()]
        if not stories:
            QMessageBox.information(self, "TrendyReels Maker", "No stories were found in that file.")
            return
        if len(stories) == 1 and self._editor_story().is_empty():
            self.title_edit.setText(stories[0].title)
            self.body_edit.setPlainText(stories[0].body)
            self._log(f"loaded 1 story from {os.path.basename(path)}")
            return
        for st in stories:
            self._queue_add(st)
        self._log(f"queued {len(stories)} stories from {os.path.basename(path)}")
        self._refresh_queue_label()
        self._settings_edited()

    def _edit_queued(self) -> None:
        item = self.queue.currentItem()
        if item is None:
            return
        story: Story = item.data(Qt.ItemDataRole.UserRole)
        if not self._editor_story().is_empty() and QMessageBox.question(
                self, "TrendyReels Maker", "Replace the story in the editor with the selected one?") != QMessageBox.StandardButton.Yes:
            return
        self.title_edit.setText(story.title)
        self.body_edit.setPlainText(story.body)
        self.queue.takeItem(self.queue.row(item))
        self._renumber_queue()
        self._refresh_queue_label()
        self._settings_edited()

    def _remove_queued(self) -> None:
        for item in self.queue.selectedItems():
            self.queue.takeItem(self.queue.row(item))
        self._renumber_queue()
        self._refresh_queue_label()
        self._settings_edited()

    def _clear_queue(self) -> None:
        if self.queue.count() and QMessageBox.question(self, "TrendyReels Maker", "Remove every queued story?") != QMessageBox.StandardButton.Yes:
            return
        self.queue.clear()
        self._refresh_queue_label()
        self._settings_edited()

    def _stories_to_render(self) -> list[Story]:
        queued = self._queued()
        return queued if queued else [self._editor_story()]

    def _preview_story(self) -> Story:
        editor = self._editor_story()
        if not editor.is_empty():
            return editor
        item = self.queue.currentItem() or (self.queue.item(0) if self.queue.count() else None)
        return item.data(Qt.ItemDataRole.UserRole) if item else editor

    # ------------------------------------------------------------ preview
    def _on_scrub(self, _v: int) -> None:
        self.time_lbl.setText(f"{fmt_seconds(self._scrub_time())} / {fmt_seconds(self._preview_total)}")
        self._preview_timer.start()

    def _scrub_time(self) -> float:
        return self.scrub.value() / 1000.0 * max(0.0, self._preview_total)

    def _request_preview(self) -> None:
        story = self._preview_story()
        if story.is_empty():
            self.preview.setPixmap(QPixmap())
            self.preview.setText("Type a story to see a preview")
            self.summary.setText("")
            return
        s = self._collect_settings()
        self._preview_id += 1
        self._requested_t = self._scrub_time()
        w, h = s.even_size
        scale = min(self.preview.width() / w, self.preview.height() / h, 1.0)
        pw, ph = max(90, int(w * scale) // 2 * 2), max(160, int(h * scale) // 2 * 2)
        QThreadPool.globalInstance().start(PreviewJob(self._preview_id, story, s, self._scrub_time(), pw, ph, self._preview_signals))

    def _preview_ready(self, request_id: int, img, total: float, captions: int) -> None:
        if request_id != self._preview_id:
            return
        self._preview_total = total
        self.preview.setText("")
        self.preview.setPixmap(QPixmap.fromImage(img))
        self.time_lbl.setText(f"{fmt_seconds(self._scrub_time())} / {fmt_seconds(total)}")
        if abs(self._scrub_time() - getattr(self, "_requested_t", 0.0)) > 0.05:
            self._preview_timer.start()      # the length changed since the frame was requested
        s = self.s
        parts = [f"{s.width}x{s.height} @ {s.fps} fps", f"about {fmt_seconds(total)}", f"{captions} captions"]
        if s.background:
            parts.append("footage " + os.path.basename(s.background))
        if s.music_path:
            parts.append("music " + os.path.basename(s.music_path))
        parts.append("timings are estimated until the voice is made")
        self.summary.setText("  ·  ".join(parts))

    def _preview_failed(self, request_id: int, msg: str) -> None:
        if request_id == self._preview_id:
            self.preview.setPixmap(QPixmap())
            self.preview.setText(f"Preview failed: {msg}")

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if not self._loading:
            self._preview_timer.start()

    # Drag-and-drop: story text files, footage, music, fonts.
    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls() and not self.thread.isRunning():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        handled = False
        for url in event.mimeData().urls():
            p = os.path.normpath(url.toLocalFile())
            if not p:
                continue
            ext = os.path.splitext(p)[1].lower()
            if os.path.isdir(p):
                if list_videos(p):
                    self.bg_pick.set_path(p)
                else:
                    self._import_path(p)
                handled = True
            elif ext in TEXT_EXTENSIONS:
                self._import_path(p)
                handled = True
            elif ext in VIDEO_EXTENSIONS:
                self.bg_pick.set_path(p)
                handled = True
            elif ext in AUDIO_EXTENSIONS:
                if self.provider.value() == "file":
                    self.narration_pick.set_path(p)
                else:
                    self.music_pick.set_path(p)
                handled = True
            elif ext in (".ttf", ".otf", ".ttc"):
                self._set_font_file(p)
                handled = True
        if not handled:
            self._log("dropped items were not stories (.txt), videos, audio or fonts")
        event.acceptProposedAction()

    # ------------------------------------------------------------- render
    def _render(self) -> None:
        s = self._render_settings()
        stories = [st for st in self._stories_to_render() if not st.is_empty()]
        if not stories:
            QMessageBox.information(self, "TrendyReels Maker", "Type or paste a story first (or press 'Try the sample').")
            return
        problems = s.validate()
        if problems:
            QMessageBox.warning(self, "TrendyReels Maker", "Please fix:\n- " + "\n- ".join(problems))
            return
        if not ff.find_ffmpeg():
            self._warn_ffmpeg()
            return
        if s.tts_provider == "elevenlabs" and not s.extra.get("elevenlabs_api_key") and not os.environ.get(ELEVENLABS_KEY_ENV):
            QMessageBox.warning(self, "TrendyReels Maker", "Enter your ElevenLabs API key, or switch the voice to Edge TTS (free).")
            return
        self._save_settings()
        self.worker.start(s, stories)
        self._set_busy(True)
        self.progress.setValue(0)
        self.log_view.clear()
        self.thread.start()

    def _cancel(self) -> None:
        self.worker.cancel()
        self.stage_lbl.setText("Cancelling...")
        self.cancel_btn.setEnabled(False)

    def _set_busy(self, busy: bool) -> None:
        self.render_btn.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)
        for w in (self.import_btn, self.import_folder_btn, self.queue_btn, self.queue_clear_btn, self.queue_remove_btn,
                  self.queue_edit_btn, self.test_voice_btn, self.sample_btn):
            w.setEnabled(not busy)
        if not busy:
            self._on_provider(self.provider.value())

    def _on_stage(self, text: str) -> None:
        self.stage_lbl.setText(text)
        self.progress.setValue(0)

    def _on_progress(self, done: int, total: int) -> None:
        self.progress.setValue(int(done * 1000 / max(1, total)))

    def _finish_thread(self) -> None:
        self.thread.quit()
        self.thread.wait(5000)
        self._set_busy(False)

    def _on_finished(self, outputs: list) -> None:
        self._finish_thread()
        self._outputs = outputs
        self.progress.setValue(1000)
        self.stage_lbl.setText(f"Done: {len(outputs)} video(s) ready")
        if outputs:
            self._log("finished: " + ", ".join(os.path.basename(p) for p in outputs))

    def _on_failed(self, msg: str) -> None:
        self._finish_thread()
        self.stage_lbl.setText("Failed")
        self._log("error: " + msg)
        QMessageBox.critical(self, "Render failed", msg)

    def _on_cancelled(self) -> None:
        self._finish_thread()
        self.stage_lbl.setText("Cancelled")
        self.progress.setValue(0)
        self._log("cancelled")

    def _open_output(self) -> None:
        folder = self.s.default_output_folder()
        if self._outputs and os.path.isdir(os.path.dirname(self._outputs[-1])):
            folder = os.path.dirname(self._outputs[-1])
        os.makedirs(folder, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _log(self, text: str) -> None:
        self.log_view.appendPlainText(text)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.thread.isRunning():
            if QMessageBox.question(self, "TrendyReels Maker", "A render is running. Cancel it and quit?") != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.worker.cancel()
            self.thread.quit()
            self.thread.wait(10000)
        self._save_settings()
        QThreadPool.globalInstance().waitForDone(3000)
        event.accept()


def main(argv: list[str] | None = None) -> int:
    app = QApplication([sys.argv[0]])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLESHEET)
    app.setWindowIcon(app_icon())
    win = MainWindow(ProjectSettings.load())
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
