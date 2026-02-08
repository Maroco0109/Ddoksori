import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  assetsInclude: ['**/*.png', '**/*.jpg', '**/*.jpeg', '**/*.gif', '**/*.svg'],
  server: {
    // ========================================
    // LOCAL DEVELOPMENT ONLY
    // Production uses nginx proxy (infra/nginx.conf)
    // ========================================
    proxy: {
      // Note: /auth/callback은 프론트엔드 라우트이므로 프록시에서 제외
      '/auth/google': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/auth/naver': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/auth/me': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/auth/verify': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/auth/delete-account': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/chat': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/search': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/case': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  esbuild: {
    drop: process.env.NODE_ENV === 'production' ? ['console', 'debugger'] : [],
  },

});
