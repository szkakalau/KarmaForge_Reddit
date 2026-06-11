import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, ArrowUp, MessageCircle, Check, CreditCard, Gift, Shield, Database, Microscope, Brain, Target, Hash, GitBranch } from 'lucide-react'
import { useLang } from '../i18n/LanguageContext'
import LangSwitch from '../components/LangSwitch'
import { trackPurchase, RD_EVENTS } from '../redditPixel'

const zh = {
  hero: {
    line1: '不是通用 AI 写作工具，',
    line2: '是 Reddit 爆款的逆向工程引擎',
    sub: '我们从 1,538 篇真实 Reddit 爆款帖子中提取了 8 种钩子类型、覆盖 16 个主流社区，用数据驱动的方式生成真正能在 Reddit 上活下来的内容。',
    cta: '免费开始',
    email_placeholder: '输入你的邮箱...',
    dashboard: '进入 Dashboard',
    pricing: '查看定价',
  },
  metrics: [
    { value: '1,538', label: '爆款帖子分析', icon: Database },
    { value: '8', label: '爆款钩子类型', icon: Hash },
    { value: '16', label: '社区覆盖', icon: GitBranch },
    { value: '41', label: '社区文化画像', icon: Microscope },
  ],
  methodology: {
    title: '方法论：不是 AI 写作，是数据蒸馏',
    steps: [
      {
        num: '01',
        title: '数据采集',
        desc: '从 Kaggle 和 Reddit API 抓取海量帖子数据，筛选 upvotes > 中位数 3 倍的爆款样本，覆盖 16 个主流 subreddit。',
      },
      {
        num: '02',
        title: '模式提取',
        desc: '对每个 subreddit 进行结构化分析——标题词数、正文长度、hook 类型、叙事模式、发布时间——提取可复制的爆款公式。',
      },
      {
        num: '03',
        title: '文化画像',
        desc: '为 41 个 subreddit 建立深度文化档案：社区偏好、语言风格、禁忌话题、发布时间窗口。不是泛化模型，是社区特化的。',
      },
      {
        num: '04',
        title: 'AI 生成',
        desc: '将爆款模式注入 DeepSeek 大模型，生成符合特定 subreddit 文化的标题和正文。每次生成都有自检报告，触发反模式自动警告。',
      },
      {
        num: '05',
        title: '自我进化',
        desc: '每篇帖子发布后追踪效果——upvotes、评论、存活率。失败案例自动归因到具体维度（标题/正文/时间），反馈数据更新模式权重。',
      },
    ],
  },
  patterns: {
    title: '8 种爆款钩子类型',
    sub: '每种钩子都来自真实爆款帖子的统计验证',
    list: [
      { name: '反直觉发现', en: 'Counterintuitive Discovery', rate: '26.2%', desc: '"I just discovered X..." — 挑战常识的意外发现' },
      { name: '好奇心问题', en: 'Curious Question', rate: '30.5%', desc: '"ELI5:" / "Why does X?" — 激发讨论的开放式问题' },
      { name: '痛点共鸣', en: 'Pain Point', rate: '33.7%', desc: '"The real problem with X..." — 戳中共同焦虑' },
      { name: '数字冲击', en: 'Number Shock', rate: '34.7%', desc: '"10 things I learned..." — 具体数字制造信息密度' },
      { name: '故事开场', en: 'Story Opener', rate: '54.6%', desc: '"My experience with X..." — 个人叙事建立信任' },
      { name: '争议观点', en: 'Controversial Opinion', rate: '25.8%', desc: '"Unpopular opinion:" — 引发站队讨论' },
      { name: '对比分析', en: 'Comparison Analysis', rate: '28.3%', desc: '"X vs Y" — 结构化对比满足决策需求' },
      { name: '悬念钩子', en: 'Suspense Mystery', rate: '31.2%', desc: '"What nobody tells you about X" — 制造信息差' },
    ],
  },
  cta: {
    title: '准备好让你的 Reddit 帖子被顶上去？',
    sub: '免费开始，每月 20 次生成。随时升级到 Pro。',
    button: '免费注册',
    dashboard: '进入 Dashboard',
  },
  anti: {
    title: '5 种反模式检测',
    desc: '每篇 AI 生成的内容都会经过反模式检测——标题过短、正文缺失、通用低互动等 5 种已知失败模式。触发时自动警告并给出改进建议。',
  },
  samples: {
    title: '看看 AI 能写出什么样的帖子',
    sub: '以下是 Reddpilot 针对不同 subreddit 生成的内容样例。所有样例基于真实爆款模式生成，无需注册即可预览。',
    cta: '创建你的第一条爆款帖子 →',
    posts: [
      {
        hook: '痛点共鸣',
        subreddit: 'r/SaaS',
        title: '你的 SaaS 留存率低，真正的原因不是定价',
        body: '我分析了 47 家 B2B SaaS 公司过去 2 年的流失数据。流失的第一预测因子不是价格、不是 onboarding、不是功能缺失——而是大多数创始人从未衡量过的指标：Time-to-First-Value（TTFV）。\n\n数据表明：TTFV 超过 48 小时的用户，30 天流失率比 TTFV 在 2 小时以内的用户高 4.7 倍...',
        upvotes: '2.4k',
        comments: '186',
      },
      {
        hook: '故事开场',
        subreddit: 'r/Entrepreneur',
        title: '我花了 3 年做了一个没人要的产品——以下是复盘',
        body: '2023 年，我从大厂辞职创业。简历完美，融了 50 万美金，做了一个功能齐全的产品——用户要什么我们做什么。\n\n上线后，我们获得了 3 个付费客户。不是 300，不是 3000。三个。\n\n问题出在哪里？复盘下来有 5 个致命错误...',
        upvotes: '3.1k',
        comments: '245',
      },
      {
        hook: '数字冲击',
        subreddit: 'r/Productivity',
        title: '我记录了30天的每一分钟，总结出10条时间管理真相',
        body: '作为一个效率控，我决定做一项实验：连续 30 天，精确记录我醒着的每一分钟。结果让我大吃一惊。\n\n1. 我 23% 的"工作时间"实际上花在了 Slack 和邮件上\n2. 真正深度工作的时间平均每天只有 2 小时 14 分钟\n3. 下午 2-4 点是我效率最低的时段...',
        upvotes: '1.8k',
        comments: '142',
      },
      {
        hook: '争议观点',
        subreddit: 'r/Technology',
        title: '不中听的观点：大多数"AI 创业公司"只是套了 API 的落地页',
        body: '我在 ML 领域做了 8 年。当前的 AI 创业潮让我想起 2017 年的 ICO 泡沫——大量包装，极少实质。\n\n真正的 AI 差异化需要：自训练模型、专有数据壁垒、或领域特化的推理架构。而我们现在看到的 90% 是：一个 ChatGPT wrapper + 一个漂亮的 landing page...',
        upvotes: '5.2k',
        comments: '423',
      },
      {
        hook: '好奇心问题',
        subreddit: 'r/AskReddit',
        title: '你的行业里，什么"无关紧要"的做法实际上在摧毁用户信任？',
        body: '我是软件工程师。我的答案是："在我机器上能跑"作为跳过测试的借口。这不是无关紧要——它在侵蚀开发者和 QA 之间的信任，最终会蔓延到公司和用户之间。\n\n你们行业里呢？',
        upvotes: '8.7k',
        comments: '1.2k',
      },
    ],
  },
  evolve: {
    title: '自我进化引擎',
    desc: '每篇 Reddit 帖子发布后，系统自动追踪效果数据。失败案例通过多维度归因（标题/正文/时间/社区匹配）自动反馈到模式权重，下一次生成更精准。',
  },
  compare: {
    title: '为什么不用 ChatGPT 写 Reddit 帖子？',
    sub: '通用 AI 不懂 Reddit 文化。Reddpilot 是专门为 Reddit 爆款构建的。',
    left: '通用 AI（ChatGPT / Claude）',
    right: 'Reddpilot',
    rows: [
      { label: 'Reddit 文化适配', left: '通用回复，不懂社区文化', right: '41 个 subreddit 深度文化画像' },
      { label: '钩子策略', left: '无结构化钩子', right: '8 种统计验证的爆款钩子' },
      { label: '反模式检测', left: '无 Reddit 专属保护', right: '5 种已知失败模式自动检测' },
      { label: 'Subreddit 匹配', left: '需要手动调研', right: 'AI 自动匹配最佳社区' },
      { label: '数据基础', left: '通用互联网训练数据', right: '1,538 篇爆款帖子逆向工程' },
      { label: '自我进化', left: '每次对话从零开始', right: '发布后追踪效果，自动优化' },
    ],
  },
  trust: {
    title: '零风险开始',
    cards: [
      { title: '无需信用卡', desc: '注册即用，不需要任何支付信息' },
      { title: '每月 20 次免费生成', desc: 'Free 计划足够验证效果，随时升级' },
      { title: '随时取消', desc: 'Pro 计划 $5/月，不支持自动续费陷阱' },
    ],
  },
  footer: { pricing: '定价', login: '登录' },
}

