"""Stratified validation — per-tier backtesting + holdout + cross-tier transferability."""

import logging
from dataclasses import dataclass, field

from ..storage import Post, Tier
from ..analyzer.pattern_extractor import PatternExtractor, ViralPattern
from .backtester import Backtester, BacktestResult
from .holdout_validator import HoldoutValidator, HoldoutResult

logger = logging.getLogger(__name__)


@dataclass
class StratifiedValidationResult:
    t1_backtest: dict = field(default_factory=dict)
    t2_backtest: dict = field(default_factory=dict)
    t3_backtest: dict = field(default_factory=dict)
    t1_holdout: dict = field(default_factory=dict)
    t2_holdout: dict = field(default_factory=dict)
    t3_holdout: dict = field(default_factory=dict)
    cross_tier_transferability: dict = field(default_factory=dict)
    universal_patterns: list[str] = field(default_factory=list)
    tier_specific_patterns: dict = field(default_factory=dict)
    overall_pass: bool = False

    def to_dict(self) -> dict:
        d = {}
        for k, v in self.__dict__.items():
            d[k] = list(v) if isinstance(v, tuple) else v
        return d


class StratifiedValidator:
    def __init__(
        self,
        backtester: Backtester,
        holdout_validator: HoldoutValidator,
        min_posts_per_tier: int = 500,
    ) -> None:
        self.backtester = backtester
        self.holdout_validator = holdout_validator
        self.min_posts_per_tier = min_posts_per_tier

    def run(self, posts: list[Post]) -> StratifiedValidationResult:
        posts_by_tier = self._split_by_tier(posts)
        result = StratifiedValidationResult()

        # Per-tier backtesting
        for tier in [Tier.T1, Tier.T2, Tier.T3]:
            tier_posts = posts_by_tier.get(tier, [])
            if len(tier_posts) < self.min_posts_per_tier:
                logger.info("Skipping %s backtest: only %d posts", tier.value, len(tier_posts))
                continue

            bt_result = self.backtester.run(tier_posts)
            setattr(result, f"{tier.value}_backtest", bt_result.to_dict())

        # Per-tier holdout
        for tier in [Tier.T1, Tier.T2, Tier.T3]:
            tier_posts = posts_by_tier.get(tier, [])
            if len(tier_posts) < self.min_posts_per_tier:
                continue

            ho_result = self.holdout_validator.run(tier_posts)
            setattr(result, f"{tier.value}_holdout", ho_result.to_dict())

        # Cross-tier transferability
        result.cross_tier_transferability = self._cross_tier_transfer(posts_by_tier)

        # Universal vs tier-specific patterns
        result.universal_patterns, result.tier_specific_patterns = self._categorize_patterns()

        # Overall pass/fail
        result.overall_pass = self._check_overall_pass(result)

        logger.info("Stratified validation complete. Overall pass: %s", result.overall_pass)
        return result

    def _split_by_tier(self, posts: list[Post]) -> dict[Tier, list[Post]]:
        groups: dict[Tier, list[Post]] = {}
        for p in posts:
            if p.tier:
                groups.setdefault(p.tier, []).append(p)
        return groups

    def _cross_tier_transfer(self, posts_by_tier: dict[Tier, list[Post]]) -> dict:
        transferability = {}
        tiers = [Tier.T1, Tier.T2, Tier.T3]

        for source_tier in tiers:
            if source_tier not in posts_by_tier:
                continue
            transferability[source_tier.value] = {}

            for target_tier in tiers:
                if source_tier == target_tier or target_tier not in posts_by_tier:
                    continue

                source_posts = posts_by_tier[source_tier]
                target_posts = posts_by_tier[target_tier]

                if len(source_posts) < 100 or len(target_posts) < 100:
                    transferability[source_tier.value][target_tier.value] = {
                        "precision": None,
                        "note": f"Insufficient data: source={len(source_posts)}, target={len(target_posts)}",
                    }
                    continue

                transferability[source_tier.value][target_tier.value] = {
                    "source_tier_size": len(source_posts),
                    "target_tier_size": len(target_posts),
                }

        return transferability

    def _categorize_patterns(self) -> tuple[list[str], dict[Tier, list[str]]]:
        return [], {Tier.T1: [], Tier.T2: [], Tier.T3: []}

    def _check_overall_pass(self, result: StratifiedValidationResult) -> bool:
        backtests = [result.t1_backtest, result.t2_backtest, result.t3_backtest]
        holdouts = [result.t1_holdout, result.t2_holdout, result.t3_holdout]

        bt_pass = any(bt.get("pass_recall") and bt.get("pass_precision") for bt in backtests if bt)
        ho_pass = any(ho.get("pass_threshold") for ho in holdouts if ho)

        return bt_pass and ho_pass
