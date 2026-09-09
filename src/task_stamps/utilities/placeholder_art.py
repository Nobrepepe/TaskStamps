"""Generate placeholder PNG images and WAV sounds using only the stdlib.

Used by the test suite so no binary
assets need to be bundled with the project.
"""

from __future__ import annotations

import math
import struct
import wave
import zlib
from pathlib import Path

# 3x5 bitmap digit font, rows top to bottom.
_DIGITS: dict[str, tuple[int, ...]] = {
    "0": (0b111, 0b101, 0b101, 0b101, 0b111),
    "1": (0b010, 0b110, 0b010, 0b010, 0b111),
    "2": (0b111, 0b001, 0b111, 0b100, 0b111),
    "3": (0b111, 0b001, 0b111, 0b001, 0b111),
    "4": (0b101, 0b101, 0b111, 0b001, 0b001),
    "5": (0b111, 0b100, 0b111, 0b001, 0b111),
    "6": (0b111, 0b100, 0b111, 0b101, 0b111),
    "7": (0b111, 0b001, 0b010, 0b010, 0b010),
    "8": (0b111, 0b101, 0b111, 0b101, 0b111),
    "9": (0b111, 0b101, 0b111, 0b001, 0b111),
}

RGB = tuple[int, int, int]


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def write_png(path: Path, width: int, height: int, pixels: list[list[RGB]]) -> None:
    """Write an RGB PNG from a row-major pixel grid."""
    raw = bytearray()
    for row in pixels:
        raw.append(0)  # no filter
        for r, g, b in row:
            raw.extend((r, g, b))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    payload = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(bytes(raw), 6))
        + _png_chunk(b"IEND", b"")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _digit_mask(text: str, width: int, height: int) -> list[list[bool]]:
    """Rasterize digits centered into a width x height boolean grid."""
    glyph_w, glyph_h, gap = 3, 5, 1
    total_w = len(text) * glyph_w + (len(text) - 1) * gap
    cell = max(1, min(width // (total_w + 2), height // (glyph_h + 2)))
    x0 = (width - total_w * cell) // 2
    y0 = (height - glyph_h * cell) // 2
    mask = [[False] * width for _ in range(height)]
    for index, char in enumerate(text):
        rows = _DIGITS[char]
        gx = x0 + index * (glyph_w + gap) * cell
        for row_index, bits in enumerate(rows):
            for col in range(glyph_w):
                if bits & (1 << (glyph_w - 1 - col)):
                    for dy in range(cell):
                        for dx in range(cell):
                            y = y0 + row_index * cell + dy
                            x = gx + col * cell + dx
                            if 0 <= y < height and 0 <= x < width:
                                mask[y][x] = True
    return mask


def _darken(color: RGB, factor: float) -> RGB:
    return tuple(int(component * factor) for component in color)  # type: ignore[return-value]


def render_stamp_png(
    path: Path, number: int, base_color: RGB, width: int = 160, height: int = 120
) -> None:
    """Landscape 4:3 stamp placeholder showing its sequence number."""
    border = _darken(base_color, 0.55)
    ink = _darken(base_color, 0.35)
    mask = _digit_mask(str(number), width, height)
    pixels: list[list[RGB]] = []
    for y in range(height):
        row: list[RGB] = []
        for x in range(width):
            if x < 4 or y < 4 or x >= width - 4 or y >= height - 4:
                row.append(border)
            elif mask[y][x]:
                row.append(ink)
            else:
                row.append(base_color)
        pixels.append(row)
    write_png(path, width, height, pixels)


def render_portrait_png(
    path: Path, base_color: RGB, width: int = 120, height: int = 160
) -> None:
    """Portrait 3:4 placeholder with a simple silhouette."""
    border = _darken(base_color, 0.55)
    ink = _darken(base_color, 0.4)
    cx, head_cy, head_r = width / 2, height * 0.38, width * 0.2
    pixels: list[list[RGB]] = []
    for y in range(height):
        row: list[RGB] = []
        for x in range(width):
            if x < 4 or y < 4 or x >= width - 4 or y >= height - 4:
                row.append(border)
            elif (x - cx) ** 2 + (y - head_cy) ** 2 <= head_r**2:
                row.append(ink)  # head
            elif y > height * 0.55 and abs(x - cx) < (y - height * 0.55) * 0.9 + width * 0.08:
                row.append(ink)  # shoulders
            else:
                row.append(base_color)
        pixels.append(row)
    write_png(path, width, height, pixels)


def render_hatch_png(path: Path, size: int = 16) -> None:
    """Small warm-white diagonal hatch tile used by missing-art masks."""
    floor = (18, 16, 15)
    line = (44, 41, 38)
    pixels = [
        [line if (x - y) % 8 == 0 else floor for x in range(size)]
        for y in range(size)
    ]
    write_png(path, size, size, pixels)


def render_beep_wav(path: Path, frequency: float = 660.0, duration: float = 0.18) -> None:
    """Short sine beep with a soft decay envelope."""
    rate = 22050
    frames = int(rate * duration)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        data = bytearray()
        for i in range(frames):
            envelope = 1.0 - i / frames
            value = int(20000 * envelope * math.sin(2 * math.pi * frequency * i / rate))
            data.extend(struct.pack("<h", value))
        handle.writeframes(bytes(data))
