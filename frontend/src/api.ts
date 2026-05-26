import axios, { AxiosHeaders } from 'axios'
import { ElMessage } from 'element-plus'

const apiBase = import.meta.env.VITE_API_BASE_URL || '/api'
const adminKeyStorage = 'admin_api_key'
const http = axios.create({ baseURL: apiBase })

function apiUrl(path: string) {
  return `${apiBase.replace(/\/$/, '')}${path}`
}

function getStoredAdminKey() {
  return localStorage.getItem(adminKeyStorage) || ''
}

function setStoredAdminKey(key: string) {
  const value = key.trim()
  if (value) localStorage.setItem(adminKeyStorage, value)
  else localStorage.removeItem(adminKeyStorage)
}

function showApiUnavailableOnce() {
  if (window.__apiErrorShown) return
  window.__apiErrorShown = true
  ElMessage.warning('后端服务未连接，仅可预览界面')
}

function markApiUnavailable() {
  window.__apiUnavailable = true
  showApiUnavailableOnce()
}

function isCoreApiNotFound(err: any) {
  if (err.response?.status !== 404) return false
  const url = String(err.config?.url || '')
  return ['/stats', '/security/status', '/concurrency', '/tasks/events'].some(path => url === path || url.startsWith(`${path}?`))
}

http.interceptors.request.use((config) => {
  const key = getStoredAdminKey()
  if (key) config.headers = AxiosHeaders.from(config.headers).set('X-Admin-Api-Key', key)
  return config
})

http.interceptors.response.use(
  (res) => {
    const contentType = String(res.headers?.['content-type'] || '')
    const body = typeof res.data === 'string' ? res.data.trimStart().toLowerCase() : ''
    if (contentType.includes('text/html') || body.startsWith('<!doctype html') || body.startsWith('<html')) {
      markApiUnavailable()
      return Promise.reject(new Error('API returned HTML fallback'))
    }
    return res
  },
  (err) => {
    if (!err.response) {
      showApiUnavailableOnce()
    } else {
      const status = err.response.status
      // 404 是预期的（后端未部署），核心接口 404 时进入静态预览模式
      if (status === 404) {
        if (isCoreApiNotFound(err)) markApiUnavailable()
      } else if (status === 500) {
        ElMessage.error('服务器内部错误')
      } else if (status === 413) {
        ElMessage.error('请求体过大')
      } else if (status && status >= 400) {
        const msg = err.response?.data?.detail
        if (msg && typeof msg === 'string') ElMessage.error(msg)
        else ElMessage.error(`请求失败 (${status})`)
      }
    }
    return Promise.reject(err)
  },
)

declare global {
  interface Window {
    __apiErrorShown?: boolean
    __apiUnavailable?: boolean
  }
}

export interface TaskItem {
  id: number
  original_filename: string
  file_size: number
  pdf_path: string | null
  timeout: number
  auto_convert_doc: boolean
  mineru_api: string
  backend: string
  server_url: string
  parse_method: string
  lang_list: string
  formula_enable: boolean
  table_enable: boolean
  return_md: boolean
  return_middle_json: boolean
  return_model_output: boolean
  return_content_list: boolean
  return_images: boolean
  response_format_zip: boolean
  replace_image_url: boolean
  start_page_id: number
  end_page_id: number
  batch_id: string | null
  batch_name: string | null
  status: 'pending' | 'processing' | 'completed' | 'failed'
  output_format: 'md' | 'txt' | 'html'
  error_message: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string
  updated_at: string
}

export interface LogItem {
  id: number
  task_id: number | null
  level: 'info' | 'warn' | 'error'
  message: string
  detail: string | null
  created_at: string
}

export interface LogGroup {
  task_id: number
  filename: string
  status: string
  created_at: string | null
  logs: LogItem[]
}

export interface UploadProgress {
  pct: number
  loaded: number
  total: number
  speed: number
  eta: number
}

export interface UploadOptions {
  backend: string
  mineruApi: string
  serverUrl: string
  endpoints?: string
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
  outputFormat: string
  timeout: number
  autoConvert: boolean
  apiKey?: string
  batchId?: string
  batchName?: string
}

export interface ServerEndpoint {
  url: string
  backend: string
  serverUrl: string
  enabled: boolean
  apiKey?: string
  hasApiKey?: boolean
}

