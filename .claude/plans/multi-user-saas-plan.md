# KarmaForge 多用户 SaaS 架构规划

## 一、现状评估

### 已具备的 SaaS 基础
项目意外地已经拥有大量多用户基础设施：

| 组件 | 状态 | 说明 |
|------|------|------|
| FastAPI 后端 | ✅ 已就绪 | JWT auth + User/Generation/Feedback 模型，已多租户 |
| React 前端 | ✅ 已就绪 | Vite 8 + React 19 + TypeScript 6 + Tailwind 4，Login/Dashboard/History |
| 用户认证 | ✅ 已就绪 | 注册/登录/JWT，bcrypt 密码哈希 |
| LLM 客户端 | ✅ 已就绪 | DeepSeek API（OpenAI 兼容），含缓存+重试+计费估算 |
| 生成管线 | ✅ 已就绪 | 标题+正文+自检+元数据，全管道可用 |
| 追踪系统 | ✅ 已就绪 | PostTracker + Feedback + Evolution |

### 缺失的 SaaS 核心

| 组件 | 状态 | 优先级 |
|------|------|--------|
| 订阅/付费系统 | ❌ 无 | P0 |
| 配额管理 | ❌ 无 | P0 |
| 生产数据库 (PostgreSQL) | ❌ 仍是 SQLite | P1 |
| Stripe 集成 | ❌ 无 | P0 |
| 计费监控 | ❌ 无 | P1 |
| Docker 部署 | ❌ 无 | P1 |
| 管理后台 | ❌ 无 | P2 |

---

## 二、成本分析：$5/月 能否不亏本？

### DeepSeek API 定价（按代码中实际定价）

```
输入: $0.14 / 1M tokens
输出: $0.28 / 1M tokens
```

### 单次生成 Token 消耗（实测估算）

| 操作 | LLM 调用次数 | 输入 Tokens | 输出 Tokens |
|------|-------------|-------------|-------------|
| 生成 3 个标题 | 3 次 | ~1,500 | ~150 |
| 生成正文 | 1 次 | ~800 | ~400 |
| **一次完整生成** | **4 次** | **~2,300** | **~550** |

### 单次生成成本

```
输入成本: 2,300 × $0.14 / 1,000,000 = $0.000322
输出成本:   550 × $0.28 / 1,000,000 = $0.000154
─────────────────────────────────────────
合计: $0.000476 ≈ $0.0005/次
```

加入安全余量（重试、SelfCheck LLM调用等）：**~$0.001/次完整生成**

### $5/月 盈亏平衡点

```
$5 / $0.001 = 5,000 次生成/月
```

### 典型用户行为预估

| 用户类型 | 日生成量 | 月生成量 | 月成本 | 月利润 |
|----------|---------|---------|--------|--------|
| 轻度用户 | 1-2 | 30-60 | $0.03-0.06 | $4.94 |
| 中度用户 | 3-5 | 90-150 | $0.09-0.15 | $4.85 |
| 重度用户 | 10-15 | 300-450 | $0.30-0.45 | $4.55 |
| 超级用户 | 20-30 | 600-900 | $0.60-0.90 | $4.10 |

### 免费用户成本

```
免费额度: 20 次/月
单个免费用户月成本: ~$0.02
100 个免费用户: ~$2/月
1,000 个免费用户: ~$20/月
```

### 结论：**$5/月定价利润空间极健康（85-95% 毛利）**

即使 10 个免费用户转化 1 个付费用户，整体仍然盈利。

---

## 三、配额设计

### Free Tier（免费版）
- **月生成次数**: 20 次完整帖子生成
- **标题候选数**: 最多 3 个
- **历史记录**: 保留最近 30 天
- **Subreddit 匹配**: 基础版
- **标记**: "KarmaForge Free" 水印或标识

### Pro Tier（$5/月）
- **月生成次数**: 300 次完整帖子生成
- **标题候选数**: 最多 5 个
- **历史记录**: 永久保留
- **Subreddit 匹配**: 完整版（含 subreddit 画像）
- **AI 修改**: 无限次 Revise
- **数据导出**: CSV/JSON
- **优先支持**: Email 支持

### 为什么 300 次对 $5？
- 重度用户上限 ~450 次/月仍然远超配额，但这个数字让 95% 用户不会碰到上限
- 即使超级用户用满 300 次，成本也仅 ~$0.30
- 配额上限主要用于防止 API 滥用，不是成本考量

### 信息架构（每个屏幕的视觉层级）

