from pathlib import Path
from conexionBD import *
import re
import json
import datetime
import os

# =========================
# DETECTORES BASE
# =========================
def is_page_header(line: str) -> bool:
    s = line.strip()
    return s[:1].isdigit() and "Applid" in s and "PAGE" in s


def is_segment_start_band(line: str, min_len: int = 80) -> bool:
    s = line.rstrip("\n\r")
    return s.startswith("+_") and (set(s) <= set("+_")) and (len(s) >= min_len)


def is_segment_end(line: str, min_len: int = 20) -> bool:
    s = line.strip()
    return s.startswith("0-") and (set(s) <= set("0-")) and (len(s) >= min_len)


def reached_segment_boundary(line: str) -> bool:
    return is_segment_end(line) or is_segment_start_band(line)


def is_title_text(text: str) -> bool:
    t = text.strip()
    if not t or ":" in t:
        return False
    if t.startswith("-"):
        return True
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 \-]{0,50}", t))


# =========================
# COLUMNAS
# =========================
def split_two_columns(line: str) -> tuple[str, str] | None:
    raw = line.rstrip("\n\r")
    if len(raw) < 40:
        return None

    runs = [(m.start(), m.end()) for m in re.finditer(r"\s{3,}", raw)]
    if not runs:
        return None

    mid = len(raw) // 2
    best = None
    best_score = -1.0

    for a, b in runs:
        run_len = b - a
        center = (a + b) // 2
        if abs(center - mid) > len(raw) * 0.25:
            continue
        score = run_len - abs(center - mid) * 0.01
        if score > best_score:
            best_score = score
            best = (a, b)

    if not best:
        return None

    a, b = best
    left = raw[:a].rstrip()
    right = raw[b:].rstrip()
    if not left or not right:
        return None
    return left, right


# =========================
# KV PARSER (MULTI CAMPO)
# =========================
KEY_RE = re.compile(r"(?P<name>(?=[^:]*[A-Za-z])[^:]{1,120}?)\s*:\s*")


def clean_field_name(name: str) -> str:
    n = name.replace(".", " ")
    n = re.sub(r"\s+", " ", n).strip()
    return n


def parse_kvs(piece: str) -> list[tuple[str, str]]:
    s = piece.rstrip()
    matches = list(KEY_RE.finditer(s))
    if not matches:
        return []

    out = []
    for idx, m in enumerate(matches):
        name_raw = m.group("name").lstrip("0").strip()
        name = clean_field_name(name_raw)

        start_val = m.end()
        end_val = matches[idx + 1].start() if idx + 1 < len(matches) else len(s)
        val = s[start_val:end_val].strip()

        if name:
            out.append((name, val))

    return out


def add_kvs_from_piece(piece: str, fields: dict[str, str]) -> None:
    for k, v in parse_kvs(piece):
        fields[k] = v


def add_kvs_from_line(line: str, fields: dict[str, str]) -> None:
    parts = split_two_columns(line)
    if parts:
        add_kvs_from_piece(parts[0], fields)
        add_kvs_from_piece(parts[1], fields)
    else:
        add_kvs_from_piece(line, fields)


# =========================
# SEGMENTO TABLA
# =========================
def looks_like_table_header(line: str) -> bool:
    s = line.rstrip()
    if not s.strip() or ":" in s:
        return False
    if not re.search(r"[A-Za-z]", s):
        return False
    return len(re.findall(r"\s{2,}", s)) >= 2


def looks_like_table_row(line: str) -> bool:
    s = line.rstrip()
    if not s.strip() or ":" in s:
        return False
    return len(re.findall(r"\s{2,}", s)) >= 2


def is_table_segment(lines: list[str], start_idx: int) -> bool:
    end_scan = min(len(lines), start_idx + 25)
    header_at = None

    for i in range(start_idx, end_scan):
        if is_page_header(lines[i]) or lines[i].strip() == "":
            continue
        if reached_segment_boundary(lines[i]):
            return False
        if looks_like_table_header(lines[i]):
            header_at = i
            break

    if header_at is None:
        return False

    for i in range(header_at + 1, end_scan):
        if is_page_header(lines[i]) or lines[i].strip() == "":
            continue
        if reached_segment_boundary(lines[i]):
            break
        if looks_like_table_row(lines[i]):
            return True

    return False


