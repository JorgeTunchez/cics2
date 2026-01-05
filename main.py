import os
import json
from pathlib import Path
from funciones import parse_cicsadm


# =========================
# CONFIGURACIÓN
# =========================
PROJECT_ROOT = Path(__file__).parent
DIRECTORIO_REPORTES = PROJECT_ROOT / "Reportes_CICS_TEST"
DIRECTORIO_SALIDA = PROJECT_ROOT / "JSON_SALIDA"

# crear carpeta de salida si no existe
DIRECTORIO_SALIDA.mkdir(exist_ok=True)


def main():
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


if __name__ == "__main__":
    main()
