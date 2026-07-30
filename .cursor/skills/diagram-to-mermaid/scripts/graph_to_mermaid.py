#!/usr/bin/env python3
"""Render an extracted node/edge graph as a Mermaid flowchart.

Escapes labels, sanitizes identifiers, groups nodes into subgraphs by section,
and renders low-confidence edges as dotted links instead of dropping them.
Output is deterministic for a given input so diagrams diff cleanly.
Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# Lowercase `end` terminates a subgraph block; the others are flowchart keywords.
RESERVED_IDS = {
    "end",
    "graph",
    "flowchart",
    "subgraph",
    "class",
    "classdef",
    "click",
    "style",
    "linkstyle",
    "direction",
}

SHAPES = {
    "rect": ("[", "]"),
    "round": ("(", ")"),
    "stadium": ("([", "])"),
    "subroutine": ("[[", "]]"),
    "cylinder": ("[(", ")]"),
    "circle": ("((", "))"),
    "decision": ("{", "}"),
    "hexagon": ("{{", "}}"),
}


def escape_label(text: Any) -> str:
    """Make text safe inside a Mermaid quoted label."""
    value = "" if text is None else str(text)
    value = value.replace("#", "#35;")
    value = value.replace('"', "#quot;")
    value = value.replace("<", "#lt;").replace(">", "#gt;")
    value = value.replace("|", "#124;")
    value = re.sub(r"\r\n?|\n", "<br/>", value)
    return value or " "


def sanitize_id(raw: Any, index: int, taken: set[str]) -> str:
    candidate = re.sub(r"[^0-9A-Za-z_]", "_", str(raw or "")).strip("_")
    if not candidate or candidate[0].isdigit() or candidate.lower() in RESERVED_IDS:
        candidate = f"n{index}_{candidate}".rstrip("_")
    base = candidate
    suffix = 2
    while candidate in taken:
        candidate = f"{base}_{suffix}"
        suffix += 1
    taken.add(candidate)
    return candidate


def is_uncertain(item: dict, threshold: float) -> bool:
    if item.get("needs_review"):
        return True
    confidence = item.get("confidence")
    return confidence is not None and confidence < threshold


def render(graph: dict, direction: str, threshold: float, title: str | None) -> tuple[str, list[str]]:
    warnings: list[str] = []
    taken: set[str] = set()
    ids: dict[str, str] = {}
    nodes: list[dict] = []

    for index, node in enumerate(graph.get("nodes") or [], start=1):
        raw_id = str(node.get("id", ""))
        if raw_id in ids:
            warnings.append(f"duplicate node id {raw_id!r} ignored")
            continue
        node_id = sanitize_id(raw_id or node.get("label"), index, taken)
        ids[raw_id] = node_id
        nodes.append({**node, "_id": node_id})

    edges: list[dict] = []
    for index, edge in enumerate(graph.get("edges") or [], start=1):
        resolved = {}
        for end in ("source", "target"):
            raw = str(edge.get(end, ""))
            if raw not in ids:
                implicit = sanitize_id(raw, 1000 + index, taken)
                ids[raw] = implicit
                nodes.append({"id": raw, "label": raw, "_id": implicit, "_implicit": True})
                warnings.append(f"edge {index} references undeclared node {raw!r}; added it")
            resolved[end] = ids[raw]
        edges.append({**edge, "_source": resolved["source"], "_target": resolved["target"]})

    lines: list[str] = []
    if title:
        lines += ["---", f"title: {title}", "---"]
    lines.append(f"flowchart {direction}")

    def node_line(node: dict) -> str:
        open_token, close_token = SHAPES.get(str(node.get("shape") or "rect"), SHAPES["rect"])
        label = escape_label(node.get("label") if node.get("label") is not None else node.get("id"))
        mark = " (?)" if is_uncertain(node, threshold) else ""
        return f'    {node["_id"]}{open_token}"{label}{mark}"{close_token}'

    grouped: dict[str, list[dict]] = {}
    for node in nodes:
        grouped.setdefault(str(node.get("section") or ""), []).append(node)

    for node in grouped.pop("", []):
        lines.append(node_line(node))

    for section_index, (section, members) in enumerate(grouped.items(), start=1):
        section_id = sanitize_id(f"sg_{section}", 5000 + section_index, taken)
        lines.append(f'    subgraph {section_id}["{escape_label(section)}"]')
        for node in members:
            lines.append("        " + node_line(node).strip())
        lines.append("    end")

    uncertain: list[str] = []
    for index, edge in enumerate(edges, start=1):
        directed = edge.get("directed", True)
        shaky = is_uncertain(edge, threshold)
        connector = ("-.->" if directed else "-.-") if shaky else ("-->" if directed else "---")
        label = edge.get("label")
        if shaky:
            label = f"{label} (?)" if label else "?"
        text = f'|"{escape_label(label)}"|' if label else ""
        lines.append(f'    {edge["_source"]} {connector}{text} {edge["_target"]}')
        if shaky:
            uncertain.append(f'{edge["_source"]}->{edge["_target"]}')

    if uncertain:
        lines.append(f"    %% unverified edges: {', '.join(uncertain)}")
    if not nodes:
        lines.append('    empty["no nodes extracted"]')
        warnings.append("graph contained no nodes")

    return "\n".join(lines) + "\n", warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graph", type=Path, help="JSON file with nodes and edges")
    parser.add_argument("--direction", default="TD", choices=["TD", "TB", "BT", "LR", "RL"])
    parser.add_argument("--confidence-threshold", type=float, default=0.6)
    parser.add_argument("--title")
    parser.add_argument("--output", type=Path, help="write to a file instead of stdout")
    parser.add_argument("--strict", action="store_true", help="fail if any warning is raised")
    args = parser.parse_args(argv)

    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    if "diagram" in graph and "nodes" not in graph:
        graph = graph["diagram"]

    text, warnings = render(graph, args.direction, args.confidence_threshold, args.title)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return 1 if warnings and args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
