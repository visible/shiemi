#!/usr/bin/env python3
"""Check the build can play the codecs most of the web ships.

  python3 utils/check_codecs.py
  python3 utils/check_codecs.py --out-dir release
  python3 utils/check_codecs.py --binary "%LOCALAPPDATA%/Shiemi/Application/chrome.exe"

Asks the binary itself rather than reading the build flags, because the
question is whether video plays, and the flags are two steps removed from
that. flags/baseline.gn once disagreed with flags/release.gn here, so every
build used to develop and measure patches had no H.264 and no AAC while the
shipped one did, and nothing anywhere said so: the build succeeded and the
browser ran.

H.264 and AAC need proprietary_codecs and ffmpeg_branding, both of which
default off in an unbranded build. The royalty-free four come with any
configuration and are checked to catch a broken media stack rather than a
missing licence.
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import cdp
import config

# Licensed, so absent unless the build asks for them. These are the ones that
# actually break the web: most MP4 on the web is H.264 video with AAC audio.
LICENSED = {
    "h264": ("video", 'video/mp4; codecs="avc1.42E01E"'),
    "aac": ("audio", 'audio/mp4; codecs="mp4a.40.2"'),
    "mp3": ("audio", "audio/mpeg"),
}

# Royalty free, so a failure here means the media stack itself is broken.
FREE = {
    "vp9": ("video", 'video/webm; codecs="vp09.00.10.08"'),
    "av1": ("video", 'video/mp4; codecs="av01.0.04M.08"'),
    "opus": ("audio", 'audio/webm; codecs="opus"'),
    "webm vorbis": ("audio", 'audio/webm; codecs="vorbis"'),
}


def probe(binary: Path, port: int) -> dict:
    profile = Path(tempfile.mkdtemp(prefix="codec-"))
    proc = subprocess.Popen([
        str(binary), f"--user-data-dir={profile}",
        f"--remote-debugging-port={port}",
        "--no-first-run", "--no-default-browser-check",
        "--disable-search-engine-choice-screen", "--headless=new",
        "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        info = cdp.wait_for_page(port, time.monotonic() + 60)
        if not info:
            raise SystemExit("devtools never came up")
        page = cdp.Target(info["webSocketDebuggerUrl"])
        results = {}
        for name, (tag, mime) in {**LICENSED, **FREE}.items():
            results[name] = page.evaluate(
                f'document.createElement("{tag}").canPlayType({mime!r})')
        page.close()
        return results
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
        time.sleep(1)
        shutil.rmtree(profile, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="baseline")
    # A build directory is the usual target, but the codecs that matter are
    # licensed ones that a GN argument decides, so the artifact a user ends up
    # with is the one worth asking. Every other gate takes --binary.
    parser.add_argument("--binary", type=Path,
                        help="a browser anywhere, instead of --out-dir")
    parser.add_argument("--port", type=int, default=9401)
    args = parser.parse_args()

    binary = args.binary or (config.require_src() / "out" / args.out_dir
                             / "chrome.exe")
    if not binary.is_file():
        raise SystemExit(f"no binary at {binary}")

    print(f"binary  {binary}")
    results = probe(binary, args.port)

    missing = []
    for group, codecs in (("licensed", LICENSED), ("royalty free", FREE)):
        print(f"\n{group}")
        for name in codecs:
            # canPlayType answers "probably", "maybe" or "".
            answer = results.get(name) or ""
            print(f"  {name:<12} {answer or 'no'}")
            if not answer:
                missing.append(name)

    if missing:
        print(f"\nabsent: {', '.join(missing)}", file=sys.stderr)
        print("H.264 or AAC missing means the flags file lost "
              "proprietary_codecs or ffmpeg_branding.", file=sys.stderr)
        return 1

    print("\nevery codec present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
