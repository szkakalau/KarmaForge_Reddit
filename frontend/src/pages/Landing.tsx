import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Database, Microscope, Brain, Target, Hash, GitBranch } from 'lucide-react'
import { useLang } from '../i18n/LanguageContext'
import LangSwitch from '../components/LangSwitch'
import { trackPurchase, RD_EVENTS } from '../redditPixel'

const zh = {
  hero: {
    line1: '不是通用 AI 写作工具，',
    line2: '是 Reddit 爆款的逆向工程引擎',
    sub: '我们从 1,538 篇真实 Reddit 爆款帖子中提取了 8 种钩子类型、覆盖 16 个主流社区，用数据驱动的方式生成真正能在 Reddit 上活下来的内容。',
    cta: '免费开始',
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
  evolve: {
    title: '自我进化引擎',
    desc: '每篇 Reddit 帖子发布后，系统自动追踪效果数据。失败案例通过多维度归因（标题/正文/时间/社区匹配）自动反馈到模式权重，下一次生成更精准。',
  },
  footer: { pricing: '定价', login: '登录' },
}

const en = {
  hero: {
    line1: 'Not another AI writing tool —',
    line2: 'a reverse-engineering engine for Reddit virality',
    sub: 'We analyzed 1,538 real viral Reddit posts, extracted 8 hook types across 16 communities, and built a data-driven engine that generates content that actually survives on Reddit.',
    cta: 'Start free',
    dashboard: 'Go to Dashboard',
    pricing: 'View pricing',
  },
  metrics: [
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
  evolve: {
    title: 'Self-Evolving Engine',
    desc: 'After each Reddit post goes live, the system automatically tracks performance. Failed posts undergo multi-dimensional attribution (title/body/timing/community fit), feeding back to improve future generations.',
  },
  footer: { pricing: 'Pricing', login: 'Login' },
}

export default function Landing() {
  const { lang } = useLang()
  const t = lang === 'zh' ? zh : en
  const token = localStorage.getItem('kf_token')

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
      <section className="max-w-[960px] mx-auto pt-24 pb-16 px-8">
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-accent" />
            <span className="font-semibold text-base text-text-primary font-mono tracking-wide uppercase text-xs">Reddpilot</span>
          </div>
          <LangSwitch />
        </div>

        <h1 className="text-[40px] sm:text-[48px] font-bold tracking-[-1.2px] leading-[1.08] mb-6 max-w-[760px]">
          {t.hero.line1}
          <br />
          <span className="text-accent">{t.hero.line2}</span>
        </h1>

        <p className="text-text-secondary text-base leading-relaxed max-w-[560px] mb-10">
          {t.hero.sub}
        </p>

        <div className="flex items-center gap-4">
          <Link to={token ? '/app' : '/login'} className="flex items-center gap-2 bg-accent text-base font-semibold px-6 py-3 rounded-md text-sm hover:bg-accent-hover transition-colors">
            {token ? t.hero.dashboard : t.hero.cta} <ArrowRight size={16} />
          </Link>
          <Link to="/pricing" className="flex items-center gap-2 bg-surface-1 border border-border text-text-primary font-semibold px-6 py-3 rounded-md text-sm hover:bg-surface-2 transition-colors">
            {t.hero.pricing}
          </Link>
        </div>
      </section>

      {/* Metrics bar */}
      <section className="border-y border-border">
        <div className="max-w-[960px] mx-auto px-8 py-12">
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

      {/* Methodology */}
      <section className="border-b border-border">
        <div className="max-w-[960px] mx-auto px-8 py-20">
          <h2 className="text-[11px] font-mono uppercase tracking-widest text-text-muted mb-12">
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

      {/* Pattern Library */}
      <section className="border-b border-border">
        <div className="max-w-[960px] mx-auto px-8 py-20">
          <h2 className="text-[11px] font-mono uppercase tracking-widest text-text-muted mb-3">
            {t.patterns.title}
          </h2>
          <p className="text-text-secondary text-sm mb-12">{t.patterns.sub}</p>
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

      {/* Anti-patterns + Self-evolution */}
      <section className="border-b border-border">
        <div className="max-w-[960px] mx-auto px-8 py-20">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-16">
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

      {/* CTA */}
      <section className="border-b border-border">
        <div className="max-w-[960px] mx-auto px-8 py-20 text-center">
          <h2 className="text-[22px] font-semibold mb-3">{t.cta.title}</h2>
          <p className="text-text-secondary text-sm mb-8 max-w-[400px] mx-auto">{t.cta.sub}</p>
          <Link to={token ? '/app' : '/login'} className="inline-flex items-center gap-2 bg-accent text-base font-semibold px-6 py-3 rounded-md text-sm hover:bg-accent-hover transition-colors">
            {token ? t.cta.dashboard : t.cta.button} <ArrowRight size={16} />
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-b border-border">
        <div className="max-w-[960px] mx-auto px-8 py-8 flex items-center justify-between">
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
