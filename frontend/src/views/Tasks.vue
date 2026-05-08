<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { Download, Delete, RefreshRight, Search, View, Switch, CircleClose, Timer, DocumentCopy, ArrowUp, ArrowDown, MagicStick } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, type TaskItem, requestNotificationPermission, notifyTaskComplete } from '../api'
import { isDocFile } from '../utils/file'
import { translateError } from '../utils/error'
import { formatTime, formatSize, statusTag } from '../utils/format'
import { useConfig } from '../stores/config'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js/lib/core'
import javascript from 'highlight.js/lib/languages/javascript'
import python from 'highlight.js/lib/languages/python'
import json from 'highlight.js/lib/languages/json'
import bash from 'highlight.js/lib/languages/bash'
import xml from 'highlight.js/lib/languages/xml'
import css from 'highlight.js/lib/languages/css'
import yaml from 'highlight.js/lib/languages/yaml'
import sql from 'highlight.js/lib/languages/sql'
import plaintext from 'highlight.js/lib/languages/plaintext'

let hljsReady = false
function ensureHljs() {
  if (hljsReady) return
  hljs.registerLanguage('javascript', javascript)
  hljs.registerLanguage('js', javascript)
  hljs.registerLanguage('python', python)
  hljs.registerLanguage('json', json)
  hljs.registerLanguage('bash', bash)
  hljs.registerLanguage('xml', xml)
  hljs.registerLanguage('html', xml)
  hljs.registerLanguage('css', css)
  hljs.registerLanguage('yaml', yaml)
  hljs.registerLanguage('sql', sql)
  hljs.registerLanguage('plaintext', plaintext)
  hljsReady = true
}

marked.setOptions({ breaks: true, gfm: true })

const tasks = ref<TaskItem[]>([])
const total = ref(0)
const page = ref(1)
const size = ref(20)
const isMobile = ref(window.innerWidth <= 768)
const filterStatus = ref('')
const filterSearch = ref('')
const loading = ref(false)
const firstLoad = ref(true)
const now = ref(Date.now())
let clockTimer: ReturnType<typeof setInterval> | null = null
let clockActive = false
let sseClose: (() => void) | null = null

function startClock() {
  if (clockActive) return
  clockActive = true
  clockTimer = setInterval(() => { now.value = Date.now() }, 1000)
}
function stopClock() {
  if (clockTimer) { clearInterval(clockTimer); clockTimer = null }
  clockActive = false
}

const selectedIds = ref<number[]>([])
const tableRef = ref<InstanceType<typeof import('element-plus')['ElTable']> | null>(null)

const statusSummary = computed(() => {
  const s = { pending: 0, processing: 0, completed: 0, failed: 0 }
  for (const t of tasks.value) s[t.status] = (s[t.status] || 0) + 1
  return s
})

const selectedHasRetryable = computed(() =>
  selectedIds.value.some(id => { const t = tasks.value.find(r => r.id === id); return t && (t.status === 'failed' || t.status === 'completed') })
)
const selectedHasConvertible = computed(() =>
  selectedIds.value.some(id => { const t = tasks.value.find(r => r.id === id); return t && isDocFile(t.original_filename) && !t.pdf_path })
)
const selectedHasDownloadable = computed(() =>
  selectedIds.value.some(id => { const t = tasks.value.find(r => r.id === id); return t && t.status === 'completed' })
)

const previewVisible = ref(false)
const previewLoading = ref(false)
const previewContent = ref('')
const previewFilename = ref('')
const previewFormat = ref('md')
const previewTaskId = ref(0)
const previewMode = ref<'render' | 'source'>('render')
const previewSearch = ref('')
const previewSearchMatches = ref(0)
const previewSearchIdx = ref(0)

function highlightSearch(text: string, query: string): string {
  if (!query) return text
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const regex = new RegExp(`(${escaped})`, 'gi')
  let idx = 0
  return text.replace(regex, () => {
    idx++
    return `<mark class="search-highlight${idx === previewSearchIdx.value ? ' active' : ''}">${'$1'}</mark>`
  })
}

const renderedPreview = ref('')
const previewRendering = ref(false)

