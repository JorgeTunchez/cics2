# CICS Analyzer - Procesamiento de Reportes

Este proyecto procesa reportes CICS en formato TXT, genera JSON estructurado por segmento y carga la informacion en SQL Server.

## Requisitos

- Python 3.8+
- pyodbc instalado
- SQL Server accesible desde la maquina donde se ejecuta el proceso

Instalacion rapida:

```bash
pip install pyodbc
```

## Estructura del proyecto

```text
depCics2/
|-- ENTRADA/
|   |-- 2026-04-22/
|   |   |-- CICSADM.TXT
|   |   |-- CICSAORP.TXT
|   |   |-- CICSFILE.TXT
|   |   |-- CICSMANT.TXT
|   |   |-- CICSPEP.TXT
|   |   `-- CICSVAR.TXT
|-- SALIDA/
|   `-- YYYY-MM-DD/
|       `-- *.JSON
|-- conexionBD.py
|-- funciones.py
|-- main.py
|-- scriptBD.sql
`-- README.md
```

## Flujo del proceso

Por cada carpeta de fecha en ENTRADA:

1. Valida formato de carpeta YYYY-MM-DD.
2. Valida que existan exactamente 6 archivos TXT.
3. Lee fecha desde encabezados y valida fecha unica.
4. Verifica que la fecha del encabezado coincida con el nombre de carpeta.
5. Omite la carpeta si ya fue registrada en cics_cargas.
6. Genera JSON por cada TXT en SALIDA/<fecha>/.
7. Inserta datos en SQL Server.
8. Registra la carpeta como procesada en cics_cargas.

## Segmentos soportados

- Programs
- Temporary Storage Queues
- Files
- Transactions
- Storage - Domain Subpools
- System Status
- Monitoring

Nota sobre Monitoring:

- Monitoring viene en bloque doble junto con Statistics.
- El parser extrae Monitoring y omite Statistics.

## Tablas principales de salida

- cics_archivos
- cics_segmento
- cics_programs
- cics_transactions
- cics_temporary_storage_queues
- cics_files
- cics_system_status
- cics_monitoring
- cics_cargas

## Ejecucion

```bash
python main.py
```

## Salidas esperadas en consola

- Archivo en analisis
- Segmentos detectados por archivo
- JSON generado
- Resumen de inserciones por tabla
- Errores de validacion o de BD

## Validaciones y control de reproceso

El proceso puede no cargar una carpeta por dos razones:

1. La carpeta ya esta registrada en cics_cargas.
2. Ya existen registros en tablas principales para esa fecha.

Si necesitas reprocesar una fecha, primero debes limpiar el control y/o las tablas objetivo para esa fecha.

## Estructura JSON

Cada segmento se guarda como objeto con esta forma:

```json
{
    "System Status": {
        "nombre": "System Status",
        "tipo": "informacion",
        "detalles": {
            "columnas": ["campo1", "campo2"],
            "datos": {
                "campo1": "valor",
                "campo2": "valor"
            }
        }
    },
    "Programs": {
        "nombre": "Programs",
        "tipo": "tabla",
        "detalles": {
            "columnas": ["col1", "col2"],
            "filas": [
                {"col1": "v1", "col2": "v2"}
            ]
        }
    }
}
```

## Troubleshooting rapido

- No inserta una tabla:
    - Verifica conectividad SQL Server en conexionBD.py.
    - Verifica que exista la tabla en BD.
    - Revisa el resumen de inserciones en consola.

- No aparece un segmento en JSON:
    - Valida que el segmento exista en el TXT de entrada.
    - Revisa que el parser lo tenga habilitado en funciones.py.

- Carpeta omitida:
    - Revisa cics_cargas para la fecha/carpeta.
    - Revisa si hay datos previos para esa fecha.