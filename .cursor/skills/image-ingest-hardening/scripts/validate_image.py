#!/usr/bin/env python3
"""Validate an image is safe and usable for whiteboard OCR ingest.

Sniffs MIME from magic bytes, enforces byte/pixel caps, optionally applies
EXIF orientation via Pillow, computes SHA-256, and reuses the long-side
resolution gate (ok / warning / unusable).

Exit codes: 0 ok, 1 warning, 2 reject.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path
from typing import Any

WARN_BELOW = 2000
UNUSABLE_BELOW = 1200
DEFAULT_MAX_BYTES = 40 * 1024 * 1024
DEFAULT_MAX_MEGAPIXELS = 40.0

TRANSFER_HINT = (
    "Copy the camera original into the project via USB-C, Quick Share, or "
    "Google Photos original download. Do not re-attach the image in Cursor chat."
)


def sniff_mime(data: bytes) -> str | None:
    if len(data) >= 3 and data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(data) >= 6 and data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


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


def header_size(data: bytes, mime: str) -> tuple[int, int] | None:
    readers = {
        "image/png": _read_png_size,
        "image/jpeg": _read_jpeg_size,
        "image/gif": _read_gif_size,
        "image/webp": _read_webp_size,
    }
    reader = readers.get(mime)
    if reader is None:
        return None
    return reader(data)


def oriented_size_with_pillow(
    path: Path, max_megapixels: float
) -> tuple[int, int, bool]:
    """Return (width, height, oriented) using Pillow EXIF transpose when present."""
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise RuntimeError("Pillow is required for EXIF orientation") from exc

    Image.MAX_IMAGE_PIXELS = int(max_megapixels * 1_000_000)
    with Image.open(path) as img:
        img.verify()
    with Image.open(path) as img:
        oriented = ImageOps.exif_transpose(img)
        return oriented.size[0], oriented.size[1], True


def assess_resolution(width: int, height: int) -> dict[str, Any]:
    long_side = max(width, height)
    if long_side < UNUSABLE_BELOW:
        status = "unusable"
        warnings = [
            f"Long side is {long_side}px (under {UNUSABLE_BELOW}px). {TRANSFER_HINT}"
        ]
    elif long_side < WARN_BELOW:
        status = "warning"
        warnings = [
            f"Long side is {long_side}px (under {WARN_BELOW}px). {TRANSFER_HINT}"
        ]
    else:
        status = "ok"
        warnings = []
    return {
        "width": width,
        "height": height,
        "long_side": long_side,
        "short_side": min(width, height),
        "quality": {"status": status, "warnings": warnings},
    }


def validate_image(
    path: Path,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_megapixels: float = DEFAULT_MAX_MEGAPIXELS,
    apply_exif: bool = True,
) -> dict[str, Any]:
    if not path.is_file():
        return {
            "ok": False,
            "reject_reason": f"not a file: {path}",
            "quality": {"status": "unusable", "warnings": []},
        }

    data = path.read_bytes()
    size_bytes = len(data)
    digest = hashlib.sha256(data).hexdigest()
    mime = sniff_mime(data)
    report: dict[str, Any] = {
        "path": str(path),
        "bytes": size_bytes,
        "source": {"id": f"sha256:{digest}"},
        "mime": mime,
        "caps": {"max_bytes": max_bytes, "max_megapixels": max_megapixels},
        "exif_applied": False,
    }

    if mime is None:
        report["ok"] = False
        report["reject_reason"] = "unsupported or unreadable image magic (need JPEG/PNG/GIF/WebP)"
        report["quality"] = {"status": "unusable", "warnings": []}
        return report

    if size_bytes > max_bytes:
        report["ok"] = False
        report["reject_reason"] = f"file exceeds max-bytes ({size_bytes} > {max_bytes})"
        report["quality"] = {"status": "unusable", "warnings": []}
        return report

    header = header_size(data, mime)
    width: int
    height: int
    if apply_exif:
        try:
            width, height, _ = oriented_size_with_pillow(path, max_megapixels)
            report["exif_applied"] = True
        except Exception as exc:  # Pillow missing, bomb, or corrupt
            if header is None:
                report["ok"] = False
                report["reject_reason"] = f"decode failed: {exc}"
                report["quality"] = {"status": "unusable", "warnings": []}
                return report
            width, height = header
            report["exif_error"] = str(exc)
    else:
        if header is None:
            report["ok"] = False
            report["reject_reason"] = "could not read dimensions from header"
            report["quality"] = {"status": "unusable", "warnings": []}
            return report
        width, height = header

    megapixels = (width * height) / 1_000_000
    if megapixels > max_megapixels:
        report["ok"] = False
        report["reject_reason"] = (
            f"image exceeds max-megapixels ({megapixels:.2f} > {max_megapixels})"
        )
        report["width"] = width
        report["height"] = height
        report["quality"] = {"status": "unusable", "warnings": []}
        return report

    res = assess_resolution(width, height)
    report.update(res)
    status = res["quality"]["status"]
    report["ok"] = status != "unusable"
    report["format"] = mime.split("/")[-1]
    if status == "unusable":
        report["reject_reason"] = "resolution unusable for OCR"
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Hardened image ingest validation for OCR pipelines."
    )
    parser.add_argument("path", type=Path, help="Path to image file")
    parser.add_argument("--json", action="store_true", help="Print JSON report to stdout")
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_BYTES,
        help=f"Maximum file size in bytes (default {DEFAULT_MAX_BYTES})",
    )
    parser.add_argument(
        "--max-megapixels",
        type=float,
        default=DEFAULT_MAX_MEGAPIXELS,
        help=f"Maximum megapixels after orientation (default {DEFAULT_MAX_MEGAPIXELS})",
    )
    parser.add_argument(
        "--no-exif",
        action="store_true",
        help="Skip Pillow EXIF orientation (header dimensions only)",
    )
    args = parser.parse_args(argv)

    report = validate_image(
        args.path,
        max_bytes=args.max_bytes,
        max_megapixels=args.max_megapixels,
        apply_exif=not args.no_exif,
    )

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        status = report.get("quality", {}).get("status", "unusable")
        dims = ""
        if "width" in report and "height" in report:
            dims = f"{report['width']}x{report['height']} "
        print(
            f"{args.path}: {dims}{report.get('mime') or 'unknown'} "
            f"bytes={report.get('bytes', 0)} → {status}"
        )
        if report.get("source"):
            print(f"  source.id: {report['source']['id']}")
        for warning in report.get("quality", {}).get("warnings", []):
            print(f"  warning: {warning}")
        if report.get("reject_reason"):
            print(f"  reject: {report['reject_reason']}")

    status = report.get("quality", {}).get("status", "unusable")
    if not report.get("ok", False) or status == "unusable":
        return 2
    if status == "warning":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
