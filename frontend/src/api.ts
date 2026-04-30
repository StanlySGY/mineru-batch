import axios from 'axios'
import { ElMessage } from 'element-plus'

const http = axios.create({ baseURL: '/api' })

http.interceptors.response.use(
  (res) => res,
  (err) => {
    const status = err.response?.status
    if (status === 500) ElMessage.error('服务器内部错误')
    else if (status === 413) ElMessage.error('请求体过大')
    else if (status && status >= 400) {
      const msg = err.response?.data?.detail
      if (msg && typeof msg === 'string') ElMessage.error(msg)
    }
    return Promise.reject(err)
  },
)

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
  status: 'pending' | 'processing' | 'completed' | 'failed'
  output_format: 'md' | 'txt'
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
}

export const api = {
  async getStats() {
    const { data } = await http.get('/stats')
    return data as { total: number; pending: number; processing: number; completed: number; failed: number; avg_duration_ms: number }
  },

  async getConcurrency() {
    const { data } = await http.get('/concurrency')
    return data as { concurrency: number }
  },

  async setConcurrency(n: number) {
    const { data } = await http.put('/concurrency', { concurrency: n })
    return data as { concurrency: number }
  },

  async upload(files: File[], opts: UploadOptions, onProgress?: (pct: number) => void) {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
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
    const { data } = await http.post('/upload', form, {
      onUploadProgress: (e) => {
        if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100))
      },
    })
    return data
  },

  async listTasks(params: { status?: string; search?: string; page?: number; size?: number }) {
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

  async retryTask(id: number) {
    const { data } = await http.post(`/tasks/${id}/retry`)
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
    return `/api/tasks/${id}/download`
  },

  batchDownloadUrl(ids: number[]) {
    return `/api/tasks/batch/download?ids=${ids.join(',')}`
  },

  async preview(id: number) {
    const { data } = await http.get(`/tasks/${id}/preview`)
    return data as { content: string; filename: string; format: string }
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

  onTaskEvent(callback: (event: { type: string; task_id?: number; status?: string; [k: string]: unknown }) => void): () => void {
    const es = new EventSource('/api/tasks/events')
    es.onmessage = (e) => {
      try { callback(JSON.parse(e.data)) } catch {}
    }
    es.onerror = () => { es.close() }
    return () => es.close()
  },
}
