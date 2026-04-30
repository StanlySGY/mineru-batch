import { ref, watch } from 'vue'

export interface MineruEndpoint {
  url: string
  backend: string
  serverUrl: string
  enabled: boolean
}

const LS = {
  backend: 'cfg_backend',
  mineruApi: 'cfg_mineru_api',
  serverUrl: 'cfg_server_url',
  mineruEndpoints: 'cfg_mineru_endpoints',
  outputFormat: 'cfg_output_format',
  parseMethod: 'cfg_parse_method',
  langList: 'cfg_lang_list',
  formulaEnable: 'cfg_formula_enable',
  tableEnable: 'cfg_table_enable',
  returnMd: 'cfg_return_md',
  returnMiddleJson: 'cfg_return_middle_json',
  returnModelOutput: 'cfg_return_model_output',
  returnContentList: 'cfg_return_content_list',
  returnImages: 'cfg_return_images',
  responseFormatZip: 'cfg_response_format_zip',
  replaceImageUrl: 'cfg_replace_image_url',
  startPageId: 'cfg_start_page_id',
  endPageId: 'cfg_end_page_id',
  timeout: 'cfg_timeout',
  autoConvert: 'cfg_auto_convert',
}

const backend = ref(localStorage.getItem(LS.backend) || 'hybrid-http-client')
const mineruApi = ref(localStorage.getItem(LS.mineruApi) || 'http://localhost:8086/file_parse')
const serverUrl = ref(localStorage.getItem(LS.serverUrl) || 'http://localhost:6002/v1')

const DEFAULT_ENDPOINT: MineruEndpoint = {
  url: 'http://localhost:8086/file_parse',
  backend: 'hybrid-http-client',
  serverUrl: 'http://localhost:6002/v1',
  enabled: true,
}
function loadEndpoints(): MineruEndpoint[] {
  try {
    const raw = localStorage.getItem(LS.mineruEndpoints)
    if (raw) {
      const arr = JSON.parse(raw)
      if (Array.isArray(arr) && arr.length) return arr
    }
  } catch {}
  return [{ ...DEFAULT_ENDPOINT }]
}
const mineruEndpoints = ref<MineruEndpoint[]>(loadEndpoints())
const outputFormat = ref(localStorage.getItem(LS.outputFormat) || 'md')
const parseMethod = ref(localStorage.getItem(LS.parseMethod) || 'auto')
const langList = ref(localStorage.getItem(LS.langList) || 'ch')
const formulaEnable = ref(localStorage.getItem(LS.formulaEnable) !== 'false')
const tableEnable = ref(localStorage.getItem(LS.tableEnable) !== 'false')
const returnMd = ref(localStorage.getItem(LS.returnMd) !== 'false')
const returnMiddleJson = ref(localStorage.getItem(LS.returnMiddleJson) !== 'false')
const returnModelOutput = ref(localStorage.getItem(LS.returnModelOutput) !== 'false')
const returnContentList = ref(localStorage.getItem(LS.returnContentList) === 'true')
const returnImages = ref(localStorage.getItem(LS.returnImages) === 'true')
const responseFormatZip = ref(localStorage.getItem(LS.responseFormatZip) === 'true')
const replaceImageUrl = ref(localStorage.getItem(LS.replaceImageUrl) !== 'false')
const startPageId = ref(Number(localStorage.getItem(LS.startPageId) || '0'))
const endPageId = ref(Number(localStorage.getItem(LS.endPageId) || '99999'))
const timeout = ref(Number(localStorage.getItem(LS.timeout) || '600'))
const autoConvert = ref(localStorage.getItem(LS.autoConvert) !== 'false')

watch(backend, (v) => localStorage.setItem(LS.backend, v))
watch(mineruApi, (v) => localStorage.setItem(LS.mineruApi, v))
watch(serverUrl, (v) => localStorage.setItem(LS.serverUrl, v))
watch(mineruEndpoints, (v) => localStorage.setItem(LS.mineruEndpoints, JSON.stringify(v)), { deep: true })
watch(outputFormat, (v) => localStorage.setItem(LS.outputFormat, v))
watch(parseMethod, (v) => localStorage.setItem(LS.parseMethod, v))
watch(langList, (v) => localStorage.setItem(LS.langList, v))
watch(formulaEnable, (v) => localStorage.setItem(LS.formulaEnable, String(v)))
watch(tableEnable, (v) => localStorage.setItem(LS.tableEnable, String(v)))
watch(returnMd, (v) => localStorage.setItem(LS.returnMd, String(v)))
watch(returnMiddleJson, (v) => localStorage.setItem(LS.returnMiddleJson, String(v)))
watch(returnModelOutput, (v) => localStorage.setItem(LS.returnModelOutput, String(v)))
watch(returnContentList, (v) => localStorage.setItem(LS.returnContentList, String(v)))
watch(returnImages, (v) => localStorage.setItem(LS.returnImages, String(v)))
watch(responseFormatZip, (v) => localStorage.setItem(LS.responseFormatZip, String(v)))
watch(replaceImageUrl, (v) => localStorage.setItem(LS.replaceImageUrl, String(v)))
watch(startPageId, (v) => localStorage.setItem(LS.startPageId, String(v)))
watch(endPageId, (v) => localStorage.setItem(LS.endPageId, String(v)))
watch(timeout, (v) => localStorage.setItem(LS.timeout, String(v)))
watch(autoConvert, (v) => localStorage.setItem(LS.autoConvert, String(v)))

const DEFAULTS: Record<string, string | number | boolean> = {
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
}

