import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'


export default defineConfig(({ mode }) => {

  const env = loadEnv(mode, process.cwd(), '')

  const target = env.VITE_API_URL || 'https://api.n11233885.leaflab.cab432.com/'

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target,
          changeOrigin: true,
        },
      },
    },
  }
})
