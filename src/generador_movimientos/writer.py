import csv
import os
from typing import List

from config import Movement


def format_amount(value: float) -> str:
    rounded = round(round(value, 2), 2)
    if abs(rounded - round(rounded)) < 1e-9:
        return str(int(round(rounded)))
    return f"{rounded:.2f}".replace(".", ",")


def sort_movements(movements: List[Movement]) -> List[Movement]:
    return sorted(movements,
                  key=lambda m: (m.fecha[6:10], m.fecha[3:5], m.fecha[0:2]),
                  reverse=True)


def write_movements(movements: List[Movement], output_path: str):
    directory = os.path.dirname(output_path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    ordered = sort_movements(movements)

    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Fecha", "Concepto", "Movimiento", "Importe"])
        for m in ordered:
            writer.writerow([m.fecha, m.concepto, m.movimiento, format_amount(m.importe)])