function resetDefaults() {
  const map: Record<string, { ref: any; ls: string }> = {
    backend: { ref: backend, ls: LS.backend },
    mineruApi: { ref: mineruApi, ls: LS.mineruApi },
    serverUrl: { ref: serverUrl, ls: LS.serverUrl },
    outputFormat: { ref: outputFormat, ls: LS.outputFormat },
    parseMethod: { ref: parseMethod, ls: LS.parseMethod },
    langList: { ref: langList, ls: LS.langList },
    formulaEnable: { ref: formulaEnable, ls: LS.formulaEnable },
    tableEnable: { ref: tableEnable, ls: LS.tableEnable },
    returnMd: { ref: returnMd, ls: LS.returnMd },
    returnMiddleJson: { ref: returnMiddleJson, ls: LS.returnMiddleJson },
    returnModelOutput: { ref: returnModelOutput, ls: LS.returnModelOutput },
    returnContentList: { ref: returnContentList, ls: LS.returnContentList },
    returnImages: { ref: returnImages, ls: LS.returnImages },
    responseFormatZip: { ref: responseFormatZip, ls: LS.responseFormatZip },
    replaceImageUrl: { ref: replaceImageUrl, ls: LS.replaceImageUrl },
    startPageId: { ref: startPageId, ls: LS.startPageId },
    endPageId: { ref: endPageId, ls: LS.endPageId },
    timeout: { ref: timeout, ls: LS.timeout },
    autoConvert: { ref: autoConvert, ls: LS.autoConvert },
  }
  for (const [key, entry] of Object.entries(map)) {
    const v = DEFAULTS[key]
    entry.ref.value = v
    localStorage.setItem(entry.ls, String(v))
  }
  mineruEndpoints.value = [{ ...DEFAULT_ENDPOINT }]
  localStorage.setItem(LS.mineruEndpoints, JSON.stringify(mineruEndpoints.value))
}

const PRESETS_KEY = 'cfg_presets'

interface Preset {
  name: string
  data: Record<string, unknown>
}

function loadPresets(): Preset[] {
  try {
    const raw = localStorage.getItem(PRESETS_KEY)
    return raw ? JSON.parse(raw) : []
  } catch { return [] }
}
function savePresets(list: Preset[]) {
  localStorage.setItem(PRESETS_KEY, JSON.stringify(list))
}

function getCurrentConfig(): Record<string, unknown> {
  return {
    backend: backend.value, mineruApi: mineruApi.value, serverUrl: serverUrl.value,
    outputFormat: outputFormat.value, parseMethod: parseMethod.value, langList: langList.value,
    formulaEnable: formulaEnable.value, tableEnable: tableEnable.value,
    returnMd: returnMd.value, returnMiddleJson: returnMiddleJson.value,
    returnModelOutput: returnModelOutput.value, returnContentList: returnContentList.value,
    returnImages: returnImages.value, responseFormatZip: responseFormatZip.value,
    replaceImageUrl: replaceImageUrl.value, startPageId: startPageId.value,
    endPageId: endPageId.value, timeout: timeout.value, autoConvert: autoConvert.value,
  }
}

function applyConfigData(data: Record<string, unknown>) {
  const map: Record<string, { ref: any; ls: string }> = {
    backend: { ref: backend, ls: LS.backend },
    mineruApi: { ref: mineruApi, ls: LS.mineruApi },
    serverUrl: { ref: serverUrl, ls: LS.serverUrl },
    outputFormat: { ref: outputFormat, ls: LS.outputFormat },
    parseMethod: { ref: parseMethod, ls: LS.parseMethod },
    langList: { ref: langList, ls: LS.langList },
    formulaEnable: { ref: formulaEnable, ls: LS.formulaEnable },
    tableEnable: { ref: tableEnable, ls: LS.tableEnable },
    returnMd: { ref: returnMd, ls: LS.returnMd },
    returnMiddleJson: { ref: returnMiddleJson, ls: LS.returnMiddleJson },
    returnModelOutput: { ref: returnModelOutput, ls: LS.returnModelOutput },
    returnContentList: { ref: returnContentList, ls: LS.returnContentList },
    returnImages: { ref: returnImages, ls: LS.returnImages },
    responseFormatZip: { ref: responseFormatZip, ls: LS.responseFormatZip },
    replaceImageUrl: { ref: replaceImageUrl, ls: LS.replaceImageUrl },
    startPageId: { ref: startPageId, ls: LS.startPageId },
    endPageId: { ref: endPageId, ls: LS.endPageId },
    timeout: { ref: timeout, ls: LS.timeout },
    autoConvert: { ref: autoConvert, ls: LS.autoConvert },
  }
  for (const [key, entry] of Object.entries(map)) {
    if (data[key] !== undefined) {
      entry.ref.value = data[key]
    }
  }
}

const presets = ref<Preset[]>(loadPresets())

function savePreset(name: string) {
  const list = loadPresets()
  const idx = list.findIndex(p => p.name === name)
  const preset: Preset = { name, data: getCurrentConfig() }
  if (idx >= 0) list[idx] = preset; else list.push(preset)
  savePresets(list)
  presets.value = list
}

function loadPreset(name: string) {
  const list = loadPresets()
  const p = list.find(p => p.name === name)
  if (p) applyConfigData(p.data)
}

function deletePreset(name: string) {
  const list = loadPresets().filter(p => p.name !== name)
  savePresets(list)
  presets.value = list
}

export function useConfig() {
  return {
    backend, mineruApi, serverUrl, outputFormat,
    parseMethod, langList,
    formulaEnable, tableEnable,
    returnMd, returnMiddleJson, returnModelOutput,
    returnContentList, returnImages,
    responseFormatZip, replaceImageUrl,
    startPageId, endPageId,
    timeout, autoConvert,
    mineruEndpoints,
    resetDefaults,
    presets, savePreset, loadPreset, deletePreset,
  }
}
