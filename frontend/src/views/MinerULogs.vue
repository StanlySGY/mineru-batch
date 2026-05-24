<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { Delete, Refresh, DocumentCopy } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox, ElDialog } from 'element-plus'
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
const containerLogsVisible = ref(false)
const containerLogs = ref('')
const containerLogsLoading = ref(false)
const containerName = ref('mineru-full')
const containerLogLines = ref(200)
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

async function loadContainerLogs() {
  containerLogsLoading.value = true
  try {
    const res = await api.getMinerUContainerLogs(containerName.value, containerLogLines.value)
    if (res.ok && res.logs) {
      containerLogs.value = res.logs
      containerLogsVisible.value = true
    } else {
      ElMessage.error(res.error || '获取容器日志失败')
    }
  } catch (e) {
    ElMessage.error('获取容器日志异常')
    console.error(e)
  } finally {
    containerLogsLoading.value = false
  }
}

function copyContainerLogs() {
  navigator.clipboard.writeText(containerLogs.value).then(() => {
    ElMessage.success('已复制到剪贴板')
  }).catch(() => {
    ElMessage.error('复制失败')
  })
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
  <div class="mineru-logs-page">
    <el-card shadow="never" class="logs-card">
      <template #header>
        <div class="page-header">
          <div>
            <span class="card-title">MinerU 节点日志</span>
            <p class="subtitle">实时查看 MinerU API 调用、连接状态、超时等关键日志</p>
          </div>
          <div class="controls">
            <el-select v-model="filterLevel" placeholder="日志级别" clearable @change="page = 1; loadLogs()">
              <el-option label="信息" value="info" />
              <el-option label="警告" value="warn" />
              <el-option label="错误" value="error" />
            </el-select>
            <el-button :icon="Refresh" @click="loadLogs" :loading="loading">刷新</el-button>
            <el-button :icon="DocumentCopy" @click="loadContainerLogs" :loading="containerLogsLoading">查看原始日志</el-button>
            <el-button :icon="Delete" type="danger" @click="handleClear">清空日志</el-button>
          </div>
        </div>
      </template>

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

      <div class="logs-list" v-loading="loading && firstLoad">
        <div v-if="filteredGroups.length === 0 && !loading" class="empty-state">
          <el-empty description="暂无 MinerU 相关日志" :image-size="80" />
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
    </el-card>

    <el-dialog v-model="containerLogsVisible" title="MinerU 容器原始日志" width="90%" :close-on-click-modal="false">
      <div class="container-logs-header">
        <div class="log-controls">
          <el-input v-model="containerName" placeholder="容器名称" style="width: 200px" />
          <el-input-number v-model="containerLogLines" :min="10" :max="1000" placeholder="日志行数" />
          <el-button :icon="Refresh" @click="loadContainerLogs" :loading="containerLogsLoading">重新加载</el-button>
          <el-button :icon="DocumentCopy" @click="copyContainerLogs">复制日志</el-button>
        </div>
      </div>
      <div class="container-logs-content">
        <pre>{{ containerLogs }}</pre>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.mineru-logs-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.logs-card {
  border-radius: 12px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.card-title {
  font-weight: 600;
}

.subtitle {
  margin: 6px 0 0;
  color: #909399;
  font-size: 13px;
}

.controls {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.controls :deep(.el-select) {
  width: 120px;
}

.stats {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: #f7f8fa;
  border-radius: 8px;
}

.stat-item .label {
  color: #909399;
  font-size: 13px;
}

.stat-item .count {
  font-weight: 700;
  font-size: 18px;
  font-variant-numeric: tabular-nums;
}

.logs-list {
  border: 1px solid #ebeef5;
  border-radius: 10px;
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
  gap: 12px;
  padding: 13px 16px;
  background: #fafafa;
  cursor: pointer;
  transition: background 0.2s;
}

.group-header:hover {
  background: #f5f7fa;
}

.group-info {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  min-width: 0;
}

.toggle-icon {
  display: inline-block;
  flex-shrink: 0;
  color: #909399;
  transition: transform 0.2s;
}

.toggle-icon.expanded {
  transform: rotate(90deg);
}

.filename {
  max-width: 360px;
  overflow: hidden;
  color: #303133;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status {
  flex-shrink: 0;
  padding: 2px 8px;
  background: #f0f9ff;
  border-radius: 10px;
  font-size: 12px;
}

.time {
  flex-shrink: 0;
  margin-left: auto;
  color: #909399;
  font-size: 12px;
}

.log-count {
  flex-shrink: 0;
  color: #909399;
  font-size: 12px;
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
  background: #f7f8fa;
}

.level-badge {
  display: inline-block;
  flex-shrink: 0;
  min-width: 50px;
  padding: 2px 8px;
  border-radius: 10px;
  color: white;
  font-size: 11px;
  font-weight: 700;
  text-align: center;
}

.message {
  flex: 1;
  min-width: 0;
  color: #303133;
  font-size: 14px;
  word-break: break-word;
}

.log-detail {
  padding: 12px 16px;
  background: #f7f8fa;
  border-top: 1px solid #ebeef5;
}

.log-detail pre {
  margin: 0;
  padding: 12px;
  overflow-x: auto;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  color: #303133;
  font-size: 12px;
  line-height: 1.5;
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

.container-logs-header {
  margin-bottom: 16px;
}

.log-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.log-controls :deep(.el-input) {
  width: auto;
}

.log-controls :deep(.el-input-number) {
  width: 120px;
}

.container-logs-content {
  max-height: 600px;
  overflow: auto;
  background: #f7f8fa;
  border: 1px solid #ebeef5;
  border-radius: 8px;
}

.container-logs-content pre {
  margin: 0;
  padding: 12px;
  color: #303133;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
  }

  .controls {
    width: 100%;
    justify-content: flex-start;
  }

  .controls :deep(.el-select) {
    width: 100%;
  }

  .controls :deep(.el-button) {
    flex: 1;
  }

  .stats {
    flex-direction: column;
  }

  .group-header,
  .log-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .group-info {
    width: 100%;
    flex-wrap: wrap;
  }

  .filename {
    max-width: 100%;
  }

  .time {
    margin-left: 0;
  }
}
</style>
