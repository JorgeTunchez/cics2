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


def normalizar_archivos_permitidos(archivos_permitidos: list[str] | None) -> set[str] | None:
    if archivos_permitidos is None:
        return None
    return {str(nombre).strip().upper() for nombre in archivos_permitidos if str(nombre).strip()}


def listar_archivos_txt(directorio_fecha: Path, archivos_permitidos: list[str] | None = None) -> list[Path]:
    permitidos = normalizar_archivos_permitidos(archivos_permitidos)
    archivos = sorted(
        [p for p in directorio_fecha.iterdir() if p.is_file() and p.suffix.upper() == ".TXT"]
    )
    if permitidos is None:
        return archivos
    return [p for p in archivos if p.name.upper() in permitidos]


def listar_archivos_json(directorio_salida_fecha: Path, archivos_permitidos: list[str] | None = None) -> list[Path]:
    permitidos = normalizar_archivos_permitidos(archivos_permitidos)
    archivos_json = sorted(
        [p for p in directorio_salida_fecha.iterdir() if p.is_file() and p.suffix.upper() == ".JSON"]
    )
    if permitidos is None:
        return archivos_json

    filtrados = []
    for json_path in archivos_json:
        nombre_txt = json_path.name.upper().replace(".JSON", ".TXT")
        if nombre_txt in permitidos:
            filtrados.append(json_path)
    return filtrados


def generar_json_desde_txt(
    directorio_fecha: Path,
    directorio_salida_fecha: Path,
    archivos_permitidos: list[str] | None = None,
):
    """
    Lee todos los TXT de una carpeta de fecha y genera un JSON por cada uno
    dentro de su carpeta correspondiente en SALIDA.
    """
    if not directorio_fecha.exists():
        raise FileNotFoundError(f"No existe el directorio: {directorio_fecha}")

    directorio_salida_fecha.mkdir(parents=True, exist_ok=True)

    archivos = listar_archivos_txt(directorio_fecha, archivos_permitidos=archivos_permitidos)

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


def insertar_bd_desde_json(
    directorio_salida_fecha: Path,
    fecha_actual: str,
    archivos_permitidos: list[str] | None = None,
):
    """
    Recorre la carpeta de JSON de una fecha específica y manda a BD.
    """
    archivos_json = listar_archivos_json(directorio_salida_fecha, archivos_permitidos=archivos_permitidos)

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


def backfill_statistics_desde_json(
    directorio_salida_fecha: Path,
    fecha_actual: str,
    archivos_permitidos: list[str] | None = None,
):
    """
    Inserta Statistics faltantes desde JSON ya generados, sin reintentar
    la carga completa de tablas con restricciones únicas.
    """
    if not directorio_salida_fecha.exists():
        print("No existe carpeta de SALIDA para backfill de Statistics.")
        return

    archivos_json = listar_archivos_json(directorio_salida_fecha, archivos_permitidos=archivos_permitidos)

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


def backfill_trace_status_desde_json(
    directorio_salida_fecha: Path,
    fecha_actual: str,
    archivos_permitidos: list[str] | None = None,
):
    """
    Inserta Trace Status faltantes desde JSON ya generados, sin reintentar
    la carga completa de tablas con restricciones únicas.
    """
    if not directorio_salida_fecha.exists():
        print("No existe carpeta de SALIDA para backfill de Trace Status.")
        return

    archivos_json = listar_archivos_json(directorio_salida_fecha, archivos_permitidos=archivos_permitidos)

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


def backfill_transaction_manager_desde_json(
    directorio_salida_fecha: Path,
    fecha_actual: str,
    archivos_permitidos: list[str] | None = None,
):
    """
    Inserta Transaction Manager faltantes desde JSON ya generados, sin reintentar
    la carga completa de tablas con restricciones únicas.
    """
    if not directorio_salida_fecha.exists():
        print("No existe carpeta de SALIDA para backfill de Transaction Manager.")
        return

    archivos_json = listar_archivos_json(directorio_salida_fecha, archivos_permitidos=archivos_permitidos)

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


