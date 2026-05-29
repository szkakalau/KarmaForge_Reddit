"""KarmaForge Web App — Gradio Blocks assembly with tabbed layout."""

import html as _html
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import gradio as gr

from .theme import create_theme
from .tabs import settings as settings_tab

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DEFAULT_DB = str(PROJECT_ROOT / "data" / "processed" / "karmaforge.db")
DEFAULT_PATTERNS = str(PROJECT_ROOT / "data" / "patterns" / "patterns.json")
DEFAULT_ANTI_PATTERNS = str(PROJECT_ROOT / "data" / "patterns" / "anti_patterns.json")
DEFAULT_FEEDBACK = str(PROJECT_ROOT / "data" / "tracking" / "feedback.jsonl")
DEFAULT_GENERATIONS = str(PROJECT_ROOT / "data" / "generations")
DEFAULT_EVOLUTION_LOG = str(PROJECT_ROOT / "data" / "tracking" / "evolution_log.md")


# Inline JS snippets — Gradio does not execute <script> tags in gr.HTML,
# so all behaviour is embedded in onclick attributes.
_COPY_JS = (
    "(function(b){var t=b.getAttribute('data-text');"
    "navigator.clipboard.writeText(t).then(function(){"
    "b.classList.add('kf-copied');"
    "setTimeout(function(){b.classList.remove('kf-copied')},1500)"
    "})})(this)"
)

_SELECT_JS = (
    "(function(c){"
    "var all=document.querySelectorAll('.kf-title-card');"
    "for(var i=0;i<all.length;i++)all[i].classList.remove('kf-selected');"
    "c.classList.add('kf-selected');"
    "var t=c.getAttribute('data-title');"
    "var inp=document.querySelector('#kf-title-trigger textarea')"
    "||document.querySelector('#kf-title-trigger input');"
    "if(inp){"
    "inp.value=t;"
    "inp.dispatchEvent(new Event('input',{bubbles:true}));"
    "}"
    "})(this)"
)


def _render_assets_html() -> str:
    """Return an empty string — all kf-* CSS is now in app.css for correct specificity."""
    return ""


def _render_titles_html(titles_data: list[dict], selected_title: str | None = None) -> str:
    """Render candidate titles as selectable cards with floating copy badges."""
    if not titles_data:
        return ""
    cards = []
    for t in titles_data:
        sel = ' kf-selected' if t['title'] == selected_title else ''
        safe = _html.escape(t['title'], quote=True)
        display = _html.escape(t['title'])
        cards.append(
            f'<div class="kf-card kf-title-card{sel}" data-title="{safe}" onclick="{_SELECT_JS}">'
            f'<button class="kf-copy-badge" onclick="event.stopPropagation();{_COPY_JS}" data-text="{safe}" title="复制">'
            f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            f'<rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>'
            f'</button>'
            f'<span class="kf-score">[{t["score"]:.0f}]</span>'
            f'<span class="kf-hook">({_html.escape(t["hook_type"])})</span>'
            f'<span class="kf-title-text">{display}</span>'
            f'</div>'
        )
    return '\n'.join(cards)


def _render_body_html(body_text: str) -> str:
    """Render generated body in a card with floating copy badge."""
    if not body_text:
        return ""
    safe = _html.escape(body_text, quote=True)
    display = _html.escape(body_text)
    return (
        f'<div class="kf-card kf-body-card">'
        f'<button class="kf-copy-badge" onclick="{_COPY_JS}" data-text="{safe}" title="复制">'
        f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f'<rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>'
        f'</button>'
        f'<div class="kf-body-label">正文预览</div>'
        f'<div class="kf-body-content">{display}</div>'
        f'</div>'
    )


