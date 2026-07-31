#!/usr/bin/env python3
"""Export action_items from parsed board JSON to dry-run / GitHub / ops dashboard.

Standard library only. needs_review items are skipped unless --allow-review-items.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any


def normalize_text(text: str) -> str:
    collapsed = " ".join(unicodedata.normalize("NFKC", text).split())
    return collapsed.casefold()


def idempotency_key(source_id: str, text: str) -> str:
    payload = f"{source_id}\n{normalize_text(text)}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def slug(text: str, limit: int = 48) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", normalize_text(text)).strip("-")
    return (s or "item")[:limit]


def iter_action_items(doc: dict[str, Any]) -> list[dict[str, Any]]:
    source_id = (doc.get("source") or {}).get("id") or doc.get("source_id") or "unknown"
    out: list[dict[str, Any]] = []
    sections = doc.get("sections")
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            title = section.get("title")
            for item in section.get("action_items") or []:
                if not isinstance(item, dict):
                    continue
                text = item.get("text")
                if not text:
                    continue
                out.append(
                    {
                        "text": str(text),
                        "owner": item.get("owner"),
                        "due": item.get("due"),
                        "confidence": item.get("confidence"),
                        "needs_review": bool(item.get("needs_review")),
                        "section_id": section.get("id"),
                        "section_title": title,
                        "source_id": source_id,
                        "priority": item.get("priority"),
                        "row": item.get("row"),
                    }
                )
    else:
        for item in doc.get("action_items") or []:
            if not isinstance(item, dict) or not item.get("text"):
                continue
            out.append(
                {
                    "text": str(item["text"]),
                    "owner": item.get("owner"),
                    "due": item.get("due"),
                    "confidence": item.get("confidence"),
                    "needs_review": bool(item.get("needs_review")),
                    "section_id": None,
                    "section_title": None,
                    "source_id": source_id,
                    "priority": item.get("priority"),
                    "row": item.get("row"),
                }
            )
    return out


def to_dryrun_record(item: dict[str, Any], skipped: bool) -> dict[str, Any]:
    key = idempotency_key(str(item["source_id"]), item["text"])
    return {
        "idempotency_key": key,
        "title": item["text"],
        "owner": item.get("owner"),
        "due": item.get("due"),
        "confidence": item.get("confidence"),
        "needs_review": item.get("needs_review"),
        "section_id": item.get("section_id"),
        "section_title": item.get("section_title"),
        "source_id": item.get("source_id"),
        "priority": item.get("priority"),
        "row": item.get("row"),
        "skipped": skipped,
        "skip_reason": "needs_review" if skipped else None,
        "provider": "dry-run",
    }


def to_ops_activity(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": record["title"],
        "status": "unscheduled",
        "owner": record.get("owner"),
        "due": record.get("due"),
        "source": record.get("source_id"),
        "needs_review": record.get("needs_review"),
        "idempotency_key": record["idempotency_key"],
        "section": record.get("section_title") or record.get("section_id"),
        "priority": record.get("priority"),
    }


def github_markdown(record: dict[str, Any]) -> str:
    lines = [
        f"# {record['title']}",
        "",
        f"- **Source:** `{record['source_id']}`",
        f"- **Idempotency:** `{record['idempotency_key']}`",
    ]
    if record.get("section_title") or record.get("section_id"):
        lines.append(
            f"- **Section:** {record.get('section_title') or record.get('section_id')}"
        )
    if record.get("owner") is not None:
        lines.append(f"- **Owner:** {record['owner']}")
    if record.get("due") is not None:
        lines.append(f"- **Due:** {record['due']}")
    if record.get("priority") is not None:
        lines.append(f"- **Priority:** {record['priority']}")
    if record.get("row") is not None:
        lines.append(f"- **Row / area:** {record['row']}")
    if record.get("confidence") is not None:
        lines.append(f"- **Confidence:** {record['confidence']}")
    lines.append("")
    lines.append("_Exported from whiteboard parser (dry-run)._")
    lines.append("")
    return "\n".join(lines)


def export(
    doc: dict[str, Any],
    out_dir: Path,
    *,
    allow_review_items: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    gh_dir = out_dir / "github"
    gh_dir.mkdir(exist_ok=True)

    dryrun: list[dict[str, Any]] = []
    activities: list[dict[str, Any]] = []
    exported = 0
    skipped = 0
    truncated = 0

    for item in iter_action_items(doc):
        skip = bool(item.get("needs_review")) and not allow_review_items
        record = to_dryrun_record(item, skipped=skip)
        if skip:
            dryrun.append(record)
            skipped += 1
            continue
        if limit is not None and exported >= limit:
            record = {**record, "skipped": True, "skip_reason": "sample_limit"}
            dryrun.append(record)
            truncated += 1
            continue
        dryrun.append(record)
        exported += 1
        activities.append(to_ops_activity(record))
        name = f"{record['idempotency_key'][:12]}-{slug(record['title'])}.md"
        (gh_dir / name).write_text(github_markdown(record), encoding="utf-8")

    dryrun_path = out_dir / "issues.dryrun.json"
    dryrun_path.write_text(
        json.dumps(
            {
                "items": dryrun,
                "exported": exported,
                "skipped": skipped,
                "truncated": truncated,
                "limit": limit,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    ops_path = out_dir / "ops_dashboard_activities.json"
    ops_path.write_text(
        json.dumps({"activities": activities}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {
        "exported": exported,
        "skipped": skipped,
        "truncated": truncated,
        "limit": limit,
        "dryrun": str(dryrun_path),
        "ops_dashboard": str(ops_path),
        "github_dir": str(gh_dir),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export board action_items to dry-run / GitHub MD / ops dashboard JSON."
    )
    parser.add_argument("input", type=Path, help="Parsed board JSON")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("out/export"),
        help="Output directory (default: out/export)",
    )
    parser.add_argument(
        "--allow-review-items",
        action="store_true",
        help="Include needs_review items (default: skip them)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Sample-before-bulk: export at most N eligible items (preview gate)",
    )
    args = parser.parse_args(argv)

    if not args.input.is_file():
        print(f"error: not a file: {args.input}", file=sys.stderr)
        return 2

    doc = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        print("error: root JSON must be an object", file=sys.stderr)
        return 2

    if args.limit is not None and args.limit < 1:
        print("error: --limit must be >= 1", file=sys.stderr)
        return 2

    summary = export(
        doc,
        args.output,
        allow_review_items=args.allow_review_items,
        limit=args.limit,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
