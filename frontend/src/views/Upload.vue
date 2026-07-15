<script setup lang="ts">
import { ref, computed, onUnmounted, onMounted, nextTick } from 'vue'
import { UploadFilled, Document, Delete } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api'
import { requestNotificationPermission } from '../api'
import { useConfig } from '../stores/config'
import type { MineruEndpoint } from '../stores/config'
import { isDocFile, ALLOWED_EXTENSIONS } from '../utils/file'
import { classifyNodeLatency, isNodeAvailable, type NodePing } from '../utils/nodeHealth'
import { useRouter } from 'vue-router'
import type { UploadUserFile } from 'element-plus'
import ConfigPanel from '../components/ConfigPanel.vue'

const router = useRouter()
const cfg = useConfig()

const fileList = ref<UploadUserFile[]>([])
const uploading = ref(false)
const uploadProgress = ref(0)
const uploadSpeed = ref('')
const uploadEta = ref('')
const uploadFileProgress = ref<Record<number, number>>({})
const uploadCurrentFile = ref('')
const abortController = ref<AbortController | null>(null)
const batchName = ref('')

const fileInputRef = ref<HTMLInputElement | null>(null)
const folderInputRef = ref<HTMLInputElement | null>(null)
const isDragging = ref(false)
const dragCounter = ref(0)

// 解析场景预设
interface ProfileItem { label: string; desc: string; config: Record<string, any>; custom?: boolean }
const CUSTOM_PROFILES_KEY = 'upload_custom_profiles'
const BUILTIN_PROFILES: Record<string, ProfileItem> = {
  easyDataset: {
    label: 'easy-dataset', desc: '推荐：轻量 Markdown，可直接批量导入数据集',
    config: { parseMethod: 'auto', formulaEnable: true, tableEnable: true, returnMd: true, returnMiddleJson: false, returnModelOutput: false, returnContentList: false, returnImages: false, responseFormatZip: false, replaceImageUrl: false, outputFormat: 'md' },
  },
  none: { label: '全局默认', desc: '使用设置页的当前配置', config: {} },
  academic: {
    label: '学术论文', desc: '公式/表格全开，保留完整结构信息',
    config: { parseMethod: 'auto', formulaEnable: true, tableEnable: true, returnMd: true, returnMiddleJson: true, returnImages: true },
  },
  plaintext: {
    label: '纯文本', desc: '仅提取文字，关闭格式识别和图片',
    config: { parseMethod: 'txt', formulaEnable: false, tableEnable: false, returnMd: false, returnMiddleJson: false, returnModelOutput: false, returnContentList: false, returnImages: false, responseFormatZip: false, replaceImageUrl: false, outputFormat: 'txt' },
  },
  ocr: {
    label: '扫描件 OCR', desc: '强制 OCR 识别，适用于扫描件/拍照文档',
    config: { parseMethod: 'ocr', formulaEnable: true, tableEnable: true, returnMd: true, returnImages: true },
  },
}
const customProfiles = ref<Record<string, ProfileItem>>(loadCustomProfiles())
const PROFILES = computed<Record<string, ProfileItem>>(() => ({ ...BUILTIN_PROFILES, ...customProfiles.value }))
const selectedProfile = ref<string>('easyDataset')

function loadCustomProfiles(): Record<string, ProfileItem> {
  try {
    const raw = localStorage.getItem(CUSTOM_PROFILES_KEY)
    const parsed = raw ? JSON.parse(raw) : {}
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    return Object.fromEntries(Object.entries(parsed).filter(([, v]: any) => v?.label && v?.config)) as Record<string, ProfileItem>
  } catch {
    return {}
  }
}

function saveCustomProfiles() {
  localStorage.setItem(CUSTOM_PROFILES_KEY, JSON.stringify(customProfiles.value))
}

