import os
import json
import smtplib
import shutil
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date, datetime
from pathlib import Path
from funciones import *

# =========================
# CONFIGURACIÓN
# =========================
PROJECT_ROOT = Path(__file__).parent

# Intenta leer las rutas desde la tabla cics_configuracion.
# Si la tabla no existe o la clave está vacía, usa los valores por defecto locales.
def _resolver_ruta(clave: str) -> Path:
    from funciones import asegurar_tabla_cics_configuracion, obtener_configuracion

    defaults_por_clave = {
        "ruta_entrada": "ENTRADA",
        "ruta_salida": "SALIDA",
    }

    if clave not in defaults_por_clave:
        raise ValueError(
            f"Clave de configuración no soportada: {clave}. "
            f"Use una de: {', '.join(defaults_por_clave.keys())}"
        )

    try:
        asegurar_tabla_cics_configuracion()
    except Exception:
        pass

    default_relativo = defaults_por_clave[clave]
    valor = obtener_configuracion(clave, default=default_relativo)
    if valor is None or not str(valor).strip():
        valor = default_relativo

    ruta = Path(valor)
    # Si la ruta es relativa, se ancla al directorio del proyecto
    if not ruta.is_absolute():
        ruta = PROJECT_ROOT / ruta
    return ruta

DIRECTORIO_REPORTES = _resolver_ruta("ruta_entrada")
DIRECTORIO_SALIDA   = _resolver_ruta("ruta_salida")

DIRECTORIO_SALIDA.mkdir(exist_ok=True)


def _config_bool(clave: str, default: bool = False) -> bool:
    valor = obtener_configuracion(clave, default="true" if default else "false")
    if valor is None:
        return default
    return str(valor).strip().lower() in {"1", "true", "t", "si", "sí", "yes", "y"}


def _config_lista_correos(clave: str) -> list[str]:
    valor = obtener_configuracion(clave, default="")
    if valor is None:
        return []
    bruto = str(valor).replace(";", ",")
    return [x.strip() for x in bruto.split(",") if x.strip()]


def _enviar_notificacion_fin_proceso(resumen: dict) -> None:
    destinatarios = _config_lista_correos("correo_notificacion_cics")
    if not destinatarios:
        print("[WARN] No hay destinatarios en correo_notificacion_cics. Se omite notificacion por correo.")
        return

    smtp_host = os.getenv("CICS_SMTP_HOST", "10.1.1.144")
    smtp_port = int(os.getenv("CICS_SMTP_PORT", "25"))
    remitente = os.getenv("CICS_EMAIL_REMITENTE", "controlcodigo@bi.com.gt")

    asunto = (
        f"Depuracion CICS finalizada | {resumen.get('fin', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}"
    )

    estado_global = "sin novedades"
    if resumen.get("errores", 0) > 0:
        estado_global = "finalizo con errores"
    elif resumen.get("procesadas", 0) > 0:
        estado_global = "finalizo correctamente"
    elif resumen.get("omitidas", 0) > 0:
        estado_global = "no proceso nuevas carpetas porque estaban omitidas"

    lineas = [
        "La depuracion de CICS ha concluido.",
        f"Estado general: {estado_global}.",
        "",
        "Resumen de ejecucion:",
        f"- Inicio: {resumen.get('inicio', '')}",
        f"- Fin: {resumen.get('fin', '')}",
        f"- Modo: {resumen.get('modo', '')}",
        f"- Carpeta entrada: {resumen.get('directorio_reportes', '')}",
        f"- Carpeta salida: {resumen.get('directorio_salida', '')}",
        f"- Carpetas consideradas: {resumen.get('carpetas_consideradas', 0)}",
        f"- Carpetas procesadas: {resumen.get('procesadas', 0)}",
        f"- Carpetas omitidas: {resumen.get('omitidas', 0)}",
        f"- Carpetas sin archivos validos: {resumen.get('sin_validos', 0)}",
        f"- Errores: {resumen.get('errores', 0)}",
        "",
        "Detalle por carpeta:",
    ]

    detalle = resumen.get("detalle", [])
    if not detalle:
        lineas.append("- Sin detalle")
    else:
        for item in detalle:
            lineas.append(
                f"- {item.get('fecha', '')} | {item.get('carpeta', '')} | {item.get('estado', '')} | {item.get('mensaje', '')}"
            )

    cuerpo = "\n".join(lineas)

    # Formato MIME, equivalente al patrón usado en el proyecto Django.
    mensaje = MIMEMultipart()
    mensaje["From"] = remitente
    mensaje["To"] = ", ".join(destinatarios)
    mensaje["Subject"] = asunto
    mensaje.attach(MIMEText(cuerpo, "plain", "utf-8"))

    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
        code, response = server.ehlo()
        print(f"[INFO] SMTP EHLO -> codigo={code} respuesta={response!r}")
        rechazados = server.sendmail(remitente, destinatarios, mensaje.as_string())

    if rechazados:
        raise RuntimeError(f"Destinatarios rechazados por SMTP: {rechazados}")

    print(
        f"[OK] Correo de notificacion aceptado por SMTP {smtp_host}:{smtp_port} "
        f"para: {', '.join(destinatarios)}"
    )


