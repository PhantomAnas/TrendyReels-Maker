"""Render a queue of stories with one settings object; shared by the GUI and the CLI."""

from __future__ import annotations

import datetime as dt
import os
import shutil
import tempfile

from . import ffmpeg as ff
from .render import RenderCancelled, RenderError, build_plan, render
from .settings import ProjectSettings
from .text import Story, safe_filename


def output_path(story: Story, s: ProjectSettings, index: int, taken: set[str] | None = None) -> str:
    folder = s.default_output_folder()
    name = safe_filename(story.title or story.body[:60], fallback=f"story {index + 1}")
    if s.timestamp_names:
        name += dt.datetime.now().strftime(" %Y-%m-%d %H%M%S")
    path = os.path.join(folder, name + ".mp4")
    n = 2
    while taken is not None and path.lower() in taken:
        path = os.path.join(folder, f"{name} ({n}).mp4")
        n += 1
    if taken is not None:
        taken.add(path.lower())
    return path


def run_job(stories: list[Story], s: ProjectSettings, log=None, stage=None, progress=None, cancelled=None) -> list[str]:
    """Render every story.  Existing outputs are skipped when `skip_existing`
    is on (so an interrupted batch can simply be run again).  A story that
    fails is logged and the batch carries on; if every story failed the last
    error is raised."""
    log = log or (lambda m: None)
    stage = stage or (lambda m: None)
    stories = [st for st in stories if not st.is_empty()]
    if not stories:
        raise RenderError("no stories to render")
    problems = s.validate()
    if problems:
        raise RenderError("; ".join(problems))
    ff.require_ffmpeg()
    out_dir = s.default_output_folder()
    os.makedirs(out_dir, exist_ok=True)
    work_root = tempfile.mkdtemp(prefix="trendyreels-")
    outputs: list[str] = []
    errors: list[str] = []
    taken: set[str] = set()
    try:
        for i, story in enumerate(stories):
            if cancelled and cancelled():
                raise RenderCancelled()
            out = output_path(story, s, i, taken)
            label = f"{i + 1}/{len(stories)} {story.label[:50]}"
            if s.skip_existing and os.path.exists(out) and not s.timestamp_names:
                log(f"skip {label}: {os.path.basename(out)} already exists")
                outputs.append(out)
                continue
            workdir = os.path.join(work_root, f"story{i + 1}")
            try:
                stage(f"{label}: voice and timings")
                plan = build_plan(story, s, workdir, i, log=log, cancelled=cancelled)
                stage(f"{label}: rendering {plan.total:.0f}s")
                render(plan, out, log=log, progress=progress, cancelled=cancelled)
                outputs.append(out)
            except RenderCancelled:
                raise
            except RenderError as exc:
                errors.append(f"{story.label[:40]}: {exc}")
                log(f"error in {label}: {exc}")
            finally:
                shutil.rmtree(workdir, ignore_errors=True)
    finally:
        shutil.rmtree(work_root, ignore_errors=True)
    if errors and not outputs:
        raise RenderError(errors[-1] if len(errors) == 1 else f"{len(errors)} stories failed; last error: {errors[-1]}")
    if errors:
        log(f"{len(errors)} of {len(stories)} stories failed")
    return outputs


SAMPLE_STORY = Story(
    "My neighbour's cat has been stealing my socks for a year",
    "So for about a year now, one sock from every pair I own has been vanishing. I blamed the dryer, like everyone does. "
    "Last week I came home early and found the neighbour's cat on my balcony with a sock in its mouth, calm as anything. "
    "I followed it to the fence. Behind their shed there is a pile. Dozens of socks. Mine, and clearly other people's too. "
    "I rang the doorbell and the neighbour just sighed and said, 'you found the pile'. "
    "They have known for months. We are now organising a street-wide sock return. "
    "The cat is not sorry.",
    source="sample",
)
