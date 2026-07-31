---
name: board-action-exporter
description: Converts parsed whiteboard action_items into dry-run issue records, GitHub issue markdown, or ops-dashboard activity JSON with idempotency keys and a hard block on silently exporting needs_review items. Use when turning board tasks into GitHub, Linear, or Jira issues, feeding a calendar ops dashboard, or exporting action items from parsed_board.json.
---

# Board Action Exporter

Use this skill **after** extraction and review. Parsing belongs to `python-whiteboard-parser`; triage belongs to `board-daily-workflow`. This skill never invents owners or due dates.

## Rules

1. **Dry-run by default.** Write artifacts; do not call live issue APIs unless explicitly extended later.
2. **Idempotency key** = `sha256(source_id + "\\n" + normalized_text)`. Re-exports of the same board produce the same keys.
3. **`needs_review: true` items are skipped** unless `--allow-review-items` is passed. Never auto-create them silently.
4. Preserve `owner`, `due`, section title, and confidence on each record.
5. Ops-dashboard shape: `{title, status, owner, due, source, needs_review, idempotency_key}` with `status` defaulting to `unscheduled`.

## Script

```bash
# Sample-before-bulk (Auto-fill gate): preview 3 eligible items first
python3 scripts/export_action_items.py scripts/example/board_slice.json -o /tmp/export --limit 3
python3 scripts/export_action_items.py parsed_board.json -o out/export
python3 scripts/export_action_items.py parsed_board.json -o out/export --allow-review-items
```

Always run a small `--limit` sample and verify titles/owners/dates before a full dashboard or issue dump.

Writes under the output directory:

- `issues.dryrun.json` — provider-neutral records
- `github/` — one Markdown file per exportable item
- `ops_dashboard_activities.json` — dashboard intake list

## Providers

| Output | Use when |
|---|---|
| dry-run JSON | reviewing what would be created |
| GitHub markdown | pasting or opening issues manually |
| ops dashboard JSON | loading into a create-ops-dashboard style planner |

Live Linear/Jira/GitHub API creates are out of scope for the bundled script.