watch([previewContent, previewFormat, previewMode, previewSearch, previewSearchIdx], () => {
  if (!previewContent.value || previewFormat.value !== 'md' || previewMode.value !== 'render') {
    renderedPreview.value = ''
    return
  }
  previewRendering.value = true
  setTimeout(() => {
    ensureHljs()
    const raw = marked.parse(previewContent.value) as string
    const clean = DOMPurify.sanitize(raw, { ADD_TAGS: ['code', 'pre', 'mark'], ADD_ATTR: ['class'] })
    const el = document.createElement('div')
    el.innerHTML = clean
    el.querySelectorAll('pre code').forEach(block => {
      hljs.highlightElement(block as HTMLElement)
    })
    let html = el.innerHTML
    if (previewSearch.value) {
      const escaped = previewSearch.value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
      const regex = new RegExp(`(${escaped})`, 'gi')
      const matches = html.match(regex)
      previewSearchMatches.value = matches ? matches.length : 0
      if (previewSearchMatches.value > 0) {
        let idx = 0
        html = html.replace(regex, () => {
          idx++
          return `<mark class="search-highlight${idx === previewSearchIdx.value ? ' active' : ''}">${'$1'}</mark>`
        })
      }
    } else {
      previewSearchMatches.value = 0
      previewSearchIdx.value = 0
    }
    renderedPreview.value = html
    previewRendering.value = false
  }, 0)
}, { immediate: true })

const sourcePreviewHighlighted = computed(() => {
  if (!previewContent.value) return ''
  if (!previewSearch.value) return escapeHtml(previewContent.value)
  const escaped = escapeHtml(previewContent.value)
  const searchEscaped = previewSearch.value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const regex = new RegExp(`(${searchEscaped})`, 'gi')
  const matches = escaped.match(regex)
  previewSearchMatches.value = matches ? matches.length : 0
  let idx = 0
  return escaped.replace(regex, () => {
    idx++
    return `<mark class="search-highlight${idx === previewSearchIdx.value ? ' active' : ''}">${'$1'}</mark>`
  })
})

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function previewSearchNext() {
  if (!previewSearchMatches.value) return
  previewSearchIdx.value = previewSearchIdx.value >= previewSearchMatches.value ? 1 : previewSearchIdx.value + 1
}
function previewSearchPrev() {
  if (!previewSearchMatches.value) return
  previewSearchIdx.value = previewSearchIdx.value <= 1 ? previewSearchMatches.value : previewSearchIdx.value - 1
}

let searchDebounceTimer: ReturnType<typeof setTimeout> | null = null
watch(previewSearch, () => {
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer)
  searchDebounceTimer = setTimeout(() => {
    previewSearchIdx.value = previewSearchMatches.value ? 1 : 0
  }, 300)
})

const detailVisible = ref(false)
const detailTask = ref<TaskItem | null>(null)

const cfg = useConfig()

function applyTaskAsPreset(task: TaskItem) {
  cfg.backend.value = task.backend
  cfg.mineruApi.value = task.mineru_api
  cfg.serverUrl.value = task.server_url
  cfg.parseMethod.value = task.parse_method
  cfg.langList.value = task.lang_list
  cfg.formulaEnable.value = task.formula_enable
  cfg.tableEnable.value = task.table_enable
  cfg.returnMd.value = task.return_md
  cfg.returnMiddleJson.value = task.return_middle_json
  cfg.returnModelOutput.value = task.return_model_output
  cfg.returnContentList.value = task.return_content_list
  cfg.returnImages.value = task.return_images
  cfg.responseFormatZip.value = task.response_format_zip
  cfg.replaceImageUrl.value = task.replace_image_url
  cfg.startPageId.value = task.start_page_id
  cfg.endPageId.value = task.end_page_id
  cfg.outputFormat.value = task.output_format
  cfg.timeout.value = task.timeout
  ElMessage.success('已将任务参数应用为当前配置，请前往上传页重新提交')
}

async function loadTasks() {
  loading.value = true
  try {
    const res = await api.listTasks({
      status: filterStatus.value || undefined,
      search: filterSearch.value || undefined,
      page: page.value,
      size: size.value,
    })
    tasks.value = res.items
    total.value = res.total
  } finally {
    loading.value = false
    firstLoad.value = false
  }
}

async function handleDelete(row: TaskItem) {
  try {
    await ElMessageBox.confirm(`确定删除 "${row.original_filename}"？`, '确认', { type: 'warning' })
    await api.deleteTask(row.id)
    ElMessage.success('已删除')
    loadTasks()
  } catch {}
}

