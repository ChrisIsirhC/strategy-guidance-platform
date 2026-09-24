"""Streamlit pages for the first case-management slice."""

from __future__ import annotations

import json
from html import escape
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import streamlit as st

from case_store import CaseStore, admin_credentials
from shared_nav import nav_css, render_nav


ROOT = Path(__file__).resolve().parent
SOURCE_SHEET_URL = "https://docs.qq.com/sheet/DRk9rYVJwbmV5T2tv?tab=6l8diy"
TEST_STRATEGY = "测试策略案例"


def _strategies() -> list[str]:
    try:
        payload = json.loads((ROOT / "site" / "site-data.json").read_text(encoding="utf-8"))
        latest = max(payload.get("documents", []), key=lambda item: item.get("dateKey", ""))
        values = [entry.get("strategy", "") for entry in latest.get("entries", [])]
        return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip())) + [TEST_STRATEGY]
    except (OSError, json.JSONDecodeError):
        return []


def _css() -> None:
    styles = """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Newsreader:opsz,wght@6..72,500;6..72,650&family=Noto+Serif+SC:wght@500;600;700;900&display=swap');
        :root { --ink:#241f20; --muted:#8b8180; --red:#b3262d; --red-deep:#791d24; --red-soft:#f3dfe0; --paper:#fffdfc; --ground:#f7f1ef; --line:rgba(92,38,41,.15); --ui:"Geist","Noto Sans SC","Microsoft YaHei",sans-serif; --display:"Newsreader","Noto Serif SC",serif; }
        #MainMenu, header[data-testid="stHeader"], [data-testid="stToolbar"], footer { display:none !important; }
        .stApp { background: radial-gradient(circle at 92% 0, rgba(163,41,53,.10), transparent 32rem), var(--ground); color:var(--ink); font-family:Geist,"Noto Sans SC","Microsoft YaHei",sans-serif; }
        .stApp:before { content:""; position:fixed; inset:0; pointer-events:none; opacity:.035; background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 280 280' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence baseFrequency='.78' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E"); z-index:0; }
        .stApp .block-container { max-width:1320px !important; padding:24px 42px 84px !important; position:relative; z-index:1; }
        .stApp div[data-testid="stElementContainer"]:has(style):not(:has(.topbar)) { display:none; }
        .case-hero { position:relative; overflow:hidden; padding:43px 47px 40px; margin-bottom:32px; border:1px solid var(--line); border-radius:20px; background:linear-gradient(118deg,rgba(179,38,45,.08),transparent 55%),#fff; box-shadow:12px 12px 0 rgba(179,38,45,.07); }
        .case-hero:after { content:""; position:absolute; right:9%; bottom:-70px; width:220px; height:220px; border:1px solid rgba(179,38,45,.18); border-radius:50%; transform:rotate(-15deg); }
        .case-kicker { margin:0 0 12px; color:var(--red); font-size:11px; font-weight:700; letter-spacing:.16em; text-transform:uppercase; }
        .case-hero h1 { position:relative; z-index:1; max-width:820px; margin:0 0 12px; color:var(--red-deep); font:650 clamp(36px,5vw,68px)/1.05 var(--display); letter-spacing:-.055em; }
        .case-meta { position:relative; z-index:1; color:var(--muted); font-size:13px; }
        .case-summary { display:flex; gap:24px; margin-top:26px; color:var(--muted); font-size:12px; }
        .case-summary strong { margin-right:5px; color:var(--red-deep); font:600 28px/1 var(--display); }
        .case-card { position:relative; padding:27px 29px 29px; margin-bottom:22px; border:1px solid var(--line); border-radius:13px; background:var(--paper); box-shadow:inset 0 1px 0 rgba(255,255,255,.9), 0 18px 34px rgba(92,38,41,.045); transition:transform .7s cubic-bezier(.32,.72,0,1), box-shadow .7s cubic-bezier(.32,.72,0,1); }
        .case-card:hover { transform:translateY(-4px); box-shadow:inset 0 1px 0 rgba(255,255,255,.9), 0 22px 42px rgba(92,38,41,.09); }
        .case-card h3 { margin:12px 0 4px; color:var(--red-deep); font:650 29px/1.18 var(--display); letter-spacing:-.035em; max-width:calc(100% - 66px); }
        .case-card-icon { position:absolute; top:25px; right:27px; width:54px; height:54px; background:#e6bfc3; opacity:.85; -webkit-mask:var(--icon) center / contain no-repeat; mask:var(--icon) center / contain no-repeat; }
        .case-type { color:var(--red); font-size:11px; font-weight:700; letter-spacing:.1em; }
        .case-type span { margin-left:10px; color:var(--muted); font-weight:500; letter-spacing:.04em; }
        .case-manager { margin:11px 0 22px; color:var(--ink); font:650 23px/1.3 var(--display); }
        .case-fields { display:grid; gap:16px; }
        .case-field { padding-top:13px; border-top:1px solid rgba(92,38,41,.12); }
        .case-card .label { color:var(--red); font-size:10px; font-weight:700; letter-spacing:.14em; }
        .case-card p { margin:5px 0 0; white-space:pre-wrap; line-height:1.78; color:#433637; font-size:14px; }
        .status-pill { display:inline-block; padding:4px 9px; color:var(--red-deep); border:1px solid rgba(179,38,45,.20); border-radius:999px; background:var(--red-soft); font-size:.72rem; font-weight:700; letter-spacing:.04em; }
        .sheet-action { display:inline-flex; align-items:center; gap:8px; color:var(--red-deep); font-size:13px; font-weight:700; text-decoration:none; }
        .sheet-action:hover { color:var(--red); }
        .sheet-note { margin-top:5px; color:var(--muted); font-size:11px; }
        .st-key-case-daily-action, .st-key-case-new-action, .st-key-case-list-surface, .st-key-case-editor-surface { position:relative; padding:25px 28px 28px; border:1px solid rgba(137,49,57,.12); border-radius:16px; background:var(--paper); box-shadow:inset 0 1px 0 #fff,0 16px 40px rgba(92,38,41,.045); animation:caseReveal .68s cubic-bezier(.32,.72,0,1) both; }
        .st-key-case-daily-action:before, .st-key-case-new-action:before { content:""; position:absolute; inset:5px; border:1px solid rgba(179,38,45,.06); border-radius:11px; pointer-events:none; }
        .st-key-case-daily-action, .st-key-case-new-action { background:linear-gradient(135deg,rgba(179,38,45,.045),transparent 70%),var(--paper); }
        .st-key-case-list-surface { margin-top:28px; }
        .st-key-case-editor-surface { margin-top:28px; }
        .case-action-eyebrow { margin:0 0 7px; color:var(--red); font-size:10px; font-weight:700; letter-spacing:.16em; }
        .case-action-title { margin:0 0 5px; color:var(--red-deep); font:650 26px/1.2 var(--display); }
        .case-action-note { margin:0 0 18px; color:var(--muted); font-size:12px; line-height:1.7; }
        .case-action-link { display:inline-flex; align-items:center; gap:14px; min-height:40px; padding:8px 15px; border-radius:999px; color:#fff !important; background:var(--red); font-size:12px; font-weight:700; text-decoration:none !important; transition:transform .55s cubic-bezier(.16,1,.3,1); }
        .case-action-link:hover { transform:translateY(-2px); }
        .case-search-group { margin-top:30px; }
        [data-testid="stForm"] { padding:22px 24px 10px; border:1px solid var(--line); border-radius:16px; background:rgba(255,253,252,.78); box-shadow:inset 0 1px 0 rgba(255,255,255,.92), 0 18px 40px rgba(92,38,41,.045); }
        [data-testid="stHeading"] h2, [data-testid="stHeading"] h3 { color:var(--red-deep); font-family:var(--display); letter-spacing:-.03em; }
        [data-testid="stSelectbox"] label, [data-testid="stTextInput"] label, [data-testid="stTextArea"] label, [data-testid="stDateInput"] label { color:var(--red); font-size:11px; font-weight:700; letter-spacing:.08em; }
        .st-key-public_case_strategy { max-width:360px; margin-bottom:14px; }
        [data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea, [data-testid="stDateInput"] input, [data-testid="stSelectbox"] > div > div { border-color:var(--line) !important; border-radius:10px !important; background:rgba(255,255,255,.78) !important; color:var(--ink) !important; }
        [data-testid="stTextArea"] textarea { min-height:108px; line-height:1.65; }
        [data-testid="stButton"] button, [data-testid="stFormSubmitButton"] button { border:1px solid var(--line) !important; border-radius:999px !important; color:var(--red-deep) !important; background:rgba(255,255,255,.85) !important; font-weight:700 !important; transition:transform .55s cubic-bezier(.16,1,.3,1), background .55s cubic-bezier(.16,1,.3,1), color .55s cubic-bezier(.16,1,.3,1) !important; }
        [data-testid="stButton"] button:hover, [data-testid="stFormSubmitButton"] button:hover { color:#fff !important; background:var(--red) !important; transform:translateY(-2px); }
        [data-testid="stFormSubmitButton"] button[kind="primary"] { color:#fff !important; background:var(--red) !important; }
        [data-testid="stButton"] button[kind="primary"] { color:#fff !important; background:var(--red) !important; }
        .case-list-marker { display:none; }
        [data-testid="stHorizontalBlock"]:has(.case-list-marker) > [data-testid="stColumn"] { animation:caseReveal .58s cubic-bezier(.16,1,.3,1) both; }
        [data-testid="stHorizontalBlock"]:has(.case-list-marker) > [data-testid="stColumn"]:nth-child(2) { animation-delay:.09s; }
        @keyframes caseReveal { from { opacity:.35; transform:translateY(14px); } to { opacity:1; transform:translateY(0); } }
        @media (prefers-reduced-motion:reduce) { [data-testid="stHorizontalBlock"]:has(.case-list-marker) > [data-testid="stColumn"] { animation:none; } }
        [data-testid="stAlert"] { border-radius:9px !important; }
        @media (max-width: 760px) { .stApp .block-container { padding:0 16px 56px !important; } .case-hero { padding:30px 24px; } .case-hero h1 { font-size:43px; } .case-summary { gap:15px; } .case-card { padding:22px 20px; } [data-testid="stForm"] { padding:18px 16px 8px; } .st-key-case-daily-action,.st-key-case-new-action,.st-key-case-list-surface,.st-key-case-editor-surface { padding:20px 18px; } }
        /* Shared public/editor navigation, identical hierarchy and sizing. */
        .stApp .block-container { padding-top:0 !important; }
        div[data-testid="stElementContainer"]:has(.topbar) { position:sticky; top:0; z-index:30; width:calc(100% + 84px) !important; max-width:none !important; margin:0 0 50px -42px; }
        .st-key-case-editor-surface [data-testid="stForm"] { margin-top:20px; box-shadow:none; background:transparent; border:0; padding:0; }
        .st-key-case-daily-action,.st-key-case-new-action { min-height:218px; }
        .st-key-case-daily-action .case-action-link,.st-key-case-new-action [data-testid="stButton"] { position:absolute; left:28px; bottom:28px; width:190px; margin:0; }
        .st-key-case-daily-action .case-action-link,.st-key-case-new-action [data-testid="stButton"] button { display:flex; align-items:center; justify-content:center; width:190px !important; height:44px; min-height:44px; padding:9px 17px; border:0 !important; border-radius:999px; color:#fff !important; background:var(--red) !important; font:700 13px/1.2 var(--ui) !important; box-shadow:none !important; text-decoration:none !important; }
        .st-key-case-daily-action .case-action-link:hover,.st-key-case-new-action [data-testid="stButton"] button:hover { background:var(--red-deep) !important; transform:translateY(-2px); }
        .st-key-case-logout { display:flex; justify-content:flex-end; margin:20px 0 0; }
        .st-key-case-logout [data-testid="stButton"] button { width:auto; min-height:32px; padding:5px 12px; color:var(--muted) !important; background:transparent !important; border:0 !important; font-size:11px; font-weight:500 !important; }
        .st-key-case-logout [data-testid="stButton"] button:hover { color:var(--red-deep) !important; background:var(--red-soft) !important; }
        @media (min-width:1321px) { div[data-testid="stElementContainer"]:has(.topbar) { width:100vw !important; margin-left:calc((1320px - 100vw) / 2 - 42px); } }
        @media (max-width:760px) { div[data-testid="stElementContainer"]:has(.topbar) { width:calc(100% + 32px) !important; margin-left:-16px; margin-bottom:30px; } .st-key-case-daily-action,.st-key-case-new-action { min-height:210px; } .st-key-case-daily-action .case-action-link,.st-key-case-new-action [data-testid="stButton"] { left:18px; bottom:20px; } }
        </style>
        """
    st.markdown(styles.replace("</style>", nav_css() + "</style>"), unsafe_allow_html=True)


