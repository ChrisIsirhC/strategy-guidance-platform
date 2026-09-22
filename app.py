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
    # Keep the status indicator in a narrow main-column lane.  The date picker
    # intentionally remains the compact dropdown used by the stable version.
    css += """
    .workspace { padding-top: 38px; }
    .update-status-row { position: fixed !important; z-index: 48 !important; top: 78px !important; left: max(244px, calc((100vw - 1520px) / 2 + 244px)) !important; right: 0 !important; height: 38px !important; background: transparent !important; border: 0 !important; backdrop-filter: none !important; pointer-events: none; }
    .update-status-row .update-toast { position: absolute !important; top: 11px !important; right: 28px !important; left: auto !important; display: flex !important; align-items: center; width: 10px; height: 10px; min-width: 0; padding: 0; overflow: hidden; border: 0; background: transparent; box-shadow: none; pointer-events: auto; transition: width .38s cubic-bezier(.16,1,.3,1), height .38s cubic-bezier(.16,1,.3,1), padding .38s cubic-bezier(.16,1,.3,1), background .38s cubic-bezier(.16,1,.3,1), box-shadow .38s cubic-bezier(.16,1,.3,1); }
    .update-status-row .update-toast:hover, .update-status-row .update-toast:focus-within { width: 270px; height: 32px; padding: 7px 11px; border: 1px solid var(--line); background: rgba(255,253,252,.97); box-shadow: 0 12px 30px rgba(92,38,41,.12); }
    .update-status-row .update-toast .update-pulse { display: block; flex: 0 0 10px; width: 10px; height: 10px; margin: 0; box-shadow: none; }
    .update-status-row .update-toast #update-message { display: block; min-width: 0; margin-left: 9px; opacity: 0; white-space: nowrap; transform: translateX(6px); transition: opacity .2s ease .1s, transform .3s cubic-bezier(.16,1,.3,1) .05s; }
    .update-status-row .update-toast:hover #update-message, .update-status-row .update-toast:focus-within #update-message { opacity: 1; transform: translateX(0); }
    body:has(#history-view:not([hidden])) .content { padding-top: 28px; }
    body:has(#history-view:not([hidden])) .context { min-height: 0; margin-bottom: 32px; align-items: center; }
    body:has(#history-view:not([hidden])) .context-rule { display: flex; padding-top: 0; }
    body:has(#history-view:not([hidden])) .calendar-control { position: relative; top: auto; right: auto; left: auto; width: auto; padding: 0; border: 0; border-radius: 0; background: transparent; box-shadow: none; backdrop-filter: none; }
    body:has(#history-view:not([hidden])) .calendar-control .date-calendar { position: absolute; display: block; width: 258px; padding: 14px; border: 1px solid var(--line); border-radius: 16px; background: #fff; box-shadow: 0 18px 45px rgba(92,38,41,.13); }
    @media (max-width: 760px) {
      .workspace { padding-top: 36px; }
      .update-status-row { top: 66px !important; left: 0 !important; right: 0 !important; height: 36px !important; }
      .update-status-row .update-toast { top: 11px !important; right: 14px !important; left: auto !important; }
      .update-status-row .update-toast:hover, .update-status-row .update-toast:focus-within { width: min(270px, calc(100vw - 28px)); }
      body:has(#history-view:not([hidden])) .content { padding-top: 18px; }
      body:has(#history-view:not([hidden])) .context { min-height: 0; margin-bottom: 24px; align-items: flex-start; }
      body:has(#history-view:not([hidden])) .context-rule { display: flex; }
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
