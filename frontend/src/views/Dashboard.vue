<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, shallowRef } from 'vue'
import { Clock, Loading, SuccessFilled, CircleClose, Files, UploadFilled } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import * as echarts from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const router = useRouter()
const stats = ref({ total: 0, pending: 0, processing: 0, completed: 0, failed: 0, avg_duration_ms: 0 })
const recentTasks = ref<any[]>([])
const loading = ref(false)
const firstLoad = ref(true)
const storageInfo = ref<{ total: number } | null>(null)
let timer: ReturnType<typeof setInterval> | null = null
let sseClose: (() => void) | null = null

const chartRef = shallowRef<echarts.ECharts | null>(null)
const chartEl = ref<HTMLElement | null>(null)

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

async function loadStats() {
  loading.value = true
  try {
    const [statsRes, recentRes, storRes] = await Promise.all([
      api.getStats(),
      api.listTasks({ page: 1, size: 5 }),
      api.getStorage().catch(() => null),
    ])
    stats.value = statsRes
    recentTasks.value = recentRes.items
    if (storRes) storageInfo.value = storRes
  } catch {
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
  } catch {}
}

function formatTime(iso: string) {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('zh-CN')
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

onMounted(() => {
  loadStats().then(loadTrend)
  timer = setInterval(loadStats, 30000)
  sseClose = api.onTaskEvent((evt) => {
    if (evt.type === 'task_update') { loadStats(); loadTrend() }
  })
  window.addEventListener('resize', () => chartRef.value?.resize())
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
  if (sseClose) sseClose()
  chartRef.value?.dispose()
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
      <el-card shadow="never" class="trend-card">
        <template #header>
          <span class="card-title">近 7 天趋势</span>
        </template>
        <div ref="chartEl" class="trend-chart"></div>
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
  </div>
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
.trend-card { border-radius: 12px; }
.trend-chart { height: 200px; }
.quick-card { border-radius: 12px; }
.quick-actions { display: flex; flex-direction: column; gap: 12px; }
.quick-btn { width: 100%; }
.card-title { font-weight: 600; }

@media (max-width: 1000px) {
  .stat-row { flex-wrap: wrap; }
  .stat-card { flex: 1 1 calc(50% - 12px); min-width: 140px; }
  .content-grid { grid-template-columns: 1fr; }
}
</style>