def _nav(active: str, pages: dict[str, Any]) -> None:
    st.html(render_nav(active, search=active != "admin"))


def _case_icon(strategy: str) -> str:
    if strategy == TEST_STRATEGY:
        return "science"
    for token, icon in (("地方债", "castle"), ("REITs", "apartment"), ("转债", "currency_exchange"), ("宏观", "public"), ("利率债", "diamond"), ("信用债", "text_increase"), ("ABS", "corporate_fare"), ("海外", "directions_boat"), ("衍生品", "graph_8"), ("黄金", "account_balance"), ("基金", "savings"), ("权益", "trending_up")):
        if token in strategy:
            return icon
    return "category"


def _case_card(case: dict[str, Any]) -> None:
    title = escape(str(case.get("title") or "未命名案例"))
    strategy = escape(str(case.get("strategy", "")))
    manager = escape(str(case.get("manager", "")))
    case_date = escape(str(case.get("case_date", "")))
    icon = _case_icon(str(case.get("strategy", "")))
    sections = "".join(
        f'<section class="case-field"><div class="label">{label}</div><p>{escape(str(case.get(key) or ""))}</p></section>'
        for label, key in (("背景", "background"), ("策略判断", "judgement"), ("执行动作", "action"), ("结果", "result"), ("复盘", "review"))
        if case.get(key)
    )
    st.markdown(
        f"""
        <article class="case-card">
          <span class="case-card-icon" style="--icon:url('https://fonts.gstatic.com/s/i/short-term/release/materialsymbolsrounded/{icon}/default/48px.svg')" aria-hidden="true"></span>
          <div class="case-type">{strategy} <span>{case_date}</span></div>
          <h3>{title}</h3>
          <div class="case-manager">{manager}</div>
          <div class="case-fields">{sections}</div>
        </article>
        """,
        unsafe_allow_html=True,
    )