const en = {
  hero: {
    line1: 'Not another AI writing tool —',
    line2: 'a reverse-engineering engine for Reddit virality',
    sub: 'We analyzed 1,538 real viral Reddit posts, extracted 8 hook types across 16 communities, and built a data-driven engine that generates content that actually survives on Reddit.',
    cta: 'Start free',
    email_placeholder: 'Enter your email...',
    dashboard: 'Go to Dashboard',
    pricing: 'View pricing',
  },  metrics: [
    { value: '1,538', label: 'Viral posts analyzed', icon: Database },
    { value: '8', label: 'Hook types', icon: Hash },
    { value: '16', label: 'Communities covered', icon: GitBranch },
    { value: '41', label: 'Cultural profiles', icon: Microscope },
  ],
  methodology: {
    title: 'Methodology: Data distillation, not AI writing',
    steps: [
      {
        num: '01',
        title: 'Data Collection',
        desc: 'Millions of Reddit posts sourced from Kaggle and Reddit API. Filtered for viral hits (upvotes > 3× median) across 16 major subreddits.',
      },
      {
        num: '02',
        title: 'Pattern Extraction',
        desc: 'Structured analysis of every post: title word count, body length, hook type, narrative mode, posting time — extracting replicable viral formulas.',
      },
      {
        num: '03',
        title: 'Cultural Profiling',
        desc: 'Deep cultural profiles for 41 subreddits: community preferences, language styles, taboos, optimal posting windows. Community-specific, not generic.',
      },
      {
        num: '04',
        title: 'AI Generation',
        desc: 'Viral patterns injected into DeepSeek LLM to generate subreddit-specific titles and body text. Every output includes a quality self-check with anti-pattern detection.',
      },
      {
        num: '05',
        title: 'Self-Evolution',
        desc: 'Track every post\'s performance — upvotes, comments, survival rate. Failed posts are auto-attributed to specific dimensions (title/body/timing), feeding back to improve future generations.',
      },
    ],
  },
  patterns: {
    title: '8 Viral Hook Types',
    sub: 'Every hook type statistically validated against real viral posts',
    list: [
      { name: 'Counterintuitive Discovery', en: '', rate: '26.2%', desc: '"I just discovered X..." — unexpected findings that challenge assumptions' },
      { name: 'Curious Question', en: '', rate: '30.5%', desc: '"ELI5:" / "Why does X?" — open-ended questions that spark discussion' },
      { name: 'Pain Point', en: '', rate: '33.7%', desc: '"The real problem with X..." — addressing shared frustrations' },
      { name: 'Number Shock', en: '', rate: '34.7%', desc: '"10 things I learned..." — specific numbers create information density' },
      { name: 'Story Opener', en: '', rate: '54.6%', desc: '"My experience with X..." — personal narrative builds instant trust' },
      { name: 'Controversial Opinion', en: '', rate: '25.8%', desc: '"Unpopular opinion:" — polarizing takes that drive engagement' },
      { name: 'Comparison Analysis', en: '', rate: '28.3%', desc: '"X vs Y" — structured comparisons for decision-making' },
      { name: 'Suspense Mystery', en: '', rate: '31.2%', desc: '"What nobody tells you about X" — creating an information gap' },
    ],
  },
  cta: {
    title: 'Ready to get your Reddit posts upvoted?',
    sub: 'Start free with 20 generations per month. Upgrade to Pro anytime.',
    button: 'Sign up free',
    dashboard: 'Go to Dashboard',
  },
  anti: {
    title: '5 Anti-Patterns Detected',
    desc: 'Every AI-generated post is checked against 5 known failure patterns — title too short, missing body, generic low-engagement. Triggers automatic warnings with improvement suggestions.',
  },
  samples: {
    title: 'See what the AI actually generates',
    sub: 'Real output samples from Reddpilot, generated for different subreddits. No signup needed to preview.',
    cta: 'Create your first viral post →',
    posts: [
      {
        hook: 'Pain Point',
        subreddit: 'r/SaaS',
        title: 'The real reason your SaaS churn is high (it\'s not your pricing)',
        body: 'I analyzed churn data across 47 B2B SaaS companies over the past 2 years. The #1 predictor of churn isn\'t price, onboarding, or feature gaps. It\'s something most founders never measure: Time-to-First-Value (TTFV).\n\nThe data shows: users whose TTFV exceeds 48 hours have a 30-day churn rate 4.7× higher than those who reach value within 2 hours...',
        upvotes: '2.4k',
        comments: '186',
      },
      {
        hook: 'Story Opener',
        subreddit: 'r/Entrepreneur',
        title: 'I spent 3 years building a product nobody wanted. Here\'s what I learned.',
        body: 'In 2023 I quit my FAANG job to build a startup. Perfect resume, raised $500k, built every feature users asked for.\n\nWe launched to 3 paying customers. Not 300. Not 3,000. Three.\n\nHere are the 5 fatal mistakes I made — and what I\'d do differently...',
        upvotes: '3.1k',
        comments: '245',
      },
      {
        hook: 'Number Shock',
        subreddit: 'r/Productivity',
        title: '10 things I learned tracking every minute of my day for 30 days',
        body: 'I\'m a productivity nerd. So I ran an experiment: log every single minute of my waking hours for a full month. The results surprised me.\n\n1. I spent 23% of my "work time" on Slack and email\n2. True deep work averaged just 2h 14m per day\n3. 2–4 PM was my least productive window...',
        upvotes: '1.8k',
        comments: '142',
      },
      {
        hook: 'Controversial',
        subreddit: 'r/Technology',
        title: 'Unpopular opinion: Most "AI startups" are just API wrappers with a landing page',
        body: 'I\'ve worked in ML engineering for 8 years. The current AI startup landscape reminds me of the 2017 ICO boom — lots of packaging, very little substance.\n\nReal AI differentiation requires: custom-trained models, proprietary data moats, or domain-specific inference architecture. What we\'re seeing instead: a ChatGPT wrapper + a nice landing page...',
        upvotes: '5.2k',
        comments: '423',
      },
      {
        hook: 'Curious Question',
        subreddit: 'r/AskReddit',
        title: 'What\'s a "harmless" industry practice that\'s actually destroying trust?',
        body: 'I\'m a software engineer, and mine is: "it works on my machine" as an excuse to skip testing. It\'s not harmless — it erodes trust between devs and QA, and eventually between the company and users.\n\nWhat\'s yours?',
        upvotes: '8.7k',
        comments: '1.2k',
      },
    ],
  },
  evolve: {
    title: 'Self-Evolving Engine',
    desc: 'After each Reddit post goes live, the system automatically tracks performance. Failed posts undergo multi-dimensional attribution (title/body/timing/community fit), feeding back to improve future generations.',
  },
  compare: {
    title: 'Why not just use ChatGPT for Reddit?',
    sub: 'Generic AI doesn\'t understand Reddit culture. Reddpilot is purpose-built for Reddit virality.',
    left: 'Generic AI (ChatGPT / Claude)',
    right: 'Reddpilot',
    rows: [
      { label: 'Reddit culture fit', left: 'Generic responses, no community awareness', right: '41 deep subreddit cultural profiles' },
      { label: 'Hook strategy', left: 'No structured hooks', right: '8 statistically-validated viral hooks' },
      { label: 'Anti-pattern detection', left: 'No Reddit-specific guardrails', right: '5 known failure patterns auto-detected' },
      { label: 'Subreddit matching', left: 'Manual research required', right: 'AI auto-matches best communities' },
      { label: 'Data foundation', left: 'Trained on general web data', right: 'Reverse-engineered from 1,538 viral posts' },
      { label: 'Self-evolution', left: 'Starts fresh every chat', right: 'Tracks live performance, auto-optimizes' },
    ],
  },
  trust: {
    title: 'Zero-risk start',
    cards: [
      { title: 'No credit card', desc: 'Start immediately — no payment info needed' },
      { title: '20 free gens/month', desc: 'Free tier gives you enough to validate. Upgrade anytime.' },
      { title: 'Cancel anytime', desc: 'Pro is $5/mo. No auto-renewal traps.' },
    ],
  },
  footer: { pricing: 'Pricing', login: 'Login' },
}

