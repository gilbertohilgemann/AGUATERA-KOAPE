import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// host/allowedHosts: aceptar pedidos desde cualquier IP de la red local (probar desde el celular).
// El puerto lo pasa start.ps1 / start.sh con --port (siguiente puerto libre).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { host: true, allowedHosts: true },
  preview: { host: true, allowedHosts: true },
})