def render_cases_page(pages: dict[str, Any]) -> None:
    _css()
    _nav("cases", pages)
    store = CaseStore()
    try:
        all_cases = store.list_cases(published_only=True)
    except Exception:
        st.error("策略案例暂时无法读取。请联系管理员检查数据库连接，稍后刷新重试。")
        return
    manager_count = len({item.get("manager", "").strip() for item in all_cases if item.get("manager", "").strip()})
    st.markdown(
        f'<section class="case-hero"><p class="case-kicker">策略案例库 / MANAGER NOTES</p><h1>萃取、沉淀、迭代、精进</h1><div class="case-meta">这里展示由投资经理填写并发布的实践记录。每日原始策略观点仍以共享表格为准，案例内容是独立的补充档案。</div><div class="case-summary"><span><strong>{len(all_cases)}</strong>个案例</span><span><strong>{manager_count}</strong>位撰写者</span></div></section>',
        unsafe_allow_html=True,
    )
    strategies = ["全部策略", *_strategies()]
    selected = st.selectbox("按策略筛选", strategies, key="public_case_strategy")
    filter_strategy = "" if selected == "全部策略" else selected
    cases = [item for item in all_cases if not filter_strategy or item.get("strategy") == filter_strategy]
    focused = st.session_state.pop("case_focus_id", "")
    if focused:
        cases.sort(key=lambda item: item.get("id") != focused)
    if not cases:
        st.info("暂时还没有已发布案例。经理发布后，内容会立即显示在这里。")
        return
    for offset in range(0, len(cases), 2):
        for column, case in zip(st.columns(2, gap="large"), cases[offset:offset + 2]):
            with column:
                _case_card(case)


