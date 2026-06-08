import { useState } from 'react'
import { ArrowRight, ArrowLeft, Check, Sparkles, TrendingUp, Target } from 'lucide-react'
import { useLang } from '../i18n/LanguageContext'

interface Props {
  onComplete: () => void
}

const zh = {
  title: '欢迎来到 Reddpilot',
  subtitle: '3 步上手，开始你的 Reddit 增长之旅',
  done: '开始使用',
  steps: [
    {
      icon: Target,
      title: '描述你的内容',
      body: '输入你想推广的产品或话题。AI 会自动分析并匹配最合适的 subreddit 社区和爆款模式。',
    },
    {
      icon: Sparkles,
      title: '选择最佳标题',
      body: '从多个 AI 生成的候选中选择评分最高的标题。每个标题都基于真实的 Reddit 爆款数据。',
    },
    {
      icon: TrendingUp,
      title: '发布并追踪效果',
      body: '复制生成的内容，手动发布到 Reddit。回来记录 upvotes 和评论，让系统越来越懂你的社区。',
    },
  ],
}

const en = {
  title: 'Welcome to Reddpilot',
  subtitle: 'Get started in 3 steps',
  done: 'Start using',
  steps: [
    {
      icon: Target,
      title: 'Describe your content',
      body: 'Tell us what you\'re promoting. AI matches the best subreddits and viral patterns for your topic.',
    },
    {
      icon: Sparkles,
      title: 'Pick the best title',
      body: 'Choose from AI-generated candidates scored against real viral data. Every title is tailored to your community.',
    },
    {
      icon: TrendingUp,
      title: 'Post & track results',
      body: 'Copy the generated content, publish to Reddit manually, then track upvotes and comments. The system learns as you go.',
    },
  ],
}

export default function Onboarding({ onComplete }: Props) {
  const { lang } = useLang()
  const t = lang === 'zh' ? zh : en
  const [step, setStep] = useState(0)

  const steps = t.steps
  const Icon = steps[step].icon

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-base/80 backdrop-blur-sm">
      <div className="bg-surface-1 border border-border rounded-lg w-full max-w-md mx-4 p-8">
        {/* Progress */}
        <div className="flex gap-2 mb-8">
          {steps.map((_, i) => (
            <div
              key={i}
              className={`h-1 flex-1 rounded-full transition-colors ${
                i <= step ? 'bg-accent' : 'bg-surface-3'
              }`}
            />
          ))}
        </div>

        {/* Icon */}
        <div className="w-12 h-12 rounded-lg bg-accent/10 flex items-center justify-center mb-6">
          <Icon size={24} className="text-accent" />
        </div>

        {/* Content */}
        <h2 className="text-[13px] font-mono uppercase tracking-widest text-text-muted mb-2">
          {step + 1} / {steps.length}
        </h2>
        <h1 className="text-xl font-semibold mb-3">{steps[step].title}</h1>
        <p className="text-text-secondary text-sm leading-relaxed mb-8">
          {steps[step].body}
        </p>

        {/* Actions */}
        <div className="flex items-center justify-between">
          <button
            onClick={() => setStep(s => s - 1)}
            disabled={step === 0}
            className="flex items-center gap-1.5 text-sm text-text-muted hover:text-text-secondary transition-colors disabled:opacity-30"
          >
            <ArrowLeft size={14} /> Back
          </button>

          {step < steps.length - 1 ? (
            <button
              onClick={() => setStep(s => s + 1)}
              className="flex items-center gap-2 bg-accent text-base font-semibold px-5 py-2.5 rounded-md text-sm hover:bg-accent-hover transition-colors"
            >
              Next <ArrowRight size={16} />
            </button>
          ) : (
            <button
              onClick={onComplete}
              className="flex items-center gap-2 bg-accent text-base font-semibold px-5 py-2.5 rounded-md text-sm hover:bg-accent-hover transition-colors"
            >
              <Check size={16} /> {t.done}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
