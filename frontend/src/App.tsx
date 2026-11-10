import { useEffect, useState, type FormEvent } from 'react'
import { api, type Cliente, type ClienteCoincidencia, type Horario, type Profesional, type Sesion, type Turno } from './api'
import { agendaLocalToIso, businessToday, dayRangeIso } from './time'
import CalendarPanel from './CalendarPanel'
import TeamView from './TeamView'

type Vista = 'agenda' | 'clientes' | 'equipo'
const dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
const fechaLocal = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}` }
const readable = (iso: string, zona: string) => new Intl.DateTimeFormat('es-AR', { dateStyle: 'medium', timeStyle: 'short', timeZone: zona }).format(new Date(iso))
const horaEnZona = (iso: string, zona: string) => new Intl.DateTimeFormat('es-AR',{hour:'2-digit',minute:'2-digit',timeZone:zona}).format(new Date(iso))

export default function App() {
  const [sesion, setSesion] = useState<Sesion | null>(null)
  const [booting, setBooting] = useState(true)
  const [negocioId, setNegocioId] = useState('')
  const [vista, setVista] = useState<Vista>('agenda')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [clientes, setClientes] = useState<Cliente[]>([])
  const [clientesEncontrados, setClientesEncontrados] = useState<Cliente[]>([])
  const [profesionales, setProfesionales] = useState<Profesional[]>([])
  const [turnos, setTurnos] = useState<Turno[]>([])
  const [fecha, setFecha] = useState(fechaLocal)
  const [vistaCalendario, setVistaCalendario] = useState(false)
  const [mesCalendario, setMesCalendario] = useState(fechaLocal().slice(0, 7))
  const [diasConTurnos, setDiasConTurnos] = useState<{fecha:string;cantidad:number}[]>([])
  const [clienteBusqueda, setClienteBusqueda] = useState('')
  const [profesionalFiltro, setProfesionalFiltro] = useState('')
  const [clienteSeleccionado, setClienteSeleccionado] = useState<Cliente | null>(null)
  const [clienteAEditar, setClienteAEditar] = useState<Cliente | null>(null)
  const [profesionalAEditar, setProfesionalAEditar] = useState<Profesional | null>(null)
  const [historial, setHistorial] = useState<Turno[]>([])
  const [horarios, setHorarios] = useState<Record<string, Horario[]>>({})
  const [nuevoCliente, setNuevoCliente] = useState(false)
  const [nuevoTurno, setNuevoTurno] = useState(false)
  const [turnoClienteId, setTurnoClienteId] = useState<string | undefined>(undefined)
  const [turnoAReprogramar, setTurnoAReprogramar] = useState<Turno | null>(null)
  const [aceptando, setAceptando] = useState(false)
  const [gestionPersonal, setGestionPersonal] = useState(false)
  const [refresh, setRefresh] = useState(0)

  useEffect(() => { api<Sesion>('/auth/me').then(s => { setSesion(s); setNegocioId(s.negocios[0]?.id ?? ''); if(s.negocios[0]?.zona_horaria) setFecha(businessToday(s.negocios[0].zona_horaria)) }).catch(() => setSesion(null)).finally(() => setBooting(false)) }, [])
  const negocio = sesion?.negocios.find(n => n.id === negocioId)
  useEffect(() => {
    if (!negocioId || !negocio?.zona_horaria) return
    let active = true
    setError('')
    let range: { desde: string; hasta: string }
    try { range = dayRangeIso(fecha, negocio.zona_horaria) } catch { setError('Fecha o zona horaria del negocio inválida.'); return }
    Promise.all([
      api<Cliente[]>('/clientes?limit=100', negocioId),
      api<Profesional[]>('/profesionales', negocioId),
      api<Turno[]>(`/turnos?desde=${encodeURIComponent(range.desde)}&hasta=${encodeURIComponent(range.hasta)}${profesionalFiltro ? `&profesional_id=${encodeURIComponent(profesionalFiltro)}` : ''}`, negocioId)
    ]).then(([c,p,t]) => { if(active) { setClientes(c); setProfesionales(p); setTurnos(t) } }).catch(e => { if(active) setError(e.message) })
    return () => { active = false }
  }, [negocioId, negocio?.zona_horaria, fecha, profesionalFiltro, refresh])
  useEffect(() => {
    if (!negocioId || vista !== 'clientes') return
    let active = true
    const handle = setTimeout(() => {
      api<Cliente[]>(`/clientes?limit=100${clienteBusqueda.trim() ? `&q=${encodeURIComponent(clienteBusqueda.trim())}` : ''}`, negocioId)
        .then(rows => { if (active) setClientesEncontrados(rows) })
        .catch(e => { if (active) setError(e.message) })
    }, 220)
    return () => { active = false; clearTimeout(handle) }
  }, [negocioId, vista, clienteBusqueda, refresh])
  useEffect(() => {
    if (!negocioId || !vistaCalendario || vista !== 'agenda') return
    let active = true
    api<{fecha:string;cantidad:number}[]>(
      `/turnos/calendario?mes=${mesCalendario}${profesionalFiltro ? `&profesional_id=${encodeURIComponent(profesionalFiltro)}` : ''}`,
      negocioId,
    ).then(days => { if (active) setDiasConTurnos(days) }).catch(e => { if (active) setError(e.message) })
    return () => { active = false }
  }, [negocioId, vistaCalendario, vista, mesCalendario, profesionalFiltro, refresh])
  useEffect(() => { if (!negocioId || !clienteSeleccionado) return; api<Turno[]>(`/turnos/clientes/${clienteSeleccionado.id}/historial`, negocioId).then(setHistorial).catch(e => setError(e.message)) }, [negocioId, clienteSeleccionado, refresh])
  useEffect(() => { if (!negocioId || vista !== 'equipo') return; Promise.all(profesionales.map(async p => [p.id, await api<Horario[]>(`/profesionales/${p.id}/horarios`, negocioId)] as const)).then(rows => setHorarios(Object.fromEntries(rows))).catch(e => setError(e.message)) }, [negocioId, vista, profesionales])

  async function login(e: FormEvent) { e.preventDefault(); setLoading(true); setError(''); try { await api('/auth/login', undefined, { method: 'POST', body: JSON.stringify({ email, password }) }); const s = await api<Sesion>('/auth/me'); setSesion(s); setNegocioId(s.negocios[0]?.id ?? ''); if(s.negocios[0]?.zona_horaria) setFecha(businessToday(s.negocios[0].zona_horaria)); setPassword('') } catch(e) { setError((e as Error).message) } finally { setLoading(false) } }
  async function logout() { try { await api('/auth/logout', undefined, { method: 'POST' }) } finally { setSesion(null); setNegocioId(''); setClientes([]); setTurnos([]); setProfesionales([]) } }
  function changed() { setRefresh(n => n + 1); setNuevoCliente(false); setNuevoTurno(false); setTurnoClienteId(undefined) }
  function abrirNuevoTurno(clienteId?: string) { setTurnoClienteId(clienteId); setNuevoTurno(true) }
  function reprogramado() { setTurnoAReprogramar(null); changed() }
  async function cancelar(t: Turno) { if (!window.confirm('¿Cancelar este turno? Quedará registrado en el historial.')) return; try { await api(`/turnos/${t.id}/cancelar`, negocioId, { method: 'POST' }); changed() } catch(e) { setError((e as Error).message) } }
  if (booting) return <div className="boot">Preparando espacio de trabajo…</div>
  if (!sesion) return aceptando ? <AcceptInvitation onClose={()=>setAceptando(false)} onAccepted={()=>{setAceptando(false);setError('Cuenta creada. Ya podés iniciar sesión.')}} /> : <div className="login-page"><div className="login-copy"><div className="brand-mark">T<span>·</span></div><p className="eyebrow">GESTIÓN DE TURNOS</p><h1>El tiempo bien<br/><em>organizado.</em></h1><p>Un espacio de trabajo para cuidar cada agenda, cada cliente y cada detalle.</p></div><form className="login-card" onSubmit={login}><span className="eyebrow">ACCESO AL ESPACIO</span><h2>Bienvenido de nuevo</h2><p>Ingresá con tu cuenta del negocio.</p><label>Email<input type="email" required autoComplete="username" value={email} onChange={e=>setEmail(e.target.value)} /></label><label>Contraseña<input type="password" required autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} /></label>{error && <div className="notice error" role="alert">{error}</div>}<button className="primary" disabled={loading}>{loading ? 'Ingresando…' : 'Ingresar'}</button><button type="button" className="invitation-link" onClick={()=>setAceptando(true)}>Tengo una invitación para unirme →</button></form></div>
  return <div className="workspace"><aside className="sidebar"><div className="sidebar-brand"><span className="brand-mark small">T<span>·</span></span><div><strong>Turnos</strong><small>ESPACIO DE TRABAJO</small></div></div><div className="business-picker"><span>NEGOCIO ACTIVO</span><select aria-label="Negocio activo" value={negocioId} onChange={e => { setNegocioId(e.target.value); const elegido = sesion.negocios.find(n => n.id === e.target.value); if (elegido?.zona_horaria) setFecha(businessToday(elegido.zona_horaria)); setProfesionalFiltro(''); setClienteSeleccionado(null) }}>{sesion.negocios.map(n => <option key={n.id} value={n.id}>{n.nombre}</option>)}</select></div><nav aria-label="Secciones"><button className={vista==='agenda'?'active':''} onClick={()=>setVista('agenda')}><span>◫</span> Turnos</button><button className={vista==='clientes'?'active':''} onClick={()=>setVista('clientes')}><span>◎</span> Clientes</button><button className={vista==='equipo'?'active':''} onClick={()=>setVista('equipo')}><span>▤</span> {negocio?.rol === 'profesional' ? 'Perfil' : 'Profesionales'}</button>{negocio?.rol !== 'admin' && <button onClick={()=>setAceptando(true)}><span>＋</span> Aceptar invitación</button>}</nav><div className="sidebar-bottom"><div className="avatar">{sesion.usuario.nombre.charAt(0).toUpperCase()}</div><div><strong>{sesion.usuario.nombre}</strong><small>{negocio?.rol ?? 'Sin negocio'}</small></div><button className="logout" onClick={logout} title="Cerrar sesión">Salir</button></div></aside><main className={`main ${vista === 'agenda' && vistaCalendario ? 'main-calendar' : ''}`}>{error && <div className="notice error" role="alert">{error} <button onClick={()=>setError('')}>Cerrar</button></div>}{!negocio ? <section className="empty">Tu cuenta todavía no pertenece a ningún negocio activo. <button className="invitation-link" onClick={()=>setAceptando(true)}>Aceptar invitación</button></section> : vista === 'agenda' ? <><div className="page-heading"><div><h1>Turnos</h1></div><div className="heading-actions"><button className="secondary" onClick={()=>{setMesCalendario(fecha.slice(0,7));setVistaCalendario(v=>!v)}}>{vistaCalendario ? 'Ver día' : 'Vista calendario'}</button><button className="primary" onClick={()=>abrirNuevoTurno()}>+ Nuevo turno</button></div></div>{vistaCalendario ? <CalendarPanel month={mesCalendario} days={diasConTurnos} selected={fecha} onMonth={setMesCalendario} onDay={day=>{setFecha(day);setVistaCalendario(false)}} /> : <><div className="toolbar"><label>Fecha<input type="date" value={fecha} onChange={e=>setFecha(e.target.value)}/></label><label>Agenda<select value={profesionalFiltro} onChange={e=>setProfesionalFiltro(e.target.value)}><option value="">Todas las agendas</option>{profesionales.filter(p=>p.activo).map(p=><option value={p.id} key={p.id}>{[p.nombre,p.apellido].filter(Boolean).join(' ')}{p.especialidad ? ` · ${p.especialidad}` : ''}</option>)}</select></label><span className="count">{turnos.length} turnos</span></div><div className="list-panel"><div className="list-header"><span>HORA</span><span>CLIENTE</span><span>PROFESIONAL</span><span>ESTADO</span><span></span></div>{turnos.length===0?<div className="empty">No hay turnos para este día y filtro.</div>:turnos.map(t=><div className="appointment-row" key={t.id}><div className="time"><strong>{horaEnZona(t.inicio, negocio.zona_horaria)}</strong><small>{horaEnZona(t.fin, negocio.zona_horaria)}</small></div><div><strong>{clientes.find(c=>c.id===t.cliente_id)?.nombre ?? 'Cliente'}</strong><small>{t.motivo || 'Sin motivo indicado'}</small></div><div>{(() => { const p = profesionales.find(p=>p.id===t.profesional_id); return p ? [p.nombre,p.apellido].filter(Boolean).join(' ') : 'Profesional' })()}</div><div><span className={`badge ${t.estado}`}>{t.estado}</span></div><div>{t.estado==='programado'&&<><button className="text-button" onClick={()=>setTurnoAReprogramar(t)}>Reprogramar</button><button className="text-button" onClick={()=>cancelar(t)}>Cancelar</button></>}</div></div>)}</div></>}</> : vista==='clientes' ? <><div className="page-heading"><div><h1>Clientes</h1></div><button className="primary" onClick={()=>setNuevoCliente(true)}>+ Nuevo cliente</button></div><div className="split"><div className="client-list"><div className="section-caption">CLIENTES · {clientesEncontrados.length} visibles</div><label className="client-search">Buscar cliente<input type="search" value={clienteBusqueda} onChange={e=>setClienteBusqueda(e.target.value)} placeholder="Nombre, email, teléfono o documento" /></label>{clientesEncontrados.length===0?<div className="empty">No se encontraron clientes.</div>:clientesEncontrados.map(c=><button key={c.id} className={`client-item ${clienteSeleccionado?.id===c.id?'selected':''}`} onClick={()=>setClienteSeleccionado(c)}><span className="avatar light">{c.nombre.charAt(0).toUpperCase()}</span><span><strong>{c.nombre}</strong><small>{c.email || c.telefono || 'Sin contacto'}</small></span><span className="arrow">→</span></button>)}</div><div className="detail-panel">{clienteSeleccionado?<><span className="eyebrow">FICHA DE CLIENTE</span><div className="detail-heading"><h2>{clienteSeleccionado.nombre}</h2><div className="detail-actions">{negocio?.rol !== 'profesional' && <button className="secondary" onClick={()=>setClienteAEditar(clienteSeleccionado)}>Editar ficha</button>}<button className="primary" onClick={()=>abrirNuevoTurno(clienteSeleccionado.id)}>+ Nuevo turno</button></div></div><div className="detail-grid"><div><span>EMAIL</span><strong>{clienteSeleccionado.email || '—'}</strong></div><div><span>TELÉFONO</span><strong>{clienteSeleccionado.telefono || '—'}</strong></div><div><span>DOCUMENTO</span><strong>{clienteSeleccionado.documento || '—'}</strong></div></div>{negocio?.rol !== 'profesional' && <CompartirCliente key={clienteSeleccionado.id} negocioId={negocioId} clienteId={clienteSeleccionado.id} profesionales={profesionales} onError={setError} />}<h3>Historial de turnos</h3>{historial.length===0?<p className="muted">Todavía no hay turnos visibles.</p>:historial.map(t=><div className="history-row" key={t.id}><span>{readable(t.inicio, negocio.zona_horaria)}</span><span>{(() => { const p = profesionales.find(p=>p.id===t.profesional_id); return p ? [p.nombre,p.apellido].filter(Boolean).join(' ') : 'Profesional' })()}</span><span className={`badge ${t.estado}`}>{t.estado}</span></div>)}</>:<div className="empty">Seleccioná un cliente para ver su ficha e historial.</div>}</div></div></> : <TeamView role={negocio.rol} userId={sesion.usuario.id} professionals={profesionales} schedules={horarios} onEdit={setProfesionalAEditar} onStaff={()=>setGestionPersonal(true)} /> }</main>{clienteAEditar&&<ClienteEditDialog negocioId={negocioId} cliente={clienteAEditar} onClose={()=>setClienteAEditar(null)} onSaved={()=>{setClienteAEditar(null);changed()}} onError={setError}/ >}{profesionalAEditar&&<ProfesionalEditDialog negocioId={negocioId} profesional={profesionalAEditar} horarios={horarios[profesionalAEditar.id]||[]} onClose={()=>setProfesionalAEditar(null)} onSaved={()=>{setProfesionalAEditar(null);changed()}} onError={setError}/ >}{nuevoCliente&&<ClienteDialog negocioId={negocioId} onClose={()=>setNuevoCliente(false)} onSaved={changed} onError={setError}/ >}{nuevoTurno&&<TurnoDialog negocioId={negocioId} clientes={clienteSeleccionado && !clientes.some(c=>c.id===clienteSeleccionado.id) ? [clienteSeleccionado,...clientes] : clientes} profesionales={profesionales.filter(p=>p.activo)} fecha={fecha} zona={negocio?.zona_horaria ?? "UTC"} initialClienteId={turnoClienteId} onClose={()=>{setNuevoTurno(false);setTurnoClienteId(undefined)}} onSaved={changed} onError={setError}/ >}{turnoAReprogramar&&<ReprogramDialog negocioId={negocioId} turno={turnoAReprogramar} profesionales={profesionales.filter(p=>p.activo)} zona={negocio?.zona_horaria ?? "UTC"} onClose={()=>setTurnoAReprogramar(null)} onSaved={reprogramado} onError={setError}/ >}<>{gestionPersonal && negocio?.rol === 'admin' && <div className="overlay" onMouseDown={e=>{if(e.target===e.currentTarget)setGestionPersonal(false)}}><div className="dialog staff-modal"><button type="button" className="close" onClick={()=>setGestionPersonal(false)} aria-label="Cerrar">×</button><StaffPanel key={negocioId} negocioId={negocioId} /></div></div>}{aceptando && <AcceptInvitation existing onClose={()=>setAceptando(false)} onAccepted={async()=>{setAceptando(false);const s=await api<Sesion>('/auth/me');setSesion(s);setNegocioId(s.negocios[0]?.id??'');if(s.negocios[0]?.zona_horaria)setFecha(businessToday(s.negocios[0].zona_horaria))}} />}</></div>
}

function CompartirCliente({ negocioId, clienteId, profesionales, onError }: { negocioId:string; clienteId:string; profesionales:Profesional[]; onError:(s:string)=>void }) {
  const [profesionalId, setProfesionalId] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  async function compartir() {
    if (!profesionalId) return
    setSaving(true)
    setSaved(false)
    try {
      await api(`/clientes/${clienteId}/profesionales/${profesionalId}`, negocioId, {method:'POST'})
      setSaved(true)
    } catch (e) { onError((e as Error).message) }
    finally { setSaving(false) }
  }
  return <div className="client-share"><label>Compartir ficha con profesional<select value={profesionalId} onChange={e=>{setProfesionalId(e.target.value);setSaved(false)}}><option value="">Seleccionar profesional</option>{profesionales.filter(p=>p.activo && p.usuario_id).map(p=><option key={p.id} value={p.id}>{[p.nombre,p.apellido].filter(Boolean).join(' ')}</option>)}</select></label><button type="button" className="secondary" disabled={!profesionalId||saving} onClick={compartir}>{saving?'Compartiendo…':'Compartir ficha'}</button>{saved&&<span role="status">Ficha compartida.</span>}</div>
}

function ClienteDialog({ negocioId, onClose, onSaved, onError }: { negocioId:string; onClose:()=>void; onSaved:()=>void; onError:(s:string)=>void }) {
  const [saving,setSaving]=useState(false)
  const [coincidencias,setCoincidencias]=useState<ClienteCoincidencia[]>([])
  const [pendiente,setPendiente]=useState<{nombre:unknown;telefono:string|null;email:string|null;documento:string|null;notas:string|null}|null>(null)
  async function crear(payload:{nombre:unknown;telefono:string|null;email:string|null;documento:string|null;notas:string|null}){setSaving(true);try{await api('/clientes',negocioId,{method:'POST',body:JSON.stringify(payload)});onSaved()}catch(e){onError((e as Error).message)}finally{setSaving(false)}}
  async function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();setSaving(true);const f=new FormData(e.currentTarget);const payload={nombre:String(f.get('nombre')||''),telefono:String(f.get('telefono')||'')||null,email:String(f.get('email')||'')||null,documento:String(f.get('documento')||'')||null,notas:String(f.get('notas')||'')||null};try{const matches=await api<ClienteCoincidencia[]>('/clientes/coincidencias',negocioId,{method:'POST',body:JSON.stringify(payload)});if(matches.length){setCoincidencias(matches);setPendiente(payload);setSaving(false);return}await crear(payload)}catch(e){onError((e as Error).message);setSaving(false)}}
  async function vincular(id:string){setSaving(true);try{await api(`/clientes/${id}/vincular`,negocioId,{method:'POST'});onSaved()}catch(e){onError((e as Error).message)}finally{setSaving(false)}}
  return <div className="overlay" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}><form className="dialog" onSubmit={submit}><button type="button" className="close" onClick={onClose} aria-label="Cerrar">×</button><span className="eyebrow">DIRECTORIO</span><h2>Nuevo cliente</h2><p>Antes de crear una ficha nueva, si creés que ya existe en otra agenda, pedí a administración o recepción que la comparta. Móvil argentino con código de área. Acepta 261 209 4262, 0261 15 209 4262 o +54 9 261 209 4262.</p><div className="form-grid"><label className="wide">Nombre completo<input name="nombre" required maxLength={200} autoFocus /></label><label>Teléfono<input name="telefono" type="tel" maxLength={50} placeholder="261 209 4262"/></label><label>Email<input name="email" type="email"/></label><label>Documento (opcional)<input name="documento" maxLength={100}/></label><label className="wide">Notas<textarea name="notas" rows={3} maxLength={5000}/></label></div>{coincidencias.length>0&&<div className="notice warning"><strong>Encontramos un cliente posiblemente existente.</strong>{coincidencias.map(c=><div key={c.id} className="match-row"><div><strong>{c.nombre}</strong><small>{c.email||c.telefono||c.documento||'Sin datos de contacto'}</small></div><button type="button" className="secondary" disabled={saving} onClick={()=>vincular(c.id)}>Usar este cliente</button></div>)}<p>Si no corresponde, revisá los datos o confirmá la creación de todos modos.</p><div className="dialog-actions"><button type="button" className="secondary" onClick={()=>{setCoincidencias([]);setPendiente(null)}}>Revisar datos</button><button type="button" className="primary" disabled={saving||!pendiente} onClick={()=>pendiente&&crear(pendiente)}>Crear de todos modos</button></div></div>}<div className="dialog-actions"><button type="button" className="secondary" onClick={onClose}>Cancelar</button>{coincidencias.length===0&&<button className="primary" disabled={saving}>{saving?'Verificando…':'Guardar cliente'}</button>}</div></form></div>
}

function ClienteEditDialog({ negocioId, cliente, onClose, onSaved, onError }: { negocioId:string; cliente:Cliente; onClose:()=>void; onSaved:()=>void; onError:(s:string)=>void }) {
  const [saving,setSaving]=useState(false)
  async function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();setSaving(true);const f=new FormData(e.currentTarget);try{await api(`/clientes/${cliente.id}`,negocioId,{method:'PUT',body:JSON.stringify({nombre:f.get('nombre'),telefono:f.get('telefono')||null,email:f.get('email')||null,documento:f.get('documento')||null,notas:f.get('notas')||null})});onSaved()}catch(e){onError((e as Error).message)}finally{setSaving(false)}}
  return <div className="overlay" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}><form className="dialog" onSubmit={submit}><button type="button" className="close" onClick={onClose} aria-label="Cerrar">×</button><span className="eyebrow">DIRECTORIO</span><h2>Editar cliente</h2><p>Los cambios se aplican al directorio compartido del negocio.</p><div className="form-grid"><label className="wide">Nombre completo<input name="nombre" required maxLength={200} defaultValue={cliente.nombre} autoFocus /></label><label>Teléfono<input name="telefono" type="tel" maxLength={50} placeholder="261 209 4262" defaultValue={cliente.telefono ?? ''}/></label><label>Email<input name="email" type="email" defaultValue={cliente.email ?? ''}/></label><label>Documento (opcional)<input name="documento" maxLength={100} defaultValue={cliente.documento ?? ''}/></label><label className="wide">Notas<textarea name="notas" rows={3} maxLength={5000} defaultValue={cliente.notas ?? ''}/></label></div><div className="dialog-actions"><button type="button" className="secondary" onClick={onClose}>Cancelar</button><button className="primary" disabled={saving}>{saving?'Guardando…':'Guardar cambios'}</button></div></form></div>
}

function ProfesionalEditDialog({ negocioId, profesional, horarios, onClose, onSaved, onError }: { negocioId:string; profesional:Profesional; horarios:Horario[]; onClose:()=>void; onSaved:()=>void; onError:(s:string)=>void }) {
  const [saving,setSaving]=useState(false)
  const [formError,setFormError]=useState('')
  const [tramos,setTramos]=useState<Record<number,{inicio:string;fin:string}[]>>(() => Object.fromEntries(Array.from({length:7},(_,dia)=>[dia, horarios.filter(h=>h.dia_semana===dia).map(h=>({inicio:h.hora_inicio.slice(0,5),fin:h.hora_fin.slice(0,5)}))])))
  const [bulkDia,setBulkDia]=useState(0)
  const [bulkIndex,setBulkIndex]=useState(0)
  const [bulkDias,setBulkDias]=useState<number[]>([])
  function update(dia:number,index:number,key:'inicio'|'fin',value:string){setTramos(prev=>({...prev,[dia]:prev[dia].map((x,i)=>i===index?{...x,[key]:value}:x)}))}
  function add(dia:number){setTramos(prev=>({...prev,[dia]:[...prev[dia],{inicio:'09:00',fin:'13:00'}]}))}
  function remove(dia:number,index:number){setTramos(prev=>({...prev,[dia]:prev[dia].filter((_,i)=>i!==index)}))}
  function toggleBulkDay(day:number){setBulkDias(prev=>prev.includes(day)?prev.filter(d=>d!==day):[...prev,day].sort())}
  function applyBulk(){const source=tramos[bulkDia]?.[bulkIndex];if(!source||bulkDias.length===0)return;setTramos(prev=>{const next={...prev};for(const day of bulkDias){const exists=next[day].some(h=>h.inicio===source.inicio&&h.fin===source.fin);if(!exists)next[day]=[...next[day],{...source}].sort((a,b)=>a.inicio.localeCompare(b.inicio))}return next})}
  async function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();setSaving(true);setFormError('');const f=new FormData(e.currentTarget);const payload=Array.from({length:7},(_,dia)=>tramos[dia].map(h=>({dia_semana:dia,hora_inicio:h.inicio,hora_fin:h.fin}))).flat();try{await api(`/profesionales/${profesional.id}`,negocioId,{method:'PUT',body:JSON.stringify({nombre:f.get('nombre'),apellido:f.get('apellido')||null,especialidad:f.get('especialidad')||null,telefono:f.get('telefono')||null,whatsapp:f.get('telefono_es_whatsapp')?f.get('telefono')||null:null,notas:f.get('notas')||null,usuario_id:profesional.usuario_id,duracion_predeterminada_minutos:Number(f.get('duracion')),activo:profesional.activo})});await api(`/profesionales/${profesional.id}/horarios`,negocioId,{method:'PUT',body:JSON.stringify(payload)});onSaved()}catch(e){setFormError((e as Error).message);onError((e as Error).message)}finally{setSaving(false)}}
  return <div className="overlay" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}><form className="dialog schedule-dialog" onSubmit={submit}><button type="button" className="close" onClick={onClose} aria-label="Cerrar">×</button><span className="eyebrow">CONFIGURACIÓN DE AGENDA</span><h2>{[profesional.nombre,profesional.apellido].filter(Boolean).join(' ')}</h2><p>Definí la duración sugerida y los tramos semanales. Los turnos futuros deben seguir dentro del nuevo horario.</p><label>Nombre de agenda<input name="nombre" required maxLength={200} defaultValue={profesional.nombre}/></label><label>Apellido<input name="apellido" maxLength={200} defaultValue={profesional.apellido ?? ""}/></label><label>Especialidad<input name="especialidad" maxLength={200} defaultValue={profesional.especialidad ?? ""}/></label><label>Teléfono<input name="telefono" type="tel" maxLength={50} placeholder="261 209 4262" defaultValue={profesional.telefono ?? ""}/></label><label className="checkbox"><input name="telefono_es_whatsapp" type="checkbox" defaultChecked={Boolean(profesional.telefono && profesional.whatsapp === profesional.telefono)}/> Este teléfono también es mi WhatsApp</label><label className="wide">Notas<textarea name="notas" rows={2} maxLength={5000} defaultValue={profesional.notas ?? ""}/></label><label>Duración predeterminada (minutos)<input name="duracion" type="number" min={1} max={1439} required defaultValue={profesional.duracion_predeterminada_minutos}/></label><div className="bulk-schedule"><div className="day-title"><strong>Aplicar un tramo a varios días</strong><span className="muted">Los tramos existentes se conservan</span></div><div className="bulk-controls"><label>Día origen<select value={bulkDia} onChange={e=>{setBulkDia(Number(e.target.value));setBulkIndex(0)}}>{dias.map((dia,index)=><option key={dia} value={index}>{dia}</option>)}</select></label><label>Tramo<select value={bulkIndex} onChange={e=>setBulkIndex(Number(e.target.value))}>{(tramos[bulkDia]||[]).length===0?<option value={0}>Sin tramos</option>:(tramos[bulkDia]||[]).map((h,index)=><option key={`${h.inicio}-${h.fin}-${index}`} value={index}>{h.inicio} — {h.fin}</option>)}</select></label></div><div className="bulk-days" aria-label="Días de destino">{dias.map((dia,index)=><label key={dia} className="day-check"><input type="checkbox" checked={bulkDias.includes(index)} onChange={()=>toggleBulkDay(index)}/><span>{dia.slice(0,3)}</span></label>)}</div><button type="button" className="secondary bulk-apply" disabled={!tramos[bulkDia]?.[bulkIndex]||bulkDias.length===0} onClick={applyBulk}>Aplicar a días seleccionados</button></div><div className="weekly-editor">{dias.map((dia,index)=><section key={dia}><div className="day-title"><strong>{dia}</strong><button type="button" className="text-button" onClick={()=>add(index)}>+ tramo</button></div>{tramos[index].length===0&&<span className="muted">Sin atención</span>}{tramos[index].map((h,i)=><div className="time-row" key={`${index}-${i}`}><input aria-label={`${dia} inicio`} type="time" step={60} value={h.inicio} onChange={e=>update(index,i,'inicio',e.target.value)}/><span>—</span><input aria-label={`${dia} fin`} type="time" step={60} value={h.fin} onChange={e=>update(index,i,'fin',e.target.value)}/><button type="button" className="text-button" onClick={()=>remove(index,i)}>Quitar</button></div>)}</section>)}</div>{formError&&<div className="notice error" role="alert">{formError}</div>}<div className="dialog-actions"><button type="button" className="secondary" onClick={onClose}>Cancelar</button><button className="primary" disabled={saving}>{saving?'Guardando…':'Guardar agenda'}</button></div></form></div>
}

type IssuedInvitation = { id:string; email:string; rol:string; expira_en:string; token:string }

function StaffPanel({negocioId}:{negocioId:string}) {
  const [issued,setIssued]=useState<IssuedInvitation|null>(null)
  const [error,setError]=useState('')
  const [busy,setBusy]=useState(false)
  async function issue(e:FormEvent<HTMLFormElement>){e.preventDefault();setBusy(true);setError('');setIssued(null);const f=new FormData(e.currentTarget);try{const result=await api<IssuedInvitation>('/personal/invitaciones',negocioId,{method:'POST',body:JSON.stringify({email:f.get('email'),rol:f.get('rol')})});setIssued(result)}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
  return <><div className="page-heading"><div><span className="eyebrow">ACCESO AL NEGOCIO</span><h1>Personal</h1><p>Invitá a recepción o a profesionales. El acceso empieza con una invitación.</p></div></div><div className="staff-layout"><form className="staff-card" onSubmit={issue}><h2>Nueva invitación</h2><p>Solo la administración puede emitir invitaciones.</p><label>Email de la persona<input name="email" type="email" required autoComplete="off"/></label><label>Rol<select name="rol"><option value="recepcionista">Recepcionista</option><option value="profesional">Profesional</option></select></label><button className="primary" disabled={busy}>{busy?'Generando…':'Generar invitación'}</button>{error&&<div className="notice error" role="alert">{error}</div>}</form><div className="staff-card info"><span className="eyebrow">ENTREGA SEGURA</span><h2>Un acceso, una persona</h2><p>El código se muestra una sola vez. Compartilo manualmente por un canal seguro con la persona invitada. No lo pegues en una URL ni lo envíes a un grupo.</p><p>La persona puede aceptar la invitación desde la pantalla de acceso. Si ya tiene cuenta, debe iniciar sesión primero.</p>{issued&&<div className="issued"><strong>Invitación para {issued.email}</strong><small>Rol: {issued.rol} · Vence: {readable(issued.expira_en, 'UTC')} UTC</small><label>Código de invitación<input value={issued.token} readOnly onFocus={e=>e.currentTarget.select()} /></label><p>Copiá este código ahora. Al cerrar esta vista o generar otra invitación no podrás recuperarlo.</p><button className="secondary" type="button" onClick={()=>setIssued(null)}>Ya lo entregué · ocultar</button></div>}</div></div></>
}

function AcceptInvitation({existing=false,onClose,onAccepted}:{existing?:boolean;onClose:()=>void;onAccepted:()=>void}) {
  const [error,setError]=useState('')
  const [busy,setBusy]=useState(false)
  async function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();setBusy(true);setError('');const f=new FormData(e.currentTarget);try{await api(existing?'/personal/invitaciones/aceptar-existente':'/personal/invitaciones/aceptar',undefined,{method:'POST',body:JSON.stringify(existing?{token:f.get('token')}:{token:f.get('token'),email:f.get('email'),nombre:f.get('nombre'),password:f.get('password')})});onAccepted()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
  return <div className={existing?'overlay':'accept-page'}><form className="dialog accept-card" onSubmit={submit}><button type="button" className="close" aria-label="Cerrar" onClick={onClose}>×</button><span className="eyebrow">UNIRSE AL EQUIPO</span><h2>{existing?'Aceptar con mi cuenta':'Aceptar invitación'}</h2><p>Pegá el código que te compartió el administrador. No uses un enlace que incluya el código en la URL.</p><label>Código de invitación<input name="token" required minLength={40} maxLength={256} autoComplete="off" autoFocus /></label>{!existing&&<><label>Email invitado<input name="email" type="email" required autoComplete="email"/></label><label>Tu nombre<input name="nombre" required maxLength={200} autoComplete="name"/></label><label>Contraseña nueva<input name="password" type="password" required minLength={12} maxLength={1024} autoComplete="new-password"/></label></>}{error&&<div className="notice error" role="alert">{error}</div>}<div className="dialog-actions"><button type="button" className="secondary" onClick={onClose}>Volver</button><button className="primary" disabled={busy}>{busy?'Validando…':'Aceptar invitación'}</button></div></form></div>
}

function TurnoDialog({ negocioId, clientes, profesionales, fecha, zona, initialClienteId, onClose, onSaved, onError }: {negocioId:string;clientes:Cliente[];profesionales:Profesional[];fecha:string;zona:string;initialClienteId?:string;onClose:()=>void;onSaved:()=>void;onError:(s:string)=>void}) {
  const [profesionalId,setProfesionalId]=useState(profesionales[0]?.id??'')
  const [clienteId,setClienteId]=useState(initialClienteId ?? clientes[0]?.id ?? '')
  const [duracion,setDuracion]=useState(profesionales[0]?.duracion_predeterminada_minutos??30)
  const [email,setEmail]=useState(false)
  const [saving,setSaving]=useState(false)
  const [formError,setFormError]=useState('')
  const cliente=clientes.find(c=>c.id===clienteId)
  function chooseProfessional(id:string){setProfesionalId(id);setDuracion(profesionales.find(p=>p.id===id)?.duracion_predeterminada_minutos??30)}
  async function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();setSaving(true);setFormError('');const f=new FormData(e.currentTarget);try{const inicio=agendaLocalToIso(String(f.get('fecha')),String(f.get('hora')),zona);await api('/turnos',negocioId,{method:'POST',body:JSON.stringify({profesional_id:profesionalId,cliente_id:clienteId,inicio,duracion_minutos:duracion,motivo:f.get('motivo')||null,recordatorio_minutos_antes:f.get('anticipo')?Number(f.get('anticipo')):null,recordatorio_email:email})});onSaved()}catch(e){setFormError((e as Error).message);onError((e as Error).message)}finally{setSaving(false)}}
  return <div className="overlay" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}><form className="dialog" onSubmit={submit}><button type="button" className="close" onClick={onClose} aria-label="Cerrar">×</button><span className="eyebrow">AGENDA</span><h2>Nuevo turno</h2><p>La duración sugerida se puede ajustar para esta reserva.</p><div className="form-grid"><label>Cliente<select required value={clienteId} onChange={e=>setClienteId(e.target.value)}>{clientes.map(c=><option key={c.id} value={c.id}>{c.nombre}</option>)}</select></label><label>Profesional<select required value={profesionalId} onChange={e=>chooseProfessional(e.target.value)}>{profesionales.map(p=><option key={p.id} value={p.id}>{[p.nombre,p.apellido].filter(Boolean).join(' ')}{p.especialidad ? ` · ${p.especialidad}` : ''}</option>)}</select></label><label>Fecha<input name="fecha" type="date" required defaultValue={fecha}/></label><label>Hora<input name="hora" type="time" required step={60}/></label><label>Duración (minutos)<input type="number" min={1} max={1439} required value={duracion} onChange={e=>setDuracion(Number(e.target.value))}/></label><label>Anticipación de aviso (minutos)<input name="anticipo" type="number" min={1} max={43200} placeholder="Predeterminado del negocio"/></label><label className="wide">Motivo (opcional)<input name="motivo"/></label><fieldset className="wide"><legend>Preferencia de recordatorio</legend><label className="checkbox"><input type="checkbox" checked={email} disabled={!cliente?.email} onChange={e=>setEmail(e.target.checked)}/> Email {!cliente?.email&&<small>· falta email del cliente</small>}</label><p className="muted">El aviso por email requiere que el cliente tenga una dirección cargada. El envío automático se habilitará cuando esté configurado el servicio de correo.</p></fieldset></div>{formError && <div className="notice error" role="alert">{formError}</div>}<div className="dialog-actions"><button type="button" className="secondary" onClick={onClose}>Cancelar</button><button className="primary" disabled={saving||!clienteId||!profesionalId}>{saving?'Guardando…':'Crear turno'}</button></div></form></div>
}

function ReprogramDialog({ negocioId, turno, profesionales, zona, onClose, onSaved, onError }: { negocioId:string; turno:Turno; profesionales:Profesional[]; zona:string; onClose:()=>void; onSaved:()=>void; onError:(s:string)=>void }) {
  const [profesionalId, setProfesionalId] = useState(turno.profesional_id)
  const [duracion, setDuracion] = useState(Math.max(1, Math.round((new Date(turno.fin).getTime() - new Date(turno.inicio).getTime()) / 60000)))
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState('')
  const local = new Intl.DateTimeFormat('en-CA', { timeZone: zona, year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', hourCycle:'h23' }).formatToParts(new Date(turno.inicio))
  const part = (type:string) => local.find(p => p.type === type)?.value ?? ''
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setSaving(true); setFormError('')
    const f = new FormData(e.currentTarget)
    try {
      const inicio = agendaLocalToIso(String(f.get('fecha')), String(f.get('hora')), zona)
      await api(`/turnos/${turno.id}/reprogramar`, negocioId, { method:'POST', body: JSON.stringify({ profesional_id: profesionalId, inicio, duracion_minutos: duracion }) })
      onSaved()
    } catch (e) { setFormError((e as Error).message); onError((e as Error).message) } finally { setSaving(false) }
  }
  return <div className="overlay" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}><form className="dialog" onSubmit={submit}><button type="button" className="close" onClick={onClose} aria-label="Cerrar">×</button><span className="eyebrow">AGENDA</span><h2>Reprogramar turno</h2><p>El turno original queda en el historial y se crea una nueva reserva.</p><div className="form-grid"><label>Profesional<select required value={profesionalId} onChange={e=>{setProfesionalId(e.target.value); const p=profesionales.find(x=>x.id===e.target.value); if(p && profesionalId!==e.target.value) setDuracion(p.duracion_predeterminada_minutos)}}>{profesionales.map(p=><option key={p.id} value={p.id}>{[p.nombre,p.apellido].filter(Boolean).join(' ')}{p.especialidad ? ` · ${p.especialidad}` : ''}</option>)}</select></label><label>Fecha<input name="fecha" type="date" required defaultValue={`${part('year')}-${part('month')}-${part('day')}`}/></label><label>Hora<input name="hora" type="time" required step={60} defaultValue={`${part('hour')}:${part('minute')}`}/></label><label>Duración (minutos)<input type="number" min={1} max={1439} required value={duracion} onChange={e=>setDuracion(Number(e.target.value))}/></label></div>{formError&&<div className="notice error" role="alert">{formError}</div>}<div className="dialog-actions"><button type="button" className="secondary" onClick={onClose}>Cancelar</button><button className="primary" disabled={saving}>{saving?'Guardando…':'Confirmar reprogramación'}</button></div></form></div>
}
















