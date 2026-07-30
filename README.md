# Whiteboard Skills for Cursor

A collection of [Cursor Agent Skills](https://cursor.com/docs) for getting structured, trustworthy data off physical whiteboards with local-first Python. Each skill is self-contained; install one or all of them.

## Skills

| Skill | What it does |
|---|---|
| [`python-whiteboard-parser`](.cursor/skills/python-whiteboard-parser/SKILL.md) | Extracts text, lists, action items, tables, and diagram structure from a whiteboard photo with OpenCV and Tesseract, preserving coordinates, confidence, and review flags |
| [`board-change-tracker`](.cursor/skills/board-change-tracker/SKILL.md) | Diffs two or more photos of the same board and reports what was added, erased, moved, or edited, without mistaking a person standing in front of the board for an erasure |
| [`diagram-to-mermaid`](.cursor/skills/diagram-to-mermaid/SKILL.md) | Renders an extracted node/edge graph as Mermaid, with identifier sanitizing, label escaping, and uncertain edges kept visible |
| [`ocr-extraction-eval`](.cursor/skills/ocr-extraction-eval/SKILL.md) | Scores extraction output against labeled fixtures and gates regressions in CI |

They compose: the parser produces the structured record, the tracker diffs records across time, the converter renders the diagram, and the eval harness proves any of it actually works.

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

Both bundled scripts are standard library only, so no virtual environment is needed to run them:

```bash
python3 .cursor/skills/ocr-extraction-eval/scripts/score.py \
  --truth .cursor/skills/ocr-extraction-eval/scripts/example/truth.json \
  --pred  .cursor/skills/ocr-extraction-eval/scripts/example/prediction.json --ignore-case

python3 .cursor/skills/diagram-to-mermaid/scripts/graph_to_mermaid.py \
  .cursor/skills/diagram-to-mermaid/scripts/example/graph.json --direction LR
```

The skills that perform image work expect OpenCV, Pillow, and a local Tesseract install in the project they are applied to.

## Design stance

- Local-first OCR; no image leaves the machine by default.
- Uncertainty is data. Unreadable content is `null` and flagged, never guessed.
- Every extracted item carries evidence coordinates so a human can check it.
- Quality claims are backed by fixtures and scores, not by one good demo photo.

## License

[MIT](LICENSE)
