"""Intervalos y disponibilidad de una agenda profesional.

Adapta la regla de solapamiento de `availability_service.py` del proyecto
anterior, sin depender de su modelo odontológico ni de sus integraciones.
"""

from dataclasses import dataclass
from datetime import time


def _minutos(valor: time) -> int:
    if valor.second or valor.microsecond:
        raise ValueError("La agenda usa precisión de minutos")
    return valor.hour * 60 + valor.minute


def _hora(minutos: int) -> time:
    return time(hour=minutos // 60, minute=minutos % 60)


@dataclass(frozen=True)
class Intervalo:
    inicio: time
    fin: time

    def __post_init__(self) -> None:
        if _minutos(self.inicio) >= _minutos(self.fin):
            raise ValueError("El fin debe ser posterior al inicio")

    def se_solapa_con(self, otro: "Intervalo") -> bool:
        return self.inicio < otro.fin and otro.inicio < self.fin

    def contiene(self, otro: "Intervalo") -> bool:
        return self.inicio <= otro.inicio and otro.fin <= self.fin


def turno_desde_inicio(inicio: time, duracion_minutos: int) -> Intervalo:
    if duracion_minutos <= 0:
        raise ValueError("La duración debe ser positiva")
    fin = _minutos(inicio) + duracion_minutos
    if fin >= 24 * 60:
        raise ValueError("El turno debe terminar antes de medianoche")
    return Intervalo(inicio, _hora(fin))


def puede_reservarse(
    turno: Intervalo,
    jornada: Intervalo,
    ocupados: list[Intervalo],
) -> bool:
    return jornada.contiene(turno) and not any(
        turno.se_solapa_con(ocupado) for ocupado in ocupados
    )


def inicios_disponibles(
    jornada: Intervalo,
    duracion_minutos: int,
    ocupados: list[Intervalo],
    *,
    paso_minutos: int | None = None,
) -> list[time]:
    """Propone inicios sin exceder jornada ni cruzar intervalos ocupados.

    `paso_minutos` es la separación entre candidatos; si se omite, usa la
    duración solicitada. No representa la duración predeterminada de la agenda.
    """
    if duracion_minutos <= 0:
        raise ValueError("La duración debe ser positiva")
    paso = duracion_minutos if paso_minutos is None else paso_minutos
    if paso <= 0:
        raise ValueError("El paso debe ser positivo")

    resultado: list[time] = []
    inicio = _minutos(jornada.inicio)
    ultimo_inicio = _minutos(jornada.fin) - duracion_minutos
    while inicio <= ultimo_inicio:
        candidato = turno_desde_inicio(_hora(inicio), duracion_minutos)
        if puede_reservarse(candidato, jornada, ocupados):
            resultado.append(candidato.inicio)
        inicio += paso
    return resultado