def _login(pages: dict[str, Any]) -> bool:
    if st.session_state.get("case_admin_logged_in"):
        return True
    _css()
    _nav("admin", pages)
    st.markdown('<section class="case-hero"><p class="case-kicker">后台维护 / EDITORIAL DESK</p><h1>萃取、迭代</h1><div class="case-meta">测试阶段使用统一账户维护案例内容；每日原始策略观点不在这里修改。</div></section>', unsafe_allow_html=True)
    username, password = admin_credentials()
    if not password:
        st.error("后台密码尚未配置。请在 Streamlit Secrets 中设置 ADMIN_PASSWORD。")
        return False
    with st.form("case_admin_login"):
        entered_user = st.text_input("用户名", value="test")
        entered_password = st.text_input("密码", type="password")
        submitted = st.form_submit_button("登录后台", type="primary")
    if submitted:
        if entered_user.strip() == username and entered_password == password:
            st.session_state.case_admin_logged_in = True
            st.rerun()
        else:
            st.error("用户名或密码不正确。")
    return False


def _empty_case() -> dict[str, Any]:
    return {
        "title": "",
        "strategy": _strategies()[0] if _strategies() else "",
        "manager": "",
        "case_date": date.today().isoformat(),
        "background": "",
        "judgement": "",
        "action": "",
        "result": "",
        "review": "",
        "source_date_key": "",
        "source_cell": "",
        "status": "draft",
    }


