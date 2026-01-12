import os
import json
import datetime
import json
from pathlib import Path
from funciones import *     

fechaActual = datetime.date.today().isoformat()


# =========================
# CONFIGURACIÓN
# =========================
PROJECT_ROOT = Path(__file__).parent
DIRECTORIO_REPORTES = PROJECT_ROOT / "Reportes_CICS_TEST"
DIRECTORIO_SALIDA = PROJECT_ROOT / "JSON_SALIDA"

# crear carpeta de salida si no existe
DIRECTORIO_SALIDA.mkdir(exist_ok=True)


def main():

    #cantidadRegFechaActual = validarCargaFecha(fechaActual)
    cantidadRegFechaActual = 0
    if cantidadRegFechaActual == 0:

        if not DIRECTORIO_REPORTES.exists():
            raise FileNotFoundError(f"No existe el directorio: {DIRECTORIO_REPORTES}")

        archivos = os.listdir(DIRECTORIO_REPORTES)

        for archivo in archivos:
            archivo = archivo.upper()

            # solo procesar txt
            if not archivo.endswith(".TXT"):
                continue

            print(f"Archivo en análisis: {archivo}")

            archivo_path = DIRECTORIO_REPORTES / archivo

            try:
                data = parse_cicsadm(archivo_path)

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


        # eliminar segmentos en el que el nombre inicie con "0"
        eliminar_segmentos_formato_0(DIRECTORIO_SALIDA)

        # imprimir listado segmentos tipo tabla
        print("========================================")
        print("Listado de segmentos tipo tabla:")
        imprimir_listado_segmentos_tabla(DIRECTORIO_SALIDA)
        print("========================================")
        print("\n")

        # obtener lista de archivos de reportes sin extensión
        archivos_reportes = [
            f[:-4]                       # elimina ".TXT"
            for f in os.listdir(DIRECTORIO_REPORTES)
            if f.upper().endswith(".TXT")
        ]

        # obtener la lista de segmentos por archivo
        segmentos_por_archivo = obtener_segmentos_por_archivo(DIRECTORIO_SALIDA, archivos_reportes)
        print("Segmentos por archivo:")
        for archivo, segmentos in segmentos_por_archivo.items():
            # imprimir el archivo y cada uno de sus segmentos
            print(f"Archivo: {archivo}")
            for segmento in segmentos:
                insertarSeg(segmento)

            

        # insertar segmentos por archivo
        insertar_segmentos_por_archivo(segmentos_por_archivo, fechaActual)

        #imprimir archivos_reportes
        for archivo in archivos_reportes:
            insertarArchivo(archivo)


        # ✅ al final, recorre JSONs e inserta en BD
        insertar_desde_json_generados(DIRECTORIO_SALIDA, fechaActual)


    else:
        print(f"Ya existen {cantidadRegFechaActual} registros de segmentos para la fecha actual {fechaActual}. No se procesará el archivo nuevamente.")

if __name__ == "__main__":
    main()
