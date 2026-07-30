# Python Whiteboard Parser Skill

A public Cursor Agent Skill for designing local-first Python pipelines that extract whiteboard text and preserve lists, action items, tables, diagrams, coordinates, confidence, and review flags.

## Install

Copy the skill into a project:

```bash
mkdir -p .cursor/skills
cp -R /path/to/this-repo/.cursor/skills/python-whiteboard-parser .cursor/skills/
```

Or install it as a personal skill:

```bash
mkdir -p ~/.cursor/skills
cp -R /path/to/this-repo/.cursor/skills/python-whiteboard-parser ~/.cursor/skills/
```

In this repository, the skill is located at:

```text
.cursor/skills/python-whiteboard-parser/
```

Cursor can automatically apply it when a request mentions whiteboard OCR, photographed notes, meeting-board transcription, or converting whiteboard images into structured data.

## What it emphasizes

- OpenCV preprocessing tailored to glare, perspective, faint strokes, shadows, and colored markers
- Local OCR through Tesseract with bounded preprocessing and page-segmentation ensembles
- Layout-aware extraction of text, lists, action items, tables, and diagrams
- Evidence coordinates, explicit uncertainty, and human-review flags
- Typed, testable, stateless Python suitable for batch processing or FastAPI workers

## License

[MIT](LICENSE)
