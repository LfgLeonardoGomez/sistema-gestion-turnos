export type Usuario = { id: string; nombre: string; email: string }
export type Negocio = { id: string; nombre: string; rol: 'admin' | 'recepcionista' | 'profesional'; zona_horaria: string }
export type Sesion = { usuario: Usuario; negocios: Negocio[] }
export type Cliente = { id: string; nombre: string; telefono: string | null; email: string | null; documento: string | null; notas: string | null }
export type ClienteCoincidencia = Pick<Cliente, 'id' | 'nombre' | 'telefono' | 'email' | 'documento'>
export type Profesional = { id: string; nombre: string; apellido: string | null; especialidad: string | null; telefono: string | null; whatsapp: string | null; notas: string | null; usuario_id: string | null; duracion_predeterminada_minutos: number; activo: boolean }
export type Horario = { id: string; dia_semana: number; hora_inicio: string; hora_fin: string }
export type Turno = { id: string; profesional_id: string; cliente_id: string; inicio: string; fin: string; estado: string; motivo: string | null }

export class ApiError extends Error { constructor(public status: number, message: string) { super(message) } }

export async function api<T>(path: string, negocioId?: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (negocioId) headers.set('X-Business-Id', negocioId)
  if (init.body) headers.set('Content-Type', 'application/json')
  const response = await fetch(path, { ...init, headers, credentials: 'same-origin', cache: 'no-store' })
  if (!response.ok) {
    let message = `Error ${response.status}`
    try { const data = await response.json(); message = typeof data.detail === 'string' ? data.detail : message } catch { /* sin cuerpo JSON */ }
    throw new ApiError(response.status, message)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}
