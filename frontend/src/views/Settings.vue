<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { Connection, Plus, Delete, Download, Upload } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useConfig } from '../stores/config'
import { formatSize as formatStorage } from '../utils/format'
import { classifyNodeLatency, type NodePing } from '../utils/nodeHealth'
import { api } from '../api'
import type { ServerSettings } from '../api'

const cfg = useConfig()

const testing = ref<number | null>(null)
const testingAll = ref(false)
const nodePings = ref<Record<number, NodePing>>({})
const concurrency = ref(5)
const storage = ref<{ uploads: number; outputs: number; converted: number; database: number; total: number } | null>(null)
const savingSettings = ref(false)
const adminKeyInput = ref(api.getAdminKey())
const securityStatus = ref<{ adminRequired: boolean; allowPrivateEndpoints: boolean } | null>(null)
const hasAdminKey = computed(() => adminKeyInput.value.trim().length > 0)

async function loadSecurityStatus() {
  try {
    securityStatus.value = await api.getSecurityStatus()
  } catch {}
}

function saveAdminKey() {
  api.setAdminKey(adminKeyInput.value)
  adminKeyInput.value = api.getAdminKey()
  ElMessage.success(adminKeyInput.value ? '管理员 Key 已保存到本机浏览器' : '管理员 Key 已清除')
}

async function loadServerSettings() {
  try {
    const settings = await api.getSettings()
    cfg.applyServerSettings(settings as any)
  } catch {}
}

async function saveServerSettings(showSuccess = true) {
  savingSettings.value = true
  try {
    const saved = await api.saveSettings(cfg.exportServerSettings() as ServerSettings)
    cfg.applyServerSettings(saved as any)
    if (showSuccess) ElMessage.success('配置已保存到服务端')
  } finally {
    savingSettings.value = false
  }
}

async function loadConcurrency() {
  try {
    const res = await api.getConcurrency()
    concurrency.value = res.concurrency
  } catch {}
}

async function handleConcurrencyChange() {
  try {
    await api.setConcurrency(concurrency.value)
    ElMessage.success(`并发数已设置为 ${concurrency.value}`)
  } catch {
    ElMessage.error('设置并发数失败')
  }
}

async function handleTestEndpoint(idx: number) {
  const ep = cfg.mineruEndpoints.value[idx]
  if (!ep) return
  testing.value = idx
  nodePings.value[idx] = { latency: null, status: 'testing' }
  const start = Date.now()
  try {
    const res = await api.testConnection({ mineru_api: ep.url, server_url: ep.serverUrl })
    const elapsed = Date.now() - start
    if (res.ok) {
      nodePings.value[idx] = { latency: elapsed, status: classifyNodeLatency(elapsed), mineru: res.detail?.mineru, server: res.detail?.server }
      ElMessage.success(`节点 ${idx + 1} 连接正常 (${elapsed}ms)`)
    } else {
      nodePings.value[idx] = { latency: null, status: 'red', mineru: res.detail?.mineru, server: res.detail?.server }
      ElMessage.error(`节点 ${idx + 1} 异常: ${res.error || '未知错误'}`)
    }
  } catch (e: any) {
    nodePings.value[idx] = { latency: null, status: 'red' }
    ElMessage.error(e?.response?.data?.detail || '测试连接失败')
  } finally {
    testing.value = null
  }
}

async function handleTestAllEndpoints() {
  testingAll.value = true
  const activeNodes = cfg.mineruEndpoints.value
    .map((ep, idx) => ({ ep, idx }))
    .filter(({ ep }) => ep.enabled)
  
  await Promise.all(
    activeNodes.map(async ({ ep, idx }) => {
      nodePings.value[idx] = { latency: null, status: 'testing' }
      const start = Date.now()
      try {
        const res = await api.testConnection({ mineru_api: ep.url, server_url: ep.serverUrl })
        const elapsed = Date.now() - start
        if (res.ok) {
          nodePings.value[idx] = { latency: elapsed, status: classifyNodeLatency(elapsed) }
        } else {
          nodePings.value[idx] = { latency: null, status: 'red' }
        }
      } catch {
        nodePings.value[idx] = { latency: null, status: 'red' }
      }
    })
  )
  testingAll.value = false
}

async function loadStorage() {
  try {
    storage.value = await api.getStorage()
  } catch {}
}