**定价页面：**
```
┌─────────────────────────────────────────────┐
│  ZONE 1: 页面标题 + 副标题                      │
│  "选择你的计划" / "从免费开始，随时升级"            │
│  Inter 28px Bold, --text-primary             │
├─────────────────────────────────────────────┤
│  ZONE 2: 并列层级卡片                           │
│  ┌──────────────┐  ┌──────────────┐          │
│  │  FREE         │  │  PRO  $5/月   │          │
│  │  $0           │  │  --accent CTA │          │
│  │  20 代/月     │  │  300 代/月    │          │
│  │  3 个标题     │  │  5 个标题     │          │
│  │  [开始使用]    │  │  [升级到Pro]   │          │
│  └──────────────┘  └──────────────┘          │
│  --surface-1 bg, --border 1px, radius-lg 8px │
├─────────────────────────────────────────────┤
│  ZONE 3: 功能对比表                             │
│  细粒度功能对比，Pro列有绿色勾选标记                 │
│  --text-secondary, 14px Inter                │
└─────────────────────────────────────────────┘
```

**仪表盘配额栏（集成到现有生成标签页）：**
```
┌─ 仪表盘顶部栏（在生成器卡片上方）──────────────────┐
│  ZONE 1: 配额进度条 + 剩余次数                       │
│  "本月已使用 12/20 次生成" ████████░░░░░░░░          │
│  --surface-2 bg, JetBrains Mono 数字, --accent 进度条 │
│  ZONE 2: 升级提示（内联，非模态框）                      │
│  "需要更多？升级到Pro享受300次/月 →"                    │
│  仅在剩余次数 < 5 时显示                                │
└──────────────────────────────────────────────────┘
```

**升级提示（内联横幅，不是模态框）：**
```
┌─ 生成器卡片和标题网格之间的内联横幅 ───────────────┐
│  ⚡ 你已用完本月所有免费生成次数。                       │
│  [升级到 Pro — $5/月, 300 次生成]   [稍后决定]         │
│  --accent-muted bg, --accent 边框 2px 左侧           │
│  非阻断——用户可以关闭并继续浏览历史记录                    │
└──────────────────────────────────────────────────┘
```

**订阅管理页面：**
```
┌─────────────────────────────────────────────┐
│  ZONE 1: 当前计划状态                           │
│  "Pro 计划 · 活跃" 绿色徽章                      │
│  "自 2026-06-01 起 · 下期账单 2026-07-01"       │
│  JetBrains Mono 日期, Inter 标签               │
├─────────────────────────────────────────────┤
│  ZONE 2: 使用情况                               │
│  本月生成: 87/300 · 费用估算: $0.09             │
│  --surface-1 卡片, 大号指标数字                  │
├─────────────────────────────────────────────┤
│  ZONE 3: 操作                                   │
│  [管理计费 →] (Stripe 门户链接)                  │
│  [取消订阅] (幽灵按钮, --text-muted)             │
└─────────────────────────────────────────────┘
```

### 交互状态覆盖

| UI 功能 | 加载中 | 空 | 错误 | 成功 | 部分 |
|----------|--------|-----|------|------|------|
| 定价页面 | 卡片区域显示骨架屏（2个并排脉冲 320x400px） | 不适用（始终有数据） | Stripe 价格获取失败："无法加载定价。请刷新。" + [重试] 次要按钮 | 页面正常渲染 | 不适用 |
| 配额进度条 | 进度条 0% 宽度，平滑动画至实际值 | 新用户：显示"本月已使用 0/20 次生成", 进度条 0%，带有"开始你的第一次生成 →" CTA | 无法获取配额："—" 计数，进度条变灰，工具提示"暂时不可用" | 配额正常显示：剩余次数 < 5 时变为 --warning 琥珀色 | 边缘：恰好剩余 1 次 → 显示"还剩 1 次"并带有温和的警告脉冲 |
| 升级提示横幅（配额已耗尽） | 生成按钮替换为旋转图标 + "检查配额..." | 不适用（仅在配额 = 0 时出现） | Stripe 结账失败："升级暂时不可用。请稍后重试。" + [关闭] | [无——用户被重定向至 Stripe] | 不适用 |
| 升级提示横幅（剩余 < 5） | 不适用（内联，无网络调用） | 不适用 | 不适用 | 显示："还剩 3 次生成。需要更多？[升级 →]" | 当用户有 1-4 次剩余时显示 |
| Stripe 结账 | "正在重定向到 Stripe..." 加载旋转图标 + 覆盖层 | 不适用 | Stripe 会话创建失败：错误 toast "支付暂时不可用" + 横幅保持可见 | 重定向至 Stripe 托管结账页面 | 不适用 |
| 订阅管理页面 | 计划卡片显示骨架屏（标题 + 3 行文本脉冲） | 无订阅："你目前使用的是 Free 计划。需要更多？[查看 Pro →]" | 无法获取 Stripe 状态："计费信息暂时不可用" | 计划状态 + 使用情况正常显示 | 订阅已取消但未过期："Pro 将于 2026-07-01 到期" 带 --warning 徽章 |
| 注册引导 | "正在创建你的账户..." 加载旋转图标位于提交按钮上 | 不适用 | 注册失败：表单上方内联错误横幅（红色，具体信息："邮箱已被注册" / "密码需至少 8 个字符"） | 重定向至仪表盘，顶部 Toast："欢迎！你已获得 20 次免费生成。" 带 --success 绿色 | 不适用 |