async function saveCurrentProfile() {
  try {
    const { value } = await ElMessageBox.prompt('为当前解析配置命名，之后可一键复用。', '保存自定义预设', {
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputPattern: /^.{1,24}$/,
      inputErrorMessage: '请输入 1-24 个字符',
    })
    const id = `custom_${Date.now()}`
    customProfiles.value[id] = {
      label: value.trim(),
      desc: '自定义预设：基于当前解析配置保存',
      config: { ...cfg.getCurrentConfig() },
      custom: true,
    }
    selectedProfile.value = id
    saveCustomProfiles()
    ElMessage.success('已保存自定义预设')
  } catch {}
}

function removeCustomProfile(key: string) {
  delete customProfiles.value[key]
  if (selectedProfile.value === key) selectedProfile.value = 'easyDataset'
  saveCustomProfiles()
  ElMessage.success('已删除自定义预设')
}

// 当前上传会话的配置 = 全局默认 + 场景预设覆盖
const sessionConfig = computed(() => ({
  ...cfg.getCurrentConfig(),
  ...PROFILES.value[selectedProfile.value]?.config,
}))

// 每批上传独立选择的节点列表，不从 store 持久化
const nodePings = ref<Record<string, NodePing>>({})

const selectedEndpoints = ref<MineruEndpoint[]>(
  cfg.mineruEndpoints.value.filter(e => e.enabled)
)

const enabledEndpoints = computed(() => cfg.mineruEndpoints.value.filter(e => e.enabled))
const selectedAvailableEndpoints = computed(() => selectedEndpoints.value.filter(ep => ep.enabled && isNodeAvailable(nodePings.value[ep.url])))
const selectedUnavailableCount = computed(() => selectedEndpoints.value.length - selectedAvailableEndpoints.value.length)
const canStartUpload = computed(() => !uploading.value && fileList.value.length > 0 && selectedAvailableEndpoints.value.length > 0)
const uploadedBatchId = ref<string | null>(null)
const canStartParse = computed(() => !uploading.value && uploadedBatchId.value !== null)

function toggleEndpoint(url: string) {
  const found = cfg.mineruEndpoints.value.find(e => e.url === url)
  if (!found?.enabled) return
  const idx = selectedEndpoints.value.findIndex(e => e.url === url)
  if (idx >= 0) {
    selectedEndpoints.value.splice(idx, 1)
  } else {
    selectedEndpoints.value.push({ ...found })
  }
}

const totalSize = computed(() => {
  const bytes = fileList.value.reduce((sum, f) => sum + (f.raw?.size || 0), 0)
  if (!bytes) return ''
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
})

function clearAllFiles() {
  fileList.value = []
}

// 拖拽文件夹时，将路径信息存储在 File 对象上
interface FileWithPath extends File { _folderPath?: string }

async function readEntry(entry: any, path: string): Promise<FileWithPath[]> {
  if (entry.isFile) {
    return new Promise((resolve) => {
      entry.file((file: FileWithPath) => {
        file._folderPath = path + file.name
        resolve([file])
      })
    })
  }
  if (entry.isDirectory) {
    const reader = entry.createReader()
    const allEntries: any[] = []
    // readEntries 可能需要多次调用才能读完
    let batch: any[]
    do {
      batch = await new Promise<any[]>((resolve) => reader.readEntries(resolve))
      allEntries.push(...batch)
    } while (batch.length > 0)
    const files: FileWithPath[] = []
    for (const e of allEntries) {
      const sub = await readEntry(e, path + entry.name + '/')
      files.push(...sub)
    }
    return files
  }
  return []
}

function triggerFileSelect() {
  fileInputRef.value?.click()
}

function triggerFolderSelect() {
  folderInputRef.value?.click()
}

function handleDragEnter() {
  dragCounter.value++
  isDragging.value = true
}

function handleDragLeave() {
  dragCounter.value--
  if (dragCounter.value <= 0) {
    isDragging.value = false
    dragCounter.value = 0
  }
}

