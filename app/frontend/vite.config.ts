import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const backendUrl = env.VITE_BACKEND_URL?.trim()
  const appBase = env.VITE_APP_BASE?.trim() || '/'

  return {
    base: appBase,
    plugins: [react()],
    server: backendUrl
      ? undefined
      : {
          proxy: {
            '/api': {
              target: 'http://localhost:8000',
              rewrite: (path) => path.replace(/^\/api/, ''),
            },
          },
        },
  }
})
