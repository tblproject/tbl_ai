#!/usr/bin/env python3
"""Categoriza movimientos bancarios (CSV) con Nimble 9B (Ollama) y DuckDB.

Flujo:
  1. Carga el CSV en la tabla ``movimientos`` de un fichero DuckDB local.
  2. Calcula ``tipo_operacion`` (ingreso / pago) según el signo del importe.
  3. Lee y valida las categorías de ``categorias.yaml``.
  4. Clasifica cada movimiento con Nimble a partir de ``concepto + movimiento``
     y rellena ``tipo_movimiento``; lo que no se pueda clasificar queda en "otros".

El script es reanudable: solo clasifica filas con ``tipo_movimiento IS NULL``.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Literal

import duckdb
import requests
import yaml
from pydantic import BaseModel, Field, ValidationError

log = logging.getLogger("categorizador")

# --------------------------------------------------------------------------- #
# Configuración por defecto
# --------------------------------------------------------------------------- #
DEFAULT_CSV = "../../data/generador_movimientos/movimientos.csv"
DEFAULT_DB = "../../data/categorizar_movimientos/movimientos.duckdb"
DEFAULT_CATEGORIAS = "../../config/categorizar_movimientos/categorias.yaml"
DEFAULT_OLLAMA_URL = "http://192.168.0.16:11434"


def url_ollama_por_defecto() -> str:
    """URL de Ollama: variable OLLAMA_HOST (admite 'host', 'host:puerto' o URL completa) o localhost."""
    host = os.environ.get("OLLAMA_HOST", "").strip().rstrip("/")
    if not host:
        return DEFAULT_OLLAMA_URL
    if "://" not in host:
        host = f"http://{host}"
    if not re.search(r":\d+$", host):
        host += ":11434"
    return host


DEFAULT_MODEL = "nimble:9b"
DEFAULT_UMBRAL = 0.5  # probabilidad mínima de la categoría elegida; si no, "otros"

TABLA_MOVIMIENTOS = "movimientos"
CATEGORIA_FALLBACK = "otros"
MAX_OPCIONES_NIMBLE = 26  # límite de opciones por pregunta tipo "choice"
MIN_VERSION_OLLAMA = (0, 35)  # primera versión con /v1/systemone (modelos de decisión)
DEFAULT_ESPERA_MODELO = 300.0  # segundos máximos esperando a que Ollama cargue el modelo
MAX_ERRORES_SEGUIDOS = 5  # tras N fallos consecutivos se aborta la ejecución

TipoOperacion = Literal["ingreso", "pago", "ambos"]


# --------------------------------------------------------------------------- #
# Catálogo de categorías (fichero YAML)
# --------------------------------------------------------------------------- #
class Categoria(BaseModel):
    nombre: str = Field(min_length=1, pattern=r"^\S+$")
    descripcion: str = Field(min_length=1)
    tipo_operacion: TipoOperacion
    ejemplos: str = ""


class CatalogoError(ValueError):
    """El fichero de categorías no existe o no es válido."""


def cargar_categorias_yaml(ruta: Path) -> list[Categoria]:
    """Lee y valida el YAML: lista de objetos con nombre, descripcion, tipo_operacion, ejemplos."""
    try:
        datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CatalogoError(f"No se puede leer el fichero de categorías {ruta}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise CatalogoError(f"YAML inválido en {ruta}: {exc}") from exc

    if not isinstance(datos, list):
        raise CatalogoError(f"{ruta} debe contener una lista de categorías.")
    try:
        categorias = [Categoria.model_validate(item) for item in datos]
    except ValidationError as exc:
        raise CatalogoError(f"Categoría inválida en {ruta}:\n{exc}") from exc

    nombres = [c.nombre for c in categorias]
    duplicados = sorted({n for n in nombres if nombres.count(n) > 1})
    if duplicados:
        raise CatalogoError(f"Nombres de categoría repetidos: {', '.join(duplicados)}")
    if CATEGORIA_FALLBACK not in nombres:
        raise CatalogoError(f"Falta la categoría obligatoria '{CATEGORIA_FALLBACK}'.")
    if len(categorias) > MAX_OPCIONES_NIMBLE:
        raise CatalogoError(
            f"Hay {len(categorias)} categorías; Nimble admite como máximo {MAX_OPCIONES_NIMBLE}."
        )
    return categorias


# --------------------------------------------------------------------------- #
# Cliente de Nimble (modelo de decisión, endpoint /v1/systemone de Ollama)
# --------------------------------------------------------------------------- #
class NimbleError(RuntimeError):
    """Error al consultar Nimble a través de Ollama."""


class NimbleFatalError(NimbleError):
    """Error que se repetiría en todas las filas (Ollama antiguo, modelo ausente...): hay que abortar."""


class _RespuestaChoice(BaseModel):
    choice: str
    probabilities: dict[str, float]
    confidence: float | None = None


class _RespuestaSystemOne(BaseModel):
    answers: dict[str, _RespuestaChoice]


class ResultadoClasificacion(BaseModel):
    categoria: str
    probabilidad: float = Field(ge=0.0, le=1.0)


class NimbleClassifier:
    """Clasifica un texto en una de las categorías recibidas (nombre -> descripción)."""

    _PREGUNTA = "tipo_movimiento"
    _INSTRUCCIONES = (
        "Eres un asistente contable. El texto es un movimiento bancario formado por el "
        "concepto y el detalle del movimiento. Elige la categoría que mejor lo describe. "
        f"Si ninguna encaja con claridad, elige '{CATEGORIA_FALLBACK}'."
    )

    def __init__(
        self,
        categorias: dict[str, str],
        *,
        base_url: str = DEFAULT_OLLAMA_URL,
        model: str = DEFAULT_MODEL,
        fallback: str = CATEGORIA_FALLBACK,
        timeout: float = 120.0,
        reintentos: int = 3,
    ) -> None:
        if fallback not in categorias:
            raise ValueError(f"La categoría de reserva '{fallback}' debe estar en las categorías.")
        if not 2 <= len(categorias) <= MAX_OPCIONES_NIMBLE:
            raise ValueError(
                f"Nimble admite entre 2 y {MAX_OPCIONES_NIMBLE} opciones; recibidas {len(categorias)}."
            )
        self._categorias = dict(categorias)
        self._url = f"{base_url.rstrip('/')}/v1/systemone"
        self._model = model
        self._fallback = fallback
        self._timeout = timeout
        self._reintentos = max(1, reintentos)
        self._session = requests.Session()

    def _payload(self, texto: str) -> dict:
        return {
            "model": self._model,
            "state": texto,
            "keep_alive": "10m",
            "questions": {
                self._PREGUNTA: {
                    "type": "choice",
                    "instructions": self._INSTRUCCIONES,
                    "criteria": self._categorias,
                }
            },
        }

    def classify(self, texto: str) -> ResultadoClasificacion:
        payload = self._payload(texto)
        datos = self._post(payload)
        try:
            respuesta = _RespuestaSystemOne.model_validate(datos).answers[self._PREGUNTA]
        except (ValidationError, KeyError) as exc:
            raise NimbleError(f"Respuesta de Nimble con formato inesperado: {datos!r}") from exc

        if respuesta.choice not in self._categorias:
            log.warning("Nimble devolvió una categoría desconocida: %r", respuesta.choice)
            return ResultadoClasificacion(categoria=self._fallback, probabilidad=0.0)
        prob = min(max(respuesta.probabilities.get(respuesta.choice, 0.0), 0.0), 1.0)
        return ResultadoClasificacion(categoria=respuesta.choice, probabilidad=prob)

    def ping(self) -> None:
        """Comprueba que Ollama responde y es compatible con modelos de decisión."""
        base = self._url.rsplit("/v1/", 1)[0]
        try:
            resp = self._session.get(f"{base}/api/version", timeout=5)
            resp.raise_for_status()
            version = str(resp.json().get("version", ""))
        except (requests.RequestException, ValueError) as exc:
            raise NimbleFatalError(
                f"No se puede conectar con Ollama en {base}. ¿Está en marcha (`ollama serve`) "
                f"y descargado el modelo (`ollama pull {self._model}`)?"
            ) from exc

        m = re.match(r"(\d+)\.(\d+)", version)
        if m and (int(m.group(1)), int(m.group(2))) < MIN_VERSION_OLLAMA:
            minima = ".".join(map(str, MIN_VERSION_OLLAMA))
            raise NimbleFatalError(
                f"Tu Ollama es la versión {version} y los modelos de decisión (Nimble) requieren "
                f"{minima} o superior. Actualiza Ollama: https://ollama.com/download"
            )

    def _validar_status(self, resp: requests.Response) -> None:
        """Lanza NimbleFatalError en los 4xx: reintentar no los arregla."""
        if resp.status_code == 404:
            raise NimbleFatalError(
                f"Ollama respondió 404 en {self._url}. Si el cuerpo es 'page not found', ese servidor "
                f"no expone /v1/systemone (versión sin soporte u otro servicio en ese puerto); si "
                f"menciona el modelo, ejecuta `ollama pull {self._model}`. Respuesta: {resp.text[:200]}"
            )
        if 400 <= resp.status_code < 500:
            raise NimbleFatalError(f"HTTP {resp.status_code}: {resp.text[:200]}")

    def esperar_modelo(self, max_espera: float = DEFAULT_ESPERA_MODELO, pausa: float = 2.0) -> float:
        """Lanza una primera petición para que Ollama cargue el modelo y espera a que responda.

        Reintenta ante timeouts, errores de conexión y 5xx (el modelo aún se está cargando).
        Los 4xx abortan de inmediato. Devuelve los segundos que tardó.
        """
        inicio = time.monotonic()
        payload = self._payload("calentamiento")
        log.info("Cargando el modelo '%s' en Ollama (puede tardar; espera máx. %.0f s)...",
                 self._model, max_espera)
        ultimo_error: object = "sin respuesta"
        while True:
            transcurrido = time.monotonic() - inicio
            restante = max_espera - transcurrido
            if restante <= 0:
                raise NimbleFatalError(
                    f"El modelo no respondió en {max_espera:.0f} s ({ultimo_error}). "
                    f"Prueba `ollama run {self._model}` o aumenta --espera-modelo."
                )
            try:
                resp = self._session.post(
                    self._url, json=payload, timeout=min(self._timeout, max(restante, 5.0))
                )
            except requests.RequestException as exc:
                ultimo_error = exc
            else:
                self._validar_status(resp)
                if resp.status_code < 300:
                    t = time.monotonic() - inicio
                    log.info("Modelo listo en %.1f s", t)
                    return t
                ultimo_error = f"HTTP {resp.status_code}: {resp.text[:120]}"
            log.info("  esperando al modelo (%.0f s)...", time.monotonic() - inicio)
            time.sleep(pausa)

    def _post(self, payload: dict) -> dict:
        ultimo_error: Exception | None = None
        for intento in range(1, self._reintentos + 1):
            try:
                resp = self._session.post(self._url, json=payload, timeout=self._timeout)
            except requests.RequestException as exc:
                ultimo_error = exc
            else:
                self._validar_status(resp)
                if resp.status_code >= 500:
                    ultimo_error = NimbleError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                else:
                    try:
                        return resp.json()
                    except ValueError as exc:
                        ultimo_error = exc
            time.sleep(min(2 ** (intento - 1), 8))
        raise NimbleError(f"Fallo tras {self._reintentos} intentos: {ultimo_error}") from ultimo_error


# --------------------------------------------------------------------------- #
# DuckDB
# --------------------------------------------------------------------------- #
def cargar_csv(con: duckdb.DuckDBPyConnection, csv_path: Path) -> int:
    """(Re)crea la tabla ``movimientos`` a partir del CSV. Devuelve nº de filas."""
    con.execute(
        f"""
        CREATE OR REPLACE TABLE {TABLA_MOVIMIENTOS} AS
        SELECT
            row_number() OVER ()           AS id,
            Fecha                          AS fecha,
            Concepto                       AS concepto,
            Movimiento                     AS movimiento,
            Importe                        AS importe,
            CAST(NULL AS VARCHAR)          AS tipo_operacion,
            CAST(NULL AS VARCHAR)          AS tipo_movimiento,
            CAST(NULL AS DOUBLE)           AS confianza_movimiento
        FROM read_csv(
            ?,
            delim = ';',
            header = true,
            encoding = 'utf-8',
            decimal_separator = ',',
            dateformat = '%d/%m/%Y',
            columns = {{
                'Fecha': 'DATE',
                'Concepto': 'VARCHAR',
                'Movimiento': 'VARCHAR',
                'Importe': 'DECIMAL(15,2)'
            }}
        )
        """,
        [str(csv_path)],
    )
    return con.execute(f"SELECT count(*) FROM {TABLA_MOVIMIENTOS}").fetchone()[0]


def calcular_tipo_operacion(con: duckdb.DuckDBPyConnection) -> None:
    """importe > 0 -> ingreso; importe < 0 -> pago; importe = 0 -> NULL."""
    con.execute(
        f"""
        UPDATE {TABLA_MOVIMIENTOS}
        SET tipo_operacion = CASE
            WHEN importe > 0 THEN 'ingreso'
            WHEN importe < 0 THEN 'pago'
        END
        """
    )


def _categorias_para(categorias: list[Categoria], tipo_operacion: str | None) -> dict[str, str]:
    """Categorías aplicables a un tipo de operación (nombre -> descripción)."""
    return {
        c.nombre: c.descripcion
        for c in categorias
        if tipo_operacion is None or c.tipo_operacion in (tipo_operacion, "ambos")
    }


# --------------------------------------------------------------------------- #
# Clasificación
# --------------------------------------------------------------------------- #
_RE_NUMEROS = re.compile(r"\d+")


def _clave_cache(tipo_operacion: str | None, texto: str) -> tuple[str | None, str]:
    """Los números (nº de factura, etc.) no cambian la categoría: se normalizan para cachear."""
    return tipo_operacion, _RE_NUMEROS.sub("#", texto).casefold()


def clasificar_movimientos(
    con: duckdb.DuckDBPyConnection,
    categorias: list[Categoria],
    *,
    base_url: str,
    model: str,
    umbral: float,
    espera_modelo: float = DEFAULT_ESPERA_MODELO,
    limite: int | None = None,
) -> tuple[int, int]:
    """Rellena tipo_movimiento en las filas pendientes. Devuelve (clasificadas, errores)."""
    clasificadores: dict[str | None, NimbleClassifier] = {}

    def clasificador(op: str | None) -> NimbleClassifier:
        if op not in clasificadores:
            clasificadores[op] = NimbleClassifier(
                _categorias_para(categorias, op), base_url=base_url, model=model
            )
        return clasificadores[op]

    clasificador("ingreso").ping()
    clasificador("ingreso").esperar_modelo(espera_modelo)

    sql = (
        f"SELECT id, concepto, movimiento, tipo_operacion FROM {TABLA_MOVIMIENTOS} "
        f"WHERE tipo_movimiento IS NULL ORDER BY id"
    )
    if limite:
        sql += f" LIMIT {int(limite)}"
    pendientes = con.execute(sql).fetchall()
    log.info("Movimientos pendientes de clasificar: %d", len(pendientes))

    cache: dict[tuple[str | None, str], ResultadoClasificacion] = {}
    ok = errores = seguidos = 0
    for i, (id_, concepto, movimiento, op) in enumerate(pendientes, start=1):
        texto = f"{concepto} - {movimiento}"
        clave = _clave_cache(op, texto)
        try:
            if clave not in cache:
                cache[clave] = clasificador(op).classify(texto)
            res = cache[clave]
        except NimbleFatalError:
            raise  # se repetiría en todas las filas: abortar con el mensaje original
        except NimbleError as exc:
            errores += 1
            seguidos += 1
            log.error("Fila %s sin clasificar (se reintentará en la próxima ejecución): %s", id_, exc)
            if seguidos >= MAX_ERRORES_SEGUIDOS:
                raise NimbleFatalError(
                    f"{seguidos} errores seguidos; se aborta. Las filas ya clasificadas se conservan."
                ) from exc
            continue
        seguidos = 0

        categoria = res.categoria if res.probabilidad >= umbral else CATEGORIA_FALLBACK
        con.execute(
            f"UPDATE {TABLA_MOVIMIENTOS} SET tipo_movimiento = ?, confianza_movimiento = ? WHERE id = ?",
            [categoria, round(res.probabilidad, 4), id_],
        )
        ok += 1
        if i % 50 == 0:
            log.info("  %d/%d", i, len(pendientes))
    return ok, errores


def resumen(con: duckdb.DuckDBPyConnection) -> None:
    filas = con.execute(
        f"""
        SELECT coalesce(tipo_movimiento, '(pendiente)') AS tipo_movimiento,
               count(*) AS n,
               round(avg(confianza_movimiento), 3) AS confianza_media
        FROM {TABLA_MOVIMIENTOS}
        GROUP BY 1 ORDER BY n DESC
        """
    ).fetchall()
    print(f"\n{'tipo_movimiento':<24}{'filas':>7}{'conf. media':>13}")
    for tipo, n, conf in filas:
        print(f"{tipo:<24}{n:>7}{(conf if conf is not None else ''):>13}")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--csv", type=Path, default=Path(DEFAULT_CSV), help="CSV de movimientos")
    p.add_argument("--db", type=Path, default=Path(DEFAULT_DB), help="Fichero DuckDB persistente")
    p.add_argument("--categorias", type=Path, default=DEFAULT_CATEGORIAS,
                   help="YAML con el catálogo de categorías")
    p.add_argument("--ollama-url", default=url_ollama_por_defecto(),
                   help="URL de Ollama (por defecto $OLLAMA_HOST o http://localhost:11434)")
    p.add_argument("--modelo", default=DEFAULT_MODEL)
    p.add_argument("--espera-modelo", type=float, default=DEFAULT_ESPERA_MODELO, metavar="SEG",
                   help="Segundos máximos esperando a que Ollama cargue el modelo (por defecto 300)")
    p.add_argument("--umbral", type=float, default=DEFAULT_UMBRAL,
                   help="Probabilidad mínima para aceptar la categoría de Nimble (si no, 'otros')")
    p.add_argument("--recargar", action="store_true",
                   help="Vuelve a cargar el CSV y descarta las clasificaciones anteriores")
    p.add_argument("--limite", type=int, default=None, help="Clasificar solo N filas (pruebas)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not 0.0 <= args.umbral <= 1.0:
        log.error("--umbral debe estar entre 0 y 1")
        return 2

    try:
        categorias = cargar_categorias_yaml(args.categorias)
    except CatalogoError as exc:
        log.error("%s", exc)
        return 2

    try:
        args.db.parent.mkdir(parents=True, exist_ok=True)  # DuckDB crea el fichero, pero no las carpetas
    except OSError as exc:
        log.error("No se puede crear la carpeta de la base de datos %s: %s", args.db.parent, exc)
        return 2

    con = duckdb.connect(str(args.db))
    try:
        existe = con.execute(
            "SELECT count(*) > 0 FROM information_schema.tables WHERE table_name = ?",
            [TABLA_MOVIMIENTOS],
        ).fetchone()[0]
        if args.recargar or not existe:
            if not args.csv.is_file():
                log.error("No existe el CSV: %s", args.csv)
                return 2
            n = cargar_csv(con, args.csv)
            log.info("CSV cargado en '%s': %d filas", TABLA_MOVIMIENTOS, n)
        calcular_tipo_operacion(con)

        ok, errores = clasificar_movimientos(
            con, categorias, base_url=args.ollama_url, model=args.modelo, umbral=args.umbral, espera_modelo=args.espera_modelo,
            limite=args.limite
        )
        log.info("Clasificadas: %d | con error: %d", ok, errores)
        resumen(con)
        return 1 if errores else 0
    except NimbleError as exc:
        log.error("%s", exc)
        return 1
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())