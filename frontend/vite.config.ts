import { defineConfig } from 'vite'

// Vite mantiene las solicitudes y la cookie en un único origen durante desarrollo.
// APP_ORIGIN debe coincidir con http://localhost:5173 (o el host elegido).
const apiTarget = process.env.VITE_API_TARGET ?? 'http://localhost:8000'
export default defineConfig({ server: { watch: { usePolling: true, interval: 300 }, proxy: { '/auth': apiTarget, '/clientes': apiTarget, '/profesionales': apiTarget, '/turnos': apiTarget, '/personal': apiTarget } } })
