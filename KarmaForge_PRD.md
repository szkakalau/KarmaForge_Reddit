# Reddit爆款引擎 - 产品需求文档 (PRD)

> 版本：v1.1 | 日期：2026-05-22 | 作者：大川 | 修订：Claude Code review

---

## 一、项目概述

### 1.1 一句话定义
基于Reddit全站Top内容的结构化分析，构建一个"输入关键词/Subreddit → 输出高概率爆款帖子"的AI创作引擎，并具备发帖后的效果追踪与自我进化能力。

### 1.2 为什么要做这件事
- Reddit是英文互联网最大的UGC社区，月活19亿+，帖子爆与不爆的规律高度可量化（upvotes、comments、awards三重信号）
- 市面上没有针对Reddit的深度爆款分析工具，现有工具（Subreddit Stats、Reddit Metrics）只做数据展示，不做创作方法论提取
- 自媒体出海的英文内容创作，Reddit是最被低估的流量入口——一篇爆款帖子可以带几万访问量到个人站/产品页
- 自用先跑通，数据和方法论沉淀后可直接SaaS化

### 1.3 成功标准
- **P0**：输入关键词，5分钟内生成一篇结构化Reddit帖子，爆款率（upvotes > subreddit中位数3倍）> 30%
- **P1**：发帖后72小时内自动追踪效果，失败案例自动归因并更新模型
- **P2**：积累500+条发帖记录后，爆款率 > 50%

---

## 二、目标用户

### 2.1 核心用户（v1自用）
- 英文自媒体创作者 / 独立开发者出海 / 个人品牌建设者

### 2.2 商业化用户（v2+）
- 出海营销团队
- Reddit营销SaaS订阅用户
- 内容机构/Agency

---

## 三、核心功能模块

### 3.0 版本范围界定

| 版本 | 范围 | 定位 |
|------|------|------|
| **v1（研究期）** | 模块A 数据采集 + 模块B 爆款分析 + 内部验证 | 输出一套经过统计验证的爆款方法论文档 |
| **v2（行动期）** | 模块C 帖子生成 + 模块D 效果追踪与进化 + Web界面 | 从分析到创作到追踪的完整闭环 |

**v1 不做的事**：帖子生成、发帖追踪、进化引擎、CLI/Web界面、多账号管理。这些是 v2 的范围。

**v2 启动关口（M2.5）**：v1 完成后，基于 backtesting 和留出验证的结果，决定是否进入 v2 开发。验证标准见模块B3。

---

### 模块A：数据采集引擎（Data Collector）`[v1]`

#### A1. Subreddit筛选与分层

核心理念：巨型subreddit（如 r/funny）和中小型niche subreddit（如 r/kubernetes）的爆款规律完全不同，用前者数据训练的方法论不适用于后者。按规模分层分析，分别提取规律。

| 层级 | 定义 | 数量 | 示例 |
|------|------|------|------|
| **T1 巨型** | 订阅 20M+，日均发帖 500+ | 5-8个 | r/funny, r/AskReddit, r/pics, r/gaming, r/worldnews |
| **T2 大型** | 订阅 1M-20M，日均发帖 100-500 | 8-12个 | r/productivity, r/Fitness, r/personalfinance, r/technology |
| **T3 中型** | 订阅 100K-1M，日均发帖 20-100 | 5-8个 | r/SaaS, r/kubernetes, r/digitalnomad, r/selfhosted |

| 参数 | 规则 |
|------|------|
| 采集范围 | 三层共计 20-25 个 subreddit，覆盖不同规模的内容生态 |
| 活跃度数据源 | Reddit API `/subreddits/popular` + subredditstats.com 交叉验证 |
| 动态更新 | 每月重新评估，替换活跃度下降的 subreddit |
| 分层用途 | 分析时按层级分别提取规律，使用时根据目标 subreddit 层级匹配对应方法论 |
| 存储格式 | `subreddit_meta.json`：名称、描述、订阅数、日均活跃度、内容类型标签（文本/图片/链接/视频）、层级标签（T1/T2/T3） |

