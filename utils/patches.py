#!/usr/bin/env python3
"""Apply, revert and check Shiemi's patches against a Chromium checkout.

  python3 utils/patches.py status
  python3 utils/patches.py apply
  python3 utils/patches.py revert
  python3 utils/patches.py capture ui/thing.patch chrome/browser/a.cc [...]

Patches are applied in the order given by patches/series and reverted in
reverse. A dry run happens before anything is written, so a conflict in the
last patch will not leave the tree half-patched.

Capture writes the working-tree diff for the given Chromium paths to a patch
file. Use it rather than redirecting git: a shell that rewrites line endings
produces a patch git refuses to apply, and the failure looks like a conflict.
"""

import argparse
import subprocess
import sys

import config


def git_apply(src, patch, reverse=False, dry_run=False) -> tuple[bool, str]:
    cmd = ["git", "-C", str(src), "apply"]
    if reverse:
        cmd.append("--reverse")
    if dry_run:
        cmd.append("--check")
    cmd.append(str(patch))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode == 0, (proc.stderr or proc.stdout).strip()


def resolve(names):
    paths = []
    for name in names:
        path = config.PATCHES_DIR / name
        if not path.exists():
            raise SystemExit(f"listed in series but missing on disk: {path}")
        paths.append(path)
    return paths


def cmd_status(src, patches) -> int:
    if not patches:
        print("series is empty - no patches to apply")
        return 0
    failed = 0
    for path in patches:
        applied, _ = git_apply(src, path, reverse=True, dry_run=True)
        clean, err = git_apply(src, path, dry_run=True)
        if applied:
            state = "applied"
        elif clean:
            state = "pending"
        else:
            state = "CONFLICT"
            failed += 1
        print(f"  {state:<9} {path.relative_to(config.PATCHES_DIR)}")
        if state == "CONFLICT" and err:
            print(f"            {err.splitlines()[0]}")
    return 1 if failed else 0


def cmd_apply(src, patches) -> int:
    if not patches:
        print("series is empty - nothing to apply")
        return 0
    for path in patches:
        ok, err = git_apply(src, path, dry_run=True)
        if not ok:
            already, _ = git_apply(src, path, reverse=True, dry_run=True)
            if already:
                continue
            print(f"would fail: {path.name}\n{err}", file=sys.stderr)
            return 1
    for path in patches:
        already, _ = git_apply(src, path, reverse=True, dry_run=True)
        if already:
            print(f"  skip  {path.name} (already applied)")
            continue
        ok, err = git_apply(src, path)
        if not ok:
            print(f"failed: {path.name}\n{err}", file=sys.stderr)
            return 1
        print(f"  apply {path.name}")
    return 0


def cmd_revert(src, patches) -> int:
    for path in reversed(patches):
        ok, _ = git_apply(src, path, reverse=True, dry_run=True)
        if not ok:
            print(f"  skip   {path.name} (not applied)")
            continue
        ok, err = git_apply(src, path, reverse=True)
        if not ok:
            print(f"failed to revert: {path.name}\n{err}", file=sys.stderr)
            return 1
        print(f"  revert {path.name}")
    return 0


def cmd_capture(src, name, paths) -> int:
    proc = subprocess.run(
        ["git", "-C", str(src), "diff", "--", *paths],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(proc.stderr.strip(), file=sys.stderr)
        return 1
    if not proc.stdout.strip():
        print(f"nothing to capture: no changes under {' '.join(paths)}",
              file=sys.stderr)
        return 1

    out = config.PATCHES_DIR / name
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(proc.stdout)

    files = sum(1 for line in proc.stdout.splitlines()
                if line.startswith("diff --git "))
    print(f"wrote {out.relative_to(config.PATCHES_DIR)} ({files} file(s))")
    if name not in config.read_series():
        print(f"note: {name} is not in patches/series yet")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",
                        choices=["status", "apply", "revert", "capture"])
    parser.add_argument("name", nargs="?", help="patch path, for capture")
    parser.add_argument("paths", nargs="*",
                        help="Chromium paths to diff, for capture")
    args = parser.parse_args()

    src = config.require_src()

    if args.action == "capture":
        if not args.name or not args.paths:
            raise SystemExit("capture needs a patch name and at least one path")
        return cmd_capture(src, args.name.replace("\\", "/"), args.paths)
    pinned, actual = config.pinned_version(), config.checkout_version()
    if pinned != actual:
        print(
            f"warning: checkout is {actual} but chromium_version.txt pins "
            f"{pinned}; patches may not apply",
            file=sys.stderr,
        )

    patches = resolve(config.read_series())
    return {"status": cmd_status, "apply": cmd_apply, "revert": cmd_revert}[
        args.action
    ](src, patches)





if __name__ == "__main__":
    sys.exit(main())
