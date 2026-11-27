"""Reproduce the install icons using the standard library."""
import math
import struct
import zlib
from pathlib import Path


def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def icon(size):
    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            dx, dy = (x + .5) / size - .5, (y + .5) / size - .5
            r, angle = math.hypot(dx, dy), math.atan2(dy, dx)
            color = (19, 47 + int(29 * y / size), 113 + int(49 * x / size))
            sweep = (angle + 0.86) % (2 * math.pi)
            if r < .35 and sweep < 1.02:
                color = (35, 92 + int(47 * (1 - sweep)), 183 + int(27 * (1 - sweep)))
            if min(abs(r - .15), abs(r - .248), abs(r - .344)) < .008:
                color = (98, 169, 244)
            if r < .344 and min(abs(dx), abs(dy)) < .0035:
                color = (67, 120, 211)
            if r < .35 and abs(sweep) < .04 or r < .033 or math.hypot(dx - .163, dy + .189) < .035:
                color = (171, 255, 229)
            row.extend(color)
        rows.append(bytes(row))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)) + chunk(
        b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b"")


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent / "radar" / "static" / "radar"
    for side in (192, 512):
        (root / f"icon-{side}.png").write_bytes(icon(side))