每个状态描述的是用户**看到**的内容（不是后端行为），遵循 Krug 的自明性原则。除非加载状态可信地 < 200ms，否则不跳过加载状态。每个空状态都包含一个行动号召。错误消息使用具体语言——绝不出现"发生错误"。

### 用户旅程与情感弧线

```
  STEP | 用户操作                    | 用户感受         | 设计如何支持
  ─────|─────────────────────────────|──────────────────|──────────────────────────────────
  1    | 进入应用 (/)                 | "这看起来很专业"   | 深色模式, Inter排版, 清晰的生成器卡片
       |                             | (5秒 visceral)   | 作为第一视觉锚点。无品牌营销绒毛。
  ─────|─────────────────────────────|──────────────────|──────────────────────────────────
  2    | 首次生成                     | "哇, 这真的有效"    | 标题以交错动画出现。分数徽章提供
       |                             | (愉悦)           | 即时反馈。复制按钮让成功触手可及。
  ─────|─────────────────────────────|──────────────────|──────────────────────────────────
  3    | 查看配额栏 (剩余8/20)         | "我在获得价值"      | 进度条显示进展, 不是不足。
       |                             | (动力)           | JetBrains Mono 数字 = 可信。
       |                             |                  | 当 < 5 次剩余时温和提醒。
  ─────|─────────────────────────────|──────────────────|──────────────────────────────────
  4    | 达到配额限制 (20/20)          | "我还想要"         | 内联横幅 — 非阻断! — 让用户
       |                             | (动机, 不是挫败)   | 继续浏览。语气："你已用完免费配额
       |                             |                  | — 准备升级？" 而不是 "已达到限制。"
  ─────|─────────────────────────────|──────────────────|──────────────────────────────────
  5    | 点击"升级到Pro"               | "这值得 $5 吗？"    | Stripe结账 = 可信的第三方。
       |                             | (承诺)           | 在点击之前清晰显示价值支撑：
       |                             |                  | "300次生成 · 无限AI修改 · $5/月"
  ─────|─────────────────────────────|──────────────────|──────────────────────────────────
  6    | 升级后返回                    | "我做出了正确选择"    | Pro 徽章在仪表盘上可见。
       | — 继续生成                   | (信心)           | 配额现在显示 300 — 自由感。
       |                             |                  | 订阅管理让取消容易（信任）。
```

**时间范围设计 (Norman):** 5秒 visceral: 信任（排版, 深色模式, 无杂乱）。5分钟 behavioral: 生成 3 个标题 → 复制一个 → 编辑正文 → 满意且快速。5年 reflective: "KarmaForge 每次都更懂我的社区"（数据飞轮）。

**升级流程的情感设计：**
- 配额横幅**始终**将用户取得的成就（"你已生成 20 篇帖子"）置于限制之上
- "升级" 措辞暗示增长/解锁, 而不是 "购买" 或 "付费"
- Stripe 门户链接上始终可见 "管理订阅" — 关闭账户与开启账户同样容易 = 信任
- 如果取消, 无内疚的取消流程："你的Pro权限在6月30日前有效。感谢你的使用。"

### AI Slop 防护 — 实现约束

所有新的 UI 组件必须遵循这些硬约束（源自 DESIGN.md APP UI 分类）：