def _limpiar_contenido_directorio(directorio: Path) -> tuple[int, int]:
    """
    Elimina el contenido interno del directorio sin borrar el directorio raíz.
    Retorna una tupla (eliminados, errores).
    """
    eliminados = 0
    errores = 0

    if not directorio.exists():
        return eliminados, errores

    for item in directorio.iterdir():
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            eliminados += 1
        except Exception as e:
            errores += 1
            print(f"[WARN] No se pudo eliminar {item}: {e}")

    return eliminados, errores


def _limpiar_entrada_salida_al_final() -> None:
    total_eliminados = 0
    total_errores = 0

    for ruta in [DIRECTORIO_REPORTES, DIRECTORIO_SALIDA]:
        eliminados, errores = _limpiar_contenido_directorio(ruta)
        total_eliminados += eliminados
        total_errores += errores
        print(
            f"[INFO] Limpieza de {ruta}: eliminados={eliminados}, errores={errores}"
        )

    if total_errores == 0:
        print(
            f"[OK] Limpieza final completada. Elementos eliminados: {total_eliminados}"
        )
    else:
        print(
            f"[WARN] Limpieza final completada con errores. "
            f"Eliminados={total_eliminados}, errores={total_errores}"
        )


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
        return {
            "estado": "SIN_VALIDOS",
            "mensaje": "sin archivos validos",
            "archivos_validos": 0,
        }

    fecha_encabezado = fecha_carpeta
    print(f"Fecha validada desde encabezados: {fecha_encabezado} (archivos válidos: {len(archivos_validos)})")

    if carpeta_ya_procesada(fecha_carpeta, nombre_carpeta, archivos_validos):
        print(f"Carpeta ya cargada: {nombre_carpeta}. Se omite completamente.")
        return {
            "estado": "OMITIDA",
            "mensaje": "carpeta ya cargada",
            "archivos_validos": len(archivos_validos),
        }

    cantidad_registros = validar_carga_fecha(fecha_encabezado)
    if cantidad_registros > 0:
        print(
            f"Ya existen {cantidad_registros} registros en base de datos "
            f"para la fecha {fecha_encabezado}. Se omite completamente esta carpeta."
        )
        return {
            "estado": "OMITIDA",
            "mensaje": f"fecha ya cargada ({cantidad_registros} registros)",
            "archivos_validos": len(archivos_validos),
        }

    generar_json_desde_txt(ruta_carpeta, directorio_salida_fecha, archivos_permitidos=archivos_validos)
    insertar_bd_desde_json(directorio_salida_fecha, fecha_encabezado, archivos_permitidos=archivos_validos)
    for nombre_archivo in archivos_validos:
        registrar_carpeta_procesada(fecha_encabezado, nombre_carpeta, nombre_archivo)

    print(f"[OK] Carpeta procesada correctamente: {nombre_carpeta}")
    return {
        "estado": "PROCESADA",
        "mensaje": "procesamiento completado",
        "archivos_validos": len(archivos_validos),
    }


def resumir_error_carga(error: Exception) -> str:
    mensaje = " ".join(str(error).split())
    if not mensaje:
        return "error no especificado"
    return mensaje[:255]