async function handleBatchDelete() {
  if (!selectedIds.value.length) return ElMessage.warning('请先选择任务')
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selectedIds.value.length} 个任务？`, '确认', { type: 'warning' })
    await api.batchDeleteTasks(selectedIds.value)
    ElMessage.success('已批量删除')
    selectedIds.value = []
    loadTasks()
  } catch {}
}

async function handleBatchRetry() {
  if (!selectedIds.value.length) return ElMessage.warning('请先选择任务')
  const ids = selectedIds.value.filter(id => {
    const t = tasks.value.find(r => r.id === id)
    return t && (t.status === 'failed' || t.status === 'completed')
  })
  if (!ids.length) return ElMessage.warning('选中的任务中没有可重试的（失败/已完成）')
  try {
    const res = await api.batchRetryTasks(ids)
    ElMessage.success(`已重试 ${res.count} 个任务`)
    selectedIds.value = []
    loadTasks()
  } catch { ElMessage.error('批量重试失败') }
}

async function handleBatchConvert() {
  if (!selectedIds.value.length) return ElMessage.warning('请先选择任务')
  const ids = selectedIds.value.filter(id => {
    const t = tasks.value.find(r => r.id === id)
    return t && isDocFile(t.original_filename) && !t.pdf_path
  })
  if (!ids.length) return ElMessage.warning('选中的任务中没有待转换的文档')
  try {
    const res = await api.batchConvertDocs(ids)
    ElMessage.success(`已转换 ${res.count} 个文档`)
    selectedIds.value = []
    loadTasks()
  } catch { ElMessage.error('批量转换失败') }
}

function handleBatchDownload() {
  const ids = selectedIds.value.filter(id => {
    const t = tasks.value.find(r => r.id === id)
    return t && t.status === 'completed'
  })
  if (!ids.length) return ElMessage.warning('选中的任务中没有已完成的')
  const a = document.createElement('a')
  a.href = api.batchDownloadUrl(ids)
  a.download = ''
  a.target = '_blank'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

async function handleRetryAllFailed() {
  const failedIds = tasks.value.filter(t => t.status === 'failed').map(t => t.id)
  if (!failedIds.length) return ElMessage.warning('当前页无失败任务')
  try {
    const res = await api.batchRetryTasks(failedIds)
    ElMessage.success(`已重试 ${res.count} 个当前页失败任务`)
    loadTasks()
  } catch { ElMessage.error('批量重试失败') }
}

async function handleConvertAllDocs() {
  const docIds = tasks.value.filter(t => isDocFile(t.original_filename) && !t.pdf_path).map(t => t.id)
  if (!docIds.length) return ElMessage.warning('当前页无待转换文档')
  try {
    const res = await api.batchConvertDocs(docIds)
    ElMessage.success(`已转换 ${res.count} 个当前页文档`)
    loadTasks()
  } catch { ElMessage.error('批量转换失败') }
}

async function handleRetry(row: TaskItem) {
  try {
    await api.retryTask(row.id)
    ElMessage.success('已重新提交')
    loadTasks()
  } catch {
    ElMessage.error('重试失败')
  }
}

async function handleCancel(row: TaskItem) {
  try {
    await ElMessageBox.confirm(`确定取消任务 "${row.original_filename}"？`, '确认', { type: 'warning' })
    await api.cancelTask(row.id)
    ElMessage.success('已取消')
    loadTasks()
  } catch {}
}

function handleDownload(row: TaskItem) {
  const a = document.createElement('a')
  a.href = api.downloadUrl(row.id)
  a.download = ''
  a.target = '_blank'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

async function handlePreview(row: TaskItem) {
  previewTaskId.value = row.id
  previewFilename.value = row.original_filename
  previewFormat.value = row.output_format
  previewMode.value = 'render'
  previewVisible.value = true
  previewLoading.value = true
  previewContent.value = ''
  try {
    const res = await api.preview(row.id)
    previewContent.value = res.content
    previewFilename.value = res.filename
    previewFormat.value = res.format
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '预览失败')
    previewVisible.value = false
  } finally {
    previewLoading.value = false
  }
}

async function handleRetryFromPreview() {
  try {
    await api.retryTask(previewTaskId.value)
    ElMessage.success('已重新提交')
    previewVisible.value = false
    loadTasks()
  } catch {
    ElMessage.error('重试失败')
  }
}

async function handleConvertDoc(row: TaskItem) {
  try {
    await api.convertDocToPdf(row.id)
    ElMessage.success('转换完成，开始解析')
    loadTasks()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '转换失败')
  }
}

function handleFilterChange() {
  page.value = 1
  loadTasks()
}

function handleSearch() {
  page.value = 1
  loadTasks()
}

function handlePageChange(val: number) {
  page.value = val
  loadTasks()
}

function handleSelectionChange(rows: TaskItem[]) {
  selectedIds.value = rows.map(r => r.id)
}

function formatDuration(start: string | null, end: string | null) {
  if (!start) return '-'
  const endTime = end ? new Date(end).getTime() : now.value
  const ms = endTime - new Date(start).getTime()
  if (ms < 0) return '-'
  if (ms < 1000) return ms + 'ms'
  if (ms < 60000) return (ms / 1000).toFixed(1) + 's'
  return (ms / 60000).toFixed(1) + 'min'
}

function isLive(row: TaskItem) {
  return row.status === 'processing' && !!row.started_at && !row.completed_at
}

function selectAllCurrent() {
  if (!tableRef.value) return
  tasks.value.forEach(row => {
    tableRef.value!.toggleRowSelection(row, true)
  })
}

function exportCSV() {
  if (!tasks.value.length) return ElMessage.warning('当前无数据可导出')
  const header = ['ID', '文件名', '大小(B)', '状态', '格式', '创建时间', '错误信息']
  const rows = tasks.value.map(t => [t.id, t.original_filename, t.file_size, t.status, t.output_format, t.created_at, t.error_message || ''])
  const csv = [header, ...rows].map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\n')
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `tasks_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(a.href)
  ElMessage.success('已导出 CSV')
}

