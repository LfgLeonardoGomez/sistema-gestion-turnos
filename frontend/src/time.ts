import { Temporal } from '@js-temporal/polyfill'

// Una hora de pared no siempre representa un instante: los cambios de horario
// pueden duplicarla o saltearla. Rechazar ambos casos evita agendar a otra hora.
export function agendaLocalToIso(fecha: string, hora: string, zona: string): string {
  try {
    const plain = Temporal.PlainDateTime.from(`${fecha}T${hora}`)
    return plain.toZonedDateTime(zona, { disambiguation: 'reject' }).toInstant().toString()
  } catch {
    throw new Error('La fecha y hora no existe, es ambigua o la zona horaria del negocio es inválida. Elegí otro horario.')
  }
}

export function dayRangeIso(fecha: string, zona: string): { desde: string; hasta: string } {
  const date = Temporal.PlainDate.from(fecha)
  const start = date.toZonedDateTime(zona).toInstant().toString()
  const end = date.add({ days: 1 }).toZonedDateTime(zona).toInstant().toString()
  return { desde: start, hasta: end }
}

export function businessToday(zona: string): string {
  return Temporal.Now.zonedDateTimeISO(zona).toPlainDate().toString()
}
