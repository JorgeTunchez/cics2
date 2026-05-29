# depCics2

Proyecto para procesar reportes CICS en formato TXT, generar salida JSON por archivo y cargar los datos en SQL Server.

El proceso esta pensado para ejecucion por lotes diarios con una carpeta por fecha dentro de ENTRADA.

## Indice

- [1) Objetivo del proyecto](#1-objetivo-del-proyecto)
- [2) Requisitos previos](#2-requisitos-previos)
- [3) Estructura del repositorio](#3-estructura-del-repositorio)
- [4) Preparacion del entorno](#4-preparacion-del-entorno)
- [5) Preparacion de base de datos](#5-preparacion-de-base-de-datos)
- [6) Formato de entrada esperado](#6-formato-de-entrada-esperado)
- [7) Ejecucion del proceso](#7-ejecucion-del-proceso)
- [8) Flujo interno de procesamiento](#8-flujo-interno-de-procesamiento)
- [9) Segmentos soportados actualmente](#9-segmentos-soportados-actualmente)
- [10) Tablas SQL principales](#10-tablas-sql-principales)
- [11) Formato de salida JSON](#11-formato-de-salida-json)
- [12) Backfill y reprocesamiento](#12-backfill-y-reprocesamiento)
- [13) Validaciones importantes](#13-validaciones-importantes)
- [14) Troubleshooting](#14-troubleshooting)
- [15) Buenas practicas operativas](#15-buenas-practicas-operativas)
- [16) Comando rapido de uso](#16-comando-rapido-de-uso)
- [17) Historial de cambios](#17-historial-de-cambios)

## 1) Objetivo del proyecto

El flujo completo realiza:

1. Lectura de archivos TXT CICS por fecha.
2. Parseo de segmentos de interes.
3. Generacion de JSON normalizado por cada archivo de entrada.
4. Insercion de datos en tablas SQL Server.
5. Control de reproceso por fecha y carpeta.
6. Backfill selectivo de segmentos nuevos cuando ya existen cargas previas.

## 2) Requisitos previos

- Sistema operativo Windows (recomendado por driver ODBC actual).
- Python 3.8 o superior.
- Acceso de red al servidor SQL Server.
- Driver ODBC de SQL Server instalado en el host.
- Permisos de lectura/escritura sobre la base de datos objetivo.

Dependencia Python actual del proyecto:

- pyodbc

Ver archivo de dependencias: [requirements.txt](requirements.txt)

## 3) Estructura del repositorio

Archivos principales:

- [main.py](main.py): orquestador de ejecucion por carpeta de fecha.
- [funciones.py](funciones.py): parser de segmentos, validaciones y funciones de insercion.
- [conexionBD.py](conexionBD.py): conexion pyodbc a SQL Server.
- [scriptBD.sql](scriptBD.sql): script de creacion y recreacion de tablas.
- [README.md](README.md): documentacion de uso.

Carpetas funcionales:

- ENTRADA: contiene subcarpetas con nombre YYYY-MM-DD y 6 archivos TXT por fecha.
- SALIDA: contiene subcarpetas YYYY-MM-DD con los JSON generados.

## 4) Preparacion del entorno

### 4.1 Crear entorno virtual

En PowerShell, desde la raiz del proyecto:

    python -m venv .venv
    .\.venv\Scripts\Activate.ps1

Si hay bloqueo por politicas de PowerShell:

    Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
    .\.venv\Scripts\Activate.ps1

### 4.2 Instalar dependencias

Con el entorno activado:

    pip install -r requirements.txt

### 4.3 Configurar conexion a SQL Server

Revisar y ajustar credenciales y endpoint en [conexionBD.py](conexionBD.py).

Actualmente la conexion usa este patron:

- DRIVER={SQL Server}
- SERVER=<host>
- DATABASE=<base>
- UID=<usuario>
- PWD=<password>

Recomendacion de seguridad:

- No dejar credenciales hardcodeadas en produccion.
- Migrar a variables de entorno o gestor de secretos.

## 5) Preparacion de base de datos

Antes de ejecutar el proceso por primera vez, ejecutar [scriptBD.sql](scriptBD.sql) en SQL Server para crear tablas, indices y llaves foraneas.

Notas:

- El script incluye sentencias DROP TABLE IF OBJECT_ID(...), por lo que recrea estructura.
- Usar con precaucion en ambientes con datos productivos.

## 6) Formato de entrada esperado

Ruta esperada:

    ENTRADA\YYYY-MM-DD\*.TXT

Reglas validadas por el proceso:

1. Solo se procesan carpetas con formato de fecha YYYY-MM-DD.
2. Cada carpeta debe contener exactamente 6 archivos TXT.
3. Todos los TXT deben compartir la misma fecha en encabezado.
4. La fecha del encabezado debe coincidir con el nombre de carpeta.

Ejemplo:

    ENTRADA\2026-04-22\CICSADM.TXT
    ENTRADA\2026-04-22\CICSAORP.TXT
    ENTRADA\2026-04-22\CICSFILE.TXT
    ENTRADA\2026-04-22\CICSMANT.TXT
    ENTRADA\2026-04-22\CICSPEP.TXT
    ENTRADA\2026-04-22\CICSVAR.TXT

## 7) Ejecucion del proceso

Con entorno virtual activo, desde la raiz del proyecto:

    python main.py

Archivo de entrada principal: [main.py](main.py)

Salida de consola esperada:

- Inicio y fin de proceso con fecha/hora.
- Carpeta en procesamiento.
- Archivo en analisis.
- Cantidad de segmentos detectados.
- Ruta de JSON generado.
- Resumen de filas insertadas por tabla.
- Mensajes de omision por duplicidad o backfill.

## 8) Flujo interno de procesamiento

Por cada carpeta de fecha:

1. Verifica si la carpeta ya fue procesada en control de cargas.
2. Si ya fue procesada:
   Re-genera JSON y ejecuta backfills selectivos de segmentos nuevos/faltantes.
3. Si no fue procesada:
   Ejecuta validaciones de cantidad de archivos y fecha.
4. Verifica si ya hay registros de la fecha en tablas principales.
5. Si ya hay datos:
   Re-genera JSON y ejecuta backfills.
6. Si no hay datos:
   Genera JSON, inserta en BD y registra carpeta como procesada.

Punto de entrada del flujo por carpeta: [main.py](main.py)

## 9) Segmentos soportados actualmente

Parser habilitado en [funciones.py](funciones.py):

- Programs
- Temporary Storage Queues
- Files
- Data Tables - Requests
- Data Tables - Storage
- Transactions
- Dispatcher
- Dispatcher TCB Modes
- Transaction Manager
- Storage - Domain Subpools
- Storage - Task Subpools
- Storage - Program Subpools
- System Status
- Monitoring
- Statistics
- Trace Status

Nota relevante para Dispatcher TCB Modes:

- Se persiste solo la primera tabla del segmento.
- No se almacenan los campos de cabecera:
  Dispatcher Start Time and Date,
  Address Space Accumulated CPU Time,
  Address Space Accumulated SRB Time,
  Address Space CPU Time (Since Reset),
  Address Space SRB Time (Since Reset).

## 10) Tablas SQL principales

Tablas de control:

- cics_cargas
- cics_archivos
- cics_segmento

Tablas de datos (principales):

- cics_programs
- cics_transactions
- cics_temporary_storage_queues
- cics_files
- cics_data_tables_requests
- cics_data_tables_storage
- cics_dispatcher
- cics_dispatcher_tcb_modes
- cics_storage_domain_subpool
- cics_storage_task_subpool
- cics_storage_program_subpool
- cics_system_status
- cics_transaction_manager
- cics_monitoring
- cics_statistics
- cics_trace_status
- cics_dumps

Definicion de tablas: [scriptBD.sql](scriptBD.sql)

## 11) Formato de salida JSON

Cada archivo TXT produce un JSON en SALIDA\YYYY-MM-DD con esta estructura general:

- Segmentos tipo informacion:

    {
      "nombre": "System Status",
      "tipo": "informacion",
      "detalles": {
        "columnas": ["campoA", "campoB"],
        "datos": {
          "campoA": "valor",
          "campoB": "valor"
        }
      }
    }

- Segmentos tipo tabla:

    {
      "nombre": "Programs",
      "tipo": "tabla",
      "detalles": {
        "columnas": ["col1", "col2"],
        "filas": [
          {"col1": "v1", "col2": "v2"}
        ]
      }
    }

## 12) Backfill y reprocesamiento

Cuando una fecha ya tiene carga previa, el proceso no repite insercion completa.

En ese caso, usa backfills para completar segmentos nuevos o faltantes a partir de los JSON ya generados.

Backfills implementados en [main.py](main.py):

- Statistics
- Trace Status
- Transaction Manager
- Dispatcher
- Data Tables - Requests
- Data Tables - Storage
- Storage - Task Subpools
- Storage - Program Subpools

Si necesitas recargar desde cero una fecha:

1. Eliminar control de esa fecha en cics_cargas.
2. Limpiar datos de esa fecha en tablas objetivo.
3. Ejecutar nuevamente python main.py.

## 13) Validaciones importantes

Validaciones de negocio y tecnica:

- Fecha unica en encabezados por carpeta.
- Coincidencia fecha encabezado vs nombre de carpeta.
- Cantidad exacta de 6 TXT por fecha.
- Existencia de tablas requeridas antes de insertar.
- Control de duplicados por indices unicos en varias tablas.

## 14) Troubleshooting

### Problema: error de conexion SQL Server

Revisar:

1. Parametros de [conexionBD.py](conexionBD.py).
2. Acceso de red al servidor.
3. Driver ODBC instalado.
4. Usuario con permisos sobre la base.

### Problema: carpeta omitida

Causas habituales:

1. Ya esta registrada en cics_cargas.
2. Ya existen datos para esa fecha en tablas principales.

Accion:

- Verificar mensajes de consola y, si aplica, limpiar control/datos para recarga completa.

### Problema: no aparece segmento en JSON

Revisar:

1. Que el segmento exista realmente en el TXT.
2. Que el segmento este habilitado en parse_cicsadm_lite de [funciones.py](funciones.py).

### Problema: no inserta una tabla especifica

Revisar:

1. Que exista la tabla en SQL (ejecutar [scriptBD.sql](scriptBD.sql) si falta estructura).
2. Que haya filas validas en el JSON para ese segmento.
3. Restricciones unicas y llaves foraneas.

## 15) Buenas practicas operativas

- Ejecutar primero en ambiente de pruebas con una fecha controlada.
- Versionar cambios de parser y DDL en conjunto.
- No exponer credenciales en repositorio.
- Monitorear la consola de ejecucion y conservar logs de corrida.

## 16) Comando rapido de uso

Resumen minimo:

1. Activar entorno virtual.
2. Instalar dependencias.
3. Configurar conexion BD.
4. Ejecutar [scriptBD.sql](scriptBD.sql).
5. Colocar archivos en ENTRADA\YYYY-MM-DD.
6. Ejecutar:

    python main.py

## 17) Historial de cambios

### v1.2.0 - 2026-05-29

Cambios principales:

- Documentacion ampliada de instalacion, configuracion y uso operativo.
- Incorporacion de indice navegable al inicio del documento.
- Seccion de troubleshooting y reproceso detallada.
- Registro explicito de flujo de backfill desde [main.py](main.py).

Cambios funcionales relevantes en el parser/carga:

- Soporte de Dispatcher TCB Modes (primera tabla).
- Persistencia en tabla cics_dispatcher_tcb_modes.
- Exclusión de campos de cabecera en Dispatcher TCB Modes:
  Dispatcher Start Time and Date,
  Address Space Accumulated CPU Time,
  Address Space Accumulated SRB Time,
  Address Space CPU Time (Since Reset),
  Address Space SRB Time (Since Reset).

### v1.1.0 - 2026-05-28

Cambios principales:

- Integracion de segmentos adicionales para backfill controlado.
- Ajustes de robustez en parseo de titulos/segmentos compuestos.
- Ampliacion de tablas de destino en SQL Server.

### v1.0.0 - 2026-05-20

Version inicial:

- Proceso base de lectura de TXT CICS, generacion de JSON e insercion SQL.
- Validaciones de fecha por encabezado y estructura de carpetas.
- Control de cargas por fecha/carpeta.