function addFiles(files: File[]) {
  const allowed = files.filter(f => {
    const ext = '.' + f.name.split('.').pop()?.toLowerCase()
    return ALLOWED_EXTENSIONS.includes(ext)
  })

  if (!allowed.length) {
    ElMessage.warning('没有可识别的合法文件类型')
    return
  }

  const oversized = allowed.filter(f => f.size > cfg.state.maxFileSize * 1024 * 1024)
  if (oversized.length > 0) {
    ElMessage.error(`有 ${oversized.length} 个文件超过了 ${cfg.state.maxFileSize}MB 的大小限制`)
    return
  }

  if (fileList.value.length + allowed.length > 200) {
    ElMessage.warning('最多 200 个文件')
    return
  }

  for (const f of allowed) {
    fileList.value.push({ name: (f as FileWithPath)._folderPath || f.name, raw: f } as any)
  }

  ElMessage.success(`已添加 ${allowed.length} 个文件`)

  // 自动开始上传（静默进行，上传后等待用户点击开始解析）
  if (!uploading.value && selectedAvailableEndpoints.value.length > 0) {
    nextTick(() => handleUpload(true))
  }
}

function handleFileSelect(e: Event) {
  const target = e.target as HTMLInputElement
  if (target.files && target.files.length) {
    addFiles(Array.from(target.files))
  }
  target.value = ''
}

function handleFolderSelect(e: Event) {
  const target = e.target as HTMLInputElement
  if (target.files && target.files.length) {
    const files = Array.from(target.files).map(f => {
      const pathFile = f as FileWithPath
      if (f.webkitRelativePath) {
        pathFile._folderPath = f.webkitRelativePath
      }
      return pathFile
    })
    addFiles(files)
  }
  target.value = ''
}

async function handleDrop(e: DragEvent) {
  isDragging.value = false
  dragCounter.value = 0
  
  const items = e.dataTransfer?.items
  if (!items) return
  
  const droppedFiles: FileWithPath[] = []
  for (const item of Array.from(items)) {
    const entry = (item as any).webkitGetAsEntry?.()
    if (entry) {
      const files = await readEntry(entry, '')
      droppedFiles.push(...files)
    }
  }
  
  if (!droppedFiles.length) return
  addFiles(droppedFiles)
}

