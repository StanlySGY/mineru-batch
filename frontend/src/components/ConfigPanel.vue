<script setup lang="ts">
const props = defineProps<{
  config: Record<string, any>
}>()

const LABELS: Record<string, string> = {
  backend: '后端类型',
  parseMethod: '解析方式',
  outputFormat: '输出格式',
  timeout: '超时',
  formulaEnable: '公式识别',
  tableEnable: '表格识别',
  returnMd: 'Markdown',
  returnMiddleJson: 'middle_json',
  returnModelOutput: '模型输出',
  returnContentList: 'content_list',
  returnImages: '返回图片',
  responseFormatZip: 'ZIP 压缩',
  replaceImageUrl: '替换图片URL',
  startPageId: '起始页码',
  endPageId: '结束页码',
  autoConvert: '自动转PDF',
  mineruApi: 'MinerU API',
  serverUrl: 'LLM Server',
  langList: '语言',
}

function fmt(key: string): string {
  const v = props.config[key]
  if (v === undefined || v === null) return '—'
  if (typeof v === 'boolean') return ''
  if (key === 'timeout') return `${v}s`
  return String(v)
}

function fmtBool(key: string): boolean {
  return !!props.config[key]
}
</script>

<template>
  <div class="config-summary">
    <div class="summary-section">
      <div class="section-title">核心参数</div>
      <div class="summary-grid">
        <div v-for="k in ['backend','parseMethod','outputFormat','timeout']" :key="k" class="summary-item">
          <span class="summary-label">{{ LABELS[k] }}</span>
          <span class="summary-value">{{ fmt(k) }}</span>
        </div>
      </div>
    </div>

    <div class="summary-section">
      <div class="section-title">功能开关</div>
      <div class="toggle-row">
        <el-tag v-for="k in ['formulaEnable','tableEnable','returnMd','returnMiddleJson','returnModelOutput','returnContentList','returnImages','responseFormatZip','replaceImageUrl','autoConvert']" :key="k"
          :type="fmtBool(k) ? 'success' : 'info'"
          :effect="fmtBool(k) ? 'light' : 'plain'"
          size="small" class="toggle-tag"
        >
          {{ LABELS[k] }}
        </el-tag>
      </div>
    </div>

    <div class="summary-section sec-address">
      <div class="section-title">服务地址</div>
      <div class="addr-line">
        <span class="addr-label">MinerU API</span>
        <code class="addr-value">{{ fmt('mineruApi') }}</code>
      </div>
      <div class="addr-line">
        <span class="addr-label">LLM Server</span>
        <code class="addr-value">{{ fmt('serverUrl') }}</code>
      </div>
      <div v-if="fmt('langList') && fmt('langList') !== 'ch'" class="addr-line">
        <span class="addr-label">语言</span>
        <code class="addr-value">{{ fmt('langList') }}</code>
      </div>
      <div v-if="fmt('startPageId') !== '0' || fmt('endPageId') !== '99999'" class="addr-line">
        <span class="addr-label">页码范围</span>
        <code class="addr-value">{{ fmt('startPageId') }} — {{ fmt('endPageId') }}</code>
      </div>
    </div>

    <div class="config-hint">
      <el-link type="info" :underline="false" @click="$router.push('/settings')" size="small">
        修改配置 → 设置页 ↗
      </el-link>
    </div>
  </div>

</template>

<style scoped>
.config-summary { display: flex; flex-direction: column; gap: 14px; }
.summary-section { background: #f8f9fb; border-radius: 8px; padding: 12px 14px; }
.section-title { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: #909399; margin-bottom: 10px; }
.summary-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 16px; }
.summary-item { display: flex; flex-direction: column; gap: 1px; }
.summary-label { font-size: 11px; color: #909399; }
.summary-value { font-size: 13px; color: #303133; font-weight: 500; word-break: break-all; }
.toggle-row { display: flex; flex-wrap: wrap; gap: 6px; }
.toggle-tag { font-size: 12px; }
.sec-address .addr-line { display: flex; align-items: baseline; gap: 8px; padding: 3px 0; }
.addr-label { font-size: 11px; color: #909399; flex-shrink: 0; min-width: 72px; }
.addr-value { font-size: 12px; color: #303133; background: #eef0f4; padding: 2px 8px; border-radius: 4px; word-break: break-all; font-family: 'SF Mono', 'Fira Code', monospace; }
.config-hint { text-align: center; padding-top: 2px; }
</style>