export interface ServerSettings {
  defaults: Record<string, string | number | boolean>
  mineruEndpoints: ServerEndpoint[]
}

export interface QualityReport {
  total: number
  completed: number
  failed: number
  processing: number
  pending: number
  success_rate: number
  avg_duration_ms: number
  recent_failures: { id: number; filename: string; error_message: string | null; created_at: string | null; completed_at: string | null }[]
}

export interface QueueStatus {
  concurrency: number
  queue_size: number
  pending: number
  processing: number
  available_slots: number
  waiting_tasks: { id: number; filename: string; priority: number; created_at: string | null }[]
}

export interface FailureCategories {
  total: number
  items: { category: string; count: number }[]
}

export interface BatchProgressReport {
  total: number
  items: { batch_id: string; batch_name: string | null; total: number; pending: number; processing: number; completed: number; failed: number; progress: number; latest_at: string | null }[]
}

export interface NodeHealthReport {
  total: number
  healthy: number
  nodes: { index: number; url: string; enabled: boolean; ok: boolean; latency_ms: number | null; status: string; error?: string }[]
}

export async function requestNotificationPermission(): Promise<boolean> {
  if (!('Notification' in window)) return false
  if (Notification.permission === 'granted') return true
  if (Notification.permission === 'denied') return false
  const result = await Notification.requestPermission()
  return result === 'granted'
}

let notificationBuffer: { filename: string; status: string }[] = []
let notificationTimer: ReturnType<typeof setTimeout> | null = null

export function notifyTaskComplete(filename: string, status: string) {
  if (!('Notification' in window) || Notification.permission !== 'granted') return
  notificationBuffer.push({ filename, status })
  if (notificationTimer) clearTimeout(notificationTimer)
  notificationTimer = setTimeout(() => {
    if (notificationBuffer.length === 0) return
    if (notificationBuffer.length === 1) {
      const item = notificationBuffer[0]
      const title = item.status === 'completed' ? '任务完成' : '任务失败'
      const body = item.status === 'completed' ? `${item.filename} 解析完成` : `${item.filename} 解析失败`
      new Notification(title, { body })
    } else {
      const completed = notificationBuffer.filter(n => n.status === 'completed').length
      const failed = notificationBuffer.filter(n => n.status === 'failed').length
      new Notification('批量任务完成', {
        body: `共 ${notificationBuffer.length} 个任务：成功 ${completed}，失败 ${failed}`,
      })
    }
    notificationBuffer = []
    notificationTimer = null
  }, 2000)
}

