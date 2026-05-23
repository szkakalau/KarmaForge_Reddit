"""KarmaForge v2 CLI — Reddit viral engine research + generation pipeline.

Usage:
    karmaforge collect    Run data collection
    karmaforge analyze    Run viral analysis
    karmaforge validate   Run validation
    karmaforge pipeline   Run full research pipeline
    karmaforge generate   Generate Reddit posts from patterns
"""

import logging
from pathlib import Path

import click

from . import __version__
from .storage import Database
from .llm import LLMClient, LLMConfig, LLMProvider

logger = logging.getLogger(__name__)


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _resolve_config_path(config_path: str) -> Path:
    path = Path(config_path)
    if not path.exists():
        raise click.BadParameter(f"Config file not found: {path}")
    return path


def _load_config(config_path: Path) -> dict:
    import yaml
    import os
    import re

    # Auto-load .env from project root if present
    _load_dotenv()

    with open(config_path, "r", encoding="utf-8") as f:
        raw = f.read()

    pattern = r'\$\{(\w+)\}'
    def replacer(match):
        return os.environ.get(match.group(1), "")

    raw = re.sub(pattern, replacer, raw)
    return yaml.safe_load(raw)


def _load_dotenv() -> None:
    """Load .env file from project root into os.environ."""
    import os
    env_path = Path.cwd() / ".env"
    if not env_path.exists():
        # Try relative to this file's location (src/karmaforge/cli.py → project root)
        env_path = Path(__file__).parent.parent.parent / ".env"
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


def _make_llm_client(config: dict, no_llm: bool = False) -> LLMClient | None:
    if no_llm:
        return None

    llm_cfg = config.get("credentials", {}).get("llm", {})
    api_key = llm_cfg.get("api_key", "")
    if not api_key or api_key == "${LLM_API_KEY}":
        logger.warning("LLM API key not set, using heuristic mode")
        return None

    cache_dir = Path(config.get("paths", {}).get("data_processed", "./data/processed")) / "llm_cache"

    return LLMClient(LLMConfig(
        provider=LLMProvider(llm_cfg.get("provider", "deepseek")),
        api_key=api_key,
        model=llm_cfg.get("model", "deepseek-chat"),
        api_base_url=llm_cfg.get("api_base_url", "https://api.deepseek.com/v1"),
        max_tokens=llm_cfg.get("max_tokens", 2000),
        temperature=llm_cfg.get("temperature", 0.0),
        request_timeout=llm_cfg.get("request_timeout", 60),
        cache_dir=cache_dir,
    ))


@click.group()
@click.version_option(__version__, prog_name="karmaforge")
def main() -> None:
    """KarmaForge v2 — Reddit Viral Engine: Research + Generation."""


@main.command()
@click.option("--source", "source", default="all",
              type=click.Choice(["kaggle", "praw", "thirdparty", "browser", "all"]))
@click.option("--config", "config_path", default="config.yaml",
              help="Path to config file")
def collect(source: str, config_path: str) -> None:
    """Run data collection."""
    _setup_logging()
    cfg_path = _resolve_config_path(config_path)
    config = _load_config(cfg_path)

    from .collector import CollectionOrchestrator
    orch = CollectionOrchestrator(cfg_path)
    report = orch.run()
    click.echo(report.summary())


