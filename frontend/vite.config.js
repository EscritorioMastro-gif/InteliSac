import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Em desenvolvimento o Vite repassa /api e /socket.io para o backend (porta 8010).
// Portas escolhidas para não colidir com o sistema-extrato-dominio (5173/8000).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5180,
    strictPort: true,
    proxy: {
      "/api": "http://127.0.0.1:8010",
      "/socket.io": { target: "http://127.0.0.1:8010", ws: true },
    },
  },
});
