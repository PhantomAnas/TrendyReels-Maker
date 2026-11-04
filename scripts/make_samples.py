"""Generate demo background footage (moving shapes, no real gameplay) and a
sample story file, for the screenshot and for trying the app without any
footage of your own.

    python scripts/make_samples.py [out_dir]

Needs FFmpeg on PATH.
"""

from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from trendyreels import ffmpeg as ff  # noqa: E402
from trendyreels.batch import SAMPLE_STORY  # noqa: E402

STORIES = """My neighbour's cat has been stealing my socks for a year -- {body}
I accidentally became the office plant whisperer -- Nobody told me the plants were dying. I just started watering them on my way to the coffee machine. Three months later people leave sticky notes on the pots asking for advice. I do not know anything about plants. I am now in charge of the plants.
"""


def make_clip(path: str, seconds: float, seed: int) -> None:
    """A slow-moving abstract clip: drifting colour gradient with soft shapes."""
    expr = (f"gradients=size=720x1280:duration={seconds}:rate=30:speed=0.03:nb_colors=5:seed={seed},"
            f"hue=h=t*6,format=yuv420p")
    ff.run(["-f", "lavfi", "-i", expr, "-f", "lavfi", "-i", "anoisesrc=color=brown:amplitude=0.03:duration=" + str(seconds),
            "-t", str(seconds), "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-c:a", "aac", "-shortest", path])


def main(out_dir: str) -> None:
    os.makedirs(os.path.join(out_dir, "footage"), exist_ok=True)
    for i, seconds in enumerate((20, 25), start=1):
        make_clip(os.path.join(out_dir, "footage", f"abstract_{i}.mp4"), seconds, seed=i * 7)
    with open(os.path.join(out_dir, "stories.txt"), "w", encoding="utf-8") as fh:
        fh.write(STORIES.format(body=SAMPLE_STORY.body))
    print("wrote", out_dir)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "samples"))