@main.command()
@click.option("--config", "config_path", default="config.yaml")
@click.option("--no-llm", is_flag=True, help="Use heuristic classification only")
@click.option("--subreddits", "-s", multiple=True, help="Filter to specific subreddits")
def analyze(config_path: str, no_llm: bool, subreddits: tuple[str, ...]) -> None:
    """Run viral analysis on collected data."""
    _setup_logging()
    cfg_path = _resolve_config_path(config_path)
    config = _load_config(cfg_path)

    db_path = Path(config["paths"]["data_processed"]) / "karmaforge.db"
    if not db_path.exists():
        click.echo(f"Database not found at {db_path}. Run 'collect' first.", err=True)
        return

    db = Database(db_path)
    posts = db.get_all_posts()
    if not posts:
        click.echo("No posts in database. Run 'collect' first.", err=True)
        return

    if subreddits:
        posts = [p for p in posts if p.subreddit.lower() in {s.lower() for s in subreddits}]

    click.echo(f"Analyzing {len(posts)} posts...")

    llm = _make_llm_client(config, no_llm)
    analyzer_cfg = config.get("analysis", {})
    sig_level = analyzer_cfg.get("significance_level", 0.05)

    from .analyzer.title_analyzer import TitleAnalyzer
    from .analyzer.content_analyzer import ContentAnalyzer
    from .analyzer.meta_analyzer import MetaAnalyzer
    from .analyzer.visual_analyzer import VisualAnalyzer
    from .analyzer.lifecycle_analyzer import LifecycleAnalyzer
    from .analyzer.pattern_extractor import PatternExtractor
    from .analyzer.report_generator import ReportGenerator

    use_llm = not no_llm and llm is not None

    click.echo("  [1/6] Analyzing titles...")
    title_results = TitleAnalyzer(llm, use_llm, sig_level).analyze(posts)

    click.echo("  [2/6] Analyzing content...")
    content_results = ContentAnalyzer(llm, use_llm, sig_level).analyze(posts)

    click.echo("  [3/6] Analyzing meta data...")
    meta_results = MetaAnalyzer(sig_level).analyze(posts)

    click.echo("  [4/6] Analyzing visual content...")
    visual_results = VisualAnalyzer(llm).analyze(posts)

    click.echo("  [5/6] Analyzing lifecycles...")
    lifecycle_results = LifecycleAnalyzer().analyze(posts)

    click.echo("  [6/6] Extracting patterns...")
    pat_cfg = analyzer_cfg.get("pattern_extraction", {})
    extractor = PatternExtractor(
        llm_client=llm,
        significance_level=pat_cfg.get("min_pattern_significance", 0.05),
        min_cluster_size=pat_cfg.get("min_cluster_size", 30),
        viral_percentile=pat_cfg.get("viral_percentile", 90),
        max_patterns=pat_cfg.get("max_patterns", 8),
    )
    patterns, anti_patterns = extractor.extract(
        posts, title_results, content_results, meta_results, visual_results, lifecycle_results
    )

    click.echo(f"  Found {len(patterns)} patterns, {len(anti_patterns)} anti-patterns")

    click.echo("Generating reports...")
    output_dir = Path(config["paths"]["reports"])
    generator = ReportGenerator(output_dir, language=config.get("output", {}).get("report_language", "zh"))

    results = {
        "global": title_results,
    }
    content_res = {"global": content_results}
    meta_res = {"global": meta_results}
    visual_res = {"global": visual_results}
    lifecycle_res = {"global": lifecycle_results}

    generator.generate_all(
        posts, results, content_res, meta_res, visual_res, lifecycle_res,
        patterns, anti_patterns,
    )

    extracts_dir = Path(config["paths"].get("data_patterns", "./data/patterns"))
    extractor.save_patterns(patterns, anti_patterns, extracts_dir)

    click.echo(f"Done! Reports saved to {output_dir}")


