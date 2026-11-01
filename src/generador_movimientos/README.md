# Generador de Movimientos Bancarios Sintéticos

## Descripción

Script en Python que genera un CSV con movimientos de cuenta bancaria sintéticos pero realistas, simulando una exportación de banco español con las columnas `Fecha`, `Concepto`, `Movimiento` e `Importe`.

Ideal para probar pipelines de categorización o análisis sin usar datos reales.

## Requisitos

- Python 3.11+
- **Dependencias:**
  - `faker`

## Instalación

### Crear entorno virtual

```bash
python3 -m venv .venv
source .venv/bin/activate  # En Windows: .venv\Scripts\activate
```

### Instalar dependencias

```bash
pip install -r requirements.txt
```

## Uso

```bash
python src/generador_movimientos/main.py --help
```

### Parámetros de la CLI

| Parámetro | Por defecto | Descripción |
|-----------|-------------|-------------|
| `--start-date` | hace 12 meses | Fecha inicio (YYYY-MM-DD) |
| `--end-date` | hoy | Fecha fin (YYYY-MM-DD) |
| `--rows` | derivado de cadencias | Nº exacto de movimientos del CSV (si es ≥ a la recurrencia mínima mensual) |
| `--seed` | aleatoria | Semilla para reproducibilidad |
| `--output` | `data/generador_movimientos/movimientos.csv` | Archivo de salida CSV |

### Ejemplo completo

```bash
python src/generador_movimientos/main.py \
    --start-date 2026-10-01 \
    --end-date 2026-10-31 \
    --seed 42
```

### Ejecutar tests

```bash
cd src/generador_movimientos
python -m unittest discover -s tests -t . -v
```

## Estructura del Proyecto

```
src/generador_movimientos/
├── main.py            # CLI y orquestación
├── config.py          # Modelos de configuración y entidades de adeudo
├── generators.py      # Funciones generate_<tipo>(fake, date_range, config)
├── writer.py          # Escritura del CSV (orden, formato, decimales)
├── requirements.txt   # Dependencias del proyecto
└── README.md
```

## Tipos de Movimiento Simulados

| Concepto | Movimiento | Importe | Frecuencia |
|----------|------------|---------|------------|
| `Pago a proveedor` | Empresa Faker (mayúsculas) | +2.500–400.000 € | 1/mes, fin de mes |
| `Transferencia realizada` | `Pago servicio X` (16 servicios), `Plan`+12 dígitos, `Pago fact. AAAA-NNNN` | -50 a -1.000 € | 2-5/mes |
| `Adeudo <entidad>` | `Adeudo nº`+16 dígitos | -15 a -100 € | 1/mes por entidad (12 entidades) |
| `Adeudo alquiler local` | `Adeudo nº`+16 dígitos | -3.000 € fijo | 1/mes |
| `Nomina` / `Cobro <proyecto>` | `factura nº`+16 dígitos | +1.500 a +700.000 € | nómina 1/mes + 5-40/mes (16 conceptos) |
| Ruido | Comercios, devoluciones, transferencias aisladas, suscripciones | pequeño | ~5% del total |

## Variabilidad

- Los catálogos (`TRANSFER_SERVICES`, `COBRO_CONCEPTS`, `NOISE_COMMERCE`) son configurables en `config.py`.
- Además del catálogo, ~8% de las transferencias y los cobros y ~10% del ruido usan **conceptos inventados** generados al vuelo con palabras aleatorias de Faker, siempre reproducibles con la misma semilla.

## Catálogo de Entidades de Adeudo

Telefonía, luz, agua, gas, internet, alquiler local, seguro, gestoría, limpieza, vigilancia, suministros y software. Configurable en `config.py` (`GeneratorConfig.billing_entities`).

## Reglas de Realismo Aplicadas

1. **Recurrencia:** los adeudos se repiten cada mes con ±2 días de variación; fines de semana desplazados al laborable siguiente.
2. **Importes fijos vs variables:** alquiler, seguro y gestoría son fijos; telefonía, luz y suministros varían ±10%.
3. **Referencias:** `Adeudo nº` + año + 12 dígitos aleatorios (16 dígitos en total), estable por entidad.
4. **Coherencia temporal:** sin fechas futuras ni fuera del rango; cada tipo respeta su cadencia mensual.
5. **Ruido:** ~5% de movimientos puntuales no recurrentes (tiendas, devoluciones, transferencias aisladas).
6. **Datos sintéticos:** todo nombre, empresa o referencia sale de Faker `locale="es_ES"`.

## Formato de Salida CSV

| Columna | Formato | Ejemplo |
|---------|---------|---------|
| `Fecha` | `dd/mm/yyyy` | `15/10/2026` |
| `Concepto` | Texto libre | `Adeudo telefonía` |
| `Movimiento` | Descripción corta | `Adeudo nº2026607241985706` |
| `Importe` | Coma decimal, enteros sin decimales; cargos negativos, abonos positivos | `-43,57`, `3207,42` |

Separador: punto y coma (`;`), el formato estándar de exportación bancaria española para que Excel y pandas interpreten los importes con coma decimal como números. Codificación UTF-8 con BOM (`utf-8-sig`), compatible con Excel. Orden: fecha descendente.

## Reproducibilidad

Con la misma `--seed` y los mismos parámetros se obtiene exactamente el mismo CSV.
