#!/usr/bin/env python3
"""Capture one window's pixels and nothing else.

  python3 utils/window_shot.py shot.png --pid 1234
  python3 utils/window_shot.py shot.png --title Shiemi --crop-height 120

UI work has to be checked by looking at it, but a full-screen grab records
whatever else is open and needs the window in the foreground. PrintWindow asks
the window to draw itself, so it needs neither.

Prefer --pid: a title match will happily find an editor with the product name
in its tab, and the largest window wins.

A browser launched behind another window comes back as a blank rectangle:
Chromium stops painting a window it believes is occluded. Launch it with
--disable-features=CalculateNativeWinOcclusion to capture without raising it.

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


def owner_pid(hwnd) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def find_window(needle: str | None = None, pid: int | None = None,
                untitled: bool = False):
    needle = needle.lower() if needle else None
    matches = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        # Menus and other popups carry no title, so they are skipped unless
        # asked for: without this a title match picks the browser window.
        if not length and not untitled:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        if needle and needle not in buffer.value.lower():
            return True
        if pid is not None and owner_pid(hwnd) != pid:
            return True
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        matches.append((hwnd, buffer.value, rect))
        return True

    user32.EnumWindows(visit, 0)
    # Largest first, so tooltips and off-screen helper windows lose.
    matches.sort(key=lambda m: (m[2].right - m[2].left) * (m[2].bottom - m[2].top),
                 reverse=True)
    return matches


def best_window(needle: str | None = None, pid: int | None = None,
                untitled: bool = False):
    matches = find_window(needle, pid, untitled)
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
    parser.add_argument("--title", help="substring of the window title")
    parser.add_argument("--pid", type=int,
                        help="only match windows owned by this process")
    parser.add_argument("--crop-height", type=int,
                        help="keep only this many rows from the top")
    parser.add_argument("--untitled", action="store_true",
                        help="also match popups, which carry no title")
    parser.add_argument("--pick", type=int, default=0,
                        help="index into the matches, largest first")
    parser.add_argument("--list", action="store_true",
                        help="print the matches and stop")
    args = parser.parse_args()

    if not args.title and args.pid is None:
        raise SystemExit("pass --title, --pid or both")

    matches = find_window(args.title, args.pid, args.untitled)
    if args.list:
        for i, (hwnd, title, rect) in enumerate(matches):
            size = f"{rect.right - rect.left}x{rect.bottom - rect.top}"
            print(f"{i}  {size:>12}  {title or '(untitled)'}")
        return 0
    if args.pick >= len(matches):
        raise SystemExit(f"only {len(matches)} window(s) matched")
    match = matches[args.pick]
    if not match:
        raise SystemExit("no visible window matched")

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
