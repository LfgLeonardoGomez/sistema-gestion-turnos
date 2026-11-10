type DayCount = { fecha: string; cantidad: number }

const weekdays = ['L', 'M', 'M', 'J', 'V', 'S', 'D']

function moveMonth(month: string, delta: number): string {
  const [year, value] = month.split('-').map(Number)
  const date = new Date(Date.UTC(year, value - 1 + delta, 1))
  return date.toISOString().slice(0, 7)
}

export default function CalendarPanel({
  month, days, selected, onMonth, onDay,
}: {
  month: string
  days: DayCount[]
  selected: string
  onMonth: (month: string) => void
  onDay: (day: string) => void
}) {
  const [year, value] = month.split('-').map(Number)
  const firstWeekday = (new Date(Date.UTC(year, value - 1, 1)).getUTCDay() + 6) % 7
  const daysInMonth = new Date(Date.UTC(year, value, 0)).getUTCDate()
  const trailing = 42 - firstWeekday - daysInMonth
  const counts = new Map(days.map(day => [day.fecha, day.cantidad]))
  const title = new Intl.DateTimeFormat('es-AR', { month: 'long', year: 'numeric', timeZone: 'UTC' })
    .format(new Date(Date.UTC(year, value - 1, 1)))
  return <section className="calendar-panel" aria-label="Calendario de turnos">
    <div className="calendar-heading">
      <div><h2>{title}</h2></div>
      <div className="calendar-arrows">
        <button type="button" className="secondary" onClick={() => onMonth(moveMonth(month, -1))} aria-label="Mes anterior">←</button>
        <button type="button" className="secondary" onClick={() => onMonth(moveMonth(month, 1))} aria-label="Mes siguiente">→</button>
      </div>
    </div>
    <div className="calendar-grid">
      {weekdays.map((day, index) => <div className="calendar-weekday" key={index}>{day}</div>)}
      {Array.from({ length: firstWeekday }, (_, index) => <div className="calendar-spacer" key={`empty-${index}`} />)}
      {Array.from({ length: daysInMonth }, (_, index) => {
        const date = `${month}-${String(index + 1).padStart(2, '0')}`
        const count = counts.get(date) ?? 0
        return <button type="button" key={date}
          className={`calendar-day ${count ? 'has-turnos' : ''} ${date === selected ? 'selected' : ''}`}
          onClick={() => onDay(date)} aria-label={`${date}: ${count} turnos programados`}>
          <strong>{index + 1}</strong>{count > 0 && <span>{count} {count === 1 ? 'turno' : 'turnos'}</span>}
        </button>
      })}
      {Array.from({ length: trailing }, (_, index) => <div className="calendar-spacer" key={`trailing-${index}`} />)}
    </div>
  </section>
}
