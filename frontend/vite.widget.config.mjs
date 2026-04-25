import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import cssInjectedByJs from 'vite-plugin-css-injected-by-js';
import path from 'path';
import { fileURLToPath } from 'url';
import { createRequire } from 'module';

const require = createRequire(import.meta.url);
const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Load .env so REACT_APP_BACKEND_URL is available at build time
try {
  require('dotenv').config({ path: path.resolve(__dirname, '.env') });
} catch { /* dotenv optional */ }

const backendUrl = process.env.REACT_APP_BACKEND_URL || '';

export default defineConfig({
  plugins: [
    react(),
    cssInjectedByJs(), // inlines CSS into the JS bundle — single file embed
  ],

  // Don't serve/copy the public folder (we're only building a lib)
  publicDir: false,

  define: {
    'process.env.REACT_APP_BACKEND_URL': JSON.stringify(backendUrl),
    'process.env.NODE_ENV': JSON.stringify('production'),
    'process.env': JSON.stringify({}),
  },

  build: {
    outDir: 'dist/widget',
    emptyOutDir: true,

    lib: {
      entry: path.resolve(__dirname, 'src/widget-entry.jsx'),
      name: 'SevaChatWidget',
      fileName: () => 'seva-widget.js',
      formats: ['iife'],
    },
  },

  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
});
