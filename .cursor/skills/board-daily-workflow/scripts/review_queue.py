#!/usr/bin/env python3
"""Build a Markdown review checklist from parsed whiteboard JSON.

Verification-scoped: lists leaf needs_review / unresolved items. Section-level
flags are omitted when children are already listed (avoids double-counting).
Quality warnings are informational by default and do not fail the exit code
unless --include-quality is passed.

Exit 1 when content items remain. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


def _leaf_items_for_section(section: dict[str, Any]) -> list[dict[str, Any]]:
    sid = section.get("id")
    items: list[dict[str, Any]] = []
    for field in ("text_lines", "action_items"):
        for entry in section.get(field) or []:
            if isinstance(entry, dict) and entry.get("needs_review"):
                items.append(
                    {
                        "kind": "action_item" if field == "action_items" else "text_line",
                        "section": sid,
                        "text": entry.get("text"),
                        "bbox": entry.get("bbox"),
                        "alternatives": entry.get("alternatives"),
                        "owner": entry.get("owner"),
                        "due": entry.get("due"),
                    }
                )
    for lst in section.get("lists") or []:
        if not isinstance(lst, dict):
            continue
        for entry in lst.get("items") or []:
            if isinstance(entry, dict) and entry.get("needs_review"):
                items.append(
                    {
                        "kind": "list_item",
                        "section": sid,
                        "text": entry.get("text"),
                        "bbox": entry.get("bbox"),
                        "alternatives": entry.get("alternatives"),
                    }
                )
    for table in section.get("tables") or []:
        if not isinstance(table, dict):
            continue
        row_flags = 0
        for row in table.get("rows") or []:
            if isinstance(row, dict) and row.get("needs_review"):
                row_flags += 1
                items.append(
                    {
                        "kind": "table_row",
                        "section": sid,
                        "text": json.dumps(
                            {k: v for k, v in row.items() if k != "needs_review"},
                            ensure_ascii=False,
                        ),
                        "bbox": None,
                    }
                )
        # Table-level flag only when no row-level flags (scope: one gate, not both)
        if table.get("needs_review") and row_flags == 0:
            items.append(
                {
                    "kind": "table",
                    "section": sid,
                    "text": table.get("id") or "table",
                    "bbox": table.get("bbox"),
                }
            )
    diagram = section.get("diagram") or {}
    if isinstance(diagram, dict):
        for edge in diagram.get("edges") or []:
            if isinstance(edge, dict) and edge.get("needs_review"):
                items.append(
                    {
                        "kind": "edge",
                        "section": sid,
                        "text": f"{edge.get('source') or edge.get('from')} → "
                        f"{edge.get('target') or edge.get('to')}",
                        "bbox": None,
                    }
                )
    return items


def _collect(
    doc: dict[str, Any], *, include_quality: bool
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (content_items, quality_items)."""
    content: list[dict[str, Any]] = []
    quality: list[dict[str, Any]] = []

    for u in doc.get("unresolved") or []:
        if isinstance(u, dict):
            content.append(
                {
                    "kind": "unresolved",
                    "section": None,
                    "text": u.get("reason") or json.dumps(u, ensure_ascii=False),
                    "bbox": u.get("bbox"),
                }
            )
        else:
            content.append(
                {"kind": "unresolved", "section": None, "text": str(u), "bbox": None}
            )

    q = doc.get("quality") or {}
    if q.get("status") in ("warning", "unusable"):
        for w in q.get("warnings") or []:
            quality.append(
                {"kind": "quality", "section": None, "text": str(w), "bbox": None}
            )

    board = doc.get("board") or {}
    for key, val in board.items():
        if isinstance(val, dict) and val.get("needs_review"):
            content.append(
                {
                    "kind": "board_field",
                    "section": key,
                    "text": val.get("text"),
                    "bbox": val.get("bbox"),
                    "alternatives": val.get("alternatives"),
                }
            )

    for section in doc.get("sections") or []:
        if not isinstance(section, dict):
            continue
        leaves = _leaf_items_for_section(section)
        content.extend(leaves)
        # Section flag only when no leaf already scopes the problem
        if section.get("needs_review") and not leaves:
            content.append(
                {
                    "kind": "section",
                    "section": section.get("id"),
                    "text": section.get("title") or section.get("id"),
                    "bbox": section.get("bbox"),
                }
            )

    if include_quality:
        return content + quality, quality
    return content, quality


def render_markdown(
    path: Path,
    content: list[dict[str, Any]],
    quality: list[dict[str, Any]],
) -> str:
    counts = Counter(i.get("kind") or "item" for i in content)
    lines = [
        f"# Review queue — `{path.name}`",
        "",
        f"**Scope:** {len(content)} content item(s) need verification.",
        "",
    ]
    if counts:
        lines.append("By kind: " + ", ".join(f"`{k}`={n}" for k, n in sorted(counts.items())))
        lines.append("")
    if quality:
        lines.append("## Quality (informational — does not block export)")
        lines.append("")
        for w in quality:
            lines.append(f"- {w.get('text')}")
        lines.append("")

    if not content:
        lines.append("All clear for content review.")
        lines.append("")
        return "\n".join(lines)

    lines.append("## Checklist")
    lines.append("")
    for i, item in enumerate(content, start=1):
        loc = item.get("section") or "—"
        kind = item.get("kind") or "item"
        text = item.get("text")
        lines.append(f"### {i}. [{kind}] section `{loc}`")
        lines.append("")
        lines.append(f"- [ ] {text}")
        if item.get("alternatives"):
            lines.append(f"  - alternatives: {item['alternatives']}")
        if item.get("owner") is not None:
            lines.append(f"  - owner: {item['owner']}")
        if item.get("due") is not None:
            lines.append(f"  - due: {item['due']}")
        if item.get("bbox") is not None:
            lines.append(f"  - bbox: {item['bbox']}")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "List needs_review / unresolved items from parsed board JSON "
            "(Verification gate for the daily chain)."
        )
    )
    parser.add_argument(
        "input",
        type=Path,
        nargs="?",
        default=Path("parsed_board.json"),
        help="Parsed board JSON (default: parsed_board.json)",
    )
    parser.add_argument("-o", "--output", type=Path, help="Write Markdown checklist")
    parser.add_argument("--json", action="store_true", help="Emit items JSON on stdout")
    parser.add_argument(
        "--include-quality",
        action="store_true",
        help="Treat quality warnings as failing content items",
    )
    parser.add_argument(
        "--kind",
        action="append",
        dest="kinds",
        help="Only include these kinds (repeatable), e.g. --kind action_item",
    )
    args = parser.parse_args(argv)

    if not args.input.is_file():
        print(f"error: not a file: {args.input}", file=sys.stderr)
        return 2

    doc = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        print("error: root JSON must be an object", file=sys.stderr)
        return 2

    content, quality = _collect(doc, include_quality=False)
    if args.kinds:
        allow = set(args.kinds)
        content = [i for i in content if i.get("kind") in allow]
    gate_items = content + (quality if args.include_quality else [])

    if args.json:
        print(
            json.dumps(
                {
                    "count": len(gate_items),
                    "content_count": len(content),
                    "quality_count": len(quality),
                    "items": gate_items,
                    "quality": quality,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        md = render_markdown(args.input, content, quality)
        if args.output:
            args.output.write_text(md, encoding="utf-8")
            print(
                f"wrote {args.output} ({len(content)} content, {len(quality)} quality)",
                file=sys.stderr,
            )
        else:
            sys.stdout.write(md)

    return 1 if gate_items else 0


if __name__ == "__main__":
    sys.exit(main())
