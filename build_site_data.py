"""Create the compact, read-only data bundle used by the strategy reading site.

The source history remains untouched.  This script deliberately reads only the
extracted ``grid.csv`` of six-digit daily tabs, preserving every non-empty
source cell and its column heading.  It omits HTML, JSONP, protobuf audit
views, and other reproducible acquisition artifacts from the website bundle.
"""

from __future__ import annotations

import csv
import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
HISTORY_ROOT = ROOT / "data" / "qq_sheet_history"
OUTPUT_FILE = ROOT / "site" / "site-data.json"
DAILY_TAB = re.compile(r"^\d{6}$")


def display_date(tab_name: str) -> str:
    return f"20{tab_name[:2]}.{tab_name[2:4]}.{tab_name[4:]}"


def read_grid(path: Path) -> list[list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return [row for row in csv.reader(source)]


def resolve_history_dir(requested: str | None) -> Path:
    """Use an explicit batch when given, otherwise the most recently updated archive.

    ``qq_sheet_extract.py --append-latest`` updates a history batch in place.
    Selecting the newest valid batch keeps the website refresh command independent
    of the timestamp in that folder's name.
    """
    if requested:
        candidate = Path(requested).expanduser().resolve()
        if not candidate.is_dir():
            raise FileNotFoundError(f"History batch does not exist: {candidate}")
        return candidate

    batches = [
        folder for folder in HISTORY_ROOT.glob("history_*")
        if folder.is_dir() and (folder / "manifest.csv").is_file()
    ]
    if not batches:
        raise FileNotFoundError(f"No history batch with manifest.csv was found in: {HISTORY_ROOT}")
    return max(batches, key=lambda folder: (folder / "manifest.csv").stat().st_mtime)


def build_document(folder: Path) -> dict[str, object] | None:
    metadata_path = folder / "metadata.json"
    grid_path = folder / "grid.csv"
    if not metadata_path.is_file() or not grid_path.is_file():
        return None
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    tab_name = str(metadata.get("selected_tab_name") or "")
    if not DAILY_TAB.fullmatch(tab_name):
        return None

    grid = read_grid(grid_path)
    if not grid:
        return None
    # A daily sheet can intentionally contain populated columns after its last
    # named heading.  Keep that source fact instead of inventing a visible
    # "列 N" label.  The site uses the stable column ordinal plus the selected
    # day to render a readable section title, while ``sourceLabel`` remains
    # available for an audit trail.
    headers = [item.strip() for item in grid[0]]
    entries: list[dict[str, object]] = []
    for row_index, row in enumerate(grid[1:], start=2):
        padded = row + [""] * (len(headers) - len(row))
        strategy = padded[0].strip()
        if not strategy:
            continue
        cells = [
            {
                "sourceLabel": headers[column] if column < len(headers) else "",
                "column": column + 1,
                # Column A is the strategy name and column B is the manager;
                # every content column thereafter has a durable ordinal.
                "ordinal": max(column - 1, 1),
                "text": value,
            }
            for column, value in enumerate(padded[1:], start=1)
            if value.strip()
        ]
        if cells:
            entries.append({"strategy": strategy, "row": row_index, "cells": cells})

    return {
        "id": folder.name,
        "dateKey": tab_name,
        "date": display_date(tab_name),
        "capturedAt": metadata.get("captured_at"),
        "entries": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the compact strategy-reading data bundle.")
    parser.add_argument("--history-dir", help="Optional explicit qq_sheet_extract history batch directory.")
    parser.add_argument("--output-file", help="Optional output path; defaults to site/site-data.json.")
    args = parser.parse_args()
    history_dir = resolve_history_dir(args.history_dir)
    documents = [document for folder in history_dir.iterdir() if folder.is_dir() if (document := build_document(folder))]
    # A live updater can retain a newer audit snapshot for an already archived
    # day. Keep only that freshest revision in the reader bundle; older raw
    # snapshots remain on disk for provenance and are never deleted here.
    latest_documents: dict[str, dict[str, object]] = {}
    for document in documents:
        key = str(document["dateKey"])
        if key not in latest_documents or str(document.get("capturedAt") or "") > str(latest_documents[key].get("capturedAt") or ""):
            latest_documents[key] = document
    documents = list(latest_documents.values())
    documents.sort(key=lambda document: str(document["dateKey"]), reverse=True)
    strategies = Counter(entry["strategy"] for document in documents for entry in document["entries"])
    payload = {
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": "Tencent Docs public-sheet snapshots",
        "historyBatch": history_dir.name,
        "documentCount": len(documents),
        "strategyCount": len(strategies),
        "strategies": [name for name, _ in strategies.most_common()],
        "documents": documents,
    }
    output_file = Path(args.output_file).resolve() if args.output_file else OUTPUT_FILE
    output_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_file.with_suffix(f"{output_file.suffix}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporary.replace(output_file)
    print(json.dumps({"output": str(output_file), "history_batch": str(history_dir), "bytes": output_file.stat().st_size, "daily_documents": len(documents), "strategies": len(strategies)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
