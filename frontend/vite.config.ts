import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxies /api/* to the FastAPI backend during local dev, so the frontend
// can call studyScheduleApi (which hits `${VITE_API_BASE_URL ?? "/api"}...`)
// without a CORS setup. Once your backend is running on :8000, requests
// from `npm run dev` (default :5173) just work.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
