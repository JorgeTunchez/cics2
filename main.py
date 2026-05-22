import os
import json
from datetime import date, datetime
from pathlib import Path
from funciones import *

# =========================
# CONFIGURACIÓN
# =========================
PROJECT_ROOT = Path(__file__).parent
DIRECTORIO_REPORTES = PROJECT_ROOT / "ENTRADA"
DIRECTORIO_SALIDA = PROJECT_ROOT / "SALIDA"

DIRECTORIO_SALIDA.mkdir(exist_ok=True)


def generar_json_desde_txt(directorio_fecha: Path, directorio_salida_fecha: Path):
    """
    Lee todos los TXT de una carpeta de fecha y genera un JSON por cada uno
    dentro de su carpeta correspondiente en SALIDA.
    """
    if not directorio_fecha.exists():
        raise FileNotFoundError(f"No existe el directorio: {directorio_fecha}")

    directorio_salida_fecha.mkdir(parents=True, exist_ok=True)

    archivos = sorted(
        [p for p in directorio_fecha.iterdir() if p.is_file() and p.suffix.upper() == ".TXT"]
    )

    for archivo_path in archivos:
        archivo = archivo_path.name.upper()
        print(f"Archivo en análisis: {archivo}")

        try:
            data = parse_cicsadm_lite(archivo_path)

            nombre_json = archivo.replace(".TXT", ".JSON")
            salida_path = directorio_salida_fecha / nombre_json

            salida_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )

            print(f"  [OK] Segmentos detectados: {len(data)}")
            print(f"  [OK] JSON generado: {salida_path}\n")

        except Exception as e:
            print(f"  [ERROR] Error procesando {archivo}: {e}\n")


def insertar_bd_desde_json(directorio_salida_fecha: Path, fecha_actual: str):
    """
    Recorre la carpeta de JSON de una fecha específica y manda a BD.
    """
    archivos_json = sorted(
        [p for p in directorio_salida_fecha.iterdir() if p.is_file() and p.suffix.upper() == ".JSON"]
    )

    if not archivos_json:
        print("No hay archivos JSON para insertar en BD.")
        return

    print("========================================")
    print("Insertando en BD desde JSON generados...")
    print("========================================")

    for json_path in archivos_json:
        nombre_archivo_json = json_path.name.upper()
        print(f"Insertando desde: {nombre_archivo_json}")

        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            nombre_txt = nombre_archivo_json.replace(".JSON", ".TXT")
            insertarValidacionSistema(fecha_actual, nombre_txt, data)

        except Exception as e:
            print(f"  [ERROR] Error insertando desde {nombre_archivo_json}: {e}\n")
            raise


def backfill_statistics_desde_json(directorio_salida_fecha: Path, fecha_actual: str):
    """
    Inserta Statistics faltantes desde JSON ya generados, sin reintentar
    la carga completa de tablas con restricciones únicas.
    """
    if not directorio_salida_fecha.exists():
        print("No existe carpeta de SALIDA para backfill de Statistics.")
        return

    archivos_json = sorted(
        [p for p in directorio_salida_fecha.iterdir() if p.is_file() and p.suffix.upper() == ".JSON"]
    )

    if not archivos_json:
        print("No hay archivos JSON para backfill de Statistics.")
        return

    inserted_total = 0

    for json_path in archivos_json:
        nombre_archivo_json = json_path.name.upper()

        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            nombre_txt = nombre_archivo_json.replace(".JSON", ".TXT")
            inserted = insertar_statistics_si_falta(fecha_actual, nombre_txt, data)
            inserted_total += inserted

        except Exception as e:
            print(f"  [ERROR] Error backfilleando Statistics desde {nombre_archivo_json}: {e}\n")
            raise

    print(f"Backfill de Statistics completado. Registros insertados: {inserted_total}")


def backfill_trace_status_desde_json(directorio_salida_fecha: Path, fecha_actual: str):
    """
    Inserta Trace Status faltantes desde JSON ya generados, sin reintentar
    la carga completa de tablas con restricciones únicas.
    """
    if not directorio_salida_fecha.exists():
        print("No existe carpeta de SALIDA para backfill de Trace Status.")
        return

    archivos_json = sorted(
        [p for p in directorio_salida_fecha.iterdir() if p.is_file() and p.suffix.upper() == ".JSON"]
    )

    if not archivos_json:
        print("No hay archivos JSON para backfill de Trace Status.")
        return

    inserted_total = 0

    for json_path in archivos_json:
        nombre_archivo_json = json_path.name.upper()

        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            nombre_txt = nombre_archivo_json.replace(".JSON", ".TXT")
            inserted = insertar_trace_status_si_falta(fecha_actual, nombre_txt, data)
            inserted_total += inserted

        except Exception as e:
            print(f"  [ERROR] Error backfilleando Trace Status desde {nombre_archivo_json}: {e}\n")
            raise

    print(f"Backfill de Trace Status completado. Registros insertados: {inserted_total}")


def backfill_transaction_manager_desde_json(directorio_salida_fecha: Path, fecha_actual: str):
    """
    Inserta Transaction Manager faltantes desde JSON ya generados, sin reintentar
    la carga completa de tablas con restricciones únicas.
    """
    if not directorio_salida_fecha.exists():
        print("No existe carpeta de SALIDA para backfill de Transaction Manager.")
        return

    archivos_json = sorted(
        [p for p in directorio_salida_fecha.iterdir() if p.is_file() and p.suffix.upper() == ".JSON"]
    )

    if not archivos_json:
        print("No hay archivos JSON para backfill de Transaction Manager.")
        return

    inserted_total = 0

    for json_path in archivos_json:
        nombre_archivo_json = json_path.name.upper()

        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            nombre_txt = nombre_archivo_json.replace(".JSON", ".TXT")
            inserted = insertar_transaction_manager_si_falta(fecha_actual, nombre_txt, data)
            inserted_total += inserted

        except Exception as e:
            print(f"  [ERROR] Error backfilleando Transaction Manager desde {nombre_archivo_json}: {e}\n")
            raise

    print(f"Backfill de Transaction Manager completado. Registros insertados: {inserted_total}")


