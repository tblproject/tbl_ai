import random
import unittest
from datetime import date, datetime

from config import BillingEntity, DateRange, GeneratorConfig
from faker import Faker
from generators import generate_billings, generate_cobros


def _as_date(fecha: str) -> date:
    return datetime.strptime(fecha, "%d/%m/%Y").date()


class RecurrenceTests(unittest.TestCase):
    def test_adeudo_uno_por_mes(self):
        random.seed(7)
        cfg = GeneratorConfig(billing_entities=[
            BillingEntity("Adeudo telefonía", 60.0, 10.0, "0001234567890000")
        ])
        dr = DateRange(date(2026, 1, 1), date(2026, 12, 31))
        movs = generate_billings(Faker("es_ES"), dr, cfg)

        self.assertEqual(len(movs), 12)
        meses = {_as_date(m.fecha).month for m in movs}
        self.assertEqual(len(meses), 12)

    def test_adeudos_dias_laborables_y_dentro_de_rango(self):
        random.seed(3)
        cfg = GeneratorConfig(billing_entities=[
            BillingEntity("Adeudo luz", 68.2, 10.0, "0001234567890001")
        ])
        dr = DateRange(date(2026, 1, 1), date(2026, 6, 30))
        movs = generate_billings(Faker("es_ES"), dr, cfg)

        for m in movs:
            d = _as_date(m.fecha)
            self.assertGreaterEqual(d, dr.start)
            self.assertLessEqual(d, dr.end)
            self.assertLess(d.weekday(), 5)

    def test_nomina_cada_mes(self):
        random.seed(11)
        cfg = GeneratorConfig()
        dr = DateRange(date(2026, 1, 1), date(2026, 6, 30))
        movs = generate_cobros(Faker("es_ES"), dr, cfg, monthly=5)

        nominas = [m for m in movs if m.concepto == "Nomina"]
        self.assertEqual(len(nominas), 6)


if __name__ == "__main__":
    unittest.main()
