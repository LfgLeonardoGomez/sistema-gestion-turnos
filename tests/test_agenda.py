import unittest
from datetime import time

from turnos.agenda import Intervalo, inicios_disponibles, puede_reservarse, turno_desde_inicio


class AgendaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.jornada = Intervalo(time(9), time(12))

    def test_duracion_personalizada_define_fin_real(self) -> None:
        self.assertEqual(turno_desde_inicio(time(9, 30), 45).fin, time(10, 15))

    def test_rechaza_turno_que_termina_fuera_de_jornada(self) -> None:
        self.assertFalse(
            puede_reservarse(turno_desde_inicio(time(11, 30), 45), self.jornada, [])
        )

    def test_detecta_solapamiento_parcial_y_permite_turnos_adyacentes(self) -> None:
        ocupado = Intervalo(time(10), time(10, 45))
        self.assertFalse(
            puede_reservarse(Intervalo(time(9, 45), time(10, 15)), self.jornada, [ocupado])
        )
        self.assertTrue(
            puede_reservarse(Intervalo(time(10, 45), time(11, 15)), self.jornada, [ocupado])
        )

    def test_no_ofrece_ultimo_slot_si_no_cabe_completo(self) -> None:
        self.assertEqual(
            inicios_disponibles(self.jornada, 75, []),
            [time(9), time(10, 15)],
        )

    def test_duracion_editada_recalcula_disponibilidad(self) -> None:
        ocupado = [Intervalo(time(10), time(10, 30))]
        self.assertEqual(
            inicios_disponibles(self.jornada, 30, ocupado, paso_minutos=30),
            [time(9), time(9, 30), time(10, 30), time(11), time(11, 30)],
        )
        self.assertEqual(
            inicios_disponibles(self.jornada, 60, ocupado, paso_minutos=30),
            [time(9), time(10, 30), time(11)],
        )

    def test_valida_intervalos_y_duraciones(self) -> None:
        with self.assertRaises(ValueError):
            Intervalo(time(10), time(10))
        with self.assertRaises(ValueError):
            turno_desde_inicio(time(10), 0)
        with self.assertRaises(ValueError):
            turno_desde_inicio(time(23, 30), 45)


if __name__ == "__main__":
    unittest.main()