def main():
    inicio = datetime.now()
    resumen = {
        "inicio": inicio.strftime("%Y-%m-%d %H:%M:%S"),
        "fin": "",
        "modo": "",
        "directorio_reportes": str(DIRECTORIO_REPORTES),
        "directorio_salida": str(DIRECTORIO_SALIDA),
        "carpetas_consideradas": 0,
        "procesadas": 0,
        "omitidas": 0,
        "sin_validos": 0,
        "errores": 0,
        "detalle": [],
    }

    if not DIRECTORIO_REPORTES.exists():
        raise FileNotFoundError(f"No existe el directorio: {DIRECTORIO_REPORTES}")

    # Asegura defaults de configuración (incluye analisis_completo).
    asegurar_tabla_cics_configuracion()

    carpetas_fecha = obtener_carpetas_fecha_ordenadas(DIRECTORIO_REPORTES)

    if not carpetas_fecha:
        print("No se encontraron carpetas con formato YYYY-MM-DD en ENTRADA.")
        return

    analisis_completo = _config_bool("analisis_completo", default=False)
    if analisis_completo:
        resumen["modo"] = "analisis_completo=true"
        print("Modo analisis_completo=true: se procesaran todas las carpetas disponibles.")
    else:
        hoy = date.today().isoformat()
        carpetas_fecha = [par for par in carpetas_fecha if par[0] <= hoy][:10]
        resumen["modo"] = "analisis_completo=false"
        print(
            "Modo analisis_completo=false: "
            "se procesaran solo las ultimas 10 fechas desde hoy. "
            f"Carpetas seleccionadas: {len(carpetas_fecha)}"
        )

    resumen["carpetas_consideradas"] = len(carpetas_fecha)

    for fecha_carpeta, ruta_carpeta in carpetas_fecha:
        try:
            resultado = procesar_carpeta_fecha(fecha_carpeta, ruta_carpeta)
            estado = (resultado or {}).get("estado", "DESCONOCIDO")
            mensaje = (resultado or {}).get("mensaje", "sin mensaje")
            resumen["detalle"].append(
                {
                    "fecha": fecha_carpeta,
                    "carpeta": ruta_carpeta.name,
                    "estado": estado,
                    "mensaje": mensaje,
                }
            )

            if estado == "PROCESADA":
                resumen["procesadas"] += 1
            elif estado == "OMITIDA":
                resumen["omitidas"] += 1
            elif estado == "SIN_VALIDOS":
                resumen["sin_validos"] += 1
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
            resumen["errores"] += 1
            resumen["detalle"].append(
                {
                    "fecha": fecha_carpeta,
                    "carpeta": ruta_carpeta.name,
                    "estado": "ERROR",
                    "mensaje": resumir_error_carga(e),
                }
            )
            print(f"[ERROR] Error procesando carpeta {ruta_carpeta.name}: {e}\n")

    resumen["fin"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return resumen


if __name__ == "__main__":
    print("\n\n\n****************************************")
    print(f"Proceso iniciado el dia {date.today().isoformat()} a las {datetime.now().strftime('%H:%M:%S')} horas\n")
    resumen_final = None
    error_global = None
    try:
        resumen_final = main()
    except Exception as e:
        error_global = e
        resumen_final = {
            "inicio": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "fin": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "modo": "error_en_arranque",
            "directorio_reportes": str(DIRECTORIO_REPORTES),
            "directorio_salida": str(DIRECTORIO_SALIDA),
            "carpetas_consideradas": 0,
            "procesadas": 0,
            "omitidas": 0,
            "sin_validos": 0,
            "errores": 1,
            "detalle": [
                {
                    "fecha": "",
                    "carpeta": "",
                    "estado": "ERROR",
                    "mensaje": resumir_error_carga(e),
                }
            ],
        }
    finally:
        try:
            _enviar_notificacion_fin_proceso(resumen_final or {})
        except Exception as mail_error:
            print(f"[WARN] No se pudo enviar correo de notificacion: {mail_error}")

        limpiar_al_final = _config_bool("limpiar_al_final", default=True)
        if limpiar_al_final:
            try:
                _limpiar_entrada_salida_al_final()
            except Exception as cleanup_error:
                print(f"[WARN] Ocurrio un error durante la limpieza final: {cleanup_error}")
        else:
            print("[INFO] limpiar_al_final=false. Se omite limpieza de ENTRADA y SALIDA.")

    if error_global is not None:
        raise error_global

    print(f"\nProceso finalizado el dia {date.today().isoformat()} a las {datetime.now().strftime('%H:%M:%S')} horas\n")
    print("****************************************\n\n\n")