def backfill_dispatcher_desde_json(
    directorio_salida_fecha: Path,
    fecha_actual: str,
    archivos_permitidos: list[str] | None = None,
):
    """
    Inserta Dispatcher faltante desde JSON ya generados.
    """
    if not directorio_salida_fecha.exists():
        print("No existe carpeta de SALIDA para backfill de Dispatcher.")
        return

    archivos_json = listar_archivos_json(directorio_salida_fecha, archivos_permitidos=archivos_permitidos)

    if not archivos_json:
        print("No hay archivos JSON para backfill de Dispatcher.")
        return

    inserted_total = 0

    for json_path in archivos_json:
        nombre_archivo_json = json_path.name.upper()

        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            nombre_txt = nombre_archivo_json.replace(".JSON", ".TXT")
            inserted = insertar_dispatcher_si_falta(fecha_actual, nombre_txt, data)
            inserted_total += inserted

        except Exception as e:
            print(f"  [ERROR] Error backfilleando Dispatcher desde {nombre_archivo_json}: {e}\n")
            raise

    print(f"Backfill de Dispatcher completado. Registros insertados: {inserted_total}")


def backfill_storage_program_subpool_desde_json(
    directorio_salida_fecha: Path,
    fecha_actual: str,
    archivos_permitidos: list[str] | None = None,
):
    """
    Inserta Storage - Program Subpools faltantes desde JSON ya generados.
    """
    if not directorio_salida_fecha.exists():
        print("No existe carpeta de SALIDA para backfill de Storage - Program Subpools.")
        return

    archivos_json = listar_archivos_json(directorio_salida_fecha, archivos_permitidos=archivos_permitidos)

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


def backfill_storage_task_subpool_desde_json(
    directorio_salida_fecha: Path,
    fecha_actual: str,
    archivos_permitidos: list[str] | None = None,
):
    """
    Inserta Storage - Task Subpools faltantes desde JSON ya generados.
    """
    if not directorio_salida_fecha.exists():
        print("No existe carpeta de SALIDA para backfill de Storage - Task Subpools.")
        return

    archivos_json = listar_archivos_json(directorio_salida_fecha, archivos_permitidos=archivos_permitidos)

    if not archivos_json:
        print("No hay archivos JSON para backfill de Storage - Task Subpools.")
        return

    inserted_total = 0

    for json_path in archivos_json:
        nombre_archivo_json = json_path.name.upper()

        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            nombre_txt = nombre_archivo_json.replace(".JSON", ".TXT")
            inserted = insertar_storage_task_subpool_si_falta(fecha_actual, nombre_txt, data)
            inserted_total += inserted

        except Exception as e:
            print(f"  [ERROR] Error backfilleando Storage - Task Subpools desde {nombre_archivo_json}: {e}\n")
            raise

    print(f"Backfill de Storage - Task Subpools completado. Registros insertados: {inserted_total}")


def backfill_data_tables_requests_desde_json(
    directorio_salida_fecha: Path,
    fecha_actual: str,
    archivos_permitidos: list[str] | None = None,
):
    """
    Inserta Data Tables - Requests faltantes desde JSON ya generados.
    """
    if not directorio_salida_fecha.exists():
        print("No existe carpeta de SALIDA para backfill de Data Tables - Requests.")
        return

    archivos_json = listar_archivos_json(directorio_salida_fecha, archivos_permitidos=archivos_permitidos)

    if not archivos_json:
        print("No hay archivos JSON para backfill de Data Tables - Requests.")
        return

    inserted_total = 0

    for json_path in archivos_json:
        nombre_archivo_json = json_path.name.upper()

        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            nombre_txt = nombre_archivo_json.replace(".JSON", ".TXT")
            inserted = insertar_data_tables_requests_si_falta(fecha_actual, nombre_txt, data)
            inserted_total += inserted

        except Exception as e:
            print(f"  [ERROR] Error backfilleando Data Tables - Requests desde {nombre_archivo_json}: {e}\n")
            raise

    print(f"Backfill de Data Tables - Requests completado. Registros insertados: {inserted_total}")


