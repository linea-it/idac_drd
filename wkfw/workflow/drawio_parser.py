"""Helpers to extract labels/edges from a diagrams.net (.drawio) file."""
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET


def _clean_label(raw: str) -> str:
    text = html.unescape(raw or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_drawio(path: Path) -> dict:
    """Return {cells: {id: label}, edges: [(source, target)], swimlanes: {id: label}}."""
    tree = ET.parse(path)
    root = tree.getroot()
    cells = {}
    edges = []
    swimlanes = {}

    for cell in root.iter("mxCell"):
        cell_id = cell.attrib.get("id")
        if not cell_id:
            continue
        style = cell.attrib.get("style", "")
        value = _clean_label(cell.attrib.get("value", ""))
        if value:
            cells[cell_id] = value
            if "swimlane" in style:
                swimlanes[cell_id] = value
        if cell.attrib.get("edge") == "1":
            src = cell.attrib.get("source")
            tgt = cell.attrib.get("target")
            if src and tgt:
                edges.append((src, tgt))

    return {"cells": cells, "edges": edges, "swimlanes": swimlanes}


def merge_drawio_labels_into_fixture(drawio_path: Path, fixture_path: Path) -> dict:
    """Keep curated fixture structure; report drawio labels for operator awareness.

    Full automatic edge mapping is ambiguous (nested geometry). The curated fixture
    remains the source of truth; this updates nothing structural unless labels match.
    """
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    parsed = parse_drawio(drawio_path)
    labels = sorted({v for v in parsed["cells"].values() if v and v not in {"\u00a0"}})
    data["_drawio_labels_detected"] = labels
    data["_drawio_edge_count"] = len(parsed["edges"])
    data["_drawio_swimlanes"] = sorted(parsed["swimlanes"].values())
    return data
