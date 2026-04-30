<script setup lang="ts">
import { ref } from 'vue'
import { Connection, Plus, Delete } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useConfig, type MineruEndpoint } from '../stores/config'
import { api } from '../api'

const cfg = useConfig()

const testing = ref<number | null>(null)

async function handleTestEndpoint(idx: number) {
  const ep = cfg.mineruEndpoints.value[idx]
  if (!ep) return
  testing.value = idx
  try {
    const res = await api.testConnection({ mineru_api: ep.url, server_url: ep.serverUrl })
    ElMessage.success(res.ok ? `节点 ${idx + 1} 连接正常` : `节点 ${idx + 1} 异常: ${res.error || '未知错误'}`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '测试连接失败')
  } finally {
    testing.value = null
  }
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
  ElMessage.success('已恢复默认配置')
}

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
  <el-card shadow="never" class="settings-card">
    <template #header>
      <div class="settings-header">
        <span class="card-title">MinerU 服务节点</span>
        <div class="header-actions">
          <el-button size="small" :icon="Plus" @click="addEndpoint">添加节点</el-button>
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
        <el-select v-model="cfg.parseMethod.value">
          <el-option value="auto" label="auto" />
          <el-option value="ocr" label="ocr" />
          <el-option value="txt" label="txt" />
        </el-select>
      </el-form-item>

      <el-form-item label="语言 (lang_list)">
        <el-input v-model="cfg.langList.value" placeholder="ch / en / ch,en" />
      </el-form-item>

      <el-form-item label="默认输出格式">
        <el-radio-group v-model="cfg.outputFormat.value">
          <el-radio-button value="md">Markdown (.md)</el-radio-button>
          <el-radio-button value="txt">纯文本 (.txt)</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="超时时间 (秒)">
        <el-input-number v-model="cfg.timeout.value" :min="60" :max="3600" :step="60" />
        <div class="form-tip">大文件建议 600~1800 秒，防止长时间解析断连</div>
      </el-form-item>

      <el-form-item label="文档自动转 PDF">
        <el-switch v-model="cfg.autoConvert.value" />
        <div class="form-tip">关闭后，Word/PPT/Excel 文件需在任务列表手动点击转换</div>
      </el-form-item>

      <el-divider content-position="left">开关选项</el-divider>

      <div class="switch-grid">
        <el-form-item label="公式识别"><el-switch v-model="cfg.formulaEnable.value" /></el-form-item>
        <el-form-item label="表格识别"><el-switch v-model="cfg.tableEnable.value" /></el-form-item>
        <el-form-item label="返回 Markdown"><el-switch v-model="cfg.returnMd.value" /></el-form-item>
        <el-form-item label="返回 middle_json"><el-switch v-model="cfg.returnMiddleJson.value" /></el-form-item>
        <el-form-item label="返回模型输出"><el-switch v-model="cfg.returnModelOutput.value" /></el-form-item>
        <el-form-item label="返回 content_list"><el-switch v-model="cfg.returnContentList.value" /></el-form-item>
        <el-form-item label="返回图片"><el-switch v-model="cfg.returnImages.value" /></el-form-item>
        <el-form-item label="ZIP 格式响应"><el-switch v-model="cfg.responseFormatZip.value" /></el-form-item>
        <el-form-item label="替换图片 URL"><el-switch v-model="cfg.replaceImageUrl.value" /></el-form-item>
      </div>

      <el-divider content-position="left">页码范围</el-divider>

      <div class="page-range-row">
        <el-form-item label="起始页码"><el-input-number v-model="cfg.startPageId.value" :min="0" /></el-form-item>
        <el-form-item label="结束页码"><el-input-number v-model="cfg.endPageId.value" :min="0" /></el-form-item>
      </div>
    </el-form>
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

@media (max-width: 900px) {
  .settings-page { grid-template-columns: 1fr; }
  .endpoint-row { grid-template-columns: 1fr; }
}
</style>
