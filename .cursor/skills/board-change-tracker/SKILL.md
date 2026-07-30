---
name: board-change-tracker
description: Compares two or more photographs of the same physical whiteboard taken at different times and reports added, erased, moved, and edited content with evidence coordinates and confidence. Use when diffing board snapshots, tracking what changed on a whiteboard between photos, building a board revision history, or reconciling before-and-after board images.
---

# Board Change Tracker

Use this skill for the multi-snapshot case: the same board, photographed more than once. Single-image extraction belongs to the `python-whiteboard-parser` skill; this skill consumes that output and adds alignment and differencing.

The hard problem is not detecting pixel differences. It is deciding which pixel differences mean the board changed, because camera position, exposure, glare, and people move between shots while the content does not.

## Pipeline

1. **Extract each snapshot independently** with the whiteboard parser. Keep per-snapshot text, coordinates, and confidence. Never diff raw photos directly.
2. **Establish a common frame.** Prefer the rectified board plane from each snapshot, then refine with a feature-based homography (ORB or SIFT with RANSAC) computed from stable board features: taped edges, printed headers, permanent markings, and the board frame itself. Reject the homography when the inlier ratio is low or the transform implies implausible scaling, and fall back to the rectification corners alone.
3. **Normalize appearance.** Match illumination and white balance across snapshots before any pixel comparison. Exposure drift alone will otherwise light up the entire board as changed.
4. **Build ink masks.** Segment marker strokes from board surface in each aligned snapshot. Diff the masks to get candidate change regions; treat this as a region proposal step only.
5. **Classify at the content level.** For each candidate region, compare the extracted text and structure, not the pixels. Match items across snapshots by normalized text similarity combined with spatial proximity.
6. **Emit change records** with evidence from both snapshots.

## Classification rules

| Outcome | Evidence required |
|---|---|
| `added` | Content present in the later snapshot, absent in the earlier, in a region that was visible and unobstructed in both |
| `erased` | Content present earlier, absent later, region visible and unobstructed in both, and surrounding ink still matches |
| `modified` | Matched content whose text or structure differs beyond OCR noise |
| `moved` | Matched content at a materially different board position with unchanged text |
| `unchanged` | Matched content within tolerance |
| `occluded` | Region blocked in one snapshot; no change claim is made |

Anything that cannot meet its evidence bar becomes `uncertain` with `needs_review: true`. Never default an ambiguous region to `erased`.

## Occlusion is the main failure mode

A person, hand, sleeve, laptop, or sticky note standing in front of the board makes content vanish exactly like erasing does. Treat occlusion detection as a required stage, not a refinement:

- Detect large connected regions whose color and texture statistics do not match board surface or marker ink.
- Treat sharp, high-saturation, non-stroke-shaped regions as candidate obstructions rather than content.
- Regions of strong glare are also unreliable; mark them `occluded` rather than comparing them.
- Once a region is occluded in either snapshot, it is excluded from `added` and `erased` findings and reported as `occluded` so a human can re-shoot.

The same logic applies to partial captures: if a snapshot crops part of the board, the missing area is out of frame, not erased.

## Distinguishing real edits from OCR noise

Two readings of the same unchanged handwriting will differ. Require a change to clear a noise floor before reporting `modified`:

- Compare normalized text with an edit-distance ratio, not exact equality.
- Weight the comparison by both readings' OCR confidence; a low-confidence reading changing to another low-confidence reading is evidence of noise, not of an edit.
- Require positional stability: matched text in the same place with small text differences is almost always the same content read twice.
- When a single character flips between visually similar glyphs, prefer `uncertain` over `modified`.

Calibrate this floor against fixtures using the `ocr-extraction-eval` skill: photograph one unchanged board twice and require the tracker to report zero changes. That null test is the single most valuable fixture in the set.

## Output

```json
{
  "base": {"source_id": "sha256:...", "captured_at": null},
  "head": {"source_id": "sha256:...", "captured_at": null},
  "alignment": {"method": "homography", "inlier_ratio": 0.0, "confidence": 0.0},
  "changes": [
    {
      "id": "change-1",
      "type": "added|erased|modified|moved|occluded|uncertain",
      "text_before": null,
      "text_after": "Ship auth by Friday",
      "bbox_before": null,
      "bbox_after": [0, 0, 0, 0],
      "confidence": 0.0,
      "needs_review": false
    }
  ],
  "excluded_regions": [{"reason": "occluded|glare|out_of_frame", "bbox": [0, 0, 0, 0]}],
  "summary": {"added": 0, "erased": 0, "modified": 0, "moved": 0, "uncertain": 0}
}
```

Report `alignment.confidence` prominently. Every change claim inherits it, so a poor alignment must invalidate the whole comparison rather than produce a long list of false changes.

## Multiple snapshots

For three or more photos, diff consecutive pairs into a revision chain rather than comparing everything to the first frame; drift accumulates and content often returns after being partially erased. Give each item a stable identity across the chain by carrying matched identifiers forward, so the history reads as one item's lifecycle instead of unrelated add and erase events.

## Testing

Build fixture pairs for: no change at all, one line added, one line erased, a line edited in place, content rewritten in a different location, a person standing in front of the board, a large exposure difference, a large camera-angle difference, and a partially cropped second shot.

The two non-negotiable assertions are that the unchanged pair reports zero changes and that the occluded pair reports zero erasures.
