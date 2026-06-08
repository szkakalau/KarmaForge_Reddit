import { createContext, useContext, useState, type ReactNode } from 'react'
import type { Lang } from './translations'
import { tx } from './translations'

const LS_KEY = 'kf_lang'

interface LanguageCtx {
  lang: Lang
  setLang: (l: Lang) => void
  t: (key: string, vars?: Record<string, string | number>) => string
}

const LanguageContext = createContext<LanguageCtx>({
  lang: 'zh',
  setLang: () => {},
  t: (key) => key,
})

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => {
    const stored = localStorage.getItem(LS_KEY)
    if (stored === 'en' || stored === 'zh') return stored
    // Default to browser language
    if (typeof navigator !== 'undefined' && navigator.language.startsWith('en')) return 'en'
    return 'zh'
  })

  const setLang = (l: Lang) => {
    setLangState(l)
    localStorage.setItem(LS_KEY, l)
  }

  const t = (key: string, vars?: Record<string, string | number>) => tx(lang, key, vars)

  return (
    <LanguageContext.Provider value={{ lang, setLang, t }}>
      {children}
    </LanguageContext.Provider>
  )
}

export function useLang() {
  return useContext(LanguageContext)
}
