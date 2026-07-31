---
name: multi-shot-board-stitcher
description: Stitches overlapping photographs of a long whiteboard into one rectified mosaic surface with feature matching, homography chaining, and weak-match failure reporting. Use when mosaicking multi-panel board photos, combining left-right whiteboard shots, or preparing a panorama for OCR parsing.
---

# Multi-Shot Board Stitcher

Use this skill when **one photo cannot cover the board**. Single-image extraction belongs to `python-whiteboard-parser`; sticky-note grids belong to `sticky-note-board-parser`. After stitching, hand the panorama path to the parser (and validate with `image-ingest-hardening`).

## Pipeline

1. Load panels in left-to-right (or capture) order.
2. Detect ORB features; match consecutive pairs with ratio test + RANSAC homography.
3. Reject pairs with low inlier ratio; fail loudly rather than inventing geometry.
4. Warp into a common canvas; blend overlaps simply (max or average).
5. Write panorama image + metadata JSON (`panels`, `inlier_ratios`, `warnings`).

## Script

```bash
python3 scripts/stitch_board.py panel_left.jpg panel_right.jpg -o out/mosaic.jpg
python3 scripts/stitch_board.py p1.jpg p2.jpg p3.jpg -o out/mosaic.jpg --meta out/mosaic.json
```

Requires OpenCV (`cv2`) and NumPy. Exit `2` when matching is too weak.

## Rules

- Prefer deliberate overlap (~30%) and similar exposure across shots.
- Do not OCR inside this skill; pass the mosaic to `python-whiteboard-parser`.
- Record per-pair `inlier_ratio` so poor alignment is visible downstream.
- For two non-overlapping photos of the **same** board over time, use `board-change-tracker` instead.
