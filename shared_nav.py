"""Shared navigation markup and styles for every strategy page."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent


def nav_css() -> str:
    return (ROOT / "shared_nav.css").read_text(encoding="utf-8")


def render_nav(active: str, *, search: bool = True) -> str:
    links = (("today", "今日指引", "/"), ("history", "历史回溯", "/archive"),
             ("cases", "策略案例", "/cases"), ("admin", "后台维护", "/admin"))
    items = []
    for key, label, href in links:
        current = ' class="is-active" aria-current="page"' if key == active else ""
        external = (' target="_blank" rel="noopener noreferrer"'
                    if (key == "admin") != (active == "admin") else "")
        items.append(f'<a href="{href}"{current}{external}>{label}</a>')
    search_html = (
        '<form class="search" id="search-form" action="/" method="get" role="search" aria-label="搜索策略或原文">'
        '<img src="https://fonts.gstatic.com/s/i/short-term/release/materialsymbolsrounded/search/default/24px.svg" alt="" />'
        '<input id="search-input" name="q" type="search" placeholder="搜索策略或原文" aria-label="搜索策略或原文" />'
        '<button type="submit" aria-label="执行搜索"><img src="https://fonts.gstatic.com/s/i/short-term/release/materialsymbolsrounded/arrow_forward/default/24px.svg" alt="" /></button>'
        '</form>'
    ) if search else '<span class="nav-spacer" aria-hidden="true"></span>'
    brand_external = ' target="_blank" rel="noopener noreferrer"' if active == "admin" else ""
    return (f'<header class="topbar"><a class="brand" href="/" aria-label="返回今日指引"{brand_external}>'
            '<span class="brand-mark">S</span><span><strong>策略指引</strong><small>STRATEGY GUIDANCE</small></span></a>'
            f'<nav aria-label="主导航">{"".join(items)}</nav>{search_html}</header>')
