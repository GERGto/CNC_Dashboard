#!/usr/bin/env python3
"""Render the CNC boot splash once as a 1-bit XBM for xsetroot.

The kiosk sets this bitmap as the X root background in the very first
milliseconds of the session (`xsetroot -bitmap`), so the branded splash is
visible the moment Xorg takes over - long before the Python splash window or
Chromium can paint. Layout matches cnc-dashboard-xsplash.py and the
dashboard startup cover.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import sys

CAIRO = ctypes.CDLL(ctypes.util.find_library("cairo") or "libcairo.so.2")

CAIRO.cairo_image_surface_create.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
CAIRO.cairo_image_surface_create.restype = ctypes.c_void_p
CAIRO.cairo_image_surface_get_data.argtypes = [ctypes.c_void_p]
CAIRO.cairo_image_surface_get_data.restype = ctypes.POINTER(ctypes.c_ubyte)
CAIRO.cairo_image_surface_get_stride.argtypes = [ctypes.c_void_p]
CAIRO.cairo_image_surface_get_stride.restype = ctypes.c_int
CAIRO.cairo_create.argtypes = [ctypes.c_void_p]
CAIRO.cairo_create.restype = ctypes.c_void_p
CAIRO.cairo_set_source_rgb.argtypes = [ctypes.c_void_p, ctypes.c_double, ctypes.c_double, ctypes.c_double]
CAIRO.cairo_paint.argtypes = [ctypes.c_void_p]
CAIRO.cairo_select_font_face.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
CAIRO.cairo_set_font_size.argtypes = [ctypes.c_void_p, ctypes.c_double]
CAIRO.cairo_move_to.argtypes = [ctypes.c_void_p, ctypes.c_double, ctypes.c_double]
CAIRO.cairo_show_text.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
CAIRO.cairo_text_extents.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p]
CAIRO.cairo_rectangle.argtypes = [ctypes.c_void_p, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double]
CAIRO.cairo_fill.argtypes = [ctypes.c_void_p]
CAIRO.cairo_surface_flush.argtypes = [ctypes.c_void_p]

CAIRO_FORMAT_RGB24 = 1


class TextExtents(ctypes.Structure):
    _fields_ = [(name, ctypes.c_double) for name in (
        "x_bearing", "y_bearing", "width", "height", "x_advance", "y_advance"
    )]


def centered_text(ctx: ctypes.c_void_p, text: str, center_x: float, baseline: float) -> None:
    encoded = text.encode("utf-8")
    extents = TextExtents()
    CAIRO.cairo_text_extents(ctx, encoded, ctypes.byref(extents))
    CAIRO.cairo_move_to(ctx, center_x - extents.width / 2 - extents.x_bearing, baseline)
    CAIRO.cairo_show_text(ctx, encoded)


def render(width: int, height: int) -> tuple[ctypes.c_void_p, ctypes.c_void_p]:
    surface = CAIRO.cairo_image_surface_create(CAIRO_FORMAT_RGB24, width, height)
    ctx = CAIRO.cairo_create(surface)

    CAIRO.cairo_set_source_rgb(ctx, 1.0, 1.0, 1.0)
    CAIRO.cairo_paint(ctx)
    center_x = width / 2
    center_y = height / 2

    CAIRO.cairo_set_source_rgb(ctx, 0.0, 0.0, 0.0)
    CAIRO.cairo_select_font_face(ctx, b"sans-serif", 0, 1)
    CAIRO.cairo_set_font_size(ctx, 52.0)
    centered_text(ctx, "CNC DASHBOARD", center_x, center_y - 48)

    CAIRO.cairo_set_font_size(ctx, 14.0)
    centered_text(ctx, "M A S C H I N E N S T E U E R U N G", center_x, center_y + 4)

    bar_width = min(520.0, width * 0.8)
    bar_x = center_x - bar_width / 2
    # 1-bit output has no grey: draw only the dark fill segment of the bar.
    CAIRO.cairo_rectangle(ctx, bar_x, center_y + 67, bar_width * 0.34, 4)
    CAIRO.cairo_fill(ctx)
    centered_text(ctx, "SYSTEM WIRD GESTARTET", center_x, center_y + 101)
    CAIRO.cairo_surface_flush(surface)
    return surface, ctx


def to_xbm(surface: ctypes.c_void_p, width: int, height: int, name: str) -> str:
    data = CAIRO.cairo_image_surface_get_data(surface)
    stride = CAIRO.cairo_image_surface_get_stride(surface)
    row_bytes = (width + 7) // 8
    out = [f"#define {name}_width {width}", f"#define {name}_height {height}",
           f"static unsigned char {name}_bits[] = {{"]
    body: list[str] = []
    for y in range(height):
        row = bytearray(row_bytes)
        base = y * stride
        for x in range(width):
            # RGB24 pixels are 32-bit native-endian; green sits at byte 1.
            green = data[base + x * 4 + 1]
            if green < 128:
                row[x >> 3] |= 1 << (x & 7)
        body.extend(f"0x{b:02x}" for b in row)
    for i in range(0, len(body), 12):
        out.append(" " + ", ".join(body[i:i + 12]) + ("," if i + 12 < len(body) else ""))
    out.append("};")
    return "\n".join(out) + "\n"


def main() -> None:
    output = sys.argv[1]
    width = int(sys.argv[2]) if len(sys.argv) > 2 else 1024
    height = int(sys.argv[3]) if len(sys.argv) > 3 else 600
    surface, _ctx = render(width, height)
    xbm = to_xbm(surface, width, height, "cnc_splash")
    with open(output, "w", encoding="ascii") as handle:
        handle.write(xbm)


if __name__ == "__main__":
    main()