async function handleCleanStorage(target: string, label: string) {
  try {
    await ElMessageBox.confirm(`确定清空${label}目录中的文件？`, '确认', { type: 'warning' })
    const res = await api.cleanStorage([target])
    ElMessage.success(`已清理 ${res.counts[target] || 0} 个文件`)
    loadStorage()
  } catch {}
}

async function handleCleanCompletedSources() {
  try {
    await ElMessageBox.confirm('将删除所有已完成任务的原始上传文件（保留输出结果）。此操作不可撤销，是否继续？', '确认清理原文件', { type: 'warning' })
    const res = await api.cleanCompletedSources()
    ElMessage.success(`已清理 ${res.count || 0} 个原文件，释放 ${formatStorage(res.freed_bytes || 0)}`)
    loadStorage()
  } catch {}
}

function addEndpoint() {
  cfg.mineruEndpoints.value.push({
    url: 'http://localhost:8086/file_parse',
    backend: 'hybrid-http-client',
    serverUrl: 'http://localhost:6002/v1',
    enabled: true,
  })
}

function removeEndpoint(idx: number) {
  if (cfg.mineruEndpoints.value.length <= 1) return ElMessage.warning('至少保留一个节点')
  cfg.mineruEndpoints.value.splice(idx, 1)
}

function handleReset() {
  cfg.resetDefaults()
  saveServerSettings(false).then(() => ElMessage.success('已恢复默认配置'))
}

async function handleExportConfig() {
  const config = await api.exportSettings()
  const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = 'mineru-batch-config.json'
  a.click()
  URL.revokeObjectURL(a.href)
  ElMessage.success('服务端配置已导出（敏感信息已脱敏）')
}

function handleImportConfig() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.json'
  input.onchange = async (e: Event) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return
    try {
      const text = await file.text()
      const config = JSON.parse(text)
      const saved = await api.importSettings(config)
      cfg.applyServerSettings(saved as any)
      ElMessage.success('配置已导入服务端')
      window.location.reload()
    } catch {
      ElMessage.error('导入失败：无效的配置文件')
    }
  }
  input.click()
}

loadSecurityStatus()
loadServerSettings()
loadConcurrency()
loadStorage()

onMounted(() => {
  handleTestAllEndpoints()
})

const paramTable = [
  { param: 'files', desc: '上传的文件', type: 'file' },
  { param: 'backend', desc: '后端类型 (hybrid-http-client / vlm-http-client)', type: 'string' },
  { param: 'server_url', desc: '大模型推理服务地址', type: 'string' },
  { param: 'parse_method', desc: '解析方式 (auto / ocr / txt)', type: 'string' },
  { param: 'lang_list', desc: '语言列表 (ch / en / ch,en)', type: 'string' },
  { param: 'timeout', desc: 'MinerU API 调用超时时间（秒）', type: 'int' },
  { param: 'auto_convert', desc: '文档格式自动转 PDF', type: 'bool' },
  { param: 'formula_enable', desc: '启用公式识别', type: 'bool' },
  { param: 'table_enable', desc: '启用表格识别', type: 'bool' },
  { param: 'return_md', desc: '返回 Markdown 内容', type: 'bool' },
  { param: 'return_middle_json', desc: '返回中间 JSON', type: 'bool' },
  { param: 'return_model_output', desc: '返回模型输出', type: 'bool' },
  { param: 'return_content_list', desc: '返回内容列表', type: 'bool' },
  { param: 'return_images', desc: '返回图片', type: 'bool' },
  { param: 'response_format_zip', desc: 'ZIP 格式响应', type: 'bool' },
  { param: 'replace_image_url', desc: '替换图片为 HTTP URL', type: 'bool' },
  { param: 'start_page_id', desc: '起始页码 (0-based)', type: 'int' },
  { param: 'end_page_id', desc: '结束页码', type: 'int' },
]

</script>

