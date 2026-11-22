"""Record the README demo: a real `datasetvet check` run, as an asciicast and a GIF.

    python tools/record_demo.py              writes docs/demo/demo.cast and docs/demo/demo.gif

The run is real (network, uncached, anonymous); nothing is typed in by a script and nothing is
edited afterwards. Output is captured from pipes with the time each chunk arrived, written as an
asciicast v2 file (replay: `asciinema play docs/demo/demo.cast`, or upload it with your own
asciinema login), and drawn to a GIF with pyte (terminal emulation) and Pillow.
Needs `pip install pyte pillow` (not dependencies of datasetvet) and a Windows font path.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pyte
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "demo"
CMD = ["datasetvet", "check", "hf:tatsu-lab/alpaca", "--no-links", "--no-evidence", "--no-cache"]
COLS, ROWS = 110, 50
FONT = "C:/Windows/Fonts/consola.ttf"
SIZE = 15
BG, FG = (24, 24, 27), (228, 228, 231)
PALETTE = {"black": (24, 24, 27), "red": (239, 68, 68), "green": (74, 222, 128),
           "brown": (250, 204, 21), "blue": (96, 165, 250), "magenta": (232, 121, 249),
           "cyan": (34, 211, 238), "white": (228, 228, 231), "default": FG,
           "brightblack": (113, 113, 122), "brightwhite": (250, 250, 250)}


def record() -> list[tuple[float, str]]:
    env = dict(os.environ, FORCE_COLOR="1", COLUMNS=str(COLS), LINES=str(ROWS),
               PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8", HF_TOKEN_PATH="/nonexistent")
    env.pop("HF_TOKEN", None)
    events: list[tuple[float, str]] = []
    start = time.monotonic()
    proc = subprocess.Popen(CMD, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                            cwd=ROOT)

    def pump() -> None:
        assert proc.stdout
        while chunk := proc.stdout.read1(4096):  # type: ignore[attr-defined]
            events.append((time.monotonic() - start, chunk.decode("utf-8", "replace")))

    t = threading.Thread(target=pump)
    t.start()
    proc.wait()
    t.join()
    return events


def crlf(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\n", "\r\n")


def write_cast(events: list[tuple[float, str]]) -> None:
    header = {"version": 2, "width": COLS, "height": ROWS, "timestamp": int(time.time()),
              "title": "datasetvet check hf:tatsu-lab/alpaca",
              "env": {"TERM": "xterm-256color"}}
    lines = [json.dumps(header), json.dumps([0.0, "o", "$ " + " ".join(CMD) + "\r\n"])]
    lines += [json.dumps([round(t + 0.5, 3), "o", crlf(text)]) for t, text in events]
    (OUT / "demo.cast").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def colour(name: str, default: tuple[int, int, int]) -> tuple[int, int, int]:
    if name in PALETTE:
        return PALETTE[name]
    if len(name) == 6:
        try:
            return (int(name[0:2], 16), int(name[2:4], 16), int(name[4:6], 16))
        except ValueError:
            pass
    return default


def render(events: list[tuple[float, str]]) -> None:
    font = ImageFont.truetype(FONT, SIZE)
    cw = int(font.getlength("M"))
    ch = SIZE + 4
    screen = pyte.Screen(COLS, ROWS)
    stream = pyte.Stream(screen)
    stream.feed("$ " + " ".join(CMD) + "\r\n")

    def frame() -> Image.Image:
        img = Image.new("RGB", (COLS * cw + 20, ROWS * ch + 20), BG)
        d = ImageDraw.Draw(img)
        for y in range(ROWS):
            line = screen.buffer[y]
            for x in range(COLS):
                c = line[x]
                if c.data == " " and c.bg == "default":
                    continue
                if c.bg != "default":
                    d.rectangle([10 + x * cw, 10 + y * ch, 10 + (x + 1) * cw, 10 + (y + 1) * ch],
                                fill=colour(c.bg, BG))
                d.text((10 + x * cw, 10 + y * ch), c.data, font=font, fill=colour(c.fg, FG))
        return img

    frames = [frame()]
    durations = [600]
    last = 0.0
    for i, (t, text) in enumerate(events):
        stream.feed(crlf(text))
        if t - last >= 0.08 or i == len(events) - 1:
            frames.append(frame())
            durations.append(max(40, int((t - last) * 1000)))
            last = t
    durations[-1] = 6000  # hold the last screen
    frames[0].save(OUT / "demo.gif", save_all=True, append_images=frames[1:], duration=durations,
                   loop=0, optimize=True)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    ev = record()
    print(f"{len(ev)} chunks over {ev[-1][0]:.1f} s")
    write_cast(ev)
    render(ev)
    print("wrote", OUT / "demo.cast", OUT / "demo.gif")
    sys.exit(0)
