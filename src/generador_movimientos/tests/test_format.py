import unittest

from config import Movement
from writer import format_amount, sort_movements


class FormatAmountTests(unittest.TestCase):
    def test_coma_decimal(self):
        self.assertEqual(format_amount(1234.5), "1234,50")

    def test_negativo_con_decimales(self):
        self.assertEqual(format_amount(-43.57), "-43,57")

    def test_entero_sin_decimales(self):
        self.assertEqual(format_amount(-230.0), "-230")


class SortTests(unittest.TestCase):
    def test_orden_fecha_descendente(self):
        movs = [
            Movement("01/03/2026", "a", "b", 10.0),
            Movement("10/02/2026", "a", "b", 10.0),
            Movement("15/03/2026", "a", "b", 10.0),
        ]
        fechas = [m.fecha for m in sort_movements(movs)]
        self.assertEqual(fechas, ["15/03/2026", "01/03/2026", "10/02/2026"])


if __name__ == "__main__":
    unittest.main()
