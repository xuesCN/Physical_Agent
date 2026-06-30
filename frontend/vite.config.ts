import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 1100,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) {
            return undefined;
          }
          const normalized = id.replace(/\\/g, "/");
          if (
            normalized.includes("/react/") ||
            normalized.includes("/react-dom/") ||
            normalized.includes("/scheduler/")
          ) {
            return "react-vendor";
          }
          if (normalized.includes("/@ant-design/x/")) {
            return "antd-x";
          }
          if (
            normalized.includes("/antd/") ||
            normalized.includes("/@ant-design/icons/") ||
            normalized.includes("/@ant-design/cssinjs/") ||
            normalized.includes("/@ant-design/colors/") ||
            normalized.includes("/@rc-component/") ||
            normalized.includes("/rc-")
          ) {
            return "antd-vendor";
          }
          if (
            normalized.includes("/react-markdown/") ||
            normalized.includes("/remark-") ||
            normalized.includes("/micromark") ||
            normalized.includes("/unified/") ||
            normalized.includes("/vfile/") ||
            normalized.includes("/hast") ||
            normalized.includes("/mdast") ||
            normalized.includes("/unist")
          ) {
            return "markdown-vendor";
          }
          return undefined;
        }
      }
    }
  },
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8766",
        changeOrigin: true
      }
    }
  }
});
