# Whiteboard Parsing Reference

## Suggested package boundaries

```text
whiteboard_parser/
  config.py
  models.py
  ingest.py
  quality.py
  rectify.py
  variants.py
  segment.py
  ocr.py
  reconcile.py
  structure.py
  render.py
  pipeline.py
```

Keep OpenCV arrays internal. Public models should use serializable coordinates, text, confidence, provenance, and review flags.

## Preprocessing guidance

- Correct orientation before any geometric analysis.
- Downscale only for board detection; perform final OCR on the highest useful resolution.
- Use CLAHE on luminance for uneven lighting.
- Compare black-hat morphology and adaptive thresholding for dark marker on a bright board.
- Use HSV masks to retain colored marker strokes that grayscale conversion weakens.
- Detect glare from high value, low saturation, and local clipping; label rather than aggressively inpaint text-sized regions.
- Estimate perspective corners from multiple cues. A large rectangular contour alone can be a wall, screen, or frame.

## OCR ensemble

Start with Tesseract configurations selected by region:

- `--psm 6`: a uniform text block
- `--psm 11`: sparse text
- `--psm 7`: a single line
- `--psm 13`: a raw line with minimal layout assumptions

Do not run every mode on every image. Select modes from region geometry and cap the ensemble. Retain the engine version, language data, preprocessing variant, and configuration with each candidate.

Handwriting quality varies substantially with Tesseract. If a local handwriting model is added, expose it through the same OCR adapter and compare it against labeled fixtures before making it the default.

## Candidate reconciliation

For candidate words or lines:

1. Map all boxes into rectified-image coordinates.
2. Build overlap groups using intersection-over-union plus baseline distance.
3. Normalize Unicode and whitespace without destroying punctuation.
4. Rank agreement across independent variants above a single high engine score.
5. Merge only near-identical candidates; retain meaningful alternatives.
6. Flag a region for review when the winning candidate lacks independent support or has conflicting high-quality alternatives.

Never use fuzzy matching to rewrite extracted text into a more plausible phrase without evidence.

## Structure heuristics

### Reading order

Cluster into columns or sections before sorting top-to-bottom. Enclosing boxes, large whitespace gaps, headings, and marker colors are useful signals.

### Action items

Treat an item as an action-item candidate when layout and text provide evidence such as:

- an unchecked checkbox
- an owner marker (`@name`, initials, or an `Owner` column)
- a due-date field
- imperative or commitment language

Return the original text and separately parsed fields. Do not remove uncertain owner/date text from the source line.

### Tables

Infer a table from visible rules or repeated alignment across at least two rows and two columns. Preserve merged or ambiguous cells and attach cell-level evidence boxes.

### Diagrams

Detect boxes and text first, then arrow shafts and arrowheads. Create edges only when endpoint geometry supports a direction. Represent uncertain endpoints as alternatives rather than attaching an arrow to the nearest node automatically.

## Quality gates

Tune thresholds on the target camera and board conditions. Useful signals include:

- blur score
- minimum character-height estimate
- saturated-pixel ratio
- glare coverage
- foreground/background contrast
- board-corner confidence
- OCR agreement rate
- unresolved-region ratio

An unusable image should produce a valid result with quality diagnostics and no fabricated sections.

## API deployment

For FastAPI:

- accept uploads into bounded temporary storage
- validate decoded image dimensions, not only file headers
- return `202 Accepted` and queue expensive jobs
- use a process pool or worker system for OpenCV and OCR
- store job state and artifacts outside the API process
- expose idempotency through the source/configuration hash
- delete temporary files in `finally` blocks

Container images need pinned Tesseract language data and system packages. Include engine and trained-data versions in results so golden tests remain explainable.