export default function Landing() {
  const { lang } = useLang()
  const t = lang === 'zh' ? zh : en
  const token = localStorage.getItem('kf_token')
  const navigate = useNavigate()
  const [heroEmail, setHeroEmail] = useState('')

  function handleHeroSubmit() {
    const email = heroEmail.trim()
    const params = new URLSearchParams({ mode: 'register' })
    if (email) params.set('email', email)
    navigate(`/login?${params.toString()}`)
  }

  // Fire Purchase when returning from Stripe checkout success
  useEffect(() => {
    const p = new URLSearchParams(window.location.search)
    if (p.get('upgraded') === 'true' && !localStorage.getItem(RD_EVENTS.PURCHASE_FIRED)) {
      trackPurchase(`stripe_${Date.now()}`)
      localStorage.setItem(RD_EVENTS.PURCHASE_FIRED, '1')
      // Clean URL without reloading
      window.history.replaceState({}, '', '/')
    }
  }, [])

  return (
    <div className="min-h-screen">
      {/* Hero */}
      <section className="max-w-[960px] mx-auto pt-16 pb-12 px-4 sm:px-8 lg:pt-24 lg:pb-16">
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-accent" />
            <span className="font-semibold text-base text-text-primary font-mono tracking-wide uppercase text-xs">Reddpilot</span>
          </div>
          <LangSwitch />
        </div>

        <h1 className="text-[28px] sm:text-[40px] lg:text-[48px] font-bold tracking-[-0.8px] sm:tracking-[-1.2px] leading-[1.08] mb-6 max-w-[760px]">
          {t.hero.line1}
          <br />
          <span className="text-accent">{t.hero.line2}</span>
        </h1>

        <p className="text-text-secondary text-base leading-relaxed max-w-[560px] mb-10">
          {t.hero.sub}
        </p>

        {token ? (
          <Link to="/app" className="inline-flex items-center gap-2 bg-accent text-base font-semibold px-6 py-3 rounded-md text-sm hover:bg-accent-hover transition-colors">
            {t.hero.dashboard} <ArrowRight size={16} />
          </Link>
        ) : (
          <div className="space-y-3">
            <div className="flex flex-col sm:flex-row gap-3 max-w-[440px]">
              <input
                type="email"
                value={heroEmail}
                onChange={e => setHeroEmail(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleHeroSubmit()}
                placeholder={t.hero.email_placeholder}
                className="flex-1 bg-surface-1 border border-border rounded-md px-4 py-3 text-sm outline-none focus:border-accent transition-colors"
              />
              <button
                onClick={handleHeroSubmit}
                className="flex items-center justify-center gap-2 bg-accent text-base font-semibold px-6 py-3 rounded-md text-sm hover:bg-accent-hover transition-colors shrink-0"
              >
                {t.hero.cta} <ArrowRight size={16} />
              </button>
            </div>
            <Link to="/pricing" className="inline-block text-sm text-text-muted hover:text-text-secondary transition-colors">
              {t.hero.pricing} →
            </Link>
          </div>
        )}
      </section>

      {/* Metrics bar */}
      <section className="border-y border-border">
        <div className="max-w-[960px] mx-auto px-4 sm:px-8 py-8 lg:py-12">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-8">
            {t.metrics.map(m => (
              <div key={m.label} className="text-center lg:text-left">
                <m.icon size={18} className="text-text-muted mb-3 mx-auto lg:mx-0" />
                <p className="font-mono text-[32px] font-bold text-accent leading-none mb-1">{m.value}</p>
                <p className="text-xs text-text-muted">{m.label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Sample Outputs — social proof, no signup needed */}
      <section className="border-b border-border">
        <div className="max-w-[960px] mx-auto px-4 sm:px-8 py-12 lg:py-20">
          <h2 className="text-[11px] font-mono uppercase tracking-widest text-text-muted mb-3">
            {t.samples.title}
          </h2>
          <p className="text-text-secondary text-sm mb-8 lg:mb-12">{t.samples.sub}</p>

          <div className="space-y-4 mb-10">
            {t.samples.posts.map((post, i) => (
              <div key={i} className="bg-surface-1 border border-border rounded-lg p-5 hover:border-accent/20 transition-colors">
                <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-3">
                  <span className="inline-flex items-center gap-1.5 self-start">
                    <span className="w-5 h-5 rounded-full bg-accent/10 flex items-center justify-center">
                      <span className="text-[10px] font-bold text-accent">r/</span>
                    </span>
                    <span className="text-xs font-semibold text-text-primary">{post.subreddit}</span>
                  </span>
                  <span className="text-[10px] font-mono text-accent bg-accent/10 px-2 py-0.5 rounded-full">
                    {post.hook}
                  </span>
                </div>
                <h3 className="text-[15px] font-semibold mb-2 leading-snug">{post.title}</h3>
                <p className="text-text-secondary text-sm leading-relaxed mb-3 line-clamp-3 whitespace-pre-line">
                  {post.body}
                </p>
                <div className="flex items-center gap-4 text-xs text-text-muted">
                  <span className="flex items-center gap-1">
                    <ArrowUp size={14} className="text-accent" />
                    {post.upvotes} upvotes
                  </span>
                  <span className="flex items-center gap-1">
                    <MessageCircle size={14} />
                    {post.comments} comments
                  </span>
                </div>
              </div>
            ))}
          </div>

          <div className="text-center">
            <Link to={token ? '/app' : '/login?mode=register'} className="inline-flex items-center gap-2 text-accent text-sm font-semibold hover:underline">
              {t.samples.cta} <ArrowRight size={14} />
            </Link>
          </div>
        </div>
      </section>

      {/* Pattern Library — shows what you get */}
      <section className="border-b border-border">
        <div className="max-w-[960px] mx-auto px-4 sm:px-8 py-12 lg:py-20">
          <h2 className="text-[11px] font-mono uppercase tracking-widest text-text-muted mb-3">
            {t.patterns.title}
          </h2>
          <p className="text-text-secondary text-sm mb-8 lg:mb-12">{t.patterns.sub}</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {t.patterns.list.map(p => (
              <div key={p.name} className="bg-surface-1 border border-border rounded-lg p-5 group hover:border-accent/30 transition-colors">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-[11px] font-mono text-accent font-bold">{p.rate}</span>
                  <span className="text-[10px] text-text-muted uppercase tracking-wide">viral rate</span>
                </div>
                <h3 className="text-sm font-semibold mb-2">{p.name}</h3>
                <p className="text-xs text-text-secondary leading-relaxed">{p.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Comparison — why not just use ChatGPT */}
      <section className="border-b border-border">
        <div className="max-w-[960px] mx-auto px-4 sm:px-8 py-12 lg:py-20">
          <h2 className="text-[11px] font-mono uppercase tracking-widest text-text-muted mb-3">
            {t.compare.title}
          </h2>
          <p className="text-text-secondary text-sm mb-8 lg:mb-10">{t.compare.sub}</p>

          {/* Mobile: card stack. Desktop: table */}
          <div className="hidden sm:block overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-3 pr-4 text-text-muted text-xs font-semibold uppercase tracking-wide w-40" />
                  <th className="text-left py-3 px-4 text-text-muted text-xs font-semibold uppercase tracking-wide">
                    {t.compare.left}
                  </th>
                  <th className="text-left py-3 pl-4 text-accent text-xs font-semibold uppercase tracking-wide">
                    {t.compare.right}
                  </th>
                </tr>
              </thead>
              <tbody>
                {t.compare.rows.map((row, i) => (
                  <tr key={i} className={i % 2 === 0 ? 'bg-surface-2/30' : ''}>
                    <td className="py-3 pr-4 text-text-secondary text-xs font-medium">{row.label}</td>
                    <td className="py-3 px-4 text-text-muted text-xs">{row.left}</td>
                    <td className="py-3 pl-4 text-accent text-xs font-medium">{row.right}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile cards */}
          <div className="sm:hidden space-y-3">
            {t.compare.rows.map((row, i) => (
              <div key={i} className="bg-surface-1 border border-border rounded-lg p-4">
                <p className="text-xs font-semibold text-text-primary mb-2">{row.label}</p>
                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div>
                    <p className="text-[10px] text-text-muted uppercase mb-0.5">{t.compare.left.split('(')[0].trim()}</p>
                    <p className="text-text-muted">{row.left}</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-accent uppercase mb-0.5">{t.compare.right}</p>
                    <p className="text-accent font-medium">{row.right}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Methodology — how it works */}
      <section className="border-b border-border">
        <div className="max-w-[960px] mx-auto px-4 sm:px-8 py-12 lg:py-20">
          <h2 className="text-[11px] font-mono uppercase tracking-widest text-text-muted mb-8 lg:mb-12">
            {t.methodology.title}
          </h2>
          <div className="space-y-0">
            {t.methodology.steps.map((s, i) => (
              <div key={s.num} className={`flex gap-6 py-6 ${i < t.methodology.steps.length - 1 ? 'border-b border-border' : ''}`}>
                <div className="font-mono text-xs text-accent font-bold pt-0.5 shrink-0 w-8">{s.num}</div>
                <div>
                  <h3 className="text-sm font-semibold mb-1.5">{s.title}</h3>
                  <p className="text-text-secondary text-sm leading-relaxed">{s.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Anti-patterns + Self-evolution */}
      <section className="border-b border-border">
        <div className="max-w-[960px] mx-auto px-4 sm:px-8 py-12 lg:py-20">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 lg:gap-16">
            <div>
              <div className="flex items-center gap-2 mb-4">
                <Target size={16} className="text-accent" />
                <h3 className="text-sm font-semibold">{t.anti.title}</h3>
              </div>
              <p className="text-text-secondary text-sm leading-relaxed">{t.anti.desc}</p>
            </div>
            <div>
              <div className="flex items-center gap-2 mb-4">
                <Brain size={16} className="text-accent" />
                <h3 className="text-sm font-semibold">{t.evolve.title}</h3>
              </div>
              <p className="text-text-secondary text-sm leading-relaxed">{t.evolve.desc}</p>
            </div>
          </div>
        </div>
      </section>

      {/* Trust / Risk reducers */}
      <section className="border-b border-border">
        <div className="max-w-[960px] mx-auto px-4 sm:px-8 py-12 lg:py-16">
          <h2 className="text-[11px] font-mono uppercase tracking-widest text-text-muted mb-8 text-center">
            {t.trust.title}
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 max-w-[720px] mx-auto">
            {t.trust.cards.map((card, i) => (
              <div key={i} className="bg-surface-1 border border-border rounded-lg p-5 text-center">
                <div className="w-8 h-8 rounded-full bg-accent/10 flex items-center justify-center mx-auto mb-3">
                  {i === 0 ? <CreditCard size={14} className="text-accent" /> : i === 1 ? <Gift size={14} className="text-accent" /> : <Shield size={14} className="text-accent" />}
                </div>
                <h3 className="text-sm font-semibold mb-1.5">{card.title}</h3>
                <p className="text-xs text-text-secondary leading-relaxed">{card.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="border-b border-border">
        <div className="max-w-[960px] mx-auto px-4 sm:px-8 py-12 lg:py-20 text-center">
          <h2 className="text-[22px] font-semibold mb-3">{t.cta.title}</h2>
          <p className="text-text-secondary text-sm mb-8 max-w-[400px] mx-auto">{t.cta.sub}</p>
          <Link to={token ? '/app' : '/login?mode=register'} className="inline-flex items-center gap-2 bg-accent text-base font-semibold px-6 py-3 rounded-md text-sm hover:bg-accent-hover transition-colors">
            {token ? t.cta.dashboard : t.cta.button} <ArrowRight size={16} />
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-b border-border">
        <div className="max-w-[960px] mx-auto px-4 sm:px-8 py-6 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-accent" />
            <span className="text-xs text-text-muted font-mono">Reddpilot v3</span>
          </div>
          <div className="flex items-center gap-6">
            <Link to="/pricing" className="text-xs text-text-muted hover:text-text-secondary transition-colors">{t.footer.pricing}</Link>
            <Link to="/login" className="text-xs text-text-muted hover:text-text-secondary transition-colors">{t.footer.login}</Link>
          </div>
        </div>
      </footer>
    </div>
  )
}
