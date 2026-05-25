<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, shallowRef } from 'vue'
import { Clock, Loading, SuccessFilled, CircleClose, Files, UploadFilled } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { api, type TaskItem, type QualityReport, type QueueStatus, type FailureCategories, type BatchProgressReport, type NodeHealthReport } from '../api'
import { formatTime } from '../utils/format'
import * as echarts from 'echarts/core'
import { BarChart, PieChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([BarChart, PieChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const router = useRouter()
const stats = ref({ total: 0, pending: 0, processing: 0, completed: 0, failed: 0, avg_duration_ms: 0 })
const recentTasks = ref<TaskItem[]>([])
const loading = ref(false)
const firstLoad = ref(true)
const storageInfo = ref<{ total: number } | null>(null)
const qualityReport = ref<QualityReport | null>(null)
const queueStatus = ref<QueueStatus | null>(null)
const failureCategories = ref<FailureCategories | null>(null)
const batchProgress = ref<BatchProgressReport | null>(null)
const nodeHealth = ref<NodeHealthReport | null>(null)
const showWelcome = ref(false)
function dismissWelcome() {
  showWelcome.value = false
  localStorage.setItem('welcome_dismissed', '1')
}
let sseClose: (() => void) | null = null

const chartRef = shallowRef<echarts.ECharts | null>(null)
const chartEl = ref<HTMLElement | null>(null)
const pieRef = shallowRef<echarts.ECharts | null>(null)
const pieEl = ref<HTMLElement | null>(null)

const cards = [
  { key: 'total', label: '总任务', icon: Files, color: '#fff', bg: 'linear-gradient(135deg, #5a67d8 0%, #6b46c1 100%)', route: '/tasks' },
  { key: 'pending', label: '等待中', icon: Clock, color: '#1a202c', bg: 'linear-gradient(135deg, #e2e8f0 0%, #cbd5e0 100%)', route: '/tasks?status=pending' },
  { key: 'processing', label: '处理中', icon: Loading, color: '#fff', bg: 'linear-gradient(135deg, #ed8936 0%, #dd6b20 100%)', route: '/tasks?status=processing' },
  { key: 'completed', label: '已完成', icon: SuccessFilled, color: '#fff', bg: 'linear-gradient(135deg, #38a169 0%, #2f855a 100%)', route: '/tasks?status=completed' },
  { key: 'failed', label: '失败', icon: CircleClose, color: '#fff', bg: 'linear-gradient(135deg, #e53e3e 0%, #c53030 100%)', route: '/tasks?status=failed' },
]

const successRate = computed(() => {
  const done = stats.value.completed + stats.value.failed
  if (!done) return '-'
  return (stats.value.completed / done * 100).toFixed(1) + '%'
})

const failureRate = computed(() => {
  const done = stats.value.completed + stats.value.failed
  if (!done) return '-'
  return (stats.value.failed / done * 100).toFixed(1) + '%'
})

const avgDuration = computed(() => {
  const ms = stats.value.avg_duration_ms
  if (!ms) return '-'
  if (ms < 60000) return (ms / 1000).toFixed(1) + 's'
  return (ms / 60000).toFixed(1) + 'min'
})

const storageDisplay = computed(() => {
  if (!storageInfo.value) return '-'
  const bytes = storageInfo.value.total
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  if (bytes < 1024 * 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + ' MB'
  return (bytes / 1024 / 1024 / 1024).toFixed(1) + ' GB'
})

const queueLoadRate = computed(() => {
  if (!queueStatus.value?.concurrency) return 0
  return Math.min(100, Math.round((queueStatus.value.processing / queueStatus.value.concurrency) * 100))
})
const failureItems = computed(() => Array.isArray(failureCategories.value?.items) ? failureCategories.value.items : [])
const recentFailures = computed(() => Array.isArray(qualityReport.value?.recent_failures) ? qualityReport.value.recent_failures : [])
const batchItems = computed(() => Array.isArray(batchProgress.value?.items) ? batchProgress.value.items : [])
const waitingTasks = computed(() => Array.isArray(queueStatus.value?.waiting_tasks) ? queueStatus.value.waiting_tasks : [])
const healthyNodes = computed(() => Array.isArray(nodeHealth.value?.nodes) ? nodeHealth.value.nodes : [])

const failureLabel: Record<string, string> = {
  timeout: '超时', network: '网络', conversion: '转换', mineru_api: 'MinerU API', other: '其他',
}

async function loadStats() {
  loading.value = true
  try {
    const [statsRes, recentRes, storRes, qualityRes, queueRes, failuresRes, batchesRes, healthRes] = await Promise.all([
      api.getStats(),
      api.listTasks({ page: 1, size: 5 }),
      api.getStorage().catch(() => null),
      api.getQualityReport().catch(() => null),
      api.getQueueStatus().catch(() => null),
      api.getFailureCategories().catch(() => null),
      api.getBatchProgress().catch(() => null),
      api.getNodeHealth().catch(() => null),
    ])
    stats.value = statsRes
    recentTasks.value = Array.isArray(recentRes?.items) ? recentRes.items : []
    if (storRes) storageInfo.value = storRes
    if (qualityRes) qualityReport.value = qualityRes
    if (queueRes) queueStatus.value = queueRes
    if (failuresRes) failureCategories.value = failuresRes
    if (batchesRes) batchProgress.value = batchesRes
    if (healthRes) nodeHealth.value = healthRes
  } catch (e) {
    console.error('[Dashboard] loadStats failed:', e)
  } finally {
    loading.value = false
    firstLoad.value = false
  }
}

async function loadTrend() {
  try {
    const data = await api.getStatsTrend(7)
    if (!chartRef.value) {
      chartRef.value = echarts.init(chartEl.value!)
    }
    chartRef.value.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['完成', '失败'], top: 0, textStyle: { fontSize: 12 } },
      grid: { top: 30, right: 16, bottom: 24, left: 36 },
      xAxis: { type: 'category', data: data.map(d => d.date.slice(5)), axisLabel: { fontSize: 11 } },
      yAxis: { type: 'value', minInterval: 1, axisLabel: { fontSize: 11 } },
      series: [
        { name: '完成', type: 'bar', data: data.map(d => d.completed), itemStyle: { color: '#67c23a' }, barMaxWidth: 24 },
        { name: '失败', type: 'bar', data: data.map(d => d.failed), itemStyle: { color: '#f56c6c' }, barMaxWidth: 24 },
      ],
    })
  } catch (e) { console.warn('[Dashboard] loadTrend failed:', e) }
}

async function loadFiletypes() {
  try {
    const data = await api.getStatsFiletypes()
    if (!Array.isArray(data) || !data.length) return
    if (!pieRef.value) {
      pieRef.value = echarts.init(pieEl.value!)
    }
    pieRef.value.setOption({
      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
      legend: { orient: 'vertical', right: 0, top: 'center', textStyle: { fontSize: 11 } },
      series: [{
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['40%', '50%'],
        avoidLabelOverlap: false,
        itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 },
        label: { show: false },
        emphasis: { label: { show: true, fontSize: 14, fontWeight: 'bold' } },
        labelLine: { show: false },
        data: data.map(d => ({ name: d.type, value: d.count })),
      }],
    })
  } catch (e) { console.warn('[Dashboard] loadFiletypes failed:', e) }
}

