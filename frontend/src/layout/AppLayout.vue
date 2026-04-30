<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  DataAnalysis, UploadFilled, List, Document, Setting, Expand, Fold,
} from '@element-plus/icons-vue'
import { api } from '../api'

const router = useRouter()
const route = useRoute()
const collapsed = ref(false)
const sseConnected = ref(false)
const concurrency = ref(0)

const navItems = [
  { path: '/dashboard', icon: DataAnalysis, label: '概览' },
  { path: '/upload', icon: UploadFilled, label: '上传解析' },
  { path: '/tasks', icon: List, label: '任务管理' },
  { path: '/logs', icon: Document, label: '运行日志' },
  { path: '/settings', icon: Setting, label: '系统设置' },
]

const currentPath = computed(() => route.path)
const sidebarWidth = computed(() => (collapsed.value ? '64px' : '220px'))
const isMobile = ref(false)

function checkMobile() {
  isMobile.value = window.innerWidth <= 768
  if (isMobile.value) collapsed.value = true
}

function navigate(path: string) {
  router.push(path)
  if (isMobile.value) collapsed.value = true
}

let sseClose: (() => void) | null = null
onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
  api.getConcurrency().then(r => concurrency.value = r.concurrency).catch(() => {})
  sseClose = api.onTaskEvent(() => { sseConnected.value = true })
  setTimeout(() => { if (!sseConnected.value) sseConnected.value = false }, 5000)
})
onUnmounted(() => {
  if (sseClose) sseClose()
  window.removeEventListener('resize', checkMobile)
})
</script>

<template>
<div class="layout">
  <div v-if="isMobile && !collapsed" class="sidebar-overlay" @click="collapsed = true"></div>
  <aside class="sidebar" :class="{ 'sidebar-mobile': isMobile }" :style="{ width: sidebarWidth }" v-show="!isMobile || !collapsed">
    <div class="sidebar-logo" @click="navigate('/dashboard')">
      <div class="logo-icon">
        <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
          <line x1="16" y1="13" x2="8" y2="13"/>
          <line x1="16" y1="17" x2="8" y2="17"/>
        </svg>
      </div>
      <transition name="fade">
        <span v-show="!collapsed" class="logo-text">MinerU Batch</span>
      </transition>
    </div>

    <nav class="sidebar-nav">
      <div
        v-for="item in navItems"
        :key="item.path"
        class="nav-item"
        :class="{ active: currentPath === item.path }"
        @click="navigate(item.path)"
      >
        <el-icon :size="18"><component :is="item.icon" /></el-icon>
        <transition name="fade">
          <span v-show="!collapsed" class="nav-label">{{ item.label }}</span>
        </transition>
      </div>
    </nav>

    <div class="sidebar-footer">
      <transition name="fade">
        <div v-show="!collapsed" class="sidebar-version">v1.0.0</div>
      </transition>
      <div class="nav-item collapse-toggle" @click="collapsed = !collapsed">
        <el-icon :size="18">
          <component :is="collapsed ? Expand : Fold" />
        </el-icon>
        <transition name="fade">
          <span v-show="!collapsed" class="nav-label">收起侧栏</span>
        </transition>
      </div>
    </div>
  </aside>

  <div class="main-area">
    <header class="topbar">
      <div class="topbar-left">
        <el-icon class="mobile-collapse" @click="collapsed = !collapsed" :size="20">
          <component :is="collapsed ? Expand : Fold" />
        </el-icon>
        <div class="topbar-title">{{ route.meta.title }}</div>
      </div>
      <div class="topbar-right">
        <el-tag v-if="concurrency" size="small" effect="plain" type="info">并发 {{ concurrency }}</el-tag>
        <span class="sse-status" :class="{ connected: sseConnected }">
          <span class="sse-dot"></span>
          {{ sseConnected ? '在线' : '离线' }}
        </span>
      </div>
    </header>

    <main class="page-content">
      <router-view />
    </main>
  </div>
</div>
</template>

<style scoped>
.layout {
  display: flex; height: 100vh; width: 100vw; overflow: hidden;
}

.sidebar {
  background: linear-gradient(180deg, #1a1c2e 0%, #161828 100%);
  display: flex; flex-direction: column;
  transition: width 0.25s cubic-bezier(0.4,0,0.2,1);
  overflow: hidden; flex-shrink: 0;
  box-shadow: 2px 0 8px rgba(0,0,0,0.15);
}

.sidebar-logo {
  height: 56px; display: flex; align-items: center; justify-content: center;
  gap: 10px; padding: 0 16px; border-bottom: 1px solid rgba(255,255,255,0.06);
  cursor: pointer;
}

.logo-icon {
  color: #409eff; display: flex; align-items: center; justify-content: center;
  width: 32px; height: 32px; border-radius: 8px;
  background: rgba(64,158,255,0.12);
}

.logo-text {
  color: #fff; font-size: 16px; font-weight: 700; white-space: nowrap; letter-spacing: 0.5px;
}

.sidebar-nav {
  flex: 1; padding: 8px 0; display: flex; flex-direction: column; gap: 2px;
}

.nav-item {
  display: flex; align-items: center; gap: 12px; padding: 0 20px; height: 44px;
  cursor: pointer; color: rgba(255,255,255,0.55); transition: all 0.2s;
  white-space: nowrap; overflow: hidden; border-radius: 0;
  margin: 0 8px; border-radius: 8px;
}

.nav-item:hover { color: #fff; background: rgba(255,255,255,0.06); }

.nav-item.active {
  color: #fff;
  background: linear-gradient(135deg, #409eff 0%, #337ecc 100%);
  box-shadow: 0 2px 8px rgba(64,158,255,0.3);
}

.nav-label { font-size: 14px; }

.sidebar-footer {
  border-top: 1px solid rgba(255,255,255,0.06); padding: 8px 0;
}

.collapse-toggle { opacity: 0.7; }
.collapse-toggle:hover { opacity: 1; }
.sidebar-version { font-size: 11px; color: rgba(255,255,255,0.3); text-align: center; padding: 4px 0; }

.main-area {
  flex: 1; display: flex; flex-direction: column; min-width: 0; overflow: hidden;
  background: #f0f2f5;
}

.topbar {
  height: 56px; min-height: 56px; background: #fff; display: flex; align-items: center;
  padding: 0 24px; gap: 16px; border-bottom: 1px solid #f0f0f0; flex-shrink: 0;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}

.topbar-left { display: flex; align-items: center; gap: 12px; }

.mobile-collapse { cursor: pointer; color: #666; transition: color 0.2s; display: none; }
.mobile-collapse:hover { color: #409eff; }

.topbar-title { font-size: 16px; font-weight: 600; color: #303133; }

.topbar-right { margin-left: auto; display: flex; align-items: center; gap: 12px; }
.sse-status { font-size: 12px; color: #909399; display: flex; align-items: center; gap: 4px; }
.sse-status.connected { color: #67c23a; }
.sse-dot { width: 6px; height: 6px; border-radius: 50%; background: #909399; }
.sse-status.connected .sse-dot { background: #67c23a; }

.page-content { flex: 1; overflow-y: auto; padding: 24px; width: 100%; }

.fade-enter-active, .fade-leave-active { transition: opacity 0.2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

.sidebar-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 99;
}
.sidebar-mobile {
  position: fixed; left: 0; top: 0; bottom: 0; z-index: 100;
}

@media (max-width: 768px) {
  .mobile-collapse { display: block !important; }
  .page-content { padding: 16px; }
}
</style>
