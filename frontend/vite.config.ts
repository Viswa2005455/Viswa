/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// During development the browser talks to Vite on :5173, which forwards /api to FastAPI on :8000.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  preview: {
    port: 4173,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  test: { environment: 'node' },
});