function handleCardClick(route: string) {
  if (route.includes('?')) {
    const [path, query] = route.split('?')
    const params = Object.fromEntries(new URLSearchParams(query))
    router.push({ path, query: params })
  } else {
    router.push(route)
  }
}

const statusLabel: Record<string, string> = {
  pending: '等待中', processing: '处理中', completed: '已完成', failed: '失败',
}

let sseDebounce: ReturnType<typeof setTimeout> | null = null
const resizeHandler = () => { chartRef.value?.resize(); pieRef.value?.resize() }

onMounted(() => {
  loadStats().then(() => { loadTrend(); loadFiletypes() })
  if (!localStorage.getItem('welcome_dismissed') && !localStorage.getItem('cfg_mineru_endpoints')) {
    showWelcome.value = true
  }
  sseClose = api.onTaskEvent(
    (evt) => {
      if (evt.type === 'task_update') {
        if (sseDebounce) clearTimeout(sseDebounce)
        sseDebounce = setTimeout(() => { loadStats(); loadTrend(); loadFiletypes() }, 500)
      }
    },
    undefined,
    () => { loadStats(); loadTrend(); loadFiletypes() },
  )
  window.addEventListener('resize', resizeHandler)
})
onUnmounted(() => {
  if (sseDebounce) clearTimeout(sseDebounce)
  if (sseClose) sseClose()
  chartRef.value?.dispose()
  pieRef.value?.dispose()
  window.removeEventListener('resize', resizeHandler)
})
</script>

