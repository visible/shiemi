#!/usr/bin/env python3
"""Configure and build shiemi from the Chromium checkout.

  python3 utils/build.py                       # baseline flags, target chrome
  python3 utils/build.py --flags release
  python3 utils/build.py --gen-only

Requires depot_tools on PATH. Output goes to out/<flags> unless --out says
otherwise, so dev and release builds do not clobber each other.
"""

import argparse
import shutil
import subprocess
import sys

import config


def run(cmd: str, cwd) -> int:
    # gn and autoninja are .bat wrappers, so this goes through the shell.
    print("+ " + cmd)
    return subprocess.run(cmd, cwd=str(cwd), shell=True).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--flags", default="baseline", help="name in flags/, without .gn"
    )
    parser.add_argument("--out", help="output dir under out/ (default: same as --flags)")
    parser.add_argument("--target", default="chrome")
    parser.add_argument("--gen-only", action="store_true")
    args = parser.parse_args()

    src = config.require_src()
    flags_file = config.FLAGS_DIR / f"{args.flags}.gn"
    if not flags_file.exists():
        raise SystemExit(f"no such flags file: {flags_file}")

    out_name = args.out or args.flags
    out_dir = f"out\\{out_name}"
    out_path = src / "out" / out_name

    print(f"chromium {config.checkout_version()} at {src}")
    print(f"flags    {flags_file.name} -> {out_dir}")

    # Writing args.gn beats passing --args on the command line: gn string
    # values contain quotes, which cmd.exe eats, and this keeps the comments.
    out_path.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(flags_file, out_path / "args.gn")

    rc = run(f"gn gen {out_dir}", src)
    if rc != 0:
        return rc
    if args.gen_only:
        return 0

    return run(f"autoninja -C {out_dir} {args.target}", src)


if __name__ == "__main__":
    sys.exit(main())