@main.command()
@click.option("--config", "config_path", default="config.yaml")
@click.option("--no-llm", is_flag=True, help="Use heuristic classification only")
@click.option("--ml", "use_ml", is_flag=True, help="Run ML classifier validation alongside rule-based")
def validate(config_path: str, no_llm: bool, use_ml: bool) -> None:
    """Run backtesting and holdout validation."""
    _setup_logging()
    cfg_path = _resolve_config_path(config_path)
    config = _load_config(cfg_path)

    db_path = Path(config["paths"]["data_processed"]) / "karmaforge.db"
    if not db_path.exists():
        click.echo(f"Database not found. Run 'collect' first.", err=True)
        return

    db = Database(db_path)
    posts = db.get_all_posts()
    if not posts:
        click.echo("No posts in database.", err=True)
        return

    click.echo(f"Validating on {len(posts)} posts...")

    llm = _make_llm_client(config, no_llm)

    from .analyzer.pattern_extractor import PatternExtractor

    pat_cfg = config.get("analysis", {}).get("pattern_extraction", {})
    extractor = PatternExtractor(
        llm_client=llm,
        min_cluster_size=pat_cfg.get("min_cluster_size", 30),
        max_patterns=pat_cfg.get("max_patterns", 8),
    )

    from .validator import Backtester, HoldoutValidator, StratifiedValidator, MLValidator

    val_cfg = config.get("validation", {})
    bt_cfg = val_cfg.get("backtesting", {})
    ho_cfg = val_cfg.get("holdout", {})
    ml_cfg = val_cfg.get("ml", {})

    backtester = Backtester(
        pattern_extractor=extractor,
        train_start=bt_cfg.get("train_start", "2023-01-01"),
        train_end=bt_cfg.get("train_end", "2023-12-31"),
        test_start=bt_cfg.get("test_start", "2024-01-01"),
        test_end=bt_cfg.get("test_end", "2024-12-31"),
        viral_percentile=bt_cfg.get("viral_percentile", 90),
        match_threshold=bt_cfg.get("pattern_match_threshold", 0.6),
        min_recall=bt_cfg.get("min_recall", 0.60),
        min_precision=bt_cfg.get("min_precision", 0.40),
        llm_client=llm,
    )

    holdout = HoldoutValidator(
        pattern_extractor=extractor,
        num_holdout=ho_cfg.get("num_holdout_subreddits", 4),
        min_precision_ratio=ho_cfg.get("min_precision_ratio", 0.70),
        seed=ho_cfg.get("seed", 42),
        llm_client=llm,
    )

    stratified = StratifiedValidator(
        backtester=backtester,
        holdout_validator=holdout,
        min_posts_per_tier=val_cfg.get("stratified", {}).get("min_posts_per_tier_for_validation", 500),
    )

    bt_result = backtester.run(posts)
    ho_result = holdout.run(posts)
    st_result = stratified.run(posts)

    click.echo(f"\n=== Rule-Based Validation ===")
    click.echo(f"Backtesting:")
    click.echo(f"  Recall: {bt_result.recall:.4f} {'PASS' if bt_result.pass_recall else 'FAIL'}")
    click.echo(f"  Precision: {bt_result.precision:.4f} {'PASS' if bt_result.pass_precision else 'FAIL'}")
    click.echo(f"  F1: {bt_result.f1_score:.4f}")

    click.echo(f"\nHoldout:")
    click.echo(f"  Precision ratio: {ho_result.precision_ratio:.4f} {'PASS' if ho_result.pass_threshold else 'FAIL'}")
    click.echo(f"  Transferability: {ho_result.transferability_score:.4f}")

    click.echo(f"\nStratified: overall={'PASS' if st_result.overall_pass else 'FAIL'}")

    if use_ml:
        click.echo(f"\n=== ML Classifier Validation ===")
        ml_validator = MLValidator(
            train_start=ml_cfg.get("train_start", bt_cfg.get("train_start", "2023-01-01")),
            train_end=ml_cfg.get("train_end", bt_cfg.get("train_end", "2023-12-31")),
            test_start=ml_cfg.get("test_start", bt_cfg.get("test_start", "2024-01-01")),
            test_end=ml_cfg.get("test_end", bt_cfg.get("test_end", "2024-12-31")),
            viral_percentile=ml_cfg.get("viral_percentile", bt_cfg.get("viral_percentile", 80)),
            min_recall=ml_cfg.get("min_recall", 0.60),
            min_precision=ml_cfg.get("min_precision", 0.30),
        )
        ml_result = ml_validator.run(posts)

        click.echo(f"  Recall: {ml_result.recall:.4f} {'PASS' if ml_result.pass_recall else 'FAIL'}")
        click.echo(f"  Precision: {ml_result.precision:.4f} {'PASS' if ml_result.pass_precision else 'FAIL'}")
        click.echo(f"  F1: {ml_result.f1_score:.4f}")
        click.echo(f"  Baseline precision: {ml_result.baseline_precision:.4f}")
        click.echo(f"  Best threshold: {ml_result.best_threshold:.4f}")
        if ml_result.best_params:
            click.echo(f"  Best params: max_iter={ml_result.best_params.get('max_iter', ml_result.best_params.get('n_estimators','?'))}, "
                       f"max_depth={ml_result.best_params.get('max_depth','?')}, "
                       f"learning_rate={ml_result.best_params.get('learning_rate','?'):.4f}")
        if ml_result.feature_importance:
            click.echo(f"  Top features:")
            for name, imp in list(ml_result.feature_importance.items())[:10]:
                click.echo(f"    {name}: {imp:.4f}")

        click.echo(f"\n  Rule-based vs ML comparison:")
        click.echo(f"    {'Metric':<20} {'Rule':>10} {'ML':>10}")
        click.echo(f"    {'-'*40}")
        click.echo(f"    {'Recall':<20} {bt_result.recall:>10.4f} {ml_result.recall:>10.4f}")
        click.echo(f"    {'Precision':<20} {bt_result.precision:>10.4f} {ml_result.precision:>10.4f}")
        click.echo(f"    {'F1':<20} {bt_result.f1_score:>10.4f} {ml_result.f1_score:>10.4f}")

    if bt_result.pass_recall and bt_result.pass_precision:
        click.echo("\nM2.5 Gate: PASSED — ready for v2")
    elif bt_result.pass_recall or bt_result.pass_precision:
        click.echo("\nM2.5 Gate: CONDITIONAL PASS — fix gaps and re-validate")
    else:
        click.echo("\nM2.5 Gate: FAILED — reassess methodology before v2")


