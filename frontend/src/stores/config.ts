import { ref, watch } from 'vue'

export interface MineruEndpoint {
  url: string
  backend: string
  serverUrl: string
  enabled: boolean
  apiKey?: string
}

// Generic localStorage-backed ref factory
function lsRef<T extends string | number | boolean>(key: string, fallback: T) {
  const raw = localStorage.getItem(key)
  let init: T
  if (typeof fallback === 'boolean') {
    init = (raw === null ? fallback : raw === 'true') as T
  } else if (typeof fallback === 'number') {
    const n = raw === null ? fallback : Number(raw)
    init = (Number.isNaN(n) ? fallback : n) as T
  } else {
    init = (raw ?? fallback) as T
  }
  const r = ref(init) as ReturnType<typeof ref<T>>
  watch(r, (v) => localStorage.setItem(key, String(v)))
  return r
}

const LS = {
  backend: 'cfg_backend', mineruApi: 'cfg_mineru_api', serverUrl: 'cfg_server_url',
  mineruEndpoints: 'cfg_mineru_endpoints', outputFormat: 'cfg_output_format',
  parseMethod: 'cfg_parse_method', langList: 'cfg_lang_list',
  formulaEnable: 'cfg_formula_enable', tableEnable: 'cfg_table_enable',
  returnMd: 'cfg_return_md', returnMiddleJson: 'cfg_return_middle_json',
  returnModelOutput: 'cfg_return_model_output', returnContentList: 'cfg_return_content_list',
  returnImages: 'cfg_return_images', responseFormatZip: 'cfg_response_format_zip',
  replaceImageUrl: 'cfg_replace_image_url', startPageId: 'cfg_start_page_id',
  endPageId: 'cfg_end_page_id', timeout: 'cfg_timeout', autoConvert: 'cfg_auto_convert',
} as const

// Typed defaults — single source of truth
const DEFAULTS = {
  backend: 'hybrid-http-client',
  mineruApi: 'http://localhost:8086/file_parse',
  serverUrl: 'http://localhost:6002/v1',
  outputFormat: 'md',
  parseMethod: 'auto',
  langList: 'ch',
  formulaEnable: true,
  tableEnable: true,
  returnMd: true,
  returnMiddleJson: true,
  returnModelOutput: true,
  returnContentList: false,
  returnImages: false,
  responseFormatZip: false,
  replaceImageUrl: true,
  startPageId: 0,
  endPageId: 99999,
  timeout: 600,
  autoConvert: true,
} as const

// Create all config refs from defaults
const cfg = Object.fromEntries(
  Object.entries(DEFAULTS).map(([k, v]) => [k, lsRef(LS[k as keyof typeof LS], v)])
) as { [K in keyof typeof DEFAULTS]: ReturnType<typeof ref<(typeof DEFAULTS)[K]>> }

// Endpoints (array type, handled separately)
const DEFAULT_ENDPOINT: MineruEndpoint = {
  url: 'http://localhost:8086/file_parse', backend: 'hybrid-http-client',
  serverUrl: 'http://localhost:6002/v1', enabled: true,
}
function loadEndpoints(): MineruEndpoint[] {
  try {
    const raw = localStorage.getItem(LS.mineruEndpoints)
    if (raw) { const arr = JSON.parse(raw); if (Array.isArray(arr) && arr.length) return arr }
  } catch {}
  return [{ ...DEFAULT_ENDPOINT }]
}
const mineruEndpoints = ref<MineruEndpoint[]>(loadEndpoints())
watch(mineruEndpoints, (v) => localStorage.setItem(LS.mineruEndpoints, JSON.stringify(v)), { deep: true })

function resetDefaults() {
  for (const [k, v] of Object.entries(DEFAULTS)) {
    cfg[k as keyof typeof DEFAULTS].value = v as never
  }
  mineruEndpoints.value = [{ ...DEFAULT_ENDPOINT }]
}

// Presets
const PRESETS_KEY = 'cfg_presets'
interface Preset { name: string; data: Record<string, unknown> }
function loadPresets(): Preset[] {
  try { const r = localStorage.getItem(PRESETS_KEY); return r ? JSON.parse(r) : [] } catch { return [] }
}
function savePresets(list: Preset[]) { localStorage.setItem(PRESETS_KEY, JSON.stringify(list)) }

function getCurrentConfig(): Record<string, unknown> {
  return Object.fromEntries(Object.entries(cfg).map(([k, r]) => [k, r.value]))
}

function applyConfigData(data: Record<string, unknown>) {
  for (const [k, r] of Object.entries(cfg)) {
    if (data[k] !== undefined) (r as ReturnType<typeof ref>).value = data[k] as never
  }
}

const presets = ref<Preset[]>(loadPresets())

function savePreset(name: string) {
  const list = loadPresets()
  const idx = list.findIndex(p => p.name === name)
  const p: Preset = { name, data: getCurrentConfig() }
  if (idx >= 0) list[idx] = p; else list.push(p)
  savePresets(list); presets.value = list
}
function loadPreset(name: string) {
  const p = loadPresets().find(p => p.name === name)
  if (p) applyConfigData(p.data)
}
function deletePreset(name: string) {
  const list = loadPresets().filter(p => p.name !== name)
  savePresets(list); presets.value = list
}

export function useConfig() {
  return {
    ...cfg,
    mineruEndpoints,
    resetDefaults,
    presets, savePreset, loadPreset, deletePreset,
  }
}
