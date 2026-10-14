import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';
export default defineConfig({
  plugins: [react(), VitePWA({
    registerType: 'autoUpdate',
    includeAssets: ['icon-192.png', 'icon-512.png'],
    manifest: {
      name: 'whichcard — your local wallet', short_name: 'whichcard', description: 'Make your next swipe count. Private, local card recommendations.',
      theme_color: '#275f46', background_color: '#f6f7f2', display: 'standalone', start_url: '/', scope: '/',
      icons: [{ src: '/icon-192.png', sizes: '192x192', type: 'image/png' }, { src: '/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any maskable' }],
    },
    workbox: {
      navigateFallbackDenylist: [/^\/api/],
      globPatterns: ['**/*.{js,css,html,png,svg,webmanifest}'],
      runtimeCaching: [{ urlPattern: ({ url }) => url.origin === self.location.origin && url.pathname.startsWith('/api/'), handler: 'NetworkFirst', method: 'GET', options: { cacheName: 'whichcard-local-data-v1', networkTimeoutSeconds: 3, cacheableResponse: { statuses: [200] }, expiration: { maxEntries: 100 } } }],
    },
  })],
  server: { host: '127.0.0.1', proxy: { '/api': 'http://127.0.0.1:8787' } },
});
