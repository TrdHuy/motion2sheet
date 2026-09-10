from __future__ import annotations

import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageSequence

ROOT = Path("sample/humanoid_motion/mixamo/walker-walk")
PREVIEW = ROOT / "preview.gif"
OUTPUT = ROOT / "body-mechanics.png"
EXPECTED_PREVIEW_BLOB = "c0695bee90e09e8301cb18c9309422757f2e7cd9"


def git_blob(path: Path) -> str:
    return subprocess.check_output(["git", "hash-object", str(path)], text=True).strip()


assert git_blob(PREVIEW) == EXPECTED_PREVIEW_BLOB
with Image.open(PREVIEW) as gif:
    frames = [frame.convert("RGB").copy() for frame in ImageSequence.Iterator(gif)]
assert len(frames) == 112

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_SMALL = ImageFont.truetype(FONT, 15)
FONT_BOLD = ImageFont.truetype(BOLD, 20)
FONT_TITLE = ImageFont.truetype(BOLD, 26)
CROP = (38, 2, 186, 224)


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


def card(frame_no: int, role: str, footer: list[str] | None = None, height: int = 560) -> Image.Image:
    out = Image.new("RGB", (300, height), "white")
    draw = ImageDraw.Draw(out)
    draw.text((12, 8), f"f{frame_no}", fill="black", font=FONT_BOLD)
    y = 36
    for line in wrapped(draw, role, FONT_SMALL, 276)[:3]:
        draw.text((12, y), line, fill="black", font=FONT_SMALL)
        y += 18
    image = frames[frame_no].crop(CROP).resize((270, 405), Image.Resampling.NEAREST)
    out.paste(image, (15, 96))
    y = 510
    for text in footer or []:
        for line in wrapped(draw, text, FONT_SMALL, 276):
            draw.text((12, y), line, fill="black", font=FONT_SMALL)
            y += 18
    return out


specs = [
    (32, "Hai tay gập, giữ trước thân", ["Không thấy tay nào vung rõ ra sau"]),
    (44, "Root xoay mạnh; tay vẫn giữ trước", ["Biến đổi tay bất đối xứng ≠ counter-swing rõ"]),
    (57, "Chân phải ở đỉnh swing", ["Hai tay vẫn ở tư thế gập phía trước"]),
    (66, "Bước phải settle", ["Tư thế tay gập phía trước vẫn duy trì"]),
    (80, "Chuyển tải sang bước trái", ["Không xuất hiện backward arm swing rõ"]),
    (95, "Anticipation bước trái", ["Hai tay tiếp tục giữ gần/phía trước thân"]),
    (51, "Upper-leg phải tiến vào swing", []),
    (56, "Foot phải đạt cực trị gập", []),
    (62, "Hips–spine–chest flex mạnh", []),
]

cards = [card(*spec) for spec in specs]
cols = 3
gap = 12
margin = 18
title_h = 56
card_w = 300
card_h = 560
rows = math.ceil(len(cards) / cols)
out = Image.new(
    "RGB",
    (margin * 2 + cols * card_w + (cols - 1) * gap, title_h + margin + rows * card_h + (rows - 1) * gap + margin),
    "white",
)
draw = ImageDraw.Draw(out)
draw.text((margin, 10), "body mechanics — walker-walk (arm posture correction)", fill="black", font=FONT_TITLE)
for index, item in enumerate(cards):
    row, col = divmod(index, cols)
    out.paste(item, (margin + col * (card_w + gap), title_h + margin + row * (card_h + gap)))

out.convert("P", palette=Image.Palette.ADAPTIVE, colors=128).save(OUTPUT, optimize=True)
