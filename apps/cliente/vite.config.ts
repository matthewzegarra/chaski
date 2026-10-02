import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['icon.svg'],
      manifest: {
        name: 'Chaski App · Banca Inteligente',
        short_name: 'Chaski',
        description: 'Tu banco 100% digital',
        lang: 'es-PE',
        theme_color: '#003b7a',
        background_color: '#f5f7fa',
        display: 'standalone',
        start_url: '/',
        icons: [{ src: 'icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any maskable' }],
      },
      workbox: {
        // Never cache API calls or the runtime config: balances must always be live.
        navigateFallbackDenylist: [/^\/api\//, /^\/env\.js$/],
        globPatterns: ['**/*.{js,css,html,svg,woff2}'],
        globIgnores: ['env.js'],
      },
    }),
  ],
  test: { environment: 'jsdom', globals: true, setupFiles: ['./src/test-setup.ts'] },
})
