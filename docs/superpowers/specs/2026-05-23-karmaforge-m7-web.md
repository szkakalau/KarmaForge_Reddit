# KarmaForge M7: Web Desktop App — Design Spec

**Date:** 2026-05-23
**Status:** Approved
**Context:** M4 (generation) and M5 (tracking + evolution) are complete. All backend logic lives in `src/karmaforge/generator/`, `tracker/`, `evolution/`. No web code exists.

---

## Goals

Turn KarmaForge from a CLI tool into a single-user desktop web app that exposes all existing functionality through a browser UI. The app runs locally (`localhost`), no multi-tenancy, no auth.

---

## Technology

**Gradio 5.x** — Python-native web UI framework. All backend logic is called via direct Python imports (not CLI subprocess). The Gradio app wraps GeneratorOrchestrator, PostTracker, EvolutionEngine, and Database classes.

- **No FastAPI, no Next.js, no JavaScript.** Pure Python.
- **LLM API key** read from existing `.env` file; a Settings tab exposes key editing.
- **Launch:** `karmaforge web` CLI command.

---

## Architecture

```
karmaforge web (gradio app)
│
├── Tab: Generate    → GeneratorOrchestrator
├── Tab: Track       → PostTracker + metrics.classify_performance
├── Tab: History     → reads data/generations/*.json + data/tracking/feedback.jsonl
├── Tab: Patterns    → reads data/patterns/patterns.json + anti_patterns.json
├── Tab: Evolve      → EvolutionEngine
└── Tab: Settings    → .env read/write
```

All modules imported directly: `from karmaforge.generator import GeneratorOrchestrator`. No subprocess.

---

## Tab Specifications

### 1. Generate (生成)

**Inputs:**
- `topic` — textbox, the user's post topic/idea
- `subreddit` — dropdown (optional), populated from DB subreddit list, or "Auto-detect"
- `n_titles` — slider, 1-5, default 3
- `generate_body` — checkbox, default True (generate full post with body)
- `use_llm` — checkbox, default True

**Outputs:**
- Matched subreddits (from SubredditMatcher)
- 3 candidate titles with scores, hook types, and pattern sources
- Selected title → body text → self-check report (if `generate_body` checked)
- Copy-to-clipboard button for title + body

**Flow:**
```
[Topic textbox] [Subreddit dropdown] [Generate button]
→ spinner while LLM runs
→ Tab with 3 candidate titles (highlight best)
→ Click a title → body + self-check panel
```

### 2. Track (追踪)

**Inputs:**
- `url` — textbox, Reddit post URL
- `generation_id` — dropdown (optional), link to a previous generation

**Outputs:**
- Upvotes, comments, upvote ratio
- Performance classification (super_viral / viral / passing / failed) with color badge
- Subreddit median comparison (bar chart)
- Attribution summary (if failed)
- Feedback saved to feedback.jsonl

**Flow:**
```
[URL textbox] [Generation ID dropdown] [Track button]
→ spinner while Playwright fetches old.reddit.com
→ Stats card with classification badge
→ (if failed) Attribution panel
```

### 3. History (历史)

**Display:**
- Table of past generations + tracking records merged by generation_id
- Columns: date, topic, subreddit, title, status (tracked? performance?), actions
- Click row → detail panel with full GenerationResult + TrackingRecord
- Filter by subreddit, date range, performance

**Data source:**
- `data/generations/*.json` for generation data
- `data/tracking/feedback.jsonl` for tracking data
- Joined by `generation_id`

### 4. Patterns (模式库)

**Display:**
- Grid of 8 viral pattern cards, each showing:
  - Name, hook_type, narrative_mode
  - Historical viral rate + success_rate blend
  - Applicable subreddits
  - Exemplar post links
- Anti-patterns section (4 items) with failure_rate and why_it_fails
- Read-only display; no editing

### 5. Evolve (进化)

**Display:**
- Feedback count (progress bar toward 50 threshold)
- "Evolve" button (enabled when count >= 50, or with --force checkbox)
- Last evolution timestamp + summary from evolution_log.md
- Patterns updated / marked inactive summary

**Action:**
- Click Evolve → EvolutionEngine.evolve() runs → display results

### 6. Settings (设置)

**Inputs:**
- LLM API Key (password field, reads from .env, writes back)
- Model selection (dropdown: deepseek-v4-pro, deepseek-v4-flash)
- Playwright headless toggle (checkbox)

---

## Visual Theme

