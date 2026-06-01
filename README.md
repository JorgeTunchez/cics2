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
- [17) Consultas SQL de monitoreo](#17-consultas-sql-de-monitoreo)
- [18) Historial de cambios](#18-historial-de-cambios)

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

- ENTRADA: contiene subcarpetas con nombre YYYY-MM-DD o YYYY_MM_DD y archivos TXT por fecha.
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
  ENTRADA\YYYY_MM_DD\*.TXT

Reglas validadas por el proceso:

1. Se procesan carpetas con formato de fecha YYYY-MM-DD o YYYY_MM_DD.
2. Si una carpeta no tiene los 6 TXT esperados, se registra advertencia y se procesan los archivos disponibles.
3. La fecha del encabezado se valida por archivo (no se descarta toda la carpeta por un solo archivo invalido).
4. Solo se procesan los TXT cuya fecha del encabezado coincide con la carpeta.
5. Los TXT con fecha faltante o invalida se registran como NO PROCESADA en cics_cargas.

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

1. Verifica cantidad esperada de TXT en la carpeta (6) y, si faltan, emite advertencia sin bloquear.
2. Valida fecha por cada archivo y separa archivos validos e invalidos.
3. Registra en cics_cargas como NO PROCESADA los archivos invalidos (con descripcion corta).
4. Si hay archivos validos ya cargados, re-genera JSON y ejecuta backfills solo para esos archivos.
5. Si no hay datos previos para la fecha, genera JSON e inserta BD solo para archivos validos.
6. Registra en cics_cargas un estado por archivo (PROCESADO o NO PROCESADA).

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

Estructura operativa de cics_cargas:

- fecha: fecha de la carpeta procesada.
- carpeta: nombre de carpeta en formato YYYY-MM-DD.
- archivo: id del archivo (FK a cics_archivos.id).
- estado: PROCESADO o NO PROCESADA.
- descripcion: motivo corto del resultado (ej. carga correcta, No se encontro la fecha...).

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

- Fecha valida por archivo.
- Coincidencia fecha encabezado vs nombre de carpeta por cada TXT valido.
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

Nota:

- Con procesamiento parcial, una carpeta puede quedar con mezcla de estados por archivo.
- Revisar cics_cargas por archivo para distinguir cuales fueron PROCESADO y cuales NO PROCESADA.

### Problema: un TXT no se procesa por fecha

Causa habitual:

1. El archivo no trae fecha en encabezado o no coincide con la fecha de carpeta.

Accion:

- Revisar cics_cargas.descripcion para el archivo afectado.
- Corregir el encabezado del TXT y reintentar la corrida.

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

## 17) Consultas SQL de monitoreo

### 17.1 Estado por fecha y porcentaje de exito (cics_cargas)

  SELECT
    c.fecha,
    COUNT(*) AS total_archivos,
    SUM(CASE WHEN c.estado = 'PROCESADO' THEN 1 ELSE 0 END) AS procesados,
    SUM(CASE WHEN c.estado = 'NO PROCESADA' THEN 1 ELSE 0 END) AS no_procesados,
    CAST(
      100.0 * SUM(CASE WHEN c.estado = 'PROCESADO' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0)
      AS DECIMAL(5,2)
    ) AS porcentaje_exito
  FROM cics_cargas c
  GROUP BY c.fecha
  ORDER BY c.fecha DESC;

### 17.2 Detalle de archivos no procesados

  SELECT
    c.fecha,
    c.carpeta,
    a.archivo AS archivo,
    c.estado,
    c.descripcion,
    c.fecha_proceso
  FROM cics_cargas c
  INNER JOIN cics_archivos a ON a.id = c.archivo
  WHERE c.estado = 'NO PROCESADA'
  ORDER BY c.fecha DESC, c.carpeta, a.archivo;

### 17.3 Ultima corrida por carpeta y archivo

  SELECT
    c.fecha,
    c.carpeta,
    a.archivo AS archivo,
    c.estado,
    c.descripcion,
    c.fecha_proceso
  FROM cics_cargas c
  INNER JOIN cics_archivos a ON a.id = c.archivo
  WHERE c.fecha = '2026-05-09'
  ORDER BY a.archivo;

### 17.4 Peso total de tablas CICS (MB)

  ;WITH cte AS
  (
    SELECT
      t.name AS tabla,
      SUM(ps.row_count) AS filas,
      SUM(ps.used_page_count) * 8.0 / 1024 AS usado_mb
    FROM sys.tables t
    INNER JOIN sys.dm_db_partition_stats ps
      ON ps.object_id = t.object_id
    WHERE t.is_ms_shipped = 0
      AND t.name LIKE 'cics[_]%'
    GROUP BY t.name
  )
  SELECT
    tabla,
    filas,
    CAST(usado_mb AS DECIMAL(18,2)) AS usado_mb
  FROM cte
  ORDER BY usado_mb DESC;

  SELECT
    'TOTAL CICS' AS concepto,
    CAST(SUM(usado_mb) AS DECIMAL(18,2)) AS usado_mb
  FROM
  (
    SELECT SUM(ps.used_page_count) * 8.0 / 1024 AS usado_mb
    FROM sys.tables t
    INNER JOIN sys.dm_db_partition_stats ps
      ON ps.object_id = t.object_id
    WHERE t.is_ms_shipped = 0
      AND t.name LIKE 'cics[_]%'
  ) x;

### 17.5 Consultas parametrizadas (fecha y carpeta)

  DECLARE @fecha DATE = '2026-05-09';
  DECLARE @carpeta NVARCHAR(100) = '2026-05-09';

  -- Resumen de estado por fecha/carpeta
  SELECT
    c.fecha,
    c.carpeta,
    COUNT(*) AS total_archivos,
    SUM(CASE WHEN c.estado = 'PROCESADO' THEN 1 ELSE 0 END) AS procesados,
    SUM(CASE WHEN c.estado = 'NO PROCESADA' THEN 1 ELSE 0 END) AS no_procesados,
    CAST(
      100.0 * SUM(CASE WHEN c.estado = 'PROCESADO' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0)
      AS DECIMAL(5,2)
    ) AS porcentaje_exito
  FROM cics_cargas c
  WHERE (@fecha IS NULL OR c.fecha = @fecha)
    AND (@carpeta IS NULL OR c.carpeta = @carpeta)
  GROUP BY c.fecha, c.carpeta
  ORDER BY c.fecha DESC, c.carpeta;

  -- Detalle por archivo (incluye descripcion)
  SELECT
    c.fecha,
    c.carpeta,
    a.archivo AS archivo,
    c.estado,
    c.descripcion,
    c.fecha_proceso
  FROM cics_cargas c
  INNER JOIN cics_archivos a ON a.id = c.archivo
  WHERE (@fecha IS NULL OR c.fecha = @fecha)
    AND (@carpeta IS NULL OR c.carpeta = @carpeta)
  ORDER BY c.fecha DESC, c.carpeta, a.archivo;

  -- Solo archivos no procesados
  SELECT
    c.fecha,
    c.carpeta,
    a.archivo AS archivo,
    c.descripcion,
    c.fecha_proceso
  FROM cics_cargas c
  INNER JOIN cics_archivos a ON a.id = c.archivo
  WHERE c.estado = 'NO PROCESADA'
    AND (@fecha IS NULL OR c.fecha = @fecha)
    AND (@carpeta IS NULL OR c.carpeta = @carpeta)
  ORDER BY c.fecha DESC, c.carpeta, a.archivo;

## 18) Historial de cambios

### v1.3.0 - 2026-06-01

Cambios principales:

- Procesamiento parcial por archivo dentro de cada carpeta de fecha.
- Si un TXT falla validacion de fecha, se marca NO PROCESADA sin bloquear los demas.
- Control de carga por archivo en cics_cargas.
- cics_cargas.archivo ahora guarda el id de cics_archivos (no el nombre literal).
- Se agrega descripcion operativa por archivo en cics_cargas.

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