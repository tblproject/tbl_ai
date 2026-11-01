# Categorizador de movimientos bancarios con Nimble 9B + DuckDB

Carga un CSV de movimientos en una base de datos DuckDB local y completa dos columnas:

- `tipo_operacion` → `ingreso` o `pago`, calculado por el **signo del importe** (sin IA).
- `tipo_movimiento` → categoría del movimiento (`soporte`, `proveedor`, `suministros`…), decidida por **Nimble 9B** a partir del texto `concepto + movimiento`.

Todo se ejecuta en local: DuckDB en un fichero y Nimble a través de Ollama.

## Contenido

| Fichero | Descripción |
|---|---|
| `categorizar_movimientos.py` | Script completo (carga, cálculo, categorías y clasificación) |
| `categorias.yaml` | Catálogo de categorías (el fichero que editas para añadir nuevas) |
| `requirements.txt` | Dependencias Python |
| `movimientos.csv` | CSV de ejemplo (574 movimientos) |
| `movimientos.duckdb` | Base de datos que se crea al ejecutar |

## Requisitos

1. Python 3.10 o superior.
2. [Ollama](https://ollama.com) **0.35 o superior** (los modelos de decisión y el endpoint `/v1/systemone` no existen en versiones anteriores) en marcha, con el modelo descargado:
   ```bash
   ollama pull nimble:9b
   ```
3. Dependencias:
   ```bash
   pip install -r requirements.txt
   ```

## Uso

```bash
python categorizar_movimientos.py --csv movimientos.csv --db movimientos.duckdb
```

| Opción | Por defecto | Descripción |
|---|---|---|
| `--csv` | `movimientos.csv` | CSV de entrada |
| `--db` | `movimientos.duckdb` | Fichero DuckDB persistente |
| `--categorias` | `categorias.yaml` | YAML con el catálogo de categorías |
| `--ollama-url` | `$OLLAMA_HOST` o `http://localhost:11434` | URL de Ollama (necesaria si corre en otra máquina) |
| `--espera-modelo` | `300` | Segundos máximos esperando a que Ollama cargue el modelo |
| `--modelo` | `nimble:9b` | Modelo a usar |
| `--umbral` | `0.5` | Probabilidad mínima de la categoría elegida; por debajo se asigna `otros` |
| `--recargar` | no | Vuelve a cargar el CSV y **borra** las clasificaciones anteriores |
| `--limite N` | todos | Clasifica solo N filas (útil para pruebas) |

El script es **reanudable**: solo clasifica las filas con `tipo_movimiento` vacío. Si Ollama falla en algún movimiento, esa fila queda pendiente y se reintenta en la siguiente ejecución. El código de salida es `1` si hubo errores.

### Ollama en otra máquina

Si Ollama no corre en local, indica su dirección con `--ollama-url http://192.168.1.50:11434` o exporta la variable `OLLAMA_HOST` (admite `host`, `host:puerto` o una URL completa). El servidor debe escuchar fuera de localhost (`OLLAMA_HOST=0.0.0.0` en el servidor).

### Carga del modelo

Antes de clasificar, el script lanza una primera petición para que Ollama cargue el modelo y espera hasta `--espera-modelo` segundos, reintentando mientras el servidor responde con timeout o error 5xx. Después las peticiones usan `keep_alive` de 10 minutos para que no se descargue entre filas.

El script falla rápido: al arrancar comprueba la versión de Ollama (`/api/version`) y aborta con un mensaje claro si es anterior a la 0.35. También aborta si Ollama devuelve un 404 o un error 4xx, o tras 5 errores seguidos, en lugar de recorrer todo el CSV registrando el mismo fallo en cada fila.

Si ves `HTTP 404: 404 page not found`, actualiza Ollama (<https://ollama.com/download>) y vuelve a ejecutar.

## Qué hace, paso a paso

1. **Carga el CSV** (separador `;`, UTF-8 con BOM, fecha `dd/mm/aaaa`, decimales con coma) en la tabla `movimientos` del fichero DuckDB. Solo se carga si la tabla no existe o si se usa `--recargar`.
2. **Calcula `tipo_operacion`** con SQL: importe > 0 → `ingreso`; importe < 0 → `pago`; importe = 0 → `NULL`.
3. **Lee `categorias.yaml` y lo valida.** El YAML es la única fuente del catálogo: de él salen las opciones que se envían a Nimble. Para añadir o cambiar categorías basta con editarlo.
4. **Clasifica cada movimiento pendiente** con Nimble y guarda `tipo_movimiento` y `confianza_movimiento`.

### Esquema de `movimientos`

| Columna | Tipo | Origen |
|---|---|---|
| `id` | BIGINT | Posición de la fila en el CSV |
| `fecha` | DATE | CSV (`Fecha`) |
| `concepto` | VARCHAR | CSV (`Concepto`) |
| `movimiento` | VARCHAR | CSV (`Movimiento`) |
| `importe` | DECIMAL(15,2) | CSV (`Importe`) |
| `tipo_operacion` | VARCHAR | Calculada: `ingreso` / `pago` |
| `tipo_movimiento` | VARCHAR | Nimble (una categoría de `categorias.yaml`) |
| `confianza_movimiento` | DOUBLE | Probabilidad que Nimble asigna a la categoría elegida |

## Cómo se usa Nimble

Nimble es un **modelo de decisión**, no un modelo de chat: no genera texto, elige entre opciones y devuelve la probabilidad de cada una. Se consulta con el endpoint `/v1/systemone` de Ollama (todavía no está en la CLI ni en las librerías `ollama` de Python/JS), así que el script lo llama por HTTP.

- **`state`**: el texto `"<concepto> - <movimiento>"`, por ejemplo `Cobro soporte mensual - factura nº2026941892498350`.
- **Pregunta de tipo `choice`**: las opciones son las categorías, con su descripción como criterio.
- **Categorías según el signo**: a cada movimiento solo se le ofrecen las categorías de su `tipo_operacion` más las marcadas como `ambos`. Así un cobro nunca acaba como `alquiler`.
- **Fallback a `otros`**: se asigna `otros` si Nimble lo elige, si la probabilidad de su elección es menor que `--umbral`, o si devuelve una categoría que no existe.
- **Caché**: los números (nº de factura, etc.) se ignoran para cachear, de modo que `factura nº1…` y `factura nº2…` del mismo concepto se consultan una sola vez.

Límites de Nimble a tener en cuenta: entre 2 y 26 opciones por pregunta (el catálogo actual usa 21) y un contexto de 8.192 tokens por consulta (las descripciones de las categorías cuentan).

## Categorías

Son las 21 categorías de `categorias.yaml`. La columna `tipo_operacion` indica a qué movimientos se ofrece cada una.

| tipo_movimiento | tipo_operacion | Descripción | Ejemplos (concepto / movimiento) |
|---|---|---|---|
| `soporte` | ingreso | Cobro de soporte técnico o mantenimiento recurrente de aplicaciones a clientes. | Cobro soporte mensual; Cobro mantenimiento aplicacion |
| `desarrollo` | ingreso | Cobro de proyectos de desarrollo e implantación de software a clientes. | Cobro proyecto web; Cobro desarrollo móvil; Cobro desarrollo frontend; Cobro integración API; Cobro implantación CRM; Cobro migración datos |
| `consultoria` | ingreso | Cobro de servicios de consultoría, auditoría técnica o analítica de datos. | Cobro servicio consultoría; Cobro auditoría técnica; Cobro analítica de datos |
| `formacion` | ingreso | Cobro de cursos y formación impartida a empresas. | Cobro formación corporativa |
| `marketing_diseno` | ingreso | Cobro de campañas de marketing y servicios de diseño a clientes. | Cobro campañas marketing; Cobro facturación diseño |
| `pasarela_pago` | ingreso | Cobros recibidos a través de una pasarela de pago. | Cobro pasarela de pago |
| `intereses` | ingreso | Intereses bancarios cobrados. | Cobro intereses internacional |
| `nomina` | ingreso | Nómina recibida de una empresa. | Nomina / Transferencia nomina empresa |
| `transferencia_recibida` | ingreso | Transferencia recibida de una persona física. | Transferencia recibida / Hortensia Martorell Higueras |
| `devolucion` | ingreso | Devolución de una compra pagada con tarjeta. | Tarjeta crédito / Devolución compra |
| `suministros` | pago | Recibos de luz, gas, agua, internet, telefonía y otros suministros. | Adeudo luz; Adeudo gas; Adeudo agua; Adeudo internet; Adeudo telefonía; Adeudo suministros; Pago servicio electricidad oficina |
| `alquiler` | pago | Alquiler del local u oficina. | Adeudo alquiler local |
| `seguro` | pago | Primas y recibos de seguros. | Adeudo seguro |
| `gestoria` | pago | Honorarios de gestoría o asesoría. | Adeudo gestoría |
| `servicios_generales` | pago | Servicios generales del local: limpieza, vigilancia, reparación de equipos. | Adeudo limpieza; Adeudo vigilancia; Pago servicio limpieza local; Pago servicio reparación equipos |
| `servicios_externos` | pago | Servicios profesionales subcontratados: copywriting, diseño gráfico, SEO, traducción, publicidad y mantenimiento web. | Pago servicio copywrite contenido; Pago servicio diseño gráfico; Pago servicio seo posicionamiento; Pago servicio traducción documentos; Pago servicio publicidad digital; Pago servicio mantenimiento web |
| `compras_tarjeta` | pago | Compras con tarjeta en comercios: restauración, supermercado, panadería, ferretería, combustible. | Tarjeta crédito / restauración PALACIOS Y ASOCIADOS S.A.T.; compra ferretería ... |
| `pago_factura` | pago | Transferencia emitida para pagar una factura concreta. | Transferencia realizada / Pago fact. 2022-5812 |
| `proveedor` | ambos | Operaciones con un proveedor identificado por su razón social (S.L., S.A., S.C.P., ...). | Pago a proveedor / CORTÉS Y ASOCIADOS S.A.D |
| `suscripcion_software` | ambos | Suscripciones, licencias y renovaciones de software, tanto pagadas como cobradas. | Cobro suscripción software; Adeudo software; Suscripción X / Renovación X |
| `otros` | ambos | Cualquier movimiento que no encaje claramente en ninguna otra categoría. | Plan 238850174782; textos ambiguos o sin sentido |

### Formato de `categorias.yaml`

Es una lista de objetos; cada uno es una categoría:

```yaml
- nombre: viajes
  descripcion: Gastos de viaje: billetes, hoteles, alquiler de coche.
  tipo_operacion: pago        # ingreso | pago | ambos
  ejemplos: Tarjeta crédito / Hotel ...   # opcional, solo para humanos
```

| Campo | Descripción |
|---|---|
| `nombre` | Identificador único sin espacios; es el valor que se escribe en `tipo_movimiento` |
| `descripcion` | Texto que se envía a Nimble como criterio de la opción |
| `tipo_operacion` | `ingreso`, `pago` o `ambos` |
| `ejemplos` | Opcional; referencia para el humano, no se envía a Nimble |

Al arrancar, el script valida el fichero y aborta con un mensaje claro si hay un YAML mal formado, un campo inválido, nombres repetidos, falta la categoría `otros` o se superan las 26 categorías que admite Nimble.

## Operaciones habituales

Añadir una categoría y reclasificar solo lo que cayó en `otros`: agrega el elemento al final de `categorias.yaml` y ejecuta

```bash
duckdb movimientos.duckdb "UPDATE movimientos SET tipo_movimiento = NULL, confianza_movimiento = NULL WHERE tipo_movimiento = 'otros'"
python categorizar_movimientos.py
```

Si quieres reclasificar todo con el catálogo nuevo, usa `--recargar`. Si eliminas o renombras una categoría, las filas ya clasificadas con el nombre antiguo conservan ese valor hasta que las reclasifiques.

Revisar lo que ha quedado en `otros`, empezando por lo menos seguro:

```sql
SELECT concepto, movimiento, importe, confianza_movimiento
FROM movimientos WHERE tipo_movimiento = 'otros'
ORDER BY confianza_movimiento;
```

Resumen por categoría y sentido:

```sql
SELECT tipo_operacion, tipo_movimiento, count(*) AS n, sum(importe) AS total
FROM movimientos GROUP BY ALL ORDER BY tipo_operacion, total DESC;
```

## Particularidades del CSV de ejemplo

- **`Pago a proveedor` con importe positivo**: las 13 filas de `Pago a proveedor` tienen importe positivo, por lo que `tipo_operacion` sale `ingreso`, siguiendo la regla del signo. La categoría `proveedor` es `ambos` justamente para que se pueda asignar. Si en tu banco el signo está invertido, revisa el CSV de origen.
- **`Plan <número>`** (transferencias realizadas sin más contexto) no encaja en ninguna categoría y debe acabar en `otros`.
- **Cobros con conceptos sin sentido** (por ejemplo `Cobro nosotros peso`) tienen factura pero no indican el servicio; es normal que vayan a `otros` o salgan con poca confianza.

## Ajustar el umbral

La probabilidad de Nimble **no equivale a la tasa de acierto real**. Para elegir un `--umbral` razonable, clasifica con `--umbral 0` y mira la distribución de `confianza_movimiento` en las filas que revisas a mano. Con el umbral por defecto de 0,5 se prioriza que lo dudoso acabe en `otros`.

## Notas

- El script se ha probado de extremo a extremo contra un servidor que imita la API de Nimble (carga, signo, categorías, reanudación y error con Ollama caído). **No se ha ejecutado con el modelo real**, así que la calidad de la clasificación hay que validarla en tu máquina; si hay desajustes, lo habitual es afinar las descripciones del fichero `categorias.yaml`.