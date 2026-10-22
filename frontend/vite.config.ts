import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The FastAPI backend (docs/API.md) runs on :8000. In dev the proxy makes /v1 same-origin, so
// no CORS setup is needed; in production set VITE_API_BASE to the API origin.
const API = process.env.VITE_DEV_API ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '127.0.0.1', // deterministic: 'localhost' can resolve to IPv6 only, which some browsers skip
    proxy: {
      '/v1': { target: API, changeOrigin: true },
      '/api': { target: API, changeOrigin: true },
      '/health': { target: API, changeOrigin: true },
    },
  },
  build: {
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (id.includes('node_modules/three')) return 'three'
        },
      },
    },
  },
})
