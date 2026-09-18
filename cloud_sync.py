"""Incrementally refresh the deployable strategy bundle in GitHub Actions.

Only ``grid.csv`` and ``metadata.json`` are retained in ``data/cloud_history``.
That is enough to compare revisions and rebuild the display bundle, while raw
Tencent Docs responses and audit payloads remain on the local workstation.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.request import HTTPCookieProcessor, build_opener

import qq_sheet_extract as extractor


ROOT = Path(__file__).resolve().parent
HISTORY = ROOT / "data" / "cloud_history"
STATE = ROOT / "data" / "cloud_sync_state.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_snapshots() -> tuple[set[str], dict[str, set[str]]]:
    dates: set[str] = set()
    known: dict[str, set[str]] = {}
    for folder in HISTORY.iterdir() if HISTORY.is_dir() else ():
        grid, metadata = folder / "grid.csv", folder / "metadata.json"
        if not folder.is_dir() or not grid.is_file() or not metadata.is_file():
            continue
        try:
            tab = str(json.loads(metadata.read_text(encoding="utf-8")).get("selected_tab_name") or "")
        except (OSError, json.JSONDecodeError):
            continue
        if tab.isdigit() and len(tab) == 6:
            dates.add(tab)
            known.setdefault(tab, set()).add(digest(grid))
    return dates, known


def persist_snapshot(source: Path, tab_name: str, tab_id: str) -> None:
    stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    target = HISTORY / f"cloud_{stamp}_{tab_name}_{tab_id}"
    target.mkdir(parents=True, exist_ok=False)
    for name in ("grid.csv", "metadata.json"):
        shutil.copy2(source / name, target / name)


def main() -> int:
    HISTORY.mkdir(parents=True, exist_ok=True)
    local_dates, known_digests = load_snapshots()
    cookies = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookies))
    _, _, _, header_payload = extractor.fetch_payload(opener, extractor.DEFAULT_URL)
    tabs = sorted(
        (tab for tab in extractor.available_tabs(header_payload) if tab["name"].isdigit() and len(tab["name"]) == 6),
        key=lambda tab: tab["name"],
    )
    if not tabs:
        raise RuntimeError("共享表中未发现六位日期命名的日表")

    latest = max(local_dates) if local_dates else tabs[0]["name"]
    candidates = [tab for tab in tabs if tab["name"] >= latest or tab["name"] not in local_dates]
    updated: list[str] = []
    with tempfile.TemporaryDirectory(prefix="strategy-cloud-sync-") as temporary:
        scratch = Path(temporary)
        for tab in candidates:
            source_url = extractor.with_tab(extractor.DEFAULT_URL, tab["id"])
            page_html, endpoint, raw_bytes, payload = extractor.fetch_payload(opener, source_url)
            candidate = scratch / f"candidate_{tab['name']}_{tab['id']}"
            extractor.write_snapshot(
                candidate,
                extractor.DEFAULT_URL,
                source_url,
                page_html,
                endpoint,
                raw_bytes,
                payload,
                sorted(cookie.name for cookie in cookies),
                persist_protobuf_audit=False,
            )
            candidate_digest = digest(candidate / "grid.csv")
            if candidate_digest not in known_digests.get(tab["name"], set()):
                persist_snapshot(candidate, tab["name"], tab["id"])
                updated.append(tab["name"])

    result = {
        "checkedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "latestLocal": latest,
        "candidateCount": len(candidates),
        "updatedTabs": updated,
    }
    STATE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if updated:
        subprocess.run(
            [sys.executable, str(ROOT / "build_site_data.py"), "--history-dir", str(HISTORY)],
            cwd=ROOT,
            check=True,
        )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
