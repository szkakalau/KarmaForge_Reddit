"""Report generator — produces the v1 deliverable: markdown methodology reports."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..storage import Post
from ..analyzer.title_analyzer import TitleAnalysisResult
from ..analyzer.content_analyzer import ContentAnalysisResult
from ..analyzer.meta_analyzer import MetaAnalysisResult
from ..analyzer.visual_analyzer import VisualAnalysisResult
from ..analyzer.lifecycle_analyzer import LifecycleAnalysisResult
from ..analyzer.pattern_extractor import ViralPattern, AntiPattern

logger = logging.getLogger(__name__)


class ReportGenerator:
    def __init__(self, output_dir: Path, language: str = "zh") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.lang = language

    def generate_all(
        self,
        posts: list[Post],
        title_results: dict,
        content_results: dict,
        meta_results: dict,
        visual_results: dict,
        lifecycle_results: dict,
        patterns: list[ViralPattern],
        anti_patterns: list[AntiPattern],
        validation_results: dict | None = None,
    ) -> list[Path]:
        files = []
        files.append(self.generate_overview(
            title_results, content_results, meta_results, patterns, validation_results
        ))
        files.append(self.generate_title_methodology(title_results))
        files.append(self.generate_content_methodology(content_results))
        files.append(self.generate_pattern_library(patterns))
        files.append(self.generate_anti_pattern_library(anti_patterns))
        files.extend(self.generate_subreddit_profiles(posts, meta_results))
        files.append(self.generate_time_matrix(meta_results))
        if validation_results:
            files.append(self.generate_validation_report(validation_results))
        files.append(self.generate_dataset_index(posts))

        logger.info("Generated %d report files in %s", len(files), self.output_dir)
        return files

    def generate_overview(
        self,
        title_results: dict,
        content_results: dict,
        meta_results: dict,
        patterns: list[ViralPattern],
        validation_results: dict | None = None,
    ) -> Path:
        lines = [self._h1("Reddit 爆款分析 — 总览报告"), ""]

        lines.append(f"**生成时间**：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"**爆款模式数量**：{len(patterns)}")
        lines.append(f"**分析方法论版本**：v1.0")
        lines.append("")

        lines.append(self._h2("关键发现"))
        lines.append("")

        if isinstance(title_results, dict) and title_results:
            lines.append(self._h3("标题策略"))
            all_results = list(title_results.values())
            if all_results:
                r = all_results[0]
                lines.append(f"- 最优标题字数区间：{r.optimal_range[0]} — {r.optimal_range[1]} 词")
                lines.append(f"- 冒号使用率：{r.colon_usage:.1%}")
                lines.append(f"- 问句使用率：{r.question_usage:.1%}")

                hooks = r.hook_type_distribution
                if hooks:
                    top_hook = max(hooks, key=lambda h: hooks[h].get("avg_upvotes", 0))
                    lines.append(f"- 最强钩子类型：{top_hook} (均分 {hooks[top_hook].get('avg_upvotes', 0)})")
            lines.append("")

        if isinstance(content_results, dict) and content_results:
            lines.append(self._h3("正文策略"))
            all_results = list(content_results.values())
            if all_results:
                r = all_results[0]
                lines.append(f"- 最优正文字数区间：{r.optimal_word_range[0]:.0f} — {r.optimal_word_range[1]:.0f} 词")
                lines.append(f"- TL;DR 使用率：{r.tldr_usage_rate:.1%}")
                lines.append(f"- 互动引导率：{r.call_to_action_rate:.1%}")
                lines.append(f"- 最优可读性 (FK Grade)：{r.optimal_readability_range[0]:.1f} — {r.optimal_readability_range[1]:.1f}")
            lines.append("")

        if patterns:
            lines.append(self._h3("爆款模式概览"))
            lines.append("")
            lines.append("| 模式 | 爆款率 | 样本量 | p值 |")
            lines.append("|------|--------|--------|-----|")
            for p in patterns:
                lines.append(f"| {p.name} | {p.historical_viral_rate:.1%} | {p.sample_size} | {p.p_value:.4f} |")
            lines.append("")

        if validation_results:
            lines.append(self._h3("验证结果"))
            vr = validation_results
            if isinstance(vr, dict):
                bt_recall = vr.get("recall", "N/A")
                bt_prec = vr.get("precision", "N/A")
                lines.append(f"- Backtesting 召回率：{bt_recall}")
                lines.append(f"- Backtesting 精确率：{bt_prec}")
            lines.append("")

        path = self.output_dir / "总览报告.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def generate_title_methodology(self, title_results: dict) -> Path:
        lines = [self._h1("Reddit 标题方法论"), ""]

        for scope, result in title_results.items():
            if isinstance(result, TitleAnalysisResult):
                lines.append(self._h2(f"范围：{scope}"))
                lines.append(f"- 样本量：{result.n}")
                lines.append(f"- 最优标题字数：{result.optimal_range[0]} — {result.optimal_range[1]}")
                lines.append("")
                lines.append(self._h3("结构特征"))
                lines.append(f"| 特征 | 使用率 |")
                lines.append(f"|------|--------|")
                lines.append(f"| 冒号 `:` | {result.colon_usage:.1%} |")
                lines.append(f"| 破折号 `—` | {result.dash_usage:.1%} |")
                lines.append(f"| 括号 `()` | {result.parenthesis_usage:.1%} |")
                lines.append(f"| 数字 | {result.number_usage:.1%} |")
                lines.append(f"| 问句 | {result.question_usage:.1%} |")
                lines.append("")

                if result.word_count_distribution:
                    lines.append(self._h3("字数分布"))
                    lines.append(self._distribution_table(result.word_count_distribution, "标题字数"))
                    lines.append("")

                if result.hook_type_distribution:
                    lines.append(self._h3("钩子类型分布"))
                    lines.append("| 钩子类型 | 数量 | 平均Upvotes |")
                    lines.append("|----------|------|-------------|")
                    for hook, stats in sorted(result.hook_type_distribution.items(), key=lambda x: x[1].get("avg_upvotes", 0), reverse=True):
                        lines.append(f"| {hook} | {stats.get('count', 0)} | {stats.get('avg_upvotes', 0)} |")
                    lines.append("")

                if result.top_keywords:
                    lines.append(self._h3("高频关键词"))
                    for kw in result.top_keywords[:15]:
                        lines.append(f"- **{kw['word']}** ({kw['frequency']}次)")
                    lines.append("")

        path = self.output_dir / "标题方法论.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def generate_content_methodology(self, content_results: dict) -> Path:
        lines = [self._h1("Reddit 正文方法论"), ""]

        for scope, result in content_results.items():
            if isinstance(result, ContentAnalysisResult):
                lines.append(self._h2(f"范围：{scope}"))
                lines.append(f"- 样本量：{result.n}")
                lines.append(f"- 最优正文字数：{result.optimal_word_range[0]:.0f} — {result.optimal_word_range[1]:.0f}")
                lines.append(f"- 最优可读性 (FK Grade)：{result.optimal_readability_range[0]:.1f} — {result.optimal_readability_range[1]:.1f}")
                lines.append("")

                lines.append(self._h3("结构特征"))
                lines.append(f"| 特征 | 使用率 |")
                lines.append(f"|------|--------|")
                lines.append(f"| 列表 (bullet/numbered) | {result.list_usage_rate:.1%} |")
                lines.append(f"| TL;DR | {result.tldr_usage_rate:.1%} |")
                lines.append(f"| 加粗 | {result.bold_usage_rate:.1%} |")
                lines.append(f"| 引用 | {result.quote_usage_rate:.1%} |")
                lines.append(f"| 结尾提问 | {result.question_ending_rate:.1%} |")
                lines.append(f"| CTA引导 | {result.call_to_action_rate:.1%} |")
                lines.append("")

                if result.narrative_mode_distribution:
                    lines.append(self._h3("叙事模式分布"))
                    lines.append("| 模式 | 占比 | 平均Upvotes |")
                    lines.append("|------|------|-------------|")
                    for mode, stats in sorted(result.narrative_mode_distribution.items(), key=lambda x: x[1].get("avg_upvotes", 0), reverse=True):
                        lines.append(f"| {mode} | {stats.get('pct', 0):.1%} | {stats.get('avg_upvotes', 0)} |")
                    lines.append("")

        path = self.output_dir / "正文方法论.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def generate_pattern_library(self, patterns: list[ViralPattern]) -> Path:
        lines = [self._h1("爆款模式库"), ""]
        lines.append(f"共提取 **{len(patterns)}** 种统计显著的爆款模式。")
        lines.append("")

        for i, p in enumerate(patterns, 1):
            lines.append(self._h2(f"模式 {i}：{p.name}"))
            lines.append(f"- **描述**：{p.description}")
            lines.append(f"- **历史爆款率**：{p.historical_viral_rate:.1%} (95% CI: {p.confidence_interval[0]:.1%} — {p.confidence_interval[1]:.1%})")
            lines.append(f"- **p值**：{p.p_value:.6f}")
            lines.append(f"- **平均Upvotes**：{p.avg_upvotes:.0f}")
            lines.append(f"- **样本量**：{p.sample_size}")
            lines.append(f"- **标题模板**：`{p.title_template}`")
            if p.body_structure_template:
                lines.append(f"- **正文结构**：")
                try:
                    structure = json.loads(p.body_structure_template)
                    for section in structure:
                        lines.append(f"  - {section}")
                except json.JSONDecodeError:
                    lines.append(f"  {p.body_structure_template}")
            lines.append(f"- **适用Subreddit**：{', '.join(f'r/{s}' for s in p.applicable_subreddits[:10])}")
            if p.recommended_metrics:
                lines.append(f"- **推荐指标**：{json.dumps(p.recommended_metrics, ensure_ascii=False)}")
            lines.append(f"- **案例帖子**：{', '.join(p.exemplar_posts[:5])}")
            lines.append("")

        path = self.output_dir / "爆款模式库.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def generate_anti_pattern_library(self, anti_patterns: list[AntiPattern]) -> Path:
        lines = [self._h1("反模式库"), ""]
        lines.append("以下模式在数据中与低表现显著相关，应避免使用。")
        lines.append("")

        for i, ap in enumerate(anti_patterns, 1):
            lines.append(self._h2(f"反模式 {i}：{ap.name}"))
            lines.append(f"- **描述**：{ap.description}")
            lines.append(f"- **失败率**：{ap.failure_rate:.1%}")
            lines.append(f"- **样本量**：{ap.sample_size}")
            lines.append(f"- **诊断**：{ap.why_it_fails}")
            lines.append(f"- **案例帖子**：{', '.join(ap.exemplar_posts[:3])}")
            lines.append("")

        path = self.output_dir / "反模式库.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def generate_subreddit_profiles(
        self, posts: list[Post], meta_results: dict
    ) -> list[Path]:
        by_sub: dict[str, list[Post]] = {}
        for p in posts:
            by_sub.setdefault(p.subreddit.lower(), []).append(p)

        paths = []
        profile_dir = self.output_dir / "subreddit画像"
        profile_dir.mkdir(parents=True, exist_ok=True)

        for sub, sub_posts in sorted(by_sub.items()):
            if len(sub_posts) < 20:
                continue

            median_upvotes = sorted([p.upvotes for p in sub_posts])[len(sub_posts) // 2]
            viral = sorted([p.upvotes for p in sub_posts], reverse=True)
            viral_90 = viral[max(0, len(viral) // 10)]

            lines = [
                self._h1(f"r/{sub} Subreddit 画像"),
                "",
                f"**样本量**：{len(sub_posts)} 篇帖子",
                f"**中位Upvotes**：{median_upvotes}",
                f"**90分位Upvotes (爆款线)**：{viral_90}",
                "",
                self._h2("标题偏好"),
                f"- 平均标题字数：{sum(len(p.title.split()) for p in sub_posts if p.title) / max(sum(1 for p in sub_posts if p.title), 1):.1f}",
                "",
                self._h2("内容形式偏好"),
            ]

            content_types = {}
            for p in sub_posts:
                ct = p.content_type.value
                content_types[ct] = content_types.get(ct, 0) + 1
            dominant = max(content_types, key=content_types.get)
            lines.append(f"- 主要形式：{dominant} ({content_types[dominant] / len(sub_posts):.1%})")

            if sub in meta_results:
                specificity = meta_results[sub]
                if isinstance(specificity, dict):
                    lines.append("")
                    lines.append(self._h2("特异度"))
                    lines.append(f"- 标题长度偏差：{specificity.get('optimal_title_length', ('N/A', 'N/A'))}")
                    lines.append(f"- 正文长度偏差：{specificity.get('optimal_body_length', ('N/A', 'N/A'))}")

            path = profile_dir / f"r-{sub}.md"
            path.write_text("\n".join(lines), encoding="utf-8")
            paths.append(path)

        return paths

    def generate_time_matrix(self, meta_results: dict) -> Path:
        lines = [self._h1("最佳发帖时间矩阵"), ""]

        for scope, result in meta_results.items():
            if hasattr(result, 'best_time_matrix') and result.best_time_matrix:
                lines.append(self._h2(f"范围：{scope}"))
                lines.append("")
                lines.append("| 时间槽 | 平均Upvotes | 中位Upvotes | 数量 | 相对得分 |")
                lines.append("|--------|-------------|-------------|------|----------|")
                for slot, stats in sorted(result.best_time_matrix.items(), key=lambda x: x[1].get("relative_score", 0), reverse=True)[:20]:
                    lines.append(
                        f"| {slot} | {stats.get('avg_upvotes', 0)} | {stats.get('median_upvotes', 0)} | "
                        f"{stats.get('count', 0)} | {stats.get('relative_score', 0):.2f} |"
                    )
                lines.append("")

        path = self.output_dir / "时间矩阵.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def generate_validation_report(self, validation_results: dict) -> Path:
        lines = [self._h1("验证报告"), ""]

        lines.append(self._h2("Backtesting 结果"))
        rec = validation_results.get("recall", 0)
        prec = validation_results.get("precision", 0)
        f1 = validation_results.get("f1_score", 0)
        lines.append(f"- **召回率**：{rec:.4f} {'✅' if rec >= 0.60 else '❌'} (目标 ≥ 0.60)")
        lines.append(f"- **精确率**：{prec:.4f} {'✅' if prec >= 0.40 else '❌'} (目标 ≥ 0.40)")
        lines.append(f"- **F1**：{f1:.4f}")
        lines.append(f"- **基线精确率**：{validation_results.get('baseline_precision', 0):.4f}")
        lines.append(f"- **训练集**：{validation_results.get('train_post_count', 0)} 篇")
        lines.append(f"- **测试集**：{validation_results.get('test_post_count', 0)} 篇")
        cm = validation_results.get("confusion_matrix", {})
        if cm:
            lines.append(f"- **混淆矩阵**：TP={cm.get('tp', 0)} FP={cm.get('fp', 0)} TN={cm.get('tn', 0)} FN={cm.get('fn', 0)}")
        lines.append("")

        per_tier = validation_results.get("per_tier_results", {})
        if per_tier:
            lines.append(self._h3("按Tier分层结果"))
            lines.append("| Tier | 召回率 | 精确率 |")
            lines.append("|------|--------|--------|")
            for tier, metrics in per_tier.items():
                lines.append(f"| {tier} | {metrics.get('recall', 0):.4f} | {metrics.get('precision', 0):.4f} |")
            lines.append("")

        ho = validation_results.get("holdout", {})
        if ho:
            lines.append(self._h2("Holdout 验证结果"))
            lines.append(f"- **训练集精确率**：{ho.get('training_precision', 0):.4f}")
            lines.append(f"- **留出集精确率**：{ho.get('holdout_precision', 0):.4f}")
            lines.append(f"- **比率**：{ho.get('precision_ratio', 0):.4f} {'✅' if ho.get('precision_ratio', 0) >= 0.70 else '❌'} (目标 ≥ 0.70)")
            lines.append(f"- **迁移力得分**：{ho.get('transferability_score', 0):.4f}")
            lines.append(f"- **留出Subreddit**：{', '.join(f'r/{s}' for s in ho.get('holdout_subreddits', []))}")

        path = self.output_dir / "验证报告.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def generate_dataset_index(self, posts: list[Post]) -> Path:
        by_sub: dict[str, list[Post]] = {}
        by_tier: dict[str, int] = {}
        by_source: dict[str, int] = {}

        for p in posts:
            by_sub.setdefault(p.subreddit.lower(), []).append(p)
            tier = p.tier.value if p.tier else "unknown"
            by_tier[tier] = by_tier.get(tier, 0) + 1
            by_source[p.source_dataset] = by_source.get(p.source_dataset, 0) + 1

        lines = [
            self._h1("数据集索引"),
            "",
            f"**总帖子数**：{len(posts)}",
            f"**总Subreddit数**：{len(by_sub)}",
            f"**数据源**：{', '.join(f'{k}({v})' for k, v in by_source.items())}",
            f"**按Tier**：{', '.join(f'{k}({v})' for k, v in sorted(by_tier.items()))}",
            "",
            self._h2("Subreddit列表"),
            "| Subreddit | 帖子数 | Tier |",
            "|-----------|--------|------|",
        ]

        for sub, sub_posts in sorted(by_sub.items(), key=lambda x: len(x[1]), reverse=True):
            tier = sub_posts[0].tier.value if sub_posts[0].tier else "unknown"
            lines.append(f"| r/{sub} | {len(sub_posts)} | {tier} |")

        path = self.output_dir / "数据集" / "index.md"
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    @staticmethod
    def _distribution_table(distribution: dict, label: str) -> str:
        bins = distribution.get("bins", [])
        counts = distribution.get("counts", [])
        inflection = distribution.get("inflection_points", [])
        pcts = distribution.get("percentiles", {})

        if not bins or not counts:
            return f"(无分布数据)"

        max_count = max(counts) if counts else 1
        lines = [f"| 区间 | 数量 | 分布 |{' ←拐点' if inflection else ''}"]
        lines.append(f"|------|------|------|{'------|' if inflection else ''}")

        for i in range(len(counts)):
            bar_len = int(counts[i] / max_count * 30)
            bar = "█" * bar_len
            marker = " ←" if (i in inflection) else ""
            lines.append(f"| {bins[i]:.0f}-{bins[i+1] if i+1 < len(bins) else ''} | {counts[i]} | {bar} |{marker}")

        if pcts:
            lines.append(f"\n关键分位数：")
            lines.append(f"| p10 | p25 | p50 | p75 | p90 | p95 | p99 |")
            lines.append(f"|-----|-----|-----|-----|-----|-----|-----|")
            lines.append(f"| {pcts.get('p10', 0)} | {pcts.get('p25', 0)} | {pcts.get('p50', 0)} | {pcts.get('p75', 0)} | {pcts.get('p90', 0)} | {pcts.get('p95', 0)} | {pcts.get('p99', 0)} |")

        return "\n".join(lines)

    @staticmethod
    def _h1(text: str) -> str:
        return f"\n# {text}\n"

    @staticmethod
    def _h2(text: str) -> str:
        return f"\n## {text}\n"

    @staticmethod
    def _h3(text: str) -> str:
        return f"\n### {text}\n"
