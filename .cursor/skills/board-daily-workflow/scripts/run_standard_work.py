#!/usr/bin/env python3
"""Lean daily standard work: ingest → (parse gate) → exception review → export.

One operator command for the CTQ path: trusted action items toward the
ops dashboard. Sibling skills (Mermaid, stitcher, eval, change-tracker) stay
pull tools — not part of daily takt.

Exit codes:
  0  clear — export written, no action_item exceptions (or --force-export)
  1  exceptions remain — review.md written; export still written for clear items
  2  hard failure (missing inputs, bad image, script error)
  3  parse required — Madlibs prompt printed; stop before review/export
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def repo_root() -> Path:
    cwd = Path.cwd()
    if (cwd / ".cursor" / "skills" / "board-daily-workflow").is_dir():
        return cwd
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / ".cursor" / "skills" / "board-daily-workflow").is_dir():
            return parent
        if (parent / ".git").is_dir() and (parent / "fixtures" / "boards").is_dir():
            return parent
    return cwd


def skill_script(root: Path, skill: str, name: str) -> Path:
    return root / ".cursor" / "skills" / skill / "scripts" / name


def run_py(script: Path, args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return data


def parse_matches_image(parsed: dict[str, Any], image: Path | None) -> bool:
    if image is None or not image.is_file():
        return False
    source = parsed.get("source") or {}
    sid = str(source.get("id") or "")
    digest = sha256_file(image)
    if sid == f"sha256:{digest}":
        return True
    # Path match fallback when id was vision-assisted / not hashed
    spath = source.get("path")
    if spath and Path(spath).resolve() == image.resolve():
        return True
    return False


def open_path(path: Path) -> bool:
    """Open a file with the OS default app (macOS `open`, else xdg-open)."""
    if not path.is_file():
        return False
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
            return True
        subprocess.run(["xdg-open", str(path)], check=False)
        return True
    except (FileNotFoundError, OSError):
        return False


def write_day_summary(
    out_dir: Path,
    *,
    image: Path | None,
    parsed_path: Path,
    review_path: Path,
    export_summary: dict[str, Any] | None,
    exception_count: int,
    parse_prompt: str | None,
    pull_summary: dict[str, Any] | None = None,
) -> Path:
    lines = [
        "# Board day — standard work",
        "",
        f"- Image: `{image}`" if image else "- Image: _(reuse existing parse)_",
        f"- Parsed: `{parsed_path}`",
        f"- Exception review: `{review_path}` ({exception_count} action_item flags)",
        "",
    ]
    if parse_prompt:
        lines.extend(
            [
                "## Blocked: parse required",
                "",
                "Paste in Cursor (do not attach the image):",
                "",
                f"```text",
                parse_prompt,
                "```",
                "",
                "Then re-run: `./run-board-day --skip-ingest`",
                "",
            ]
        )
    if export_summary:
        lines.extend(
            [
                "## Export (clear items only — needs_review skipped)",
                "",
                f"- Exported: {export_summary.get('exported')}",
                f"- Skipped (review/limit): {export_summary.get('skipped')} "
                f"(truncated={export_summary.get('truncated')})",
                f"- Ops dashboard JSON: `{export_summary.get('ops_dashboard')}`",
                f"- Dry-run issues: `{export_summary.get('dryrun')}`",
                "",
                "## Human takt (exceptions only)",
                "",
                "1. Open the review checklist; confirm or correct flagged action items in "
                "`parsed_board.json` (set `needs_review: false` only when verified).",
                "2. Re-run `./run-board-day --skip-ingest` to refresh export.",
                "3. Pull clear rows into the dashboard:",
                "   `./run-board-day --skip-ingest --pull-dashboard`",
                "   (or set `BOARD_DASHBOARD_URL` if not on http://127.0.0.1:8000).",
                "",
            ]
        )
    if pull_summary:
        lines.extend(
            [
                "## Dashboard pull",
                "",
                f"- Posted: {pull_summary.get('posted')} / {pull_summary.get('candidates')}",
                f"- URL: `{pull_summary.get('base_url')}`",
                "",
            ]
        )
        if pull_summary.get("errors"):
            lines.append("Errors:")
            for err in pull_summary["errors"]:
                lines.append(f"- {err}")
            lines.append("")
    path = out_dir / "DAY.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    root = repo_root()
    parser = argparse.ArgumentParser(
        description=(
            "Lean standard work: ingest/harden → parse gate → action_item exceptions "
            "→ dry-run export. Other suite skills are pull-only."
        )
    )
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        help="Photo to ingest (default: newest ~/Downloads, or use --from-inbox)",
    )
    parser.add_argument("--from-inbox", action="store_true", help="Newest fixtures/boards/inbox/")
    parser.add_argument(
        "--skip-ingest",
        action="store_true",
        help="Skip photo ingest; use existing parsed_board.json",
    )
    parser.add_argument(
        "--parsed",
        type=Path,
        default=Path("parsed_board.json"),
        help="Parsed board JSON (default: ./parsed_board.json)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("out/day"),
        help="Output directory for review + export (default: out/day)",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=None,
        help="Optional Auto-fill sample size before full export (e.g. 3)",
    )
    parser.add_argument(
        "--force-export",
        action="store_true",
        help="Export even when action_item exceptions remain (still skips needs_review rows)",
    )
    parser.add_argument(
        "--allow-unparsed",
        action="store_true",
        help="Continue with existing parse even if source hash does not match ingested image",
    )
    parser.add_argument(
        "--pull-dashboard",
        action="store_true",
        help="POST clear exported activities to Calendar/Ops dashboard (/api/directions)",
    )
    parser.add_argument(
        "--dashboard-url",
        default=os.environ.get("BOARD_DASHBOARD_URL", "http://127.0.0.1:8000"),
        help="Dashboard base URL for --pull-dashboard",
    )
    parser.add_argument(
        "--dashboard-floor",
        default=os.environ.get("BOARD_DASHBOARD_FLOOR", "1F"),
        help="Floor for pulled activities (1F or 2F)",
    )
    parser.add_argument(
        "--no-open-review",
        action="store_true",
        help="Do not open review.md when exceptions remain (default: open on macOS)",
    )
    args = parser.parse_args(argv)

    out_dir = (root / args.out).resolve() if not args.out.is_absolute() else args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    parsed_path = (root / args.parsed).resolve() if not args.parsed.is_absolute() else args.parsed

    ingest_script = skill_script(root, "python-whiteboard-parser", "ingest_board_photo.py")
    validate_script = skill_script(root, "image-ingest-hardening", "validate_image.py")
    review_script = skill_script(root, "board-daily-workflow", "review_queue.py")
    export_script = skill_script(root, "board-action-exporter", "export_action_items.py")
    pull_script = skill_script(root, "board-daily-workflow", "pull_to_dashboard.py")

    image: Path | None = None
    parse_prompt: str | None = None

    # --- 1. Ingest / harden ---
    if not args.skip_ingest:
        if not ingest_script.is_file():
            print(f"error: missing {ingest_script}", file=sys.stderr)
            return 2
        ingest_args: list[str] = ["--no-clipboard"]
        if args.from_inbox:
            ingest_args.append("--from-inbox")
        elif args.path:
            ingest_args.append(str(args.path.expanduser()))
        proc = run_py(ingest_script, ingest_args, cwd=root)
        sys.stderr.write(proc.stderr)
        sys.stdout.write(proc.stdout)
        if proc.returncode not in (0,):
            return 2 if proc.returncode >= 2 else proc.returncode

        # Recover ingested path from stdout: "ingested: …"
        for line in proc.stdout.splitlines():
            if line.startswith("ingested:"):
                image = Path(line.split("ingested:", 1)[1].strip())
                break
        if image is None:
            print("error: could not determine ingested image path", file=sys.stderr)
            return 2

        if validate_script.is_file():
            v = run_py(validate_script, [str(image)], cwd=root)
            if v.returncode == 2:
                sys.stderr.write(v.stderr or v.stdout)
                print("error: image failed hardening gate", file=sys.stderr)
                return 2
            if v.returncode == 1:
                print("warning: image resolution warning (continuing)", file=sys.stderr)

        rel = image.relative_to(root) if image.is_relative_to(root) else image
        parse_prompt = f"Parse the whiteboard photo at @{rel}"
    else:
        print("skip-ingest: using existing parse artifacts", file=sys.stderr)

    # --- 2. Parse gate ---
    if not parsed_path.is_file():
        if parse_prompt is None:
            parse_prompt = "Parse the whiteboard photo at @fixtures/boards/<your-file>.jpg"
        print("\nPARSE REQUIRED — paste in Cursor (do not attach image):\n", file=sys.stderr)
        print(f"  {parse_prompt}\n", file=sys.stderr)
        write_day_summary(
            out_dir,
            image=image,
            parsed_path=parsed_path,
            review_path=out_dir / "review.md",
            export_summary=None,
            exception_count=-1,
            parse_prompt=parse_prompt,
        )
        print(f"wrote {out_dir / 'DAY.md'}", file=sys.stderr)
        return 3

    try:
        parsed = load_json(parsed_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if image is not None and not parse_matches_image(parsed, image) and not args.allow_unparsed:
        print(
            "PARSE STALE — parsed_board.json does not match ingested image.\n"
            "Paste in Cursor, then re-run with --skip-ingest:\n",
            file=sys.stderr,
        )
        print(f"  {parse_prompt}\n", file=sys.stderr)
        write_day_summary(
            out_dir,
            image=image,
            parsed_path=parsed_path,
            review_path=out_dir / "review.md",
            export_summary=None,
            exception_count=-1,
            parse_prompt=parse_prompt,
        )
        print(f"wrote {out_dir / 'DAY.md'}", file=sys.stderr)
        return 3

    # --- 3. Exception review (action items only = CTQ) ---
    review_path = out_dir / "review.md"
    r = run_py(
        review_script,
        [str(parsed_path), "-o", str(review_path), "--kind", "action_item"],
        cwd=root,
    )
    sys.stderr.write(r.stderr)
    if r.returncode not in (0, 1):
        sys.stderr.write(r.stdout)
        return 2
    exception_count = 0
    meta = run_py(
        review_script,
        [str(parsed_path), "--json", "--kind", "action_item"],
        cwd=root,
    )
    if meta.returncode in (0, 1) and meta.stdout.strip():
        try:
            exception_count = int(json.loads(meta.stdout).get("count") or 0)
        except json.JSONDecodeError:
            exception_count = -1

    # --- 4. Dry-run export (clear items only) ---
    export_args = [str(parsed_path), "-o", str(out_dir / "export")]
    if args.sample_limit is not None:
        export_args.extend(["--limit", str(args.sample_limit)])
    e = run_py(export_script, export_args, cwd=root)
    sys.stderr.write(e.stderr)
    if e.returncode != 0:
        sys.stderr.write(e.stdout)
        print("error: export failed", file=sys.stderr)
        return 2
    try:
        export_summary = json.loads(e.stdout)
    except json.JSONDecodeError:
        export_summary = {"raw": e.stdout}

    # --- 5. Optional dashboard pull (clear items only; idempotent) ---
    pull_summary: dict[str, Any] | None = None
    ops_json = out_dir / "export" / "ops_dashboard_activities.json"
    if args.pull_dashboard:
        if not pull_script.is_file():
            print(f"error: missing {pull_script}", file=sys.stderr)
            return 2
        p = run_py(
            pull_script,
            [
                str(ops_json),
                "--url",
                args.dashboard_url,
                "--floor",
                args.dashboard_floor,
            ],
            cwd=root,
        )
        sys.stderr.write(p.stderr)
        try:
            pull_summary = json.loads(p.stdout) if p.stdout.strip() else {"errors": ["empty pull output"]}
        except json.JSONDecodeError:
            pull_summary = {"errors": [p.stdout or p.stderr or "pull failed"], "posted": 0}
        if p.returncode == 2 and not (pull_summary or {}).get("posted"):
            print("error: dashboard pull failed", file=sys.stderr)
            # still write DAY.md below

    day_path = write_day_summary(
        out_dir,
        image=image,
        parsed_path=parsed_path,
        review_path=review_path,
        export_summary=export_summary if isinstance(export_summary, dict) else None,
        exception_count=exception_count,
        parse_prompt=None,
        pull_summary=pull_summary,
    )

    if exception_count > 0 and not args.no_open_review:
        if open_path(review_path):
            print(f"opened {review_path}", file=sys.stderr)

    print(json.dumps(
        {
            "ok": exception_count == 0 or args.force_export,
            "exceptions": exception_count,
            "review": str(review_path),
            "export": export_summary,
            "pull": pull_summary,
            "summary": str(day_path),
        },
        indent=2,
    ))

    if exception_count > 0 and not args.force_export:
        print(
            f"\n{exception_count} action_item exception(s) — confirm in {review_path}, "
            "fix parsed_board.json, re-run ./run-board-day --skip-ingest "
            "[--pull-dashboard]",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
