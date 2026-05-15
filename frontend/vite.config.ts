import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '../', '')
  const frontendPort = Number(env.VITE_TELEOP_FRONTEND_PORT || env.TELEOP_FRONTEND_PORT || 5173)

  return {
    envDir: '../',
    plugins: [react()],
    server: {
      host: env.VITE_TELEOP_FRONTEND_HOST || env.TELEOP_FRONTEND_HOST || '0.0.0.0',
      port: Number.isInteger(frontendPort) ? frontendPort : 5173,
    },
  }
})
