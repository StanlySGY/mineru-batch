<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { Delete, Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, type LogGroup } from '../api'
import { formatTime } from '../utils/format'

const groups = ref<LogGroup[]>([])
const total = ref(0)
const page = ref(1)
const size = ref(20)
const filterLevel = ref('')
const loading = ref(false)
const firstLoad = ref(true)
const expandedTaskIds = ref<Set<number>>(new Set())
const expandedLogId = ref<number | null>(null)
let sseClose: (() => void) | null = null

const levelSummary = computed(() => {
  const s = { info: 0, warn: 0, error: 0 }
  for (const g of groups.value) for (const l of g.logs) {
    if (l.message.includes('MinerU') || l.message.includes('API') || l.message.includes('连接') || l.message.includes('超时')) {
      s[l.level] = (s[l.level] || 0) + 1
    }
  }
  return s
})

const filteredGroups = computed(() => {
  return groups.value.filter(g => {
    const hasMinerULog = g.logs.some(l =>
      l.message.includes('MinerU') ||
      l.message.includes('API') ||
      l.message.includes('连接') ||
      l.message.includes('超时') ||
      l.message.includes('Webhook')
    )
    return hasMinerULog
  })
})

async function loadLogs() {
  loading.value = true
  try {
    const res = await api.listLogsGrouped({
      level: filterLevel.value || undefined,
      page: page.value,
      size: size.value,
    })
    groups.value = res.items
    total.value = res.total
  } finally {
    loading.value = false
    firstLoad.value = false
  }
}

async function handleClear() {
  try {
    await ElMessageBox.confirm('确定清空所有日志？', '确认', { type: 'warning' })
    await api.clearLogs()
    ElMessage.success('日志已清空')
    loadLogs()
  } catch {}
}

function toggleGroup(taskId: number) {
  if (expandedTaskIds.value.has(taskId)) {
    expandedTaskIds.value.delete(taskId)
  } else {
    expandedTaskIds.value.add(taskId)
  }
}

function isGroupExpanded(taskId: number) {
  return expandedTaskIds.value.has(taskId)
}

function toggleLogDetail(id: number) {
  expandedLogId.value = expandedLogId.value === id ? null : id
}

function getLevelColor(level: string) {
  const colors: Record<string, string> = {
    info: '#409eff',
    warn: '#e6a23c',
    error: '#f56c6c',
  }
  return colors[level] || '#909399'
}

function getMinerULogs(logs: any[]) {
  return logs.filter(l =>
    l.message.includes('MinerU') ||
    l.message.includes('API') ||
    l.message.includes('连接') ||
    l.message.includes('超时') ||
    l.message.includes('Webhook')
  )
}

onMounted(() => {
  loadLogs()
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  sseClose = api.onTaskEvent(
    () => {
      if (debounceTimer) clearTimeout(debounceTimer)
      debounceTimer = setTimeout(() => loadLogs(), 500)
    },
  )
})

onUnmounted(() => {
  sseClose?.()
})
</script>

<template>
  <div class="mineru-logs-container">
    <div class="header">
      <h1>🔌 MinerU 节点日志</h1>
      <p class="subtitle">实时查看 MinerU API 调用、连接状态、超时等关键日志</p>
    </div>

    <div class="toolbar">
      <div class="stats">
        <div class="stat-item">
          <span class="label">信息</span>
          <span class="count" style="color: #409eff">{{ levelSummary.info }}</span>
        </div>
        <div class="stat-item">
          <span class="label">警告</span>
          <span class="count" style="color: #e6a23c">{{ levelSummary.warn }}</span>
        </div>
        <div class="stat-item">
          <span class="label">错误</span>
          <span class="count" style="color: #f56c6c">{{ levelSummary.error }}</span>
        </div>
      </div>

      <div class="controls">
        <el-select v-model="filterLevel" placeholder="日志级别" clearable @change="page = 1; loadLogs()">
          <el-option label="信息" value="info" />
          <el-option label="警告" value="warn" />
          <el-option label="错误" value="error" />
        </el-select>
        <el-button :icon="Refresh" @click="loadLogs" :loading="loading">刷新</el-button>
        <el-button :icon="Delete" type="danger" @click="handleClear">清空日志</el-button>
      </div>
    </div>

    <div class="logs-list" v-loading="loading && firstLoad">
      <div v-if="filteredGroups.length === 0 && !loading" class="empty-state">
        <p>暂无 MinerU 相关日志</p>
      </div>

      <div v-for="group in filteredGroups" :key="group.task_id" class="log-group">
        <div class="group-header" @click="toggleGroup(group.task_id)">
          <div class="group-info">
            <span class="toggle-icon" :class="{ expanded: isGroupExpanded(group.task_id) }">▶</span>
            <span class="filename">{{ group.filename }}</span>
            <span class="status" :style="{ color: group.status === 'completed' ? '#67c23a' : group.status === 'failed' ? '#f56c6c' : '#e6a23c' }">
              {{ group.status }}
            </span>
            <span class="time">{{ formatTime(group.created_at) }}</span>
          </div>
          <div class="log-count">
            {{ getMinerULogs(group.logs).length }} 条日志
          </div>
        </div>

        <transition name="expand">
          <div v-show="isGroupExpanded(group.task_id)" class="group-content">
            <div v-for="log in getMinerULogs(group.logs)" :key="log.id" class="log-item">
              <div class="log-header" @click="toggleLogDetail(log.id)">
                <span class="level-badge" :style="{ backgroundColor: getLevelColor(log.level) }">{{ log.level.toUpperCase() }}</span>
                <span class="message">{{ log.message }}</span>
                <span class="time">{{ formatTime(log.created_at) }}</span>
              </div>
              <transition name="expand">
                <div v-show="expandedLogId === log.id" class="log-detail">
                  <pre>{{ log.detail }}</pre>
                </div>
              </transition>
            </div>
          </div>
        </transition>
      </div>
    </div>

    <div class="pagination">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="size"
        :page-sizes="[10, 20, 50]"
        :total="total"
        layout="total, sizes, prev, pager, next"
        @change="loadLogs"
      />
    </div>
  </div>