@main.command()
@click.argument("user_input")
@click.option("--subreddit", "-s", default=None, help="Target subreddit (skip matching)")
@click.option("--full", is_flag=True, help="Generate full post (title + body)")
@click.option("--title-index", "-t", default=0, type=int, help="Which title candidate to use for body (0-based)")
@click.option("--n-titles", default=3, type=int, help="Number of title candidates (1-5)")
@click.option("--config", "config_path", default="config.yaml")
@click.option("--no-llm", is_flag=True, help="Use heuristic generation only")
@click.option("--output", "output_format", default="markdown",
              type=click.Choice(["markdown", "json"]))
def generate(
    user_input: str, subreddit: str | None, full: bool, title_index: int,
    n_titles: int, config_path: str, no_llm: bool, output_format: str,
) -> None:
    """Generate Reddit post from topic/keywords.

    \b
    Examples:
      karmaforge generate "automation script saves time"
      karmaforge generate "my weight loss journey" -s Fitness --full
      karmaforge generate "SaaS startup lessons" --n-titles 5 --output json
    """
    _setup_logging()
    cfg_path = _resolve_config_path(config_path)
    config = _load_config(cfg_path)

    path_cfg = config.get("paths", {})
    db_path = Path(path_cfg.get("data_processed", "./data/processed")) / "karmaforge.db"
    if not db_path.exists():
        click.echo(f"Database not found at {db_path}. Run 'collect' first.", err=True)
        return

    patterns_path = Path(path_cfg.get("data_patterns", "./data/patterns")) / "patterns.json"
    anti_patterns_path = Path(path_cfg.get("data_patterns", "./data/patterns")) / "anti_patterns.json"

    llm = _make_llm_client(config, no_llm)

    from .generator.orchestrator import GeneratorOrchestrator

    orch = GeneratorOrchestrator(
        db_path=str(db_path),
        patterns_path=str(patterns_path),
        anti_patterns_path=str(anti_patterns_path),
        llm_client=llm,
    )

    n_titles = max(1, min(5, n_titles))

    if full:
        click.echo(f"Generating full post for: {user_input}")
        result = orch.generate_full(user_input, subreddit, title_index, n_titles)
        _print_full_result(result, output_format)
    else:
        click.echo(f"Generating title candidates for: {user_input}")
        result = orch.generate_titles(user_input, subreddit, n_titles)
        _print_titles_result(result, output_format)