def _can_save_cases(store: CaseStore) -> bool:
    return store.remote is not None or (store.local_fallback and not store.initialization_error)


def render_admin_page(pages: dict[str, Any]) -> None:
    if not _login(pages):
        return
    _css()
    store = CaseStore()
    can_save = _can_save_cases(store)
    _nav("admin", pages)
    try:
        all_cases = store.list_cases()
    except Exception:
        st.error("案例数据库暂时无法访问。请检查数据库配置和网络后重试。")
        return
    published_count = sum(1 for item in all_cases if item.get("status") == "published")
    draft_count = len(all_cases) - published_count
    st.markdown(f'<section class="case-hero"><p class="case-kicker">后台维护 / EDITORIAL DESK</p><h1>沉淀、精进</h1><div class="case-meta">数据后端：{escape(store.backend_name)} · 共享表格原始观点不在此处修改。</div><div class="case-summary"><span><strong>{len(all_cases)}</strong>全部案例</span><span><strong>{published_count}</strong>已发布</span><span><strong>{draft_count}</strong>草稿</span></div></section>', unsafe_allow_html=True)
    daily_column, new_column = st.columns(2, gap="medium")
    with daily_column:
        with st.container(key="case-daily-action"):
            st.markdown(f'<p class="case-action-eyebrow">DAILY GUIDANCE</p><h2 class="case-action-title">编辑每日指引</h2><p class="case-action-note">原始策略观点仍在腾讯共享表格中维护。</p><a class="case-action-link" href="{SOURCE_SHEET_URL}" target="_blank" rel="noopener noreferrer">打开共享表格 <span aria-hidden="true">↗</span></a>', unsafe_allow_html=True)
    with new_column:
        with st.container(key="case-new-action"):
            st.markdown('<p class="case-action-eyebrow">MANAGER CASES</p><h2 class="case-action-title">新增案例</h2><p class="case-action-note">先保存草稿，再由经理决定何时发布。</p>', unsafe_allow_html=True)
            if st.button("＋ 新增案例", key="case-add", type="primary"):
                st.session_state.case_editor_id = "__new__"
                st.rerun()
    if not can_save:
        st.warning("案例数据库未连接，暂不能保存草稿或发布。请检查后台数据库配置后重试。")

    strategies = _strategies()
    existing = all_cases
    editor_id = st.session_state.get("case_editor_id")
    if editor_id:
        left, right = st.columns([1.1, 2.2], gap="large")
    else:
        left, centered, right = st.columns([1, 1.75, 1])
        left = centered
    with left:
        st.markdown('<span class="case-list-marker" aria-hidden="true"></span>', unsafe_allow_html=True)
        with st.container(key="case-list-surface"):
            st.subheader("案例列表")
            for item in existing:
                label = f"{'●' if item.get('status') == 'published' else '○'} {item.get('title') or '未命名案例'}"
                if st.button(label, key=f"case-select-{item.get('id')}", use_container_width=True):
                    st.session_state.case_editor_id = item.get("id")
                    st.rerun()
            if not existing:
                st.caption("还没有案例，先新建一条。")

    if not editor_id:
        _logout()
        return
    with right:
        with st.container(key="case-editor-surface"):
            initial = _empty_case() if editor_id == "__new__" else (store.get_case(editor_id) or _empty_case())
            st.subheader("＋ 新增案例" if editor_id == "__new__" else "· 编辑案例")
            with st.form("case_editor"):
                title = st.text_input("案例标题 *", value=initial.get("title", ""))
                c1, c2 = st.columns(2)
                with c1:
                    strategy = st.selectbox("所属策略 *", strategies or ["待配置"], index=(strategies.index(initial.get("strategy")) if initial.get("strategy") in strategies else 0))
                    manager = st.text_input("投资经理 *", value=initial.get("manager", ""))
                with c2:
                    case_date = st.date_input("案例日期 *", value=_safe_date(initial.get("case_date")))
                background = st.text_area("背景", value=initial.get("background", ""), height=110)
                judgement = st.text_area("策略判断 *", value=initial.get("judgement", ""), height=130)
                action = st.text_area("执行动作", value=initial.get("action", ""), height=110)
                result = st.text_area("结果", value=initial.get("result", ""), height=110)
                review = st.text_area("复盘", value=initial.get("review", ""), height=110)
                save_draft = st.form_submit_button("保存草稿", disabled=not can_save)
                publish = st.form_submit_button("发布", type="primary", disabled=not can_save)
                status = "published" if publish else "draft"
                submitted = save_draft or publish
        if submitted:
            if not can_save:
                st.error("案例数据库尚未配置，无法保存到云端。")
                return
            if not title.strip() or not manager.strip() or not strategy.strip() or not judgement.strip():
                st.error("带 * 的项目必须填写：案例标题、所属策略、投资经理、案例日期和策略判断。")
                return
            try:
                saved = store.save_case(
                {
                    **initial,
                    "id": None if editor_id == "__new__" else editor_id,
                    "title": title,
                    "strategy": strategy,
                    "manager": manager,
                    "case_date": case_date.isoformat(),
                    "background": background,
                    "judgement": judgement,
                    "action": action,
                    "result": result,
                    "review": review,
                    "status": status,
                },
                    actor="test",
                )
            except Exception:
                st.error("保存失败，案例没有发布。请检查数据库连接后重试。")
                return
            st.session_state.case_editor_id = saved.get("id")
            st.success("案例已发布，前台现在可以看到它。" if status == "published" else "草稿已保存，尚未在前台显示。")
    _logout()


def _logout() -> None:
    with st.container(key="case-logout"):
        if st.button("退出登录", key="case-sign-out"):
            st.session_state.pop("case_admin_logged_in", None)
            st.rerun()


def _safe_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return date.today()