async function handleUpload(autoParse = false) {
  const rawFiles = fileList.value.map((f) => f.raw).filter(Boolean) as File[]
  if (!rawFiles.length) return ElMessage.warning('请选择文件')
  if (!enabledEndpoints.value.length) return ElMessage.warning('没有启用的解析节点，请先在设置页启用节点')
  if (!selectedEndpoints.value.length) return ElMessage.warning('请至少选择一个解析节点')
  if (!selectedAvailableEndpoints.value.length) return ElMessage.warning('已选择的解析节点当前不可用，请检查节点状态')
  uploading.value = true
  uploadProgress.value = 0
  uploadSpeed.value = ''
  uploadEta.value = ''
  uploadFileProgress.value = {}
  uploadCurrentFile.value = ''
  abortController.value = new AbortController()
  const batchId = crypto.randomUUID ? crypto.randomUUID().replace(/-/g, '') : `${Date.now()}${Math.random().toString(16).slice(2)}`

  function buildUploadOpts() {
    const sc = sessionConfig.value
    return {
      backend: sc.backend,
      mineruApi: sc.mineruApi,
      serverUrl: sc.serverUrl,
      endpoints: JSON.stringify(selectedAvailableEndpoints.value),
      parseMethod: sc.parseMethod,
      langList: sc.langList,
      formulaEnable: sc.formulaEnable,
      tableEnable: sc.tableEnable,
      returnMd: sc.returnMd,
      returnMiddleJson: sc.returnMiddleJson,
      returnModelOutput: sc.returnModelOutput,
      returnContentList: sc.returnContentList,
      returnImages: sc.returnImages,
      responseFormatZip: sc.responseFormatZip,
      replaceImageUrl: sc.replaceImageUrl,
      startPageId: sc.startPageId,
      endPageId: sc.endPageId,
      outputFormat: sc.outputFormat,
      timeout: sc.timeout,
      autoConvert: sc.autoConvert,
      batchId,
      batchName: batchName.value.trim() || undefined,
      autoParse,
    } as import('../api').UploadOptions
  }

  const totalSize = rawFiles.reduce((sum, f) => sum + f.size, 0)
  const fileSizes = rawFiles.map(f => f.size)
  const MAX_CONCURRENT = 3
  const queue = rawFiles.map((f, i) => ({ file: f, idx: i }))
  const totalFiles = queue.length
  let completed = 0
  let failed = 0
  const allTasks: any[] = []

  function updateOverallProgress() {
    // 字节级进度：所有文件已完成字节 / 总字节
    let loadedTotal = 0
    for (let i = 0; i < totalFiles; i++) {
      const fp = uploadFileProgress.value[i]
      if (fp !== undefined) {
        // fp 是百分比，转为字节
        loadedTotal += (fp / 100) * fileSizes[i]
      }
    }
    uploadProgress.value = totalSize > 0 ? Math.min(99, Math.round((loadedTotal / totalSize) * 100)) : 0
  }

  async function uploadOne(file: File, fileIdx: number): Promise<void> {
    uploadCurrentFile.value = file.name
    try {
      const res = await api.upload(
        [file],
        buildUploadOpts(),
        (p) => {
          uploadFileProgress.value[fileIdx] = p.pct
          updateOverallProgress()
          if (p.speed > 0) uploadSpeed.value = formatSpeed(p.speed)
          if (p.eta > 0 && p.eta < 3600) uploadEta.value = formatEta(p.eta)
        },
        abortController.value?.signal,
      )
      allTasks.push(...res.tasks)
      uploadFileProgress.value[fileIdx] = 100
      completed++
    } catch (e: any) {
      if (e?.code === 'ERR_CANCELED' || e?.name === 'CanceledError') throw e
      uploadFileProgress.value[fileIdx] = 100
      failed++
      completed++
      ElMessage.error(`"${file.name}" 上传失败: ${e?.response?.data?.detail || e?.message || '未知错误'}`)
    }
    updateOverallProgress()
  }

  function formatSpeed(bytesPerSec: number): string {
    if (bytesPerSec < 1024) return bytesPerSec.toFixed(0) + ' B/s'
    if (bytesPerSec < 1024 * 1024) return (bytesPerSec / 1024).toFixed(1) + ' KB/s'
    return (bytesPerSec / 1024 / 1024).toFixed(1) + ' MB/s'
  }

  function formatEta(seconds: number): string {
    if (seconds < 60) return Math.ceil(seconds) + 's'
    if (seconds < 3600) return Math.ceil(seconds / 60) + 'min'
    return Math.floor(seconds / 3600) + 'h'
  }

  try {
    const workers: Promise<void>[] = []
    for (let i = 0; i < Math.min(MAX_CONCURRENT, queue.length); i++) {
      workers.push((async () => {
        while (queue.length) {
          const item = queue.shift()
          if (!item) break
          if (abortController.value?.signal.aborted) break
          await uploadOne(item.file, item.idx)
        }
      })())
    }
    await Promise.all(workers)

    if (completed > 0) {
      uploadProgress.value = 100
      uploadSpeed.value = ''
      uploadEta.value = ''
      if (autoParse) {
        const msg = failed > 0
          ? `完成 ${completed} 个，失败 ${failed} 个`
          : `已提交 ${allTasks.length} 个解析任务`
        ElMessage.success(msg)
        requestNotificationPermission()
        fileList.value = []
        batchName.value = ''
        router.push('/tasks')
      } else {
        uploadedBatchId.value = batchId
        ElMessage.success(`已上传 ${completed} 个文件，点击"开始解析"进行解析`)
        fileList.value = []
        batchName.value = ''
      }
    }
  } catch (e: any) {
    if (e?.code === 'ERR_CANCELED' || e?.name === 'CanceledError') {
      ElMessage.info('上传已取消')
    }
  } finally {
    uploading.value = false
    abortController.value = null
  }
}

