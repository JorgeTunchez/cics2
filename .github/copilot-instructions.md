# Instrucciones para agentes AI — depCics2

Propósito breve
- Ayudar a agentes a ser productivos rápidamente: arquitectura, flujo de datos, comandos y convenciones específicas del proyecto.

Quick start
- Requisitos: Python 3.8+, paquete `pyodbc` disponible (la conexión a BD usa SQL Server). Instalar dependencias manualmente.
- Ejecutar procesamiento completo: `python main.py` desde la raíz del proyecto.

Arquitectura y flujo principal
- Entrada: `Reportes_CICS_TEST/` contiene archivos `.TXT` (se procesan en mayúsculas). Ver [main.py](main.py#L1).
- Parser: `funciones.parse_cicsadm(Path)` convierte un `.TXT` en un diccionario {"Titulo Segmento": {campo: valor}}. Reglas clave: segmentos empiezan con una banda `+_`, terminan con líneas que comienzan por `0-`, y páginas se detectan por líneas con `PAGE`/`Applid`. Ver [funciones.py](funciones.py#L1).
- Salida intermedia: `JSON_SALIDA/` — se escriben JSON por cada TXT procesado (UTF-8). main.py usa `json.dumps(..., ensure_ascii=False)`.
- Post-proc e inserción: `eliminar_segmentos_formato_0()` limpia títulos que empiezan por `0`; `insertar_desde_json_generados()` recorre JSONs e inserta en BD vía funciones en `funciones.py` que llaman a `conexionBD.conectar_base_datos()`.

Puntos relevantes / convenciones del parser
- Nombres de archivo: main transforma a mayúsculas y solo procesa `.TXT`.
- Dos columnas: `split_two_columns` detecta separadores de 3+ espacios y permite parseo de KVs en ambas columnas.
- KVs: Patrón principal `KEY_RE` busca `NombreCampo: valor` (colon-separated). Funciones útiles: `parse_kvs`, `add_kvs_from_line`.
- Tablas: `is_table_segment` detecta segmentos que parecen tablas; el código actual deja el segmento como `{}` (sin detalle).
- Unicidad: `unique_title()` evita duplicados añadiendo ` (2)`, ` (3)`, etc.

Bases de datos y credenciales
- Conexión: `conexionBD.py` contiene la conexión pyodbc con credenciales embebidas (archivo: [conexionBD.py](conexionBD.py#L1)).
- Tablas creadas sobre la marcha: `archivos`, `segmento`, `validacion_sistema` (creación condicional dentro de `funciones.py`).
- Advertencia: las credenciales están en el repositorio; para despliegues/PRs, sustituir por variables de entorno o vault.

Flujos de inserción importantes
- `insertarArchivo(nombreArchivo)` registra nombres procesados en tabla `archivos`.
- `insertarSeg(nombreSegmento)` registra segmentos únicos en tabla `segmento`.
- `insertarValidacionSistema(fecha, archivo, diccionarioSegmentos)` inserta filas por campo en `validacion_sistema`.

Comprobaciones y debugging rápido
- Para depurar un archivo concreto en REPL:
```
from pathlib import Path
from funciones import parse_cicsadm
print(parse_cicsadm(Path('Reportes_CICS_TEST/MI_ARCHIVO.TXT')))
```
- Para debug de inserciones: revisar prints en `insertarValidacionSistema` que muestran `Archivo/Segmento/Campo/Valor`.

Lo que un agente debería modificar si extiende el parser
- Añadir nuevas reglas en `funciones.py` (ej.: detectar nuevo encabezado de página o formato de tabla).
- Mantener salida JSON en la misma estructura: dict título -> dict campos. Otras herramientas dependen de esa forma.

Contactos y próximos pasos sugeridos
- Si quieres: actualizar `conexionBD.py` para usar variables de entorno y añadir `requirements.txt` con `pyodbc`.
- Dime si deseas que adapte el archivo a un estilo más estricto (más ejemplos, tests unitarios o CI).

Fin.