function showDetail(row: TaskItem) {
  detailTask.value = row
  detailVisible.value = true
}

const detailTimeline = computed(() => {
  const t = detailTask.value
  if (!t) return []
  const items = [{ label: '创建', time: formatTime(t.created_at), icon: '📁' }]
  if (t.started_at) items.push({ label: '开始处理', time: formatTime(t.started_at), icon: '⚙️' })
  if (t.completed_at) items.push({ label: t.status === 'completed' ? '完成' : '失败', time: formatTime(t.completed_at), icon: t.status === 'completed' ? '✅' : '❌' })
  return items
})

let sseDebounce: ReturnType<typeof setTimeout> | null = null

watch(tasks, (list) => {
  if (list.some(t => t.status === 'processing')) startClock()
  else stopClock()
}, { immediate: true })

onMounted(() => {
  loadTasks()
  sseClose = api.onTaskEvent((evt) => {
    if (evt.type === 'task_update') {
      if (sseDebounce) clearTimeout(sseDebounce)
      sseDebounce = setTimeout(() => loadTasks(), 300)
      if (evt.status === 'completed' || evt.status === 'failed') {
        const task = tasks.value.find(t => t.id === evt.task_id)
        if (task) notifyTaskComplete(task.original_filename, evt.status)
      }
    }
  })
  window.addEventListener('resize', checkMobile)
})
onUnmounted(() => {
  stopClock()
  if (sseDebounce) clearTimeout(sseDebounce)
  if (sseClose) sseClose()
  window.removeEventListener('resize', checkMobile)
})

function checkMobile() {
  isMobile.value = window.innerWidth <= 768
}
</script>

