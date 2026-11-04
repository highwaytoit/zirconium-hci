#!/usr/bin/env python3
"""Resolve only truly mechanical mkosi Packages= list conflicts.

Do not guess about scripts, section changes, or non-package settings.
"""
import re
import subprocess
import sys
from pathlib import PurePosixPath


PACKAGE = re.compile(r"^[ \t]+([@A-Za-z0-9_][A-Za-z0-9_+.@:/=-]*)[ \t]*\n?$")
ASSIGNMENT = re.compile(r"^[A-Za-z][A-Za-z0-9]*[ \t]*=")


def git(*args):
    return subprocess.check_output(("git", *args))


def parse_packages(blob):
    text = blob.decode("utf-8")
    if "\r" in text:
        raise ValueError("CRLF is not supported")
    lines = text.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.strip() == "Packages="]
    if len(starts) != 1:
        raise ValueError("Expected exactly one Packages= assignment")
    start = starts[0]
    end = start + 1
    packages = []
    while end < len(lines):
        m = PACKAGE.fullmatch(lines[end])
        if not m:
            break
        packages.append(m.group(1))
        end += 1
    if not packages or len(set(packages)) != len(packages):
        raise ValueError("Packages list is empty or contains duplicates")
    # All remaining content, including other keys and comments, must be
    # identical in base, ours and theirs before merging any package list.
    return "".join(lines[:start + 1]), packages, "".join(lines[end:])


def merge(base, ours, theirs):
    bp, b, bs = parse_packages(base)
    op, o, os = parse_packages(ours)
    tp, t, ts = parse_packages(theirs)
    if (bp, bs) != (op, os) or (bp, bs) != (tp, ts):
        raise ValueError("Non-package mkosi configuration changed")
    removed_locally = set(b) - set(o)
    added_locally = set(o) - set(b)
    result = [package for package in t if package not in removed_locally]
    for package in o:
        if package in added_locally and package not in result:
            at = next((i for i, p in enumerate(result) if p.casefold() > package.casefold()), len(result))
            result.insert(at, package)
    content = tp + "".join("    " + p + "\n" for p in result) + ts
    return content.encode("utf-8"), added_locally, removed_locally


def allowed(path):
    parts = PurePosixPath(path).parts
    if not path.endswith(".conf"):
        return False
    if len(parts) >= 4 and parts[0] == "mkosi.conf.d" and "mkosi.conf.d" in parts[1:]:
        return True
    if len(parts) >= 6 and parts[0] == "mkosi.profiles" and "mkosi.conf.d" in parts[2:]:
        return True
    return False


def resolve():
    raw = git("ls-files", "-u", "-z")
    if not raw:
        raise ValueError("git apply failed without an unmerged index entry")
    unmerged = {}
    for entry in filter(None, raw.split(b"\0")):
        meta, name = entry.split(b"\t", 1)
        mode, sha, stage = meta.decode("ascii").split(" ")
        unmerged.setdefault(name.decode("utf-8"), {})[int(stage)] = (mode, sha)
    # Compute all resolutions before writing anything. If any path is unsafe,
    # leave every conflict unmerged for human review.
    resolved = []
    for path, stages in unmerged.items():
        if not allowed(path) or set(stages) != {1, 2, 3}:
            raise ValueError(f"Manual resolution required: {path} (unsupported path or stages)")
        if any(mode != "100644" for mode, _ in stages.values()):
            raise ValueError(f"Manual resolution required: {path} (non-regular file)")
        try:
            content, added, removed = merge(
                *(git("cat-file", "blob", stages[s][1]) for s in (1, 2, 3))
            )
        except (UnicodeError, ValueError) as exc:
            raise ValueError(f"Manual resolution required: {path}: {exc}") from exc
        resolved.append((path, content, added, removed))
    for path, content, added, removed in resolved:
        with open(path, "wb") as out:
            out.write(content)
        subprocess.check_call(("git", "add", "--", path))
        print(f"Safe package-list merge: {path}")
        print(f"  Preserved HCI additions: {', '.join(sorted(added)) or '(none)'}")
        print(f"  Preserved HCI removals: {', '.join(sorted(removed)) or '(none)'}")
    if git("ls-files", "-u", "-z"):
        raise ValueError("Conflicts remain after attempted package merge")
    print(f"Resolved {len(resolved)} strictly package-only conflict(s)")


if __name__ == "__main__":
    try:
        resolve()
    except (ValueError, subprocess.CalledProcessError, OSError) as e:
        print(f"::error::{e}", file=sys.stderr)
        sys.exit(1)