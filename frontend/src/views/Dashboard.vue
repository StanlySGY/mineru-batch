<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { Clock, Loading, SuccessFilled, CircleClose, Files } from '@element-plus/icons-vue'
import { api } from '../api'

const stats = ref({ total: 0, pending: 0, processing: 0, completed: 0, failed: 0 })
const recentTasks = ref<any[]>([])
const loading = ref(false)
const firstLoad = ref(true)
let timer: ReturnType<typeof setInterval> | null = null

const cards = [
  { key: 'total', label: '总任务', icon: Files, color: '#fff', bg: 'linear-gradient(135deg, #5a67d8 0%, #6b46c1 100%)' },
  { key: 'pending', label: '等待中', icon: Clock, color: '#1a202c', bg: 'linear-gradient(135deg, #e2e8f0 0%, #cbd5e0 100%)' },
  { key: 'processing', label: '处理中', icon: Loading, color: '#fff', bg: 'linear-gradient(135deg, #ed8936 0%, #dd6b20 100%)' },
  { key: 'completed', label: '已完成', icon: SuccessFilled, color: '#fff', bg: 'linear-gradient(135deg, #38a169 0%, #2f855a 100%)' },
  { key: 'failed', label: '失败', icon: CircleClose, color: '#fff', bg: 'linear-gradient(135deg, #e53e3e 0%, #c53030 100%)' },
]

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

const statusLabel: Record<string, string> = {
  pending: '等待中', processing: '处理中', completed: '已完成', failed: '失败',
}

onMounted(() => {
  loadStats()
  timer = setInterval(loadStats, 10000)
})
onUnmounted(() => { if (timer) clearInterval(timer) })
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
    <div v-for="c in cards" :key="c.key" class="stat-card" :style="{ background: c.bg }">
      <div class="stat-icon" :style="{ color: c.color }">
        <el-icon :size="28"><component :is="c.icon" /></el-icon>
      </div>
      <div class="stat-info">
        <div class="stat-value" :style="{ color: c.color }">{{ stats[c.key as keyof typeof stats] }}</div>
        <div class="stat-label" :style="{ color: c.color }">{{ c.label }}</div>
      </div>
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
  </div>
</template>

<style scoped>
.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 16px; margin-bottom: 24px;
}
.stat-card {
  border-radius: 12px; padding: 20px 24px;
  display: flex; align-items: center; gap: 16px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.08);
  transition: transform 0.2s, box-shadow 0.2s;
}
.stat-card:hover { transform: translateY(-2px); box-shadow: 0 6px 16px rgba(0,0,0,0.12); }
.stat-icon { display: flex; opacity: 0.9; }
.stat-value { font-size: 28px; font-weight: 700; line-height: 1.2; }
.stat-label { font-size: 13px; opacity: 0.85; margin-top: 4px; }
.recent-card { border-radius: 12px; }
.card-title { font-weight: 600; }
</style>