<template>
<el-card shadow="never" class="table-card">
  <template #header>
    <div class="card-header">
      <span class="card-title">任务列表</span>
      <div class="filter-row">
        <el-input v-model="filterSearch" placeholder="搜索文件名" clearable style="width:160px" size="small" :prefix-icon="Search" @clear="handleSearch" @keyup.enter="handleSearch" />
        <el-select v-model="filterStatus" placeholder="状态筛选" clearable style="width:130px" size="small" @change="handleFilterChange">
          <el-option label="等待中" value="pending" />
          <el-option label="处理中" value="processing" />
          <el-option label="已完成" value="completed" />
          <el-option label="失败" value="failed" />
        </el-select>
        <el-button v-if="selectedIds.length" type="danger" size="small" plain :icon="Delete" @click="handleBatchDelete">
          删除选中 ({{ selectedIds.length }})
        </el-button>
        <el-button v-if="selectedHasRetryable" type="warning" size="small" plain :icon="RefreshRight" @click="handleBatchRetry">
          重试选中
        </el-button>
        <el-button v-if="selectedHasConvertible" type="success" size="small" plain :icon="Switch" @click="handleBatchConvert">
          转换选中
        </el-button>
        <el-button v-if="selectedHasDownloadable" type="primary" size="small" plain :icon="Download" @click="handleBatchDownload">
          下载选中
        </el-button>
        <el-divider v-if="selectedIds.length" direction="vertical" />
        <el-button size="small" plain :icon="RefreshRight" @click="handleRetryAllFailed">重试当前页失败</el-button>
        <el-button size="small" plain :icon="Switch" @click="handleConvertAllDocs">转换当前页文档</el-button>
        <el-button size="small" plain :icon="DocumentCopy" @click="exportCSV">导出 CSV</el-button>
      </div>
    </div>
  </template>

  <el-skeleton v-if="firstLoad" :rows="8" animated />
  <template v-else>
  <div class="summary-bar">
    <span>共 <strong>{{ total }}</strong> 个任务</span>
    <span class="summary-divider">|</span>
    <el-tag type="info" size="small" effect="plain">等待 {{ statusSummary.pending }}</el-tag>
    <el-tag type="warning" size="small" effect="plain">处理中 {{ statusSummary.processing }}</el-tag>
    <el-tag type="success" size="small" effect="plain">已完成 {{ statusSummary.completed }}</el-tag>
    <el-tag type="danger" size="small" effect="plain">失败 {{ statusSummary.failed }}</el-tag>
    <span class="summary-spacer" />
    <el-button size="small" text @click="selectAllCurrent">全选当前页</el-button>
  </div>
  <el-table v-if="!isMobile" ref="tableRef" :data="tasks" row-key="id" v-loading="loading" stripe @selection-change="handleSelectionChange" @row-click="showDetail" class="task-table">
    <el-table-column type="selection" width="40" reserve-selection />
    <el-table-column prop="id" label="ID" width="60" sortable />
    <el-table-column prop="original_filename" label="文件名" min-width="180" show-overflow-tooltip sortable>
      <template #default="{ row }">
        <span>{{ row.original_filename }}</span>
        <el-tag v-if="isDocFile(row.original_filename) && row.pdf_path" type="success" size="small" style="margin-left:6px">已转PDF</el-tag>
        <el-tag v-else-if="isDocFile(row.original_filename)" type="warning" size="small" style="margin-left:6px">待转换</el-tag>
      </template>
    </el-table-column>
    <el-table-column label="大小" width="85" prop="file_size" sortable :sort-method="(a: TaskItem, b: TaskItem) => a.file_size - b.file_size">
      <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
    </el-table-column>
    <el-table-column label="状态" width="120" prop="status" sortable :sort-method="(a: TaskItem, b: TaskItem) => a.status.localeCompare(b.status)">
      <template #default="{ row }">
        <el-tooltip v-if="row.status === 'failed' && row.error_message" :content="translateError(row.error_message)" placement="top">
          <el-tag :type="statusTag[row.status]?.type" size="small" style="cursor:help">
            {{ statusTag[row.status]?.label || row.status }}
          </el-tag>
        </el-tooltip>
        <el-tag v-else :type="statusTag[row.status]?.type" size="small">
          {{ statusTag[row.status]?.label || row.status }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column label="格式" width="65">
      <template #default="{ row }">.{{ row.output_format }}</template>
    </el-table-column>
    <el-table-column label="耗时" width="80">
      <template #default="{ row }">
        <span :class="{ 'live-timer': isLive(row) }">{{ formatDuration(row.started_at, row.completed_at) }}</span>
      </template>
    </el-table-column>
    <el-table-column label="创建时间" width="160" prop="created_at" sortable :sort-method="(a: TaskItem, b: TaskItem) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()">
      <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
    </el-table-column>
    <el-table-column label="操作" width="280" fixed="right">
      <template #default="{ row }">
        <el-tooltip v-if="isDocFile(row.original_filename) && !row.pdf_path" content="转换为PDF" placement="top">
          <el-button size="small" type="warning" :icon="Switch" :disabled="row.status === 'processing'" @click="handleConvertDoc(row)" circle />
        </el-tooltip>
        <el-tooltip content="预览" placement="top">
          <el-button size="small" type="success" :icon="View" :disabled="row.status !== 'completed'" @click="handlePreview(row)" circle />
        </el-tooltip>
        <el-tooltip content="下载" placement="top">
          <el-button size="small" type="primary" :icon="Download" :disabled="row.status !== 'completed'" @click="handleDownload(row)" circle />
        </el-tooltip>
        <el-tooltip content="重试" placement="top">
          <el-button size="small" type="warning" :icon="RefreshRight" :disabled="row.status !== 'failed' && row.status !== 'completed'" @click="handleRetry(row)" circle />
        </el-tooltip>
        <el-tooltip content="取消" placement="top">
          <el-button size="small" type="info" :icon="CircleClose" :disabled="row.status !== 'pending' && row.status !== 'processing'" @click="handleCancel(row)" circle />
        </el-tooltip>
        <el-tooltip content="删除" placement="top">
          <el-button size="small" type="danger" :icon="Delete" @click="handleDelete(row)" circle />
        </el-tooltip>
      </template>
    </el-table-column>
    <template #empty><el-empty description="暂无任务" /></template>
  </el-table>

  <div v-else class="mobile-card-list">
    <div v-if="loading" v-loading="true" style="min-height:120px" />
    <div v-for="row in tasks" :key="row.id" class="mobile-task-card" @click="showDetail(row)">
      <div class="mobile-card-top">
        <span class="mobile-card-name">{{ row.original_filename }}</span>
        <el-tag :type="statusTag[row.status]?.type" size="small">{{ statusTag[row.status]?.label || row.status }}</el-tag>
      </div>
      <div class="mobile-card-meta">
        <span>#{{ row.id }}</span>
        <span>{{ formatSize(row.file_size) }}</span>
        <span>.{{ row.output_format }}</span>
        <span :class="{ 'live-timer': isLive(row) }">{{ formatDuration(row.started_at, row.completed_at) }}</span>
      </div>
      <div class="mobile-card-time">{{ formatTime(row.created_at) }}</div>
      <div v-if="row.status === 'failed' && row.error_message" class="mobile-card-error">{{ translateError(row.error_message).slice(0, 100) }}</div>
      <div class="mobile-card-actions">
        <el-button size="small" type="success" :icon="View" :disabled="row.status !== 'completed'" @click.stop="handlePreview(row)" circle />
        <el-button size="small" type="primary" :icon="Download" :disabled="row.status !== 'completed'" @click.stop="handleDownload(row)" circle />
        <el-button size="small" type="warning" :icon="RefreshRight" :disabled="row.status !== 'failed' && row.status !== 'completed'" @click.stop="handleRetry(row)" circle />
        <el-button size="small" type="danger" :icon="Delete" @click.stop="handleDelete(row)" circle />
      </div>
    </div>
    <el-empty v-if="!loading && !tasks.length" description="暂无任务" />
  </div>

  <div class="pagination-row" v-if="total > size">
    <el-pagination
      background
      layout="total, sizes, prev, pager, next, jumper"
      :total="total"
      :page-sizes="[20, 50, 100]"
      :page-size="size"
      :current-page="page"
      @current-change="handlePageChange"
      @size-change="(s: number) => { size = s; page = 1; loadTasks() }"
    />
  </div>
  </template>
  </el-card>

<el-dialog v-model="previewVisible" :title="`预览 - ${previewFilename}`" width="75%" top="5vh" destroy-on-close>
  <div v-loading="previewLoading" class="preview-container">
    <div class="preview-toolbar">
      <el-radio-group v-if="previewFormat === 'md'" v-model="previewMode" size="small">
        <el-radio-button value="render">渲染</el-radio-button>
        <el-radio-button value="source">源码</el-radio-button>
      </el-radio-group>
      <div class="preview-search">
        <el-input v-model="previewSearch" placeholder="搜索内容" clearable size="small" style="width:180px" :prefix-icon="Search" />
        <template v-if="previewSearch">
          <span class="search-count">{{ previewSearchMatches ? `${previewSearchIdx}/${previewSearchMatches}` : '无匹配' }}</span>
          <el-button size="small" :icon="ArrowUp" circle @click="previewSearchPrev" :disabled="!previewSearchMatches" />
          <el-button size="small" :icon="ArrowDown" circle @click="previewSearchNext" :disabled="!previewSearchMatches" />
        </template>
      </div>
    </div>
    <div v-if="previewRendering" class="preview-rendering">
      <el-skeleton :rows="10" animated />
    </div>
    <div v-else-if="previewContent && previewFormat === 'md' && previewMode === 'render'" class="md-preview" v-html="renderedPreview" />
    <pre v-else-if="previewContent" class="text-preview" v-html="sourcePreviewHighlighted" />
  </div>
  <template #footer>
    <el-button @click="previewVisible = false">关闭</el-button>
    <el-button type="primary" @click="handleDownload({ id: previewTaskId } as TaskItem)">下载</el-button>
    <el-button type="warning" @click="handleRetryFromPreview">重试</el-button>
  </template>
</el-dialog>

<el-drawer v-model="detailVisible" :title="`任务 #${detailTask?.id || ''} 详情`" size="420px" destroy-on-close>
  <template v-if="detailTask">
    <div class="detail-section">
      <div class="detail-label">文件名</div>
      <div class="detail-value">{{ detailTask.original_filename }}</div>
    </div>
    <div class="detail-row">
      <div class="detail-section"><div class="detail-label">状态</div>
        <el-tag :type="statusTag[detailTask.status]?.type" size="small">{{ statusTag[detailTask.status]?.label }}</el-tag>
      </div>
      <div class="detail-section"><div class="detail-label">大小</div><div class="detail-value">{{ formatSize(detailTask.file_size) }}</div></div>
      <div class="detail-section"><div class="detail-label">输出格式</div><div class="detail-value">.{{ detailTask.output_format }}</div></div>
    </div>

    <el-divider content-position="left">时间线</el-divider>
    <div class="detail-timeline">
      <div v-for="(item, i) in detailTimeline" :key="i" class="timeline-item">
        <span class="timeline-icon">{{ item.icon }}</span>
        <div class="timeline-content">
          <div class="timeline-label">{{ item.label }}</div>
          <div class="timeline-time">{{ item.time }}</div>
        </div>
      </div>
    </div>

    <el-divider content-position="left">MinerU 参数</el-divider>
    <div class="detail-params">
      <div class="param-row"><span class="param-key">backend</span><span class="param-val">{{ detailTask.backend }}</span></div>
      <div class="param-row"><span class="param-key">parse_method</span><span class="param-val">{{ detailTask.parse_method }}</span></div>
      <div class="param-row"><span class="param-key">lang_list</span><span class="param-val">{{ detailTask.lang_list }}</span></div>
      <div class="param-row"><span class="param-key">mineru_api</span><span class="param-val param-long">{{ detailTask.mineru_api }}</span></div>
      <div class="param-row"><span class="param-key">server_url</span><span class="param-val param-long">{{ detailTask.server_url }}</span></div>
      <div class="param-row"><span class="param-key">timeout</span><span class="param-val">{{ detailTask.timeout }}s</span></div>
      <div class="param-row"><span class="param-key">formula_enable</span><span class="param-val">{{ detailTask.formula_enable }}</span></div>
      <div class="param-row"><span class="param-key">table_enable</span><span class="param-val">{{ detailTask.table_enable }}</span></div>
    </div>

    <template v-if="detailTask.error_message">
      <el-divider content-position="left">错误信息</el-divider>
      <div class="detail-error"><pre>{{ translateError(detailTask.error_message) }}</pre></div>
    </template>

    <div class="detail-actions">
      <el-button type="primary" :disabled="detailTask.status !== 'completed'" @click="handleDownload(detailTask); detailVisible = false">下载结果</el-button>
      <el-button type="success" :disabled="detailTask.status !== 'completed'" @click="handlePreview(detailTask); detailVisible = false">预览结果</el-button>
      <el-button type="warning" :disabled="detailTask.status !== 'failed' && detailTask.status !== 'completed'" @click="handleRetry(detailTask); detailVisible = false">重试</el-button>
      <el-button :icon="MagicStick" @click="applyTaskAsPreset(detailTask)">套用参数</el-button>
    </div>
  </template>
</el-drawer>
</template>

<style scoped>
.table-card { border-radius: 10px; height: 100%; }
.summary-bar {
  display: flex; align-items: center; gap: 8px; padding: 8px 0 12px;
  font-size: 13px; color: #606266; flex-wrap: wrap;
}
.summary-divider { color: #dcdfe6; }
.summary-spacer { flex: 1; }
.live-timer { color: #e6a23c; font-variant-numeric: tabular-nums; }
.card-header { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.card-header .filter-row { margin-left: auto; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.card-title { font-weight: 600; }
.pagination-row { display: flex; justify-content: center; margin-top: 16px; }
.preview-container { max-height: 70vh; overflow-y: auto; padding: 16px; background: #fafafa; border-radius: 8px; border: 1px solid #ebeef5; }
.preview-toolbar { margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.preview-search { display: flex; align-items: center; gap: 6px; }
.preview-rendering { padding: 20px 0; }
.search-count { font-size: 12px; color: #909399; white-space: nowrap; }
:deep(.search-highlight) { background: #ffe58f; padding: 1px 2px; border-radius: 2px; }
:deep(.search-highlight.active) { background: #ffc53d; box-shadow: 0 0 0 2px #faad14; }
.md-preview { line-height: 1.8; color: #303133; }
.md-preview :deep(h1) { font-size: 1.5em; border-bottom: 1px solid #ddd; padding-bottom: 8px; margin-top: 16px; }
.md-preview :deep(h2) { font-size: 1.3em; border-bottom: 1px solid #eee; padding-bottom: 6px; margin-top: 14px; }
.md-preview :deep(h3) { font-size: 1.15em; margin-top: 12px; }
.md-preview :deep(code) { background: #f0f0f0; padding: 2px 6px; border-radius: 3px; font-size: 0.9em; }
.md-preview :deep(pre) { background: #f5f7fa; padding: 12px; border-radius: 6px; overflow-x: auto; }
.md-preview :deep(pre code) { background: none; padding: 0; }
.md-preview :deep(blockquote) { border-left: 4px solid #ddd; padding-left: 12px; color: #666; margin: 8px 0; }
.md-preview :deep(table) { border-collapse: collapse; margin: 8px 0; }
.md-preview :deep(th), .md-preview :deep(td) { border: 1px solid #ddd; padding: 6px 10px; }
.md-preview :deep(th) { background: #f5f7fa; }
.md-preview :deep(img) { margin: 8px 0; border-radius: 4px; max-width: 100%; }
.md-preview :deep(hr) { border: none; border-top: 1px solid #ddd; margin: 16px 0; }
.text-preview { white-space: pre-wrap; word-break: break-all; font-size: 13px; line-height: 1.7; margin: 0; }
.task-table { cursor: pointer; }
.detail-row { display: flex; gap: 16px; }
.detail-section { margin-bottom: 12px; }
.detail-label { font-size: 12px; color: #909399; margin-bottom: 4px; }
.detail-value { font-size: 14px; color: #303133; word-break: break-all; }
.detail-timeline { display: flex; flex-direction: column; gap: 10px; padding-left: 4px; }
.timeline-item { display: flex; align-items: flex-start; gap: 10px; }
.timeline-icon { font-size: 16px; flex-shrink: 0; width: 24px; text-align: center; }
.timeline-content { flex: 1; }
.timeline-label { font-size: 13px; color: #303133; font-weight: 500; }
.timeline-time { font-size: 12px; color: #909399; }
.detail-params { display: flex; flex-direction: column; gap: 6px; }
.param-row { display: flex; gap: 8px; font-size: 13px; }
.param-key { color: #909399; width: 100px; flex-shrink: 0; }
.param-val { color: #303133; word-break: break-all; }
.param-long { font-size: 12px; }
.detail-error { background: #fef0f0; border-radius: 6px; padding: 12px; }
.detail-error pre { margin: 0; font-size: 12px; color: #c0392b; white-space: pre-wrap; word-break: break-all; line-height: 1.6; }
.detail-actions { display: flex; gap: 8px; margin-top: 20px; }
.mobile-card-list { display: flex; flex-direction: column; gap: 10px; }
.mobile-task-card {
  background: #fff; border: 1px solid #ebeef5; border-radius: 8px; padding: 12px;
  cursor: pointer; transition: box-shadow 0.2s;
}
.mobile-task-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
.mobile-card-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 6px; }
.mobile-card-name { font-size: 14px; font-weight: 500; color: #303133; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.mobile-card-meta { display: flex; gap: 12px; font-size: 12px; color: #909399; margin-bottom: 4px; }
.mobile-card-time { font-size: 12px; color: #c0c4cc; }
.mobile-card-error { font-size: 12px; color: #f56c6c; margin-top: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mobile-card-actions { display: flex; gap: 6px; margin-top: 8px; padding-top: 8px; border-top: 1px solid #f0f0f0; }
</style>
