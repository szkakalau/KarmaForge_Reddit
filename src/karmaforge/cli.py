"""KarmaForge v1 CLI — Reddit viral engine research pipeline.

Usage:
    karmaforge collect    Run data collection
    karmaforge analyze    Run viral analysis
    karmaforge validate   Run validation
    karmaforge pipeline   Run full pipeline
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

    with open(config_path, "r", encoding="utf-8") as f:
        raw = f.read()

    pattern = r'\$\{(\w+)\}'
    def replacer(match):
        return os.environ.get(match.group(1), "")

    raw = re.sub(pattern, replacer, raw)
    return yaml.safe_load(raw)


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
    """KarmaForge v1 — Reddit Viral Engine Research Phase."""


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
def validate(config_path: str) -> None:
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

    from .analyzer.pattern_extractor import PatternExtractor

    pat_cfg = config.get("analysis", {}).get("pattern_extraction", {})
    extractor = PatternExtractor(
        min_cluster_size=pat_cfg.get("min_cluster_size", 30),
        max_patterns=pat_cfg.get("max_patterns", 8),
    )

    from .validator import Backtester, HoldoutValidator, StratifiedValidator

    val_cfg = config.get("validation", {})
    bt_cfg = val_cfg.get("backtesting", {})
    ho_cfg = val_cfg.get("holdout", {})

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
    )

    holdout = HoldoutValidator(
        pattern_extractor=extractor,
        num_holdout=ho_cfg.get("num_holdout_subreddits", 4),
        min_precision_ratio=ho_cfg.get("min_precision_ratio", 0.70),
        seed=ho_cfg.get("seed", 42),
    )

    stratified = StratifiedValidator(
        backtester=backtester,
        holdout_validator=holdout,
        min_posts_per_tier=val_cfg.get("stratified", {}).get("min_posts_per_tier_for_validation", 500),
    )

    bt_result = backtester.run(posts)
    ho_result = holdout.run(posts)
    st_result = stratified.run(posts)

    click.echo(f"\nBacktesting:")
    click.echo(f"  Recall: {bt_result.recall:.4f} {'PASS' if bt_result.pass_recall else 'FAIL'}")
    click.echo(f"  Precision: {bt_result.precision:.4f} {'PASS' if bt_result.pass_precision else 'FAIL'}")
    click.echo(f"  F1: {bt_result.f1_score:.4f}")

    click.echo(f"\nHoldout:")
    click.echo(f"  Precision ratio: {ho_result.precision_ratio:.4f} {'PASS' if ho_result.pass_threshold else 'FAIL'}")
    click.echo(f"  Transferability: {ho_result.transferability_score:.4f}")

    click.echo(f"\nStratified: overall={'PASS' if st_result.overall_pass else 'FAIL'}")

    if bt_result.pass_recall and bt_result.pass_precision:
        click.echo("\nM2.5 Gate: PASSED — ready for v2")
    elif bt_result.pass_recall or bt_result.pass_precision:
        click.echo("\nM2.5 Gate: CONDITIONAL PASS — fix gaps and re-validate")
    else:
        click.echo("\nM2.5 Gate: FAILED — reassess methodology before v2")


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
    ctx.invoke(validate, config_path=config_path)

    click.echo("\nPipeline complete. M2.5 gate results above.")


if __name__ == "__main__":
    main()
