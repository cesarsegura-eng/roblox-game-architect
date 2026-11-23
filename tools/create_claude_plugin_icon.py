"""Generate the reproducible RGA marketplace icon using only stdlib."""

from __future__ import annotations

import binascii
import struct
import zlib
from pathlib import Path

SIZE = 512
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "apps" / "claude-code-plugin" / "assets" / "icon.png"
NAVY = (15, 25, 43, 255)
EDGE = (38, 58, 82, 255)
TEAL = (80, 222, 196, 255)
GOLD = (255, 196, 93, 255)
WHITE = (241, 247, 255, 255)
pixels = bytearray(NAVY * (SIZE * SIZE))


def paint(x: int, y: int, color: tuple[int, int, int, int]) -> None:
    if 0 <= x < SIZE and 0 <= y < SIZE:
        offset = (y * SIZE + x) * 4
        pixels[offset : offset + 4] = bytes(color)


def rounded_rectangle(
    left: int, top: int, right: int, bottom: int, radius: int, color: tuple[int, int, int, int]
) -> None:
    for y in range(top, bottom):
        for x in range(left, right):
            nearest_x = min(max(x, left + radius), right - radius - 1)
            nearest_y = min(max(y, top + radius), bottom - radius - 1)
            if (x - nearest_x) ** 2 + (y - nearest_y) ** 2 <= radius**2:
                paint(x, y, color)


def diamond(cx: int, cy: int, rx: int, ry: int, color: tuple[int, int, int, int]) -> None:
    for y in range(cy - ry, cy + ry + 1):
        for x in range(cx - rx, cx + rx + 1):
            if abs(x - cx) * ry + abs(y - cy) * rx <= rx * ry:
                paint(x, y, color)


rounded_rectangle(20, 20, 492, 492, 92, EDGE)
rounded_rectangle(31, 31, 481, 481, 82, NAVY)
diamond(256, 140, 78, 52, TEAL)
diamond(256, 140, 42, 28, NAVY)
diamond(256, 140, 13, 9, GOLD)
rounded_rectangle(248, 170, 264, 216, 7, GOLD)

glyphs = {
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "G": ("01111", "10000", "10000", "10111", "10001", "10001", "01111"),
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
}
scale = 18
gap = 18
glyph_width = 5 * scale
start_x = (SIZE - (3 * glyph_width + 2 * gap)) // 2
start_y = 246
for glyph_index, letter in enumerate("RGA"):
    color = GOLD if letter == "G" else WHITE
    left = start_x + glyph_index * (glyph_width + gap)
    for row, pattern in enumerate(glyphs[letter]):
        for column, bit in enumerate(pattern):
            if bit == "1":
                for dy in range(scale):
                    for dx in range(scale):
                        paint(left + column * scale + dx, start_y + row * scale + dy, color)

diamond(190, 410, 32, 18, TEAL)
diamond(256, 410, 32, 18, GOLD)
diamond(322, 410, 32, 18, TEAL)


def chunk(kind: bytes, data: bytes) -> bytes:
    body = kind + data
    return (
        struct.pack(">I", len(data)) + body + struct.pack(">I", binascii.crc32(body) & 0xFFFFFFFF)
    )


raw = b"".join(b"\0" + pixels[y * SIZE * 4 : (y + 1) * SIZE * 4] for y in range(SIZE))
png = (
    b"\x89PNG\r\n\x1a\n"
    + chunk(b"IHDR", struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0))
    + chunk(b"IDAT", zlib.compress(raw, level=9))
    + chunk(b"IEND", b"")
)
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_bytes(png)
print(f"Generated {OUTPUT.relative_to(ROOT)} ({len(png)} bytes)")
