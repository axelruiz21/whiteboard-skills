#!/usr/bin/env python3
"""Check whether an image is full-resolution enough for whiteboard OCR.

Flags chat/Google Photos-style previews (often ~1024px wide) before parsing.
Standard library only (JPEG/PNG/GIF/WebP headers).
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path
from typing import Any

# Long-side thresholds (after natural pixel decode; EXIF orientation not applied
# for header-only reads—callers with Pillow/OpenCV should orient first).
WARN_BELOW = 2000
UNUSABLE_BELOW = 1200

TRANSFER_HINT = (
    "Copy the camera original into the project via USB-C (DCIM/Camera), "
    "Quick Share, or Google Photos original download on desktop, then parse "
    "that path. Do not re-attach the image in Cursor chat. "
    "See SKILL.md: Getting full-res photos into the parser."
)


def _read_png_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", data[16:24])


def _read_gif_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 10 or data[:6] not in (b"GIF87a", b"GIF89a"):
        return None
    return struct.unpack("<HH", data[6:10])


def _read_webp_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    kind = data[12:16]
    if kind == b"VP8X" and len(data) >= 30:
        w = 1 + int.from_bytes(data[24:27], "little")
        h = 1 + int.from_bytes(data[27:30], "little")
        return w, h
    if kind == b"VP8 " and len(data) >= 30:
        # Lossy bitstream: 16-bit dimensions at offset 26 within payload start 20
        w = struct.unpack("<H", data[26:28])[0] & 0x3FFF
        h = struct.unpack("<H", data[28:30])[0] & 0x3FFF
        return w, h
    if kind == b"VP8L" and len(data) >= 25:
        bits = struct.unpack("<I", data[21:25])[0]
        w = (bits & 0x3FFF) + 1
        h = ((bits >> 14) & 0x3FFF) + 1
        return w, h
    return None


def _read_jpeg_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        return None
    i = 2
    n = len(data)
    while i + 9 < n:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        i += 2
        if marker in (0xD8, 0xD9) or marker == 0x01:
            continue
        if 0xD0 <= marker <= 0xD7:
            continue
        if i + 2 > n:
            break
        seglen = struct.unpack(">H", data[i : i + 2])[0]
        if seglen < 2 or i + seglen > n:
            break
        # SOF0–SOF3, SOF5–SOF7, SOF9–SOF11, SOF13–SOF15
        if marker in (
            0xC0,
            0xC1,
            0xC2,
            0xC3,
            0xC5,
            0xC6,
            0xC7,
            0xC9,
            0xCA,
            0xCB,
            0xCD,
            0xCE,
            0xCF,
        ):
            if seglen < 7:
                break
            height, width = struct.unpack(">HH", data[i + 3 : i + 7])
            return width, height
        i += seglen
    return None


def read_image_size(path: Path) -> tuple[int, int, str]:
    data = path.read_bytes()
    for name, reader in (
        ("png", _read_png_size),
        ("jpeg", _read_jpeg_size),
        ("gif", _read_gif_size),
        ("webp", _read_webp_size),
    ):
        size = reader(data)
        if size is not None:
            return size[0], size[1], name
    raise ValueError(
        f"unsupported or unreadable image header: {path} "
        "(supported: JPEG, PNG, GIF, WebP)"
    )


def assess_resolution(width: int, height: int) -> dict[str, Any]:
    long_side = max(width, height)
    short_side = min(width, height)
    if long_side < UNUSABLE_BELOW:
        status = "unusable"
        warnings = [
            (
                f"Long side is {long_side}px (under {UNUSABLE_BELOW}px). "
                "This is far below camera resolution and is often a ~1024-wide "
                f"chat/Photos preview. {TRANSFER_HINT}"
            )
        ]
    elif long_side < WARN_BELOW:
        status = "warning"
        warnings = [
            (
                f"Long side is {long_side}px (under {WARN_BELOW}px). "
                "Likely compressed by chat or Google Photos. "
                f"{TRANSFER_HINT}"
            )
        ]
    else:
        status = "ok"
        warnings = []
    return {
        "width": width,
        "height": height,
        "long_side": long_side,
        "short_side": short_side,
        "thresholds": {"warn_below": WARN_BELOW, "unusable_below": UNUSABLE_BELOW},
        "quality": {"status": status, "warnings": warnings},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fail loudly when an image looks like a chat/Google Photos preview "
            "instead of a full-resolution camera still."
        )
    )
    parser.add_argument("path", type=Path, help="Path to JPEG/PNG/GIF/WebP image")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable assessment JSON",
    )
    args = parser.parse_args(argv)

    path: Path = args.path
    if not path.is_file():
        print(f"error: not a file: {path}", file=sys.stderr)
        return 2

    try:
        width, height, fmt = read_image_size(path)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    result = assess_resolution(width, height)
    result["path"] = str(path)
    result["format"] = fmt
    status = result["quality"]["status"]

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"{path}: {width}x{height} {fmt} → quality.status={status}")
        for warning in result["quality"]["warnings"]:
            print(f"  warning: {warning}")
        if status == "ok":
            print(
                "  ok: long side meets the 2000px gate; prefer parsing this "
                "path from disk (do not re-attach in chat)."
            )

    if status == "ok":
        return 0
    if status == "warning":
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
