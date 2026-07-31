#!/usr/bin/env python3
"""Extract sticky-note regions by color + column position (OpenCV)."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

# HSV ranges (OpenCV H: 0-179) for common sticky colors
COLOR_RANGES: list[tuple[str, tuple[int, int, int], tuple[int, int, int]]] = [
    ("yellow", (18, 60, 120), (38, 255, 255)),
    ("orange", (8, 80, 120), (18, 255, 255)),
    ("pink", (140, 40, 120), (175, 255, 255)),
    ("green", (40, 40, 80), (85, 255, 255)),
    ("blue", (90, 40, 80), (130, 255, 255)),
]


def _cv2_np():
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise SystemExit(
            "OpenCV and NumPy required: pip install opencv-python-headless numpy"
        ) from exc
    return cv2, np


def source_id(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def find_notes(bgr: Any) -> list[dict[str, Any]]:
    cv2, np = _cv2_np()
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h_img, w_img = bgr.shape[:2]
    min_area = (h_img * w_img) * 0.0008
    max_area = (h_img * w_img) * 0.08
    notes: list[dict[str, Any]] = []

    for name, lo, hi in COLOR_RANGES:
        mask = cv2.inRange(hsv, np.array(lo), np.array(hi))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < min_area or area > max_area:
                continue
            x, y, w, h = cv2.boundingRect(cnt)
            aspect = w / max(h, 1)
            if aspect < 0.4 or aspect > 2.5:
                continue
            notes.append(
                {
                    "color": name,
                    "text": None,
                    "bbox": [int(x), int(y), int(w), int(h)],
                    "confidence": 0.55,
                    "needs_review": True,
                    "x_center": float(x + w / 2),
                }
            )
    # Dedup heavy overlaps (same note hitting two color ranges)
    notes.sort(key=lambda n: (n["bbox"][2] * n["bbox"][3]), reverse=True)
    kept: list[dict[str, Any]] = []
    for n in notes:
        x, y, w, h = n["bbox"]
        overlap = False
        for k in kept:
            kx, ky, kw, kh = k["bbox"]
            ix = max(0, min(x + w, kx + kw) - max(x, kx))
            iy = max(0, min(y + h, ky + kh) - max(y, ky))
            inter = ix * iy
            if inter > 0.5 * min(w * h, kw * kh):
                overlap = True
                break
        if not overlap:
            kept.append(n)
    return kept


def cluster_columns(notes: list[dict[str, Any]], width: int) -> list[list[dict[str, Any]]]:
    _, np = _cv2_np()
    if not notes:
        return []
    xs = sorted(n["x_center"] for n in notes)
    # Gap-based split
    gaps = [(xs[i + 1] - xs[i], i) for i in range(len(xs) - 1)]
    gaps.sort(reverse=True)
    # Keep gaps that are large relative to median spacing
    if len(xs) == 1:
        splits: set[int] = set()
    else:
        spacings = [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
        median = float(np.median(spacings)) if spacings else width
        threshold = max(median * 2.2, width * 0.08)
        split_after = {i for gap, i in gaps if gap >= threshold}
        splits = split_after

    # Assign notes to column bins by x order
    ordered = sorted(notes, key=lambda n: n["x_center"])
    unique_xs = xs
    col_of_x: dict[float, int] = {}
    col_idx = 0
    for i, x in enumerate(unique_xs):
        if i > 0 and (i - 1) in splits:
            col_idx += 1
        col_of_x[x] = col_idx
    n_cols = col_idx + 1
    columns: list[list[dict[str, Any]]] = [[] for _ in range(n_cols)]
    for n in ordered:
        nearest = min(unique_xs, key=lambda u: abs(u - n["x_center"]))
        columns[col_of_x[nearest]].append(n)
    # Sort each column top-to-bottom
    for col in columns:
        col.sort(key=lambda n: n["bbox"][1])
    return columns


def maybe_ocr(bgr: Any, note: dict[str, Any]) -> None:
    try:
        import pytesseract
    except ImportError:
        return
    cv2, _ = _cv2_np()
    x, y, w, h = note["bbox"]
    crop = bgr[y : y + h, x : x + w]
    if crop.size == 0:
        return
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    up = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    text = pytesseract.image_to_string(up, config="--psm 6").strip()
    text = " ".join(text.split())
    if text:
        note["text"] = text
        note["confidence"] = 0.45
        note["needs_review"] = True
    else:
        note["text"] = None
        note["needs_review"] = True


def extract(path: Path, *, do_ocr: bool) -> dict[str, Any]:
    cv2, _np = _cv2_np()
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise FileNotFoundError(f"could not read image: {path}")
    h, w = bgr.shape[:2]
    notes = find_notes(bgr)
    if do_ocr:
        for n in notes:
            maybe_ocr(bgr, n)
    cols = cluster_columns(notes, w)
    columns_out = []
    for i, col in enumerate(cols, start=1):
        clean = []
        for n in col:
            clean.append(
                {
                    "color": n["color"],
                    "text": n["text"],
                    "bbox": n["bbox"],
                    "confidence": n["confidence"],
                    "needs_review": n["needs_review"],
                }
            )
        x_center = float(np.mean([n["x_center"] for n in col])) if col else 0.0
        columns_out.append({"name": f"column-{i}", "x_center": x_center, "notes": clean})
    return {
        "source": {"id": source_id(path), "width": w, "height": h, "path": str(path)},
        "columns": columns_out,
        "unresolved": []
        if notes
        else [{"reason": "no sticky-note colored regions detected", "bbox": None}],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract sticky notes by color and column position."
    )
    parser.add_argument("image", type=Path, help="Board photograph")
    parser.add_argument("-o", "--output", type=Path, help="Write JSON (default stdout)")
    parser.add_argument(
        "--ocr",
        action="store_true",
        help="Best-effort pytesseract OCR on each note crop",
    )
    args = parser.parse_args(argv)

    if not args.image.is_file():
        print(f"error: not a file: {args.image}", file=sys.stderr)
        return 2
    try:
        doc = extract(args.image, do_ocr=args.ocr)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
