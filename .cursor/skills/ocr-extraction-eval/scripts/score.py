#!/usr/bin/env python3
"""Score extraction output against labeled ground truth.

Reads eval records (see SKILL.md) and reports transcription error rates,
action-item precision/recall, table cell accuracy, and diagram edge F1.
Standard library only.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable, Sequence

MAX_SEQUENCE = 20000


def normalize(text: Any, ignore_case: bool) -> str:
    if text is None:
        return ""
    collapsed = " ".join(unicodedata.normalize("NFKC", str(text)).split())
    return collapsed.casefold() if ignore_case else collapsed


def edit_distance(a: Sequence[Any], b: Sequence[Any]) -> int:
    if len(a) > MAX_SEQUENCE or len(b) > MAX_SEQUENCE:
        raise ValueError(
            f"sequence longer than {MAX_SEQUENCE} units; score per region instead of per board"
        )
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, item_a in enumerate(a, start=1):
        current = [i]
        for j, item_b in enumerate(b, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (item_a != item_b),
                )
            )
        previous = current
    return previous[-1]


def similarity(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def greedy_match(
    truth: Sequence[str], pred: Sequence[str], threshold: float
) -> list[tuple[int, int, float]]:
    """Pair truth and prediction indices, best similarity first, one use each."""
    candidates = [
        (similarity(t, p), ti, pi)
        for ti, t in enumerate(truth)
        for pi, p in enumerate(pred)
    ]
    candidates.sort(key=lambda c: (-c[0], c[1], c[2]))
    used_truth: set[int] = set()
    used_pred: set[int] = set()
    matches: list[tuple[int, int, float]] = []
    for score, ti, pi in candidates:
        if score < threshold:
            break
        if ti in used_truth or pi in used_pred:
            continue
        used_truth.add(ti)
        used_pred.add(pi)
        matches.append((ti, pi, score))
    return matches


@dataclass
class Counts:
    """Micro-averaged accumulators, summed across sources before dividing."""

    char_errors: int = 0
    char_total: int = 0
    word_errors: int = 0
    word_total: int = 0
    items_matched: int = 0
    items_truth: int = 0
    items_pred: int = 0
    owner_correct: int = 0
    owner_total: int = 0
    due_correct: int = 0
    due_total: int = 0
    cells_correct: int = 0
    cells_total: int = 0
    table_shape_mismatches: int = 0
    tables_missed: int = 0
    tables_spurious: int = 0
    edges_matched: int = 0
    edges_truth: int = 0
    edges_pred: int = 0
    flagged_pred: int = 0

    def add(self, other: "Counts") -> None:
        for name in self.__dataclass_fields__:
            setattr(self, name, getattr(self, name) + getattr(other, name))


def ratio(errors: int, total: int, empty_value: float | None = 0.0) -> float | None:
    return errors / total if total else empty_value


def prf(matched: int, truth_total: int, pred_total: int) -> dict[str, float]:
    precision = matched / pred_total if pred_total else (1.0 if not truth_total else 0.0)
    recall = matched / truth_total if truth_total else (1.0 if not pred_total else 0.0)
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall)
        else 0.0
    )
    return {"precision": precision, "recall": recall, "f1": f1}


def lines_text(record: dict, ignore_case: bool) -> str:
    lines = record.get("text_lines") or []
    return "\n".join(normalize(line.get("text"), ignore_case) for line in lines).strip()


def item_texts(record: dict, ignore_case: bool) -> list[str]:
    return [normalize(i.get("text"), ignore_case) for i in record.get("action_items") or []]


def edge_keys(record: dict, ignore_case: bool) -> list[str]:
    diagram = record.get("diagram") or {}
    keys = []
    for edge in diagram.get("edges") or []:
        source = normalize(edge.get("source"), ignore_case)
        target = normalize(edge.get("target"), ignore_case)
        label = normalize(edge.get("label"), ignore_case)
        keys.append(f"{source}\u2192{target}|{label}")
    return keys


def score_tables(truth: dict, pred: dict, ignore_case: bool, counts: Counts) -> None:
    truth_tables = truth.get("tables") or []
    pred_tables = pred.get("tables") or []
    flat = lambda t: " | ".join(
        normalize(cell, ignore_case) for row in t.get("cells") or [] for cell in row
    )
    matches = greedy_match(
        [flat(t) for t in truth_tables], [flat(t) for t in pred_tables], threshold=0.4
    )
    matched_pred = {pi for _, pi, _ in matches}
    matched_truth = {ti for ti, _, _ in matches}

    for ti, pi, _ in matches:
        truth_rows = truth_tables[ti].get("cells") or []
        pred_rows = pred_tables[pi].get("cells") or []
        if len(truth_rows) != len(pred_rows) or any(
            len(tr) != len(pr) for tr, pr in zip(truth_rows, pred_rows)
        ):
            counts.table_shape_mismatches += 1
        for r, truth_row in enumerate(truth_rows):
            pred_row = pred_rows[r] if r < len(pred_rows) else []
            for c, truth_cell in enumerate(truth_row):
                counts.cells_total += 1
                pred_cell = pred_row[c] if c < len(pred_row) else None
                if normalize(truth_cell, ignore_case) == normalize(pred_cell, ignore_case):
                    counts.cells_correct += 1

    for ti, table in enumerate(truth_tables):
        if ti in matched_truth:
            continue
        counts.tables_missed += 1
        counts.cells_total += sum(len(row) for row in table.get("cells") or [])
    counts.tables_spurious += len(pred_tables) - len(matched_pred)


def score_record(truth: dict, pred: dict, ignore_case: bool, threshold: float) -> Counts:
    counts = Counts()

    truth_text = lines_text(truth, ignore_case)
    pred_text = lines_text(pred, ignore_case)
    counts.char_total = len(truth_text)
    counts.char_errors = edit_distance(truth_text, pred_text)
    truth_words = truth_text.split()
    pred_words = pred_text.split()
    counts.word_total = len(truth_words)
    counts.word_errors = edit_distance(truth_words, pred_words)

    truth_items = truth.get("action_items") or []
    pred_items = pred.get("action_items") or []
    matches = greedy_match(
        item_texts(truth, ignore_case), item_texts(pred, ignore_case), threshold
    )
    counts.items_truth = len(truth_items)
    counts.items_pred = len(pred_items)
    counts.items_matched = len(matches)
    for ti, pi, _ in matches:
        for key, correct_attr, total_attr in (
            ("owner", "owner_correct", "owner_total"),
            ("due", "due_correct", "due_total"),
        ):
            expected = truth_items[ti].get(key)
            if expected is None:
                continue
            setattr(counts, total_attr, getattr(counts, total_attr) + 1)
            if normalize(expected, ignore_case) == normalize(pred_items[pi].get(key), ignore_case):
                setattr(counts, correct_attr, getattr(counts, correct_attr) + 1)

    score_tables(truth, pred, ignore_case, counts)

    truth_edges = edge_keys(truth, ignore_case)
    pred_edges = edge_keys(pred, ignore_case)
    remaining = list(pred_edges)
    for key in truth_edges:
        if key in remaining:
            remaining.remove(key)
            counts.edges_matched += 1
    counts.edges_truth = len(truth_edges)
    counts.edges_pred = len(pred_edges)
    counts.flagged_pred = len(pred.get("needs_review") or [])
    return counts


def metrics_from(counts: Counts) -> dict[str, Any]:
    items = prf(counts.items_matched, counts.items_truth, counts.items_pred)
    edges = prf(counts.edges_matched, counts.edges_truth, counts.edges_pred)
    return {
        "cer": ratio(counts.char_errors, counts.char_total),
        "wer": ratio(counts.word_errors, counts.word_total),
        "action_items_precision": items["precision"],
        "action_items_recall": items["recall"],
        "action_items_f1": items["f1"],
        "owner_accuracy": ratio(counts.owner_correct, counts.owner_total, empty_value=None),
        "due_accuracy": ratio(counts.due_correct, counts.due_total, empty_value=None),
        "owner_evaluated": counts.owner_total,
        "due_evaluated": counts.due_total,
        "table_cell_accuracy": ratio(counts.cells_correct, counts.cells_total, empty_value=None),
        "table_shape_mismatches": counts.table_shape_mismatches,
        "tables_missed": counts.tables_missed,
        "tables_spurious": counts.tables_spurious,
        "edges_precision": edges["precision"],
        "edges_recall": edges["recall"],
        "edges_f1": edges["f1"],
        "flagged_for_review": counts.flagged_pred,
    }


def load_records(path: Path) -> dict[str, dict]:
    """Key records by their source_id so truth and predictions pair by content."""
    files = [path] if path.is_file() else sorted(path.glob("*.json"))
    records: dict[str, dict] = {}
    for file in files:
        record = json.loads(file.read_text(encoding="utf-8"))
        key = str(record.get("source_id") or file.stem)
        if key in records:
            raise SystemExit(f"duplicate source_id {key!r} in {path}")
        records[key] = record
    if not records:
        raise SystemExit(f"no JSON records found in {path}")
    return records


def check_thresholds(summary: dict[str, Any], thresholds: dict[str, dict]) -> list[str]:
    violations = []
    for metric, bounds in thresholds.items():
        if metric not in summary:
            violations.append(f"{metric}: unknown metric")
            continue
        value = summary[metric]
        if value is None:
            violations.append(f"{metric}: no data to evaluate")
            continue
        if "min" in bounds and value < bounds["min"]:
            violations.append(f"{metric}: {value:.4f} below min {bounds['min']}")
        if "max" in bounds and value > bounds["max"]:
            violations.append(f"{metric}: {value:.4f} above max {bounds['max']}")
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--truth", required=True, type=Path, help="ground truth file or directory")
    parser.add_argument("--pred", required=True, type=Path, help="prediction file or directory")
    parser.add_argument("--ignore-case", action="store_true")
    parser.add_argument("--match-threshold", type=float, default=0.85)
    parser.add_argument("--thresholds", type=Path, help="JSON file of per-metric min/max gates")
    parser.add_argument("--metadata", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--quiet", action="store_true", help="suppress the stderr summary")
    args = parser.parse_args(argv)

    truth_records = load_records(args.truth)
    pred_records = load_records(args.pred)

    total = Counts()
    per_source = []
    missing = []
    for source_id, truth in sorted(truth_records.items()):
        pred = pred_records.get(source_id)
        if pred is None:
            missing.append(source_id)
            pred = {}
        counts = score_record(truth, pred, args.ignore_case, args.match_threshold)
        total.add(counts)
        per_source.append({"source_id": source_id, **metrics_from(counts)})

    summary = metrics_from(total)
    metadata = dict(pair.split("=", 1) for pair in args.metadata if "=" in pair)
    thresholds = json.loads(args.thresholds.read_text(encoding="utf-8")) if args.thresholds else {}
    violations = check_thresholds(summary, thresholds)

    report = {
        "summary": summary,
        "per_source": per_source,
        "sources_scored": len(per_source),
        "missing_predictions": missing,
        "unmatched_predictions": sorted(set(pred_records) - set(truth_records)),
        "metadata": metadata,
        "violations": violations,
    }
    json.dump(report, sys.stdout, indent=2, allow_nan=False)
    sys.stdout.write("\n")

    if not args.quiet:
        print(f"\nscored {len(per_source)} source(s)", file=sys.stderr)
        for key in ("cer", "wer", "action_items_f1", "table_cell_accuracy", "edges_f1"):
            value = summary[key]
            shown = "n/a" if value is None else f"{value:.4f}"
            print(f"  {key:22} {shown}", file=sys.stderr)
        if len(per_source) > 1:
            for row in sorted(per_source, key=lambda r: -r["cer"])[:3]:
                print(f"  worst cer: {row['source_id']} {row['cer']:.4f}", file=sys.stderr)
        for note in missing:
            print(f"  missing prediction: {note}", file=sys.stderr)
        for violation in violations:
            print(f"  THRESHOLD {violation}", file=sys.stderr)

    return 1 if violations or missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
