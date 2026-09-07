import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiTarget: string = process.env.FEWIA_API_TARGET ?? "http://127.0.0.1:8010";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    proxy: {
      "/api": {
        target: apiTarget,
        changeOrigin: true,
        rewrite: (path: string) => path.slice(4),
      },
    },
  },
});
