import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  optimizeDeps: {
    // maplibre-gl bundles its own worker — exclude from Vite pre-bundling
    exclude: ['maplibre-gl'],
  },
  define: {
    '__APP_VERSION__': JSON.stringify('0.5.0-phase5'),
  },
})


