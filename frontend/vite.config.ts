/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// During development the browser talks to Vite on :5173, which forwards /api to FastAPI on :8000.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Fail clearly instead of moving to another port: the launchers open :5173, and a second
    // copy on :5174 usually means an older copy of the app is still running.
    strictPort: true,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  preview: {
    port: 4173,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  test: { environment: 'node' },
});