def _print_titles_result(result, fmt: str) -> None:
    """Print title-only generation result."""
    if fmt == "json":
        import json as _json
        data = {
            "generation_id": result.generation_id,
            "matched_subreddits": [
                {"subreddit": s, "score": sc} for s, sc in result.matched_subreddits
            ],
            "candidate_titles": [
                {"title": t.title, "score": t.score, "hook_type": t.hook_type}
                for t in result.candidate_titles
            ],
            "metadata": result.metadata,
        }
        click.echo(_json.dumps(data, ensure_ascii=False, indent=2))
        return

    click.echo(f"\n  Generation ID: {result.generation_id}")
    click.echo(f"  Matched subreddits:")
    for sub, score in result.matched_subreddits[:5]:
        marker = " <-- primary" if sub == result.matched_subreddits[0][0] else ""
        click.echo(f"    r/{sub:25s} (match: {score:.0%}){marker}")

    if not result.candidate_titles:
        click.echo("\n  No titles generated. Check patterns and LLM configuration.")
        return

    click.echo(f"\n  Candidate Titles:")
    click.echo(f"  {'#':<3} {'Score':<7} {'Hook':<28} {'Title'}")
    click.echo(f"  {'-'*3} {'-'*7} {'-'*28} {'-'*50}")

    for i, ct in enumerate(result.candidate_titles):
        hook_short = ct.hook_type[:26] if ct.hook_type else "—"
        click.echo(f"  {i:<3} {ct.score:<7.0f} {hook_short:<28} {ct.title}")

    if result.metadata:
        click.echo(f"\n  Metadata suggestions:")
        click.echo(f"    Best day: {result.metadata.get('recommended_day', '?')}")
        click.echo(f"    Best hour (UTC): {result.metadata.get('recommended_hour_utc', '?')}")
        click.echo(f"    Recommended flair: {result.metadata.get('recommended_flair', '?')}")
        click.echo(f"    Mark as OC: {result.metadata.get('should_mark_oc', False)}")

    click.echo(f"\n  Use 'karmaforge generate ... --full --title-index N' to generate a full post.")


def _print_full_result(result, fmt: str) -> None:
    """Print full generation result (title + body + self-check)."""
    if fmt == "json":
        import json as _json
        data = {
            "generation_id": result.generation_id,
            "matched_subreddits": [
                {"subreddit": s, "score": sc} for s, sc in result.matched_subreddits
            ],
            "candidate_titles": [
                {"title": t.title, "score": t.score, "hook_type": t.hook_type}
                for t in result.candidate_titles
            ],
            "selected_title": (
                {"title": result.selected_title.title, "score": result.selected_title.score}
                if result.selected_title else None
            ),
            "body": result.body,
            "metadata": result.metadata,
            "self_check": (
                {
                    "passed": result.self_check.passed,
                    "dimensions": result.self_check.dimensions,
                    "suggestions": result.self_check.suggestions,
                }
                if result.self_check else None
            ),
        }
        click.echo(_json.dumps(data, ensure_ascii=False, indent=2))
        return

    click.echo(f"\n{'='*60}")
    click.echo(f"  Generation ID: {result.generation_id}")
    primary_sub = result.matched_subreddits[0][0] if result.matched_subreddits else "?"
    click.echo(f"  Target: r/{primary_sub}")
    click.echo(f"{'='*60}")

    if result.selected_title:
        click.echo(f"\n  Title (score: {result.selected_title.score:.0f}/100):")
        click.echo(f"  {result.selected_title.title}")

    if result.body:
        click.echo(f"\n  Body:")
        click.echo(f"  {'-'*50}")
        for line in result.body.split("\n"):
            click.echo(f"  {line}")
        click.echo(f"  {'-'*50}")

    if result.self_check:
        sc = result.self_check
        status = "PASSED" if sc.passed else "WARNINGS"
        click.echo(f"\n  Self-Check: {status}")
        for dim, info in sc.dimensions.items():
            dim_status = info.get("status", "?")
            dim_score = info.get("score", 0)
            icon = {"ok": "[OK]", "warn": "[WARN]", "fail": "[FAIL]"}.get(dim_status, "[?]")
            click.echo(f"    {icon} {dim:20s} {dim_score:5.0f} [{dim_status}]")
        if sc.suggestions:
            click.echo(f"\n  Suggestions:")
            for s in sc.suggestions:
                click.echo(f"    - {s}")

    if result.metadata:
        click.echo(f"\n  Metadata:")
        click.echo(f"    Best day: {result.metadata.get('recommended_day', '?')}")
        click.echo(f"    Best hour (UTC): {result.metadata.get('recommended_hour_utc', '?')}")
        click.echo(f"    Flair: {result.metadata.get('recommended_flair', '?')}")
        click.echo(f"    Mark OC: {result.metadata.get('should_mark_oc', False)}")


