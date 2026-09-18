"""Read-only snapshots for a publicly shared Tencent Docs sheet.

No browser automation, login, AI model, or write access to the source document is
needed.  The script obtains the public page first (to establish the anonymous
session cookies required by Tencent Docs), then requests the page-advertised
``dop-api/opendoc`` endpoint and archives its JSONP response.
"""

from __future__ import annotations

import argparse
import base64
import csv
import html
import json
import re
import sys
import zlib
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from urllib.request import HTTPCookieProcessor, Request, build_opener
from http.cookiejar import CookieJar


DEFAULT_URL = "https://docs.qq.com/sheet/DRk9rYVJwbmV5T2tv?tab=6l8diy"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) qq-sheet-snapshot/1.0"


def request(opener, url: str, referer: str | None = None) -> tuple[bytes, str]:
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/javascript,*/*"}
    if referer:
        headers["Referer"] = referer
    with opener.open(Request(url, headers=headers), timeout=30) as response:
        return response.read(), response.headers.get_content_charset() or "utf-8"


def find_opendoc_endpoint(page_html: str, page_url: str) -> str:
    match = re.search(r'<script[^>]+src=["\']([^"\']*?/dop-api/opendoc[^"\']*)["\']', page_html)
    if not match:
        raise RuntimeError("Tencent Docs page did not expose its public opendoc endpoint.")
    return urljoin(page_url, html.unescape(match.group(1)))


def as_json(jsonp: str) -> dict:
    match = re.fullmatch(r"\s*clientVarsCallback\((.*)\)\s*;?\s*", jsonp, flags=re.DOTALL)
    if not match:
        raise RuntimeError("Unexpected opendoc response; it was not clientVarsCallback(JSON).")
    payload = json.loads(match.group(1))
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected opendoc JSON payload type.")
    return payload


def walk(value: object, path: str = "$") -> Iterator[tuple[str, object]]:
    yield path, value
    if isinstance(value, dict):
        for key, item in value.items():
            yield from walk(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from walk(item, f"{path}[{index}]")


def decode_embedded_json(payload: dict) -> list[dict[str, object]]:
    """Find JSON strings embedded by different Tencent Docs response versions."""
    decoded: list[dict[str, object]] = []
    for path, value in walk(payload):
        if not isinstance(value, str):
            continue
        stripped = value.strip()
        if len(stripped) < 2 or stripped[0] not in "[{":
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        decoded.append({"path": path, "value": parsed})
    return decoded


def scalar_preview(value: object, limit: int = 180) -> str:
    if isinstance(value, str):
        return value.replace("\n", " ")[:limit]
    return json.dumps(value, ensure_ascii=False)[:limit]


def collect_text_leaves(payload: object) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path, value in walk(payload):
        if isinstance(value, str) and value.strip():
            rows.append({"path": path, "text": value})
    return rows


def selected_tab(source_url: str) -> str | None:
    return dict(parse_qsl(urlparse(source_url).query)).get("tab")


def with_tab(source_url: str, tab: str) -> str:
    parsed = urlparse(source_url)
    query = dict(parse_qsl(parsed.query))
    query["tab"] = tab
    return urlunparse(parsed._replace(query=urlencode(query)))


def available_tabs(payload: dict) -> list[dict[str, str]]:
    header = payload.get("clientVars", {}).get("collab_client_vars", {}).get("header", [])
    tabs: list[dict[str, str]] = []
    for group in header if isinstance(header, list) else []:
        for sheet in group.get("d", []) if isinstance(group, dict) else []:
            if isinstance(sheet, dict) and isinstance(sheet.get("id"), str) and isinstance(sheet.get("name"), str):
                tabs.append({"id": sheet["id"], "name": sheet["name"], "type": str(sheet.get("type", ""))})
    return tabs


def fetch_payload(opener, source_url: str) -> tuple[str, str, bytes, dict]:
    page_bytes, page_charset = request(opener, source_url)
    page_html = page_bytes.decode(page_charset, errors="replace")
    # Tencent's embedded script URL can retain the workbook's default tab even
    # when ``source_url`` addresses another worksheet.  Bind the advertised
    # endpoint back to the requested tab so a daily-tab refresh never silently
    # reads the default worksheet instead.
    endpoint = find_opendoc_endpoint(page_html, source_url)
    requested_tab = selected_tab(source_url)
    if requested_tab:
        endpoint = with_tab(endpoint, requested_tab)
    raw_bytes, response_charset = request(opener, endpoint, referer=source_url)
    raw_jsonp = raw_bytes.decode(response_charset, errors="replace")
    return page_html, endpoint, raw_bytes, as_json(raw_jsonp)


def protobuf_varint(data: bytes, position: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while position < len(data):
        byte = data[position]
        position += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, position
        shift += 7
        if shift > 63:
            raise ValueError("Protobuf varint is too large")
    raise ValueError("Unexpected end of protobuf varint")


def protobuf_message(data: bytes, depth: int = 0, max_depth: int = 14) -> list[dict[str, object]]:
    """Lossless-enough generic protobuf view for auditing undocumented payloads.

    Tencent Docs does not publish a stable public schema for these sheet blocks.
    This generic wire reader keeps every field number and primitive value, while
    recursively exposing UTF-8 text and nested messages for deterministic review.
    """
    fields: list[dict[str, object]] = []
    position = 0
    while position < len(data):
        start = position
        try:
            key, position = protobuf_varint(data, position)
            number, wire = key >> 3, key & 0x07
            item: dict[str, object] = {"field": number, "wire": wire}
            if not number:
                raise ValueError("Invalid field number 0")
            if wire == 0:
                item["value"] = protobuf_varint(data, position)[0]
                _, position = protobuf_varint(data, position)
            elif wire == 1:
                item["hex"] = data[position : position + 8].hex()
                position += 8
            elif wire == 2:
                size, position = protobuf_varint(data, position)
                blob = data[position : position + size]
                if len(blob) != size:
                    raise ValueError("Truncated length-delimited protobuf field")
                position += size
                try:
                    decoded = blob.decode("utf-8")
                except UnicodeDecodeError:
                    decoded = None
                if decoded is not None and decoded and all(char.isprintable() or char in "\n\r\t" for char in decoded):
                    item["text"] = decoded
                if depth < max_depth and blob:
                    try:
                        nested = protobuf_message(blob, depth + 1, max_depth)
                    except ValueError:
                        nested = []
                    if nested:
                        item["message"] = nested
                if "text" not in item and "message" not in item:
                    item["base64"] = base64.b64encode(blob).decode("ascii")
            elif wire == 5:
                item["hex"] = data[position : position + 4].hex()
                position += 4
            else:
                raise ValueError(f"Unsupported protobuf wire type {wire}")
            fields.append(item)
        except (ValueError, IndexError):
            if start == position:
                position += 1
            raise
    return fields


def decode_compressed_blob(value: str) -> bytes:
    return zlib.decompress(base64.b64decode(value))


def write_protobuf_audit(payload: dict, snapshot_dir: Path, persist: bool = True) -> list[dict[str, object]]:
    attributed = payload.get("clientVars", {}).get("collab_client_vars", {}).get("initialAttributedText", {})
    texts = attributed.get("text", []) if isinstance(attributed, dict) else []
    decoded: list[dict[str, object]] = []
    for text_index, text in enumerate(texts if isinstance(texts, list) else []):
        if not isinstance(text, dict):
            continue
        for key in ("workbook", "related_sheet"):
            encoded = text.get(key)
            if isinstance(encoded, str) and encoded:
                decoded.append({"path": f"text[{text_index}].{key}", "message": protobuf_message(decode_compressed_blob(encoded))})
        for block_index, block in enumerate(text.get("block_datas", []) or []):
            encoded = block.get("related_sheet") if isinstance(block, dict) else None
            if isinstance(encoded, str) and encoded:
                decoded.append(
                    {
                        "path": f"text[{text_index}].block_datas[{block_index}].related_sheet",
                        "range": {key: block.get(key) for key in ("start_row_index", "end_row_index", "start_col_index", "end_col_index")},
                        "message": protobuf_message(decode_compressed_blob(encoded)),
                    }
                )
    if persist:
        (snapshot_dir / "protobuf_audit.json").write_text(json.dumps(decoded, ensure_ascii=False, indent=2), encoding="utf-8")
    return decoded


def field(message: list[dict[str, object]], number: int) -> dict[str, object] | None:
    return next((item for item in message if item.get("field") == number), None)


def field_value(message: list[dict[str, object]], number: int, default: int = 0) -> int:
    item = field(message, number)
    return int(item["value"]) if item and "value" in item else default


def text_leaves(value: object) -> list[str]:
    if isinstance(value, dict):
        result = [value["text"]] if isinstance(value.get("text"), str) else []
        for child in value.values():
            result.extend(text_leaves(child))
        return result
    if isinstance(value, list):
        result: list[str] = []
        for child in value:
            result.extend(text_leaves(child))
        return result
    return []


def rich_text(item: dict[str, object]) -> str:
    """Render a Tencent rich-string pool item without bringing style metadata along.

    Rich strings are a sequence of field-3 runs.  A run's readable content is
    either its direct ``text`` value or the nested field-1 text below the run
    payload.  ``text_leaves(...)[-1]`` used to keep only the final run, which
    silently truncated multi-paragraph views such as 260812!E13.
    """
    parts: list[str] = []
    message = item.get("message")
    if not isinstance(message, list):
        return ""
    for run in message:
        if not isinstance(run, dict) or run.get("field") != 3:
            continue
        direct = run.get("text")
        if isinstance(direct, str):
            parts.append(direct)
            continue
        run_message = run.get("message")
        if not isinstance(run_message, list):
            continue
        # Field 1 contains the run style; field 3 carries its text payload.
        text_container = field(run_message, 3)
        text_message = text_container.get("message") if isinstance(text_container, dict) else None
        text_value = field(text_message, 1) if isinstance(text_message, list) else None
        text = text_value.get("text") if isinstance(text_value, dict) else None
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts)


def column_name(column: int) -> str:
    name = ""
    while True:
        column, remainder = divmod(column, 26)
        name = chr(65 + remainder) + name
        if column == 0:
            return name
        column -= 1


def extract_cells(protobuf_audit: list[dict[str, object]], snapshot_dir: Path) -> tuple[str | None, list[dict[str, object]]]:
    """Decode the supported Tencent Docs v3 sparse grid representation.

    In the public block, ordinary strings and rich strings are held in separate
    pools.  Sparse cell entries refer to those pools by a zero-based index.
    Style-only cells intentionally produce no data row; their full source is
    retained in ``protobuf_audit.json``.
    """
    if not protobuf_audit:
        return None, []
    workbook = next((item for item in protobuf_audit if item.get("path", "").endswith("related_sheet")), None)
    if not workbook or not isinstance(workbook.get("message"), list):
        return None, []
    root = workbook["message"]
    outer = field(root, 1)
    if not outer or not isinstance(outer.get("message"), list):
        return None, []
    sheet_container = next(
        (
            item
            for item in outer["message"]
            if item.get("field") == 5
            and isinstance(item.get("message"), list)
            and field_value(item["message"], 1, -1) == 18
        ),
        None,
    )
    if not sheet_container:
        return None, []
    grid = field(sheet_container["message"], 19)
    if not grid or not isinstance(grid.get("message"), list):
        return None, []
    shared_pool = field(grid["message"], 5)
    if not shared_pool or not isinstance(shared_pool.get("message"), list):
        return None, []

    plain_strings = [text_leaves(item)[-1] if text_leaves(item) else "" for item in shared_pool["message"] if item.get("field") == 1]
    rich_strings = [rich_text(item) for item in shared_pool["message"] if item.get("field") == 2]
    rows: list[dict[str, object]] = []
    for entry in grid["message"]:
        if entry.get("field") != 6 or not isinstance(entry.get("message"), list):
            continue
        coordinate = entry["message"]
        content = field(coordinate, 3)
        if not content or not isinstance(content.get("message"), list):
            continue
        content_message = content["message"]
        cell_type = field_value(content_message, 1)
        value = field(content_message, 2)
        # Tencent Docs omits the value field for the first entry in either
        # pooled string table; in that case the implicit index is zero.
        value_index = field_value(value.get("message", []), 1) if value and isinstance(value.get("message"), list) else 0
        rendered: str | None = None
        value_kind: str | None = None
        if cell_type == 4 and value_index is not None and value_index < len(plain_strings):
            rendered, value_kind = plain_strings[value_index], "plain_string"
        elif cell_type == 6 and value_index is not None and value_index < len(rich_strings):
            rendered, value_kind = rich_strings[value_index], "rich_string"
        if rendered is None:
            continue
        row_index = field_value(coordinate, 1)
        column_index = field_value(coordinate, 2)
        rows.append(
            {
                "address": f"{column_name(column_index)}{row_index + 1}",
                "row_index": row_index,
                "column_index": column_index,
                "cell_type": cell_type,
                "value_kind": value_kind,
                "value": rendered,
            }
        )

    rows.sort(key=lambda item: (int(item["row_index"]), int(item["column_index"])))
    with (snapshot_dir / "nonempty_cells.csv").open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=["address", "row_index", "column_index", "cell_type", "value_kind", "value"])
        writer.writeheader()
        writer.writerows(rows)
    if rows:
        maximum_row = max(int(item["row_index"]) for item in rows)
        maximum_column = max(int(item["column_index"]) for item in rows)
        values = {(int(item["row_index"]), int(item["column_index"])): str(item["value"]) for item in rows}
        with (snapshot_dir / "grid.csv").open("w", encoding="utf-8-sig", newline="") as output:
            writer = csv.writer(output)
            for row in range(maximum_row + 1):
                writer.writerow([values.get((row, column), "") for column in range(maximum_column + 1)])

    title = None
    sheet_meta = field(sheet_container["message"], 5)
    if sheet_meta:
        texts = text_leaves(sheet_meta)
        title = next((item for item in texts if item and item != "3.0.0"), None)
    return title, rows


def write_snapshot(
    snapshot_dir: Path,
    requested_url: str,
    source_url: str,
    page_html: str,
    endpoint: str,
    raw_bytes: bytes,
    payload: dict,
    cookie_names: list[str],
    persist_protobuf_audit: bool,
) -> dict[str, object]:
    """Persist one source tab with raw and structured, local-only artifacts."""
    snapshot_dir.mkdir(parents=True, exist_ok=False)
    raw_jsonp = raw_bytes.decode("utf-8", errors="replace")
    tabs = available_tabs(payload)
    embedded = decode_embedded_json(payload)
    protobuf_audit = write_protobuf_audit(payload, snapshot_dir, persist=persist_protobuf_audit)
    tab_name, cells = extract_cells(protobuf_audit, snapshot_dir)
    tab_token = selected_tab(source_url)
    tab_name = next((tab["name"] for tab in tabs if tab["id"] == tab_token), tab_name)

    (snapshot_dir / "source.html").write_text(page_html, encoding="utf-8")
    (snapshot_dir / "opendoc.jsonp").write_text(raw_jsonp, encoding="utf-8")
    (snapshot_dir / "opendoc.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (snapshot_dir / "embedded_json.json").write_text(json.dumps(embedded, ensure_ascii=False, indent=2), encoding="utf-8")
    with (snapshot_dir / "available_tabs.csv").open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=["id", "name", "type"])
        writer.writeheader()
        writer.writerows(tabs)

    text_rows = collect_text_leaves(payload)
    for embedded_item in embedded:
        text_rows.extend(
            {"path": f"{embedded_item['path']}::{path}", "text": text}
            for path, text in collect_text_leaves(embedded_item["value"])
        )
    with (snapshot_dir / "text_leaves.csv").open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=["path", "text"])
        writer.writeheader()
        writer.writerows(text_rows)

    client_vars = payload.get("clientVars", {}) if isinstance(payload.get("clientVars"), dict) else {}
    metadata: dict[str, object] = {
        "captured_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "requested_url": requested_url,
        "source_url": source_url,
        "selected_tab_token": tab_token,
        "opendoc_endpoint": endpoint,
        "http_session_cookie_names": cookie_names,
        "document_title": client_vars.get("title") or client_vars.get("padTitle") or payload.get("bodyData", {}).get("description"),
        "document_id": client_vars.get("padId"),
        "last_modify_time": client_vars.get("lastModifyTime"),
        "can_read": client_vars.get("privilegeAttribute", {}).get("can_read"),
        "can_export": client_vars.get("privilegeAttribute", {}).get("can_export"),
        "can_copy": client_vars.get("privilegeAttribute", {}).get("can_copy_doc"),
        "raw_response_bytes": len(raw_bytes),
        "embedded_json_count": len(embedded),
        "protobuf_blob_count": len(protobuf_audit),
        "protobuf_audit_saved": persist_protobuf_audit,
        "selected_tab_name": tab_name,
        "available_tab_count": len(tabs),
        "extracted_nonempty_cell_count": len(cells),
        "text_leaf_count": len(text_rows),
        "top_level_keys": list(payload),
        "client_vars_keys": list(client_vars),
    }
    (snapshot_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def safe_component(value: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .") or "unnamed"


def ordered_tabs(tabs: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(tabs, key=lambda tab: (not bool(re.fullmatch(r"\d{6}", tab["name"])), tab["name"], tab["id"]))


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive a publicly readable Tencent Docs sheet response.")
    parser.add_argument("url", nargs="?", default=DEFAULT_URL, help="Tencent Docs sheet URL")
    parser.add_argument("--output-dir", default="data/qq_sheet_snapshots", help="Local snapshot directory")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--latest-daily-tab", action="store_true", help="Select the greatest six-digit daily tab name.")
    selection.add_argument("--all-tabs", action="store_true", help="Archive every currently listed worksheet into one dated batch.")
    selection.add_argument("--resume-batch", help="Continue a prior --all-tabs batch directory, skipping successful tabs.")
    selection.add_argument("--append-latest", help="Append only a new latest daily tab to an existing history batch.")
    parser.add_argument("--include-protobuf-audit", action="store_true", help="Also save verbose decoded Protobuf audit JSON for every selected tab.")
    args = parser.parse_args()

    requested_url = args.url
    output_root = Path(args.output_dir)
    timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    cookies = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookies))
    initial_html, initial_endpoint, initial_raw, initial_payload = fetch_payload(opener, requested_url)
    tabs = available_tabs(initial_payload)
    cookie_names = lambda: sorted(cookie.name for cookie in cookies)

    if args.append_latest:
        batch_dir = Path(args.append_latest)
        manifest_path = batch_dir / "manifest.csv"
        if not batch_dir.is_dir() or not manifest_path.is_file():
            raise RuntimeError("--append-latest must point to an existing history batch with manifest.csv.")
        daily_tabs = [tab for tab in tabs if re.fullmatch(r"\d{6}", tab["name"])]
        if not daily_tabs:
            raise RuntimeError("No six-digit daily tab was found in the public workbook header.")
        newest_tab = max(daily_tabs, key=lambda tab: tab["name"])
        with manifest_path.open(encoding="utf-8-sig", newline="") as source:
            manifest = list(csv.DictReader(source))
        previous = next((item for item in manifest if item["tab_id"] == newest_tab["id"] and item["status"] == "success"), None)
        if previous:
            print(json.dumps({"batch_dir": str(batch_dir), "updated": False, "latest_tab_name": newest_tab["name"], "reason": "latest tab is already archived"}, ensure_ascii=False, indent=2))
            return 0
        source_url = with_tab(requested_url, newest_tab["id"])
        page_html, endpoint, raw_bytes, payload = fetch_payload(opener, source_url)
        order = max((int(item["order"]) for item in manifest), default=0) + 1
        tab_dir = batch_dir / f"{order:03d}_{safe_component(newest_tab['name'])}_{newest_tab['id']}"
        metadata = write_snapshot(tab_dir, requested_url, source_url, page_html, endpoint, raw_bytes, payload, cookie_names(), args.include_protobuf_audit)
        record = {"order": order, "tab_id": newest_tab["id"], "tab_name": newest_tab["name"], "status": "success", "snapshot_dir": tab_dir.name, "cell_count": metadata["extracted_nonempty_cell_count"], "error": ""}
        manifest.append(record)
        with manifest_path.open("w", encoding="utf-8-sig", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=["order", "tab_id", "tab_name", "status", "snapshot_dir", "cell_count", "error"])
            writer.writeheader()
            writer.writerows(sorted(manifest, key=lambda item: int(item["order"])))
        print(json.dumps({"batch_dir": str(batch_dir), "updated": True, "latest_tab_name": newest_tab["name"], "snapshot_dir": str(tab_dir), "cell_count": metadata["extracted_nonempty_cell_count"]}, ensure_ascii=False, indent=2))
        return 0

    if args.all_tabs or args.resume_batch:
        batch_dir = Path(args.resume_batch) if args.resume_batch else output_root / f"history_{timestamp}"
        manifest_path = batch_dir / "manifest.csv"
        if args.resume_batch:
            if not batch_dir.is_dir() or not manifest_path.is_file():
                raise RuntimeError("--resume-batch must point to an existing batch directory with manifest.csv.")
            with manifest_path.open(encoding="utf-8-sig", newline="") as source:
                manifest = list(csv.DictReader(source))
        else:
            batch_dir.mkdir(parents=True, exist_ok=False)
            manifest = []
        selected_tabs = ordered_tabs(tabs)
        existing = {str(item["tab_id"]): item for item in manifest}
        for index, tab in enumerate(selected_tabs, start=1):
            previous = existing.get(tab["id"])
            if previous and previous.get("status") == "success":
                continue
            source_url = with_tab(requested_url, tab["id"])
            tab_dir = batch_dir / f"{index:03d}_{safe_component(tab['name'])}_{tab['id']}"
            print(f"[{index}/{len(selected_tabs)}] {tab['name']} ({tab['id']})", flush=True)
            try:
                page_html, endpoint, raw_bytes, payload = fetch_payload(opener, source_url)
                metadata = write_snapshot(
                    tab_dir, requested_url, source_url, page_html, endpoint, raw_bytes, payload, cookie_names(), args.include_protobuf_audit
                )
                record = {"order": index, "tab_id": tab["id"], "tab_name": tab["name"], "status": "success", "snapshot_dir": tab_dir.name, "cell_count": metadata["extracted_nonempty_cell_count"], "error": ""}
            except Exception as error:  # Continue recording the remaining source tabs.
                record = {"order": index, "tab_id": tab["id"], "tab_name": tab["name"], "status": "failed", "snapshot_dir": "", "cell_count": "", "error": f"{type(error).__name__}: {error}"}
            if previous:
                manifest[manifest.index(previous)] = record
            else:
                manifest.append(record)
            existing[tab["id"]] = record
            with manifest_path.open("w", encoding="utf-8-sig", newline="") as output:
                writer = csv.DictWriter(output, fieldnames=["order", "tab_id", "tab_name", "status", "snapshot_dir", "cell_count", "error"])
                writer.writeheader()
                writer.writerows(sorted(manifest, key=lambda item: int(item["order"])))
        successful = sum(item["status"] == "success" for item in manifest)
        summary = {"batch_dir": str(batch_dir), "requested_url": requested_url, "tab_count": len(selected_tabs), "success_count": successful, "failure_count": len(selected_tabs) - successful, "protobuf_audit_saved": args.include_protobuf_audit}
        (batch_dir / "batch_metadata.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if successful == len(selected_tabs) else 1

    source_url = requested_url
    page_html, endpoint, raw_bytes, payload = initial_html, initial_endpoint, initial_raw, initial_payload
    if args.latest_daily_tab:
        daily_tabs = [tab for tab in tabs if re.fullmatch(r"\d{6}", tab["name"])]
        if not daily_tabs:
            raise RuntimeError("No six-digit daily tab was found in the public workbook header.")
        newest_tab = max(daily_tabs, key=lambda tab: tab["name"])
        if newest_tab["id"] != selected_tab(source_url):
            source_url = with_tab(source_url, newest_tab["id"])
            page_html, endpoint, raw_bytes, payload = fetch_payload(opener, source_url)
    snapshot_dir = output_root / timestamp
    metadata = write_snapshot(snapshot_dir, requested_url, source_url, page_html, endpoint, raw_bytes, payload, cookie_names(), True)
    print(json.dumps({"snapshot_dir": str(snapshot_dir), **metadata}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
