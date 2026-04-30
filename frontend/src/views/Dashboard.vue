<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { Clock, Loading, SuccessFilled, CircleClose, Files, UploadFilled } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { api } from '../api'

const router = useRouter()
const stats = ref({ total: 0, pending: 0, processing: 0, completed: 0, failed: 0 })
const recentTasks = ref<any[]>([])
const loading = ref(false)
const firstLoad = ref(true)
let timer: ReturnType<typeof setInterval> | null = null
let sseClose: (() => void) | null = null

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

async function loadStats() {
  loading.value = true
  try {
    const [statsRes, recentRes] = await Promise.all([
      api.getStats(),
      api.listTasks({ page: 1, size: 5 }),
    ])
    stats.value = statsRes
    recentTasks.value = recentRes.items
  } catch {
  } finally {
    loading.value = false
    firstLoad.value = false
  }
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
  loadStats()
  timer = setInterval(loadStats, 30000)
  sseClose = api.onTaskEvent((evt) => {
    if (evt.type === 'task_update') loadStats()
  })
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
  if (sseClose) sseClose()
})
</script>

<template>
  <div class="dashboard" v-if="firstLoad">
    <div class="stat-grid">
      <el-skeleton v-for="i in 5" :key="i" animated style="border-radius:12px">
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
  <div class="stat-grid">
    <div v-for="c in cards" :key="c.key" class="stat-card clickable" :style="{ background: c.bg }" @click="handleCardClick(c.route)">
      <div class="stat-icon" :style="{ color: c.color }">
        <el-icon :size="28"><component :is="c.icon" /></el-icon>
      </div>
      <div class="stat-info">
        <div class="stat-value" :style="{ color: c.color }">{{ stats[c.key as keyof typeof stats] }}</div>
        <div class="stat-label" :style="{ color: c.color }">{{ c.label }}</div>
      </div>
    </div>
  </div>

  <div class="extra-stats">
    <el-card shadow="never" class="rate-card">
      <div class="rate-item">
        <span class="rate-label">成功率</span>
        <span class="rate-value success">{{ successRate }}</span>
      </div>
      <el-divider direction="vertical" />
      <div class="rate-item">
        <span class="rate-label">失败率</span>
        <span class="rate-value danger">{{ failureRate }}</span>
      </div>
      <el-divider direction="vertical" />
      <div class="rate-item">
        <span class="rate-label">处理中</span>
        <span class="rate-value warning">{{ stats.processing }}</span>
      </div>
    </el-card>
  </div>

  <div class="bottom-grid">
    <el-card shadow="never" class="recent-card">
      <template #header>
        <span class="card-title">最近任务</span>
      </template>
      <el-table :data="recentTasks" stripe size="small">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="original_filename" label="文件名" min-width="180" show-overflow-tooltip />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="{ pending:'info', processing:'warning', completed:'success', failed:'danger' }[row.status]" size="small">
              {{ statusLabel[row.status] || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
      </el-table>
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

<style scoped>
.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 16px; margin-bottom: 16px;
}
.stat-card {
  border-radius: 12px; padding: 20px 24px;
  display: flex; align-items: center; gap: 16px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.08);
  transition: transform 0.2s, box-shadow 0.2s;
}
.stat-card.clickable { cursor: pointer; }
.stat-card:hover { transform: translateY(-2px); box-shadow: 0 6px 16px rgba(0,0,0,0.12); }
.stat-icon { display: flex; opacity: 0.9; }
.stat-value { font-size: 28px; font-weight: 700; line-height: 1.2; }
.stat-label { font-size: 13px; opacity: 0.85; margin-top: 4px; }

.extra-stats { margin-bottom: 20px; }
.rate-card { border-radius: 12px; }
.rate-card :deep(.el-card__body) { display: flex; align-items: center; justify-content: center; gap: 24px; padding: 16px 24px; }
.rate-item { display: flex; flex-direction: column; align-items: center; gap: 4px; }
.rate-label { font-size: 12px; color: #909399; }
.rate-value { font-size: 22px; font-weight: 700; }
.rate-value.success { color: #67c23a; }
.rate-value.danger { color: #f56c6c; }
.rate-value.warning { color: #e6a23c; }

.bottom-grid { display: grid; grid-template-columns: 1fr 320px; gap: 20px; }
.recent-card { border-radius: 12px; }
.quick-card { border-radius: 12px; }
.quick-actions { display: flex; flex-direction: column; gap: 12px; }
.quick-btn { width: 100%; }
.card-title { font-weight: 600; }

@media (max-width: 900px) {
  .bottom-grid { grid-template-columns: 1fr; }
}
</style>
