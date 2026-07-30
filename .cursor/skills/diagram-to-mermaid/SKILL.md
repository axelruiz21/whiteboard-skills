---
name: diagram-to-mermaid
description: Converts extracted node and edge graphs into Mermaid flowcharts, Graphviz DOT, draw.io XML, or Excalidraw scenes while preserving uncertain edges, labels, and grouping. Use when rendering a parsed diagram as Mermaid, exporting nodes and edges to a diagram format, turning extracted graph structure into an editable diagram file, or escaping labels that break Mermaid syntax.
---

# Diagram to Mermaid

Use this skill to turn a graph that some upstream process already extracted into a renderable diagram. Detecting boxes and arrows in an image belongs to the `python-whiteboard-parser` skill; this skill starts from its `diagram` output.

## Input

```json
{
  "nodes": [{"id": "client", "label": "Client app", "shape": "round", "section": "Edge", "confidence": 0.9}],
  "edges": [{"source": "client", "target": "gateway", "label": "HTTPS", "directed": true, "confidence": 0.4, "needs_review": true}]
}
```

Only `nodes[].id`, `edges[].source`, and `edges[].target` are required. A full whiteboard-parser record is also accepted; its `diagram` key is unwrapped automatically.

## Converting

```bash
python scripts/graph_to_mermaid.py graph.json --direction LR --title "Auth flow"
```

Options: `--confidence-threshold` (default 0.6) sets what counts as uncertain, `--output` writes to a file, and `--strict` fails the run on any warning. A runnable example lives in `scripts/example/graph.json`.

## Rules the converter enforces

**Uncertainty survives the conversion.** Edges below the confidence threshold or marked `needs_review` render as dotted links with a `?` in the label and are listed in a trailing `%%` comment. Never silently drop a low-confidence edge; a diagram that quietly omits a connection is worse than one that shows it as unverified.

**Identifiers are sanitized, labels are escaped.** These are the failures that produce a blank Mermaid canvas with no useful error:

| Input | Problem | Handling |
|---|---|---|
| node id `end` | lowercase `end` closes a subgraph block | renamed to a prefixed id |
| `graph`, `class`, `style`, `click`, `direction` | flowchart keywords | renamed the same way |
| id with spaces, dashes, or accents | invalid identifier | non-word characters become underscores |
| `#` in a label | starts a Mermaid entity code | escaped to `#35;` |
| `"` in a label | terminates the quoted label | escaped to `#quot;` |
| `<` or `>` | parsed as markup | escaped to `#lt;` and `#gt;` |
| `\|` in an edge label | terminates the label delimiter | escaped to `#124;` |
| newline in a label | breaks the statement | converted to `<br/>` |

Every label is emitted quoted, so a label is never parsed as syntax.

**Edges to undeclared nodes create the node** and raise a warning rather than failing or dropping the edge. Whiteboard extraction routinely finds an arrow whose endpoint text was unreadable, and losing that arrow loses real information.

**Output is deterministic.** Input order is preserved and nothing is timestamped, so regenerating a diagram from the same graph produces a byte-identical file and version-control diffs show only genuine changes.

## Shapes and grouping

`shape` maps to `rect`, `round`, `stadium`, `subroutine`, `cylinder`, `circle`, `decision`, or `hexagon`; anything unrecognized falls back to `rect`. Nodes sharing a `section` render inside a labeled `subgraph`, which maps naturally onto whiteboard regions that were drawn inside a box or separated by a divider line.

## Choosing a target format

| Format | Use when | Cost |
|---|---|---|
| Mermaid | the diagram lives in Markdown, a PR, or docs | limited layout control |
| Graphviz DOT | layout quality matters for dense graphs | not editable by hand in most tools |
| draw.io XML | a human will rearrange it afterward | verbose, needs geometry for every shape |
| Excalidraw | keeping the hand-drawn feel of the original board | needs explicit coordinates and seeds |

Mermaid is the default. For the other three, keep the same sanitizing and uncertainty rules and change only the emitter; the escaping table above is format-specific, so re-derive it rather than reusing Mermaid's entity codes.

For draw.io and Excalidraw, reuse the extracted bounding boxes as initial coordinates instead of running a fresh layout. Preserving the board's spatial arrangement is most of why someone wants those formats.

## Validation

Render the output before shipping it. `mmdc -i out.mmd -o out.svg` catches syntax errors that a visual scan misses, and pairing it with `--strict` turns unresolved warnings into a failed build. When a diagram fails to render, check identifiers and label escaping first; those account for nearly every parse failure.
