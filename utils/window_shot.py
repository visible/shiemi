#!/usr/bin/env python3
"""Capture one window's pixels and nothing else.

  python3 utils/window_shot.py shot.png
  python3 utils/window_shot.py shot.png --title shiemi --crop-height 120

UI work has to be checked by looking at it, but a full-screen grab records
whatever else is open and needs the window in the foreground. PrintWindow asks
the window to draw itself, so it needs neither.

PNG is written by hand to keep this dependency free; --crop-height is there
because the tab strip is the top inch of the window.
"""

import argparse
import ctypes
import itertools
import struct
import zlib
from ctypes import wintypes
from pathlib import Path

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

PW_RENDERFULLCONTENT = 2
DIB_RGB_COLORS = 0
BI_RGB = 0


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


user32.GetWindowDC.restype = ctypes.c_void_p
user32.GetWindowDC.argtypes = [wintypes.HWND]
gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
gdi32.CreateDIBSection.restype = ctypes.c_void_p
gdi32.CreateDIBSection.argtypes = [ctypes.c_void_p, ctypes.POINTER(BITMAPINFO),
                                   wintypes.UINT, ctypes.POINTER(ctypes.c_void_p),
                                   ctypes.c_void_p, wintypes.DWORD]
gdi32.SelectObject.restype = ctypes.c_void_p
gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
user32.PrintWindow.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.UINT]
# Without argtypes the DC comes back as a Python int too wide for the default
# conversion, which fails only once a handle happens to be large.
user32.ReleaseDC.argtypes = [wintypes.HWND, ctypes.c_void_p]
user32.ReleaseDC.restype = ctypes.c_int


def find_window(needle: str):
    needle = needle.lower()
    matches = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if not length:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        if needle in buffer.value.lower():
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            matches.append((hwnd, buffer.value, rect))
        return True

    user32.EnumWindows(visit, 0)
    # Largest first, so tooltips and off-screen helper windows lose.
    matches.sort(key=lambda m: (m[2].right - m[2].left) * (m[2].bottom - m[2].top),
                 reverse=True)
    return matches[0] if matches else None


def capture(hwnd, rect):
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if width <= 0 or height <= 0:
        raise SystemExit("window has no area")

    window_dc = user32.GetWindowDC(hwnd)
    mem_dc = gdi32.CreateCompatibleDC(window_dc)

    info = BITMAPINFO()
    info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    info.bmiHeader.biWidth = width
    info.bmiHeader.biHeight = -height  # negative keeps the rows top down
    info.bmiHeader.biPlanes = 1
    info.bmiHeader.biBitCount = 32
    info.bmiHeader.biCompression = BI_RGB

    bits = ctypes.c_void_p()
    bitmap = gdi32.CreateDIBSection(mem_dc, ctypes.byref(info), DIB_RGB_COLORS,
                                    ctypes.byref(bits), None, 0)
    previous = gdi32.SelectObject(mem_dc, bitmap)
    ok = user32.PrintWindow(hwnd, mem_dc, PW_RENDERFULLCONTENT)
    pixels = ctypes.string_at(bits, width * height * 4)
    gdi32.SelectObject(mem_dc, previous)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(hwnd, window_dc)

    if not ok:
        raise SystemExit("PrintWindow refused to draw the window")
    return width, height, pixels


def write_png(path: Path, width: int, height: int, bgra: bytes) -> None:
    stride = width * 4
    rows = bytearray()
    for y in range(height):
        row = bgra[y * stride:(y + 1) * stride]
        rows.append(0)  # filter type none
        rows += bytes(itertools.chain.from_iterable(
            zip(row[2::4], row[1::4], row[0::4])))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(rows), 6))
        + chunk(b"IEND", b""))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("--title", default="shiemi",
                        help="substring of the window title")
    parser.add_argument("--crop-height", type=int,
                        help="keep only this many rows from the top")
    args = parser.parse_args()

    match = find_window(args.title)
    if not match:
        raise SystemExit(f"no visible window with {args.title!r} in the title")

    hwnd, title, rect = match
    width, height, pixels = capture(hwnd, rect)

    if args.crop_height and args.crop_height < height:
        height = args.crop_height
        pixels = pixels[:width * height * 4]

    write_png(args.out, width, height, pixels)
    print(f"{title}  {width}x{height} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
