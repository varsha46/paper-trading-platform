import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],

  server: {
    proxy: {
      "/api": {
        target: "http://16.171.0.118",
        changeOrigin: true,
      },

      "/ws": {
        target: "ws://16.171.0.118",
        ws: true,
        changeOrigin: true,
      },
    },
  },
});