**Direction:** Warm Paper — warm off-white background, serif headings, coral accent.

| Property | Value |
|----------|-------|
| Background | `#faf6f0` (warm off-white) |
| Card bg | `#ffffff` |
| Text primary | `#3d3226` (dark brown) |
| Text secondary | `#5c4d3d` |
| Accent / primary | `#c1663a` (tuscan coral) |
| Success | `#e8f0e4` bg / `#3d6b35` text |
| Error | `#fce8e4` bg / `#b83a1f` text |
| Heading font | Lora (Google Fonts) |
| Body font | Public Sans (Google Fonts) — via Gradio font param |
| Border radius | `lg` (8-10px) |
| Spacing | `md` |

**Gradio theme config:**
```python
theme = gr.themes.Soft(
    primary_hue="orange",
    neutral_hue="stone",
    font=gr.themes.GoogleFont("Lora"),
    font_mono=gr.themes.GoogleFont("JetBrains Mono"),
    radius_size="lg",
    spacing_size="md",
)
```

---

## Directory Structure (new)

```
src/karmaforge/
├── web/                       # [NEW]
│   ├── __init__.py            # create_app() → gr.Blocks instance
│   ├── app.py                 # Tab layout assembly
│   ├── theme.py               # Gradio theme config
│   └── tabs/
│       ├── __init__.py
│       ├── generate.py        # Generate tab
│       ├── track.py           # Track tab
│       ├── history.py         # History tab
│       ├── patterns.py        # Patterns tab
│       ├── evolution.py       # Evolve tab
│       └── settings.py        # Settings tab
└── cli.py                     # [MODIFY] +web command
```

---

## CLI Addition

```bash
karmaforge web              # Start Gradio on localhost:7860, open browser
karmaforge web --port 8080  # Custom port
karmaforge web --no-browser # Don't auto-open browser
```

Implementation in `cli.py`:
```python
@cli.command("web")
@click.option("--port", default=7860)
@click.option("--no-browser", is_flag=True)
@click.option("--share", is_flag=True)
def web_command(port, no_browser, share):
    """Launch the KarmaForge web interface."""
    from karmaforge.web import create_app
    app = create_app()
    app.launch(server_port=port, inbrowser=not no_browser, share=share)
```

---

## Dependencies

Add to `pyproject.toml`:
```toml
[project.optional-dependencies]
web = ["gradio>=5.0"]
```

---

## Implementation Sequence

| # | File | What | Est. |
|---|------|------|------|
| 1 | `src/karmaforge/web/theme.py` | Gradio Soft theme with warm paper colors | 0.3d |
| 2 | `src/karmaforge/web/__init__.py` + `app.py` | `create_app()`, tab skeleton, Gradio Blocks | 0.5d |
| 3 | `src/karmaforge/web/tabs/generate.py` | Topic input → orchestrator → titles + body | 1d |
| 4 | `src/karmaforge/web/tabs/track.py` | URL input → PostTracker → perf classification | 0.5d |
| 5 | `src/karmaforge/web/tabs/history.py` | Table + detail from generations/ + feedback | 0.5d |
| 6 | `src/karmaforge/web/tabs/patterns.py` | Pattern card grid + anti-patterns | 0.5d |
| 7 | `src/karmaforge/web/tabs/evolution.py` | Feedback count + evolve button + log | 0.5d |
| 8 | `src/karmaforge/web/tabs/settings.py` | API key + model + headless toggle | 0.3d |
| 9 | `src/karmaforge/cli.py` | `karmaforge web` command | 0.2d |
| 10 | `pyproject.toml` | gradio dependency | 0.1d |
| 11 | `tests/test_web.py` | Component + callback tests | 1d |
| **Total** | | | **~5.5 days** |

---

## Verification

```bash
# Unit tests
python -m pytest tests/test_web.py -v --tb=short

# Full test suite (ensure no regressions)
python -m pytest tests/ -v --tb=short

# Launch and smoke test
karmaforge web --no-browser
# Visit http://localhost:7860, test each tab manually
```

## Scope Boundaries

**In scope:**
- All 6 tabs (Generate, Track, History, Patterns, Evolve, Settings)
- Gradio app with warm paper theme
- `karmaforge web` CLI command
- Tests for web layer

**Out of scope:**
- User authentication / accounts
- Multi-user support
- Remote deployment / hosting
- Mobile responsive design
- API endpoints for external consumption
- Automated posting to Reddit