</template>

<style scoped>
.mineru-logs-container {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.header {
  margin-bottom: 24px;
}

.header h1 {
  margin: 0 0 8px 0;
  font-size: 24px;
  color: #333;
}

.subtitle {
  margin: 0;
  color: #666;
  font-size: 14px;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
  padding: 16px;
  background: #f5f7fa;
  border-radius: 4px;
}

.stats {
  display: flex;
  gap: 24px;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.stat-item .label {
  color: #666;
  font-size: 14px;
}

.stat-item .count {
  font-weight: bold;
  font-size: 18px;
}

.controls {
  display: flex;
  gap: 8px;
}

.controls :deep(.el-select) {
  width: 120px;
}

.logs-list {
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  overflow: hidden;
}

.empty-state {
  padding: 40px;
  text-align: center;
  color: #909399;
}

.log-group {
  border-bottom: 1px solid #ebeef5;
}

.log-group:last-child {
  border-bottom: none;
}

.group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: #fafafa;
  cursor: pointer;
  transition: background 0.2s;
}

.group-header:hover {
  background: #f0f2f5;
}

.group-info {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
}

.toggle-icon {
  display: inline-block;
  transition: transform 0.2s;
  color: #909399;
}

.toggle-icon.expanded {
  transform: rotate(90deg);
}

.filename {
  font-weight: 500;
  color: #333;
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 2px;
  background: #f0f9ff;
}

.time {
  color: #909399;
  font-size: 12px;
  margin-left: auto;
}

.log-count {
  color: #909399;
  font-size: 12px;
  margin-left: 16px;
}

.group-content {
  padding: 0;
  background: #fff;
}

.log-item {
  border-top: 1px solid #ebeef5;
}

.log-item:first-child {
  border-top: none;
}

.log-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  cursor: pointer;
  transition: background 0.2s;
}

.log-header:hover {
  background: #f5f7fa;
}

.level-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 2px;
  color: white;
  font-size: 11px;
  font-weight: bold;
  min-width: 50px;
  text-align: center;
}

.message {
  flex: 1;
  color: #333;
  font-size: 14px;
  word-break: break-word;
}

.log-detail {
  padding: 12px 16px;
  background: #f5f7fa;
  border-top: 1px solid #ebeef5;
}

.log-detail pre {
  margin: 0;
  padding: 12px;
  background: #fff;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  overflow-x: auto;
  font-size: 12px;
  line-height: 1.5;
  color: #333;
}

.pagination {
  display: flex;
  justify-content: center;
  margin-top: 20px;
}

.expand-enter-active,
.expand-leave-active {
  transition: all 0.3s ease;
}

.expand-enter-from,
.expand-leave-to {
  opacity: 0;
  max-height: 0;
}

@media (max-width: 768px) {
  .toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .controls {
    flex-direction: column;
  }

  .controls :deep(.el-select) {
    width: 100%;
  }

  .group-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .log-count {
    margin-left: 0;
    margin-top: 8px;
  }

  .log-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .time {
    margin-left: 0;
    margin-top: 8px;
  }
}
</style>
