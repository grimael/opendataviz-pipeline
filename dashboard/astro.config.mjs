// @ts-check
import { defineConfig } from 'astro/config';

import tailwindcss from '@tailwindcss/vite';

// https://astro.build/config
export default defineConfig({
  vite: {
    plugins: [tailwindcss()],
    server: {
      // Proxies /api/* to the local FastAPI service so the browser only
      // ever talks to one origin (localhost:4321) in dev — no second port
      // to remember, no CORS. See src/lib/config.ts.
      proxy: {
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
        },
        // Swagger UI (served at /api/docs) fetches its schema from the
        // root-relative "/openapi.json" regardless of the prefix it was
        // loaded under, so that one extra path needs its own proxy entry.
        '/openapi.json': {
          target: 'http://localhost:8000',
          changeOrigin: true,
        },
      },
    },
  }
});