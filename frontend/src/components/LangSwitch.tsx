import { useLang } from '../i18n/LanguageContext'

export default function LangSwitch() {
  const { lang, setLang } = useLang()

  return (
    <button
      onClick={() => setLang(lang === 'zh' ? 'en' : 'zh')}
      className="text-[11px] font-mono px-2 py-0.5 rounded border border-border text-text-muted hover:text-text-secondary hover:border-border-hover transition-colors"
      title={lang === 'zh' ? 'Switch to English' : '切换到中文'}
    >
      {lang === 'zh' ? 'EN' : '中'}
    </button>
  )
}
