import random
import unittest
from datetime import date

from config import DateRange, GeneratorConfig, Movement
from faker import Faker
from main import _adjust_to_rows


class RowsTests(unittest.TestCase):
    def test_rellena_hasta_filas_exactas(self):
        random.seed(1)
        dr = DateRange(date(2026, 1, 1), date(2026, 2, 28))
        cfg = GeneratorConfig()
        movs = [Movement("01/01/2026", "x", "y", 1.0)]
        out = _adjust_to_rows(movs, 10, Faker("es_ES"), dr, cfg)
        self.assertEqual(len(out), 10)

    def test_recorta_hasta_filas_exactas(self):
        dr = DateRange(date(2026, 1, 1), date(2026, 2, 28))
        cfg = GeneratorConfig()
        movs = [Movement(f"{i:02d}/03/2026", "Cobro proyecto web", "m", float(i + 1))
                for i in range(6)]
        out = _adjust_to_rows(movs, 3, Faker("es_ES"), dr, cfg)
        self.assertEqual(len(out), 3)

    def test_recorte_no_pasa_de_minimo(self):
        movs = [Movement("05/01/2026", "Adeudo telefonía", "m", -50.0)]
        out = _adjust_to_rows(
            movs, 0, Faker("es_ES"),
            DateRange(date(2026, 1, 1), date(2026, 1, 31)),
            GeneratorConfig(),
        )
        self.assertEqual(len(out), 1)


if __name__ == "__main__":
    unittest.main()
