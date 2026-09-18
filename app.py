"""Streamlit Cloud entry point for the read-only strategy guidance platform.

The original browser application stays unchanged under ``site/``.  Streamlit
renders a self-contained version in a component frame so the deployment needs
only the compact ``site-data.json`` bundle, never the large Tencent-document
audit archives stored on a local workstation.
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components


ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"


def read(name: str) -> str:
    return (SITE / name).read_text(encoding="utf-8")


def safely_embed_json(value: object) -> str:
    """Avoid allowing source text to terminate the script element."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def navigation_script(view: str) -> str:
    """Navigation needs to leave the Streamlit component iframe."""
    target = "archive" if view == "home" else "home"
    return f"""
    <script>
      window.__strategyNavigate = function(query) {{
        const path = '/?view=' + query;
        const anchor = document.createElement('a');
        anchor.href = path;
        anchor.target = '_top';
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
      }};
      document.addEventListener('click', function(event) {{
        const link = event.target.closest('a[data-strategy-route]');
        if (!link) return;
        event.preventDefault();
        window.__strategyNavigate(link.dataset.strategyRoute);
      }});
    </script>
    """


def route_markup(html: str, view: str) -> str:
    home = 'data-strategy-route="home" href="/?view=home" target="_top"'
    archive = 'data-strategy-route="archive" href="/?view=archive" target="_top"'
    html = html.replace('href="./index.html"', home)
    html = html.replace('href="./archive.html"', archive)
    return html


def page_document(view: str) -> str:
    page = "index.html" if view == "home" else "archive.html"
    code = "app.js" if view == "home" else "archive.js"
    html = route_markup(read(page), view)
    css = read("style.css")
    script = read(code)
    data = json.loads(read("site-data.json"))
    data_literal = safely_embed_json(data)

    # Components cannot expose sibling static files.  Supply the immutable
    # data bundle in memory and retain the exact front-end rendering logic.
    script = script.replace(
        "fetch('./site-data.json')",
        "Promise.resolve({ ok: true, json: async () => window.__STRATEGY_DATA__ })",
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
    html = html.replace(f'<script src="./{code}"></script>', f"<script>window.__STRATEGY_DATA__={data_literal};</script><script>{script}</script>{navigation_script(view)}")
    html = html.replace('<script src="./update-client.js"></script>', "")
    return html


st.set_page_config(page_title="策略指引 · 原文图谱", page_icon="◌", layout="wide", initial_sidebar_state="collapsed")
st.markdown(
    "<style>[data-testid='stHeader'], [data-testid='stToolbar'], [data-testid='stDecoration'] {display:none} .block-container {max-width:none;padding:0}</style>",
    unsafe_allow_html=True,
)

view = st.query_params.get("view", "home")
if view not in {"home", "archive"}:
    view = "home"
components.html(page_document(view), height=1280, scrolling=True)
