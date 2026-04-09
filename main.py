import os
import json
import datetime
from pathlib import Path
#from funciones_old import *
from funciones import *

fechaActual = datetime.date.today().isoformat()

# =========================
# CONFIGURACIÓN
# =========================
PROJECT_ROOT = Path(__file__).parent
DIRECTORIO_REPORTES = PROJECT_ROOT / "ENTRADA"
DIRECTORIO_SALIDA = PROJECT_ROOT / "SALIDA"

DIRECTORIO_SALIDA.mkdir(exist_ok=True)


def generar_json_desde_txt():
    """Lee todos los TXT y genera un JSON por cada uno en JSON_SALIDA."""
    if not DIRECTORIO_REPORTES.exists():
        raise FileNotFoundError(f"No existe el directorio: {DIRECTORIO_REPORTES}")

    archivos = [p for p in DIRECTORIO_REPORTES.iterdir() if p.is_file() and p.suffix.upper() == ".TXT"]

    for archivo_path in archivos:
        archivo = archivo_path.name.upper()
        print(f"Archivo en análisis: {archivo}")

        try:
            data = parse_cicsadm_lite(archivo_path)

            nombre_json = archivo.replace(".TXT", ".JSON")
            salida_path = DIRECTORIO_SALIDA / nombre_json

            salida_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )

            print(f"  ✔ Segmentos detectados: {len(data)}")
            print(f"  ✔ JSON generado: {salida_path}\n")

        except Exception as e:
            print(f"  ❌ Error procesando {archivo}: {e}\n")


def insertar_bd_desde_json():
    """Recorre JSON_SALIDA y manda a BD solo (archivos, segmento, programs, transactions)."""
    archivos_json = [p for p in DIRECTORIO_SALIDA.iterdir() if p.is_file() and p.suffix.upper() == ".JSON"]

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

            # tu función espera nombreArchivo, puede ser TXT o JSON
            # aquí usamos el nombre base como TXT para mantener consistencia
            nombre_txt = nombre_archivo_json.replace(".JSON", ".TXT")
            insertarValidacionSistema(fechaActual, nombre_txt, data)

        except Exception as e:
            print(f"  ❌ Error insertando desde {nombre_archivo_json}: {e}\n")



def main():
    # Si quieres reactivar validación por fecha, pon tu función aquí.
    countProgramas, countTransacciones, cantidadRegFechaActual = validarCargaFecha(fechaActual)
    if cantidadRegFechaActual != 0:
        print(f"Registros existentes para la fecha {fechaActual}: PROGRAMAS = {countProgramas}, TRANSACCIONES = {countTransacciones}, TOTAL = {cantidadRegFechaActual}")
        return

    generar_json_desde_txt()
    insertar_bd_desde_json()


if __name__ == "__main__":
    print("\n\n\n****************************************")
    print(f"Proceso iniciado el dia {datetime.date.today().isoformat()} a las {datetime.datetime.now().strftime('%H:%M:%S')} horas\n")
    main() # Ejecuta el proceso principal
    print(f"\nProceso finalizado el dia {datetime.date.today().isoformat()} a las {datetime.datetime.now().strftime('%H:%M:%S')} horas\n")
    print("****************************************\n\n\n")

