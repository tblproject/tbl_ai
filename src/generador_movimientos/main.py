import argparse
import calendar
import random
from datetime import date, timedelta
from typing import List

from config import ConfigError, DateRange, GeneratorConfig, Movement
from faker import Faker
from generators import (
    generate_billings,
    generate_cobros,
    generate_noise,
    generate_payments,
    generate_transfers,
)
from writer import write_movements


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ConfigError(f"Fecha inválida '{value}', formato esperado YYYY-MM-DD") from exc


def _count_months(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month) + 1


def _adjust_to_rows(movements: List[Movement], rows: int, fake: Faker,
                    date_range: DateRange, config: GeneratorConfig) -> List[Movement]:
    while len(movements) < rows:
        before = len(movements)
        movements.extend(generate_cobros(fake, date_range, config,
                                         monthly=1, include_nomina=False))
        if len(movements) == before:
            raise ConfigError("No se pueden generar más cobros dentro del rango dado")
    removable = {"Tarjeta crédito", "Transferencia recibida"}
    while len(movements) > rows:
        for i in range(len(movements) - 1, -1, -1):
            concepto = movements[i].concepto
            if concepto.startswith("Cobro") or concepto.startswith("Suscripción") \
                    or concepto in removable:
                movements.pop(i)
                break
        else:
            break  # recurrencia mínima alcanzada; no se recorta más
    return movements


def main():
    parser = argparse.ArgumentParser(
        description="Generador de movimientos bancarios sintéticos"
    )
    parser.add_argument("--start-date", default=None,
                        help="Fecha inicio YYYY-MM-DD (por defecto, hace 12 meses)")
    parser.add_argument("--end-date", default=None,
                        help="Fecha fin YYYY-MM-DD (por defecto, hoy)")
    parser.add_argument("--rows", type=int, default=None,
                        help="Nº aproximado de movimientos (ajusta la cadencia de cobros)")
    parser.add_argument("--seed", type=int, default=None,
                        help="Semilla de aleatoriedad (por defecto, aleatoria)")
    parser.add_argument("--output", default="../../data/generador_movimientos/movimientos.csv",
                        help="Ruta del CSV de salida")
    args = parser.parse_args()

    try:
        today = date.today()
        start = parse_date(args.start_date) if args.start_date else today - timedelta(days=365)
        end = parse_date(args.end_date) if args.end_date else today
    except ConfigError as exc:
        parser.error(str(exc))
        return

    if start > end:
        parser.error("--start-date debe ser anterior o igual a --end-date")
    if end > today:
        parser.error("No se permiten fechas futuras (coherencia temporal)")

    seed = args.seed if args.seed is not None else random.randint(0, 2**31 - 1)
    random.seed(seed)
    Faker.seed(seed)
    fake = Faker("es_ES")

    config = GeneratorConfig().assign_references()
    date_range = DateRange(start, end)

    base: List[Movement] = []
    base.extend(generate_payments(fake, date_range, config))
    base.extend(generate_transfers(fake, date_range, config))
    base.extend(generate_billings(fake, date_range, config))

    months = _count_months(start, end)
    monthly_cobros = None
    noise_count = None
    if args.rows is not None:
        noise_count = max(10, round(args.rows * 0.05))
        rest = args.rows - noise_count - months - len(base)
        monthly_cobros = max(0, rest // max(1, months))

    movements = list(base)
    movements.extend(generate_cobros(fake, date_range, config, monthly=monthly_cobros))

    if noise_count is None:
        noise_count = max(10, round(len(movements) * 0.05))
    movements.extend(generate_noise(fake, date_range, noise_count))

    if args.rows is not None:
        movements = _adjust_to_rows(movements, args.rows, fake, date_range, config)

    write_movements(movements, args.output)
    print(f"Generados {len(movements)} movimientos en {args.output} (seed: {seed})")


if __name__ == "__main__":
    main()
