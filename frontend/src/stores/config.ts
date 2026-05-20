import { reactive, ref, watch } from 'vue'

export interface MineruEndpoint {
  url: string
  backend: string
  serverUrl: string
  enabled: boolean
  apiKey?: string
}

export interface ConfigState {
  backend: string
  mineruApi: string
  serverUrl: string
  outputFormat: string
  parseMethod: string
  langList: string
  formulaEnable: boolean
  tableEnable: boolean
  returnMd: boolean
  returnMiddleJson: boolean
  returnModelOutput: boolean
  returnContentList: boolean
  returnImages: boolean
  responseFormatZip: boolean
  replaceImageUrl: boolean
  startPageId: number
  endPageId: number
  timeout: number
  autoConvert: boolean
  [key: string]: string | number | boolean
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

const state = reactive<ConfigState>({ ...DEFAULTS })

for (const [k, v] of Object.entries(DEFAULTS)) {
  const raw = localStorage.getItem(LS[k as keyof typeof LS])
  if (raw !== null) {
    if (typeof v === 'boolean') state[k] = raw === 'true'
    else if (typeof v === 'number') state[k] = Number.isNaN(Number(raw)) ? v : Number(raw)
    else state[k] = raw
  }
}

watch(
  () => Object.keys(DEFAULTS).map(k => String(state[k])).join('\x00'),
  () => {
    for (const k of Object.keys(DEFAULTS)) {
      localStorage.setItem(LS[k as keyof typeof LS], String(state[k]))
    }
  }
)

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
  Object.assign(state, DEFAULTS)
  mineruEndpoints.value = [{ ...DEFAULT_ENDPOINT }]
}

function getCurrentConfig(): ConfigState {
  return { ...state }
}

function applyConfigData(data: Partial<ConfigState>) {
  console.debug('[config] applyConfigData:', JSON.stringify(data))
  for (const [k, v] of Object.entries(data)) {
    if (k in DEFAULTS && v !== undefined) {
      const old = state[k]
      state[k] = v
      console.debug(`[config]  ${k}: ${JSON.stringify(old)} → ${JSON.stringify(v)}`)
    }
  }
}

export function useConfig() {
  return {
    state,
    mineruEndpoints,
    applyConfigData,
    resetDefaults,
    getCurrentConfig,
  }
}
