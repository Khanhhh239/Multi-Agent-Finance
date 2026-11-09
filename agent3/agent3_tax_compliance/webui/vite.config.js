import { defineConfig } from 'vite';
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';

const design = fileURLToPath(new URL('../../../design/', import.meta.url));
function platformAssets() {
  const files = () => new Map([
    ...['platform-theme.css', 'platform-theme.js'].map((name) => [name, readFileSync(design + name)]),
    ...readdirSync(design + 'fonts').filter((n) => n.endsWith('.woff2')).map((name) => ['platform-fonts/' + name, readFileSync(design + 'fonts/' + name)]),
    ['agent3-product.css', readFileSync(new URL('./src/product.css', import.meta.url))],
  ]);
  return {
    name: 'agent3-platform-assets',
    transformIndexHtml: { order: 'post', handler(html) {
      for (const [name, bytes] of files()) {
        if (!name.startsWith('platform-theme')) continue;
        const hash = createHash('sha256').update(bytes).digest('hex').slice(0, 8);
        html = html.replace(new RegExp('/assets/' + name.replace('.', '\\.') + '(?:\\?v=[a-f0-9]+)?', 'g'), '/assets/' + name + '?v=' + hash);
      }
      const hash = (name) => createHash('sha256').update(files().get(name)).digest('hex').slice(0, 8);
      return html.replace('</head>', `<link rel="stylesheet" href="/assets/platform-theme.css?v=${hash('platform-theme.css')}">\n<script src="/assets/platform-theme.js?v=${hash('platform-theme.js')}"></script>\n<link rel="stylesheet" href="/assets/agent3-product.css?v=${hash('agent3-product.css')}">\n</head>`);
    } },
    generateBundle() {
      for (const [name, source] of files()) this.emitFile({ type: 'asset', fileName: 'assets/' + name, source });
    },
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const name = (req.url || '').split('?')[0].replace(/^\/assets\//, '');
        const source = files().get(name);
        if (!source) return next();
        res.setHeader('Content-Type', name.endsWith('.css') ? 'text/css' : name.endsWith('.js') ? 'text/javascript' : 'font/woff2');
        res.end(source);
      });
    },
  };
}

export default defineConfig({
  base: '/',
  plugins: [{ name: 'agent3-theme-links', transformIndexHtml: { order: 'pre', handler(html) {
    return html.replace(/<link[^>]+href="\/assets\/platform-theme\.css[^>]*>/g, '').replace(/<script[^>]+src="\/assets\/platform-theme\.js[^>]*><\/script>/g, '');
  } } }, platformAssets()],
  build: { outDir: '../src/assistant/static', emptyOutDir: true, assetsDir: 'assets' },
  server: { proxy: { '/api': 'http://127.0.0.1:8640' } },
});
