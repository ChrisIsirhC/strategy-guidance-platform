"""Create the small Git-tracked history seed from local audit archives."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from build_site_data import resolve_history_dir


ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "data" / "cloud_history"


def captured_at(folder: Path) -> str:
    try:
        return str(json.loads((folder / "metadata.json").read_text(encoding="utf-8")).get("captured_at") or "")
    except (OSError, json.JSONDecodeError):
        return ""


def tab_name(folder: Path) -> str:
    try:
        return str(json.loads((folder / "metadata.json").read_text(encoding="utf-8")).get("selected_tab_name") or "")
    except (OSError, json.JSONDecodeError):
        return ""


def main() -> int:
    source = resolve_history_dir(None)
    candidates = [folder for folder in source.iterdir() if folder.is_dir() and (folder / "grid.csv").is_file() and (folder / "metadata.json").is_file()]
    newest: dict[str, Path] = {}
    for folder in candidates:
        date = tab_name(folder)
        if not (date.isdigit() and len(date) == 6):
            continue
        if date not in newest or captured_at(folder) > captured_at(newest[date]):
            newest[date] = folder
    TARGET.mkdir(parents=True, exist_ok=True)
    for date, folder in newest.items():
        destination = TARGET / f"seed_{date}"
        destination.mkdir(exist_ok=True)
        for name in ("grid.csv", "metadata.json"):
            shutil.copy2(folder / name, destination / name)
    print(json.dumps({"source": str(source), "target": str(TARGET), "dailyTabs": len(newest)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