| 约束 | 规则 | 原因 |
|------|------|------|
| 排版 | Inter (标题+正文) + JetBrains Mono (数字/价格/配额)。永不使用 system-ui 或 -apple-system | AI slop #11 |
| 颜色 | `--accent` = `#00C48C` 仅用于 CTA + 增长指标。永不使用紫色/靛蓝渐变 | AI slop #1 |
| 布局 | 左对齐仪表盘。定价卡片：并排，非居中堆叠 | AI slop #4 |
| 卡片 | 1px `--border` (`#2A2A30`)，无发光，无阴影，`--radius-lg` (8px) 最大 | AI slop #5 |
| 图标 | Tabler/lucide 图标以 `--text-secondary` 颜色。永不使用彩色圆形背景中的图标 | AI slop #3 |
| 装饰 | 零装饰元素。无 blob、无波浪线、无 emoji 图标 | AI slop #6, #7 |
| 定价 | 价格数字：JetBrains Mono 28px/700。功能列表：Inter 14px/400。CTA：Inter 14px/600 | 开发者工具 = 数据优先 |
| 进度条 | `--surface-2` 轨道 + `--accent` 填充。永不使用渐变填充。无发光 | 工业精确 |
| 徽章 | 半透明背景 `rgba(color, 0.15)` + 实色文字。胶囊形 (`border-radius: 9999px`) | 来自 DESIGN.md |
| 空状态 | 永远不只是 "未找到项目。" — 始终包含上下文 + 操作 | Krug: 不要让我思考 |

**分类器：APP UI** (工作区驱动, 数据密集, 任务导向)。应用 Calm surface hierarchy 规则。定价页面是唯一例外——它遵循 landing-page-lite（清晰的价值支撑, 一个 CTA 组），但仍然遵循 APP UI 排版和颜色令牌。

### 响应式 & 无障碍

**断点行为：**

| 屏幕 | ≥1024px (桌面) | 640-1023px (平板) | <640px (移动) |
|------|---------------|-------------------|---------------|
| 定价页面 | 两张卡片并排 (各 400px 宽, 32px 间距) | 两张卡片并排 (弹性宽度, 16px 间距) | 卡片堆叠为单列, Pro 优先 (Pro 卡片在上, Free 在下), 全宽 |
| 配额进度条 | 全内容宽度, 标签在左 + 进度条在右 | 全内容宽度 | 进度条全宽, 标签堆叠在进度条上方 |
| 升级横幅 | 最大宽度 720px, 内联于生成器卡片和标题网格之间 | 全内容宽度 | 全宽, 按钮堆叠为纵向 |
| 订阅管理 | 两张卡片并排 (计划 + 使用情况) | 堆叠为单列 | 堆叠为单列, 按钮全宽 |

**无障碍要求：**