def backfill_storage_program_subpool_desde_json(directorio_salida_fecha: Path, fecha_actual: str):
    """
    Inserta Storage - Program Subpools faltantes desde JSON ya generados.
    """
    if not directorio_salida_fecha.exists():
        print("No existe carpeta de SALIDA para backfill de Storage - Program Subpools.")
        return

    archivos_json = sorted(
        [p for p in directorio_salida_fecha.iterdir() if p.is_file() and p.suffix.upper() == ".JSON"]
    )

    if not archivos_json:
        print("No hay archivos JSON para backfill de Storage - Program Subpools.")
        return

    inserted_total = 0

    for json_path in archivos_json:
        nombre_archivo_json = json_path.name.upper()

        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            nombre_txt = nombre_archivo_json.replace(".JSON", ".TXT")
            inserted = insertar_storage_program_subpool_si_falta(fecha_actual, nombre_txt, data)
            inserted_total += inserted

        except Exception as e:
            print(f"  [ERROR] Error backfilleando Storage - Program Subpools desde {nombre_archivo_json}: {e}\n")
            raise

    print(f"Backfill de Storage - Program Subpools completado. Registros insertados: {inserted_total}")


def procesar_carpeta_fecha(fecha_carpeta: str, ruta_carpeta: Path):
    """
    Procesa una carpeta de fecha:
    - valida cantidad de archivos
    - valida fecha única en encabezados
    - valida que no exista ya la carga
    - genera JSON
    - inserta a BD
    - registra carpeta procesada
    """
    nombre_carpeta = ruta_carpeta.name
    directorio_salida_fecha = DIRECTORIO_SALIDA / nombre_carpeta
    print(f"\nProcesando carpeta: {nombre_carpeta}")

    if carpeta_ya_procesada(fecha_carpeta, nombre_carpeta):
        print(f"Carpeta ya procesada anteriormente: {nombre_carpeta}. Se omite.")
        # Regenerar JSON para incluir segmentos nuevos soportados por parser.
        generar_json_desde_txt(ruta_carpeta, directorio_salida_fecha)
        backfill_statistics_desde_json(directorio_salida_fecha, fecha_carpeta)
        backfill_trace_status_desde_json(directorio_salida_fecha, fecha_carpeta)
        backfill_transaction_manager_desde_json(directorio_salida_fecha, fecha_carpeta)
        backfill_storage_program_subpool_desde_json(directorio_salida_fecha, fecha_carpeta)
        return

    validar_cantidad_archivos(ruta_carpeta, 6)

    fecha_encabezado = validar_fecha_unica_archivos(ruta_carpeta)
    print(f"Fecha validada desde encabezados: {fecha_encabezado}")

    # Validación adicional: el nombre de carpeta debe coincidir con la fecha del encabezado
    if fecha_encabezado != fecha_carpeta:
        raise ValueError(
            f"La carpeta '{nombre_carpeta}' indica fecha {fecha_carpeta}, "
            f"pero los archivos contienen fecha {fecha_encabezado}."
        )

    cantidad_registros = validar_carga_fecha(fecha_encabezado)
    if cantidad_registros > 0:
        print(
            f"Ya existen {cantidad_registros} registros en base de datos "
            f"para la fecha {fecha_encabezado}. No se realizará la carga de esta carpeta."
        )
        # Regenerar JSON para incluir segmentos nuevos soportados por parser.
        generar_json_desde_txt(ruta_carpeta, directorio_salida_fecha)
        backfill_statistics_desde_json(directorio_salida_fecha, fecha_encabezado)
        backfill_trace_status_desde_json(directorio_salida_fecha, fecha_encabezado)
        backfill_transaction_manager_desde_json(directorio_salida_fecha, fecha_encabezado)
        backfill_storage_program_subpool_desde_json(directorio_salida_fecha, fecha_encabezado)
        return

    generar_json_desde_txt(ruta_carpeta, directorio_salida_fecha)
    insertar_bd_desde_json(directorio_salida_fecha, fecha_encabezado)
    registrar_carpeta_procesada(fecha_encabezado, nombre_carpeta)

    print(f"[OK] Carpeta procesada correctamente: {nombre_carpeta}")


def main():
    if not DIRECTORIO_REPORTES.exists():
        raise FileNotFoundError(f"No existe el directorio: {DIRECTORIO_REPORTES}")

    carpetas_fecha = obtener_carpetas_fecha_ordenadas(DIRECTORIO_REPORTES)

    if not carpetas_fecha:
        print("No se encontraron carpetas con formato YYYY-MM-DD en ENTRADA.")
        return

    for fecha_carpeta, ruta_carpeta in carpetas_fecha:
        try:
            procesar_carpeta_fecha(fecha_carpeta, ruta_carpeta)
        except Exception as e:
            print(f"[ERROR] Error procesando carpeta {ruta_carpeta.name}: {e}\n")


if __name__ == "__main__":
    print("\n\n\n****************************************")
    print(f"Proceso iniciado el dia {date.today().isoformat()} a las {datetime.now().strftime('%H:%M:%S')} horas\n")
    main()
    print(f"\nProceso finalizado el dia {date.today().isoformat()} a las {datetime.now().strftime('%H:%M:%S')} horas\n")
    print("****************************************\n\n\n")