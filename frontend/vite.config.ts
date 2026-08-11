import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // 开发期通过 vite 代理到后端，避免 CORS
      // 用 127.0.0.1 而非 localhost，避免 IPv6 解析问题
      '/admin': {
        target: 'http://127.0.0.1:10002',
        changeOrigin: true,
      },
      '/v1': {
        target: 'http://127.0.0.1:10002',
        changeOrigin: true,
      },
      '/status': {
        target: 'http://127.0.0.1:10002',
        changeOrigin: true,
      },
    },
  },
})
