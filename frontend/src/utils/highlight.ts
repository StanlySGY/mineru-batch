import hljs from 'highlight.js/lib/core'

const LANG_MAP: Record<string, () => Promise<any>> = {
  javascript: () => import('highlight.js/lib/languages/javascript'),
  js: () => import('highlight.js/lib/languages/javascript'),
  typescript: () => import('highlight.js/lib/languages/typescript'),
  ts: () => import('highlight.js/lib/languages/typescript'),
  python: () => import('highlight.js/lib/languages/python'),
  json: () => import('highlight.js/lib/languages/json'),
  bash: () => import('highlight.js/lib/languages/bash'),
  shell: () => import('highlight.js/lib/languages/bash'),
  xml: () => import('highlight.js/lib/languages/xml'),
  html: () => import('highlight.js/lib/languages/xml'),
  css: () => import('highlight.js/lib/languages/css'),
  yaml: () => import('highlight.js/lib/languages/yaml'),
  sql: () => import('highlight.js/lib/languages/sql'),
  markdown: () => import('highlight.js/lib/languages/markdown'),
  md: () => import('highlight.js/lib/languages/markdown'),
  plaintext: () => import('highlight.js/lib/languages/plaintext'),
  java: () => import('highlight.js/lib/languages/java'),
  go: () => import('highlight.js/lib/languages/go'),
  rust: () => import('highlight.js/lib/languages/rust'),
  cpp: () => import('highlight.js/lib/languages/cpp'),
  c: () => import('highlight.js/lib/languages/c'),
}

const loaded = new Set<string>()

export async function ensureHljsLanguage(lang: string): Promise<void> {
  if (loaded.has(lang)) return
  const loader = LANG_MAP[lang]
  if (loader) {
    try {
      const mod = await loader()
      hljs.registerLanguage(lang, mod.default || mod)
      loaded.add(lang)
    } catch {
      // 语言包加载失败，忽略
    }
  }
}

export async function ensureAllCommonLanguages(): Promise<void> {
  await Promise.all(Object.keys(LANG_MAP).map(ensureHljsLanguage))
}

export { hljs }
