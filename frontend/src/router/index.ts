import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/dashboard' },
  { path: '/dashboard', name: 'Dashboard', component: () => import('../views/Dashboard.vue'), meta: { title: '概览' } },
  { path: '/upload', name: 'Upload', component: () => import('../views/Upload.vue'), meta: { title: '上传解析' } },
  { path: '/tasks', name: 'Tasks', component: () => import('../views/Tasks.vue'), meta: { title: '任务管理' } },
  { path: '/logs', name: 'Logs', component: () => import('../views/Logs.vue'), meta: { title: '运行日志' } },
  { path: '/settings', name: 'Settings', component: () => import('../views/Settings.vue'), meta: { title: '系统设置' } },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
