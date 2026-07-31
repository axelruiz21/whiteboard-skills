#!/usr/bin/env python3
"""Ingest a full-res whiteboard photo into the project for parsing.

Solves the painful chat-attach problem: Cursor downscales images pasted into
chat (~1024px). This script copies a camera original into fixtures/boards/,
checks resolution, copies a ready-to-paste prompt to the clipboard (macOS),
and prints what to say in chat.

Examples:
  # Newest image in ~/Downloads (typical Google Photos / USB drop)
  python3 ingest_board_photo.py

  # Explicit file
  python3 ingest_board_photo.py ~/Downloads/20260730_101644.jpg

  # Drop folder inside the project
  python3 ingest_board_photo.py --from-inbox
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Reuse resolution gate from sibling script
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from check_image_resolution import (  # noqa: E402
    assess_resolution,
    read_image_size,
)

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif"}


def repo_root_from_script() -> Path:
    """Prefer the project cwd; else walk up from this skill to a git/.cursor root."""
    cwd = Path.cwd()
    if (cwd / ".cursor" / "skills" / "python-whiteboard-parser").is_dir():
        return cwd
    for parent in [SCRIPT_DIR, *SCRIPT_DIR.parents]:
        if (parent / ".git").is_dir() or (
            parent / "fixtures" / "boards"
        ).is_dir():
            return parent
        # skill lives at <root>/.cursor/skills/python-whiteboard-parser/scripts
        if parent.name == "python-whiteboard-parser":
            cursor_skills = parent.parent
            if cursor_skills.name == "skills" and cursor_skills.parent.name == ".cursor":
                return cursor_skills.parent.parent
    return cwd


def default_inbox(root: Path) -> Path:
    return root / "fixtures" / "boards" / "inbox"


def default_boards(root: Path) -> Path:
    return root / "fixtures" / "boards"


def newest_image(directory: Path) -> Path | None:
    if not directory.is_dir():
        return None
    candidates = [
        p
        for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES and not p.name.startswith(".")
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def convert_heic_to_jpeg(src: Path, dest: Path) -> Path:
    """Convert HEIC with macOS sips when needed; otherwise copy."""
    if src.suffix.lower() not in {".heic", ".heif"}:
        shutil.copy2(src, dest)
        return dest
    dest = dest.with_suffix(".jpg")
    result = subprocess.run(
        ["sips", "-s", "format", "jpeg", str(src), "--out", str(dest)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not dest.is_file():
        raise RuntimeError(
            f"HEIC conversion failed (is sips available?): {result.stderr or result.stdout}"
        )
    return dest


def copy_to_clipboard(text: str) -> bool:
    try:
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def unique_dest(boards: Path, src: Path) -> Path:
    boards.mkdir(parents=True, exist_ok=True)
    stem = src.stem
    suffix = ".jpg" if src.suffix.lower() in {".heic", ".heif"} else src.suffix.lower()
    if suffix == ".jpeg":
        suffix = ".jpg"
    candidate = boards / f"{stem}{suffix}"
    if not candidate.exists():
        return candidate
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return boards / f"{stem}_{stamp}{suffix}"


def main(argv: list[str] | None = None) -> int:
    root = repo_root_from_script()

    parser = argparse.ArgumentParser(
        description="Copy a full-res board photo into fixtures/boards/ and print a chat-ready parse prompt."
    )
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        help="Image to ingest (default: newest in ~/Downloads or --from-inbox)",
    )
    parser.add_argument(
        "--from-inbox",
        action="store_true",
        help=f"Use newest image in {default_inbox(Path('.'))} (relative to project root)",
    )
    parser.add_argument(
        "--downloads",
        type=Path,
        default=Path.home() / "Downloads",
        help="Downloads folder when auto-picking (default: ~/Downloads)",
    )
    parser.add_argument(
        "--no-clipboard",
        action="store_true",
        help="Do not copy the parse prompt to the clipboard",
    )
    args = parser.parse_args(argv)

    inbox = default_inbox(root)
    boards = default_boards(root)
    inbox.mkdir(parents=True, exist_ok=True)
    boards.mkdir(parents=True, exist_ok=True)
    (inbox / ".gitkeep").touch(exist_ok=True)
    (boards / ".gitkeep").touch(exist_ok=True)

    if args.path:
        src = args.path.expanduser().resolve()
    elif args.from_inbox:
        src = newest_image(inbox)
        if src is None:
            print(f"error: no images in inbox: {inbox}", file=sys.stderr)
            print("Drop a full-res JPG into that folder, then re-run.", file=sys.stderr)
            return 2
    else:
        src = newest_image(args.downloads.expanduser())
        if src is None:
            print(f"error: no images in {args.downloads}", file=sys.stderr)
            return 2

    if not src.is_file():
        print(f"error: not a file: {src}", file=sys.stderr)
        return 2

    dest = unique_dest(boards, src)
    try:
        dest = convert_heic_to_jpeg(src, dest)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        width, height, fmt = read_image_size(dest)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    assessment = assess_resolution(width, height)
    status = assessment["quality"]["status"]
    rel = dest.relative_to(root) if dest.is_relative_to(root) else dest
    prompt = f"Parse the whiteboard photo at @{rel}"

    print(f"source:  {src}")
    print(f"ingested: {dest}")
    print(f"size:    {width}x{height} {fmt} → quality.status={status}")
    for warning in assessment["quality"]["warnings"]:
        print(f"warning: {warning}")

    if status != "ok":
        print(
            "\nNot ingesting for parse: fix the transfer (USB / Quick Share / Photos "
            "original download), then drop the real camera file and run again.",
            file=sys.stderr,
        )
        # Remove bad copy so inbox stays clean of previews
        if dest.exists() and dest.resolve() != src.resolve():
            dest.unlink()
        return 1 if status == "warning" else 2

    print(f"\nPaste this in Cursor chat (do not attach the image):\n\n  {prompt}\n")
    if not args.no_clipboard and copy_to_clipboard(prompt):
        print("Copied to clipboard.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
