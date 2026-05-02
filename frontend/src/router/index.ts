import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/dashboard' },
  { path: '/dashboard', name: 'Dashboard', component: () => import('../views/Dashboard.vue'), meta: { title: '概览' } },
  { path: '/upload', name: 'Upload', component: () => import('../views/Upload.vue'), meta: { title: '上传解析' } },
  { path: '/tasks', name: 'Tasks', component: () => import('../views/Tasks.vue'), meta: { title: '任务管理' } },
  { path: '/logs', name: 'Logs', component: () => import('../views/Logs.vue'), meta: { title: '运行日志' } },
  { path: '/settings', name: 'Settings', component: () => import('../views/Settings.vue'), meta: { title: '系统设置' } },
  { path: '/:pathMatch(.*)*', name: 'NotFound', component: () => import('../views/NotFound.vue'), meta: { title: '页面不存在' } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.afterEach((to) => {
  document.title = `${to.meta.title || 'MinerU'} - MinerU Batch`
})

export default router
