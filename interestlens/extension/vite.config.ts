import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { crx } from '@crxjs/vite-plugin';
import { resolve } from 'path';
import manifest from './manifest.json';

export default defineConfig({
  plugins: [
    react(),
    crx({ manifest }),
  ],
  base: './',  // Use relative paths for Chrome extension
  build: {
    outDir: 'dist',
    rollupOptions: {
      input: {
        sidepanel: 'sidepanel.html',
        popup: 'popup.html',
      },
    },
  },
  publicDir: 'public',
});