# =========================
# UTILS
# =========================
def unique_title(base: str, store: dict) -> str:
    if base not in store:
        return base
    i = 2
    while f"{base} ({i})" in store:
        i += 1
    return f"{base} ({i})"


# =========================
# PARSER PRINCIPAL
# =========================
def parse_cicsadm(file_path: Path) -> dict:
    lines = file_path.read_text(errors="ignore").splitlines()
    out: dict[str, dict] = {}
    i = 0

    while i < len(lines):
        if is_page_header(lines[i]):
            i += 1
            continue

        if is_segment_start_band(lines[i]):
            j = i + 1
            while j < len(lines) and (lines[j].strip() == "" or is_page_header(lines[j])):
                j += 1
            if j >= len(lines):
                break

            split = split_two_columns(lines[j])
            if split and is_title_text(split[0]) and is_title_text(split[1]):
                tL = split[0].lstrip("-").strip()
                tR = split[1].lstrip("-").strip()
                j += 1

                left, right = {}, {}
                while j < len(lines) and not reached_segment_boundary(lines[j]):
                    if not is_page_header(lines[j]) and lines[j].strip():
                        parts = split_two_columns(lines[j])
                        if parts:
                            add_kvs_from_piece(parts[0], left)
                            add_kvs_from_piece(parts[1], right)
                        else:
                            add_kvs_from_piece(lines[j], left)
                    j += 1

                out[unique_title(tL, out)] = left
                out[unique_title(tR, out)] = right
                i = j
                continue

            title = lines[j].lstrip("-").strip()
            j += 1

            while j < len(lines) and (lines[j].strip() == "" or is_page_header(lines[j]) or lines[j].startswith("+_")):
                j += 1

            if j < len(lines) and is_table_segment(lines, j):
                out[unique_title(title, out)] = {}
                while j < len(lines) and not reached_segment_boundary(lines[j]):
                    j += 1
                i = j
                continue

            fields = {}
            while j < len(lines) and not reached_segment_boundary(lines[j]):
                if not is_page_header(lines[j]) and lines[j].strip():
                    add_kvs_from_line(lines[j], fields)
                j += 1

            out[unique_title(title, out)] = fields
            i = j
            continue

        i += 1

    return out



# Validar si ya existe un segmento con la misma fecha
def validarArchivoFecha(archivo, fecha_str):
    #validar si en base de datos ya existe un segmento con la misma 
    conn = conectar_base_datos()

    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM validacion_sistema WHERE archivo = ? AND fecha = ?", (archivo, fecha_str))   
    count = cursor.fetchone()[0]
    conn.close()    
    return count


# crear funcion que valide si ya existe un archivo en la tabla archivos
def validarArchivoExistente(nombreArchivo):
    count = 0
    conn = conectar_base_datos()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM archivos WHERE archivo = ?", (nombreArchivo))   
    count = cursor.fetchone()[0]
    conn.close()    
    return count

#crear función para insertar nombre de archivo
def insertarArchivo(nombreArchivo):
    conn_sqlserver = conectar_base_datos()
    cursor = conn_sqlserver.cursor()

    # ✅ crear tabla si no existe
    cursor.execute("""
    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='archivos' AND xtype='U')
    CREATE TABLE archivos
    (
        id INT IDENTITY(1,1) PRIMARY KEY,
        archivo NVARCHAR(255)
    );
    """)
    conn_sqlserver.commit()

    cantidadArchivos = validarArchivoExistente(nombreArchivo)
    if cantidadArchivos == 0:

        # insertar nombre de archivo
        insert_sql = """
            INSERT INTO archivos (archivo)
            VALUES (?)
        """

        cursor.execute(insert_sql, (nombreArchivo,))
        conn_sqlserver.commit()
        conn_sqlserver.close()
        print(f"Archivo insertado en archivos_procesados: {nombreArchivo}")


# validar si existe Segmento
def validarSegmentoExistente(nombreSegmento):
    count = 0
    conn = conectar_base_datos()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM segmento WHERE segmento = ?", (nombreSegmento))   
    count = cursor.fetchone()[0]
    conn.close()    
    return count


