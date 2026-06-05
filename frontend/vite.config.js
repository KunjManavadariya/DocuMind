import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const allowedHosts = (process.env.VITE_ALLOWED_HOSTS || "documind-web-kunj.onrender.com")
  .split(",")
  .map((host) => host.trim())
  .filter(Boolean);

export default defineConfig({
  plugins: [react()],
  preview: {
    allowedHosts,
  },
});
