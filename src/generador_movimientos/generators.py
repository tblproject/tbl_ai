import calendar
import random
from datetime import date, timedelta
from typing import List

from config import NOISE_COMMERCE, DateRange, GeneratorConfig, Movement
from faker import Faker


MAX_BILLING_DAY = 25


def _months(start: date, end: date):
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield year, month
        month += 1
        if month > 12:
            year += 1
            month = 1


def _next_business_day(d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _prev_business_day(d: date) -> date:
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _fmt(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _mmovement(d: date, concepto: str, movimiento: str,
               importe: float) -> Movement:
    return Movement(_fmt(d), concepto, movimiento, round(importe, 2))


def _reference(year: int) -> str:
    return f"{year}{random.randint(0, 999999999999):012d}"


def generate_payments(fake: Faker, date_range: DateRange,
                      config: GeneratorConfig) -> List[Movement]:
    out = []
    for year, month in _months(date_range.start, date_range.end):
        day = calendar.monthrange(year, month)[1]
        d = date(year, month, day)
        d = _prev_business_day(d)
        if d < date_range.start or d > date_range.end:
            continue
        amount = random.uniform(2500, 400000)
        out.append(_mmovement(d, "Pago a proveedor",
                              fake.company().upper(), amount))
    return out


def generate_transfers(fake: Faker, date_range: DateRange,
                       config: GeneratorConfig) -> List[Movement]:
    out = []
    for year, month in _months(date_range.start, date_range.end):
        last_day = calendar.monthrange(year, month)[1]
        for _ in range(random.randint(2, 5)):
            d = date(year, month, random.randint(1, last_day))
            if d < date_range.start or d > date_range.end:
                continue
            kind = random.random()
            if kind < 0.08:
                text = f"Pago {fake.word()} {fake.word()}"
            elif kind < 0.67:
                text = f"Pago servicio {fake.random_element(config.transfer_services)}"
            elif kind < 0.87:
                text = f"Plan {random.randint(0, 999999999999):012d}"
            else:
                text = f"Pago fact. {random.randint(2020, date_range.end.year)}-{random.randint(1000, 9999)}"
            amount = -random.uniform(50, 1000)
            out.append(_mmovement(d, "Transferencia realizada", text,
                                  amount))
    return out


def generate_billings(fake: Faker, date_range: DateRange,
                      config: GeneratorConfig) -> List[Movement]:
    out = []
    for entity in config.billing_entities:
        base_day = random.randint(10, MAX_BILLING_DAY)
        for year, month in _months(date_range.start, date_range.end):
            day = max(1, min(28, base_day + random.randint(-2, 2)))
            d = _next_business_day(date(year, month, day))
            if d < date_range.start or d > date_range.end:
                continue
            out.append(_mmovement(d, entity.concepto,
                                  f"Adeudo nº{entity.reference}",
                                  -entity.random_amount()))
    return out


def generate_cobros(fake: Faker, date_range: DateRange,
                    config: GeneratorConfig,
                    monthly: int = None,
                    include_nomina: bool = True) -> List[Movement]:
    out = []
    for year, month in _months(date_range.start, date_range.end):
        last_day = calendar.monthrange(year, month)[1]

        if include_nomina:
            d = _next_business_day(date(year, month, 1))
            if date_range.start <= d <= date_range.end:
                out.append(_mmovement(d, "Nomina", "Transferencia nomina empresa",
                                      random.uniform(1800, 4500)))

        count = monthly if monthly is not None else random.randint(5, 40)
        for _ in range(count):
            d = date(year, month, random.randint(1, last_day))
            if d < date_range.start or d > date_range.end:
                continue
            if random.random() < 0.08:
                concepto = f"Cobro {fake.word()} {fake.word()}"
            else:
                concepto = fake.random_element(config.cobro_concepts)
            out.append(_mmovement(d, concepto,
                                  f"factura nº{_reference(year)}",
                                  random.uniform(1500, 700000)))
    return out


def generate_noise(fake: Faker, date_range: DateRange,
                   count: int) -> List[Movement]:
    out = []
    total_days = (date_range.end - date_range.start).days
    for _ in range(count):
        d = date_range.start + timedelta(days=random.randint(0, max(0, total_days)))
        kind = random.random()
        if kind < 0.35:
            comercio = fake.random_element(NOISE_COMMERCE)
            out.append(_mmovement(d, "Tarjeta crédito",
                                  f"{comercio} {fake.company().upper()}",
                                  -random.uniform(5, 300)))
        elif kind < 0.55:
            out.append(_mmovement(d, "Tarjeta crédito", "Devolución compra",
                                  random.uniform(5, 300)))
        elif kind < 0.75:
            out.append(_mmovement(d, "Transferencia recibida", fake.name(),
                                  random.uniform(50, 2000)))
        elif kind < 0.9:
            suscripcion = fake.word()
            out.append(_mmovement(d, f"Suscripción {suscripcion}",
                                  f"Renovación {suscripcion}",
                                  -random.uniform(4.99, 29.99)))
        else:
            out.append(_mmovement(d, "Tarjeta crédito",
                                  f"Compra {fake.word()} {fake.word()}",
                                  -random.uniform(3, 250)))
    return out
