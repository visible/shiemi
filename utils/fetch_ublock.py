#!/usr/bin/env python3
"""Fetch the bundled content blocker and lay it out for the installer.

  python3 utils/fetch_ublock.py --dest E:/cr/src/out/release/extensions

uBlock Origin's Manifest V2 build is no longer served by the Chrome Web Store,
so a user cannot install it themselves however much they want it. It ships with
the browser instead.

What lands here is the release the author signed and published, byte for byte:
no repacking, no key of ours, no build step that could alter what runs. That is
the point of the checksum below. Repacking would mean holding a private key
whose only purpose is to make the extension look like ours, and it would break
the one property worth having, which is that anyone can download the same file
from the same URL and compare hashes.

To move to a new release, change all three pins together and run with --probe
to have the checksum and id read back off the download.
"""

import argparse
import hashlib
import io
import json
import struct
import sys
import urllib.request
import zipfile
from pathlib import Path

VERSION = "1.74.0"
SHA256 = "b6be71ed3e3e85eaad8f02710b9071d06428e141d942c43d5f65d4526e82dc3e"

# Signed with the author's own key rather than the store's, so this is not the
# id uBlock Origin has on the Web Store. It is fixed by the signature and has
# to match the name of the json file the browser reads.
EXTENSION_ID = "fkgkibajhfbepljeaefdnfnegdcjomkh"

URL = ("https://github.com/gorhill/uBlock/releases/download/"
       f"{VERSION}/uBlock0_{VERSION}.chromium.crx")


def download(cache: Path) -> bytes:
    if cache.exists():
        return cache.read_bytes()
    print(f"fetching {URL}")
    request = urllib.request.Request(URL, headers={"User-Agent": "shiemi-build"})
    with urllib.request.urlopen(request, timeout=180) as response:
        blob = response.read()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(blob)
    return blob


def read_varint(buf: bytes, at: int) -> tuple[int, int]:
    shift = value = 0
    while True:
        byte = buf[at]
        at += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, at
        shift += 7


def crx_identity(blob: bytes) -> str:
    """The extension id the browser will derive from this crx."""
    magic, version, header_len = struct.unpack("<4sII", blob[:12])
    if magic != b"Cr24" or version != 3:
        raise SystemExit(f"not a crx3 file: magic={magic!r} version={version}")

    # signed_header_data is field 10000, so its tag is a multi-byte varint and
    # its offset moves with the number of signatures. Walk the fields.
    header, at, signed = blob[12:12 + header_len], 0, None
    while at < len(header):
        tag, at = read_varint(header, at)
        wire = tag & 7
        if wire == 0:
            _value, at = read_varint(header, at)
            continue
        if wire != 2:
            raise SystemExit(f"unexpected wire type {wire} in the crx header")
        length, at = read_varint(header, at)
        if tag >> 3 == 10000:
            signed = header[at:at + length]
        at += length

    if signed is None:
        raise SystemExit("crx header carries no signed_header_data")

    tag, at = read_varint(signed, 0)
    if tag >> 3 != 1:
        raise SystemExit("signed_header_data does not start with the crx id")
    length, at = read_varint(signed, at)
    crx_id = signed[at:at + length]

    # Chromium renders the id by mapping each nibble onto a-p rather than hex.
    return "".join(chr(ord("a") + nibble) for byte in crx_id
                   for nibble in (byte >> 4, byte & 0xF))


def manifest_of(blob: bytes) -> dict:
    _magic, _version, header_len = struct.unpack("<4sII", blob[:12])
    archive = zipfile.ZipFile(io.BytesIO(blob[12 + header_len:]))
    return json.loads(archive.read("manifest.json"))


def check(blob: bytes, probe: bool) -> dict:
    digest = hashlib.sha256(blob).hexdigest()
    identity = crx_identity(blob)
    manifest = manifest_of(blob)

    if probe:
        print(f"  sha256   {digest}")
        print(f"  id       {identity}")
        print(f"  version  {manifest['version']}")
        print(f"  manifest v{manifest['manifest_version']}")
        return manifest

    if digest != SHA256:
        raise SystemExit(
            f"checksum mismatch for {URL}\n"
            f"  expected {SHA256}\n"
            f"  got      {digest}\n"
            "Refusing to ship a blocker that is not the pinned release.")
    if identity != EXTENSION_ID:
        raise SystemExit(f"id is {identity}, expected {EXTENSION_ID}")
    if manifest["version"] != VERSION:
        raise SystemExit(
            f"crx says version {manifest['version']}, pinned at {VERSION}")
    if manifest["manifest_version"] != 2:
        raise SystemExit(
            f"crx is manifest v{manifest['manifest_version']}."
            " The V2 build is the one with blocking webRequest; V3 is capped by"
            " the declarativeNetRequest rule limit and is a different product.")
    return manifest


DEFAULT_CACHE = (Path(__file__).resolve().parent.parent / ".cache"
                 / f"uBlock0_{VERSION}.chromium.crx")

CRX_NAME = f"{EXTENSION_ID}.crx"
JSON_NAME = f"{EXTENSION_ID}.json"

# A relative external_crx resolves against the directory holding the json, so
# the pair travels together and no install path is baked in anywhere.
DECLARATION = json.dumps({"external_crx": CRX_NAME,
                          "external_version": VERSION}, indent=2) + "\n"


def place(dest: Path, cache: Path = DEFAULT_CACHE) -> bool:
    """Write the crx and its declaration into dest, if not already there.

    Returns whether anything was written, so a build can stay quiet when the
    files are already in place.
    """
    blob = download(cache)
    check(blob, probe=False)

    dest.mkdir(parents=True, exist_ok=True)
    crx, declaration = dest / CRX_NAME, dest / JSON_NAME
    if (crx.exists() and crx.read_bytes() == blob
            and declaration.exists()
            and declaration.read_text(encoding="utf-8") == DECLARATION):
        return False

    crx.write_bytes(blob)
    declaration.write_text(DECLARATION, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path,
                        help="directory to write the crx and its json into")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--probe", action="store_true",
                        help="report the checksum and id instead of enforcing"
                             " them, for bumping the pins")
    args = parser.parse_args()

    if args.probe:
        blob = download(args.cache)
        print(f"  {len(blob)} bytes from {args.cache}")
        check(blob, probe=True)
        return 0

    if not args.dest:
        blob = download(args.cache)
        print(f"  {len(blob)} bytes from {args.cache}")
        check(blob, probe=False)
        print("  pins match")
        return 0

    if place(args.dest, args.cache):
        print(f"  wrote {CRX_NAME} and {JSON_NAME} to {args.dest}")
    else:
        print(f"  already in place at {args.dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
