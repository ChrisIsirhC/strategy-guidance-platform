"""Streamlit Cloud entry point for the read-only strategy guidance platform.

The original browser application stays unchanged under ``site/``.  Streamlit
renders a self-contained version in a component frame so the deployment needs
only the compact ``site-data.json`` bundle, never the large Tencent-document
audit archives stored on a local workstation.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

import streamlit as st
import streamlit.components.v1 as components


ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
PROTOTYPE_MAIN = ROOT / "prototype_main"
PROTOTYPE_ARCHIVE = ROOT / "prototype_v0"


def read(name: str) -> str:
    return (SITE / name).read_text(encoding="utf-8")


def read_from(folder: Path, name: str) -> str:
    return (folder / name).read_text(encoding="utf-8")


def safely_embed_json(value: object) -> str:
    """Avoid allowing source text to terminate the script element."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def navigation_script() -> str:
    """Switch documents inside Streamlit's sandboxed component iframe.

    Streamlit deliberately prevents a component iframe from navigating the
    surrounding application.  Keeping the two static documents in this frame
    makes navigation reliable both in Streamlit Cloud and locally.
    """
    return """
    <script>
      window.__strategyNavigate = function(query) {
        const [view, ...params] = String(query || 'home').split('&');
        const nextDocument = window.__strategyPages && window.__strategyPages[view];
        if (!nextDocument) return;
        // The app scripts read this exactly like their ordinary URL query.
        window.__STRATEGY_ROUTE_QUERY__ = params.join('&');
        document.open();
        document.write(nextDocument);
        document.close();
      };
      document.addEventListener('click', function(event) {
        const link = event.target.closest('a[data-strategy-route]');
        if (!link) return;
        event.preventDefault();
        window.__strategyNavigate(link.dataset.strategyRoute);
      });
    </script>
    """


def route_markup(html: str) -> str:
    home = 'data-strategy-route="home" href="#home"'
    archive = 'data-strategy-route="archive" href="#archive"'
    html = html.replace('href="./index.html"', home)
    html = html.replace('href="./archive.html"', archive)
    return html


def prepared_page(view: str) -> str:
    """Prepare one page; the shell supplies shared data and the router."""
    page = "index.html" if view == "home" else "archive.html"
    code = "app.js" if view == "home" else "archive.js"
    html = route_markup(read(page))
    css = read("style.css")
    script = read(code)

    # Components cannot expose sibling static files.  Supply the immutable
    # data bundle in memory and retain the exact front-end rendering logic.
    script = script.replace(
        "fetch('./site-data.json')",
        "Promise.resolve({ ok: true, json: async () => window.__STRATEGY_DATA__ })",
    )
    script = script.replace(
        "new URLSearchParams(window.location.search)",
        "new URLSearchParams(window.__STRATEGY_ROUTE_QUERY__ || window.location.search)",
    )
    if view == "home":
        script = script.replace(
            "window.location.href = `./archive.html?mode=strategy&strategy=${encodeURIComponent(entry.strategy)}&date=${encodeURIComponent(currentDocument().dateKey)}`;",
            "window.__strategyNavigate(`archive&mode=strategy&strategy=${encodeURIComponent(entry.strategy)}&date=${encodeURIComponent(currentDocument().dateKey)}`);",
        )
    else:
        script = script.replace(
            "window.location.href = `./index.html?q=${encodeURIComponent(input.value.trim())}`;",
            "window.__strategyNavigate(`home&q=${encodeURIComponent(input.value.trim())}`);",
        )

    html = html.replace('<link rel="stylesheet" href="./style.css" />', f"<style>{css}</style>")
    # ``document.write`` reuses the component window.  Give each route script
    # its own lexical scope so revisiting a route cannot redeclare top-level
    # ``const`` bindings from an earlier visit.
    scoped_script = f"(() => {{\n{script}\n}})();"
    html = html.replace(f'<script src="./{code}"></script>', f"<script>{scoped_script}</script>{navigation_script()}")
    html = html.replace('<script src="./update-client.js"></script>', "")
    return html


def page_document(view: str) -> str:
    """Bootstrap both static routes inside the Streamlit component frame."""
    data_literal = safely_embed_json(json.loads(read("site-data.json")))
    pages_literal = safely_embed_json({"home": prepared_page("home"), "archive": prepared_page("archive")})
    initial = prepared_page(view)
    bootstrap = f"<script>window.__STRATEGY_DATA__={data_literal};window.__strategyPages={pages_literal};window.__STRATEGY_ROUTE_QUERY__='';</script>"
    return initial.replace("</head>", f"{bootstrap}</head>", 1)


def prototype_document(folder: Path) -> str:
    """Embed one prototype variant with the same compact data bundle."""
    html = read_from(folder, "index.html")
    script = read_from(folder, "app.js")
    css = read_from(folder, "style.css")
    data_literal = safely_embed_json(json.loads(read("site-data.json")))
    script = script.replace(
        "fetch('../site/site-data.json')",
        "Promise.resolve({ ok: true, json: async () => window.__STRATEGY_DATA__ })",
    )
    script = script.replace(
        "fetch('./site-data.json')",
        "Promise.resolve({ ok: true, json: async () => window.__STRATEGY_DATA__ })",
    )
    script = f"(() => {{\n{script}\n}})();"
    html = html.replace('<link rel="stylesheet" href="./style.css" />', f"<style>{css}</style>")
    html = html.replace(
        '<script src="./app.js"></script>',
        f"<script>window.__STRATEGY_DATA__={data_literal};</script><script>{script}</script>",
    )
    return html


def requested_product() -> str:
    """Resolve the public sub-site from the URL path.

    Streamlit keeps the same Python entry point for these paths; the browser
    URL is the stable public contract: / is the modified prototype, /prototype
    is the original prototype archive, and /new is the current site.
    """
    request_url = str(getattr(getattr(st, "context", None), "url", "") or "")
    path = urlparse(request_url).path.rstrip("/")
    if path.endswith("/prototype"):
        return "prototype"
    if path.endswith("/new"):
        return "new"
    return "main"


st.set_page_config(page_title="策略指引 · 原文图谱", page_icon="◌", layout="wide", initial_sidebar_state="collapsed")
st.markdown(
    "<style>[data-testid='stHeader'], [data-testid='stToolbar'], [data-testid='stDecoration'] {display:none} .block-container {max-width:none;padding:0}</style>",
    unsafe_allow_html=True,
)

product = requested_product()
if product == "new":
    view = st.query_params.get("view", "home")
    if view not in {"home", "archive"}:
        view = "home"
    document = page_document(view)
elif product == "prototype":
    document = prototype_document(PROTOTYPE_ARCHIVE)
else:
    document = prototype_document(PROTOTYPE_MAIN)
components.html(document, height=1280, scrolling=True)
