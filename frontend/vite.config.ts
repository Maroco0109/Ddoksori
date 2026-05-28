import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import type { IncomingMessage } from 'node:http';

const backendProxyTarget = process.env.VITE_PROXY_TARGET ?? 'http://localhost:8000';

const bypassSpaDocumentRequest = (req: IncomingMessage) => {
  const acceptsHtml = req.headers.accept?.includes('text/html') ?? false;
  return req.method === 'GET' && acceptsHtml ? '/index.html' : undefined;
};

const backendProxy = () => ({
  target: backendProxyTarget,
  changeOrigin: true,
  bypass: bypassSpaDocumentRequest,
});

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
      '/auth/google': backendProxy(),
      '/auth/naver': backendProxy(),
      '/auth/me': backendProxy(),
      '/auth/verify': backendProxy(),
      '/auth/delete-account': backendProxy(),
      '/chat': backendProxy(),
      '/search': backendProxy(),
      '/api': backendProxy(),
      '/case': backendProxy(),
      '/health': backendProxy(),
    },
  },
  esbuild: {
    drop: process.env.NODE_ENV === 'production' ? ['console', 'debugger'] : [],
  },

});
