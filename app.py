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
STRATEGY_COMPONENT = components.declare_component(
    "strategy_guidance_shell", path=str(ROOT / "streamlit_component")
)


def read(name: str) -> str:
    return (SITE / name).read_text(encoding="utf-8")


def read_from(folder: Path, name: str) -> str:
    return (folder / name).read_text(encoding="utf-8")


def safely_embed_json(value: object) -> str:
    """Avoid allowing source text to terminate the script element."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def local_update_status() -> dict[str, object]:
    state_path = ROOT / "data" / "update_state.json"
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"inProgress": False, "lastResult": "", "updatedAt": ""}


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


def frame_height_script() -> str:
    """Let the Streamlit component grow with the page instead of nesting scrollbars."""
    return """
    <script>
      (() => {
        let lastHeight = 0;
        // components.html uses the v1 custom-component bridge.  The host
        // ignores frame-height messages until this handshake has completed.
        const ready = () => window.parent.postMessage({isStreamlitMessage: true, type: 'streamlit:componentReady', apiVersion: 1}, '*');
        ready();
        window.setTimeout(ready, 100);
        window.setTimeout(ready, 500);
        window.setTimeout(ready, 1200);
        const send = (height) => {
          const message = {isStreamlitMessage: true, type: 'streamlit:setFrameHeight', height: Math.ceil(height)};
          // Streamlit's component host listens for this message.  Send it to
          // both the immediate host and the top window so it also works when
          // the component is nested by a local proxy.
          window.parent.postMessage(message, '*');
          if (window.top !== window.parent) window.top.postMessage(message, '*');
        };
        const resize = () => {
          const height = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
          if (height === lastHeight) return;
          lastHeight = height;
          send(height);
        };
        const observer = new MutationObserver(resize);
        observer.observe(document.documentElement, {childList: true, subtree: true, attributes: true, characterData: true});
        if (window.ResizeObserver) new ResizeObserver(resize).observe(document.documentElement);
        window.addEventListener('load', resize);
        window.addEventListener('resize', resize);
        resize();
        window.setTimeout(resize, 50);
        window.setTimeout(resize, 250);
        window.setTimeout(resize, 800);
        window.setInterval(resize, 1500);
      })();
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
    return html.replace('</body>', f'{frame_height_script()}</body>', 1)


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
    # The strategy timeline is long; keep its calendar pinned beneath the
    # navigation so users can jump between dates without returning to top.
    css += """
    body:has(#history-view:not([hidden])) .content { padding-top: 38px; }
    body:has(#history-view:not([hidden])) .context { min-height: 350px; margin-bottom: 0; align-items: flex-start; }
    body:has(#history-view:not([hidden])) .context-rule { padding-top: 12px; }
    body:has(#history-view:not([hidden])) .calendar-control.is-inline { position: fixed; top: 126px; right: max(28px, calc((100vw - 1520px) / 2 + 42px)); z-index: 47; display: block; width: 322px; padding: 14px; border: 1px solid var(--line); border-radius: 16px; background: rgba(255,253,252,.94); box-shadow: 0 18px 45px rgba(92,38,41,.13); backdrop-filter: blur(16px); }
    body:has(#history-view:not([hidden])) .calendar-control.is-inline .date-calendar { position: static; display: block; width: 100%; padding: 0; border: 0; border-radius: 0; background: transparent; box-shadow: none; }
    body .update-toast { width: 10px; height: 10px; display: block; }
    body .update-toast .update-pulse { display: block; width: 10px; height: 10px; box-shadow: none; }
    body .update-toast:hover, body .update-toast:focus-within { display: flex; }
    body .update-status-row { position: fixed; z-index: 48; top: 78px; left: 0; right: 0; height: 38px; pointer-events: none; background: rgba(255,253,252,.86); border-bottom: 1px solid rgba(92,38,41,.08); backdrop-filter: blur(14px); }
    body .update-status-row .update-toast { position: absolute; top: 10px; right: 28px; left: auto; pointer-events: auto; }
    @media (max-width: 760px) {
      body:has(#history-view:not([hidden])) .content { padding-top: 36px; }
      body:has(#history-view:not([hidden])) .context { min-height: 286px; }
      body:has(#history-view:not([hidden])) .context-rule { display: none; }
      body:has(#history-view:not([hidden])) .calendar-control.is-inline { top: 110px; left: 12px; right: 12px; width: auto; }
      body:has(.calendar-control.is-strategy-history) #history-view .timeline { padding-top: 0; }
      body .update-status-row { top: 66px; height: 36px; }
      body .update-status-row .update-toast { top: 10px; right: 14px; left: auto; }
    }
    """
    data_literal = safely_embed_json(json.loads(read("site-data.json")))
    update_status_literal = safely_embed_json(local_update_status())
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
        f"<script>window.__STRATEGY_DATA__={data_literal};window.__STRATEGY_UPDATE_STATUS__={update_status_literal};</script><script>{script}</script>",
    )
    return html.replace('</body>', f'{frame_height_script()}</body>', 1)


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
STRATEGY_COMPONENT(document=document, key=f"strategy-shell-{product}")
