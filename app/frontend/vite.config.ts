import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Load env vars from .env files (e.g., .env.production for production builds)
  const env = loadEnv(mode, process.cwd(), '')
  const backendUrl = env.VITE_BACKEND_URL?.trim()
  const appBase = env.VITE_APP_BASE?.trim() || '/'

  // Production builds (GitHub Pages) require VITE_BACKEND_URL to be set
  // pointing to the deployed backend (Railway/Render).
  // Local development uses Vite's proxy to forward /api to localhost:8000.
  const isDev = mode === 'development'

  return {
    base: appBase,
    plugins: [react()],
    server: isDev && !backendUrl
      ? {
          proxy: {
            '/api': {
              target: 'http://localhost:8000',
              rewrite: (path) => path.replace(/^\/api/, ''),
            },
          },
        }
      : undefined,
  }
})