# permite registrar segmento unicos en base de datos
def insertarSeg(nombreSegmento):
    conn_sqlserver = conectar_base_datos()
    cursor = conn_sqlserver.cursor()

    # ✅ crear tabla si no existe
    cursor.execute("""
    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='segmento' AND xtype='U')
    CREATE TABLE segmento
    (
        id INT IDENTITY(1,1) PRIMARY KEY,
        segmento NVARCHAR(255)
    );
    """)
    conn_sqlserver.commit()
    cantidadSegmentos = validarSegmentoExistente(nombreSegmento)
    if cantidadSegmentos == 0:

        # insertar nombre de segmento
        insert_sql = """
            INSERT INTO segmento (segmento)
            VALUES (?)
        """

        cursor.execute(insert_sql, (nombreSegmento,))
        conn_sqlserver.commit()
        conn_sqlserver.close()
        print(f"Segmento insertado en segmentos_procesados: {nombreSegmento}")


def obtenerIdSegmento(nombreSegmento):
    conn_sqlserver = conectar_base_datos()
    cursor = conn_sqlserver.cursor()
    cursor.execute("SELECT id FROM segmento WHERE segmento = ?", (nombreSegmento,))
    segmento_id_row = cursor.fetchone()  
    segmento_id = segmento_id_row[0] if segmento_id_row else None
    return segmento_id


def insertarValidacionSistema(fechaActual, nombreArchivo, diccionarioSegmentos):
    """
    diccionarioSegmentos esperado:
      {
        "Titulo Segmento": {"Campo": "Valor", ...},
        "Otro Segmento": {...},
        "Segmento Tabla": {}  # sin detalle por ahora
      }
    """

    conn_sqlserver = conectar_base_datos()
    cursor = conn_sqlserver.cursor()

    # ✅ crear tabla si no existe (corregido: valida el nombre correcto)
    cursor.execute("""
    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='validacion_sistema' AND xtype='U')
    CREATE TABLE validacion_sistema
    (
        id INT IDENTITY(1,1) PRIMARY KEY,
        archivo INT,
        segmento INT,
        campo NVARCHAR(255),
        valor NVARCHAR(MAX),
        fecha DATE
    );
    """)
    conn_sqlserver.commit()

    # índice para mejorar consultas por fecha
    cursor.execute("""
    IF NOT EXISTS (
        SELECT * FROM sys.indexes
        WHERE name = 'IX_validacion_sistema_fecha'
          AND object_id = OBJECT_ID('validacion_sistema')
    )
    CREATE INDEX IX_validacion_sistema_fecha ON validacion_sistema(fecha);
    """)
    conn_sqlserver.commit()


    # en vez de ser nombreArchivo un INT, debería ser el ID del archivo en la tabla archivos
    archivoNombre = nombreArchivo.replace(".TXT", "")
    cursor.execute("SELECT id FROM archivos WHERE archivo = ?", (archivoNombre,))
    archivo_id_row = cursor.fetchone()  
    archivo_id = archivo_id_row[0] if archivo_id_row else None

    print(f"Archivo ID para {archivoNombre}: {archivo_id}")
    

    # ✅ tu validación de duplicado por archivo+fecha
    cantidadRegFechaActual = validarArchivoFecha(archivo_id, fechaActual)
    print(f"Cantidad de registros para la fecha {fechaActual} y archivo {nombreArchivo}: {cantidadRegFechaActual}")

    if cantidadRegFechaActual > 0:
        print(f"Ya existen segmentos registrados para la fecha {fechaActual} y archivo {nombreArchivo}. No se insertarán nuevos registros.")
        conn_sqlserver.close()
        return

    print(f"Insertando nuevos segmentos para la fecha {fechaActual} y archivo {nombreArchivo}...")

    insert_sql = """
        INSERT INTO validacion_sistema (archivo, segmento, campo, valor, fecha)
        VALUES (?, ?, ?, ?, ?)
    """

    filas_insertadas = 0

    # ✅ recorrer: titulo -> {campo:valor}
    for titulo, campos in diccionarioSegmentos.items():

        # Segmento tabla (vacío) => por ahora no insertamos detalle
        if not campos:
            # Si quieres registrar que existe el segmento aunque no tenga detalle, descomenta:
            # cursor.execute(insert_sql, (nombreArchivo, titulo, "__TABLE__", "__NO_DETAIL__", fechaActual))
            # filas_insertadas += 1
            continue

        # campos debe ser dict
        if not isinstance(campos, dict):
            # por si llega algo raro
            continue

        for campo, valor in campos.items():
            # Normalizar valor a string (por seguridad)
            if valor is None:
                valor = ""
            else:
                valor = str(valor)

            #obtener el id del segmento en base a su nombre
            segmento_id = obtenerIdSegmento(titulo)

            #print debug opcional
            print(f"Archivo: {nombreArchivo}, Segmento: {titulo}, Campo: {campo}, Valor: {valor}")
            cursor.execute(insert_sql, (archivo_id, segmento_id, str(campo), valor, fechaActual))
            filas_insertadas += 1

    conn_sqlserver.commit()
    conn_sqlserver.close()
    print(f"Inserción completada. Filas insertadas: {filas_insertadas}")


