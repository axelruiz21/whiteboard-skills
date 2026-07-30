---
name: ocr-extraction-eval
description: Builds labeled fixture sets and scores extraction pipelines with character and word error rate, field precision and recall, table cell accuracy, and diagram edge F1, then gates regressions in CI. Use when measuring OCR accuracy, scoring an extraction pipeline against ground truth, creating golden fixtures, tuning preprocessing empirically, calibrating confidence, or adding extraction quality regression tests.
---

# OCR Extraction Eval

Use this skill to make extraction quality measurable. Any preprocessing, OCR, or structuring change must be justified by a score on a fixture set, not by inspecting one image.

This skill scores extraction output. It does not perform extraction. For producing whiteboard output, use the `python-whiteboard-parser` skill.

## Ground truth format

Store one JSON record per source image, in the eval record shape:

```json
{
  "source_id": "board-2024-03-11-a",
  "text_lines": [{"text": "Ship auth by Friday", "bbox": [12, 40, 320, 28]}],
  "action_items": [{"text": "Ship auth by Friday", "owner": "AR", "due": "2024-03-15"}],
  "tables": [{"cells": [["Task", "Owner"], ["Auth", "AR"]]}],
  "diagram": {"edges": [{"source": "Client", "target": "Gateway"}]},
  "needs_review": []
}
```

Predictions use the same shape, so the whiteboard parser output needs a thin adapter rather than a parallel format. Keep `bbox` optional; it is only used to disambiguate repeated identical text.

## Fixture rules

- Label real photographs. Synthetic clean renders overstate accuracy badly.
- Cover glare, perspective, faint or dying marker, colored marker, dense text, tables, arrows, sticky notes, multiple handwriting styles, and at least one blank board.
- Keep a `dev` split for tuning and a `test` split that is scored rarely and never tuned against.
- Record camera, lighting, and board surface for each fixture so failures cluster into fixable groups.
- Transcribe exactly what is on the board, including misspellings. Do not silently correct the human who wrote it.
- Mark genuinely illegible content as `null` in truth and add it to `needs_review`, so a parser is not punished for correctly refusing to guess.

## Scoring

Run the bundled scorer:

```bash
python scripts/score.py --truth fixtures/dev/truth --pred out/dev --ignore-case
```

Both arguments accept a single JSON file or a directory of them. Records pair on `source_id`, falling back to filename, so truth and prediction files need not share names. A runnable pair lives in `scripts/example/`. Add `--thresholds thresholds.json` to fail the run when a metric regresses:

```json
{"cer": {"max": 0.18}, "action_items_f1": {"min": 0.75}, "edges_f1": {"min": 0.6}}
```

The scorer exits non-zero on any violation or missing prediction, prints a human summary to stderr, and writes a metrics JSON document to stdout for CI artifacts. Metrics with nothing to score are `null` rather than zero, so an empty category never looks like a perfect or failing result. Pass `--metadata engine=tesseract-5.3.4` to stamp engine and configuration versions into the report.

## Metrics that matter

| Metric | Reads as | Watch for |
|---|---|---|
| `cer` / `wer` | raw transcription quality | dominated by the densest fixture unless you also read per-source values |
| `action_items_f1` | usable output quality | precision falls when headings are misread as tasks |
| `owner_accuracy` / `due_accuracy` | field parsing on matched items | high scores on very few matches mean nothing |
| `table_cell_accuracy` | structure recovery | shape mismatches are reported separately and must not be averaged away |
| `edges_f1` | diagram fidelity | direction errors count as wrong, which is intended |

Always read per-source results, not only the aggregate. A mean hides one catastrophic fixture behind nine good ones, and the catastrophic one is the bug.

## Confidence calibration

A confidence score is only useful if it predicts correctness. Bin predictions by reported confidence, compute observed accuracy per bin, and compare. If items at 0.9 are right 60% of the time, the pipeline is overconfident and downstream `needs_review` gating is meaningless. Recalibrate the mapping rather than moving the review threshold until the dashboard looks acceptable.

Track review-flag quality separately: of the items that were wrong, what fraction were flagged? A parser that is wrong and confident is far worse than one that is wrong and honest.

## CI gating

- Gate on per-metric thresholds, never on a single blended score.
- Commit thresholds next to the fixtures and tighten them as the pipeline improves; a threshold that never moves stops being a gate.
- Record OCR engine version, language data version, and pipeline configuration hash in the metrics output. A score is not comparable across engine upgrades without it.
- Store the metrics JSON as a build artifact so regressions can be bisected.

## Anti-patterns

- Tuning preprocessing against the `test` split, then reporting that split as evidence.
- Reporting accuracy without reporting how many items were extracted at all; dropping hard content inflates precision.
- Fuzzy-matching predictions to truth so loosely that a wrong owner or date still counts as a match.
- Averaging across fixtures of wildly different text volume without also reporting the per-source table.
