# Whiteboard Skills for Cursor

A collection of [Cursor Agent Skills](https://cursor.com/docs) for getting structured, trustworthy data off physical whiteboards with local-first Python. Each skill is self-contained; install one or all of them.

## Skills

| Skill | What it does |
|---|---|
| [`python-whiteboard-parser`](.cursor/skills/python-whiteboard-parser/SKILL.md) | Extracts text, lists, action items, tables, and diagram structure from a whiteboard photo with OpenCV and Tesseract, preserving coordinates, confidence, and review flags |
| [`board-change-tracker`](.cursor/skills/board-change-tracker/SKILL.md) | Diffs two or more photos of the same board and reports what was added, erased, moved, or edited, without mistaking a person standing in front of the board for an erasure |
| [`diagram-to-mermaid`](.cursor/skills/diagram-to-mermaid/SKILL.md) | Renders an extracted node/edge graph as Mermaid, with identifier sanitizing, label escaping, and uncertain edges kept visible |
| [`ocr-extraction-eval`](.cursor/skills/ocr-extraction-eval/SKILL.md) | Scores extraction output against labeled fixtures and gates regressions in CI |
| [`image-ingest-hardening`](.cursor/skills/image-ingest-hardening/SKILL.md) | Sniffs MIME, caps bytes/pixels, applies EXIF orientation, hashes sources, and rejects bombs or chat-sized previews |
| [`board-daily-workflow`](.cursor/skills/board-daily-workflow/SKILL.md) | Daily loop: full-res transfer → ingest → parse → review queue → export |
| [`board-action-exporter`](.cursor/skills/board-action-exporter/SKILL.md) | Dry-run export of action items to GitHub markdown and ops-dashboard JSON with idempotency keys |
| [`fastapi-cpu-bound-jobs`](.cursor/skills/fastapi-cpu-bound-jobs/SKILL.md) | FastAPI patterns for process-pool OCR jobs, 202 Accepted, and content-hash idempotency |
| [`multi-shot-board-stitcher`](.cursor/skills/multi-shot-board-stitcher/SKILL.md) | Stitches overlapping board photos into one mosaic for OCR |
| [`sticky-note-board-parser`](.cursor/skills/sticky-note-board-parser/SKILL.md) | Parses sticky-note / kanban boards by color and column position |

They compose as a toolbox. **Daily takt** is lean standard work — not all ten skills:

```bash
./run-board-day                              # ingest → parse gate → exceptions → export
./run-board-day --skip-ingest                # after Cursor parse
./run-board-day --skip-ingest --pull-dashboard   # push clear items to Ops dashboard
```

Pull the others when needed (change-track, Mermaid, stitcher, eval, FastAPI). See [`board-daily-workflow`](.cursor/skills/board-daily-workflow/SKILL.md).

## Install

```bash
git clone https://github.com/axelruiz21/whiteboard-skills.git
cd whiteboard-skills
./install.sh                              # all skills, personal (~/.cursor/skills)
./install.sh --project ~/code/my-app      # all skills into a project
./install.sh --list                       # show available skills
./install.sh diagram-to-mermaid           # install just one
```

Personal skills are available in every project; project skills live in the repository and are shared with anyone who clones it. Re-running the installer refuses to overwrite an existing skill unless you pass `--force`.

## Included scripts

Bundled scripts prefer the standard library; vision skills need OpenCV/Pillow as noted:

```bash
python3 .cursor/skills/ocr-extraction-eval/scripts/score.py \
  --truth .cursor/skills/ocr-extraction-eval/scripts/example/truth.json \
  --pred  .cursor/skills/ocr-extraction-eval/scripts/example/prediction.json --ignore-case

python3 .cursor/skills/ocr-extraction-eval/scripts/adapt_parser_output.py \
  parsed_board.json -o /tmp/eval_pred.json

python3 .cursor/skills/diagram-to-mermaid/scripts/graph_to_mermaid.py \
  .cursor/skills/diagram-to-mermaid/scripts/example/graph.json --direction LR

python3 .cursor/skills/image-ingest-hardening/scripts/validate_image.py PATH.jpg --json

python3 .cursor/skills/board-daily-workflow/scripts/review_queue.py parsed_board.json

python3 .cursor/skills/board-action-exporter/scripts/export_action_items.py \
  .cursor/skills/board-action-exporter/scripts/example/board_slice.json -o /tmp/export

python3 .cursor/skills/multi-shot-board-stitcher/scripts/stitch_board.py \
  left.jpg right.jpg -o /tmp/mosaic.jpg

python3 .cursor/skills/sticky-note-board-parser/scripts/extract_sticky_notes.py board.jpg

# Fail loudly on chat/Photos previews before OCR (exit 1 = warning, 2 = unusable)
python3 .cursor/skills/python-whiteboard-parser/scripts/check_image_resolution.py PATH.jpg

# Lean daily standard work (preferred)
./run-board-day
./run-board-day --from-inbox
./run-board-day --skip-ingest

# Ingest only (clipboard Madlibs prompt) if you are not ready to run the full day chain
./ingest-board
./ingest-board ~/Downloads/20260730_101644.jpg
```


FastAPI demo (optional deps):

```bash
pip install fastapi uvicorn
python3 .cursor/skills/fastapi-cpu-bound-jobs/scripts/example_job_api.py
```

The skills that perform image work expect OpenCV, Pillow, and a local Tesseract install in the project they are applied to. Prefer `./ingest-board` over attaching images in chat—see the whiteboard parser skill’s “Getting full-res photos into the parser” section.

## Design stance

- Local-first OCR; no image leaves the machine by default.
- Uncertainty is data. Unreadable content is `null` and flagged, never guessed.
- Every extracted item carries evidence coordinates so a human can check it.
- Quality claims are backed by fixtures and scores, not by one good demo photo.

## License

[MIT](LICENSE)