def eliminar_segmentos_formato_0(DIRECTORIO_SALIDA):
    archivos_json = os.listdir(DIRECTORIO_SALIDA)

    for archivo_json in archivos_json:
        archivo_json = archivo_json.upper()

        if not archivo_json.endswith(".JSON"):
            continue

        json_path = DIRECTORIO_SALIDA / archivo_json

        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))

            prefijos_excluir = ("0", "Pool Number :", "Totals")

            data = {
                k: v
                for k, v in data.items()
                if not k.startswith(prefijos_excluir)
            }

            json_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )

            print(f"✔ Segmentos formato '0' eliminados en: {archivo_json}")    

        except Exception as e:
            print(f"❌ Error eliminando segmentos en {archivo_json}: {e}")


def insertar_desde_json_generados(DIRECTORIO_SALIDA, fechaActual):
    archivos_json = os.listdir(DIRECTORIO_SALIDA)

    for archivo_json in archivos_json:
        archivo_json = archivo_json.upper()

        if not archivo_json.endswith(".JSON"):
            continue

        json_path = DIRECTORIO_SALIDA / archivo_json

        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))

            # nombreArchivo lo guardamos como el txt original si quieres,
            # o usamos el JSON como referencia
            nombreArchivo = archivo_json.replace(".JSON", "")

            print(f"Insertando segmentos desde: {archivo_json}")
            insertarValidacionSistema(fechaActual, nombreArchivo, data)

        except Exception as e:
            print(f"❌ Error insertando desde {archivo_json}: {e}")



def obtener_segmentos_por_archivo(DIRECTORIO_SALIDA, archivos_reportes):
    segmentos_por_archivo = {}

    for archivo in archivos_reportes:
        nombre_json = archivo + ".JSON"
        json_path = DIRECTORIO_SALIDA / nombre_json

        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            segmentos = list(data.keys())
            segmentos_por_archivo[archivo] = segmentos

            print(f"✔ Segmentos obtenidos para {archivo}: {len(segmentos)}")

        except Exception as e:
            print(f"❌ Error obteniendo segmentos para {archivo}: {e}")

    return segmentos_por_archivo


def insertar_segmentos_por_archivo(segmentos_por_archivo, fechaActual):
    for archivo, segmentos in segmentos_por_archivo.items():
        nombreArchivo = archivo

        print(f"Insertando segmentos para archivo: {nombreArchivo}")

        # Crear un diccionario simulado para insertar
        diccionarioSegmentos = {segmento: {} for segmento in segmentos}

        insertarValidacionSistema(fechaActual, nombreArchivo, diccionarioSegmentos)


def imprimir_listado_segmentos_tabla(DIRECTORIO_SALIDA):
    archivos_json = os.listdir(DIRECTORIO_SALIDA)

    for archivo_json in archivos_json:
        archivo_json = archivo_json.upper()

        if not archivo_json.endswith(".JSON"):
            continue

        json_path = DIRECTORIO_SALIDA / archivo_json

        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))

            print(f"Listado de segmentos en {archivo_json}:")
            for segmento in data.keys():
                print(f" - {segmento}")
            print("\n")

        except Exception as e:
            print(f"❌ Error imprimiendo segmentos en {archivo_json}: {e}")