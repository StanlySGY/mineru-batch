<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { Delete, Refresh, ArrowDown, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, type LogGroup } from '../api'
import { formatTime, statusTag } from '../utils/format'

const groups = ref<LogGroup[]>([])
const total = ref(0)
const page = ref(1)
const size = ref(20)
const filterLevel = ref('')
const filterSearch = ref('')
const loading = ref(false)
const firstLoad = ref(true)
const expandedTaskIds = ref<Set<number>>(new Set())
const expandedLogId = ref<number | null>(null)
const allExpanded = ref(false)
let timer: ReturnType<typeof setInterval> | null = null

const levelSummary = computed(() => {
  const s = { info: 0, warn: 0, error: 0 }
  for (const g of groups.value) for (const l of g.logs) s[l.level] = (s[l.level] || 0) + 1
  return s
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

function toggleAllGroups() {
  if (allExpanded.value) {
    expandedTaskIds.value = new Set()
    allExpanded.value = false
  } else {
    expandedTaskIds.value = new Set(groups.value.map(g => g.task_id))
    allExpanded.value = true
  }
}

function handleFilterChange() {
  page.value = 1
  loadLogs()
}

function handleSearch() {
  page.value = 1
  loadLogs()
}

function handlePageChange(val: number) {
  page.value = val
  loadLogs()
}

function formatRelative(iso: string | null) {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return Math.floor(diff / 60000) + ' 分钟前'
  if (diff < 86400000) return Math.floor(diff / 3600000) + ' 小时前'
  return Math.floor(diff / 86400000) + ' 天前'
}

function matchSearch(msg: string): boolean {
  if (!filterSearch.value) return true
  return msg.toLowerCase().includes(filterSearch.value.toLowerCase())
}

const statusTagType: Record<string, string> = {
  pending: statusTag.pending.type, processing: statusTag.processing.type,
  completed: statusTag.completed.type, failed: statusTag.failed.type,
}
const statusLabel: Record<string, string> = {
  pending: '等待', processing: '处理中', completed: '完成', failed: '失败',
}

const levelColor: Record<string, string> = {
  info: '#67c23a', warn: '#e6a23c', error: '#f56c6c',
}

function hasActiveLogs() {
  return groups.value.some(g => g.status === 'processing' || g.status === 'pending')
}

onMounted(() => {
  loadLogs()
  timer = setInterval(() => { if (hasActiveLogs()) loadLogs() }, 8000)
})
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<template>
<el-card shadow="never" class="logs-card">
  <template #header>
    <div class="card-header">
      <span class="card-title">运行日志</span>
      <div class="filter-row">
        <el-input v-model="filterSearch" placeholder="搜索日志内容" clearable style="width:160px" size="small" :prefix-icon="Search" @clear="handleSearch" @keyup.enter="handleSearch" />
        <el-select v-model="filterLevel" placeholder="级别" clearable style="width:100px" size="small" @change="handleFilterChange">
          <el-option label="INFO" value="info" />
          <el-option label="WARN" value="warn" />
          <el-option label="ERROR" value="error" />
        </el-select>
        <span class="level-badges">
          <span v-if="levelSummary.info" class="level-badge info">{{ levelSummary.info }} INFO</span>
          <span v-if="levelSummary.warn" class="level-badge warn">{{ levelSummary.warn }} WARN</span>
          <span v-if="levelSummary.error" class="level-badge error">{{ levelSummary.error }} ERROR</span>
        </span>
        <el-button size="small" plain @click="toggleAllGroups">{{ allExpanded ? '收起全部' : '展开全部' }}</el-button>
        <el-button :icon="Refresh" @click="loadLogs" circle size="small" />
        <el-button :icon="Delete" @click="handleClear" type="danger" size="small" plain>清空</el-button>
      </div>
    </div>
  </template>

  <el-skeleton v-if="firstLoad" :rows="6" animated />
  <div v-else class="log-groups" v-loading="loading">
    <div v-if="!groups.length" class="empty-state">
      <el-empty description="暂无日志" />
    </div>

    <div v-for="g in groups" :key="g.task_id" class="log-group">
      <div class="group-header" @click="toggleGroup(g.task_id)">
        <el-icon :size="14" class="group-arrow" :class="{ rotated: isGroupExpanded(g.task_id) }">
          <ArrowDown />
        </el-icon>
        <span class="group-task-id">#{{ g.task_id }}</span>
        <span class="group-filename">{{ g.filename }}</span>
        <el-tag :type="statusTagType[g.status] as any" size="small" class="group-status">
          {{ statusLabel[g.status] || g.status }}
        </el-tag>
        <span class="group-meta">
          <span v-if="g.created_at" class="group-time">{{ formatTime(g.created_at) }}</span>
          <span class="group-relative">{{ formatRelative(g.created_at) }}</span>
        </span>
        <span class="group-count">{{ g.logs.length }} 条日志</span>
      </div>

      <div v-if="isGroupExpanded(g.task_id)" class="group-logs">
        <div
          v-for="log in g.logs"
          :key="log.id"
          v-show="matchSearch(log.message)"
          class="log-row"
          :class="{ 'log-error': log.level === 'error', 'log-warn': log.level === 'warn' }"
        >
          <div class="log-main" @click="log.detail ? toggleLogDetail(log.id) : null" :style="{ cursor: log.detail ? 'pointer' : 'default' }">
            <span class="log-badge" :style="{ background: levelColor[log.level] || '#909399' }">
              {{ log.level?.toUpperCase() }}
            </span>
            <span class="log-msg">{{ log.message }}</span>
            <span class="log-time">{{ formatTime(log.created_at) }}</span>
            <el-icon v-if="log.detail" class="log-expand" :size="14">
              <ArrowDown :class="{ rotated: expandedLogId === log.id }" />
            </el-icon>
          </div>
          <div v-if="expandedLogId === log.id && log.detail" class="log-detail">
            <pre>{{ log.detail }}</pre>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div class="pagination-row" v-if="total > size">
    <el-pagination background layout="prev, pager, next" :total="total" :page-size="size" :current-page="page" @current-change="handlePageChange" />
  </div>
</el-card>
</template>

<style scoped>
.logs-card { border-radius: 10px; height: 100%; display: flex; flex-direction: column; }
.logs-card :deep(.el-card__body) { flex: 1; overflow: hidden; display: flex; flex-direction: column; }
.card-header { display: flex; align-items: center; }
.card-header .filter-row { margin-left: auto; display: flex; align-items: center; gap: 8px; }
.card-title { font-weight: 600; }
.log-groups { flex: 1; overflow-y: auto; }

.log-group { border: 1px solid #ebeef5; border-radius: 8px; margin-bottom: 10px; overflow: hidden; }
.group-header {
  display: flex; align-items: center; gap: 10px; padding: 12px 14px;
  background: #fafbfc; cursor: pointer; transition: background 0.15s; user-select: none;
}
.group-header:hover { background: #f0f2f5; }
.group-arrow { color: #909399; transition: transform 0.2s; flex-shrink: 0; }
.group-arrow.rotated { transform: rotate(180deg); }
.group-task-id { color: #409eff; font-weight: 700; font-size: 13px; flex-shrink: 0; }
.group-filename { flex: 1; font-weight: 500; color: #303133; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.group-status { flex-shrink: 0; }
.group-meta {
  display: flex; flex-direction: column; align-items: flex-end; gap: 1px; flex-shrink: 0;
}
.group-time { font-size: 12px; color: #606266; white-space: nowrap; }
.group-relative { font-size: 11px; color: #909399; }
.group-count { font-size: 12px; color: #909399; flex-shrink: 0; }

.group-logs { border-top: 1px solid #ebeef5; }
.log-row { border-bottom: 1px solid #f5f5f5; }
.log-row:last-child { border-bottom: none; }
.log-error { background: #fef0f0; }
.log-warn { background: #fdf6ec; }
.log-main {
  display: flex; align-items: center; gap: 10px; padding: 8px 14px; font-size: 13px;
}
.log-badge {
  display: inline-block; padding: 1px 8px; border-radius: 3px;
  color: #fff; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; flex-shrink: 0;
}
.log-msg { flex: 1; color: #303133; word-break: break-all; }
.log-time { color: #606266; font-size: 12px; flex-shrink: 0; white-space: nowrap; font-variant-numeric: tabular-nums; }
.log-expand { color: #909399; transition: transform 0.2s; flex-shrink: 0; }
.log-expand.rotated { transform: rotate(180deg); }
.log-detail { padding: 0 14px 10px 14px; }
.log-detail pre {
  background: #1e1e1e; color: #d4d4d4; padding: 12px; border-radius: 6px;
  font-size: 12px; line-height: 1.6; white-space: pre-wrap; word-break: break-all;
  margin: 0; max-height: 300px; overflow-y: auto;
}
.pagination-row { display: flex; justify-content: center; margin-top: 16px; }
.empty-state { padding: 40px 0; }
.level-badges { display: flex; gap: 4px; }
.level-badge {
  font-size: 11px; padding: 2px 8px; border-radius: 3px;
  color: #fff; font-weight: 600;
}
.level-badge.info { background: #67c23a; }
.level-badge.warn { background: #e6a23c; }
.level-badge.error { background: #f56c6c; }
</style>
