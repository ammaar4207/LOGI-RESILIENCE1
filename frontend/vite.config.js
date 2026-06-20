import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      devOptions: {
        enabled: true
      },
      manifest: {
        name: 'Logi-Resilience Enterprise',
        short_name: 'LogiRes',
        description: 'Predictive maritime logistics resilience platform',
        theme_color: '#0f172a',
        icons: [
          {
            src: '/vite.svg',
            sizes: '192x192',
            type: 'image/svg+xml'
          }
        ]
      }
    })
  ],
  server: {
    host: true,
    port: 5173,
    watch: { usePolling: true }
  },
  build: {
    target: 'esnext',
    minify: 'esbuild',
    cssMinify: true,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom'],
          charts: ['react-chartjs-2']
        }
      }
    },
    chunkSizeWarningLimit: 1000
  }
})