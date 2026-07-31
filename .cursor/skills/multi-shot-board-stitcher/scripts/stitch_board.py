#!/usr/bin/env python3
"""Stitch overlapping whiteboard photos into one mosaic (OpenCV ORB + homography)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

MIN_INLIER_RATIO = 0.15
MIN_MATCHES = 12


def _cv2_np():
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise SystemExit(
            "OpenCV and NumPy required: pip install opencv-python-headless numpy"
        ) from exc
    return cv2, np


def load_gray_color(path: Path) -> tuple[Any, Any]:
    cv2, _ = _cv2_np()
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"could not read image: {path}")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return img, gray


def match_pair(
    gray_a: Any, gray_b: Any
) -> tuple[Any | None, float, int]:
    """Return (H mapping B→A coords, inlier_ratio, inlier_count)."""
    cv2, np = _cv2_np()
    orb = cv2.ORB_create(4000)
    kp_a, des_a = orb.detectAndCompute(gray_a, None)
    kp_b, des_b = orb.detectAndCompute(gray_b, None)
    if des_a is None or des_b is None or len(kp_a) < 8 or len(kp_b) < 8:
        return None, 0.0, 0

    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    raw = bf.knnMatch(des_b, des_a, k=2)
    good = []
    for pair in raw:
        if len(pair) < 2:
            continue
        m, n = pair
        if m.distance < 0.75 * n.distance:
            good.append(m)
    if len(good) < MIN_MATCHES:
        return None, 0.0, 0

    src = np.float32([kp_b[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([kp_a[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    h_mat, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    if h_mat is None or mask is None:
        return None, 0.0, 0
    inliers = int(mask.ravel().sum())
    ratio = inliers / max(len(good), 1)
    if ratio < MIN_INLIER_RATIO:
        return None, ratio, inliers
    return h_mat, ratio, inliers


def stitch(paths: list[Path]) -> tuple[Any, dict[str, Any]]:
    if len(paths) < 2:
        raise ValueError("need at least two images")

    cv2, np = _cv2_np()
    colors: list[Any] = []
    grays: list[Any] = []
    for p in paths:
        c, g = load_gray_color(p)
        colors.append(c)
        grays.append(g)

    meta: dict[str, Any] = {
        "panels": [str(p) for p in paths],
        "pairs": [],
        "warnings": [],
        "inlier_ratios": [],
    }

    # Chain: accumulate homography of each image into frame 0
    identity = np.eye(3, dtype=np.float64)
    transforms = [identity]
    for i in range(1, len(paths)):
        h_mat, ratio, inliers = match_pair(grays[i - 1], grays[i])
        meta["pairs"].append(
            {
                "from": str(paths[i]),
                "to": str(paths[i - 1]),
                "inlier_ratio": ratio,
                "inliers": inliers,
            }
        )
        meta["inlier_ratios"].append(ratio)
        if h_mat is None:
            raise RuntimeError(
                f"weak match between {paths[i - 1].name} and {paths[i].name} "
                f"(inlier_ratio={ratio:.3f}, min={MIN_INLIER_RATIO})"
            )
        # H maps i -> i-1; compose into frame 0
        transforms.append(transforms[i - 1] @ h_mat)

    # Global canvas from all transforms
    all_corners = []
    for img, h_mat in zip(colors, transforms):
        h, w = img.shape[:2]
        corners = np.float32([[0, 0], [w, 0], [w, h], [0, h]]).reshape(-1, 1, 2)
        wc = cv2.perspectiveTransform(corners, h_mat).reshape(-1, 2)
        all_corners.append(wc)
    pts = np.vstack(all_corners)
    x_min, y_min = np.floor(pts.min(axis=0)).astype(int)
    x_max, y_max = np.ceil(pts.max(axis=0)).astype(int)
    translate = np.array([[1, 0, -x_min], [0, 1, -y_min], [0, 0, 1]], dtype=np.float64)
    out_w = int(x_max - x_min)
    out_h = int(y_max - y_min)
    if out_w * out_h > 80_000_000:
        raise RuntimeError(f"mosaic too large ({out_w}x{out_h}); check transforms")

    canvas = np.zeros((out_h, out_w, 3), dtype=np.uint8)
    for img, h_mat in zip(colors, transforms):
        h_adj = translate @ h_mat
        warped = cv2.warpPerspective(img, h_adj, (out_w, out_h))
        mask = warped.sum(axis=2) > 0
        both = mask & (canvas.sum(axis=2) > 0)
        only = mask & ~both
        canvas[only] = warped[only]
        canvas[both] = (
            (canvas[both].astype(np.uint16) + warped[both].astype(np.uint16)) // 2
        ).astype(np.uint8)

    meta["output_size"] = {"width": out_w, "height": out_h}
    return canvas, meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Stitch overlapping whiteboard photos with ORB + homography."
    )
    parser.add_argument("images", nargs="+", type=Path, help="Panel images in order")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Output mosaic image")
    parser.add_argument("--meta", type=Path, help="Write metadata JSON")
    args = parser.parse_args(argv)

    try:
        mosaic, meta = stitch(args.images)
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    cv2, _ = _cv2_np()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(args.output), mosaic):
        print(f"error: failed to write {args.output}", file=sys.stderr)
        return 2
    meta["output"] = str(args.output)
    meta_path = args.meta or args.output.with_suffix(".json")
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "meta": str(meta_path), **{k: meta[k] for k in ("inlier_ratios", "output_size")}}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
