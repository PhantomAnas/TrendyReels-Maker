"""Background workers: the render job, preview frames, voice lists and voice tests."""

from __future__ import annotations

import copy
import os
import tempfile
import threading
import traceback

import numpy as np
from PySide6.QtCore import QObject, QRunnable, Signal
from PySide6.QtGui import QImage

from .. import background as bgmod
from .. import batch, render, tts
from ..settings import ProjectSettings
from ..text import Story


class RenderWorker(QObject):
    """Runs `batch.run_job` on a QThread.  All signals are delivered on the GUI thread."""

    log = Signal(str)
    stage = Signal(str)
    progress = Signal(int, int)
    finished = Signal(list)          # output paths
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._cancel = threading.Event()
        self.settings = ProjectSettings()
        self.stories: list[Story] = []

    def cancel(self) -> None:
        self._cancel.set()

    def start(self, settings: ProjectSettings, stories: list[Story]) -> None:
        self._cancel.clear()
        self.settings = copy.deepcopy(settings)
        self.stories = list(stories)

    def run(self) -> None:
        try:
            outputs = batch.run_job(self.stories, self.settings, log=self.log.emit, stage=self.stage.emit,
                                    progress=self.progress.emit, cancelled=self._cancel.is_set)
        except render.RenderCancelled:
            self.cancelled.emit()
            return
        except render.RenderError as exc:
            self.failed.emit(str(exc))
            return
        except Exception:  # noqa: BLE001 - surface anything else in the log
            self.failed.emit("unexpected error:\n" + traceback.format_exc())
            return
        self.finished.emit(outputs)


class PreviewSignals(QObject):
    ready = Signal(int, QImage, float, int)      # request id, frame, total seconds, caption count
    failed = Signal(int, str)


_frame_cache: dict[tuple, np.ndarray] = {}
_frame_lock = threading.Lock()


class PreviewJob(QRunnable):
    """Composes one preview frame (estimated timings, no voice) on the thread pool."""

    def __init__(self, request_id: int, story: Story, settings: ProjectSettings, t: float, width: int, height: int,
                 signals: PreviewSignals) -> None:
        super().__init__()
        self.request_id, self.story, self.t, self.width, self.height, self.signals = request_id, story, t, width, height, signals
        self.settings = copy.deepcopy(settings)

    def run(self) -> None:
        try:
            s = self.settings
            plan = render.plan_preview(self.story, s)
            t = min(self.t, max(0.0, plan.total - 0.01))
            bg = self._background(plan, t)
            comp = render.FrameComposer(plan, self.width, self.height)
            frame = comp.frame_at(t, bg)
            img = QImage(frame.data, frame.shape[1], frame.shape[0], frame.shape[1] * 3, QImage.Format.Format_RGB888).copy()
            self.signals.ready.emit(self.request_id, img, plan.total, len(plan.captions))
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(self.request_id, str(exc))

    def _background(self, plan: render.Plan, t: float) -> np.ndarray:
        s = self.settings
        bgp = plan.background
        if bgp.path:
            src_t = bgp.start + (t % bgp.src_duration if bgp.src_duration > 0 else t)
            key = (bgp.path, round(src_t * 2) / 2, self.width, self.height, s.fit)
            with _frame_lock:
                cached = _frame_cache.get(key)
            if cached is None:
                cached = bgmod.grab_frame(bgp.path, key[1], self.width, self.height, s.fit)
                if cached is not None:
                    with _frame_lock:
                        if len(_frame_cache) > 120:
                            _frame_cache.clear()
                        _frame_cache[key] = cached
            if cached is not None:
                return cached.copy()
        return bgmod.gradient_frame(self.width, self.height, s.background_rgb)


class VoiceListSignals(QObject):
    ready = Signal(str, list)        # provider, [(id, label)]
    failed = Signal(str, str)


class VoiceListJob(QRunnable):
    def __init__(self, provider: str, settings: ProjectSettings, signals: VoiceListSignals, refresh: bool) -> None:
        super().__init__()
        self.provider, self.settings, self.signals, self.refresh = provider, copy.deepcopy(settings), signals, refresh

    def run(self) -> None:
        try:
            if self.provider == "edge":
                voices = tts.list_edge_voices(refresh=self.refresh)
            else:
                voices = tts.list_elevenlabs_voices(tts.elevenlabs_api_key(self.settings))
            self.signals.ready.emit(self.provider, voices)
        except Exception as exc:  # noqa: BLE001
            try:
                self.signals.failed.emit(self.provider, str(exc))
            except RuntimeError:     # window already closed
                pass


class VoiceTestSignals(QObject):
    ready = Signal(str)              # path to the sample audio
    failed = Signal(str)


class VoiceTestJob(QRunnable):
    SAMPLE = "Hey! This is how your story is going to sound. Not bad, right?"

    def __init__(self, settings: ProjectSettings, signals: VoiceTestSignals, text: str | None = None) -> None:
        super().__init__()
        self.settings, self.signals = copy.deepcopy(settings), signals
        self.text = text or self.SAMPLE

    def run(self) -> None:
        try:
            folder = os.path.join(tempfile.gettempdir(), "trendyreels-voice-test")
            os.makedirs(folder, exist_ok=True)
            out = os.path.join(folder, "sample.wav")
            n = tts.synthesize(self.text, self.settings, out)
            self.signals.ready.emit(n.audio_path)
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(str(exc))
