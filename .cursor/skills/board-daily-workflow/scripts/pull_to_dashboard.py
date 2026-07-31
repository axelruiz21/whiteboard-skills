#!/usr/bin/env python3
"""Pull clear exported action items into the Ops/Calendar dashboard.

Posts each activity to POST /api/directions with external_id = idempotency_key
so re-runs do not duplicate. Standard library only.

Default base URL: http://127.0.0.1:8000 (override with --url or BOARD_DASHBOARD_URL).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_URL = os.environ.get("BOARD_DASHBOARD_URL", "http://127.0.0.1:8000")


def activity_to_direction(act: dict[str, Any], *, floor: str) -> dict[str, Any]:
    title = str(act.get("title") or "").strip()
    parts = [title]
    if act.get("section"):
        parts.append(f"Section: {act['section']}")
    if act.get("due"):
        parts.append(f"Due: {act['due']}")
    if act.get("owner"):
        parts.append(f"Owner: {act['owner']}")
    if act.get("source"):
        parts.append(f"Board source: {act['source']}")
    message = "\n".join(parts)
    priority = "P1" if str(act.get("priority") or "").upper() == "SOS" else "P2"
    return {
        "message": message,
        "author": str(act.get("owner") or "whiteboard"),
        "floor": floor,
        "priority": priority,
        "source": "Whiteboard parser",
        "external_id": str(act.get("idempotency_key") or ""),
        "link": "",
    }


def post_direction(base_url: str, payload: dict[str, Any], secret: str = "") -> dict[str, Any]:
    url = base_url.rstrip("/") + "/api/directions"
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["X-Teams-Secret"] = secret
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_activities(path: Path) -> list[dict[str, Any]]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(doc, dict) and isinstance(doc.get("activities"), list):
        return [a for a in doc["activities"] if isinstance(a, dict)]
    if isinstance(doc, list):
        return [a for a in doc if isinstance(a, dict)]
    raise ValueError("expected {activities:[...]} JSON")


def pull(
    activities_path: Path,
    *,
    base_url: str,
    floor: str,
    secret: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    acts = load_activities(activities_path)
    # Only clear rows (exporter already omits needs_review; belt-and-suspenders)
    clear = [a for a in acts if not a.get("needs_review")]
    created = 0
    skipped = 0
    errors: list[str] = []
    results: list[dict[str, Any]] = []

    for act in clear:
        payload = activity_to_direction(act, floor=floor)
        if not payload["external_id"]:
            errors.append(f"missing idempotency_key for: {payload['message'][:60]}")
            continue
        if dry_run:
            results.append({"dry_run": True, "payload": payload})
            created += 1
            continue
        try:
            row = post_direction(base_url, payload, secret)
            # directions endpoint returns existing row on dedupe without a flag;
            # treat presence of id as success either way
            results.append({"id": row.get("id"), "title": row.get("title"), "external_id": payload["external_id"]})
            created += 1
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            errors.append(f"HTTP {exc.code}: {body[:200]}")
        except urllib.error.URLError as exc:
            errors.append(f"unreachable {base_url}: {exc}")
            break

    return {
        "base_url": base_url,
        "input": str(activities_path),
        "candidates": len(clear),
        "posted": created,
        "errors": errors,
        "dry_run": dry_run,
        "results": results,
        "skipped_needs_review": len(acts) - len(clear),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pull ops_dashboard_activities.json into Calendar/Ops dashboard."
    )
    parser.add_argument(
        "activities",
        type=Path,
        nargs="?",
        default=Path("out/day/export/ops_dashboard_activities.json"),
        help="Exported activities JSON (default: out/day/export/ops_dashboard_activities.json)",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help=f"Dashboard base URL (default: {DEFAULT_URL})",
    )
    parser.add_argument(
        "--floor",
        default=os.environ.get("BOARD_DASHBOARD_FLOOR", "1F"),
        help="Floor code required by dashboard (1F or 2F)",
    )
    parser.add_argument(
        "--secret",
        default=os.environ.get("BOARD_DASHBOARD_SECRET", ""),
        help="Optional shared secret (unused by /api/directions; reserved)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print payloads without POSTing",
    )
    args = parser.parse_args(argv)

    if not args.activities.is_file():
        print(f"error: not a file: {args.activities}", file=sys.stderr)
        return 2

    try:
        summary = pull(
            args.activities,
            base_url=args.url,
            floor=args.floor,
            secret=args.secret,
            dry_run=args.dry_run,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(summary, indent=2))
    if summary["errors"] and summary["posted"] == 0:
        return 2
    if summary["errors"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
