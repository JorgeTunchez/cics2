📊 CICS Analyzer – Procesamiento de Reportes

Este proyecto procesa archivos .TXT generados por CICS, los convierte a formato JSON y posteriormente los inserta en base de datos SQL Server para análisis.

🚀 Flujo General
Se leen archivos .TXT desde el directorio ENTRADA
Se transforman a JSON
Se almacenan en SALIDA
Se insertan en base de datos
Se registra la carpeta como procesada
📁 Estructura del Proyecto
DEPCICS2/
├── ENTRADA/
│   ├── 2025-09-12/
│   │   ├── CICSADM.TXT
│   │   ├── CICSAORP.TXT
│   │   ├── CICSFILE.TXT
│   │   ├── CICSMANT.TXT
│   │   ├── CICSPEP.TXT
│   │   └── CICSVAR.TXT
│   └── 2025-09-11/
│       └── ...
│
├── SALIDA/
│   ├── 2025-09-12/
│   │   ├── CICSADM.JSON
│   │   └── ...
│
├── funciones.py
├── main.py
├── conexionBD.py
├── scriptBD.sql
└── README.md
⚠️ REGLAS IMPORTANTES
📌 1. Estructura obligatoria

Todos los archivos deben estar dentro de carpetas con formato:

YYYY-MM-DD
Cada carpeta debe contener exactamente 6 archivos TXT
📌 2. Validación de fecha
La fecha se obtiene desde el encabezado de los archivos
Todos los archivos dentro de la carpeta deben tener la misma fecha
La fecha del encabezado debe coincidir con el nombre de la carpeta

Ejemplo:

Carpeta: 2026-04-20
Encabezado: Date 04/20/2026
📌 3. Procesamiento automático

El sistema:

Detecta la carpeta más reciente
Procesa desde la más reciente hacia atrás
Omite carpetas ya procesadas
📌 4. Control de cargas

Se utiliza la tabla:

cics_cargas

Para evitar reprocesar información ya cargada.

🧠 Lógica del Proceso

Por cada carpeta:

Validar cantidad de archivos
Validar fecha única
Verificar si ya fue procesada
Generar JSON
Insertar en BD
Registrar carga
🗃️ Tablas principales
🔹 cics_programs
Contiene información de programas
Campos numéricos convertidos a INT
🔹 cics_transactions
Contiene transacciones
Métricas como attachCount, abendCount en INT
🔹 cics_temporary_storage_queues
Información de colas temporales
Longitudes y cantidades en INT
🔹 cics_files
Información de archivos CICS
Campos numéricos:
strings
buffersIndex
buffersData
🔢 Conversión de datos

Los siguientes campos se convierten a INT:

Programs:
timesUsed
timesFetched
libraryOffset
timesNewCopy
timesRemoved
programSize
Transactions:
attachCount
restartCount
dynamicLocal
remoteStarts
storageViols
abendCount
Temporary Storage Queues:
numberOfItems
minItemLength
maxItemLength
tsqueueFlength
Files:
strings
buffersIndex
buffersData
🧹 Limpieza de datos
Se eliminan comas en números (1,344 → 1344)
Valores inválidos se convierten a NULL
Se evitan encabezados en inserciones
⚙️ Ejecución
python main.py
🛠️ Recomendaciones
No mezclar archivos de diferentes fechas en una carpeta
Verificar que todos los archivos estén completos
Evitar modificar manualmente los JSON generados
Revisar logs en consola para detectar errores
📊 Ejemplo de consulta
SELECT TOP 10
    fileName,
    SUM(buffersData) AS total_buffers
FROM cics_files
GROUP BY fileName
ORDER BY total_buffers DESC;
🧾 Logs del sistema

El sistema muestra:

Archivos procesados
JSON generados
Registros insertados
Errores detectados
📌 Estado del Proyecto

✔ Procesamiento por carpetas
✔ Control de duplicados
✔ Conversión a tipos numéricos
✔ Parsing robusto por tokens
✔ Evita encabezados en BD

🚀 Próximos pasos (opcional)
Dashboard de métricas
Optimización con paralelismo
Alertas de inconsistencias
Automatización programada (Job)
👨‍💻 Autor

Proyecto desarrollado para análisis de reportes CICS.