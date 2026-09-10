import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { sites } from '@openai/sites-vite-plugin'

// https://vite.dev/config/
export default defineConfig({
  base: process.env.VITE_BASE_PATH || '/',
  plugins: [react(), sites()],
  worker: { format: 'es' },
  build: { target: 'esnext' },
  server: {
    proxy: {
      '/api': {
        target: process.env.API_PROXY_TARGET || 'http://localhost:8000',
        rewrite: (path) => process.env.VITE_BROWSER_ENGINE === 'true' ? path : path.replace(/^\/api/, ''),
      },
    },
  },
})