@main.command()
@click.option("--config", "config_path", default="config.yaml")
@click.option("--no-llm", is_flag=True)
def pipeline(config_path: str, no_llm: bool) -> None:
    """Run full pipeline: collect → analyze → validate."""
    _setup_logging()

    ctx = click.get_current_context()
    click.echo("=== Phase 1: Collection ===")
    ctx.invoke(collect, config_path=config_path)

    click.echo("\n=== Phase 2: Analysis ===")
    ctx.invoke(analyze, config_path=config_path, no_llm=no_llm)

    click.echo("\n=== Phase 3: Validation ===")
    ctx.invoke(validate, config_path=config_path, no_llm=no_llm)

    click.echo("\nPipeline complete. M2.5 gate results above.")


# ── Track command ──────────────────────────────────────────────


@main.command()
@click.option("--upvotes", "-u", type=int, default=None, help="Post upvote count")
@click.option("--comments", "-c", type=int, default=None, help="Post comment count")
@click.option("--ratio", "-r", type=float, default=None, help="Upvote ratio (0.0-1.0)")
@click.option("--subreddit", "-s", default=None, help="Subreddit name (e.g. productivity)")
@click.option("--url", default="", help="Optional post URL for reference")
@click.option("--generation-id", "-g", default=None, help="Link to a prior generation result")
@click.option("--list", "list_mode", is_flag=True, help="List recent tracking entries")
@click.option("--history", "-H", "history_sub", default=None, help="Filter tracking by subreddit")
@click.option("--detail", "-d", "detail_id", default=None, help="Show detail for a generation ID")
@click.option("--config", "config_path", default="config.yaml")
def track(
    upvotes: int | None,
    comments: int | None,
    ratio: float | None,
    subreddit: str | None,
    url: str,
    generation_id: str | None,
    list_mode: bool,
    history_sub: str | None,
    detail_id: str | None,
    config_path: str,
) -> None:
    """Record Reddit post performance manually.

    \b
    Enter upvotes, comments, and upvote ratio to classify post performance.
    Data is saved to feedback.jsonl for the evolution engine.

    \b
    Examples:
      karmaforge track --upvotes 245 --comments 32 --ratio 0.94 --subreddit productivity
      karmaforge track -u 500 -c 45 -r 0.88 -s rust --generation-id gen_abc123
      karmaforge track --list
      karmaforge track --history productivity
      karmaforge track --detail gen_abc123
    """
    _setup_logging()
    cfg_path = _resolve_config_path(config_path)
    config = _load_config(cfg_path)

    path_cfg = config.get("paths", {})
    db_path = str(Path(path_cfg.get("data_processed", "./data/processed")) / "karmaforge.db")
    feedback_path = Path(path_cfg.get("data_tracking", "./data/tracking")) / "feedback.jsonl"

    from .tracker.post_tracker import PostTracker

    tracker = PostTracker(db_path=db_path, feedback_path=feedback_path)

    # --list
    if list_mode:
        entries = tracker.load_feedback()
        if not entries:
            click.echo("No tracking entries yet.")
            return
        _print_track_list(entries, history_sub)
        return

    # --detail
    if detail_id:
        entries = tracker.load_feedback()
        entry = next((e for e in entries if e.get("generation_id") == detail_id), None)
        if not entry:
            click.echo(f"No entry found for generation '{detail_id}'.")
            return
        _print_track_detail(entry)
        return

    # --history (implies list mode filter)
    if history_sub:
        entries = tracker.load_feedback()
        filtered = [e for e in entries if e.get("subreddit", "").lower() == history_sub.lower()]
        if not filtered:
            click.echo(f"No tracking entries for r/{history_sub}.")
            return
        _print_track_list(filtered, None)
        return

    # Manual record requires upvotes, comments, ratio, subreddit
    if upvotes is None or comments is None or ratio is None or not subreddit:
        click.echo(
            "Error: Provide --upvotes, --comments, --ratio, and --subreddit to record.\n"
            "  Or use --list / --history / --detail to browse.",
            err=True,
        )
        return

    # Load generation context if linked
    gen_title = ""
    gen_body = ""
    gen_pattern_id = ""
    gen_sub = subreddit.lower()

    if generation_id:
        gen_path = Path("data/generations") / f"{generation_id}.json"
        if gen_path.exists():
            import json as _json
            with open(gen_path, "r", encoding="utf-8") as f:
                gen_data = _json.load(f)
            gen_title = (gen_data.get("selected_title") or {}).get("title", "")
            gen_body = gen_data.get("body", "")
            if gen_data.get("selected_patterns"):
                gen_pattern_id = gen_data["selected_patterns"][0].get("pattern_id", "")
        else:
            click.echo(f"Generation '{generation_id}' not found. Proceeding without context.")

    entry = tracker.track(
        generation_id=generation_id or "manual",
        subreddit=gen_sub,
        title=gen_title,
        body=gen_body,
        pattern_id=gen_pattern_id,
        upvotes=upvotes,
        num_comments=comments,
        upvote_ratio=ratio,
        url=url,
    )

    click.echo(f"\n  Recorded for r/{gen_sub}:")
    click.echo(f"    Upvotes:      {entry.actual_upvotes}")
    click.echo(f"    Comments:     {entry.num_comments}")
    click.echo(f"    Upvote ratio: {entry.upvote_ratio:.0%}")
    click.echo(f"    Performance:  {entry.performance}")
    click.echo(f"    Subreddit median: {entry.subreddit_median:.0f}")

    if entry.performance == "failed":
        click.echo(f"\n  This post underperformed. Run 'karmaforge evolve' to learn from it.")