<template>
<div class="settings-page">
  <el-card shadow="never" class="settings-card admin-card">
    <template #header>
      <span class="card-title">安全与权限</span>
    </template>

    <div class="security-grid">
      <div class="security-row">
        <span class="security-label">管理员保护</span>
        <el-tag v-if="securityStatus?.adminRequired" type="warning">已启用</el-tag>
        <el-tag v-else type="info">未启用</el-tag>
      </div>
      <div class="security-row">
        <span class="security-label">私有地址节点</span>
        <el-tag v-if="securityStatus?.allowPrivateEndpoints" type="success">允许</el-tag>
        <el-tag v-else type="danger">禁止</el-tag>
      </div>
    </div>

    <el-form label-position="top" class="admin-form">
      <el-form-item label="管理员 Key">
        <div class="admin-key-row">
          <el-input v-model="adminKeyInput" placeholder="填写部署环境中的 ADMIN_API_KEY" show-password clearable />
          <el-button type="primary" @click="saveAdminKey">保存</el-button>
        </div>
        <div class="form-tip">
          {{ securityStatus?.adminRequired ? (hasAdminKey ? '已配置本机管理员 Key，管理操作会自动携带认证头' : '后端已启用管理员保护，保存配置、删除、重试、清理等操作需要填写 Key') : '后端未设置 ADMIN_API_KEY，当前管理操作不需要 Key' }}
        </div>
      </el-form-item>
    </el-form>
  </el-card>

  <el-card shadow="never" class="settings-card">
    <template #header>
      <div class="settings-header">
        <span class="card-title">MinerU 服务节点</span>
        <div class="header-actions">
          <el-button size="small" :icon="Plus" @click="addEndpoint">添加节点</el-button>
          <el-button size="small" :loading="testingAll" @click="handleTestAllEndpoints">测试全部</el-button>
          <el-button size="small" :icon="Download" @click="handleExportConfig">导出配置</el-button>
          <el-button size="small" :icon="Upload" @click="handleImportConfig">导入配置</el-button>
          <el-button size="small" type="primary" :loading="savingSettings" @click="saveServerSettings()">保存配置</el-button>
          <el-button size="small" @click="handleReset">恢复默认</el-button>
        </div>
      </div>
    </template>

    <div class="endpoint-hint">
      多节点时采用轮询（Round-Robin）负载均衡，上传的任务会自动分配到不同节点
    </div>

    <div class="endpoint-list">
      <div v-for="(ep, idx) in cfg.mineruEndpoints.value" :key="idx" class="endpoint-card">
        <div class="endpoint-header">
          <el-switch v-model="ep.enabled" size="small" />
          <span class="endpoint-label">节点 {{ idx + 1 }}</span>
          <el-tag v-if="ep.enabled" type="success" size="small">启用</el-tag>
          <el-tag v-else type="info" size="small">禁用</el-tag>
          <!-- Ping Status Indicator -->
          <div v-if="nodePings[idx]" class="node-ping-badge" :class="nodePings[idx].status">
            <span class="ping-dot" />
            <span class="ping-text">
              <template v-if="nodePings[idx].status === 'testing'">测速中...</template>
              <template v-else-if="nodePings[idx].latency !== null">{{ nodePings[idx].latency }}ms</template>
              <template v-else>不可用</template>
            </span>
          </div>
          <div v-if="ep.backend === 'vlm-http-client' && nodePings[idx] && nodePings[idx].status !== 'testing' && nodePings[idx].server" class="vlm-status-badge" :class="nodePings[idx].server.ok ? 'ok' : 'fail'">
            <span class="ping-dot" />
            <span class="ping-text">VLM {{ nodePings[idx].server.ok ? '正常' : '异常' }}</span>
          </div>
          <div class="endpoint-actions">
            <el-button size="small" :icon="Connection" :loading="testing === idx" @click="handleTestEndpoint(idx)" />
            <el-button size="small" type="danger" :icon="Delete" @click="removeEndpoint(idx)" plain />
          </div>
        </div>
        <el-form label-position="top" class="endpoint-form">
          <el-form-item label="MinerU 端点 (file_parse)">
            <el-input v-model="ep.url" placeholder="http://host:port/file_parse" />
          </el-form-item>
          <div class="endpoint-row">
            <el-form-item label="后端类型">
              <el-select v-model="ep.backend" style="width:100%">
                <el-option value="hybrid-http-client" label="hybrid-http-client" />
                <el-option value="vlm-http-client" label="vlm-http-client" />
              </el-select>
            </el-form-item>
            <el-form-item label="大模型服务地址 (server_url)">
              <el-input v-model="ep.serverUrl" placeholder="http://host:port/v1" />
            </el-form-item>
          </div>
          <el-form-item label="API Key (可选)">
            <el-input v-model="ep.apiKey" :placeholder="ep.hasApiKey ? '已配置，留空则保留服务端密钥' : '留空则不发送认证头'" show-password clearable />
          </el-form-item>
        </el-form>
      </div>
    </div>
  </el-card>

  <el-card shadow="never" class="settings-card">
    <template #header>
      <span class="card-title">通用配置</span>
    </template>

    <el-form label-position="top" class="settings-form">
      <el-form-item label="解析方式 (parse_method)">
          <el-select v-model="cfg.state.parseMethod">
          <el-option value="auto" label="auto" />
          <el-option value="ocr" label="ocr" />
          <el-option value="txt" label="txt" />
        </el-select>
      </el-form-item>

      <el-form-item label="语言 (lang_list)">
        <el-input v-model="cfg.state.langList" placeholder="ch / en / ch,en" />
      </el-form-item>

      <el-form-item label="默认输出格式">
        <el-radio-group v-model="cfg.state.outputFormat">
          <el-radio-button value="md">Markdown (.md)</el-radio-button>
          <el-radio-button value="txt">纯文本 (.txt)</el-radio-button>
          <el-radio-button value="html">HTML (.html)</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="超时时间 (秒)">
        <el-input-number v-model="cfg.state.timeout" :min="60" :max="3600" :step="60" />
        <div class="form-tip">大文件建议 600~1800 秒，防止长时间解析断连</div>
      </el-form-item>

      <el-form-item label="文档自动转 PDF">
        <el-switch v-model="cfg.state.autoConvert" />
        <div class="form-tip">关闭后，Word/PPT/Excel 文件需在任务列表手动点击转换</div>
      </el-form-item>

      <el-form-item label="并发处理数">
        <el-input-number v-model="concurrency" :min="1" :max="20" :step="1" @change="handleConcurrencyChange" />
        <div class="form-tip">同时处理的任务数（1~20），增大可提高吞吐但会占用更多资源</div>
      </el-form-item>

      <el-divider content-position="left">开关选项</el-divider>

      <div class="switch-grid">
        <el-form-item label="公式识别"><el-switch v-model="cfg.state.formulaEnable" /></el-form-item>
        <el-form-item label="表格识别"><el-switch v-model="cfg.state.tableEnable" /></el-form-item>
        <el-form-item label="返回 Markdown"><el-switch v-model="cfg.state.returnMd" /></el-form-item>
        <el-form-item label="返回 middle_json"><el-switch v-model="cfg.state.returnMiddleJson" /></el-form-item>
        <el-form-item label="返回模型输出"><el-switch v-model="cfg.state.returnModelOutput" /></el-form-item>
        <el-form-item label="返回 content_list"><el-switch v-model="cfg.state.returnContentList" /></el-form-item>
        <el-form-item label="返回图片"><el-switch v-model="cfg.state.returnImages" /></el-form-item>
        <el-form-item label="ZIP 格式响应"><el-switch v-model="cfg.state.responseFormatZip" /></el-form-item>
        <el-form-item label="替换图片 URL"><el-switch v-model="cfg.state.replaceImageUrl" /></el-form-item>
      </div>

      <el-divider content-position="left">页码范围</el-divider>

      <div class="page-range-row">
        <el-form-item label="起始页码"><el-input-number v-model="cfg.state.startPageId" :min="0" /></el-form-item>
        <el-form-item label="结束页码"><el-input-number v-model="cfg.state.endPageId" :min="0" /></el-form-item>
      </div>
    </el-form>
  </el-card>

  <el-card shadow="never" class="info-card">
    <template #header>
      <div class="settings-header">
        <span class="card-title">存储管理</span>
        <el-button size="small" text @click="loadStorage">刷新</el-button>
      </div>
    </template>
    <div v-if="storage" class="storage-grid">
      <div class="storage-item">
        <span class="storage-label">上传文件</span>
        <span class="storage-value">{{ formatStorage(storage.uploads) }}</span>
        <el-button size="small" text type="danger" @click="handleCleanStorage('uploads', '上传文件')">清理</el-button>
      </div>
      <div class="storage-item">
        <span class="storage-label">输出结果</span>
        <span class="storage-value">{{ formatStorage(storage.outputs) }}</span>
        <el-button size="small" text type="danger" @click="handleCleanStorage('outputs', '输出结果')">清理</el-button>
      </div>
      <div class="storage-item">
        <span class="storage-label">转换文件</span>
        <span class="storage-value">{{ formatStorage(storage.converted) }}</span>
        <el-button size="small" text type="danger" @click="handleCleanStorage('converted', '转换文件')">清理</el-button>
      </div>
      <div class="storage-item">
        <span class="storage-label">数据库</span>
        <span class="storage-value">{{ formatStorage(storage.database) }}</span>
      </div>
      <div class="storage-total">
        <span>磁盘总占用</span>
        <strong>{{ formatStorage(storage.total) }}</strong>
      </div>
      <el-divider />
      <div class="gc-actions">
        <el-button type="warning" @click="handleCleanCompletedSources">
          清理已完成任务的原文件
        </el-button>
        <span class="gc-hint">删除已解析完成任务的原始上传文件，保留输出结果，释放磁盘空间</span>
      </div>
    </div>
    <el-skeleton v-else :rows="3" animated />
  </el-card>

  <el-card shadow="never" class="info-card">
    <template #header>
      <span class="card-title">调用说明</span>
    </template>
    <div class="info-content">
      <p>上传文件后，系统会从已启用的 MinerU 节点中<strong>轮询选择</strong>一个，发送 POST 请求并携带以下参数：</p>
      <el-table :data="paramTable" size="small" stripe>
        <el-table-column prop="param" label="参数" width="180" />
        <el-table-column prop="desc" label="说明" />
        <el-table-column prop="type" label="类型" width="80" />
      </el-table>
    </div>
  </el-card>
	</div>