def backfill_data_tables_storage_desde_json(
    directorio_salida_fecha: Path,
    fecha_actual: str,
    archivos_permitidos: list[str] | None = None,
):
    """
    Inserta Data Tables - Storage faltantes desde JSON ya generados.
    """
    if not directorio_salida_fecha.exists():
        print("No existe carpeta de SALIDA para backfill de Data Tables - Storage.")
        return

    archivos_json = listar_archivos_json(directorio_salida_fecha, archivos_permitidos=archivos_permitidos)

    if not archivos_json:
        print("No hay archivos JSON para backfill de Data Tables - Storage.")
        return

    inserted_total = 0

    for json_path in archivos_json:
        nombre_archivo_json = json_path.name.upper()

        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            nombre_txt = nombre_archivo_json.replace(".JSON", ".TXT")
            inserted = insertar_data_tables_storage_si_falta(fecha_actual, nombre_txt, data)
            inserted_total += inserted

        except Exception as e:
            print(f"  [ERROR] Error backfilleando Data Tables - Storage desde {nombre_archivo_json}: {e}\n")
            raise

    print(f"Backfill de Data Tables - Storage completado. Registros insertados: {inserted_total}")


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
    archivos_txt = sorted(
        [p.name.upper() for p in ruta_carpeta.iterdir() if p.is_file() and p.suffix.upper() == ".TXT"]
    )
    print(f"\nProcesando carpeta: {nombre_carpeta}")

    validar_cantidad_archivos(ruta_carpeta, 6)

    archivos_validos = []
    for archivo_path in listar_archivos_txt(ruta_carpeta):
        nombre_archivo = archivo_path.name.upper()
        try:
            fecha_archivo = obtener_fecha_encabezado(archivo_path, fecha_esperada=fecha_carpeta)
        except Exception as e:
            registrar_estado_carpeta(
                fecha_carpeta,
                nombre_carpeta,
                "NO PROCESADA",
                resumir_error_carga(e),
                nombre_archivo=nombre_archivo,
            )
            print(f"  [WARN] {nombre_archivo} no será procesado: {e}")
            continue

        if fecha_archivo != fecha_carpeta:
            motivo = f"fecha {fecha_archivo} no coincide con carpeta {fecha_carpeta}"
            registrar_estado_carpeta(
                fecha_carpeta,
                nombre_carpeta,
                "NO PROCESADA",
                motivo,
                nombre_archivo=nombre_archivo,
            )
            print(f"  [WARN] {nombre_archivo} no será procesado: {motivo}")
            continue

        archivos_validos.append(nombre_archivo)

    if not archivos_validos:
        print(f"[WARN] Ningún archivo válido para procesar en {nombre_carpeta}.")
        return

    fecha_encabezado = fecha_carpeta
    print(f"Fecha validada desde encabezados: {fecha_encabezado} (archivos válidos: {len(archivos_validos)})")

    if carpeta_ya_procesada(fecha_carpeta, nombre_carpeta, archivos_validos):
        print(f"Carpeta ya cargada: {nombre_carpeta}. Se omite completamente.")
        return

    cantidad_registros = validar_carga_fecha(fecha_encabezado)
    if cantidad_registros > 0:
        print(
            f"Ya existen {cantidad_registros} registros en base de datos "
            f"para la fecha {fecha_encabezado}. Se omite completamente esta carpeta."
        )
        return

    generar_json_desde_txt(ruta_carpeta, directorio_salida_fecha, archivos_permitidos=archivos_validos)
    insertar_bd_desde_json(directorio_salida_fecha, fecha_encabezado, archivos_permitidos=archivos_validos)
    for nombre_archivo in archivos_validos:
        registrar_carpeta_procesada(fecha_encabezado, nombre_carpeta, nombre_archivo)

    print(f"[OK] Carpeta procesada correctamente: {nombre_carpeta}")


def resumir_error_carga(error: Exception) -> str:
    mensaje = " ".join(str(error).split())
    if not mensaje:
        return "error no especificado"
    return mensaje[:255]


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
            archivos_txt = sorted(
                [p.name.upper() for p in ruta_carpeta.iterdir() if p.is_file() and p.suffix.upper() == ".TXT"]
            )
            for nombre_archivo in archivos_txt:
                registrar_estado_carpeta(
                    fecha_carpeta,
                    ruta_carpeta.name,
                    "NO PROCESADA",
                    resumir_error_carga(e),
                    nombre_archivo=nombre_archivo,
                )
            print(f"[ERROR] Error procesando carpeta {ruta_carpeta.name}: {e}\n")


if __name__ == "__main__":
    print("\n\n\n****************************************")
    print(f"Proceso iniciado el dia {date.today().isoformat()} a las {datetime.now().strftime('%H:%M:%S')} horas\n")
    main()
    print(f"\nProceso finalizado el dia {date.today().isoformat()} a las {datetime.now().strftime('%H:%M:%S')} horas\n")
    print("****************************************\n\n\n")