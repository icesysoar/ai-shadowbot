import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// AI 影刀画布前端构建配置
// 产物输出到 dist/，由 l5_gateway.py 托管（根路径 + /assets）
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    chunkSizeWarningLimit: 1500,
  },
  server: {
    port: 5173,
    proxy: {
      // 开发期代理后端 API，避免跨域
      '/api': 'http://127.0.0.1:8792',
      '/l5': 'http://127.0.0.1:8792',
    },
  },
})