</template>

<style scoped>
.settings-page {
  display: grid; grid-template-columns: 1fr 1fr; gap: 20px;
}
.settings-card, .info-card { border-radius: 12px; }
.admin-card { grid-column: 1 / -1; }
.admin-form { margin-top: 14px; }
.admin-key-row { display: flex; gap: 10px; }
.security-grid { display: flex; flex-wrap: wrap; gap: 16px; }
.security-row { display: flex; align-items: center; gap: 10px; font-size: 14px; }
.security-label { color: #606266; }
.settings-form { display: flex; flex-direction: column; gap: 2px; }
.card-title { font-weight: 600; }
.form-tip { font-size: 12px; color: #909399; margin-top: 2px; }
.switch-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 4px 16px;
}
.page-range-row { display: flex; gap: 16px; }
.page-range-row > * { flex: 1; }
.info-content { font-size: 14px; color: #606266; line-height: 1.8; }
.info-content p { margin-bottom: 12px; }
.settings-header { display: flex; align-items: center; }
.settings-header .header-actions { margin-left: auto; display: flex; gap: 8px; }

.endpoint-hint { font-size: 13px; color: #909399; margin-bottom: 16px; }
.endpoint-list { display: flex; flex-direction: column; gap: 16px; }
.endpoint-card { border: 1px solid #ebeef5; border-radius: 8px; padding: 14px; }
.endpoint-header { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.endpoint-label { font-weight: 600; font-size: 14px; }
.endpoint-actions { margin-left: auto; display: flex; gap: 6px; }
.endpoint-form { display: flex; flex-direction: column; gap: 2px; }
.endpoint-row { display: grid; grid-template-columns: 200px 1fr; gap: 12px; }
.endpoint-row > * { margin-bottom: 0; }
.storage-grid { display: flex; flex-direction: column; gap: 10px; }
.storage-item { display: flex; align-items: center; gap: 12px; font-size: 14px; }
.storage-label { color: #606266; width: 80px; }
.storage-value { color: #303133; font-weight: 500; font-variant-numeric: tabular-nums; }
.storage-total { display: flex; justify-content: space-between; padding-top: 10px; border-top: 1px solid #ebeef5; font-size: 14px; color: #606266; }
.storage-total strong { color: #303133; font-size: 16px; }
.gc-actions { display: flex; align-items: center; gap: 12px; }
.gc-hint { font-size: 12px; color: #909399; }

@media (max-width: 900px) {
  .settings-page { grid-template-columns: 1fr; }
  .endpoint-row { grid-template-columns: 1fr; }
}

/* Node Ping Badges & Status Dots */
.node-ping-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  padding: 2px 8px;
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
.vlm-status-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  background: #f4f4f5;
  color: #909399;
  flex-shrink: 0;
}
.vlm-status-badge.ok {
  background: #e1f3d8;
  color: #67c23a;
}
.vlm-status-badge.fail {
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
</style>
