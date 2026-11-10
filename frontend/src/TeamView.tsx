import { useState } from 'react'
import type { Horario, Profesional } from './api'

const weekdays = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
const fullName = (p: Profesional) => [p.nombre, p.apellido].filter(Boolean).join(' ')

export default function TeamView({
  role, userId, professionals, schedules, onEdit, onStaff,
}: {
  role: 'admin' | 'recepcionista' | 'profesional'
  userId: string
  professionals: Profesional[]
  schedules: Record<string, Horario[]>
  onEdit: (professional: Profesional) => void
  onStaff: () => void
}) {
  const [showSchedule, setShowSchedule] = useState<Profesional | null>(null)
  const visible = role === 'profesional'
    ? professionals.filter(p => p.usuario_id === userId)
    : professionals
  const schedule = showSchedule ? schedules[showSchedule.id] ?? [] : []
  return <>
    <div className="page-heading team-heading">
      <h1>{role === 'profesional' ? 'Mi perfil' : 'Profesionales'}</h1>
      {role === 'admin' && <button className="secondary" onClick={onStaff}>Gestionar personal</button>}
    </div>
    <div className="professional-grid">
      {visible.map(p => <article className="professional-card compact" key={p.id}>
        <div className="professional-identity">
          <span className="avatar">{p.nombre.charAt(0).toUpperCase()}</span>
          <div><h2>{fullName(p)}</h2>{p.especialidad && <span className="professional-specialty">{p.especialidad}</span>}</div>
        </div>
        <div className="professional-meta">
          <span className={p.activo ? 'status-active' : 'status-inactive'}>{p.activo ? 'Activa' : 'Inactiva'}</span>
          <span>Turno habitual: {p.duracion_predeterminada_minutos} min</span>
        </div>
        <div className="professional-actions">
          <button className="secondary" onClick={() => setShowSchedule(p)}>Ver horarios</button>
          {(role === 'admin' || (role === 'profesional' && p.usuario_id === userId)) &&
            <button className="primary" onClick={() => onEdit(p)}>{role === 'profesional' ? 'Editar perfil y agenda' : 'Configurar agenda'}</button>}
        </div>
      </article>)}
      {visible.length === 0 && <div className="empty">No hay profesionales visibles.</div>}
    </div>
    {showSchedule && <div className="overlay" onMouseDown={e => { if (e.target === e.currentTarget) setShowSchedule(null) }}>
      <div className="dialog schedule-view" role="dialog" aria-modal="true" aria-label={`Horarios de ${fullName(showSchedule)}`}>
        <button type="button" className="close" onClick={() => setShowSchedule(null)} aria-label="Cerrar">×</button>
        <span className="eyebrow">HORARIOS</span>
        <h2>{fullName(showSchedule)}</h2>
        {schedule.length === 0
          ? <p className="muted">Todavía no tiene horarios configurados.</p>
          : <div className="schedule-view-days">{weekdays.map((day, index) => {
            const spans = schedule.filter(h => h.dia_semana === index).sort((a, b) => a.hora_inicio.localeCompare(b.hora_inicio))
            return spans.length > 0 && <div className="schedule-view-day" key={day}>
              <strong>{day}</strong><div>{spans.map(h => <span key={h.id}>{h.hora_inicio.slice(0, 5)}–{h.hora_fin.slice(0, 5)}</span>)}</div>
            </div>
          })}</div>}
      </div>
    </div>}
  </>
}
