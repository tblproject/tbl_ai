import random
import unittest
from datetime import date

from config import BillingEntity, DateRange, GeneratorConfig
from faker import Faker
from generators import generate_billings, generate_payments, generate_transfers


def _build(seed: int, fn):
    random.seed(seed)
    fake = Faker("es_ES")
    Faker.seed(seed)
    cfg = GeneratorConfig(billing_entities=[
        BillingEntity("Adeudo test", 50.0, 10.0, "0001234567890000")
    ])
    dr = DateRange(date(2026, 1, 1), date(2026, 3, 31))
    return [(m.fecha, m.concepto, m.movimiento, m.importe) for m in fn(fake, dr, cfg)]


class ReproducibilityTests(unittest.TestCase):
    def test_billings_misma_seed_mismo_resultado(self):
        self.assertEqual(_build(42, generate_billings), _build(42, generate_billings))

    def test_seeds_distintas_resultados_distintos(self):
        a = _build(1, generate_billings)
        b = _build(2, generate_billings)
        self.assertNotEqual(a, b)

    def test_payments_reproducible(self):
        self.assertEqual(_build(9, generate_payments), _build(9, generate_payments))

    def test_transfers_reproducible(self):
        self.assertEqual(_build(9, generate_transfers), _build(9, generate_transfers))


if __name__ == "__main__":
    unittest.main()
