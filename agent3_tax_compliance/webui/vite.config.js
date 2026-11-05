import { defineConfig } from 'vite';

export default defineConfig({
  base: '/',
  build: { outDir: '../src/assistant/static', emptyOutDir: true, assetsDir: 'assets' },
  server: { proxy: { '/api': 'http://127.0.0.1:8640' } },
});
