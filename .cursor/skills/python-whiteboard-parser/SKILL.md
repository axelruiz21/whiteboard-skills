---
name: python-whiteboard-parser
description: Builds and improves local-first Python workflows that extract text, lists, action items, tables, and diagram structure from a whiteboard photo. Use when a user mentions whiteboard OCR, photographed notes, marker-board images, meeting-board transcription, or converting whiteboard content into structured JSON, Markdown, or CSV.
---

# Python Whiteboard Parser

Use this skill to turn a whiteboard image into traceable structured data. Favor deterministic Python processing and local OCR. Never silently invent unreadable content.

Hand off when the request is not single-image extraction: comparing two photos of the same board belongs to the `board-change-tracker` skill, rendering the extracted graph belongs to `diagram-to-mermaid`, measuring extraction accuracy belongs to `ocr-extraction-eval`, multi-panel mosaics belong to `multi-shot-board-stitcher`, sticky-note/kanban boards belong to `sticky-note-board-parser`, safe load gates belong to `image-ingest-hardening`, daily ingest/review belongs to `board-daily-workflow`, action-item export belongs to `board-action-exporter`, and FastAPI job serving belongs to `fastapi-cpu-bound-jobs`.

## Package layout

Implement stages under `python/whiteboard_parser/` (see [REFERENCE.md](REFERENCE.md)):

```text
python/whiteboard_parser/
  config.py      # PipelineConfig
  models.py      # Pydantic / serializable output
  ingest.py      # calls image-ingest-hardening when available
  quality.py     # stub
  rectify.py     # stub
  ocr.py         # stub adapter
  pipeline.py    # run_pipeline() ingest-only by default
```

```bash
PYTHONPATH=.cursor/skills/python-whiteboard-parser/python python3 -c \
  "from whiteboard_parser import run_pipeline, PipelineConfig; \
   print(run_pipeline('fixtures/boards/example.jpg', PipelineConfig()))"
```

## Default stack

- Python 3.11+
- OpenCV and NumPy for image analysis and preprocessing
- Pillow for image loading and EXIF orientation
- Tesseract through `pytesseract` for OCR
- Pydantic for validated output models
- `rapidfuzz` for conservative OCR-result reconciliation

Use another local OCR engine only as an explicit fallback. Keep OCR engines behind a small adapter so they can be replaced without changing the parsing pipeline.

## Pipeline

1. **Ingest safely**
   - Preserve the original image.
   - Correct EXIF orientation and convert to a consistent color space.
   - Reject unsupported or decompression-bomb images and enforce pixel limits.
   - Record a SHA-256 source identifier and processing settings.

