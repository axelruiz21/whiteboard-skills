#!/usr/bin/env python3
"""Adapt whiteboard-parser JSON into the ocr-extraction-eval record shape.

Flattens sections into corpus-level text_lines, action_items, tables, and
diagram edges so score.py can compare against labeled truth without hand glue.
Standard library only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        text = value.get("text")
        return None if text is None else str(text)
    return str(value)


def _line_record(item: Any) -> dict[str, Any] | None:
    if isinstance(item, str):
        return {"text": item}
    if not isinstance(item, dict):
        return None
    text = item.get("text")
    if text is None:
        return None
    record: dict[str, Any] = {"text": str(text)}
    if item.get("bbox") is not None:
        record["bbox"] = item["bbox"]
    return record


def _action_record(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        text = _as_text(item)
        return None if text is None else {"text": text, "owner": None, "due": None}
    text = item.get("text")
    if text is None:
        return None
    return {
        "text": str(text),
        "owner": item.get("owner"),
        "due": item.get("due"),
    }


def _table_record(table: Any) -> dict[str, Any] | None:
    if not isinstance(table, dict):
        return None
    if "cells" in table and isinstance(table["cells"], list):
        return {"cells": table["cells"]}
    headers = table.get("headers") or []
    rows = table.get("rows") or []
    if not headers and not rows:
        return None
    cells: list[list[Any]] = []
    if headers:
        cells.append([str(h) for h in headers])
    for row in rows:
        if isinstance(row, list):
            cells.append(row)
        elif isinstance(row, dict):
            if headers:
                cells.append([row.get(h) for h in headers])
            else:
                # Stable key order for deterministic output
                keys = sorted(row.keys())
                cells.append([row[k] for k in keys])
        else:
            cells.append([row])
    return {"cells": cells}


def _edge_record(edge: Any) -> dict[str, Any] | None:
    if not isinstance(edge, dict):
        return None
    source = edge.get("source", edge.get("from"))
    target = edge.get("target", edge.get("to"))
    if source is None or target is None:
        return None
    return {"source": str(source), "target": str(target)}


def adapt_parser_output(doc: dict[str, Any]) -> dict[str, Any]:
    source = doc.get("source") or {}
    source_id = source.get("id") or doc.get("source_id") or "unknown"

    text_lines: list[dict[str, Any]] = []
    action_items: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    needs_review: list[Any] = []

    # Top-level unresolved / needs_review
    for item in doc.get("unresolved") or []:
        needs_review.append(item)
    if isinstance(doc.get("needs_review"), list):
        needs_review.extend(doc["needs_review"])

    sections = doc.get("sections")
    if not isinstance(sections, list):
        sections = [doc] if any(k in doc for k in ("text_lines", "action_items")) else []

    for section in sections:
        if not isinstance(section, dict):
            continue
        if section.get("needs_review"):
            needs_review.append(
                {"section_id": section.get("id"), "reason": "section needs_review"}
            )
        for line in section.get("text_lines") or []:
            rec = _line_record(line)
            if rec:
                text_lines.append(rec)
            if isinstance(line, dict) and line.get("needs_review"):
                needs_review.append({"text": line.get("text"), "reason": "line needs_review"})
        for item in section.get("action_items") or []:
            rec = _action_record(item)
            if rec:
                action_items.append(rec)
            if isinstance(item, dict) and item.get("needs_review"):
                needs_review.append({"text": item.get("text"), "reason": "action needs_review"})
        for table in section.get("tables") or []:
            rec = _table_record(table)
            if rec:
                tables.append(rec)
        diagram = section.get("diagram") or {}
        if isinstance(diagram, dict):
            for edge in diagram.get("edges") or []:
                rec = _edge_record(edge)
                if rec:
                    edges.append(rec)

    # Also accept already-flat records
    if not text_lines:
        for line in doc.get("text_lines") or []:
            rec = _line_record(line)
            if rec:
                text_lines.append(rec)
    if not action_items:
        for item in doc.get("action_items") or []:
            rec = _action_record(item)
            if rec:
                action_items.append(rec)
    if not tables:
        for table in doc.get("tables") or []:
            rec = _table_record(table)
            if rec:
                tables.append(rec)
    if not edges:
        diagram = doc.get("diagram") or {}
        if isinstance(diagram, dict):
            for edge in diagram.get("edges") or []:
                rec = _edge_record(edge)
                if rec:
                    edges.append(rec)

    return {
        "source_id": str(source_id),
        "text_lines": text_lines,
        "action_items": action_items,
        "tables": tables,
        "diagram": {"edges": edges},
        "needs_review": needs_review,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert whiteboard-parser JSON to eval record shape."
    )
    parser.add_argument("input", type=Path, help="Parser JSON file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write adapted JSON to this path (default: stdout)",
    )
    args = parser.parse_args(argv)

    if not args.input.is_file():
        print(f"error: not a file: {args.input}", file=sys.stderr)
        return 2

    doc = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        print("error: root JSON value must be an object", file=sys.stderr)
        return 2

    adapted = adapt_parser_output(doc)
    text = json.dumps(adapted, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