#### A2. 帖子采集
| 参数 | 规则 |
|------|------|
| 每个subreddit | Top 500篇帖子（按upvotes排序） |
| 采集字段 | 标题、正文、作者、发布时间、upvotes、upvote_ratio、评论数、awards（按类型）、flair、标签、是否OC、是否NSFW、**内容类型**（text/image/video/link/poll）、**是否crosspost**（来源subreddit）、**upvotes增长曲线数据**（首小时/6h/24h增速） |
| 评论采样 | 每篇帖子Top 20评论（按upvotes）+ **Top 5最深子线程**（reply chain depth >= 3），用于分析"什么样的内容引发高质量深度讨论" |
| 时间窗口 | 近2年内（保证数据时效性） |
| 去重规则 | 同一帖子在多个subreddit出现时，保留upvotes最高的那个，**但记录crosspost来源用于跨subreddit传播分析** |
| 存储格式 | `posts/{subreddit}.jsonl`，每行一条帖子完整数据 |

#### A3. 数据采集技术方案

> ⚠️ **Reddit API政策重大变更（2025.11-2026.5）**
> - 2025年11月：关闭自助创建App，新建App需手动审批（[Developer Support表单](https://support.reddithelp.com/hc/en-us/requests/new?ticket_form_id=14868593862164)）
> - 2026年3月：所有API请求必须带OAuth token，匿名访问全面禁止
> - 2026年5月：新内容政策明确"公开≠可自由使用"，批量采集需授权，商业化用途需许可
> - Token有效期仅10分钟，需自动刷新循环
> - 来源：[n8n文档更新](https://github.com/n8n-io/n8n-docs/pull/4510)、[LavX报道](https://news.lavx.hu/article/reddit-tightens-api-access-developer-tokens-now-required-for-all-requests)、[GeekChamp政策解读](https://geekchamp.com/reddit-releases-new-content-policy-locking-public-data/)

```
采集策略：三路并行，按优先级递进

=== 方案1（优先）：官方API（需审批） ===
前置条件：提交Developer Support申请，说明用途为"personal research for content pattern analysis"
- 审批周期：未知（社区反馈48-72小时到数周不等）
- 获批后用PRAW采集，token自动刷新
- 速率限制：100 requests/min（OAuth认证用户）
- 10,000篇帖子 + 200,000条评论，预估5-7天
- ⚠️ 申请时不能提商业化，审批通过后再说
- ⚠️ 采集量可能触发Reddit的异常检测，需分批+加延迟

=== 方案2（并行）：第三方数据源 ===
数据源优先级：
1. Reddit Data Dump（Kaggle/学术界公开数据集）
   - 已有多个1M+帖子的历史数据集，免费
   - 推荐数据集：
     - **UCSD Reddit Submissions Dataset** — 覆盖2005-2023，字段最全，首选用
     - **Stanford SNAP Reddit Hyperlinks** — 含跨subreddit链接关系，用于传播分析
     - **Reddit r/TheRedditArchive** — 社区维护的历史存档
   - 缺点：时效性差（多数截止到2024），但方法论分析不需要最新数据
   - 优点：零API成本，立即可用，数据量大
2. Subreddit Stats (subredditstats.com)
   - 提供subreddit级别的帖子排名
   - 可获取Top帖子的标题/分数/评论数，无正文
   - 作为标题分析的补充数据源
3. Reddit Archive (reveddit.com, unddit.com)
   - 部分历史帖子缓存
   - 不稳定，仅作补充
4. Pushshift API
   - 2023年后大幅限制，但部分端点仍可用
   - 学术研究可申请扩容访问

=== 方案3（兜底）：Browser Use + 搜索引擎 ===
- 用Browser Use自动化浏览Reddit网页版
- 速度慢（每篇帖子需5-10秒），仅用于补关键数据
- 搜索引擎缓存：site:reddit.com + 关键词可获取部分帖子
- 配合mobile_use（Reddit App）获取移动端独有数据
- ⚠️ 高频访问可能触发反爬，需模拟人类行为（随机延迟、滚动模式）

=== 推荐执行路径 ===
Step 1: 立即提交API审批申请（方案1）
Step 2: 同时下载Kaggle历史数据集，先跑通分析流程（方案2）
Step 3: 用历史数据完成爆款模式提取，API获批后补充最新数据
Step 4: Browser Use补齐数据缺口（方案3）
→ 即使API审批不通过，历史数据集+第三方源足够完成v1的方法论提取
```

---

### 模块B：爆款分析引擎（Viral Analyzer）`[v1]`

#### B1. 多维度分析框架

**标题分析：**
| 维度 | 分析项 | 产出 |
|------|--------|------|
| 长度 | 字符数、单词数分布 | 最优标题长度区间 |
| 结构 | 是否用冒号/破折号/括号/数字/问号 | 高爆款率标题结构模板 |
| 情绪 | 情绪极性（正/负/中性）+ 情绪强度 | 情绪与爆款率的相关性 |
| 钩子类型 | 反常识/悬念/痛点/身份/数字冲击/故事开头 | 各钩子类型的平均upvotes |
| 关键词 | 高频词/短语/大写词 | 按subreddit分类的标题关键词库 |
| 时效性 | 是否包含时间词（today/just/finally/finally） | 时效性词汇对爆款的增益 |

**正文分析：**
| 维度 | 分析项 | 产出 |
|------|--------|------|
| 长度 | 字数分布 vs 爆款率 | 各subreddit的最优字数区间 |
| 结构 | 段落数、列表占比、是否用TL;DR、是否有加粗/引用 | 结构模板 |
| 叙事模式 | 故事型/教程型/观点型/提问型/资源分享型 | 各模式的爆款率对比 |
| 开头模式 | 首段是否设置钩子/背景/冲突 | 开头写法模板 |
| 互动引导 | 是否在结尾提问/引导讨论 | 互动引导对评论数的影响 |
| 可读性 | Flesch-Kincaid分数、平均句长 | 可读性与爆款率的关系 |

**元数据分析：**
| 维度 | 分析项 | 产出 |
|------|--------|------|
| 发布时间 | 星期几 + 小时 vs upvotes | 最佳发布时间矩阵 |
| 作者画像 | karma/账号年龄/发帖频率 vs 爆款率 | 作者因素权重 |
| Subreddit特性 | 不同subreddit对标题/正文长度的偏好差异 | 分subreddit的定制规则 |
| Flair | 是否使用flair + flair类型 vs 爆款率 | Flair使用建议 |
| 首小时表现 | 前1小时upvotes增速 vs 最终upvotes | 早期信号预测模型 |
| 争议度 | upvote_ratio 低但评论数高的帖子特征 | "高讨论度"帖子的价值评估 |

**视觉内容分析（图片/视频帖专项）：**
| 维度 | 分析项 | 产出 |
|------|--------|------|
| 内容类型分布 | text/image/video/link 各类型的爆款率 | 各subreddit的内容形式偏好 |
| 图文配合 | 标题+图片的协同模式（screenshot/infographic/meme/photo） | 不同图片类型的标题策略 |
| 纯文本 vs 富媒体 | 同主题下纯文本帖和图片帖的表现差异 | 内容形式的ROI对比 |

**帖子生命周期与传播分析：**
| 维度 | 分析项 | 产出 |
|------|--------|------|
| 增长曲线 | upvotes增长曲线形态（对数型/指数型/脉冲型） | 算法推流时机推断 |
| 跨subreddit传播 | crosspost来源和目标subreddit的映射 | 什么内容容易被跨版转发 |
| 传播链 | 同一内容在多个subreddit出现的时间顺序 | 传播路径和引爆点 |

#### B2. 爆款模式归纳

从10,000篇帖子中提炼出**有限数量的爆款模式**（预估5-8种）：

```
模式示例（待数据验证）：
1. "I just discovered X, and it changed everything" — 反常识发现型
2. "After 10 years of X, here's what nobody tells you" — 资深揭秘型
3. "PSA: X is happening and you need to know" — 紧急通知型
4. "[Resource] I built X to solve Y" — 工具分享型
5. "Unpopular opinion: X" — 争议观点型
6. "My X journey: from Y to Z" — 故事成长型
7. "ELI5: Why does X happen?" — 好奇提问型
8. "X vs Y: A comprehensive comparison" — 对比分析型
```

每种模式输出：
- 适用subreddit列表（按层级标注）
- 标题模板（含变量占位符）
- 正文结构模板
- 历史爆款率 + 置信区间
- 典型案例（3-5篇）
- **统计显著性**（p值，验证该模式是否显著优于随机）

#### B3. 内部验证体系（v1 关键模块）

v1 不发帖，因此必须在分析阶段内部验证方法论的可靠性。两种验证互补：

**Backtesting（时间切分验证）：**
```
方法：
1. 数据集按时间切分：训练集（2023年数据）→ 提取爆款模式
2. 测试集（2024年数据）→ 用提取的模式去"预测"哪些帖子会爆
3. 计算：召回率（实际爆款中我们预测到了多少）、精确率（我们预测爆款的中有多少真爆了）
4. 验收标准：召回率 > 60% 且 精确率 > 40%（爆款预测本身是低概率事件，40%精确率已经远超随机）
```

**留出验证（Subreddit Holdout）：**
```
方法：
1. 20-25个subreddit中随机留出3-4个不参与模式提取
2. 用其他subreddit提取的方法论去套这3-4个"未见过的"subreddit
3. 看方法论在未见过的subreddit上的表现
4. 验收标准：留出subreddit的预测精确率不低于训练subreddit的70%
```

**分层验证：**
- 以上两种验证分别在 T1/T2/T3 层级内独立进行
- 输出"方法论迁移能力报告"：哪些规律是跨层级通用的，哪些是层级特有的

#### B4. 分析引擎输出物
```
./Reddit爆款引擎/分析报告/
├── 总览报告.md              # 全局发现、关键结论、方法论迁移能力（跨层级/跨subreddit）
├── 标题方法论.md            # 标题写法规则 + 模板库 + 分布图数据（含拐点分析）
├── 正文方法论.md            # 正文写法规则 + 结构模板
├── 爆款模式库.md            # 5-8种爆款模式的完整定义（含统计显著性）
├── 反模式库.md              # 明确无效的做法、常见踩坑点
├── subreddit画像/           # 每个subreddit的定制规则 + 特异度评分（偏离通用模式的程度）
│   ├── r-funny.md
│   ├── r-AskReddit.md
│   └── ...
├── 时间矩阵.md              # 最佳发帖时间
├── 验证报告.md              # Backtesting + 留出验证结果（召回率/精确率/分层表现）
└── 数据集/                  # 原始+清洗后的结构化数据
    ├── posts_all.jsonl
    ├── comments_sample.jsonl
    └── subreddit_meta.json
```

---

### 模块C：帖子生成引擎（Post Generator）`[v2]`

> ⚠️ 此模块为 v2 范围，v1 不做。以下内容为前瞻设计，v2 启动前需重新评估。

#### C1. 输入
| 输入类型 | 示例 | 处理逻辑 |
|----------|------|----------|
| 关键词 | "productivity", "AI tools" | 匹配最相关的subreddit + 爆款模式 |
| Subreddit域名 | r/productivity | 直接使用该subreddit的定制规则 + 通用爆款模式 |
| 主题描述 | "我想分享一个帮我省了3小时的自动化脚本" | 提取关键要素，匹配最佳模式 |

#### C2. 生成流程
```
输入 → 1.Subreddit匹配（关键词→最相关subreddit）
     → 2.爆款模式选择（基于subreddit+主题，选最合适的1-3种模式）
     → 3.标题生成（按模式模板 + subreddit定制规则，生成3个候选标题）
     → 4.正文生成（按模式的结构模板 + 字数/可读性约束）
     → 5.元数据建议（发布时间、flair、是否OC标签）
     → 6.自检（标题长度/情绪/钩子评分，正文可读性/互动引导评分）
     → 输出
```

#### C3. 输出格式
```markdown
# 生成结果

## 推荐Subreddit
r/productivity (匹配度 92%) | r/getdisciplined (78%) | r/productivitycafe (65%)

## 候选标题（3个）
1. [分数: 87] I automated 3 hours of my daily workflow with one script — here's the breakdown
2. [分数: 82] After months of manual work, I finally built something that saves me 3 hours every day
3. [分数: 79] [Resource] This one script replaced 3 hours of my daily routine (open source)

## 正文
...

## 元数据建议
- 推荐发布时间：周二 9:00 EST
- 推荐Flair：Resource / Tool
- 标记OC：是
- 预估upvotes中位数：800-1500（基于历史模式）

## 自检报告
- 标题长度：18词 ✅ (该subreddit最优区间 12-22词)
- 钩子类型：反常识发现 ✅
- 正文字数：340词 ✅ (该subreddit最优区间 200-500词)
- 互动引导：结尾提问 ✅
- 可读性分数：72 ✅
```

---

### 模块D：效果追踪与自我进化（Evolution Engine）`[v2]`

> ⚠️ 此模块为 v2 范围，v1 不做。以下内容为前瞻设计，v2 启动前需重新评估。

#### D1. 发帖效果追踪
| 指标 | 采集时间 | 数据源 |
|------|----------|--------|
| upvotes | 发帖后1h/6h/24h/72h | Reddit API |
| 评论数 | 同上 | Reddit API |
| upvote_ratio | 同上 | Reddit API |
| awards | 同上 | Reddit API |
| 首小时upvotes增速 | 1h | 自动计算 |

#### D2. 效果判定标准
```
爆款判定（按subreddit中位数倍数）：
- 超级爆款：upvotes > 中位数 × 10
- 爆款：upvotes > 中位数 × 3
- 及格：upvotes > 中位数 × 1.5
- 失败：upvotes < 中位数 × 1.5
```

#### D3. 失败归因
当帖子被判定为"失败"时，自动分析原因：
```
归因维度：
1. 标题问题：长度偏长/偏短？钩子类型不匹配？情绪方向错误？
2. 正文问题：字数偏多/偏少？结构不对？可读性差？
3. 发布时间：是否偏离最佳时间？
4. Subreddit匹配：关键词与subreddit的匹配度是否偏低？
5. 竞争环境：同时间段是否有类似爆款帖子抢了注意力？
6. 话题时效性：是否错过了话题热度窗口？
```

#### D4. 自我进化机制
```
进化动作：
- 每条发帖记录存入 feedback.jsonl
- 每50条记录触发一次模型微调：
  - 更新标题/正文方法论中的权重参数
  - 更新爆款模式的成功率
  - 发现新模式（之前未归纳的爆款结构）
  - 淘汰失效模式（连续10次失败的模式降权）
- 进化日志保存到 evolution_log.md
```

---

## 四、技术架构

### 4.1 技术栈
```
数据层：   Python + PRAW + Kaggle数据集 + SQLite/JSONL（v1）
分析层：   Python (pandas/nltk/spaCy/textstat) + LLM API（DeepSeek/Claude）
           → nltk 负责基础文本处理，spaCy 负责句法分析（从句结构、被动语态比例等）
生成层：   LLM API + 结构化prompt模板
追踪层：   Python + PRAW + 定时任务（cron）
进化层：   Python + 规则引擎 + LLM辅助归因
界面层：   v1 CLI → v2 Web界面 → v3 API服务
```

### 4.2 目录结构

```
./Reddit爆款引擎/
├── PRD.md                    # 本文档
├── config.yaml               # 配置（API keys、采集参数）
├── src/
│   ├── collector/            # 数据采集模块 [v1]
│   │   ├── kaggle_loader.py      # Kaggle历史数据集加载
│   │   ├── praw_collector.py     # Reddit API采集（需审批后使用）
│   │   ├── thirdparty_scraper.py # 第三方源（Subreddit Stats等）
│   │   └── browser_collector.py  # Browser Use兜底采集
│   ├── analyzer/             # 爆款分析模块 [v1]
│   │   ├── title_analyzer.py
│   │   ├── content_analyzer.py
│   │   ├── meta_analyzer.py
│   │   ├── pattern_extractor.py
│   │   └── report_generator.py
│   └── validator/            # 内部验证模块 [v1]
│       ├── backtester.py         # 时间切分验证
│       └── holdout_validator.py  # 留出验证
├── data/
│   ├── raw/                  # 原始采集数据
│   ├── processed/            # 清洗后数据
│   └── patterns/             # 爆款模式库
├── 分析报告/                  # v1 核心交付物
└── logs/                     # 运行日志
```

> **v2 扩展**：`src/generator/`、`src/tracker/`、`src/evolution/`、`templates/` 目录在 v2 阶段加入。

### 4.3 关键技术决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 数据采集 | Kaggle优先→API补充→Browser兜底 | API审批不确定，历史数据集立即可用，爆款方法论不依赖最新数据 |
| 数据存储 | JSONL + SQLite | v1轻量够用，JSONL便于追加和版本控制，SQLite便于查询 |
| NLP分析 | nltk + textstat + LLM | 统计指标用本地库（快+免费），语义分析用LLM（准） |
| 帖子生成 | LLM + 结构化模板 | 纯LLM生成不可控，模板+LLM保证结构和创意兼顾 |
| 进化方式 | 规则引擎 + LLM辅助 | 不急着上ML模型，先用规则+LLM归因，数据量够再考虑微调 |
| 界面 | v1 无界面（纯脚本+报告） → v2 CLI/Web | v1 交付物是方法论文档，不需要界面；v2 再做CLI或Web |
| API合规 | 先研究用途申请，后期正式授权 | 自用阶段以研究名义申请，SaaS化前获取商业授权 |

---

## 五、数据合规与风控

### 5.1 Reddit API合规
- 严格遵守Reddit API使用条款，每分钟不超过60次请求
- 采集数据仅用于分析，不原文搬运
- 用户生成的内容版权归作者所有，商业化时需注意数据脱敏

### 5.2 发帖风控
- 禁止生成垃圾/重复/钓鱼内容
- 遵守各subreddit的规则（sidebar rules）
- 同一subreddit每日发帖不超过1条
- 生成内容必须包含真实有价值的信息，不允许纯标题党

### 5.3 商业化数据脱敏
- 帖子原文不直接作为产品数据出售
- 输出的是"模式、方法论、模板"，不是具体帖子内容
- 用户画像数据加密存储，不关联Reddit账号

---

## 六、商业化路径

### 6.1 三阶段规划

**Phase 1 — 自用验证（0-3个月）**
- 跑通完整链路：采集→分析→生成→追踪→进化
- 积累100+条发帖记录，验证爆款率
- 打磨方法论，形成可复用的知识库
- 成本：API费用约$50/月（Reddit API免费，LLM API为主）

**Phase 2 — 内测SaaS（3-6个月）**
- Web界面，支持用户注册
- 按subreddit/关键词生成帖子
- 基础版免费（每月5次生成），Pro版$29/月（无限生成+追踪）
- 积累用户发帖数据，反哺进化引擎

**Phase 3 — API+企业版（6-12个月）**
- 开放API，接入第三方营销工具
- 企业版：多账号管理、团队协作、品牌级内容策略
- 定价：API $0.1/次调用，企业版 $299/月起
- 数据飞轮：用户越多 → 发帖数据越多 → 模型越准 → 用户越多

### 6.2 竞品分析
| 竞品 | 定位 | 差异 |
|------|------|------|
| Subreddit Stats | 数据展示 | 只看不做，没有创作指导 |
| Reddit Post Inspector | 单帖分析 | 没有全量数据，没有生成能力 |
| Later for Reddit | 发帖时间优化 | 只解决"何时发"，不解决"发什么"和"怎么写" |
| GPT直接生成 | 通用AI写作 | 没有Reddit爆款数据支撑，生成内容不接地气 |

**我们的差异化**：唯一一个从10,000+真实爆款帖子中提炼方法论 → 生成 → 追踪 → 进化的闭环系统。

---

## 七、里程碑

### v1 里程碑（研究期）

| 阶段 | 交付物 | 时间 | 验收标准 |
|------|--------|------|----------|
| M0 | API申请+数据源就绪 | 第1周 | API审批已提交；UCSD + Stanford SNAP 数据集已下载并加载到SQLite |
| M1 | 数据采集完成 | 第2-3周 | 20-25个subreddit（T1/T2/T3三层）× 500篇帖子 + 评论全部入库（Kaggle为主，API补充） |
| M2 | 爆款分析报告 | 第4-5周 | 标题/正文/元数据方法论文档 + 5-8种爆款模式 + 反模式库 + subreddit画像 |
| M3 | 内部验证完成 | 第5周 | Backtesting召回率>60% 且 精确率>40%；留出验证精确率不低于训练集70% |

### 🚦 M2.5 关口：v1 结束，v2 启动决策

| 决策点 | 条件 | 行动 |
|--------|------|------|
| ✅ 通过 | M3 验证标准全部达标 | 进入 v2 开发（模块C + 模块D + Web界面） |
| ⚠️ 有条件通过 | 部分达标，但关键维度（标题/正文）达标 | 修复未达标维度，2周后复验 |
| ❌ 搁置 | 核心指标（精确率）未达标 | 重新评估方法论，不投入 v2 工程开发 |

### v2 里程碑（行动期，前瞻）

| 阶段 | 交付物 | 时间 | 验收标准 |
|------|--------|------|----------|
| M4 | 生成引擎MVP | 关口通过后2-3周 | 输入关键词 → 输出3个标题+正文+元数据建议 |
| M5 | 追踪+进化 | 关口通过后4-5周 | 发帖后72h自动追踪，失败自动归因，50条记录后触发进化 |
| M6 | 自用验证 | 关口通过后8周 | 100条发帖记录，爆款率>30% |
| M7 | Web界面 | 关口通过后12周 | 可注册、可生成、可追踪的Web产品 |

---

## 八、风险与应对

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| Reddit API审批不通过 | 中 | 高 | Kaggle历史数据集可独立完成v1，不依赖API |
| API获批但采集量触发限制 | 中 | 中 | 分批采集，加随机延迟，模拟人类行为模式 |
| Reddit 2026内容政策收紧 | 高 | 中 | 采集分析属于研究范畴，不直接转售数据；商业化时输出方法论而非原始内容 |
| 爆款规律难以量化 | 中 | 中 | 降低对"精确预测"的期望，侧重"显著提升概率" |
| 生成内容被社区标记为spam | 低 | 高 | 严格风控规则；生成内容必须包含真实价值 |
| LLM生成同质化 | 中 | 中 | 模板+LLM混合策略；进化引擎持续差异化 |
| Reddit封号 | 低 | 高 | 养号策略；不同subreddit用不同号；遵守频率限制 |
| Kaggle数据集时效性不足 | 低 | 低 | 爆款方法论跨年有效，API获批后补充最新数据验证 |

---

## 九、下一步行动（v1）

1. **今天**：确认 PRD v1.1，提交 Reddit API 审批申请
2. **今天**：下载 UCSD Reddit Submissions Dataset + Stanford SNAP Reddit Hyperlinks
3. **明天**：Kaggle 数据加载到 SQLite，选 3 个 subreddit（T1/T2/T3 各一）跑通分析流程
4. **本周**：完成全量数据采集+清洗，启动分析引擎
5. **下周**：输出第一版爆款方法论 + 启动 backtesting 验证
6. **第5周**：M2.5 关口评审，决定是否进入 v2
