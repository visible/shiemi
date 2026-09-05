#!/usr/bin/env python3
"""Build a Windows installer and check that it carries our defaults.

  python3 utils/package.py                     # release flags
  python3 utils/package.py --flags baseline    # quicker, for testing the flow
  python3 utils/package.py --skip-build        # re-check an existing build

Produces dist/shiemi-<version>-win64.exe from Chromium's mini_installer, and
prints the SHA-256 to publish alongside it.

The check is the point. Our privacy defaults live in a file beside the
binary rather than in C++ defaults, so an installer that omits it installs a
browser with none of them. Two upstream behaviours make that easy to ship by
accident:

  create_installer_archive.py skips any file in chrome.release it cannot
  find, printing a line only with --verbose, and carries on to produce a
  perfectly good installer.

  It also copies into the staging directory only when the destination is
  absent, so a stale copy from an earlier build is never refreshed, and the
  staging directory is not cleared between builds.

So the staged file is compared byte for byte with the one in the repo, and
packaging fails if it is missing or out of date.
"""

import argparse
import hashlib
import shutil
import subprocess
import sys

import config
import fetch_ublock

INSTALLER = "mini_installer.exe"
DEFAULTS = "initial_preferences"

# The archive stages the install directory under a name of its own choosing
# inside the mini_installer gen directory, so it is found rather than spelled
# out: the path has an interior level that is not ours to depend on.
STAGED_GLOB = "gen/chrome/installer/mini_installer/**/Chrome-bin"


def check_defaults(out_path) -> None:
    """Fail unless the staged defaults match the ones in the repo."""
    source = config.ROOT / "defaults" / DEFAULTS
    if not source.is_file():
        raise SystemExit(f"missing {source}")

    staged_dirs = sorted(out_path.glob(STAGED_GLOB))
    if not staged_dirs:
        raise SystemExit(
            f"no staged install directory under {out_path / STAGED_GLOB}.\n"
            f"The installer archive has not been built here."
        )

    staged = staged_dirs[0] / DEFAULTS
    if not staged.is_file():
        raise SystemExit(
            f"{DEFAULTS} is not in the installer archive ({staged}).\n"
            f"chrome.release needs a line placing it in %(ChromeDir)s, and "
            f"the file has to exist in {out_path} before the archive runs."
        )
    if staged.read_bytes() != source.read_bytes():
        raise SystemExit(
            f"staged {DEFAULTS} is stale.\n"
            f"The archive step does not overwrite what is already staged, so "
            f"delete {staged.parent} and build again."
        )
    print(f"defaults {DEFAULTS} staged and current")

    check_blocker(staged_dirs[0])


def check_blocker(staged_dir) -> None:
    """Fail unless the bundled blocker is staged for the version directory.

    Same failure as the defaults above and just as quiet: the browser installs
    and runs perfectly with no blocker in it, and the only visible difference
    is ads. Upstream's Extensions\\*.* line does the carrying, so what can go
    wrong is the files not being in the build directory when the archive runs.
    """
    source = config.ROOT / ".cache" / fetch_ublock.DEFAULT_CACHE.name
    version_dirs = [p for p in staged_dir.iterdir()
                    if p.is_dir() and p.name[0].isdigit()]
    if not version_dirs:
        raise SystemExit(f"no version directory staged under {staged_dir}")

    staged = version_dirs[0] / "Extensions" / fetch_ublock.CRX_NAME
    declaration = staged.parent / fetch_ublock.JSON_NAME
    for path in (staged, declaration):
        if not path.is_file():
            raise SystemExit(
                f"the bundled blocker is not in the installer archive"
                f" ({path}).\n"
                "Both the crx and its json have to be in the build directory's"
                " Extensions folder before the archive runs; utils/build.py"
                " puts them there."
            )

    if source.is_file() and staged.read_bytes() != source.read_bytes():
        raise SystemExit(f"staged {fetch_ublock.CRX_NAME} is not the pinned"
                         " release; clear the staging directory and rebuild")

    print(f"blocker  uBlock Origin {fetch_ublock.VERSION} staged for the"
          " version directory")


def digest(path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flags", default="release")
    parser.add_argument("--out", help="output dir under out/ (default: --flags)")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--no-yield", action="store_true",
                        help="passed through: take every core")
    args = parser.parse_args()

    src = config.require_src()
    out_name = args.out or args.flags
    out_path = src / "out" / out_name

    if not args.skip_build:
        # The archive copies into staging only where the destination is absent
        # and nothing clears it, so anything already there survives forever.
        # An interrupted build leaves a truncated file that is then never
        # rewritten, and the installer it produces looks perfectly fine.
        for staged in sorted(out_path.glob(STAGED_GLOB)):
            print(f"staging clearing {staged.relative_to(out_path)}")
            shutil.rmtree(staged, ignore_errors=True)

        cmd = [sys.executable, str(config.ROOT / "utils" / "build.py"),
               "--flags", args.flags, "--target", "mini_installer"]
        if args.out:
            cmd += ["--out", args.out]
        if args.no_yield:
            cmd.append("--no-yield")
        rc = subprocess.run(cmd).returncode
        if rc != 0:
            return rc

    installer = out_path / INSTALLER
    if not installer.is_file():
        raise SystemExit(f"no installer at {installer}")

    check_defaults(out_path)

    version = config.checkout_version()
    dist = config.ROOT / "dist"
    dist.mkdir(exist_ok=True)
    artifact = dist / f"shiemi-{version}-win64.exe"
    shutil.copyfile(installer, artifact)

    print(f"artifact {artifact.relative_to(config.ROOT)}")
    print(f"size     {artifact.stat().st_size / (1 << 20):.1f} MB")
    print(f"sha256   {digest(artifact)}")
    print("unsigned: Windows will warn until the binary is code signed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