export const api = {
  getAdminKey() {
    return getStoredAdminKey()
  },

  setAdminKey(key: string) {
    setStoredAdminKey(key)
  },

  async getSecurityStatus() {
    const { data } = await http.get('/security/status')
    return data as { adminRequired: boolean; allowPrivateEndpoints: boolean }
  },

  async getStats() {
    const { data } = await http.get('/stats')
    return data as { total: number; pending: number; processing: number; completed: number; failed: number; avg_duration_ms: number }
  },

  async getSettings() {
    const { data } = await http.get('/settings')
    return data as ServerSettings
  },

  async saveSettings(settings: ServerSettings) {
    const { data } = await http.put('/settings', settings)
    return data as ServerSettings
  },

  async getQualityReport() {
    const { data } = await http.get('/reports/quality')
    return data as QualityReport
  },

  async getQueueStatus() {
    const { data } = await http.get('/queue/status')
    return data as QueueStatus
  },

  async getFailureCategories() {
    const { data } = await http.get('/reports/failures')
    return data as FailureCategories
  },

  async getBatchProgress() {
    const { data } = await http.get('/reports/batches')
    return data as BatchProgressReport
  },

  async getNodeHealth() {
    const { data } = await http.get('/nodes/health')
    return data as NodeHealthReport
  },

  async exportSettings() {
    const { data } = await http.get('/settings/export')
    return data as ServerSettings
  },

  async importSettings(settings: ServerSettings) {
    const { data } = await http.post('/settings/import', settings)
    return data as ServerSettings
  },

  async getConcurrency() {
    const { data } = await http.get('/concurrency')
    return data as { concurrency: number }
  },

  async setConcurrency(n: number) {
    const { data } = await http.put('/concurrency', { concurrency: n })
    return data as { concurrency: number }
  },

  async upload(files: File[], opts: UploadOptions, onProgress?: (p: UploadProgress) => void, signal?: AbortSignal) {
    const form = new FormData()
    const relativePaths: string[] = []
    files.forEach((f) => {
      form.append('files', f)
      relativePaths.push((f as any).webkitRelativePath || (f as any)._folderPath || f.name)
    })
    form.append('relative_paths', JSON.stringify(relativePaths))
    form.append('backend', opts.backend)
    form.append('mineru_api', opts.mineruApi)
    form.append('server_url', opts.serverUrl)
    if (opts.endpoints) form.append('mineru_endpoints', opts.endpoints)
    form.append('parse_method', opts.parseMethod)
    form.append('lang_list', opts.langList)
    form.append('formula_enable', String(opts.formulaEnable))
    form.append('table_enable', String(opts.tableEnable))
    form.append('return_md', String(opts.returnMd))
    form.append('return_middle_json', String(opts.returnMiddleJson))
    form.append('return_model_output', String(opts.returnModelOutput))
    form.append('return_content_list', String(opts.returnContentList))
    form.append('return_images', String(opts.returnImages))
    form.append('response_format_zip', String(opts.responseFormatZip))
    form.append('replace_image_url', String(opts.replaceImageUrl))
    form.append('start_page_id', String(opts.startPageId))
    form.append('end_page_id', String(opts.endPageId))
    form.append('output_format', opts.outputFormat)
    form.append('timeout', String(opts.timeout))
    form.append('auto_convert', String(opts.autoConvert))
    if (opts.apiKey) form.append('api_key', opts.apiKey)
    if (opts.batchId) form.append('batch_id', opts.batchId)
    if (opts.batchName) form.append('batch_name', opts.batchName)
    const startTime = Date.now()
    let lastLoaded = 0
    let lastTime = startTime
    const { data } = await http.post('/upload', form, {
      signal,
      onUploadProgress: (e) => {
        if (!onProgress || !e.total) return
        const now = Date.now()
        const elapsed = now - lastTime
        const speed = elapsed > 0 ? (e.loaded - lastLoaded) / (elapsed / 1000) : 0
        lastLoaded = e.loaded
        lastTime = now
        const remaining = speed > 0 ? (e.total - e.loaded) / speed : 0
        onProgress({
          pct: Math.round((e.loaded / e.total) * 100),
          loaded: e.loaded,
          total: e.total,
          speed,
          eta: remaining,
        })
      },
    })
    return data
  },

  async listTasks(params: { status?: string; search?: string; batch_id?: string; page?: number; size?: number }) {
    const { data } = await http.get('/tasks', { params })
    return data as { total: number; items: TaskItem[] }
  },

  async getTask(id: number) {
    const { data } = await http.get(`/tasks/${id}`)
    return data as TaskItem
  },

  async deleteTask(id: number) {
    const { data } = await http.delete(`/tasks/${id}`)
    return data
  },

  async batchDeleteTasks(ids: number[]) {
    const { data } = await http.delete('/tasks/batch', { params: { ids: ids.join(',') } })
    return data
  },

  async batchRetryTasks(ids: number[]) {
    const { data } = await http.post('/tasks/batch/retry', null, { params: { ids: ids.join(',') } })
    return data as { count: number }
  },

  async batchConvertDocs(ids: number[]) {
    const { data } = await http.post('/tasks/batch/convert', null, { params: { ids: ids.join(',') } })
    return data as { count: number }
  },

  async retryTask(id: number, opts?: { mineruApi?: string; serverUrl?: string }) {
    const form = new FormData()
    if (opts?.mineruApi) form.append('mineru_api', opts.mineruApi)
    if (opts?.serverUrl) form.append('server_url', opts.serverUrl)
    const { data } = await http.post(`/tasks/${id}/retry`, form)
    return data
  },

  async cancelTask(id: number) {
    const { data } = await http.post(`/tasks/${id}/cancel`)
    return data
  },

  async convertDocToPdf(id: number) {
    const { data } = await http.post(`/tasks/${id}/convert`)
    return data
  },

  downloadUrl(id: number) {
    return apiUrl(`/tasks/${id}/download`)
  },

  batchDownloadUrl(ids: number[]) {
    return apiUrl(`/tasks/batch/download?ids=${ids.join(',')}`)
  },

  batchMarkdownDownloadUrl(ids: number[]) {
    return apiUrl(`/tasks/batch/download-markdown?ids=${encodeURIComponent(ids.join(','))}`)
  },

  batchMarkdownDownloadByBatchUrl(batchId: string) {
    return apiUrl(`/tasks/batch/download-markdown?batch_id=${encodeURIComponent(batchId)}`)
  },

  async preview(id: number) {
    const { data } = await http.get(`/tasks/${id}/preview`)
    return data as { content: string; filename: string; format: string }
  },

  async updateTaskContent(id: number, content: string) {
    const { data } = await http.put(`/tasks/${id}/content`, { content })
    return data as { detail: string }
  },

  async listLogs(params: { task_id?: number; level?: string; page?: number; size?: number }) {
    const { data } = await http.get('/logs', { params })
    return data as { total: number; items: LogItem[] }
  },

  async listLogsGrouped(params: { level?: string; page?: number; size?: number }) {
    const { data } = await http.get('/logs/grouped', { params })
    return data as { total: number; items: LogGroup[] }
  },

  async clearLogs() {
    const { data } = await http.delete('/logs')
    return data
  },

  async getMinerUContainerLogs(containerName: string = 'mineru-full', lines: number = 100) {
    const { data } = await http.get('/logs/mineru-container', { params: { container_name: containerName, lines } })
    return data as { ok: boolean; container?: string; logs?: string; lines?: number; error?: string }
  },

  async testConnection(params: { mineru_api: string; server_url: string }) {
    const { data } = await http.post('/test-connection', params)
    return data as { ok: boolean; detail?: string; error?: string }
  },

  async getStorage() {
    const { data } = await http.get('/storage')
    return data as { uploads: number; outputs: number; converted: number; database: number; total: number }
  },

  async cleanStorage(targets: string[]) {
    const { data } = await http.post('/storage/clean', { targets })
    return data as { detail: string; counts: Record<string, number> }
  },

  async cleanCompletedSources() {
    const { data } = await http.post('/storage/clean-sources')
    return data as { detail: string; count: number; freed_bytes: number }
  },

  async getStatsTrend(days = 7) {
    const { data } = await http.get('/stats/trend', { params: { days } })
    return data as { date: string; completed: number; failed: number }[]
  },

  async getStatsFiletypes() {
    const { data } = await http.get('/stats/filetypes')
    return data as { type: string; count: number }[]
  },

  async getTasksSince(since: string) {
    const { data } = await http.get('/tasks/since', { params: { since } })
    return data as { items: TaskItem[] }
  },

  onTaskEvent(
    callback: (event: { type: string; task_id?: number; status?: string; [k: string]: unknown }) => void,
    onStatusChange?: (connected: boolean) => void,
    onReconnectSync?: (tasks: TaskItem[]) => void,
  ): () => void {
    let reconnectAttempts = 0
    const MAX_RECONNECT = 30
    let es: EventSource | null = null
    let stopped = false
    let lastEventTime: string | null = null
    let wasDisconnected = false

    async function syncMissedTasks() {
      if (!lastEventTime || !onReconnectSync) return
      try {
        const { items } = await api.getTasksSince(lastEventTime)
        if (items.length > 0) onReconnectSync(items)
      } catch (e) { console.warn('[SSE] sync missed tasks failed:', e) }
    }

    function connect() {
      if (stopped || window.__apiUnavailable) return
      es = new EventSource(apiUrl('/tasks/events'))
      es.onopen = () => {
        reconnectAttempts = 0
        onStatusChange?.(true)
        if (wasDisconnected) {
          syncMissedTasks()
          wasDisconnected = false
        }
      }
      es.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data)
          lastEventTime = new Date().toISOString()
          callback(data)
        } catch (e) { console.warn('[SSE] parse event failed:', e) }
      }
      es.onerror = () => {
        onStatusChange?.(false)
        wasDisconnected = true
        es?.close()
        if (stopped || window.__apiUnavailable) return
        if (reconnectAttempts >= MAX_RECONNECT) return
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000)
        reconnectAttempts++
        setTimeout(connect, delay)
      }
    }
    connect()

    function onVisible() {
      if (document.visibilityState === 'visible' && (!es || es.readyState === EventSource.CLOSED)) {
        reconnectAttempts = 0
        wasDisconnected = true
        es?.close()
        connect()
      }
    }
    document.addEventListener('visibilitychange', onVisible)

    return () => {
      stopped = true
      es?.close()
      document.removeEventListener('visibilitychange', onVisible)
    }
  },
}
