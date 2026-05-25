import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import pkg from './package.json'

export default defineConfig({
  plugins: [vue()],
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  build: {
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/@element-plus/icons-vue')) return 'element-icons'
          const elementComponentMatch = id.match(/node_modules\/element-plus\/es\/components\/([^/]+)/)
          if (elementComponentMatch) return `element-${elementComponentMatch[1]}`
          if (id.includes('node_modules/element-plus/es/hooks')) return 'element-hooks'
          if (id.includes('node_modules/element-plus/es/utils')) return 'element-utils'
          if (id.includes('node_modules/element-plus/es/tokens')) return 'element-utils'
          if (id.includes('node_modules/element-plus')) return 'element-core'
          if (id.includes('node_modules/echarts/lib/chart')) return 'echarts-chart'
          if (id.includes('node_modules/echarts')) return 'echarts-core'
          if (id.includes('node_modules/highlight.js')) return 'highlight'
          if (id.includes('node_modules/marked') || id.includes('node_modules/dompurify')) return 'markdown'
        },
      },
    },
  },
  server: {
    port: 3001,
    proxy: {
      '/api': {
        target: 'http://localhost:8900',
        changeOrigin: true,
      },
    },
  },
})
