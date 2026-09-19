import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const gatewayTarget = env.VITE_GATEWAY_PROXY_TARGET || 'http://localhost:8080'

  return {
    plugins: [react()],
    build: {
      chunkSizeWarningLimit: 700,
      rollupOptions: {
        output: {
          manualChunks: {
            react: ['react', 'react-dom', 'react-router-dom'],
            query: ['@tanstack/react-query'],
            charts: ['recharts'],
            auth: ['keycloak-js'],
          },
        },
      },
    },
    server: {
      port: 5173,
      host: '0.0.0.0',
      proxy: {
        '/api': { target: gatewayTarget, changeOrigin: true },
        '/health': { target: gatewayTarget, changeOrigin: true },
        '/ready': { target: gatewayTarget, changeOrigin: true },
      },
    },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: './src/test/setup.ts',
      css: true,
    },
  }
})