def _print_track_list(entries: list[dict], sub_filter: str | None) -> None:
    """Print tracking entries as a table."""
    if sub_filter:
        entries = [e for e in entries if e.get("subreddit", "").lower() == sub_filter.lower()]

    click.echo(f"\n  Tracking entries ({len(entries)}):")
    click.echo(f"  {'Date':<22} {'Subreddit':<22} {'Votes':<8} {'Performance':<16} {'Title'}")
    click.echo(f"  {'-'*22} {'-'*22} {'-'*8} {'-'*16} {'-'*40}")

    for e in sorted(entries, key=lambda x: x.get("tracked_at", ""), reverse=True)[:30]:
        date = e.get("tracked_at", "")[:19]
        sub = f"r/{e.get('subreddit', '?')}"
        votes = str(e.get("actual_upvotes", "?"))
        perf = e.get("performance", "?")
        title = (e.get("title", "") or "")[:38]
        click.echo(f"  {date:<22} {sub:<22} {votes:<8} {perf:<16} {title}")


def _print_track_detail(entry: dict) -> None:
    """Print a single tracking entry in detail."""
    click.echo(f"\n  Generation ID:  {entry.get('generation_id', '?')}")
    click.echo(f"  Tracked at:     {entry.get('tracked_at', '?')}")
    click.echo(f"  Subreddit:      r/{entry.get('subreddit', '?')}")
    click.echo(f"  Title:          {entry.get('title', '?')}")
    click.echo(f"  URL:            {entry.get('url', '?')}")
    click.echo(f"\n  Actual upvotes: {entry.get('actual_upvotes', '?')}")
    click.echo(f"  Comments:       {entry.get('num_comments', '?')}")
    click.echo(f"  Upvote ratio:   {entry.get('upvote_ratio', 0):.0%}")
    click.echo(f"  Performance:    {entry.get('performance', '?')}")
    click.echo(f"  Subreddit median: {entry.get('subreddit_median', '?')}")

    attribution = entry.get("attribution")
    if attribution and isinstance(attribution, dict):
        click.echo(f"\n  Attribution:")
        click.echo(f"    Primary:   {attribution.get('primary_reason', '?')}")
        for r in attribution.get("secondary_reasons", []):
            click.echo(f"    Secondary: {r}")
        for a in attribution.get("action_items", []):
            click.echo(f"    Action:    {a}")
        click.echo(f"    Confidence: {attribution.get('confidence', '?')}%")


