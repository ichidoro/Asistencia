import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  build: {
    // Output directly to the existing frontend/js directory
    outDir: path.resolve(__dirname, '../frontend/js'),
    emptyOutDir: false, // CRITICAL: do not delete other JS files in frontend/js
    rollupOptions: {
      input: path.resolve(__dirname, 'src/main.jsx'),
      output: {
        entryFileNames: 'dashboard_react.js',
        chunkFileNames: '[name].js',
        assetFileNames: '[name].[ext]',
        // Disable code splitting to bundle everything into a single file
        manualChunks: undefined
      }
    }
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src')
    }
  }
});