def _load_dotenv() -> None:
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip()
                if key not in os.environ or not os.environ[key]:
                    os.environ[key] = value.strip('"').strip("'")
        # Mirror LLM_API_KEY → OPENAI_API_KEY for OpenAI SDK compatibility
        if os.environ.get("LLM_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = os.environ["LLM_API_KEY"]


def _init_llm() -> tuple:
    """Initialize LLM client from env vars. Returns (client, available)."""
    from ..llm import LLMClient, LLMConfig, LLMProvider

    api_key = os.environ.get("LLM_API_KEY", "")
    if not api_key:
        return None, False

    model = os.environ.get("LLM_MODEL", "deepseek-chat")
    return LLMClient(LLMConfig(
        provider=LLMProvider("deepseek"),
        api_key=api_key,
        model=model,
        api_base_url="https://api.deepseek.com/v1",
        max_tokens=4096,
        temperature=0.7,
        request_timeout=60,
    )), True


def _load_subreddit_list() -> list[str]:
    """Get sorted list of subreddits from the database."""
    import sqlite3
    try:
        conn = sqlite3.connect(DEFAULT_DB)
        rows = conn.execute(
            "SELECT DISTINCT subreddit FROM posts ORDER BY subreddit"
        ).fetchall()
        conn.close()
        return [r[0] for r in rows]
    except Exception:
        return []


def _list_generation_files() -> list[dict]:
    """Load all generation JSON files from output directory."""
    gen_dir = Path(DEFAULT_GENERATIONS)
    if not gen_dir.exists():
        return []
    results = []
    for f in sorted(gen_dir.glob("gen_*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            results.append(data)
        except Exception:
            continue
    return results


def _load_feedback_entries() -> list[dict]:
    """Load all feedback entries from JSONL."""
    fb_path = Path(DEFAULT_FEEDBACK)
    if not fb_path.exists():
        return []
    entries = []
    with open(fb_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def create_app() -> gr.Blocks:
    """Create the KarmaForge Gradio application."""
    _load_dotenv()
    llm, llm_available = _init_llm()

    shared: dict = {
        "llm": llm,
        "llm_available": llm_available,
        "headless": os.environ.get("PLAYWRIGHT_HEADLESS", "1") == "1",
        "api_key": os.environ.get("LLM_API_KEY", ""),
        "model": os.environ.get("LLM_MODEL", "deepseek-v4-pro"),
        "db_path": DEFAULT_DB,
        "patterns_path": DEFAULT_PATTERNS,
        "anti_patterns_path": DEFAULT_ANTI_PATTERNS,
        "feedback_path": DEFAULT_FEEDBACK,
        "generations_dir": DEFAULT_GENERATIONS,
        "evolution_log_path": DEFAULT_EVOLUTION_LOG,
    }

    css = """
    /* ═══════════════════════════════════════════════
       Brutalist Data Lab — KarmaForge (warm paper)
       ═══════════════════════════════════════════════ */

    /* ── Dot-grid background texture ────────── */
    .gradio-container {
        background-image: radial-gradient(circle, rgba(217,119,6,.08) 1px, transparent 1px) !important;
        background-size: 20px 20px !important;
    }

    /* ── Global: zero-radius regime ─────────── */
    *, *::before, *::after { border-radius: 0 !important; }

    /* ── Tabs: underline monospace ──────────── */
    .tabs > .tab-nav > button {
        font-family: 'Space Mono', monospace !important;
        text-transform: uppercase !important;
        letter-spacing: .04em !important;
        font-size: .82rem !important;
        color: #8b7355 !important;
        background: transparent !important;
        border: none !important;
        border-bottom: 2px solid transparent !important;
        padding: .5rem 1rem !important;
        transition: color .15s, border-color .15s !important;
    }
    .tabs > .tab-nav > button:hover { color: #d97706 !important; }
    .tabs > .tab-nav > button.selected {
        color: #d97706 !important;
        border-bottom-color: #d97706 !important;
        background: transparent !important;
    }

    /* ── Inputs: sharp, warm, amber focus ──── */
    textarea, input[type="text"], input[type="number"], select {
        background: #fdfaf6 !important;
        border: 1px solid #e0d5c5 !important;
        color: #3d3025 !important;
        font-family: 'Space Mono', monospace !important;
        font-size: .85rem !important;
        padding: .6rem .75rem !important;
        transition: border-color .15s !important;
    }
    textarea:focus, input:focus, select:focus {
        border-color: #d97706 !important;
        box-shadow: none !important;
        outline: none !important;
    }
    textarea::placeholder, input::placeholder {
        color: #b8a58a !important;
    }

    /* ── Labels: monospace uppercase ────────── */
    label, .label-text, .block label {
        font-family: 'Space Mono', monospace !important;
        text-transform: uppercase !important;
        letter-spacing: .05em !important;
        font-size: .75rem !important;
        color: #8b7355 !important;
    }

    /* ── Buttons: sharp amber ──────────────── */
    button {
        font-family: 'Space Mono', monospace !important;
        text-transform: uppercase !important;
        letter-spacing: .04em !important;
        font-size: .82rem !important;
        transition: background .12s, color .12s, border-color .12s !important;
    }
    button.primary {
        background: #d97706 !important;
        color: #faf7f2 !important;
        border: none !important;
        font-weight: 700 !important;
    }
    button.primary:hover { background: #b85c05 !important; }
    button.secondary {
        background: #faf7f2 !important;
        color: #d97706 !important;
        border: 1px solid #d97706 !important;
    }
    button.secondary:hover {
        background: #fef3e0 !important;
    }

    /* ── Cards: sharp + left amber accent ───── */
    .kf-card {
        position: relative;
        background: #f5f0e8;
        border: 1px solid #e0d5c5;
        border-left: 2px solid #e0d5c5;
        padding: 1rem 1.25rem;
        margin-bottom: .5rem;
        transition: border-color .12s;
    }
    .kf-title-card { cursor: pointer; }
    .kf-title-card:hover {
        border-color: #d5c8b5;
        border-left-color: #d97706;
    }
    .kf-title-card.kf-selected {
        border-color: #e8d5b0;
        border-left-color: #d97706;
        background: #fef3e0;
    }
    .kf-body-card { margin-top: 1rem; }

    /* ── Copy badge: sharp amber ───────────── */
    button.kf-copy-badge {
        position: absolute;
        top: 6px; right: 6px;
        width: 26px; height: 26px;
        min-width: 0; padding: 0;
        border: 1px solid transparent;
        background: transparent;
        cursor: pointer;
        color: #8b7355;
        transition: color .12s, border-color .12s, background .12s;
        z-index: 10;
    }
    button.kf-copy-badge:hover {
        color: #d97706;
        border-color: #e8d5b0;
        background: #fef3e0;
    }
    button.kf-copy-badge:active { color: #b85c05; }
    button.kf-copy-badge.kf-copied {
        background: rgba(217,119,6,.12);
        border-color: #d97706;
        color: #d97706;
    }
    button.kf-copy-badge svg { width: 14px; height: 14px; }

    /* ── Title display ─────────────────────── */
    .kf-score { font-weight: 700; color: #d97706; margin-right: .25em; font-family: 'Space Mono', monospace; }
    .kf-hook { color: #8b7355; font-size: .82em; margin-right: .5em; font-family: 'Space Mono', monospace; }
    .kf-title-text { color: #3d3025; }
    .kf-body-content { color: #3d3025; line-height: 1.7; white-space: pre-wrap; font-family: 'Source Serif 4', 'Georgia', serif; }
    .kf-body-label {
        font-size: .75em; color: #8b7355; margin-bottom: .5rem;
        text-transform: uppercase; letter-spacing: .06em;
        font-family: 'Space Mono', monospace;
    }

    /* ── Status indicator ──────────────────── */
    .kf-status {
        padding: .4rem .75rem;
        margin-bottom: .75rem;
        font-size: .84rem;
        font-family: 'Space Mono', monospace;
        border-left: 3px solid #d97706;
        background: #f5f0e8;
        color: #d97706;
    }
    .kf-status p { margin: 0; font-family: inherit; }

    /* ── Matched subreddits ────────────────── */
    .kf-matched { color: #8b7355; font-family: 'Space Mono', monospace; font-size: .78rem; }

    /* ── Performance badges ────────────────── */
    .perf-badge {
        display: inline-block;
        padding: 2px 10px;
        font-size: .82rem;
        font-weight: 700;
        font-family: 'Space Mono', monospace;
        text-transform: uppercase;
        letter-spacing: .04em;
    }
    .perf-super_viral { background: rgba(217,119,6,.14); color: #b85c05; border: 1px solid #d97706; }
    .perf-viral { background: rgba(217,119,6,.08); color: #d97706; border: 1px solid rgba(217,119,6,.4); }
    .perf-passing { background: rgba(139,115,85,.08); color: #6b5840; border: 1px solid rgba(139,115,85,.3); }
    .perf-failed { background: rgba(190,60,40,.08); color: #b84030; border: 1px solid rgba(190,60,40,.4); }

    /* ── Pattern cards ─────────────────────── */
    .pattern-card {
        background: #f5f0e8;
        border: 1px solid #e0d5c5;
        border-left: 2px solid #d97706;
        padding: 1rem;
    }

    /* ── Accordions ────────────────────────── */
    .accordion > .label-wrap {
        font-family: 'Space Mono', monospace !important;
        background: #f5f0e8 !important;
        border: 1px solid #e0d5c5 !important;
        color: #3d3025 !important;
    }
    .accordion > .label-wrap:hover { border-color: #d5c8b5 !important; }
    .accordion > .label-wrap.open { border-bottom-color: #d97706 !important; }

    /* ── Progress bar ──────────────────────── */
    .progress-bar, .progress {
        background: #ede5d8 !important;
    }
    .progress-bar-fill, .progress-fill {
        background: #d97706 !important;
    }

    /* ── Slider ────────────────────────────── */
    input[type="range"] {
        accent-color: #d97706;
    }

    /* ── Dropdown ──────────────────────────── */
    .options-menu, .dropdown-options {
        background: #fdfaf6 !important;
        border: 1px solid #e0d5c5 !important;
    }
    .option:hover, .dropdown-option:hover {
        background: #fef3e0 !important;
    }

    /* ── Scrollbar ─────────────────────────── */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: #f5f0e8; }
    ::-webkit-scrollbar-thumb { background: #d5c8b5; }
    ::-webkit-scrollbar-thumb:hover { background: #b8a58a; }

    /* ── Headings ──────────────────────────── */
    h1, h2, h3 {
        font-family: 'Space Mono', monospace !important;
        text-transform: uppercase;
        letter-spacing: .03em;
        color: #3d3025;
    }
    h1 { font-size: 1.5rem; font-weight: 700; }
    h2 { font-size: 1.15rem; font-weight: 600; color: #b85c05; }
    h3 { font-size: .95rem; font-weight: 600; }

    /* ── Markdown text ─────────────────────── */
    .prose, .md, .markdown { color: #3d3025; }
    .prose strong, .md strong { color: #b85c05; font-family: 'Space Mono', monospace; font-weight: 600; }

    /* ── Footer hide ───────────────────────── */
    footer { visibility: hidden; }

    /* ── Hidden trigger (in DOM, not rendered) ─ */
    #kf-title-trigger {
        display: none !important;
    }
    """

    with gr.Blocks(title="KarmaForge Desktop") as app:
        gr.Markdown("# KarmaForge Desktop")
        gr.Markdown("Reddit 爆款引擎 — 从研究到行动闭环")

        with gr.Tabs() as tabs:
            with gr.TabItem("生成", id="generate"):
                _build_generate_tab(shared)
            with gr.TabItem("追踪", id="track"):
                _build_track_tab(shared)
            with gr.TabItem("历史", id="history"):
                _build_history_tab(shared)
            with gr.TabItem("模式库", id="patterns"):
                _build_patterns_tab(shared)
            with gr.TabItem("进化", id="evolve"):
                _build_evolve_tab(shared)
            with gr.TabItem("设置", id="settings"):
                settings_tab.build(shared)

    app.theme = create_theme()
    app.css = css
    return app


# ── Tab Builders ──────────────────────────────────────────────────


def _build_generate_tab(shared: dict) -> None:
    """Build the Generate tab — topic → titles → body → self-check."""
    subreddits = _load_subreddit_list()
    choices = ["Auto-detect"] + subreddits

    with gr.Row():
        with gr.Column(scale=2):
            topic = gr.Textbox(
                label="帖子主题",
                placeholder="描述你想发的内容，例如：I built a Python automation script that saves 3 hours daily",
                lines=3,
            )
            with gr.Row():
                subreddit_dd = gr.Dropdown(
                    label="目标 Subreddit",
                    choices=choices,
                    value="Auto-detect",
                    scale=2,
                )
                n_titles_slider = gr.Slider(
                    1, 5, value=3, step=1, label="候选标题数",
                    scale=1,
                )
            with gr.Row():
                generate_btn = gr.Button("生成标题", variant="primary")
                full_btn = gr.Button("生成完整帖子", variant="secondary")

    assets_html = gr.HTML(value=_render_assets_html())

    with gr.Column(visible=False) as results_col:
        status_md = gr.Markdown(elem_classes=["kf-status"])
        matched_md = gr.Markdown()
        titles_html = gr.HTML()
        body_html = gr.HTML()
        self_check_json = gr.JSON(label="自检报告")
        metadata_json = gr.JSON(label="元数据建议")

    generation_state = gr.State(None)
    selected_title_trigger = gr.Textbox(visible=True, show_label=False, elem_id="kf-title-trigger", elem_classes=["kf-trigger-input"])

    def on_generate_titles(topic_val: str, sub_val: str, n_val: int):
        try:
            if not topic_val.strip():
                yield (gr.update(visible=False), None, "请输入帖子主题",
                       "", "", "", None, None, "")
                return

            yield (gr.update(visible=True), None,
                   "> 分析主题 + 生成标题中...",
                   "", "", "", None, None, "")

            from ..generator.orchestrator import GeneratorOrchestrator

            target = None if sub_val == "Auto-detect" else sub_val
            orch = GeneratorOrchestrator(
                db_path=shared["db_path"],
                patterns_path=shared["patterns_path"],
                anti_patterns_path=shared["anti_patterns_path"],
                llm_client=shared.get("llm"),
            )

            result = orch.generate_titles(topic_val, target, n_val)

            if not result.candidate_titles:
                matched_str = ", ".join(f"r/{s}" for s, _ in result.matched_subreddits)
                yield (gr.update(visible=True), None,
                       f"[失败] 未找到匹配模式。\n\n匹配到的 Subreddit: {matched_str}",
                       f"**匹配:** {matched_str}", "", "", None, None, "")
                return

            subs_text = " | ".join(f"r/{s} ({sc:.0%})" for s, sc in result.matched_subreddits)
            titles_data = [
                {"title": t.title, "score": t.score, "hook_type": t.hook_type, "pattern_id": t.pattern_id}
                for t in result.candidate_titles
            ]
            primary_sub = result.matched_subreddits[0][0]
            tier = orch._get_tier(primary_sub)
            patterns_map = {p.get("pattern_id"): p for p in result.selected_patterns}

            yield (gr.update(visible=True),
                   {"titles": titles_data, "topic": topic_val, "subreddit": primary_sub,
                    "tier": tier, "patterns": patterns_map},
                   f"[完成] {len(titles_data)} 个标题已生成 — {subs_text}\n\n点击标题选中，然后点击 **生成完整帖子** 生成正文。",
                   f"**Matched Subreddits:** {subs_text}",
                   _render_titles_html(titles_data),
                   "",
                   None,
                   result.metadata if result.metadata else None,
                   "")
        except Exception as e:
            logger.exception("Generate titles failed in Gradio handler")
            yield (gr.update(visible=False), None,
                   f"[500] {type(e).__name__}: {e}",
                   "", "", "", None, None, "")

    generate_btn.click(
        fn=on_generate_titles,
        inputs=[topic, subreddit_dd, n_titles_slider],
        outputs=[results_col, generation_state, status_md, matched_md, titles_html, body_html,
                 self_check_json, metadata_json, selected_title_trigger],
    )

    def on_generate_full(topic_val: str, sub_val: str, n_val: int, gen_state: dict,
                         trigger_val: str):
        try:
            if not topic_val.strip():
                yield (gr.update(visible=False), None, "请输入帖子主题",
                       "", "", "", None, None, "")
                return

            # ── Path A: reuse titles from gen_state (user clicked "生成标题" first) ──
            if gen_state and gen_state.get("titles"):
                titles = gen_state["titles"]
                # Resolve selected title: use trigger_val (from JS card click), else first
                selected = titles[0]
                if trigger_val:
                    for t in titles:
                        if t["title"] == trigger_val:
                            selected = t
                            break
                selected_title_text = selected["title"]
                topic_val = gen_state.get("topic", topic_val)
                subreddit = gen_state.get("subreddit", "unknown")
                tier = gen_state.get("tier", "t2")
                patterns_map = gen_state.get("patterns", {})
                pattern = patterns_map.get(
                    selected["pattern_id"],
                    {"pattern_id": selected["pattern_id"], "hook_type": selected["hook_type"]},
                )
                subs_text = f"r/{subreddit}"

                yield (gr.update(visible=True),
                       gen_state,
                       "> generating post body + quality check...",
                       f"**Matched Subreddits:** {subs_text}",
                       _render_titles_html(titles, selected_title_text),
                       _render_body_html(""),
                       None,
                       None,
                       "")

                from ..generator.body_generator import BodyGenerator
                bg = BodyGenerator(shared.get("llm"))
                body, _body_metrics = bg.generate(selected_title_text, pattern, topic_val, subreddit, tier)

                from ..generator.self_checker import SelfChecker
                checker = SelfChecker(shared["anti_patterns_path"])
                sc = checker.check(selected_title_text, body, pattern, subreddit)
                sc_data = None
                if sc:
                    sc_data = {"是否通过": sc.passed, "各维度": sc.dimensions, "改进建议": sc.suggestions}

                passed = sc.passed if sc else True
                check_tag = "[完成]" if passed else "[警告]"
                check_note = "质量检查通过。" if passed else f"质量检查: {len(sc.suggestions)} 条建议。"

                from ..generator.metadata_suggester import MetadataSuggester
                meta = MetadataSuggester()
                metadata = meta.suggest(subreddit, tier, topic_val)

                yield (gr.update(visible=True),
                       {**gen_state, "body_text": body, "body_title": selected_title_text,
                        "body_sc": sc_data, "body_meta": metadata, "selected_title": selected},
                       f"{check_tag} — {check_note}",
                       f"**Matched Subreddits:** {subs_text}",
                       _render_titles_html(titles, selected_title_text),
                       _render_body_html(body),
                       sc_data,
                       metadata,
                       "")
                return

            # ── Path B: full pipeline (titles + body from scratch) ──
            from ..generator.orchestrator import GeneratorOrchestrator

            target = None if sub_val == "Auto-detect" else sub_val
            orch = GeneratorOrchestrator(
                db_path=shared["db_path"],
                patterns_path=shared["patterns_path"],
                anti_patterns_path=shared["anti_patterns_path"],
                llm_client=shared.get("llm"),
            )

            yield (gr.update(visible=True), None,
                   "> 分析主题 + 生成标题及正文中...",
                   "", "", "", None, None, "")

            result = orch.generate_titles(topic_val, target, n_titles=n_val)

            if not result.candidate_titles:
                matched_str = ", ".join(f"r/{s}" for s, _ in result.matched_subreddits)
                yield (gr.update(visible=True), None,
                       f"[失败] 未找到匹配模式。\n\n匹配到的 Subreddit: {matched_str}",
                       f"**匹配:** {matched_str}", "", "", None, None, "")
                return

            primary_sub = result.matched_subreddits[0][0]
            tier = orch._get_tier(primary_sub)
            patterns_map = {p.get("pattern_id"): p for p in result.selected_patterns}

            subs_text = " | ".join(f"r/{s} ({sc:.0%})" for s, sc in result.matched_subreddits)
            titles_data = [
                {"title": t.title, "score": t.score, "hook_type": t.hook_type, "pattern_id": t.pattern_id}
                for t in result.candidate_titles
            ]
            selected = result.candidate_titles[0]
            selected_title_text = selected.title
            result.selected_title = selected
            selected_data = {"title": selected.title, "score": selected.score,
                             "hook_type": selected.hook_type, "pattern_id": selected.pattern_id}

            base_state = {"titles": titles_data, "topic": topic_val, "subreddit": primary_sub,
                          "tier": tier, "patterns": patterns_map, "selected_title": selected_data}

            # Generate body + self-check
            orch._init_components()
            pattern = next(
                (p for p in result.selected_patterns if p.get("pattern_id") == selected.pattern_id),
                result.selected_patterns[0] if result.selected_patterns else {},
            )

            body, _body_metrics = orch._body_gen.generate(
                selected.title, pattern, topic_val, primary_sub, tier
            )
            result.body = body

            sc = orch._checker.check(selected.title, body, pattern, primary_sub)
            result.self_check = sc

            sc_data = None
            if sc:
                sc_data = {"是否通过": sc.passed, "各维度": sc.dimensions, "改进建议": sc.suggestions}

            orch.save_generation(result)

            passed = sc.passed if sc else True
            check_tag = "[完成]" if passed else "[警告]"
            check_note = "质量检查通过。" if passed else f"质量检查: {len(sc.suggestions)} 条建议。"

            yield (gr.update(visible=True),
                   {**base_state, "body_text": body, "body_title": selected_title_text,
                    "body_sc": sc_data, "body_meta": result.metadata if result.metadata else None},
                   f"{check_tag} — {check_note}\n\n{subs_text}",
                   f"**Matched Subreddits:** {subs_text}",
                   _render_titles_html(titles_data, selected_title_text),
                   _render_body_html(body),
                   sc_data,
                   result.metadata if result.metadata else None,
                   "")
        except Exception as e:
            logger.exception("Generate full post failed in Gradio handler")
            yield (gr.update(visible=False), None,
                   f"[500] {type(e).__name__}: {e}",
                   "", "", "", None, None, "")

    full_btn.click(
        fn=on_generate_full,
        inputs=[topic, subreddit_dd, n_titles_slider, generation_state, selected_title_trigger],
        outputs=[results_col, generation_state, status_md, matched_md, titles_html, body_html,
                 self_check_json, metadata_json, selected_title_trigger],
    )


def _build_track_tab(shared: dict) -> None:
    """Build the Track tab — generation-centric: select gen → enter stats → classify + attribute."""
    gen_choices = ["(选择一条生成记录...)"]
    gen_files = _list_generation_files()
    gen_map: dict[str, dict] = {}
    for g in gen_files:
        gid = g.get("generation_id", "")
        title = ""
        st = g.get("selected_title") or {}
        title = st.get("title", "")
        candidates = g.get("candidate_titles", [])
        if not title and candidates:
            title = candidates[0].get("title", "")
        label = f"{gid}: {title[:60]}"
        gen_choices.append(label)
        gen_map[label] = g

    gen_dd = gr.Dropdown(
        label="选择生成记录",
        choices=gen_choices,
        value=gen_choices[0],
    )

    # Generation preview card
    gen_preview = gr.Markdown(visible=False, elem_classes=["kf-gen-preview"])

    with gr.Row():
        upvotes_num = gr.Number(label="Upvotes", value=0, precision=0, minimum=0)
        comments_num = gr.Number(label="Comments", value=0, precision=0, minimum=0)
        ratio_slider = gr.Slider(
            0, 100, value=90, step=1, label="Upvote Ratio (%)",
        )
        subreddit_display = gr.Textbox(
            label="目标 Subreddit (自动识别)",
            interactive=False,
            scale=1,
        )

    track_btn = gr.Button("记录效果", variant="primary")

    with gr.Column(visible=False) as track_result_col:
        stats_md = gr.Markdown()
        perf_label = gr.Label(label="效果判定")
        attr_btn = gr.Button("分析归因", variant="secondary", visible=False)
        attribution_json = gr.JSON(label="归因分析", value=None)

    # Store last entry for on-demand attribution
    last_entry_state = gr.State(None)

    def on_gen_select(gen_label: str):
        """When user selects a generation, show preview and auto-fill subreddit."""
        if not gen_label or gen_label.startswith("(选择"):
            return gr.update(visible=False), ""

        gen_data = gen_map.get(gen_label, {})
        if not gen_data:
            return gr.update(visible=False), ""

        title = ""
        st = gen_data.get("selected_title")
        if st:
            title = st.get("title", "")
        candidates = gen_data.get("candidate_titles", [])
        if not title and candidates:
            title = candidates[0].get("title", "")

        body_text = gen_data.get("body", "")

        matched = gen_data.get("matched_subreddits", [])
        subreddit = matched[0].get("subreddit", "") if matched else ""

        patterns = gen_data.get("selected_patterns", [])
        pattern_name = patterns[0].get("name", "") if patterns else ""
        pattern_hook = patterns[0].get("hook_type", "") if patterns else ""

        gid = gen_data.get("generation_id", "")
        created = gen_data.get("created_at", "")[:16]

        lines = [
            f"## {_html.escape(title or '(未选择标题)')}",
            "",
            f"**Subreddit:** r/{subreddit or 'unknown'} | **Pattern:** {_html.escape(pattern_name)} ({pattern_hook})",
            f"**ID:** `{gid}` | **Created:** {created}",
            "",
        ]
        if body_text:
            excerpt = body_text[:250].replace("\n", " ")
            lines.append(f"> {_html.escape(excerpt)}...")
            lines.append("")

        preview_md = "\n".join(lines)
        return (
            gr.update(value=preview_md, visible=True),
            subreddit or "",
        )

    gen_dd.change(
        fn=on_gen_select,
        inputs=[gen_dd],
        outputs=[gen_preview, subreddit_display],
    )

    def on_track(upvotes, num_comments, ratio_pct, gen_label):
        try:
            gen_data = gen_map.get(gen_label, {})
            generation_id = gen_data.get("generation_id", "manual")
            title = ""
            st = gen_data.get("selected_title")
            if st:
                title = st.get("title", "")
            candidates = gen_data.get("candidate_titles", [])
            if not title and candidates:
                title = candidates[0].get("title", "")
            body_text = gen_data.get("body", "")
            pid = ""
            patterns = gen_data.get("selected_patterns", [])
            if patterns:
                pid = patterns[0].get("pattern_id", "")

            matched = gen_data.get("matched_subreddits", [])
            subreddit = matched[0].get("subreddit", "") if matched else ""

            if not generation_id or generation_id == "manual":
                return (
                    gr.update(visible=True), "", "", gr.update(visible=False),
                    gr.update(value=None), None,
                )

            if upvotes is None or upvotes < 0:
                return (
                    gr.update(visible=False), "", "", gr.update(visible=False),
                    gr.update(value=None), None,
                )

            from ..tracker.post_tracker import PostTracker

            tracker = PostTracker(
                db_path=shared["db_path"],
                feedback_path=shared["feedback_path"],
            )

            entry = tracker.track(
                generation_id=generation_id,
                subreddit=subreddit,
                title=title,
                body=body_text,
                pattern_id=pid,
                upvotes=int(upvotes),
                num_comments=int(num_comments),
                upvote_ratio=ratio_pct / 100.0,
            )

            perf = entry.performance
            perf_display = {
                "super_viral": "超级爆款 (upvotes > median × 10)",
                "viral": "爆款 (upvotes > median × 3)",
                "passing": "及格 (upvotes > median × 1.5)",
                "failed": "失败 (upvotes < median × 1.5)",
            }.get(perf, perf)

            stats = (
                f"**r/{subreddit}** | "
                f"**Upvotes:** {entry.actual_upvotes} | "
                f"**Comments:** {entry.num_comments} | "
                f"**Ratio:** {entry.upvote_ratio:.0%} | "
                f"**Median:** {entry.subreddit_median:.0f}"
            )

            is_failed = perf == "failed"

            return (
                gr.update(visible=True),
                stats,
                f"**[{perf}]** {perf_display}",
                gr.update(visible=is_failed),
                gr.update(value=None),
                {
                    "generation_id": generation_id,
                    "subreddit": subreddit,
                    "title": title,
                    "body": body_text,
                    "pattern_id": pid,
                    "actual_upvotes": entry.actual_upvotes,
                    "num_comments": entry.num_comments,
                    "upvote_ratio": entry.upvote_ratio,
                    "performance": perf,
                    "subreddit_median": entry.subreddit_median,
                    "patterns": patterns,
                },
            )
        except Exception as e:
            logger.exception("Track failed in Gradio handler")
            return (
                gr.update(visible=True),
                f"[500] {type(e).__name__}: {e}",
                "",
                gr.update(visible=False),
                gr.update(value=None),
                None,
            )

    track_btn.click(
        fn=on_track,
        inputs=[upvotes_num, comments_num, ratio_slider, gen_dd],
        outputs=[
            track_result_col, stats_md, perf_label,
            attr_btn, attribution_json, last_entry_state,
        ],
    )

    def on_attr(last_entry):
        try:
            if not last_entry:
                return gr.update(value=None)

            from ..evolution.failure_attributor import FailureAttributor

            attributor = FailureAttributor(llm_client=shared.get("llm"))
            pattern = last_entry.get("patterns", [{}])[0] if last_entry.get("patterns") else None

            attribution = attributor.attribute(last_entry, pattern)
            attr_data = {
                "主要失败原因": attribution.primary_reason,
                "次要因素": attribution.secondary_reasons,
                "改进建议": attribution.action_items,
                "诊断信心度": attribution.confidence,
                "各维度分析": attribution.dimensions,
            }
            return gr.update(value=attr_data)
        except Exception as e:
            logger.exception("Attribution failed in Gradio handler")
            return gr.update(value={
                "错误": f"{type(e).__name__}: {e}",
            })

    attr_btn.click(
        fn=on_attr,
        inputs=[last_entry_state],
        outputs=[attribution_json],
    )


def _build_history_tab(shared: dict) -> None:
    """Build the History tab — past generations + tracking records."""
    gen_files = _list_generation_files()
    fb_entries = _load_feedback_entries()
    fb_by_gen: dict[str, dict] = {}
    for fb in fb_entries:
        fb_by_gen[fb.get("generation_id", "")] = fb

    rows = []
    all_subs = set()
    for g in gen_files:
        gid = g.get("generation_id", "")
        fb = fb_by_gen.get(gid)
        created = g.get("created_at", "")[:10]
        matched = g.get("matched_subreddits", [])
        subs = [f"r/{m['subreddit']}" for m in matched] if matched else []
        sub_display = subs[0] if subs else "-"
        all_subs.update(subs)
        st = g.get("selected_title") or {}
        title = st.get("title", "")
        if not title:
            candidates = g.get("candidate_titles", [])
            if candidates:
                title = candidates[0].get("title", "")
        perf = fb.get("performance", "-") if fb else "-"
        rows.append({
            "ID": gid, "Date": created, "Subreddit": sub_display,
            "Subreddits": subs, "Title": title[:80],
            "Performance": perf, "gen_data": g, "fb_data": fb,
        })

    if not rows:
        gr.Markdown("还没有生成记录。去 **生成** 标签页创建第一条吧。")
        return

    with gr.Row():
        sub_filter = gr.Dropdown(
            label="按 Subreddit 筛选",
            choices=["全部"] + sorted(all_subs),
            value="全部",
        )
        perf_filter = gr.Dropdown(
            label="按效果筛选",
            choices=["全部", "super_viral", "viral", "passing", "failed", "-"],
            value="全部",
        )

    # Prepare dataframe
    def filter_rows(sub_filt: str, perf_filt: str):
        filtered = [r for r in rows
                    if (sub_filt == "全部" or sub_filt in r["Subreddits"])
                    and (perf_filt == "全部" or r["Performance"] == perf_filt)]
        display = [[r["ID"], r["Date"], r["Subreddit"], r["Title"][:60], r["Performance"]] for r in filtered]
        return display

    df = gr.Dataframe(
        headers=["ID", "日期", "Subreddit", "标题", "效果"],
        value=filter_rows("全部", "全部"),
        label="生成历史",
        interactive=False,
    )

    sub_filter.change(fn=filter_rows, inputs=[sub_filter, perf_filter], outputs=[df])
    perf_filter.change(fn=filter_rows, inputs=[sub_filter, perf_filter], outputs=[df])

    with gr.Column(visible=False) as detail_col:
        detail_md = gr.Markdown()
    detail_btn = gr.Button("查看详情")

    # Store the selected row
    selected_row_state = gr.State(None)

    def on_select(evt: gr.SelectData):
        idx = evt.index[0] if hasattr(evt, 'index') else evt.index
        if isinstance(idx, (list, tuple)):
            idx = idx[0]
        gid = filter_rows("全部", "全部")[idx][0]
        gen_data = None
        fb_data = None
        for r in rows:
            if r["ID"] == gid:
                gen_data = r["gen_data"]
                fb_data = r["fb_data"]
                break
        if not gen_data:
            return gr.update(visible=False), "未找到记录。"
        md = _format_gen_detail(gen_data, fb_data)
        return gr.update(visible=True), md

    df.select(fn=on_select, inputs=[], outputs=[detail_col, detail_md])


def _format_gen_detail(gen_data: dict, fb_data: dict | None) -> str:
    """Format a generation detail as markdown."""
    lines = [f"### Generation: {gen_data.get('generation_id', '')}", ""]
    lines.append(f"**Created:** {gen_data.get('created_at', '')[:19]}")
    matched = gen_data.get("matched_subreddits", [])
    if matched:
        lines.append(f"**Subreddits:** {', '.join('r/' + m['subreddit'] for m in matched)}")

    st = gen_data.get("selected_title") or {}
    if st:
        lines.extend(["", "**Selected Title:**", f"> {st.get('title', '')}", f"_Score: {st.get('score', '')}_"])

    candidates = gen_data.get("candidate_titles", [])
    if candidates:
        lines.extend(["", "**All Candidates:**"])
        for c in candidates:
            lines.append(f"- [{c.get('score', 0):.0f}] ({c.get('hook_type', '')}) {c.get('title', '')}")

    body = gen_data.get("body", "")
    if body:
        lines.extend(["", "**Body:**", body[:500]])

    sc = gen_data.get("self_check") or {}
    if sc:
        passed = "通过" if sc.get("是否通过") else "未通过"
        lines.extend(["", f"**自检:** {passed}"])

    if fb_data:
        lines.extend([
            "", "### Tracking",
            f"- Upvotes: **{fb_data.get('actual_upvotes', '?')}** (median: {fb_data.get('subreddit_median', '?')})",
            f"- Comments: {fb_data.get('num_comments', '?')}",
            f"- Ratio: {fb_data.get('upvote_ratio', 0):.0%}",
            f"- Performance: **{fb_data.get('performance', '?')}**",
        ])

    return "\n".join(lines)


def _build_patterns_tab(shared: dict) -> None:
    """Build the Patterns tab — viral patterns + anti-patterns display."""
    import json

    patterns_data = []
    pat_path = Path(shared["patterns_path"])
    if pat_path.exists():
        patterns_data = json.loads(pat_path.read_text(encoding="utf-8"))

    anti_data = []
    anti_path = Path(shared["anti_patterns_path"])
    if anti_path.exists():
        anti_data = json.loads(anti_path.read_text(encoding="utf-8"))

    gr.Markdown("## Viral Patterns (爆款模式)")

    if not patterns_data:
        gr.Markdown("未加载模式数据。")
    else:
        with gr.Column():
            for i, p in enumerate(patterns_data):
                if i % 2 == 0:
                    with gr.Row():
                        _render_pattern_card(p)
                else:
                    _render_pattern_card(p)

    gr.Markdown("---")
    gr.Markdown("## Anti-Patterns (反模式)")

    if not anti_data:
        gr.Markdown("未加载反模式数据。")
    else:
        for ap in anti_data:
            with gr.Accordion(f"{ap.get('name', 'Unknown')} (failure rate: {ap.get('failure_rate', 0):.0%})"):
                gr.Markdown(f"**Why it fails:** {ap.get('why_it_fails', 'N/A')}")
                gr.Markdown(f"_Sample size: {ap.get('sample_size', 0)}_")


def _render_pattern_card(p: dict) -> None:
    """Render a single pattern card using Gradio components."""
    pid = p.get("pattern_id", "")
    name = p.get("name", "")
    hook = p.get("hook_type", "")
    hist_rate = p.get("historical_viral_rate", 0)
    succ_rate = p.get("success_rate")
    if succ_rate is not None:
        rate_text = f"**Viral Rate:** {hist_rate:.1%} (hist) / {succ_rate:.1%} (live)"
    else:
        rate_text = f"**Viral Rate:** {hist_rate:.1%}"
    subs = ", ".join(f"r/{s}" for s in p.get("applicable_subreddits", []))
    sample = p.get("sample_size", 0)
    status = p.get("status", "active")
    status_badge = "Inactive" if status == "inactive" else ""

    with gr.Column(elem_classes=["warm-card"]):
        gr.Markdown(
            f"### {name}\n"
            f"**Hook:** {hook} | **Sample:** {sample}  "
            + (f" | Inactive" if status_badge else "")
        )
        gr.Markdown(f"{rate_text}\n\n**Subreddits:** {subs}")
        desc = p.get("description", "")
        if desc:
            gr.Markdown(f"_{desc}_")


def _build_evolve_tab(shared: dict) -> None:
    """Build the Evolve tab — feedback count + evolve button + log."""
    fb_path = Path(shared["feedback_path"])
    count = 0
    if fb_path.exists():
        with open(fb_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1

    threshold = 50

    with gr.Row():
        with gr.Column(scale=2):
            feedback_count = gr.Number(
                label="Feedback 条目数",
                value=count, interactive=False,
            )
            progress_bar = gr.Slider(
                0, threshold, value=min(count, threshold),
                label=f"距离下一次进化 (阈值: {threshold})", interactive=False,
            )
        with gr.Column(scale=1):
            force_checkbox = gr.Checkbox(label="强制执行 (无视阈值)", value=False)
            evolve_btn = gr.Button("执行进化", variant="primary", size="lg")

    result_md = gr.Markdown()

    # Evolution log preview
    log_path = Path(shared["evolution_log_path"])
    log_text = ""
    if log_path.exists():
        log_content = log_path.read_text(encoding="utf-8")
        log_text = log_content[:2000]

    with gr.Accordion("进化日志", open=False):
        gr.Markdown(log_text or "暂无进化记录。")

    def on_evolve(force: bool):
        try:
            from ..evolution.evolution_engine import EvolutionEngine

            engine = EvolutionEngine(
                llm_client=shared.get("llm"),
                evolution_log_path=shared["evolution_log_path"],
            )
            result = engine.evolve(
                feedback_path=shared["feedback_path"],
                patterns_path=shared["patterns_path"],
                output_path=shared["patterns_path"],
            )

            if result is None:
                cnt = engine._count_entries(shared["feedback_path"])
                if cnt < threshold:
                    return f"**未执行进化。** 当前 {cnt} 条记录，需要 {threshold} 条。勾选「强制执行」可无视阈值。", gr.update(value=cnt), gr.update(value=min(cnt, threshold))
                return "**未找到 feedback 文件或 patterns 文件。**", gr.update(value=0), gr.update(value=0)

            new_cnt = engine._count_entries(shared["feedback_path"])
            summary = (
                f"### 进化完成\n"
                f"- 处理了 **{result.feedback_count}** 条反馈\n"
                f"- 更新了 **{result.patterns_updated}** 个模式\n"
                f"- 标记了 **{result.patterns_marked_inactive}** 个 inactive 模式\n\n"
                f"{result.summary}"
            )
            return (
                summary,
                gr.update(value=new_cnt),
                gr.update(value=min(new_cnt, threshold)),
            )
        except Exception as e:
            logger.exception("Evolution failed in Gradio handler")
            return (
                f"[500] {type(e).__name__}: {e}",
                gr.update(value=count),
                gr.update(value=min(count, threshold)),
            )

    evolve_btn.click(
        fn=on_evolve,
        inputs=[force_checkbox],
        outputs=[result_md, feedback_count, progress_bar],
    )