async function handleStartParse() {
  if (!uploadedBatchId.value) return
  try {
    const res = await api.startParse(uploadedBatchId.value)
    ElMessage.success(`已提交 ${res.enqueued} 个任务进行解析`)
    uploadedBatchId.value = null
    requestNotificationPermission()
    router.push('/tasks')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '开始解析失败')
  }
}

function handleKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    e.preventDefault()
    if (canStartParse.value) handleStartParse()
    else if (canStartUpload.value) handleUpload()
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  if (uploading.value && abortController.value) {
    abortController.value.abort()
  }
  window.removeEventListener('keydown', handleKeydown)
})

async function pingAllNodes() {
  cfg.mineruEndpoints.value.forEach(async (ep) => {
    nodePings.value[ep.url] = { latency: null, status: 'testing' }
    const startTime = Date.now()
    try {
      const res = await api.testConnection({ mineru_api: ep.url, server_url: ep.serverUrl })
      const elapsed = Date.now() - startTime
      if (res.ok) {
        nodePings.value[ep.url] = { latency: elapsed, status: classifyNodeLatency(elapsed) }
      } else {
        nodePings.value[ep.url] = { latency: null, status: 'red' }
      }
    } catch {
      nodePings.value[ep.url] = { latency: null, status: 'red' }
    }
  })
}

onMounted(() => {
  pingAllNodes()
})
</script>

