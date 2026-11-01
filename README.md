# Objetivo
La idea de este repositorio es recopilar utilidades y código de demos que se hagan asociados a TBL Project utilizando herramientas de Inteligencia artificial.

# Contenido

El repositorio actualmente tiene los siguientes directorios y contenido:
- ***config***: es el directorio en donde se mantendrán los archivos de configuración.
    - **categorizar_movimientos**: en este directorio se almacena el catálogo de categorías que utiliza el script categorizar_movimientos.py como catálogo base. Esta configuración está en el archivo **categorias.yaml**
- ***data***: en este directorio se persistirán datos que se usarán en procesados. Se deja un archivo CSV con datos sintéticos de movimientos bancarios generados con la funcionalidad de **src/generador_movimientos** para usarlo de base de categorización para el proceso de **src/categorizar_movimientos**. El archivo es **movimientos.csv**.
- ***src***: recoge el código de scripts y utilidades. Actualmente tiene:
    - **categorizar_movimientos**: que recopila el código para una demo del uso de modelos de decisión para enriquecer una tabla de movimientos bancarios añadiendo categorías en cada movimiento.
    - **generador_movimientos**: recopila código para generar datos sintéticos de movimientos bancarios utilizado por el proceso de **categorizar_movimientos**.
