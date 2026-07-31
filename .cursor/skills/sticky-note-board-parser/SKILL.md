---
name: sticky-note-board-parser
description: Extracts sticky-note and kanban-style boards by clustering note color and column position into structured columns of notes, with optional OCR. Use when parsing retro boards, sticky-note walls, kanban columns photographed on a wall, or when note color and column layout carry meaning.
---

# Sticky Note Board Parser

Use this skill when **color + column position** are the primary structure. Free-form marker whiteboards belong to `python-whiteboard-parser`. Multi-panel mosaics belong to `multi-shot-board-stitcher` first.

## Model

```json
{
  "source": {"id": "sha256:...", "width": 0, "height": 0},
  "columns": [
    {
      "name": "column-1",
      "x_center": 0.0,
      "notes": [
        {
          "color": "yellow",
          "text": null,
          "bbox": [0, 0, 0, 0],
          "confidence": 0.0,
          "needs_review": true
        }
      ]
    }
  ],
  "unresolved": []
}
```

Column names default to `column-N` ordered left-to-right unless a header strip is OCR'd.

## Script

```bash
python3 scripts/extract_sticky_notes.py board.jpg
python3 scripts/extract_sticky_notes.py board.jpg -o notes.json --ocr
```

Requires OpenCV and NumPy. OCR uses pytesseract when `--ocr` is set and Tesseract is installed; otherwise geometry-only with `needs_review: true`.

## Rules

- Segment by HSV color clusters typical of sticky notes (yellow, pink, green, blue, orange).
- Bin notes into columns by x-center clustering / gaps — do not force a fixed column count.
- Never invent note text when OCR is absent or low-confidence; use `null` + `needs_review`.
- Validate the photo with `image-ingest-hardening` before trusting results.
- For action items on a marker board (not stickies), use `python-whiteboard-parser` then `board-action-exporter`.
