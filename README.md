# 📊 CICS Parser & Analyzer

Este proyecto permite procesar archivos tipo **CICSADM** (.TXT), extraer información relevante y almacenarla en una base de datos SQL Server para su análisis.

Actualmente soporta los siguientes segmentos:

* Programs
* Transactions
* Temporary Storage Queues
* Files

---

## ⚙️ Requisitos

* Python 3.10+
* SQL Server
* Librerías Python (según tu proyecto, por ejemplo):

  * pyodbc
  * pathlib (nativo)
  * json (nativo)

---

## 📁 Estructura del proyecto

```
DEPCICS2/
│
├── ENTRADA/        # Archivos .TXT de entrada (OBLIGATORIO)
├── SALIDA/         # Archivos .JSON generados (OBLIGATORIO)
│
├── funciones.py    # Lógica principal de parsing e inserción
├── conexionDB.py   # Conexión a base de datos
├── main.py         # Punto de ejecución
├── scriptBD.sql    # Script de creación de tablas
└── .gitignore
```

---

## ⚠️ IMPORTANTE (OBLIGATORIO)

El proyecto depende de los siguientes directorios:

### 📥 ENTRADA

* Aquí deben colocarse los archivos `.TXT` provenientes de CICS
* Ejemplo:

  ```
  ENTRADA/
  ├── CICSADM.TXT
  ├── CICSVAR.TXT
  ```

### 📤 SALIDA

* Aquí se generan automáticamente los archivos `.JSON`
* No se deben modificar manualmente

👉 Si estos directorios no existen, el proceso fallará.

---

## 🚀 Ejecución

1. Colocar archivos `.TXT` en la carpeta `ENTRADA`
2. Ejecutar el proyecto:

```bash
python main.py
```

3. El sistema:

* Procesa cada archivo
* Genera JSON en `SALIDA`
* Inserta datos en base de datos

---

## 🗄️ Base de datos

Las siguientes tablas deben existir previamente:

* `cics_archivos`
* `cics_segmento`
* `cics_programs`
* `cics_transactions`
* `cics_temporary_storage_queues`
* `cics_files`

👉 Puedes usar `scriptBD.sql` para crearlas.

---

## 📊 Tipos de datos procesados

### 🔹 Programs

Información sobre programas ejecutados en CICS.

### 🔹 Transactions

Relación entre transacciones y programas.

### 🔹 Temporary Storage Queues

Colas temporales utilizadas por CICS.

### 🔹 Files

Configuración de archivos (VSAM, buffers, recovery, etc.).

---

## ⚡ Rendimiento

* Se utilizan inserciones por lotes (`executemany`)
* Optimizado para grandes volúmenes de datos
* Tiempo promedio: ~20 minutos para cargas grandes (puede mejorar con paralelización)

---

## 🛠️ Recomendaciones

* No subir archivos de `ENTRADA` ni `SALIDA` al repositorio
* Mantener `.gitignore` actualizado
* Validar datos antes de ejecutar consultas analíticas

---

## 🧪 Ejemplo de consulta

```sql
SELECT TOP 10
    fileName,
    SUM(TRY_CAST(buffersData AS INT)) AS total_buffers
FROM cics_files
GROUP BY fileName
ORDER BY total_buffers DESC;
```

---

## 📌 Notas adicionales

* El parser está diseñado para tolerar formatos inconsistentes del reporte CICS
* Se aplican normalizaciones para evitar errores de conversión
* Algunos campos pueden venir vacíos dependiendo del entorno CICS

---

## 👨‍💻 Autor

Proyecto desarrollado para análisis y auditoría de entornos CICS.

---
