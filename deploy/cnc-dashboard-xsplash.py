#!/usr/bin/env python3
"""Draw a dependency-free X11 splash until the dashboard is on screen.

The window replicates the Plymouth theme and the dashboard startup-cover
layout, so the whole boot shows one continuous, animated frame. It stays
raised above Chromium's blank startup surfaces (Chromium commits empty frames
for seconds during a cold start) and removes itself only when app.js reports
the rendered dashboard by setting the window title to "CNC Dashboard bereit".
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import time

# Set by app.js the moment the startup cover is dismissed; the parse-time
# title (plain "CNC Dashboard") can be present while Chromium still shows
# blank frames.
DASHBOARD_READY_MARKER = b"CNC Dashboard bereit"
PAINT_GRACE_SECONDS = 0.35
MAX_COVER_SECONDS = 60.0

X = ctypes.CDLL(ctypes.util.find_library("X11") or "libX11.so.6")
CAIRO = ctypes.CDLL(ctypes.util.find_library("cairo") or "libcairo.so.2")

Display = ctypes.c_void_p
Window = ctypes.c_ulong
Atom = ctypes.c_ulong

X.XOpenDisplay.argtypes = [ctypes.c_char_p]
X.XOpenDisplay.restype = Display
X.XDefaultScreen.argtypes = [Display]
X.XDefaultScreen.restype = ctypes.c_int
X.XRootWindow.argtypes = [Display, ctypes.c_int]
X.XRootWindow.restype = Window
X.XDisplayWidth.argtypes = [Display, ctypes.c_int]
X.XDisplayWidth.restype = ctypes.c_int
X.XDisplayHeight.argtypes = [Display, ctypes.c_int]
X.XDisplayHeight.restype = ctypes.c_int
X.XBlackPixel.argtypes = [Display, ctypes.c_int]
X.XBlackPixel.restype = ctypes.c_ulong
X.XWhitePixel.argtypes = [Display, ctypes.c_int]
X.XWhitePixel.restype = ctypes.c_ulong
X.XCreateSimpleWindow.argtypes = [
    Display, Window, ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint,
    ctypes.c_uint, ctypes.c_ulong, ctypes.c_ulong,
]
X.XCreateSimpleWindow.restype = Window
X.XMapRaised.argtypes = [Display, Window]
X.XRaiseWindow.argtypes = [Display, Window]
X.XFlush.argtypes = [Display]
X.XSync.argtypes = [Display, ctypes.c_int]
X.XDestroyWindow.argtypes = [Display, Window]
X.XCloseDisplay.argtypes = [Display]
X.XStoreName.argtypes = [Display, Window, ctypes.c_char_p]
X.XSelectInput.argtypes = [Display, Window, ctypes.c_long]
X.XPending.argtypes = [Display]
X.XPending.restype = ctypes.c_int
X.XNextEvent.argtypes = [Display, ctypes.c_void_p]
X.XQueryTree.argtypes = [
    Display, Window, ctypes.POINTER(Window), ctypes.POINTER(Window),
    ctypes.POINTER(ctypes.POINTER(Window)), ctypes.POINTER(ctypes.c_uint),
]
X.XQueryTree.restype = ctypes.c_int
X.XFetchName.argtypes = [Display, Window, ctypes.POINTER(ctypes.c_char_p)]
X.XFetchName.restype = ctypes.c_int
X.XFree.argtypes = [ctypes.c_void_p]
X.XInternAtom.argtypes = [Display, ctypes.c_char_p, ctypes.c_int]
X.XInternAtom.restype = Atom
X.XGetWindowProperty.argtypes = [
    Display, Window, Atom, ctypes.c_long, ctypes.c_long, ctypes.c_int, Atom,
    ctypes.POINTER(Atom), ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
    ctypes.POINTER(ctypes.POINTER(ctypes.c_char)),
]
X.XGetWindowProperty.restype = ctypes.c_int

# Windows can vanish between XQueryTree and the name lookup; the default Xlib
# error handler would terminate the process, so ignore X errors entirely.
ERROR_HANDLER_TYPE = ctypes.CFUNCTYPE(ctypes.c_int, Display, ctypes.c_void_p)
IGNORE_X_ERRORS = ERROR_HANDLER_TYPE(lambda _display, _event: 0)
X.XSetErrorHandler.argtypes = [ERROR_HANDLER_TYPE]
X.XSetErrorHandler(IGNORE_X_ERRORS)

CAIRO.cairo_xlib_surface_create.argtypes = [Display, Window, ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
CAIRO.cairo_xlib_surface_create.restype = ctypes.c_void_p
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
CAIRO.cairo_destroy.argtypes = [ctypes.c_void_p]
CAIRO.cairo_surface_destroy.argtypes = [ctypes.c_void_p]


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


def window_name(display: Display, window: Window, net_wm_name: Atom, utf8_string: Atom) -> bytes:
    name_ptr = ctypes.c_char_p()
    if X.XFetchName(display, window, ctypes.byref(name_ptr)) and name_ptr.value:
        value = name_ptr.value
        X.XFree(name_ptr)
        return value

    actual_type = Atom()
    actual_format = ctypes.c_int()
    nitems = ctypes.c_ulong()
    bytes_after = ctypes.c_ulong()
    prop = ctypes.POINTER(ctypes.c_char)()
    status = X.XGetWindowProperty(
        display, window, net_wm_name, 0, 1024, 0, utf8_string,
        ctypes.byref(actual_type), ctypes.byref(actual_format),
        ctypes.byref(nitems), ctypes.byref(bytes_after), ctypes.byref(prop),
    )
    value = b""
    if status == 0 and prop and nitems.value:
        value = ctypes.string_at(prop, nitems.value)
    if prop:
        X.XFree(prop)
    return value


def dashboard_is_ready(display: Display, root: Window, own_window: Window,
                       net_wm_name: Atom, utf8_string: Atom) -> bool:
    tree_root = Window()
    tree_parent = Window()
    children = ctypes.POINTER(Window)()
    child_count = ctypes.c_uint()
    if not X.XQueryTree(display, root, ctypes.byref(tree_root), ctypes.byref(tree_parent),
                        ctypes.byref(children), ctypes.byref(child_count)):
        return False
    found = False
    try:
        for index in range(child_count.value):
            candidate = children[index]
            if candidate == own_window:
                continue
            if window_name(display, candidate, net_wm_name, utf8_string).startswith(DASHBOARD_READY_MARKER):
                found = True
                break
    finally:
        if children:
            X.XFree(children)
    return found


def main() -> int:
    display = X.XOpenDisplay(os.environ.get("DISPLAY", ":0").encode())
    if not display:
        return 1
    screen = X.XDefaultScreen(display)
    root = X.XRootWindow(display, screen)
    width = X.XDisplayWidth(display, screen)
    height = X.XDisplayHeight(display, screen)
    window = X.XCreateSimpleWindow(
        display, root, 0, 0, width, height, 0,
        X.XBlackPixel(display, screen), X.XWhitePixel(display, screen),
    )
    # The name must not match DASHBOARD_READY_MARKER, or the cover finds itself.
    X.XStoreName(display, window, b"cnc-boot-cover")
    EXPOSURE_MASK = 1 << 15
    X.XSelectInput(display, window, EXPOSURE_MASK)
    X.XMapRaised(display, window)

    # XDefaultVisual is a function on the target Raspberry Pi Xlib.
    X.XDefaultVisual.argtypes = [Display, ctypes.c_int]
    X.XDefaultVisual.restype = ctypes.c_void_p
    surface = CAIRO.cairo_xlib_surface_create(display, window, X.XDefaultVisual(display, screen), width, height)
    ctx = CAIRO.cairo_create(surface)

    center_x = width / 2
    center_y = height / 2
    bar_width = min(520.0, width * 0.8)
    bar_x = center_x - bar_width / 2
    bar_y = center_y + 67
    fill_width = bar_width * 0.34

    def draw_bar(phase: float) -> None:
        # Sliding loader in the same style as the CSS boot animation.
        CAIRO.cairo_set_source_rgb(ctx, 0.87, 0.87, 0.87)
        CAIRO.cairo_rectangle(ctx, bar_x, bar_y, bar_width, 4)
        CAIRO.cairo_fill(ctx)
        slide_start = bar_x - fill_width + (bar_width + fill_width) * phase
        left = max(bar_x, slide_start)
        right = min(bar_x + bar_width, slide_start + fill_width)
        if right > left:
            CAIRO.cairo_set_source_rgb(ctx, 0.0, 0.0, 0.0)
            CAIRO.cairo_rectangle(ctx, left, bar_y, right - left, 4)
            CAIRO.cairo_fill(ctx)

    def draw_frame(phase: float) -> None:
        CAIRO.cairo_set_source_rgb(ctx, 1.0, 1.0, 1.0)
        CAIRO.cairo_paint(ctx)

        CAIRO.cairo_set_source_rgb(ctx, 0.0, 0.0, 0.0)
        CAIRO.cairo_select_font_face(ctx, b"sans-serif", 0, 1)
        CAIRO.cairo_set_font_size(ctx, 52.0)
        centered_text(ctx, "CNC DASHBOARD", center_x, center_y - 48)

        CAIRO.cairo_set_source_rgb(ctx, 0.28, 0.28, 0.28)
        CAIRO.cairo_set_font_size(ctx, 14.0)
        centered_text(ctx, "M A S C H I N E N S T E U E R U N G", center_x, center_y + 4)

        draw_bar(phase)

        CAIRO.cairo_set_source_rgb(ctx, 0.0, 0.0, 0.0)
        CAIRO.cairo_set_font_size(ctx, 14.0)
        centered_text(ctx, "SYSTEM WIRD GESTARTET", center_x, center_y + 101)
        CAIRO.cairo_surface_flush(surface)

    draw_frame(0.34)
    X.XFlush(display)

    # Chromium maps its windows above this one, so keep re-raising the cover
    # until app.js reports the rendered dashboard. The window has no backing
    # store: every raise fight exposes (blanks) it, so watch for Expose events
    # and repaint the whole frame then; otherwise only animate the bar strip.
    net_wm_name = X.XInternAtom(display, b"_NET_WM_NAME", 0)
    utf8_string = X.XInternAtom(display, b"UTF8_STRING", 0)
    event_buffer = ctypes.create_string_buffer(256)
    started = time.monotonic()
    deadline = started + MAX_COVER_SECONDS
    ready_seen_at: float | None = None
    while True:
        now = time.monotonic()
        if now >= deadline:
            break
        if ready_seen_at is None:
            if dashboard_is_ready(display, root, window, net_wm_name, utf8_string):
                ready_seen_at = now
        elif now - ready_seen_at >= PAINT_GRACE_SECONDS:
            break
        X.XRaiseWindow(display, window)
        phase = ((now - started) % 1.6) / 1.6
        exposed = False
        while X.XPending(display):
            X.XNextEvent(display, event_buffer)
            exposed = True
        if exposed:
            draw_frame(phase)
        else:
            draw_bar(phase)
            CAIRO.cairo_surface_flush(surface)
        X.XFlush(display)
        time.sleep(0.1)

    CAIRO.cairo_destroy(ctx)
    CAIRO.cairo_surface_destroy(surface)
    X.XDestroyWindow(display, window)
    X.XSync(display, 0)
    X.XCloseDisplay(display)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