<template>
  <div class="dashboard" v-if="firstLoad">
    <div class="stat-row">
      <el-skeleton v-for="i in 5" :key="i" animated style="border-radius:12px;flex:1">
        <template #template>
          <div style="padding:20px 24px;display:flex;align-items:center;gap:16px">
            <el-skeleton-item variant="circle" style="width:28px;height:28px" />
            <div>
              <el-skeleton-item variant="h3" style="width:60px" />
              <el-skeleton-item variant="text" style="width:40px;margin-top:6px" />
            </div>
          </div>
        </template>
      </el-skeleton>
    </div>
    <el-skeleton :rows="5" animated style="margin-top:24px" />
  </div>
  <div class="dashboard" v-else v-loading="loading">
  <div v-if="stats.total === 0" class="empty-dashboard">
    <el-empty description="还没有解析任务" :image-size="80">
      <el-button type="primary" size="large" :icon="UploadFilled" @click="router.push('/upload')">开始处理 easy-dataset 文档</el-button>
    </el-empty>
    <div class="empty-steps">
      <div class="empty-step"><strong>1.</strong> 在设置页配置 MinerU 服务地址</div>
      <div class="empty-step"><strong>2.</strong> 在上传页选择 easy-dataset 场景并拖拽 PDF 文件夹</div>
      <div class="empty-step"><strong>3.</strong> 任务完成后下载 Markdown-only ZIP 导入 easy-dataset</div>
    </div>
  </div>
  <template v-else>
  <div class="stat-row">
    <div v-for="c in cards" :key="c.key" class="stat-card clickable" :style="{ background: c.bg }" @click="handleCardClick(c.route)">
      <div class="stat-icon" :style="{ color: c.color }">
        <el-icon :size="24"><component :is="c.icon" /></el-icon>
      </div>
      <div class="stat-info">
        <div class="stat-value" :style="{ color: c.color }">{{ stats[c.key as keyof typeof stats] }}</div>
        <div class="stat-label" :style="{ color: c.color }">{{ c.label }}</div>
      </div>
    </div>
  </div>

  <div class="content-grid">
    <div class="left-col">
      <div class="rate-bar">
        <div class="rate-chip">
          <span class="rate-dot success"></span>
          <span class="rate-text">成功率 <strong>{{ successRate }}</strong></span>
        </div>
        <div class="rate-chip">
          <span class="rate-dot danger"></span>
          <span class="rate-text">失败率 <strong>{{ failureRate }}</strong></span>
        </div>
        <div class="rate-chip">
          <span class="rate-dot warning"></span>
          <span class="rate-text">处理中 <strong>{{ stats.processing }}</strong></span>
        </div>
        <div class="rate-chip">
          <span class="rate-dot primary"></span>
          <span class="rate-text">平均耗时 <strong>{{ avgDuration }}</strong></span>
        </div>
        <div class="rate-chip">
          <span class="rate-dot info"></span>
          <span class="rate-text">磁盘占用 <strong>{{ storageDisplay }}</strong></span>
        </div>
      </div>

      <el-card shadow="never" class="recent-card">
        <template #header>
          <span class="card-title">解析质量概览</span>
        </template>
        <div class="quality-grid" v-if="qualityReport">
          <div class="quality-item"><span>成功率</span><strong>{{ qualityReport.success_rate }}%</strong></div>
          <div class="quality-item"><span>失败数</span><strong>{{ qualityReport.failed }}</strong></div>
          <div class="quality-item"><span>处理中</span><strong>{{ qualityReport.processing }}</strong></div>
          <div class="quality-item"><span>平均耗时</span><strong>{{ avgDuration }}</strong></div>
        </div>
        <div class="insight-list" v-if="failureItems.length">
          <div v-for="item in failureItems" :key="item.category" class="insight-item danger">
            <span>{{ failureLabel[item.category] || item.category }}</span>
            <strong>{{ item.count }}</strong>
          </div>
        </div>
        <div v-if="recentFailures.length" class="failure-list">
          <div v-for="item in recentFailures" :key="item.id" class="failure-item" @click="router.push('/tasks?status=failed')">
            <span>{{ item.filename }}</span>
            <small>{{ item.error_message || '解析失败' }}</small>
          </div>
        </div>
      </el-card>

      <el-card shadow="never" class="recent-card" v-if="batchItems.length">
        <template #header>
          <span class="card-title">批次进度</span>
        </template>
        <div class="batch-list">
          <div v-for="batch in batchItems.slice(0, 4)" :key="batch.batch_id" class="batch-item" @click="router.push(`/tasks?batch_id=${batch.batch_id}`)">
            <div class="batch-title"><span>{{ batch.batch_name || batch.batch_id }}</span><strong>{{ batch.progress }}%</strong></div>
            <el-progress :percentage="batch.progress" :stroke-width="8" />
            <small>共 {{ batch.total }} · 完成 {{ batch.completed }} · 失败 {{ batch.failed }}</small>
          </div>
        </div>
      </el-card>

      <el-card shadow="never" class="recent-card">
        <template #header>
          <span class="card-title">最近任务</span>
        </template>
        <el-table :data="recentTasks" stripe size="small">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="original_filename" label="文件名" min-width="180" show-overflow-tooltip />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="({ pending:'info', processing:'warning', completed:'success', failed:'danger' } as Record<string,string>)[row.status]" size="small">
                {{ statusLabel[row.status] || row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="时间" width="170">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>

    <div class="right-col">
      <el-card shadow="never" class="queue-card">
        <template #header>
          <span class="card-title">队列状态</span>
        </template>
        <div v-if="queueStatus" class="queue-panel">
          <div class="queue-meter">
            <el-progress type="dashboard" :percentage="queueLoadRate" :width="104">
              <template #default>
                <div class="queue-percent">{{ queueLoadRate }}%</div>
                <div class="queue-caption">并发占用</div>
              </template>
            </el-progress>
            <div class="queue-metrics">
              <div><span>并发上限</span><strong>{{ queueStatus.concurrency }}</strong></div>
              <div><span>运行中</span><strong>{{ queueStatus.processing }}</strong></div>
              <div><span>等待中</span><strong>{{ queueStatus.pending }}</strong></div>
              <div><span>可用槽位</span><strong>{{ queueStatus.available_slots }}</strong></div>
            </div>
          </div>
          <div class="waiting-list" v-if="waitingTasks.length">
            <div v-for="item in waitingTasks" :key="item.id" class="waiting-item" @click="router.push('/tasks?status=pending')">
              <span>{{ item.filename }}</span>
              <small>#{{ item.id }} · 优先级 {{ item.priority }}</small>
            </div>
          </div>
          <el-empty v-else description="暂无等待任务" :image-size="48" />
        </div>
      </el-card>

      <el-card shadow="never" class="trend-card">
        <template #header>
          <span class="card-title">节点健康</span>
        </template>
        <div v-if="nodeHealth" class="health-list">
          <div v-for="node in healthyNodes.slice(0, 4)" :key="node.index" class="health-item">
            <span class="health-dot" :class="node.status"></span>
            <span>{{ node.url }}</span>
            <strong>{{ node.ok ? `${node.latency_ms}ms` : node.status }}</strong>
          </div>
        </div>
      </el-card>

      <el-card shadow="never" class="trend-card">
        <template #header>
          <span class="card-title">近 7 天趋势</span>
        </template>
        <div ref="chartEl" class="trend-chart"></div>
      </el-card>
      <el-card shadow="never" class="pie-card">
        <template #header>
          <span class="card-title">文件类型分布</span>
        </template>
        <div ref="pieEl" class="pie-chart"></div>
      </el-card>
      <el-card shadow="never" class="quick-card">
        <template #header>
          <span class="card-title">快捷操作</span>
        </template>
        <div class="quick-actions">
          <el-button type="primary" size="large" :icon="UploadFilled" @click="router.push('/upload')" class="quick-btn">上传解析</el-button>
          <el-button size="large" @click="router.push('/tasks?status=failed')" class="quick-btn">查看失败任务</el-button>
          <el-button size="large" @click="router.push('/logs')" class="quick-btn">查看日志</el-button>
        </div>
      </el-card>
    </div>
  </div>
  </template>
  </div>

  <el-dialog v-model="showWelcome" title="欢迎使用 MinerU Batch" width="480px" :close-on-click-modal="false">
    <div style="line-height:1.8;color:#606266">
      <p>MinerU Batch 可将批量 PDF、图片和 Office 文档转换为 Markdown，适合作为 easy-dataset 的前置预处理工具。</p>
      <h4 style="margin:16px 0 8px;color:#303133">推荐流程</h4>
      <ol style="padding-left:20px;margin:0">
        <li>前往 <strong>设置页</strong> 配置 MinerU 服务地址</li>
        <li>在 <strong>上传页</strong> 选择 easy-dataset 场景并拖拽 PDF 文件夹</li>
        <li>任务完成后在 <strong>任务页</strong> 下载 Markdown-only ZIP 并导入 easy-dataset</li>
      </ol>
      <p style="margin-top:12px;font-size:13px;color:#909399">提示：在线演示仅预览界面，完整解析能力需要部署后端服务。</p>
    </div>
    <template #footer>
      <el-button @click="dismissWelcome">稍后再说</el-button>
      <el-button type="primary" @click="dismissWelcome(); router.push('/settings')">前往设置</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.stat-row {
  display: flex; gap: 16px; margin-bottom: 20px;
}
.stat-card {
  flex: 1; min-width: 0;
  border-radius: 12px; padding: 18px 20px;
  display: flex; align-items: center; gap: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  transition: transform 0.2s, box-shadow 0.2s;
}
.stat-card.clickable { cursor: pointer; }
.stat-card:hover { transform: translateY(-2px); box-shadow: 0 6px 16px rgba(0,0,0,0.12); }
.stat-icon { display: flex; opacity: 0.9; }
.stat-value { font-size: 24px; font-weight: 700; line-height: 1.2; }
.stat-label { font-size: 12px; opacity: 0.85; margin-top: 2px; }

.content-grid { display: grid; grid-template-columns: 1fr 380px; gap: 20px; }
.left-col { display: flex; flex-direction: column; gap: 16px; }
.right-col { display: flex; flex-direction: column; gap: 16px; }

.rate-bar {
  display: flex; gap: 20px; padding: 12px 20px;
  background: #fff; border-radius: 10px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}
.rate-chip { display: flex; align-items: center; gap: 6px; }
.rate-dot { width: 8px; height: 8px; border-radius: 50%; }
.rate-dot.success { background: #67c23a; }
.rate-dot.danger { background: #f56c6c; }
.rate-dot.warning { background: #e6a23c; }
.rate-dot.primary { background: #409eff; }
.rate-dot.info { background: #909399; }
.rate-text { font-size: 13px; color: #606266; }
.rate-text strong { font-size: 15px; }

.recent-card { border-radius: 12px; flex: 1; }
.quality-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.quality-item { padding: 12px; background: #f7f8fa; border-radius: 8px; display: flex; flex-direction: column; gap: 6px; }
.quality-item span { font-size: 12px; color: #909399; }
.quality-item strong { font-size: 18px; color: #303133; }
.failure-list { margin-top: 12px; display: flex; flex-direction: column; gap: 8px; }
.failure-item { padding: 8px 10px; background: #fef0f0; border-radius: 6px; cursor: pointer; display: flex; flex-direction: column; gap: 2px; }
.failure-item span { font-size: 13px; color: #303133; }
.failure-item small { color: #f56c6c; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.insight-list { margin-top: 12px; display: flex; gap: 8px; flex-wrap: wrap; }
.insight-item { padding: 8px 10px; border-radius: 8px; display: flex; gap: 8px; align-items: center; background: #f7f8fa; }
.insight-item span { font-size: 12px; color: #606266; }
.insight-item strong { color: #303133; }
.insight-item.danger { background: #fef0f0; }
.batch-list { display: flex; flex-direction: column; gap: 12px; }
.batch-item { padding: 10px; background: #f7f8fa; border-radius: 8px; cursor: pointer; }
.batch-title { display: flex; justify-content: space-between; margin-bottom: 6px; font-size: 13px; }
.batch-title span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.batch-item small { color: #909399; }
.health-list { display: flex; flex-direction: column; gap: 8px; }
.health-item { display: grid; grid-template-columns: auto 1fr auto; gap: 8px; align-items: center; font-size: 13px; }
.health-item span:nth-child(2) { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.health-dot { width: 8px; height: 8px; border-radius: 50%; background: #909399; }
.health-dot.green { background: #67c23a; }
.health-dot.yellow { background: #e6a23c; }
.health-dot.red { background: #f56c6c; }
.queue-card { border-radius: 12px; }
.queue-panel { display: flex; flex-direction: column; gap: 14px; }
.queue-meter { display: flex; gap: 16px; align-items: center; }
.queue-percent { font-size: 20px; font-weight: 700; color: #303133; line-height: 1; }
.queue-caption { font-size: 12px; color: #909399; margin-top: 4px; }
.queue-metrics { flex: 1; display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
.queue-metrics div { padding: 10px; background: #f7f8fa; border-radius: 8px; display: flex; flex-direction: column; gap: 4px; }
.queue-metrics span { font-size: 12px; color: #909399; }
.queue-metrics strong { font-size: 18px; color: #303133; }
.waiting-list { display: flex; flex-direction: column; gap: 8px; }
.waiting-item { padding: 8px 10px; background: #f4f8ff; border-radius: 6px; cursor: pointer; display: flex; flex-direction: column; gap: 2px; }
.waiting-item span { font-size: 13px; color: #303133; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.waiting-item small { color: #409eff; }
.trend-card { border-radius: 12px; }
.trend-chart { height: 200px; }
.pie-card { border-radius: 12px; }
.pie-chart { height: 200px; }
.quick-card { border-radius: 12px; }
.quick-actions { display: flex; flex-direction: column; gap: 12px; }
.quick-btn { width: 100%; }
.card-title { font-weight: 600; }
.empty-dashboard { display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 400px; gap: 24px; }
.empty-steps { display: flex; flex-direction: column; gap: 8px; font-size: 14px; color: #606266; }
.empty-step strong { color: #409eff; }

@media (max-width: 1000px) {
  .stat-row { flex-wrap: wrap; }
  .stat-card { flex: 1 1 calc(50% - 12px); min-width: 140px; }
  .content-grid { grid-template-columns: 1fr; }
}
</style>
