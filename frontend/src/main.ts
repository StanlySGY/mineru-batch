import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import { ElMessage } from 'element-plus'
import 'element-plus/dist/index.css'
import 'highlight.js/styles/github.css'
import App from './App.vue'
import router from './router'

const app = createApp(App)

app.config.errorHandler = (err, instance, info) => {
  console.error(`[Vue Error] ${info}`, err)
  ElMessage.error('页面渲染异常，请刷新重试')
}

app.use(ElementPlus).use(router).mount('#app')
