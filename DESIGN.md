# Design System — KarmaForge

## Product Context
- **What this is:** KarmaForge — Reddit 增长副驾驶。独立开发者的一键生成+发布+追踪 Reddit 内容工具。
- **Who it's for:** 独立开发者/Indie Hacker 在 Reddit 上做产品增长。
- **Space/industry:** 开发者工具 / Reddit 营销。
- **Project type:** Web App (SaaS Dashboard, FastAPI + React)。

## Aesthetic Direction
- **Direction:** 工业精确 (Industrial Precision) — 像瑞士手表，每个像素都有目的。冷静、可读、数据为第一公民。
- **Decoration level:** Minimal — 排版做所有的工作。无渐变、无 blur、无材质效果。
- **Mood:** 这不是一个营销工具。这是一个用数据说话的工程师战略副驾驶。每一个绿色数字都是增长信号。
- **Memorable thing:** 数据驱动的增长副驾驶。

## Typography
- **Display/Headings:** Inter (Google Fonts) — 600-700 weight, -0.4px to -1.2px letter-spacing。开发者最熟悉的 sans-serif，不需要额外的字体适应成本。
- **Body/UI:** Inter — 400-500 weight。14px primary reading size。
- **Data/Metrics:** JetBrains Mono (Google Fonts) — tabular-nums 天然对齐数字列。
- **Loading:** Google Fonts CDN (`fonts.googleapis.com`)。
- **Scale:**
  | Level | Size | Weight | Letter-spacing | Usage |
  |-------|------|--------|---------------|-------|
  | Heading XL | 28px | 700 | -0.8px | Page titles |
  | Heading L | 22px | 600 | -0.4px | Section headers |
  | Heading M | 18px | 600 | -0.2px | Card headers |
  | Body | 14px | 400 | 0 | Primary reading |
  | Caption | 12px | 400 | 0 | Metadata, timestamps |
  | Metric | 28px | 700 | -0.5px | Dashboard numbers (mono) |

## Color
- **Approach:** Restrained — 1 个强调色 + 中性色系统。颜色稀缺 = 有意义。
- **Color space:** OKLCH-derived (Tailwind v4 compatible).
- **Primary accent:** `#00C48C` — 青绿色，代表增长、upvotes、数据上升。刻意避开紫色/蓝色（每个开发者工具都在用的颜色）。
- **Palette:**
  | Token | Hex | Usage |
  |-------|-----|-------|
  | `--base` | `#0D0D0F` | Deepest background (off-black, warm tint) |
  | `--surface-1` | `#141417` | Cards, sidebar |
  | `--surface-2` | `#1A1A1F` | Elevated surfaces, hover states |
  | `--surface-3` | `#212128` | Highest elevation |
  | `--border` | `#2A2A30` | 1px hairline borders |
  | `--border-hover` | `#3A3A42` | Interactive border states |
  | `--text-primary` | `#EBEBEC` | Headings, body (off-white, never pure white) |
  | `--text-secondary` | `#8E8E98` | Secondary information |
  | `--text-muted` | `#5C5C66` | Tertiary, placeholders, disabled |
  | `--accent` | `#00C48C` | Primary actions, selected states, growth indicators |
  | `--accent-hover` | `#00E6A6` | Hover/active accent states |
  | `--accent-muted` | `rgba(0,196,140,0.12)` | Focus rings, subtle accent backgrounds |
- **Semantic:**
  | Token | Hex | Usage |
  |-------|-----|-------|
  | `--success` | `#00C48C` | Live posts, positive trends |
  | `--warning` | `#F5A623` | Pending, attention needed |
  | `--error` | `#E5484D` | Removed posts, destructive actions |
  | `--info` | `#5B9BD5` | Informational states |
- **Dark mode:** Dark-first (default). All tokens above are for dark mode.

## Spacing
- **Base unit:** 4px
- **Density:** Comfortable — 适合数据密集型仪表盘，但不拥挤。
- **Scale:**
  | Token | Value | Usage |
  |-------|-------|-------|
  | `xs` | 4px | Icon gaps, inline spacing |
  | `sm` | 8px | Button padding, card gaps |
  | `md` | 16px | Section gaps, card padding |
  | `lg` | 24px | Container padding |
  | `xl` | 32px | Page section gaps |
  | `2xl` | 48px | Major section dividers |

## Layout
- **Approach:** Grid-disciplined — 严格列对齐，关键指标可跨列强调。
- **Navigation:** 左侧边栏 (220px 固定) + 主内容区。
- **Max content width:** 1280px (主内容区)。
- **Grid:** 12 列，16px gutter，响应式断点。
- **Border radius:** 层级化 — 卡片 8px (`--radius-lg`), 按钮/输入框 6px (`--radius-md`), 小标签 4px (`--radius-sm`)。无泡泡圆角。

## Motion
- **Approach:** Minimal-functional — 仅有助于理解的过渡。
- **Easing:** enter: `ease-out`, exit: `ease-in`, move: `ease-in-out`.
- **Duration:** micro: 100-150ms, short: 150-250ms, medium: 250-400ms.
- **No:** 滚动驱动动画、装饰性运动、入场编排。

## Component Patterns
- **Cards:** `--surface-1` 背景 + `--border` 1px 边框 + `--radius-lg` 圆角。卡片只在意卡片即交互时使用。
- **Buttons:** 三种变体：Primary (`--accent` 背景 + `--base` 文字)、Secondary (`--surface-2` 背景 + `--text-primary` 文字 + 边框)、Ghost（透明背景 + `--text-secondary` 文字）。
- **Form inputs:** `--surface-2` 背景 + `--border` 1px 边框。Focus: `--accent` 边框 + `--accent-muted` box-shadow ring（2px）。
- **Badges:** Semi-transparent 背景 (`rgba(color, 0.15)`) + solid 文字。Round-full 胶囊形。
- **Data tables:** `--surface-2` header row + 1px `--border` 分隔。数字列用 JetBrains Mono tabular-nums。
- **Metric cards:** 大号 JetBrains Mono 数字 (28px/700) + Inter 标签。绿色 delta = 正面趋势，红色 = 负面。

## AI Slop Mitigation
- **禁止：** 紫色渐变、3 列图标网格、全居中布局、泡泡圆角、装饰 blob、emoji 图标、system-ui 字体栈。
- **分类：** APP UI — 应用 Calm surface hierarchy 规则。工作区驱动，数据密集，任务导向。
- **Typeface discipline:** 只用 Inter + JetBrains Mono。不引入第三种字体。
- **Cards earn existence:** 每个卡片必须有交互目的，不为了「好看」而放卡片。

## Decisions Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-05-28 | Initial design system created | Created by /design-consultation. Green accent to differentiate from purple-dominated dev tool landscape. Inter + JetBrains Mono for developer familiarity. Dark-first, industrial precision aesthetic. |
| 2026-05-28 | Generator-first layout | Approved in /plan-design-review. Dashboard prioritizes content generation as primary action. |
| 2026-05-28 | Full responsive | Approved in /plan-design-review. Mobile supports complete generate+tracking flow. |
