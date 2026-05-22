# KarmaForge v1 — Reddit Viral Engine

Research phase: data-driven Reddit viral content methodology extraction.

## Setup

```bash
# Install dependencies
pip install -e .

# Optional: browser collection support
pip install -e ".[browser]"

# Optional: development tools
pip install -e ".[dev]"

# Download spaCy model (required for NLP analysis)
python -m spacy download en_core_web_sm

# Download nltk data
python -m nltk.downloader punkt vader_lexicon stopwords
```

## Configuration

1. Copy `config.yaml` and adjust settings
2. Set environment variables for credentials:
   ```powershell
   $env:LLM_API_KEY = "your-deepseek-api-key"
   $env:REDDIT_CLIENT_ID = "your-reddit-client-id"      # optional for v1
   $env:REDDIT_CLIENT_SECRET = "your-reddit-secret"     # optional for v1
   ```

## Usage

```bash
# Full pipeline
karmaforge pipeline --no-llm

# Or step by step
karmaforge collect
karmaforge analyze --no-llm
karmaforge validate
```

## Output

All reports are generated in `分析报告/`:
- `总览报告.md` — Overview and key findings
- `标题方法论.md` — Title methodology
- `正文方法论.md` — Body content methodology
- `爆款模式库.md` — Viral pattern library
- `反模式库.md` — Anti-pattern library
- `subreddit画像/` — Per-subreddit profiles
- `时间矩阵.md` — Best posting time matrix
- `验证报告.md` — Validation results

## Testing

```bash
pytest
pytest --cov=src/karmaforge
```
