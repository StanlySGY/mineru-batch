<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'
import { UploadFilled, Document, Delete, QuestionFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { api } from '../api'
import { requestNotificationPermission } from '../api'
import { useConfig } from '../stores/config'
import { isDocFile, ALLOWED_EXTENSIONS, MAX_FILE_SIZE_MB } from '../utils/file'
import { useRouter } from 'vue-router'
import type { UploadUserFile, UploadProps } from 'element-plus'

const router = useRouter()
const cfg = useConfig()

const fileList = ref<UploadUserFile[]>([])
const uploading = ref(false)
const uploadProgress = ref(0)
const uploadSpeed = ref('')
const uploadEta = ref('')
const showAdvanced = ref(false)
const abortController = ref<AbortController | null>(null)

const presetProxy = ref('')

function onPresetChange(name: string) {
  if (name) {
    cfg.loadPreset(name)
    ElMessage.success(`已加载预设 "${name}"`)
  }
  presetProxy.value = ''
}

const hasDocFiles = computed(() => fileList.value.some(f => isDocFile(f.name)))
const totalSize = computed(() => {
  const bytes = fileList.value.reduce((sum, f) => sum + (f.raw?.size || 0), 0)
  if (!bytes) return ''
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
})

function clearAllFiles() {
  fileList.value = []
}

async function readEntry(entry: any, path: string): Promise<File[]> {
  if (entry.isFile) {
    return new Promise((resolve) => {
      entry.file((file: File) => {
        Object.defineProperty(file, 'webkitRelativePath', { value: path + file.name })
        resolve([file])
      })
    })
  }
  if (entry.isDirectory) {
    const reader = entry.createReader()
    const entries = await new Promise<any[]>((resolve) => reader.readEntries(resolve))
    const files: File[] = []
    for (const e of entries) {
      const sub = await readEntry(e, path + entry.name + '/')
      files.push(...sub)
    }
    return files
  }
  return []
}

async function handleDrop(e: DragEvent) {
  const items = e.dataTransfer?.items
  if (!items) return
  const droppedFiles: File[] = []
  for (const item of Array.from(items)) {
    const entry = (item as any).webkitGetAsEntry?.()
    if (entry) {
      const files = await readEntry(entry, '')
      droppedFiles.push(...files)
    }
  }
  if (!droppedFiles.length) return
  const allowed = droppedFiles.filter(f => {
    const ext = '.' + f.name.split('.').pop()?.toLowerCase()
    return ALLOWED_EXTENSIONS.includes(ext)
  })
  if (!allowed.length) return ElMessage.warning('没有可识别的文件')
  if (fileList.value.length + allowed.length > 200) return ElMessage.warning('最多 200 个文件')
  for (const f of allowed) {
    fileList.value.push({ name: f.webkitRelativePath || f.name, raw: f } as any)
  }
  ElMessage.success(`已添加 ${allowed.length} 个文件`)
}

const handleExceed: UploadProps['onExceed'] = () => {
  ElMessage.warning('最多上传 50 个文件')
}

const beforeUpload: UploadProps['beforeUpload'] = (rawFile) => {
  if (rawFile.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
    ElMessage.error(`文件 "${rawFile.name}" 超过 ${MAX_FILE_SIZE_MB}MB 大小限制`)
    return false
  }
  return true
}

async function handleUpload() {
  const rawFiles = fileList.value.map((f) => f.raw).filter(Boolean) as File[]
  if (!rawFiles.length) return ElMessage.warning('请选择文件')
  uploading.value = true
  uploadProgress.value = 0
  uploadSpeed.value = ''
  uploadEta.value = ''
  abortController.value = new AbortController()

  function buildUploadOpts() {
    return {
      backend: cfg.backend.value,
      mineruApi: cfg.mineruApi.value,
      serverUrl: cfg.serverUrl.value,
      endpoints: cfg.mineruEndpoints.value.filter(e => e.enabled).length > 0
        ? JSON.stringify(cfg.mineruEndpoints.value.filter(e => e.enabled))
        : undefined,
      parseMethod: cfg.parseMethod.value,
      langList: cfg.langList.value,
      formulaEnable: cfg.formulaEnable.value,
      tableEnable: cfg.tableEnable.value,
      returnMd: cfg.returnMd.value,
      returnMiddleJson: cfg.returnMiddleJson.value,
      returnModelOutput: cfg.returnModelOutput.value,
      returnContentList: cfg.returnContentList.value,
      returnImages: cfg.returnImages.value,
      responseFormatZip: cfg.responseFormatZip.value,
      replaceImageUrl: cfg.replaceImageUrl.value,
      startPageId: cfg.startPageId.value,
      endPageId: cfg.endPageId.value,
      outputFormat: cfg.outputFormat.value,
      timeout: cfg.timeout.value,
      autoConvert: cfg.autoConvert.value,
      webhookUrl: (cfg as any).webhookUrl?.value || undefined,
    } as import('../api').UploadOptions
  }

  const MAX_CONCURRENT = 3
  const queue = [...rawFiles]
  const totalFiles = queue.length
  let completed = 0
  let failed = 0
  const allTasks: any[] = []

  async function uploadOne(file: File): Promise<void> {
    try {
      const res = await api.upload([file], buildUploadOpts(), undefined, abortController.value?.signal)
      allTasks.push(...res.tasks)
      completed++
    } catch (e: any) {
      if (e?.code === 'ERR_CANCELED' || e?.name === 'CanceledError') throw e
      failed++
      completed++
      ElMessage.error(`"${file.name}" 上传失败: ${e?.response?.data?.detail || e?.message || '未知错误'}`)
    }
    uploadProgress.value = Math.round((completed / totalFiles) * 100)
  }

  try {
    const workers: Promise<void>[] = []
    for (let i = 0; i < Math.min(MAX_CONCURRENT, queue.length); i++) {
      workers.push((async () => {
        while (queue.length) {
          const file = queue.shift()
          if (!file) break
          if (abortController.value?.signal.aborted) break
          await uploadOne(file)
        }
      })())
    }
    await Promise.all(workers)

    if (completed > 0) {
      const msg = failed > 0
        ? `完成 ${completed} 个，失败 ${failed} 个`
        : `已提交 ${allTasks.length} 个解析任务`
      ElMessage.success(msg)
      requestNotificationPermission()
      fileList.value = []
      router.push('/tasks')
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

onUnmounted(() => {
  if (uploading.value && abortController.value) {
    abortController.value.abort()
  }
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

      <div class="upload-drop-zone" @drop.prevent="handleDrop" @dragover.prevent>
        <el-upload
          v-model:file-list="fileList"
          multiple
          :auto-upload="false"
          :limit="200"
          :accept="ALLOWED_EXTENSIONS"
          :on-exceed="handleExceed"
          :before-upload="beforeUpload"
          drag
          class="upload-dragger"
        >
          <el-icon class="el-icon--upload" :size="48"><UploadFilled /></el-icon>
          <div class="el-upload__text">拖拽文件或文件夹到此处，或 <em>点击选择</em></div>
          <template #tip>
            <div class="el-upload__tip">支持 PDF / 图片 / Word / PPT / Excel，单文件最大 200MB，可直接拖拽文件夹</div>
          </template>
        </el-upload>
      </div>

      <div class="folder-upload-hint">
        <el-upload
          v-model:file-list="fileList"
          :auto-upload="false"
          :limit="200"
          :on-exceed="handleExceed"
          :before-upload="beforeUpload"
          webkitdirectory
          class="folder-btn"
          :show-file-list="false"
        >
          <el-button size="small" plain>选择文件夹上传</el-button>
        </el-upload>
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
          <el-select v-if="cfg.presets.value.length" v-model="presetProxy" placeholder="加载预设" size="small" clearable style="width:140px" @change="onPresetChange">
            <el-option v-for="p in cfg.presets.value" :key="p.name" :label="p.name" :value="p.name" />
          </el-select>
        </div>
      </template>

      <el-form label-position="top" class="config-form">
        <el-form-item>
          <template #label>
            后端类型 (backend)
            <el-tooltip content="hybrid: 纯文本偏多时更快；vlm: 含大量图片和复杂版式时效果更好" placement="top">
              <el-icon style="vertical-align: middle; margin-left: 4px"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-select v-model="cfg.backend.value">
            <el-option value="hybrid-http-client" label="hybrid-http-client" />
            <el-option value="vlm-http-client" label="vlm-http-client" />
          </el-select>
        </el-form-item>

        <el-form-item label="MinerU 服务地址">
          <el-input v-model="cfg.mineruApi.value" />
        </el-form-item>

        <el-form-item label="大模型服务地址 (server_url)">
          <el-input v-model="cfg.serverUrl.value" />
        </el-form-item>

        <el-form-item>
          <template #label>
            解析方式 (parse_method)
            <el-tooltip content="auto: 自动选择；ocr: 强制OCR识别；txt: 纯文本提取" placement="top">
              <el-icon style="vertical-align: middle; margin-left: 4px"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-select v-model="cfg.parseMethod.value">
            <el-option value="auto" label="auto" />
            <el-option value="ocr" label="ocr" />
            <el-option value="txt" label="txt" />
          </el-select>
        </el-form-item>

        <el-form-item label="语言 (lang_list)">
          <el-input v-model="cfg.langList.value" placeholder="ch / en / ch,en" />
        </el-form-item>

        <el-form-item label="输出格式">
          <el-radio-group v-model="cfg.outputFormat.value">
            <el-radio-button value="md">Markdown</el-radio-button>
            <el-radio-button value="txt">纯文本</el-radio-button>
            <el-radio-button value="html">HTML</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="超时时间 (秒)">
          <el-input-number v-model="cfg.timeout.value" :min="60" :max="3600" :step="60" />
          <div class="form-tip">大文件建议 600~1800 秒</div>
        </el-form-item>

        <el-form-item v-if="hasDocFiles" label="文档自动转 PDF">
          <el-switch v-model="cfg.autoConvert.value" />
          <div class="form-tip">关闭后，Word/PPT/Excel 文件需在任务列表手动转换</div>
        </el-form-item>

        <el-link type="primary" :underline="false" @click="showAdvanced = !showAdvanced" style="margin: 4px 0">
          {{ showAdvanced ? '收起高级选项 ▲' : '展开高级选项 ▼' }}
        </el-link>

        <template v-if="showAdvanced">
          <el-form-item label="公式识别"><el-switch v-model="cfg.formulaEnable.value" /></el-form-item>
          <el-form-item label="表格识别"><el-switch v-model="cfg.tableEnable.value" /></el-form-item>
          <el-form-item label="返回 Markdown"><el-switch v-model="cfg.returnMd.value" /></el-form-item>
          <el-form-item label="返回 middle_json"><el-switch v-model="cfg.returnMiddleJson.value" /></el-form-item>
          <el-form-item label="返回模型输出"><el-switch v-model="cfg.returnModelOutput.value" /></el-form-item>
          <el-form-item label="返回 content_list"><el-switch v-model="cfg.returnContentList.value" /></el-form-item>
          <el-form-item label="返回图片"><el-switch v-model="cfg.returnImages.value" /></el-form-item>
          <el-form-item label="ZIP 格式响应"><el-switch v-model="cfg.responseFormatZip.value" /></el-form-item>
          <el-form-item label="替换图片 URL"><el-switch v-model="cfg.replaceImageUrl.value" /></el-form-item>
          <el-form-item label="起始页码"><el-input-number v-model="cfg.startPageId.value" :min="0" :step="1" /></el-form-item>
          <el-form-item label="结束页码"><el-input-number v-model="cfg.endPageId.value" :min="0" :step="1" /></el-form-item>
        </template>

        <el-form-item v-if="uploading">
          <el-progress :percentage="uploadProgress" :stroke-width="10" striped striped-flow />
          <div class="form-tip">上传中... {{ uploadProgress < 100 ? `${uploadProgress}%` : '上传完成，服务端处理中...' }}</div>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" size="large" :loading="uploading" @click="handleUpload" class="submit-btn">
            开始解析
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</div>
</template>

<style scoped>
.upload-page {
  display: grid;
  grid-template-columns: 1fr 380px;
  gap: 20px;
  height: 100%;
}
.upload-card { border-radius: 10px; }
.config-card { border-radius: 10px; overflow-y: auto; }
.config-form { display: flex; flex-direction: column; gap: 2px; }
.submit-btn { width: 100%; margin-top: 8px; }
.upload-dragger :deep(.el-upload-dragger) { padding: 40px 0; border-radius: 8px; }
.upload-drop-zone { position: relative; }
.upload-drop-zone::after {
  content: ''; position: absolute; inset: 0; border-radius: 8px;
  border: 2px dashed transparent; transition: border-color 0.2s; pointer-events: none;
}
.upload-drop-zone:hover::after { border-color: #409eff; }
.card-header-row { display: flex; align-items: center; gap: 10px; }
.card-title { font-weight: 600; }

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
.form-tip { font-size: 12px; color: #909399; margin-top: 2px; }
.folder-upload-hint { display: flex; justify-content: center; margin-top: 8px; }

@media (max-width: 800px) {
  .upload-page { grid-template-columns: 1fr; }
}
</style>