2. **Measure image quality**
   - Estimate blur with variance of Laplacian.
   - Detect clipping, glare, low contrast, shadows, and insufficient resolution.
   - If the long side of the decoded image is under **2000px**, emit a `warning` (or `unusable` when under **1200px**) that the file is likely a chat/Google Photos preview, not a camera original—see [Getting full-res photos into the parser](#getting-full-res-photos-into-the-parser).
   - Return actionable warnings instead of forcing low-confidence extraction.

3. **Rectify the board**
   - Detect the largest plausible quadrilateral using edges and contours.
   - Apply a perspective transform only when corner confidence is adequate.
   - Retain both rectified and original-coordinate transforms for traceability.

4. **Create OCR variants**
   - Normalize illumination using LAB/HSV luminance channels.
   - Reduce glare conservatively; do not erase faint marker strokes.
   - Generate a small ensemble: color-enhanced, grayscale, adaptive-thresholded, and inverted variants.
   - Deskew each variant. Avoid one universal threshold.

5. **Segment by layout**
   - Detect text regions, horizontal/vertical rules, arrows, boxes, sticky notes, and marker-color clusters separately.
   - Use morphology and connected components to propose regions.
   - OCR regions rather than only the full board.

6. **Run OCR with coordinates**
   - Request word text, confidence, bounding box, line/block identifiers, and OCR variant.
   - Try a limited set of Tesseract page segmentation modes appropriate to each region.
   - Reconcile overlapping candidates by spatial overlap, normalized text similarity, confidence, and agreement across variants.
   - Preserve alternatives when candidates disagree materially.

7. **Reconstruct structure**
   - Group words into lines using vertical overlap and baseline proximity.
   - Group lines into sections by spacing, alignment, enclosing boxes, and marker color.
   - Detect bullets, numbered lists, checkboxes, owners, dates, and action-item verbs.
   - Infer tables only when repeated row/column alignment or visible rules support them.
   - Represent diagrams as nodes and edges; do not flatten arrows into prose.

8. **Validate**
   - Validate all output with Pydantic.
   - Flag suspicious dates, duplicated lines, orphan arrows, malformed tables, and low-confidence fields.
   - Include evidence coordinates and confidence for every extracted item.
   - Save optional debug overlays showing regions, reading order, and rejected candidates.

## Confidence rules

- Keep OCR confidence separate from structural-inference confidence.
- Calibrate thresholds from real samples; do not present Tesseract scores as probabilities.
- Mark uncertain text with alternatives and `needs_review: true`.
- Use `null` for unreadable values. Never guess missing characters, owners, dates, or connections.
- Compute aggregate confidence from the weakest required evidence, not a simple optimistic average.

## Required output

Default to UTF-8 JSON plus a readable Markdown rendering. Use this minimum shape:

```json
{
  "source": {"id": "sha256:...", "width": 0, "height": 0},
  "quality": {"status": "ok|warning|unusable", "warnings": []},
  "sections": [
    {
      "id": "section-1",
      "title": null,
      "text_lines": [],
      "lists": [],
      "action_items": [],
      "tables": [],
      "diagram": {"nodes": [], "edges": []},
      "bbox": [0, 0, 0, 0],
      "confidence": 0.0,
      "needs_review": false
    }
  ],
  "unresolved": []
}
```

Coordinates use `[x, y, width, height]` in the rectified image. Include the inverse transform when consumers need original-image coordinates.

## Implementation conventions

- Build pure, typed functions for each stage; pass configuration explicitly.
- Keep the service stateless. Store artifacts externally when exposed through FastAPI.
- Bound CPU, memory, file size, OCR time, and worker concurrency.
- Run CPU-heavy OpenCV/OCR work outside the async event loop.
- Emit structured logs with source ID, stage duration, warnings, and engine version; never log full extracted content by default.
- Make every stage reproducible with a random seed and serialized configuration.
- Cache by source hash, pipeline version, and configuration hash.

## Testing

Create fixtures covering glare, perspective distortion, colored markers, faint strokes, dense text, tables, arrows, sticky notes, handwriting, and blank boards.

Test at three levels:

1. Unit-test transforms, grouping, candidate reconciliation, and schema validation.
2. Golden-test representative images with normalized text and geometry tolerances.
3. Measure character/word error rate, action-item precision/recall, table cell accuracy, diagram edge F1, and review-flag recall using the `ocr-extraction-eval` skill.

Do not optimize only for OCR text accuracy. A parser succeeds when it preserves layout, uncertainty, and provenance.

## Delivery checklist

- [ ] Original image remains unchanged
- [ ] Quality warnings are actionable
- [ ] Text has coordinates and confidence
- [ ] Lists, action items, tables, and diagrams remain distinct
- [ ] Uncertainty is visible and machine-readable
- [ ] Debug overlays can explain extraction
- [ ] Resource limits and malformed inputs are tested
- [ ] Output schema and pipeline version are recorded

## Getting full-res photos into the parser

Phone cameras are fine for handwriting OCR. What breaks parsing is the **transfer path**: **Cursor chat attachments are always downscaled** (often to ~1024×576). Google Photos “Share” and Storage saver can also shrink the file. Always parse a file on disk—never attach the image in chat.

### Easy daily loop (recommended)

1. Download/share the **original** to the Mac (Google Photos → Download, USB, or Quick Share) — typically lands in `~/Downloads`.
2. From the project root, run:

```bash
./ingest-board
# or: ./ingest-board ~/Downloads/YOUR_PHOTO.jpg
# or: drop into fixtures/boards/inbox/ then: ./ingest-board --from-inbox
```

3. Paste the clipboard prompt into Cursor (already copied), e.g. `Parse the whiteboard photo at @fixtures/boards/….jpg`.

`ingest-board` copies the file into `fixtures/boards/`, rejects chat-sized previews, converts HEIC via `sips` when needed, and copies the `@` prompt to the clipboard.

### Other transfer options

1. USB-C → File transfer / MTP → `DCIM/Camera` (or `DCIM/Samsung`) → drop into `fixtures/boards/inbox/`.
2. Samsung Quick Share into `fixtures/boards/inbox/`.
3. Google Photos **Original quality** backup → desktop **Download** (not Share into chat).

### Avoid for OCR

- Attaching or pasting the image in the Cursor chat composer
- Google Photos Storage saver as the only copy
- Screenshots of the photo, or messaging “optimized” shares

### Confirm manually

```bash
python3 .cursor/skills/python-whiteboard-parser/scripts/check_image_resolution.py PATH
```

Expect roughly `(4000, 2250)` / `(4032, 3024) JPEG`, not `(1024, 576)`.

Capture still matters at full resolution: fill the frame with the board, prefer landscape with edges visible, even lighting, minimal glare.

For implementation details and tuning guidance, read [REFERENCE.md](REFERENCE.md).
