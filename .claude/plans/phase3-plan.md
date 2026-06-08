# Phase 3 实施方案：自然选择机制

## 目标

让系统能够自主发现新模式、从成功中提取基因、跨社区迁移知识。

## 三个子任务

### 3.1: 模式挖掘引擎 (`src/karmaforge/evolution/pattern_miner.py`)

**问题**: 8 个模式来自一次性 V1 分析，之后再无新发现。

**算法**:
- 从 feedback.jsonl 的所有条目（不只是未处理的）中提取 (hook_type, narrative_mode, tier) 三元组
- 对每个三元组计算 viral_rate = (viral+passing) / total
- 执行 Fisher's exact test（样本少）或 chi-square test（样本多）检验显著性
- 筛选 p < 0.05 且不在现有 patterns.json 中的组合
- 候选模式 status="candidate"，历史爆款率从 feedback 数据推算
- 当 candidate 积累 30+ 条 feedback 且 success_rate > 0.3 时，自动提升为 active

**类**: `PatternMiner`
- `mine(feedback_path, existing_patterns)` → list of candidate patterns
- `promote_candidates(patterns, feedback_path)` → promote qualified candidates

### 3.2: 基因提取器 (`src/karmaforge/evolution/gene_extractor.py`)

**问题**: 成功帖子的结构模板从未被复用。

**方案**:
- 从 feedback.jsonl 中筛选 viral + super_viral 帖子
- 提取三类"基因片段":
  1. **标题结构模板**: 用简单规则抽象化标题 (数字→N, 动词原形, 名词保留)
     例: "I built a Python script that saved 40 hours" → "I [built/made] [a/an] [tool] that [saved/cut] N [hours/days]"
  2. **正文开头模式**: 前 50 词的句子类型 (数据开头/故事开头/问题开头)
  3. **CTA 句式**: 结尾引导互动的句式
- 存储在 pattern 的 `successful_templates` 列表中 (最多保留 10 条)
- 生成时注入 prompt: "参考以下成功结构：..."

**类**: `GeneExtractor`
- `extract_from_feedback(feedback_path, patterns)` → enriches patterns with templates
- `inject_into_prompt(templates, base_prompt)` → augmented prompt string

### 3.3: 跨 Subreddit 迁移 (`src/karmaforge/evolution/subreddit_transfer.py`)

**问题**: 新 subreddit 从零开始，没有历史数据。

**方案**:
- 用每个 pattern 在各 subreddit 的 success_rate 构建向量
- 计算 subreddit 间的 cosine similarity
- 对于缺乏数据的目标 subreddit，用最相似的源 subreddit 的 pattern 做 warm start
- 随着目标 subreddit 数据积累，迁移权重逐渐衰减

**类**: `SubredditTransfer`
- `build_similarity(patterns)` → {sub: {similar_sub: score}}
- `warm_start(target_subreddit, patterns, top_k=3)` → recommended patterns

## 修改文件清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新建 | `src/karmaforge/evolution/pattern_miner.py` | 模式挖掘引擎 |
| 新建 | `src/karmaforge/evolution/gene_extractor.py` | 基因提取器 |
| 新建 | `src/karmaforge/evolution/subreddit_transfer.py` | 跨 subreddit 迁移 |
| 修改 | `src/karmaforge/evolution/__init__.py` | 导出新类 |
| 修改 | `src/karmaforge/generator/title_generator.py` | 注入基因模板到 prompt |
| 修改 | `src/karmaforge/generator/body_generator.py` | 注入基因模板到 prompt |
| 修改 | `src/karmaforge/cli.py` | 新增 `karmaforge mine` 命令 |

## 验证
- 现有 181 个测试保持通过
- `karmaforge mine` 能从 feedback.jsonl 生成候选模式
- 基因提取器能从 viral 帖子中提取可复用的结构模板