# ── Evolve command ─────────────────────────────────────────────


@main.command()
@click.option("--config", "config_path", default="config.yaml")
@click.option("--force", is_flag=True, help="Force evolution even below threshold")
@click.option("--no-llm", is_flag=True, help="Skip LLM-based attribution")
def evolve(config_path: str, force: bool, no_llm: bool) -> None:
    """Run pattern evolution from accumulated feedback.

    \b
    Processes feedback.jsonl and updates pattern success rates.
    Requires 50+ feedback entries by default. Use --force to override.
    """
    _setup_logging()
    cfg_path = _resolve_config_path(config_path)
    config = _load_config(cfg_path)

    path_cfg = config.get("paths", {})
    feedback_path = Path(path_cfg.get("data_tracking", "./data/tracking")) / "feedback.jsonl"
    patterns_path = Path(path_cfg.get("data_patterns", "./data/patterns")) / "patterns.json"
    evolution_log_path = Path(path_cfg.get("data_tracking", "./data/tracking")) / "evolution_log.md"

    if not feedback_path.exists():
        click.echo(f"No feedback file at {feedback_path}. Nothing to evolve from.", err=True)
        return

    if not patterns_path.exists():
        click.echo(f"No patterns file at {patterns_path}.", err=True)
        return

    llm = _make_llm_client(config, no_llm)

    from .evolution.evolution_engine import EvolutionEngine

    engine = EvolutionEngine(llm_client=llm, evolution_log_path=evolution_log_path)

    if not force and not engine.should_evolve(feedback_path):
        from .evolution.evolution_engine import EVOLUTION_THRESHOLD
        click.echo(
            f"Not enough feedback entries. Need {EVOLUTION_THRESHOLD}+ entries.\n"
            f"Use --force to override."
        )
        return

    click.echo("Running evolution cycle...")
    result = engine.evolve(feedback_path, patterns_path)

    if result:
        click.echo(f"\nEvolution complete!")
        click.echo(f"  Patterns updated:    {result.patterns_updated}")
        click.echo(f"  Patterns inactivated: {result.patterns_marked_inactive}")
        click.echo(f"  Log: {evolution_log_path}")
    else:
        click.echo("No changes made.")


@main.command("web")
@click.option("--port", default=7860, help="Server port (default: 7860)")
@click.option("--no-browser", is_flag=True, help="Don't auto-open browser")
@click.option("--share", is_flag=True, help="Create a public sharing link")
@click.option("--debug", is_flag=True, help="Enable Gradio debug mode")
def web(port: int, no_browser: bool, share: bool, debug: bool) -> None:
    """Launch the KarmaForge web desktop interface."""
    _setup_logging()
    _load_dotenv()

    try:
        import gradio  # noqa: F401
    except ImportError:
        click.echo("gradio not installed. Run: pip install karmaforge[web]", err=True)
        return

    from .web.app import create_app

    click.echo(f"Starting KarmaForge Desktop at http://localhost:{port}")
    if not no_browser:
        click.echo("Opening browser...")

    app = create_app()
    app.launch(
        server_port=port,
        inbrowser=not no_browser,
        share=share,
        debug=debug,
        theme=getattr(app, "theme", None),
        css=getattr(app, "css", None),
    )


if __name__ == "__main__":
    main()
