"""Local strategy-reading server with serialized, incremental Tencent Docs sync.

Run this file instead of ``python -m http.server``.  It serves the existing
read-only site and owns all acquisition work, so browsers never fetch Tencent
Docs directly and multiple visitors cannot start duplicate refreshes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
from datetime import datetime, time, timedelta
from http.cookiejar import CookieJar
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import HTTPCookieProcessor, build_opener

import qq_sheet_extract as extractor
from build_site_data import resolve_history_dir


ROOT = Path(__file__).resolve().parent
SITE_ROOT = ROOT / "site"
STATE_PATH = ROOT / "data" / "update_state.json"
LOCK_PATH = ROOT / "data" / "strategy_update.lock"


def now() -> datetime:
    return datetime.now().astimezone()


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def grid_digest(folder: Path) -> str | None:
    grid = folder / "grid.csv"
    if not grid.is_file():
        return None
    return hashlib.sha256(grid.read_bytes()).hexdigest()


class UpdateManager:
    """One update worker for both scheduled and visit-triggered refreshes."""

    def __init__(self) -> None:
        self._thread_lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._state = self._load_state()
        self._scheduler = threading.Thread(target=self._schedule_loop, name="strategy-update-scheduler", daemon=True)

    def _load_state(self) -> dict[str, Any]:
        if not STATE_PATH.is_file():
            return {"inProgress": False, "lastSlot": "", "lastResult": "", "updatedAt": "", "message": "尚未检查"}
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"inProgress": False, "lastSlot": "", "lastResult": "", "updatedAt": "", "message": "状态文件已重置"}

    def status(self) -> dict[str, Any]:
        with self._thread_lock:
            return dict(self._state)

    def _save_state(self, **changes: Any) -> None:
        with self._thread_lock:
            self._state.update(changes)
            snapshot = dict(self._state)
        atomic_json(STATE_PATH, snapshot)

    @staticmethod
    def slot(at: datetime | None = None) -> str:
        current = at or now()
        phase = "18" if current.time() >= time(18) else "08"
        return f"{current:%Y-%m-%d}@{phase}"

    def start(self) -> None:
        self.maybe_start("startup")
        self._scheduler.start()

    def _schedule_loop(self) -> None:
        while True:
            current = now()
            if current.hour in {8, 18}:
                self.maybe_start("schedule")
            # The state slot makes repeated checks inside the hour harmless.
            threading.Event().wait(30)

    def maybe_start(self, trigger: str) -> bool:
        current_slot = self.slot()
        with self._thread_lock:
            if self._state.get("inProgress"):
                return False
            same_slot = self._state.get("lastSlot") == current_slot
            # A successful/no-change run consumes its time slot.  A failure is
            # different: retry it on a later visit, but hold a short cool-down
            # so several simultaneous page loads do not hammer Tencent Docs.
            if same_slot and self._state.get("lastResult") != "failed":
                return False
            if same_slot and self._state.get("lastResult") == "failed":
                try:
                    failed_at = datetime.fromisoformat(str(self._state.get("updatedAt") or ""))
                    if now() - failed_at < timedelta(minutes=5):
                        return False
                except ValueError:
                    pass
            if self._worker and self._worker.is_alive():
                return False
            self._state.update({
                "inProgress": True,
                "lastTrigger": trigger,
                "startedAt": now().isoformat(timespec="seconds"),
                "message": "正在检查共享日表更新",
                "error": "",
            })
            atomic_json(STATE_PATH, dict(self._state))
            self._worker = threading.Thread(target=self._run, args=(current_slot,), name="strategy-update-worker", daemon=True)
            self._worker.start()
            return True

    def _acquire_file_lock(self) -> int | None:
        LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            return os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            # The lock is primarily for two server processes started by accident.
            # A crashed process can leave it behind, though, so do not let one stale
            # file permanently prevent the next scheduled or visit-triggered check.
            try:
                modified = datetime.fromtimestamp(LOCK_PATH.stat().st_mtime, tz=now().tzinfo)
                if now() - modified > timedelta(hours=2):
                    LOCK_PATH.unlink()
                    return os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileNotFoundError:
                # A concurrent worker released the file between the checks.
                try:
                    return os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                except FileExistsError:
                    pass
            return None

    def _latest_source_snapshot(self, history_dir: Path, tab_name: str) -> list[Path]:
        snapshots: list[Path] = []
        for folder in history_dir.iterdir():
            metadata = folder / "metadata.json"
            if not folder.is_dir() or not metadata.is_file():
                continue
            try:
                if json.loads(metadata.read_text(encoding="utf-8")).get("selected_tab_name") == tab_name:
                    snapshots.append(folder)
            except (OSError, json.JSONDecodeError):
                continue
        return snapshots

    def _snapshot_tab_names(self, history_dir: Path) -> set[str]:
        names: set[str] = set()
        for folder in history_dir.iterdir():
            metadata = folder / "metadata.json"
            if not folder.is_dir() or not metadata.is_file():
                continue
            try:
                tab_name = str(json.loads(metadata.read_text(encoding="utf-8")).get("selected_tab_name") or "")
                if tab_name.isdigit() and len(tab_name) == 6:
                    names.add(tab_name)
            except (OSError, json.JSONDecodeError):
                continue
        return names

    def _bundle_is_stale(self, history_dir: Path) -> bool:
        """Recover from a failed publish after raw snapshots were written."""
        bundle = SITE_ROOT / "site-data.json"
        if not bundle.is_file():
            return True
        source_files = [
            item for folder in history_dir.iterdir() if folder.is_dir()
            for item in (folder / "metadata.json", folder / "grid.csv") if item.is_file()
        ]
        return bool(source_files) and bundle.stat().st_mtime < max(item.stat().st_mtime for item in source_files)

    def _sync_tab_if_changed(
        self,
        history_dir: Path,
        opener: Any,
        cookies: CookieJar,
        tab: dict[str, str],
    ) -> bool:
        """Persist one source revision only when its displayed grid has changed."""
        source_url = extractor.with_tab(extractor.DEFAULT_URL, tab["id"])
        page_html, endpoint, raw_bytes, payload = extractor.fetch_payload(opener, source_url)
        stamp = now().strftime("%Y%m%d_%H%M%S")
        staging = history_dir / f".updating_{stamp}_{tab['id']}"
        final_snapshot = history_dir / f"update_{stamp}_{tab['name']}_{tab['id']}"
        try:
            extractor.write_snapshot(
                staging,
                extractor.DEFAULT_URL,
                source_url,
                page_html,
                endpoint,
                raw_bytes,
                payload,
                sorted(cookie.name for cookie in cookies),
                persist_protobuf_audit=False,
            )
            candidate_digest = grid_digest(staging)
            # Staging is inside the history batch. Excluding it prevents its own
            # digest from making every fetch appear unchanged.
            known = {grid_digest(folder) for folder in self._latest_source_snapshot(history_dir, tab["name"]) if folder != staging}
            if candidate_digest and candidate_digest in known:
                shutil.rmtree(staging)
                return False
            staging.replace(final_snapshot)
            return True
        except Exception:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            raise

    def _sync_once(self) -> tuple[str, str]:
        """Recheck the latest saved day, then fill every later or missing daily tab.

        A shared workbook can receive a late-added date tab.  Looking at the
        numerical maximum alone loses such an intermediate day, so the sync
        window starts at the latest local tab (inclusive) and also includes any
        remote date tab that is absent from the archive regardless of its date.
        """
        history_dir = resolve_history_dir(None)
        cookies = CookieJar()
        opener = build_opener(HTTPCookieProcessor(cookies))
        _, _, _, header_payload = extractor.fetch_payload(opener, extractor.DEFAULT_URL)
        daily_tabs = sorted(
            [tab for tab in extractor.available_tabs(header_payload) if tab["name"].isdigit() and len(tab["name"]) == 6],
            key=lambda item: item["name"],
        )
        if not daily_tabs:
            raise RuntimeError("共享表中未发现六位日期命名的日表")

        local_tabs = self._snapshot_tab_names(history_dir)
        latest_local = max(local_tabs) if local_tabs else daily_tabs[0]["name"]
        candidates = [tab for tab in daily_tabs if tab["name"] >= latest_local or tab["name"] not in local_tabs]
        updated_tabs = [tab["name"] for tab in candidates if self._sync_tab_if_changed(history_dir, opener, cookies, tab)]
        if updated_tabs or self._bundle_is_stale(history_dir):
            child_environment = os.environ.copy()
            child_environment["PYTHONUTF8"] = "1"
            subprocess.run(
                [sys.executable, str(ROOT / "build_site_data.py"), "--history-dir", str(history_dir)],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=child_environment,
            )
            label = "、".join(updated_tabs) if updated_tabs else "已归档日表"
            return "updated", f"{label} 已同步并发布"
        return "no_change", f"已复核 {latest_local} 起的 {len(candidates)} 份日表，无新增或内容变更"

    def _run(self, current_slot: str) -> None:
        descriptor = self._acquire_file_lock()
        if descriptor is None:
            self._save_state(inProgress=False, lastSlot=current_slot, lastResult="busy", updatedAt=now().isoformat(timespec="seconds"), message="已有更新任务正在执行")
            return
        try:
            os.write(descriptor, f"pid={os.getpid()} started={now().isoformat()}".encode("utf-8"))
            # Network requests to Tencent Docs can occasionally fail
            # transiently.  Retry once within the same run; only publish a
            # failed state after both attempts fail.
            last_error: Exception | None = None
            result = message = None
            for attempt in range(2):
                try:
                    self._save_state(message="正在同步最新策略日表" if attempt == 0 else "首次检查失败，正在重新检查策略日表")
                    result, message = self._sync_once()
                    break
                except Exception as error:  # stored below only if retry also fails
                    last_error = error
            if result is None or message is None:
                assert last_error is not None
                raise last_error
            checked_at = now().isoformat(timespec="seconds")
            changes = {"inProgress": False, "lastSlot": current_slot, "lastResult": result, "retryCount": attempt, "checkedAt": checked_at, "message": message}
            if result == "updated":
                changes["updatedAt"] = checked_at
            self._save_state(**changes)
        except Exception as error:
            self._save_state(inProgress=False, lastSlot=current_slot, lastResult="failed", retryCount=2, checkedAt=now().isoformat(timespec="seconds"), message="检查失败，已重试 2 次；下次检查会继续重试", error=f"{type(error).__name__}: {error}")
        finally:
            os.close(descriptor)
            try:
                LOCK_PATH.unlink()
            except FileNotFoundError:
                pass


class StrategyHandler(SimpleHTTPRequestHandler):
    manager: UpdateManager

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(SITE_ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/update-status":
            payload = json.dumps(self.manager.status(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if path in {"/", "/index.html", "/archive.html"}:
            self.manager.maybe_start("visit")
        super().do_GET()

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[{now():%H:%M:%S}] {self.address_string()} {fmt % args}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the strategy site with local scheduled updates.")
    parser.add_argument("--port", type=int, default=4174)
    args = parser.parse_args()
    manager = UpdateManager()
    StrategyHandler.manager = manager
    manager.start()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), StrategyHandler)
    print(f"Strategy platform: http://127.0.0.1:{args.port}/index.html", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
