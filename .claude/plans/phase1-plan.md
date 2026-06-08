# Phase 1 实施方案：打通进化循环

## 目标

将 KarmaForge 从"手动触发式工具"升级为"自动化自我进化系统"。

## 四个子任务

### 1. ML 模型持久化 + 标题排序器 (`src/karmaforge/generator/ml_ranker.py`)

**问题**：MLValidator 训练完 GradientBoostingClassifier 后直接丢弃，从未用于生成管道。

**方案**：创建一个独立的"标题排序模型"，只使用生成时可用的特征（16个），训练一个小型分类器，部署到 TitleGenerator 中。

**为什么不用完整的 42 特征模型**：完整模型依赖 body 特征、VADER 情感、发布时间、内容类型等，这些在标题生成阶段不可用。用默认值填充 20+ 个缺失特征会严重降低预测质量。

**实现**：
- 新建 `src/karmaforge/generator/ml_ranker.py`
- `TitleRanker` 类：
  - `train(feedback_entries, patterns)` — 从 feedback.jsonl 构建训练数据，训练 LogisticRegression
  - `save(path)` / `load(path)` — joblib 序列化到 `data/models/title_ranker.joblib`
  - `rank(candidates, subreddit, tier, pattern)` — 对候选标题重新打分
  - 16 个特征：title_word_count, title_char_count, avg_word_length_title, title_has_question/number/exclamation, title_caps_ratio, title_starts_how/why, title_exclamation_count, hook_type_index, narrative_mode_index, subreddit_viral_rate, tier_t1/t2/t3, pattern_historical_viral_rate
  - 标签：从 feedback 的 performance 列（viral/passing→1, failed→0）
- 集成到 `TitleGenerator.generate()`：启发式评分与 ML 评分加权混合（默认 50/50）
- 新增 CLI 命令：`karmaforge train-ranker` — 从 feedback.jsonl 训练并保存模型

### 2. Reddit 帖子监控器 (`src/karmaforge/monitor/reddit_monitor.py`)

**问题**：用户必须手动跑 `karmaforge track` 才能记录帖子表现。反馈循环的最大瓶颈。

**方案**：创建一个 PRAW 驱动的监控器，自动获取已发帖子的实时表现数据。

**实现**：
- 新建 `src/karmaforge/monitor/` 模块（`__init__.py` + `reddit_monitor.py`）
- `RedditMonitor` 类：
  - 从 feedback.jsonl 读取所有带 Reddit URL 的帖子
  - 通过 PRAW `submission(id=...)` 获取当前 upvotes/num_comments/upvote_ratio
  - 更新 feedback entry（仅当数值变化时）
  - 对 URL 不包含 reddit.com 的条目，从 title+subreddit 尝试搜索匹配
  - 返回更新的条目列表
- 与 `PostTracker` 集成：监控器获取数据后自动调用 `track()`

### 3. 自动进化触发器

**问题**：evolution 完全手动触发。即使 Phase 0 修复了无限循环，用户仍需手动跑 `karmaforge evolve`。

**方案**：在每次 track 后自动检查是否需要进化。

**实现**：
- 修改 `PostTracker.track()` 添加 `auto_evolve` 参数
- track 后检查 unprocessed feedback count >= EVOLUTION_THRESHOLD
- 如果满足条件，自动调用 EvolutionEngine.evolve()
- 在 CLI `track` 和 Web track 中默认开启
- 新增 `--no-auto-evolve` flag 允许跳过

### 4. CLI 统一监控命令

**问题**：没有一步到位的自动化入口。

**方案**：新增 `karmaforge monitor` 命令，串联所有自动化步骤。

**实现**：
- 新增 `karmaforge monitor` CLI 命令：
  - `--once`：单次运行（fetch → track → evolve）
  - `--daemon`：持续运行模式，每 N 秒循环
  - `--interval`：循环间隔（默认 21600 = 6 小时）
  - `--auto-evolve`：获取数据后自动进化
  - `--dry-run`：只获取不记录
  ```
  # 单次监控
  karmaforge monitor --once
  
  # 后台持续监控（每6小时）
  karmaforge monitor --daemon --interval 21600
  ```

## 修改文件清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新建 | `src/karmaforge/generator/ml_ranker.py` | 标题排序模型 |
| 新建 | `src/karmaforge/monitor/__init__.py` | 监控模块入口 |
| 新建 | `src/karmaforge/monitor/reddit_monitor.py` | Reddit 帖子监控器 |
| 新建 | `src/karmaforge/monitor/auto_evolve.py` | 自动进化触发器 |
| 修改 | `src/karmaforge/generator/title_generator.py` | 集成 MLRanker |
| 修改 | `src/karmaforge/tracker/post_tracker.py` | 添加 auto_evolve 钩子 |
| 修改 | `src/karmaforge/cli.py` | 新增 monitor + train-ranker 命令 |
| 修改 | `config.yaml` | praw_enabled: true + 添加 monitor 配置段 |

## 验证方式

- 新增模块的单元测试
- 现有 181 个测试全部保持通过
- `karmaforge train-ranker` 完成训练并保存模型文件
- `karmaforge monitor --once --dry-run` 成功获取 Reddit 帖子数据
