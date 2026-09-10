from __future__ import annotations

import json
import math
import os
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageSequence

ROOT = Path("sample/humanoid_motion/mixamo/walker-walk")
ANIMATION = ROOT / "animation.json"
PREVIEW = ROOT / "preview.gif"

EXPECTED_ANIMATION_BLOB = "91353bc01b3686fef36e7ac226f20d1564d6a95e"
EXPECTED_PREVIEW_BLOB = "c0695bee90e09e8301cb18c9309422757f2e7cd9"


def git_blob(path: Path) -> str:
    return subprocess.check_output(["git", "hash-object", str(path)], text=True).strip()


assert git_blob(ANIMATION) == EXPECTED_ANIMATION_BLOB
assert git_blob(PREVIEW) == EXPECTED_PREVIEW_BLOB

doc = json.loads(ANIMATION.read_text(encoding="utf-8"))
assert doc["id"] == "walker-walk"
assert doc["frameCount"] == 112
assert doc["fps"] == 30.0
assert doc["durationSeconds"] == 3.7

with Image.open(PREVIEW) as gif:
    frames = [frame.convert("RGB").copy() for frame in ImageSequence.Iterator(gif)]
assert len(frames) == 112

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_SMALL = ImageFont.truetype(FONT, 16)
FONT_TINY = ImageFont.truetype(FONT, 14)
FONT_BOLD = ImageFont.truetype(BOLD, 22)
FONT_TITLE = ImageFont.truetype(BOLD, 28)

CROP = (38, 2, 186, 224)
IMG_W, IMG_H = 296, 444


def wrapped(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        test = (current + " " + word).strip()
        if draw.textbbox((0, 0), test, font=font)[2] <= width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def card(frame_no: int, role: str, footer: list[str] | None = None, seq: int | None = None, height: int = 560) -> Image.Image:
    out = Image.new("RGB", (330, height), "white")
    draw = ImageDraw.Draw(out)
    header = f"f{frame_no}" if seq is None else f"{seq}.  f{frame_no}"
    draw.text((14, 10), header, fill="black", font=FONT_BOLD)
    y = 40
    for line in wrapped(draw, role, FONT_SMALL, 302)[:2]:
        draw.text((14, y), line, fill="black", font=FONT_SMALL)
        y += 20
    image = frames[frame_no].crop(CROP).resize((IMG_W, IMG_H), Image.Resampling.NEAREST)
    out.paste(image, ((330 - IMG_W) // 2, 82))
    y = 82 + IMG_H + 8
    for text in footer or []:
        for line in wrapped(draw, text, FONT_TINY, 302):
            draw.text((14, y), line, fill="black", font=FONT_TINY)
            y += 17
    return out


def sheet(cards: list[Image.Image], title: str, cols: int) -> Image.Image:
    gap, margin, title_h = 12, 18, 52
    rows = math.ceil(len(cards) / cols)
    cw = max(item.width for item in cards)
    ch = max(item.height for item in cards)
    width = margin * 2 + cols * cw + (cols - 1) * gap
    height = title_h + margin + rows * ch + (rows - 1) * gap + margin
    out = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(out)
    draw.text((margin, 10), title, fill="black", font=FONT_TITLE)
    for i, item in enumerate(cards):
        row, col = divmod(i, cols)
        out.paste(item, (margin + col * (cw + gap), title_h + margin + row * (ch + gap)))
    return out


def save_evidence(image: Image.Image, name: str) -> None:
    # Palette PNG keeps review evidence small while preserving labels and source pixels.
    image.convert("P", palette=Image.Palette.ADAPTIVE, colors=128).save(ROOT / name, optimize=True)


phase_specs = [
    (0, "Tiếp tục swing chân trái qua seam"),
    (8, "Kết thúc/settle bước chân trái"),
    (9, "Bắt đầu chuyển tải sang bước phải"),
    (44, "Kết thúc chuẩn bị bước chân phải"),
    (45, "Bắt đầu nhấc/swing chân phải"),
    (57, "Đỉnh swing chân phải"),
    (58, "Bắt đầu duỗi/hạ chân phải"),
    (66, "Settle bước chân phải"),
    (67, "Bắt đầu chuyển tải sang bước trái"),
    (99, "Kết thúc chuẩn bị bước chân trái"),
    (100, "Bắt đầu nhấc/swing chân trái"),
    (111, "Swing trái tiếp tục → f0"),
]
save_evidence(sheet([card(f, role) for f, role in phase_specs], "phases — walker-walk (boundary evidence)", 4), "phases.png")

key_specs = [
    (8, "Settle bước chân trái"),
    (42, "Root xoay cực trị; anticipation bước phải"),
    (57, "Đỉnh swing chân phải"),
    (66, "Settle bước chân phải"),
    (95, "Anticipation bước chân trái"),
    (108, "Đỉnh swing chân trái"),
]
save_evidence(sheet([card(f, role) for f, role in key_specs], "key poses — walker-walk", 3), "key-poses.png")

weight_specs = [
    (8, "Settle trái", "hips T  X +0.0206 | Y -0.0354 | Z -0.0421"),
    (40, "Trước swing phải", "hips T  X +0.0410 | Y +0.1464 | Z -0.0288"),
    (53, "Swing phải", "hips T  X +0.0688 (lateral max) | Y +0.0185 | Z -0.0337"),
    (66, "Settle phải", "hips T  X +0.0457 | Y -0.0507 | Z -0.0460"),
    (95, "Trước swing trái", "hips T  X +0.0164 | Y +0.1123 | Z -0.0385"),
    (108, "Swing trái", "hips T  X +0.0015 | Y +0.0128 | Z -0.0355"),
]
save_evidence(
    sheet([card(f, role, [metrics], height=590) for f, role, metrics in weight_specs], "weight transfer — pelvis/hips translation proxy", 3),
    "weight-transfer.png",
)

body_specs = [
    (42, "Root rotation cực trị", ["root rotvec Z = -9.30° (cycle min)"]),
    (44, "Hai tay counter-swing", ["R upper-arm Z = +34.88° (max)", "L upper-arm Z = -6.60° (local min)"]),
    (51, "Chân phải tiến vào swing", ["R upper-leg rotvec X = +13.55° (max)"]),
    (56, "Foot phải đạt cực trị gập", ["R foot rotvec X = +39.62° (max)"]),
    (57, "Gối/chân dưới phải đạt đỉnh", ["R lower-leg rotvec X = +38.49° (max)"]),
    (62, "Hips–spine–chest flex cực trị", ["rotvec X = +16.87° / +18.99° / +27.40°"]),
    (66, "Pelvis hạ và bước settle", ["hips Y = -0.0507; Z = -0.0460 (local minima)"]),
]
save_evidence(
    sheet([card(f, role, footer, seq=i + 1, height=610) for i, (f, role, footer) in enumerate(body_specs)], "body mechanics — observed sequence for the right step", 4),
    "body-mechanics.png",
)