<template>
<div class="upload-page">
  <div class="upload-left">
    <el-card shadow="never" class="upload-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">上传文件</span>
          <el-tag v-if="fileList.length" type="info" size="small">{{ fileList.length }} 个文件</el-tag>
        </div>
      </template>

      <el-form label-position="top" class="batch-form" @submit.prevent>
        <el-form-item label="批次名称（可选）">
          <el-input v-model="batchName" maxlength="80" show-word-limit placeholder="例如：产品手册入库-2026-05" />
        </el-form-item>
      </el-form>

      <div v-if="!fileList.length" class="quick-start-card">
        <div class="quick-start-title">easy-dataset 快速流程</div>
        <div class="quick-start-steps">
          <span>1. 拖入 PDF/文档文件夹</span>
          <span>2. 使用右侧 easy-dataset 预设</span>
          <span>3. 完成后在任务页导出 Markdown ZIP</span>
        </div>
      </div>

      <div
        class="upload-drop-zone"
        :class="{ 'is-dragging': isDragging }"
        @dragenter.prevent="handleDragEnter"
        @dragleave.prevent="handleDragLeave"
        @dragover.prevent
        @drop.prevent="handleDrop"
        @click="triggerFileSelect"
      >
        <input
          type="file"
          ref="fileInputRef"
          multiple
          :accept="ALLOWED_EXTENSIONS"
          style="display: none;"
          @change="handleFileSelect"
        />
        
        <el-icon class="el-icon--upload" :size="48"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖拽文件或文件夹到此处，或 <em>点击选择</em></div>
        <div class="el-upload__tip">支持 PDF / 图片 / Word / PPT / Excel，单文件最大 200MB，可直接拖拽文件夹</div>
      </div>

      <div class="folder-upload-hint">
        <input
          type="file"
          ref="folderInputRef"
          webkitdirectory
          multiple
          style="display: none;"
          @change="handleFolderSelect"
        />
        <el-button size="small" plain @click="triggerFolderSelect">选择文件夹上传</el-button>
      </div>

      <div v-if="fileList.length" class="file-list-section">
        <div class="file-list-header">
          <span>待上传文件</span>
          <span class="file-summary">
            <span v-if="totalSize">共 {{ totalSize }}</span>
            <el-button size="small" text type="danger" @click="clearAllFiles">清空全部</el-button>
          </span>
        </div>
        <div class="file-list-scroll">
          <div v-for="(f, idx) in fileList" :key="idx" class="file-row">
            <el-icon :size="16" class="file-icon"><Document /></el-icon>
            <span class="file-name" :title="f.name">{{ f.name }}</span>
            <el-tag v-if="isDocFile(f.name)" type="warning" size="small" class="doc-tag">文档</el-tag>
            <el-button
              size="small"
              type="danger"
              :icon="Delete"
              circle
              plain
              @click="fileList.splice(idx, 1)"
              class="file-remove"
            />
          </div>
        </div>
      </div>
    </el-card>
  </div>

  <div class="upload-right">
    <el-card shadow="never" class="config-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">解析配置</span>
          <el-tag v-if="cfg.mineruEndpoints.value.length" size="small" type="info" effect="plain">
            {{ cfg.mineruEndpoints.value.length }} 节点
          </el-tag>
        </div>
      </template>

      <!-- 解析场景 -->
      <div class="card-section">
        <div class="section-title-row">
          <div class="section-label">解析场景</div>
          <el-button size="small" text type="primary" @click="saveCurrentProfile">保存当前配置</el-button>
        </div>
        <div class="profile-selector">
          <div v-for="(p, key) in PROFILES" :key="key"
            class="profile-card"
            :class="{ active: selectedProfile === key }"
            @click="selectedProfile = key"
          >
            <div class="profile-label-row">
              <div class="profile-label">{{ p.label }}</div>
              <el-button v-if="p.custom" size="small" text type="danger" @click.stop="removeCustomProfile(String(key))">删除</el-button>
            </div>
            <div class="profile-desc">{{ p.desc }}</div>
          </div>
        </div>
      </div>

      <!-- 节点选择 -->
      <div v-if="cfg.mineruEndpoints.value.length" class="card-section">
        <div class="section-label">选择解析节点</div>
        <div class="node-list">
          <div
            v-for="ep in cfg.mineruEndpoints.value"
            :key="ep.url"
            class="node-row"
            :class="{ selected: selectedEndpoints.some(e => e.url === ep.url), disabled: !ep.enabled, unavailable: nodePings[ep.url]?.status === 'red' }"
            @click="toggleEndpoint(ep.url)"
          >
            <el-checkbox
              :model-value="selectedEndpoints.some(e => e.url === ep.url)"
              :disabled="!ep.enabled"
              size="small"
              @click.stop
              @change="toggleEndpoint(ep.url)"
            />
            <div class="node-info">
              <span class="node-url">{{ ep.url }}</span>
              <span class="node-meta">{{ ep.backend }} · {{ ep.enabled ? '启用' : '禁用' }}</span>
            </div>
            <!-- Ping Status Indicator -->
            <div v-if="nodePings[ep.url]" class="node-ping-badge" :class="nodePings[ep.url].status">
              <span class="ping-dot" />
              <span class="ping-text">
                <template v-if="nodePings[ep.url].status === 'testing'">测速中...</template>
                <template v-else-if="nodePings[ep.url].latency !== null">{{ nodePings[ep.url].latency }}ms</template>
                <template v-else>不可用</template>
              </span>
            </div>
          </div>
        </div>
        <div v-if="!enabledEndpoints.length" class="form-tip warn">没有启用的节点，请先在设置页启用</div>
        <div v-else-if="!selectedEndpoints.length" class="form-tip warn">请至少选择一个节点</div>
        <div v-else-if="selectedUnavailableCount" class="form-tip warn">{{ selectedUnavailableCount }} 个已选节点不可用，上传时会自动跳过</div>
      </div>
      <div v-else class="card-section">
        <div class="no-nodes">
          <span>未配置解析节点，暂时无法开始上传解析</span>
          <el-button type="primary" size="small" plain @click="$router.push('/settings')">去设置页配置</el-button>
        </div>
      </div>

      <ConfigPanel :config="sessionConfig" :endpoints="selectedAvailableEndpoints" />

      <div v-if="uploading" class="card-section">
        <el-progress :percentage="uploadProgress" :stroke-width="10" striped striped-flow />
        <div class="upload-status">
          <span v-if="uploadProgress < 100">
            {{ uploadCurrentFile ? `正在上传: ${uploadCurrentFile.split('/').pop()}` : '准备中...' }}
            {{ uploadSpeed ? ` · ${uploadSpeed}` : '' }}
            {{ uploadEta ? ` · 剩余 ${uploadEta}` : '' }}
          </span>
          <span v-else>上传完成，服务端处理中...</span>
        </div>
      </div>

      <div class="card-section">
        <el-button v-if="canStartParse" type="success" size="large" @click="handleStartParse" class="submit-btn">
          开始解析 <span class="shortcut-hint">Ctrl+↵</span>
        </el-button>
        <el-button v-else type="primary" size="large" :loading="uploading" :disabled="!canStartUpload" @click="handleUpload" class="submit-btn">
          开始解析 <span class="shortcut-hint">Ctrl+↵</span>
        </el-button>
      </div>
    </el-card>
  </div>
