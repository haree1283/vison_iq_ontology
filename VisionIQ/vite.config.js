import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8080',
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on('error', (err, _req, res) => {
            if (res && res.writeHead && !res.headersSent) {
              res.writeHead(502, { 'Content-Type': 'application/json' })
              res.end(JSON.stringify({ error: 'Backend connecting...' }))
            }
          })
        },
      },
      '/socket.io': {
        target: 'http://127.0.0.1:8080',
        changeOrigin: true,
        ws: true,
        configure: (proxy) => {
          proxy.on('error', () => {
            // Gracefully handle transient socket reconnects during backend restarts
          })
        },
      },
      '/evidence': {
        target: 'http://127.0.0.1:8080',
        changeOrigin: true,
      },
      '/images': {
        target: 'http://127.0.0.1:8080',
        changeOrigin: true,
      },
      // NH5 files/streams served by the same Python backend (videos, photos, report.xlsx, live websocket)
      '^/(media|status|stream|download|live_ws)(/|\\?|$)': {
        target: 'http://127.0.0.1:8080',
        changeOrigin: true,
        ws: true,
      },
      '^/scenes/[^/]+/(frame|preview)\\.jpg': {
        target: 'http://127.0.0.1:8080',
        changeOrigin: true,
        ws: true,
      },
    },
  },
})