| 元素 | 要求 | 实现 |
|------|------|------|
| 配额进度条 | `role="progressbar"`, `aria-valuenow={used}`, `aria-valuemin="0"`, `aria-valuemax={limit}` | 自定义 `<div>` (非原生 `<progress>` —— 样式化自定义元素) |
| 升级按钮 | 最小触摸目标 44×44px, WCAG 2.1 AA | 所有交互元素的 `min-height: 44px; min-width: 44px` |
| 颜色对比度 | 文本与背景对比度 ≥ 4.5:1, 大型文本 ≥ 3:1 | `--text-primary` (#EBEBEC) 在 `--base` (#0D0D0F) 上 = 13.7:1 ✅ |
| 焦点指示器 | 所有交互元素上可见的焦点环 | `--accent-muted` box-shadow, 2px, 无 `outline: none` |
| 键盘导航 | Tab 顺序: 生成器 → 标题卡片 → CTA → 配额信息。Enter/Space 触发操作。 | 原生 Tab 顺序 + React 事件处理器 |
| 屏幕阅读器 | 定价卡片: 标题 (`h2`) + 价格 (`<strong>`) + 功能列表 (`<ul>`) | 语义 HTML, 无仅 div 布局 |
| 升级状态通知 | 付费升级成功/失败通过 aria-live 区域播报 | `<div aria-live="polite">` 挂载 Toast 消息 |

**移动端特定约束：**
- 定价页面上无横向滚动——卡片在 <640px 时必须堆叠
- 升级横幅上的 CTA 按钮在 <640px 时需全宽 (44px 高 最小)
- 配额进度条在 <640px 时保持 ≥ 200px 宽以保持可点击性
- 生成器输入在移动端获得 `inputmode="text"` 和 `autocapitalize="none"`

### 未解决的设计决策 → 已解决

| 决策 | 解决方案 |
|------|---------|
| "升级到Pro"入口点 | 侧边栏底部，现有导航项下方。免费用户：`#00C48C` 强调色文字 + "升级 →" 标签。Pro用户：无入口（替换为绿色 "Pro" 徽章） |
| 定价页面路由 | `/pricing` — 从侧边栏和升级横幅链接 |
| 配额用尽后的行为 | 非阻断——内联横幅，用户可以关闭。生成按钮禁用并带有提示："配额已用完"。关闭横幅 = 用户可以浏览历史记录但无法生成 |
| 免费用户水印 | 无视觉水印。过于惩罚性。相反，免费用户在侧边栏中看到微妙的 "Free 计划" 徽章（`--text-muted` 颜色），Pro用户看到 `--accent` "Pro" 徽章。让用户想要Pro徽章——社交证明 > 惩罚 |
| 移动端侧边栏 | 在 <768px 时折叠为汉堡菜单。升级入口：始终在底部可见（粘性，在导航列表之后） |

### 目标架构

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  React SPA  │────▶│  FastAPI      │────▶│  PostgreSQL │
│  (Vercel)   │     │  (Railway/   │     │  (Supabase/ │
│             │     │   Render)     │     │   Railway)  │
└─────────────┘     └──────┬───────┘     └─────────────┘
                           │
                    ┌──────┴───────┐
                    │  DeepSeek    │
                    │  API         │
                    └──────────────┘
                           │
                    ┌──────┴───────┐
                    │  Stripe      │
                    │  (Payments)  │
                    └──────────────┘
```

### 数据库迁移：SQLite → PostgreSQL

当前 SQLAlchemy 模型（`api/models.py`）已经写好了，换数据库只需改 `DATABASE_URL`：

```python
# 从
DATABASE_URL = "sqlite:///data/processed/karmaforge.db"
# 改为
DATABASE_URL = "postgresql://user:pass@host:5432/karmaforge"
```

### 新增模型

```python
class Subscription(Base):
    __tablename__ = "subscriptions"
    
    id: str (PK)
    user_id: str (FK → users.id)
    stripe_customer_id: str
    stripe_subscription_id: str
    plan: str  # "free" | "pro"
    status: str  # "active" | "canceled" | "past_due"
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool
    created_at: datetime

class Usage(Base):
    __tablename__ = "usage"
    
    id: str (PK)
    user_id: str (FK → users.id)
    period_start: datetime  # 月计费周期开始
    generations_used: int (default 0)
    titles_generated: int (default 0)
    tokens_input: int (default 0)
    tokens_output: int (default 0)
    cost_estimate: float (default 0.0)
```

### Stripe 集成方案

```
POST /api/billing/create-checkout  → 创建 Stripe Checkout Session
POST /api/billing/portal           → 创建 Customer Portal (管理订阅)
POST /api/webhooks/stripe          → Stripe Webhook 接收事件
GET  /api/billing/status           → 当前订阅状态
GET  /api/usage                    → 当前用量统计
```

核心逻辑：
1. 用户注册 → 自动创建 `free` 订阅
2. 用户升级 → Stripe Checkout → Webhook `checkout.session.completed` → 更新为 `pro`
3. 取消订阅 → Webhook `customer.subscription.deleted` → 降级为 `free`
4. 每次生成 → 检查配额 → 扣减 → 记录用量

### 配额中间件

```python
# FastAPI dependency
async def check_quota(user: User, session: Session) -> bool:
    usage = get_current_usage(user.id, session)
    plan = get_user_plan(user.id, session)
    limit = PLAN_LIMITS[plan]  # {"free": 20, "pro": 300}
    
    if usage.generations_used >= limit:
        raise HTTPException(402, "Quota exceeded. Upgrade to Pro.")
    return True
```

---

## 五、实施路线图

### Phase 1：数据库 + 订阅核心（3-5 天）
- [ ] 扩展 `api/models.py`：添加 Subscription + Usage 模型
- [ ] 写 Alembic migration 脚本
- [ ] 开发环境用 PostgreSQL（Docker）
- [ ] 配额系统 Middleware
- [ ] 用户注册时自动创建 free 订阅
- [ ] 每次 API 调用扣减配额

### Phase 2：Stripe 集成（2-3 天）
- [ ] Stripe SDK 安装配置
- [ ] Checkout Session 端点
- [ ] Customer Portal 端点
- [ ] Webhook 处理（subscription created/updated/deleted）
- [ ] 本地测试（Stripe CLI + webhook forwarding）

### Phase 3：前端升级（3-4 天）
- [ ] Pricing 页面（Free vs Pro 对比）
- [ ] Dashboard 显示剩余配额
- [ ] 配额用尽时的升级引导 UI
- [ ] Subscription 管理页面（查看/取消/重新订阅）
- [ ] 注册后引导流程（Onboarding）

### Phase 4：部署 + 运维（2-3 天）
- [ ] Docker Compose 生产配置
- [ ] PostgreSQL 实例（Railway / Supabase / Render）
- [ ] FastAPI 部署（Railway / Render）
- [ ] 前端部署（Vercel）
- [ ] 环境变量 + Secret 管理
- [ ] 监控 + 日志（Sentry + basic logging）

### Phase 5：打磨（2-3 天）
- [ ] 错误页面（402 Payment Required 等）
- [ ] Email 通知（欢迎邮件、配额警告、订阅到期）
- [ ] 管理后台（用户列表、用量统计、成本监控）
- [ ] 免费用户水印/标识

**总预估：12-18 天**

---

## 六、财务可行性总结

| 指标 | 数值 |
|------|------|
| 单价 | $5/月/用户 |
| 单用户月成本（重度） | ~$0.45 |
| 单用户月成本（平均） | ~$0.15 |
| 毛利率 | 91-97% |
| 盈亏平衡需要的付费用户 | ~3 个（覆盖服务器 $15/月） |
| 免费用户承载能力 | 1,000+ 免费用户成本仅 ~$20/月 |

### 风险提示
- **API 定价变化**: DeepSeek 若涨价，需相应调整配额或定价
- **滥用风险**: 需要加 rate limiting（如 1 req/s per user）
- **大规模后**: 可考虑自部署开源模型（如 DeepSeek 开源版）降本

---

## 七、关键决策待确认

1. **部署平台**: Railway ($5/月起) vs Render (免费层) vs 自建 VPS？
2. **PostgreSQL**: Supabase 免费层 (500MB) 是否够用？还是直接用 Railway PG？
3. **是否保留 Gradio 桌面版**: 建议保留为 "本地开发版"，线上版用 React 前端
4. **免费版是否需要信用卡**: 建议不需要，降低注册摩擦
5. **多语言支持**: 先只做英文（Reddit 用户为主），后续加中文

---

## 八、NOT in Scope（明确排除）

| 项目 | 理由 |
|------|------|
| Phase 1 验证（30+ 真实 Reddit 帖子） | 创始人决定跳过——直接 SaaS |
| Email 通知系统 | Phase 5，非核心计费路径 |
| 管理后台 | Phase 5，手动数据库查询在前 50 个用户时完全够用 |
| Gradio 桌面版迁移 | 保留为本地开发工具，不迁移 |
| 多语言支持 | 启动时仅英文 |
| LemonSqueezy/Paddle 作为 Stripe 替代方案 | 以 Stripe 起步；如需要可稍后添加 |
| 自部署 LLM（DeepSeek 开源版） | 扩展时的成本优化——不是 MVP |
| OAuth 登录（Google/GitHub） | 邮箱+密码在启动时够用 |
| 团队/工作区功能 | 单人创业者的 B2C 产品 |
| 自动发布到 Reddit（违反 ToS） | 故意排除——保持人工审核层 |
| CI/CD 流水线 | 在 Phase 4 的部署步骤中隐含——但未设计明确的流水线。待 Phase 4 开始时解决 |

## 九、现有成果（已存在，请勿重建）

| 现有代码 | 用途 | 计划处理方式 |
|----------|------|-------------|
| `api/models.py` — User, Generation, Feedback | 多租户数据模型 | ✅ 重用——添加 Subscription + Usage |
| `api/routes_auth.py` — JWT 注册/登录 | 用户认证 | ✅ 完全重用 |
| `api/deps.py` — get_db, get_current_user | DB session + auth 依赖 | ✅ 重用——添加 check_quota |
| `api/routes_generate.py` — titles, full, recheck | 生成端点 | ✅ 重用——包裹配额门控 |
| `api/routes_track.py` — track, history | 追踪端点 | ✅ 完全重用 |
| `llm/client.py` — DeepSeek 客户端 | LLM API 调用 | ✅ 重用——添加多密钥轮换 |
| `frontend/src/api.ts` — API 客户端 | 前端 ↔ 后端 | ✅ 重用——添加计费端点 |
| `frontend/src/pages/Login.tsx` — 认证 | 登录/注册 UI | ✅ 完全重用 |
| `frontend/src/pages/Dashboard.tsx` — 生成 | 核心生成 UI | ✅ 修改——添加配额显示 |
| `tests/api/test_auth.py` — 认证测试 | 现有测试基础设施 | ✅ 重用——遵循相同模式 |

## 十、审查中已解决的设计决策

| ID | 章节 | 决策 | 理由 |
|----|------|------|------|
| D3 | 架构 | JWT 密钥启动验证 | 硬编码的默认值 `dev-secret-change-me...` 是生产环境的安全风险 |
| D4 | 架构 | 多 API 密钥轮换 + 按用户速率限制 | 单个密钥爆炸半径影响所有用户 |
| D5 | 架构 | Stripe webhook 签名验证 | 防止通过伪造 webhook 事件免费升级 |
| D6 | 架构 | Alembic + 数据迁移脚本 | SQLite → PostgreSQL 不仅仅是更改 URL |
| D7 | 代码质量 | 从 Generation 表计算配额 | 消除计数器漂移风险（双重真相来源） |
| D8 | 代码质量 | Webhook 幂等性键存储 | Stripe 可以多次投递相同事件 |
| D9 | 测试 | 全面测试套件——所有新代码路径 | 新增代码路径 0% 覆盖——计费代码必须经过测试 |
| D10 | 性能 | 异步生成 + 轮询 | 同步 LLM 调用在 HTTP 请求期间阻塞 4-12 秒 |

## 十一、失败模式

| # | 代码路径 | 失败场景 | 测试？ | 错误处理？ | 用户可见？ |
|---|---------|---------|--------|-----------|-----------|
| F1 | Stripe webhook → DB 写入 | 处理 webhook 时 DB 断开 → 订阅状态不同步 | 需要测试 | 重试逻辑 + 幂等性 | 静默——订阅未激活 |
| F2 | 配额检查 → COUNT 查询 | DB 暂时不可用 → 配额检查失败 → 合法生成被阻止 | 需要测试 | 在少量 DB 错误时优雅降级 | 是——显示 "服务暂时不可用" |
| F3 | DeepSeek API 超时 | 在生成期间，4 个 API 调用中的第 3 个超时 → 生成部分失败 | 需要测试 | LLMClient 中已有重试逻辑；最多重试 3 次 | 是——"生成失败，请重试" |
| F4 | Stripe Checkout → 用户关闭浏览器 | 用户在 Stripe 托管页面上但未完成 → Pro 从未激活 | 需要测试 | 未完成的结账会话在 24 小时后过期 | 否——无状态变更，良性 |
| F5 | **关键**：JWT 密钥在生产环境中丢失（未设置） | 应用启动但使用硬编码密钥 → 攻击者可以伪造任何用户的令牌 | 需要测试 | 启动验证现已在范围内 | 是——所有用户账户被攻破 |

## 十二、Worktree 并行化

| 步骤 | 触及的模块 | 依赖于 |
|------|-----------|--------|
| P1 — 数据库模型 + 配额 | models/, deps/, routes_generate/ | — |
| P2 — Stripe 集成 | routes_billing/, webhooks/ | P1 |
| P3a — 前端计费 UI | frontend/src/pages/, frontend/src/api.ts | P2 |
| P3b — 前端配额 UI | frontend/src/pages/Dashboard.tsx | P1 |
| P4 — 部署 | Dockerfile, docker-compose.yml, alembic/ | P1, P2 |
| P5 — 打磨 | routes_auth.py, email/, admin/ | P2 |

**并行通道：**
- 通道 A：P1 → P2 → P3a（顺序，共享 billing 模块）
- 通道 B：P1 → P3b（在 P1 完成后独立——纯前端配额显示）
- 通道 C：P1 + P2 → P4（在 P1+P2 都完成后启动）

**执行顺序：** 启动 P1。P1 完成后，并行启动 P2 + P3b。P2 完成后，顺序启动 P3a。P1+P2 都完成后，启动 P4。P5 最后运行。

## 十三、实施任务

综合自本次审查的发现。每项任务都源自上述具体发现。

- [ ] **T1（P0，人工：~15 分钟 / CC：~5 分钟）** — deps.py — 添加 JWT 密钥启动验证
  - 来源：架构审查 — A1：硬编码的 JWT 默认值
  - 文件：`src/karmaforge/api/deps.py`
  - 验证：`pytest tests/api/test_auth.py -v`，手动：设置 `JWT_SECRET=""` 并确认启动被拒绝

- [ ] **T2（P1，人工：~2 小时 / CC：~30 分钟）** — llm/client.py、deps.py — 多 API 密钥轮换 + 按用户速率限制
  - 来源：架构审查 — A2：所有用户共享单个 API 密钥
  - 文件：`src/karmaforge/llm/client.py`、`src/karmaforge/api/deps.py`
  - 验证：测试多个并发用户不会触发单个密钥的速率限制

- [ ] **T3（P0，人工：~30 分钟 / CC：~10 分钟）** — routes_billing.py — Stripe webhook 签名验证
  - 来源：架构审查 — A3：webhook 签名缺失
  - 文件：`src/karmaforge/api/routes_billing.py`（新建）
  - 验证：使用无效签名测试 webhook → 400；有效签名 → 200

- [ ] **T4（P2，人工：~1.5 小时 / CC：~25 分钟）** — models.py、alembic/ — Alembic 迁移 + SQLite→PostgreSQL 数据脚本
  - 来源：架构审查 — A4：迁移路径未指定
  - 文件：`src/karmaforge/api/models.py`、`alembic/`（新建）
  - 验证：在 SQLite（开发环境）和 PostgreSQL（生产环境）上运行迁移

- [ ] **T5（P1，人工：~20 分钟 / CC：~5 分钟）** — webhooks/ — Webhook 幂等性（事件 ID 跟踪）
  - 来源：代码质量 — C2：Stripe webhook 可能重复投递
  - 文件：`src/karmaforge/api/routes_billing.py`
  - 验证：向 webhook 端点发送相同的事件两次 → 第二次是 200 no-op

- [ ] **T6（P1，人工：~2 天 / CC：~40 分钟）** — tests/ — 所有新代码路径的全面测试套件
  - 来源：测试 — D9：新增路径 0% 覆盖
  - 文件：`tests/api/test_billing.py`（新建）、`tests/api/test_quota.py`（新建）、`tests/api/test_subscription.py`（新建）
  - 验证：`pytest tests/ -v --cov=src/karmaforge/api --cov-report=term-missing`

- [ ] **T7（P1，人工：~3 小时 / CC：~45 分钟）** — routes_generate.py — 异步生成 + 轮询
  - 来源：性能 — P1：同步 LLM 调用阻塞 HTTP 请求
  - 文件：`src/karmaforge/api/routes_generate.py`、`src/karmaforge/api/routes_generate.py`（新状态端点）
  - 验证：POST 生成 → 立即 202 + generation_id → 轮询状态直到完成

- [ ] **T8（P0，人工：~30 分钟 / CC：~10 分钟）** — routes_generate.py — 配额中间件（从 Generation 表计算）
  - 来源：代码质量 — C1：Usage 计数器 vs Generation 记录的双重真相来源
  - 文件：`src/karmaforge/api/deps.py`、`src/karmaforge/api/routes_generate.py`
  - 验证：免费用户在 20/20 次生成时 → 402；Pro 用户在 300/300 次生成时 → 402

---

## 十四、审查完成摘要

- **Step 0：范围挑战** — 范围按原样接受（完整计划，跳过验证）
- **架构审查**：发现 4 个问题
- **代码质量审查**：发现 2 个问题
- **测试审查**：生成图表，发现 21 个缺口 → 全面测试套件
- **性能审查**：发现 1 个问题
- **NOT in scope**：已编写（11 项被推迟）
- **现有成果**：已编写（10 个现有组件被重用）
- **TODOS.md 更新**：0 项（通过审查的所有发现均已解决；无需推迟项）
- **失败模式**：发现 5 种失败模式，标记 1 项关键缺口（F5：JWT 密钥）
- **外部意见**：不可用（子代理 API 错误）
- **并行化**：3 个通道，2 个并行 / 1 个顺序
- **Lake 得分**：8/8 条建议选择了完整选项

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 1 | CLEAR (2026-05-28) | Design doc approved; Phase 1→2 gated |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | 8 issues found, all resolved |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Design Review | `/plan-design-review` | UI/UX gaps | 1 | CLEAR | score: 3/10 → 9/10, 8 decisions |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

**DESIGN REVIEW:** Initial 3/10 → Final 9/10. 8 design decisions resolved: info architecture for 4 new screens, interaction state table (7 features × 5 states), user journey storyboard (6 emotional steps), AI slop constraints (10 rules), DESIGN.md updated (progress bar component), responsive breakpoints + WCAG 2.1 AA a11y specs, 5 unresolved decisions resolved, upgrade entry point placed in sidebar.
**UNRESOLVED:** 0
**VERDICT: ENG + DESIGN CLEARED — ready to implement.** All P0 blockers addressed. 8 eng tasks + 8 design decisions codified in plan.