</div>
</template>

<style scoped>
.upload-page {
  display: grid;
  grid-template-columns: 1fr 380px;
  gap: 20px;
}
.upload-card { border-radius: 10px; }
.config-card { border-radius: 10px; overflow-y: auto; }
.submit-btn { width: 100%; margin-top: 8px; }
.shortcut-hint {
  font-size: 11px;
  opacity: 0.6;
  margin-left: 6px;
  font-weight: 400;
}
.upload-drop-zone {
  position: relative;
  border: 2px dashed #dcdfe6;
  border-radius: 16px;
  padding: 48px 24px;
  text-align: center;
  cursor: pointer;
  background: #ffffff;
  transition: all 0.4s cubic-bezier(0.25, 0.8, 0.25, 1);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.02);
  overflow: hidden;
}

/* 彻底杜绝子元素拖拽闪烁的终极秘籍 */
.upload-drop-zone * {
  pointer-events: none;
}

.upload-drop-zone:hover {
  border-color: #409eff;
  background: #fcfdfe;
  box-shadow: 0 6px 16px rgba(64, 158, 255, 0.05);
  transform: translateY(-2px);
}

/* 尊贵流光呼吸效果伪元素 */
.upload-drop-zone::before {
  content: "";
  position: absolute;
  inset: -2px;
  border-radius: 16px;
  padding: 2px;
  background: linear-gradient(135deg, #409eff, #67c23a, #e6a23c, #409eff);
  background-size: 300% 300%;
  -webkit-mask: 
     linear-gradient(#fff 0 0) content-box, 
     linear-gradient(#fff 0 0);
  -webkit-mask-composite: xor;
          mask-composite: exclude;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.4s ease;
  animation: flowing-light 4s linear infinite;
}

.upload-drop-zone.is-dragging {
  border-color: transparent;
  background: #ffffff;
  box-shadow: 0 10px 30px rgba(64, 158, 255, 0.15);
  transform: scale(1.015);
}

.upload-drop-zone.is-dragging::before {
  opacity: 1;
}

@keyframes flowing-light {
  0% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
}

.el-icon--upload {
  color: #909399;
  transition: color 0.4s, transform 0.4s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.upload-drop-zone:hover .el-icon--upload,
.upload-drop-zone.is-dragging .el-icon--upload {
  color: #409eff;
  transform: translateY(-4px) scale(1.05);
}

.el-upload__text {
  font-size: 14px;
  color: #606266;
  user-select: none;
}

.el-upload__text em {
  color: #409eff;
  font-style: normal;
  font-weight: 500;
}

.el-upload__tip {
  font-size: 12px;
  color: #909399;
  user-select: none;
  margin-top: 4px;
}
.card-header-row { display: flex; align-items: center; gap: 10px; }
.card-title { font-weight: 600; }
.quick-start-card {
  margin-bottom: 12px; padding: 12px; border-radius: 10px;
  background: #f0f9eb; border: 1px solid #d1edc4; color: #529b2e;
}
.quick-start-title { font-size: 13px; font-weight: 600; margin-bottom: 6px; }
.quick-start-steps { display: flex; flex-direction: column; gap: 4px; font-size: 12px; line-height: 1.4; }

.profile-selector { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.section-title-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
.section-title-row .section-label { margin-bottom: 0; }
.profile-card {
  padding: 8px 10px; border-radius: 8px; cursor: pointer;
  border: 1.5px solid #e4e7ed; transition: all 0.15s; background: #fff;
}
.profile-card:hover { border-color: #409eff; }
.profile-card.active { border-color: #409eff; background: #ecf5ff; }
.profile-label-row { display: flex; align-items: center; justify-content: space-between; gap: 6px; margin-bottom: 2px; }
.profile-label { font-size: 13px; font-weight: 600; color: #303133; }
.profile-card.active .profile-label { color: #409eff; }
.profile-desc { font-size: 11px; color: #909399; line-height: 1.3; }

.file-list-section { margin-top: 16px; border-top: 1px solid #f0f0f0; padding-top: 12px; }
.file-list-header { font-size: 13px; font-weight: 600; color: #606266; margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between; }
.file-summary { display: flex; align-items: center; gap: 8px; font-weight: 400; color: #909399; font-size: 12px; }
.file-list-scroll { max-height: 240px; overflow-y: auto; }
.file-row {
  display: flex; align-items: center; gap: 8px; padding: 6px 8px;
  border-radius: 6px; transition: background 0.15s; font-size: 13px;
}
.file-row:hover { background: #f5f7fa; }
.file-icon { color: #909399; flex-shrink: 0; }
.file-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #303133; }
.doc-tag { flex-shrink: 0; }
.file-remove { flex-shrink: 0; }
.card-section { margin-top: 12px; }
.form-tip { font-size: 12px; color: #909399; margin-top: 2px; }
.form-tip.warn { color: #e6a23c; }
.upload-status { font-size: 12px; color: #909399; margin-top: 4px; display: flex; align-items: center; gap: 4px; min-height: 18px; }
.folder-upload-hint { display: flex; justify-content: center; margin-top: 12px; }
.section-label { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: #909399; margin-bottom: 8px; }

.node-list { display: flex; flex-direction: column; gap: 4px; }
.node-row {
  display: flex; align-items: center; gap: 8px; padding: 6px 8px;
  border-radius: 6px; cursor: pointer; transition: all 0.15s;
  border: 1px solid transparent;
}
.node-row:hover { background: #f5f7fa; border-color: #e4e7ed; }
.node-row.selected { background: #ecf5ff; border-color: #409eff; }
.node-row.disabled { cursor: not-allowed; opacity: 0.55; }
.node-row.disabled:hover { background: transparent; border-color: transparent; }
.node-row.unavailable:not(.disabled) { border-color: #fcd3d3; }
.node-info { display: flex; flex-direction: column; gap: 1px; min-width: 0; flex: 1; }
.node-url { font-size: 12px; color: #303133; font-weight: 500; word-break: break-all; }
.node-meta { font-size: 11px; color: #909399; }

.no-nodes { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 16px 0; font-size: 13px; color: #909399; }

/* Node Ping Badges & Status Dots */
.node-ping-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 10px;
  background: #f4f4f5;
  color: #909399;
  flex-shrink: 0;
}
.node-ping-badge.testing {
  background: #f4f4f5;
  color: #909399;
}
.node-ping-badge.green {
  background: #e1f3d8;
  color: #67c23a;
}
.node-ping-badge.yellow {
  background: #faecd8;
  color: #e6a23c;
}
.node-ping-badge.red {
  background: #fde2e2;
  color: #f56c6c;
}
.ping-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  display: inline-block;
}
.node-ping-badge.testing .ping-dot {
  animation: pulse 1.2s infinite ease-in-out;
}
@keyframes pulse {
  0% { transform: scale(0.8); opacity: 0.5; }
  50% { transform: scale(1.2); opacity: 1; }
  100% { transform: scale(0.8); opacity: 0.5; }
}

@media (max-width: 800px) {
  .upload-page { grid-template-columns: 1fr; }
}
</style>
