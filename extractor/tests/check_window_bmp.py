#!/usr/bin/env python3
"""Decide whether a window screenshot is a drawn UI or a blank Tk window.

sips on macOS writes a BMP this script can read with the standard library.
A blank window (the macOS Tk failure mode) is nearly one colour. A drawn
form has text and controls, so a noticeable share of the content pixels
differ from the median.

  python tests/check_window_bmp.py --self-test
  python tests/check_window_bmp.py shot.bmp --crop-top-frac 0.14
"""

from __future__ import annotations

import argparse
import struct
import sys
import tempfile
from pathlib import Path


def write_bmp(path: Path, width: int, height: int, paint) -> None:
    """24-bit bottom-up BMP. paint(x, y_top) -> (r, g, b) with y_top 0 at the top."""
    row_stride = ((24 * width + 31) // 32) * 4
    pixels = bytearray()
    for y_bottom in range(height):
        y = height - 1 - y_bottom
        row = bytearray()
        for x in range(width):
            r, g, b = paint(x, y)
            row += bytes((b & 255, g & 255, r & 255))
        row += b"\x00" * (row_stride - width * 3)
        pixels += row
    header_size = 14 + 40
    size = header_size + len(pixels)
    blob = struct.pack("<2sIHHI", b"BM", size, 0, 0, header_size)
    blob += struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0, len(pixels), 2835, 2835, 0, 0)
    path.write_bytes(blob + pixels)


def load_luminance(path: Path, crop_top_frac: float) -> list[int]:
    data = path.read_bytes()
    if data[:2] != b"BM":
        raise SystemExit(f"{path} is not a BMP")
    pixel_off = struct.unpack_from("<I", data, 10)[0]
    width = struct.unpack_from("<i", data, 18)[0]
    height_raw = struct.unpack_from("<i", data, 22)[0]
    bpp = struct.unpack_from("<H", data, 28)[0]
    compression = struct.unpack_from("<I", data, 30)[0]
    if bpp not in (24, 32) or compression not in (0, 3):
        raise SystemExit(f"unsupported BMP bpp={bpp} compression={compression}")
    top_down = height_raw < 0
    height = abs(height_raw)
    if width < 40 or height < 40:
        raise SystemExit(f"window bitmap is too small ({width}x{height})")
    row_stride = ((bpp * width + 31) // 32) * 4
    channels = bpp // 8
    y0 = max(1, int(height * crop_top_frac))
    y1 = height - max(1, int(height * 0.03))
    x0 = max(1, int(width * 0.03))
    x1 = width - x0
    if y1 - y0 < 20 or x1 - x0 < 20:
        raise SystemExit(f"nothing left after cropping the title bar ({width}x{height})")
    samples: list[int] = []
    for y_top in range(y0, y1):
        src_y = y_top if top_down else (height - 1 - y_top)
        start = pixel_off + src_y * row_stride
        row = data[start:start + row_stride]
        for x in range(x0, x1):
            i = x * channels
            b, g, r = row[i], row[i + 1], row[i + 2]
            samples.append((r + g + b) // 3)
    return samples


def verdict(samples: list[int]) -> tuple[bool, str]:
    """True when the content area looks like a drawn form rather than a flat fill."""
    n = len(samples)
    if n < 100:
        return False, f"too few pixels ({n})"
    ordered = sorted(samples)
    median = ordered[n // 2]
    contrast = sum(1 for p in samples if abs(p - median) >= 40)
    frac = contrast / n
    lo, hi = ordered[0], ordered[-1]
    detail = f"median={median} range={lo}-{hi} contrast={frac:.4f} n={n}"
    if hi - lo < 25 or frac < 0.008:
        if hi < 25:
            kind = "blank-black"
        elif lo > 200:
            kind = "blank-light"
        else:
            kind = "blank-flat"
        return False, f"{kind} {detail}"
    return True, f"ok {detail}"


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="ppe_bmp_") as tmp:
        root = Path(tmp)

        def flat(colour):
            path = root / f"flat-{colour}.bmp"

            def paint(_x, _y, c=colour):
                return (c, c, c)

            write_bmp(path, 200, 120, paint)
            ok, msg = verdict(load_luminance(path, 0.14))
            if ok:
                raise SystemExit(f"flat image should fail: {msg}")

        flat(245)
        flat(0)
        flat(128)

        drawn = root / "drawn.bmp"

        def paint(x, y):
            if 30 <= y <= 42 and 20 <= x <= 160:
                return (20, 20, 20)
            if 70 <= y <= 88 and 20 <= x <= 170:
                return (230, 230, 230) if 22 <= x <= 168 and 72 <= y <= 86 else (80, 80, 80)
            return (245, 245, 245)

        write_bmp(drawn, 220, 140, paint)
        ok, msg = verdict(load_luminance(drawn, 0.14))
        if not ok:
            raise SystemExit(f"drawn image should pass: {msg}")

        border = root / "border.bmp"

        def paint_border(x, y, w=220, h=140):
            if x == 0 or y == 0 or x == w - 1 or y == h - 1:
                return (40, 40, 40)
            return (245, 245, 245)

        write_bmp(border, 220, 140, paint_border)
        ok, msg = verdict(load_luminance(border, 0.14))
        if ok:
            raise SystemExit(f"a hairline border should not count as a UI: {msg}")
    print("PASS check_window_bmp self-test")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("bmp", nargs="?", type=Path)
    ap.add_argument("--crop-top-frac", type=float, default=0.14)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        self_test()
        if args.bmp is None:
            return 0
    if args.bmp is None:
        ap.error("pass a BMP path, --self-test, or both")
    ok, msg = verdict(load_luminance(args.bmp, args.crop_top_frac))
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
