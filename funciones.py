from __future__ import annotations

import os
from pathlib import Path
from conexionBD import *
import re
from datetime import datetime


boolPrueba = False
cantidadRegistroPrueba = 5


def _is_debug_storage_enabled() -> bool:
    """
    Activa debug del segmento Storage - Domain Subpools con variable de entorno.
    Valores truthy soportados: 1, true, yes, on.
    """
    return str(os.getenv("DEBUG_STORAGE_SEGMENT", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

# define una función para convertir un valor a entero o None si no es posible
def to_int_or_none(value):
    if value is None:
        return None

    s = str(value).strip().replace(",", "")

    if s == "":
        return None

    if not s.isdigit():
        return None

    return int(s)


def to_float_or_none(value):
    if value is None:
        return None

    s = str(value).strip().replace(",", "").replace("%", "")

    if s == "":
        return None

    if not re.fullmatch(r"-?\d+(\.\d+)?", s):
        return None

    return float(s)


def clean_segment_title(title: str) -> str:
    """
    Limpia títulos de segmentos CICS.
    """

    if not title:
        return ""

    s = str(title)

    # remover prefijo 0 típico de CICS
    s = re.sub(r"^\s*0", "", s)

    # colapsar espacios múltiples
    s = re.sub(r"\s+", " ", s)

    return s.strip()


# Define una función para obtener la fecha del encabezado de un archivo, buscando un patrón específico y formateando la fecha encontrada
def obtener_fecha_encabezado(file_path: Path) -> str:
    """
    Busca la fecha en el encabezado del archivo.
    Retorna la fecha en formato YYYY-MM-DD.
    Soporta:
      - DD/MM/YYYY
      - MM/DD/YYYY
    """
    patron = re.compile(r"Date\s+(\d{2}/\d{2}/\d{4})", re.IGNORECASE)

    with file_path.open("r", encoding="utf-8", errors="ignore") as f:
        for _ in range(20):
            linea = f.readline()
            if not linea:
                break

            m = patron.search(linea)
            if m:
                fecha_txt = m.group(1).strip()

                formatos = ["%d/%m/%Y", "%m/%d/%Y"]
                for fmt in formatos:
                    try:
                        fecha_obj = datetime.strptime(fecha_txt, fmt)
                        return fecha_obj.strftime("%Y-%m-%d")
                    except ValueError:
                        continue

                raise ValueError(
                    f"La fecha '{fecha_txt}' del archivo {file_path.name} no coincide con formatos esperados."
                )

    raise ValueError(f"No se encontró la fecha en el encabezado del archivo: {file_path.name}")


# Genera archivos JSON a partir de los archivos TXT en el directorio de reportes, extrayendo solo los segmentos permitidos y guardando el resultado en el directorio de salida
def validar_fecha_unica_archivos(directorio_reportes: Path) -> str:
    """
    Recorre todos los .TXT del directorio y valida que tengan la misma fecha.
    Retorna la fecha única en formato YYYY-MM-DD.
    Lanza excepción si hay fechas distintas o si no encuentra fecha.
    """
    archivos = sorted([p for p in directorio_reportes.iterdir() if p.is_file() and p.suffix.upper() == ".TXT"])

    if not archivos:
        raise FileNotFoundError(f"No se encontraron archivos .TXT en: {directorio_reportes}")

    fechas_por_archivo = {}

    for archivo in archivos:
        fecha = obtener_fecha_encabezado(archivo)
        fechas_por_archivo[archivo.name] = fecha

    fechas_unicas = sorted(set(fechas_por_archivo.values()))

    if len(fechas_unicas) > 1:
        detalle = "\n".join([f" - {nombre}: {fecha}" for nombre, fecha in fechas_por_archivo.items()])
        raise ValueError(
            "Se detectaron archivos con fechas distintas. "
            "Todos los archivos de entrada deben pertenecer a la misma fecha.\n"
            f"{detalle}"
        )

    return fechas_unicas[0]


# Define una función para validar que todos los archivos TXT en un directorio tengan la misma fecha en su encabezado, lanzando una excepción si se encuentran fechas distintas o si no se encuentra la fecha en alguno de los archivos
def validar_cantidad_archivos(directorio_reportes: Path, cantidad_esperada: int = 6) -> None:
    archivos = [p for p in directorio_reportes.iterdir() if p.is_file() and p.suffix.upper() == ".TXT"]
    if len(archivos) != cantidad_esperada:
        raise ValueError(
            f"Se esperaban {cantidad_esperada} archivos .TXT en ENTRADA, "
            f"pero se encontraron {len(archivos)}."
        )



# Valida si ya existen registros en la base de datos para la fecha indicada
def validar_carga_fecha(fecha_actual: str) -> int:
    """
    Retorna la cantidad total de registros encontrados para la fecha indicada
    en las tablas principales del proceso.
    """
    conn = conectar_base_datos()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            ISNULL((SELECT COUNT(*) FROM cics_programs WHERE fecha = ?), 0) +
            ISNULL((SELECT COUNT(*) FROM cics_transactions WHERE fecha = ?), 0) +
            ISNULL((SELECT COUNT(*) FROM cics_temporary_storage_queues WHERE fecha = ?), 0) +
            ISNULL((SELECT COUNT(*) FROM cics_files WHERE fecha = ?), 0)
    """, (fecha_actual, fecha_actual, fecha_actual, fecha_actual))

    row = cursor.fetchone()
    conn.close()

    return int(row[0]) if row and row[0] is not None else 0


# Determina si una línea corresponde al encabezado de página
def is_page_header(line: str) -> bool:
    s = line.strip()
    return s[:1].isdigit() and "Applid" in s and "PAGE" in s


# Determina si una línea corresponde al inicio de un segmento, basado en que empiece con "+_" y contenga solo "+" y "_" con una longitud mínima
def is_segment_start_band(line: str, min_len: int = 80) -> bool:
    s = line.rstrip("\n\r")
    return s.startswith("+_") and (set(s) <= set("+_")) and (len(s) >= min_len)


# Determina si una línea corresponde al final de un segmento, basado en que empiece con "0-" y contenga solo "0" y "-" con una longitud mínima
def is_segment_end(line: str, min_len: int = 20) -> bool:
    s = line.strip()
    return s.startswith("0-") and (set(s) <= set("0-")) and (len(s) >= min_len)


# Determina si una línea corresponde al límite de un segmento, ya sea inicio o fin
def reached_segment_boundary(line: str) -> bool:
    return is_segment_end(line) or is_segment_start_band(line)


# Determina si una línea corresponde a una línea separadora, basada en que empiece con "+" y el resto de la línea contenga solo "_" 
def is_separator_line(line: str) -> bool:
    s = line.rstrip("\n\r")
    if not s.startswith("+"):
        return False
    rest = s[1:].strip()
    return bool(rest) and set(rest) == {"_"}


# Determina si un texto corresponde a un título, basado en que no esté vacío, no contenga ":" y cumpla con un patrón de caracteres alfanuméricos y guiones
def is_title_text(text: str) -> bool:
    t = text.strip()
    if not t or ":" in t:
        return False
    if t.startswith("-"):
        return True
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 \-]{0,50}", t))


# Normaliza un nombre de campo reemplazando puntos por espacios y eliminando espacios extra
def clean_field_name(name: str) -> str:
    n = str(name).replace(".", " ")
    n = re.sub(r"\s+", " ", n).strip()
    return n


# Genera un título único basado en un título base y un diccionario de títulos ya existentes
def unique_title(base: str, store: dict) -> str:
    if base not in store:
        return base
    i = 2
    while f"{base} ({i})" in store:
        i += 1
    return f"{base} ({i})"

# Determina si una línea corresponde a una línea de totales, basada en que después de eliminar ceros a la izquierda comience con "Totals"
def _is_totals_line(line: str) -> bool:
    s = line.strip()
    s2 = s.lstrip("0").strip()
    return s2.startswith("Totals")


# Determina si una línea puede dividirse en dos columnas basadas en espacios consecutivos
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


# Divide una línea en tokens basados en espacios consecutivos, eliminando ceros a la izquierda y espacios extra
def _split_tokens_2plus_spaces(line: str) -> list[str]:
    s = line.rstrip("\n\r").lstrip()
    if s.startswith("0"):
        s = s[1:].lstrip()
    parts = re.split(r"\s{2,}", s.strip())
    return [p.strip() for p in parts if p.strip()]


# Genera nombres únicos para una lista de nombres numéricos agregando un sufijo incremental si hay duplicados
def make_unique_numeric(names: list[str]) -> list[str]:
    counter = {}
    out = []
    for n in names:
        base = n
        if base not in counter:
            counter[base] = 1
            out.append(base)
        else:
            counter[base] += 1
            out.append(f"{base}_{counter[base]}")
    return out


# Normaliza un contador extrayendo el último token de un valor de texto, devolviendo "0" si no hay tokens
def _normalize_counter(v: str) -> str:
    parts = str(v).strip().split()
    if not parts:
        return "0"
    return parts[-1]


# Normaliza un valor de program counter extrayendo el último token de un valor de texto, devolviendo una cadena vacía si no hay tokens
def _normalize_program_counter(v: str) -> str:
    parts = str(v).strip().split()
    if not parts:
        return ""
    return parts[-1]


# Devuelve la lista de columnas forzadas para el segmento Programs, en el orden esperado
def get_programs_forced_columns() -> list[str]:
    return [
        "programName",
        "dataLocExecKey",
        "timesUsed",
        "timesFetched",
        "totalFecthTime",
        "AverageFetchTime",
        "libraryName",
        "libraryOffset",
        "timesNewCopy",
        "timesRemoved",
        "programSize",
        "progLocn",
    ]


# Construye los spans de columnas basados en espacios verticales en las líneas de datos, solo considerando los datos y no los encabezados
def _build_spans_by_vertical_spaces_data_only(data_lines: list[str], ncols: int) -> list[tuple[int, int]]:
    if not data_lines or ncols < 2:
        return []
    max_len = max(len(x) for x in data_lines)
    norm = [(x + " " * (max_len - len(x))) for x in data_lines]
    mask = [all(line[j] == " " for line in norm) for j in range(max_len)]
    runs = []
    j = 0
    while j < max_len:
        if mask[j]:
            start = j
            while j < max_len and mask[j]:
                j += 1
            end = j
            if end - start >= 2:
                runs.append((start, end))
        else:
            j += 1
    if not runs:
        return []
    runs_sorted = sorted(runs, key=lambda ab: (ab[1] - ab[0]), reverse=True)
    top_runs = runs_sorted[: (ncols - 1)]
    cut_points = sorted({(a + b) // 2 for a, b in top_runs})
    if len(cut_points) != ncols - 1:
        return []
    spans = []
    prev = 0
    for c in cut_points:
        spans.append((prev, c))
        prev = c
    spans.append((prev, max_len))
    return spans


# Analiza un segmento Programs con formato fijo, extrayendo los encabezados y las filas de datos basadas en spans fijos
def parse_programs_segment_fixed(lines: list[str], start_idx: int) -> tuple[list[str], list[dict], int]:
    headers = [
        "programName",
        "dataLocExecKey",
        "timesUsed",
        "timesFetched",
        "totalFecthTime",
        "AverageFetchTime",
        "libraryName",
        "libraryOffset",
        "timesNewCopy",
        "timesRemoved",
        "programSize",
        "progLocn",
    ]

    def _normalize_fixed(line: str) -> str:
        s = line.rstrip("\n\r")
        m = re.match(r"^(\s*)0(.*)$", s)
        if m:
            s = m.group(1) + m.group(2)
        return s

    def _is_omit(line: str) -> bool:
        if is_page_header(line) or line.strip() == "" or is_separator_line(line):
            return True
        if re.match(r"^\s*\+\s*_+", line):
            return True
        return False

    def _is_data_row(line: str) -> bool:
        s = _normalize_fixed(line).strip()

        if not s:
            return False

        if not re.match(r"^[A-Z0-9$#@]{3,}", s):
            return False

        return True

    def _spans_from_subheader(sub: str) -> list[tuple[int, int]]:
        s = _normalize_fixed(sub)
        spans: list[tuple[int, int]] = []
        for m in re.finditer(r"\S(?:.*?\S)?(?=\s{2,}|$)", s):
            if m.group(0).strip():
                spans.append((m.start(), m.end()))
        return spans

    i = start_idx
    subheader_line = None

    scan_limit = min(len(lines), start_idx + 30)
    while i < scan_limit:
        if _is_omit(lines[i]):
            i += 1
            continue

        line = lines[i]
        if ("Exec Key" in line) and ("Times Used" in line):
            subheader_line = line
            i += 1
            break

        i += 1

    if subheader_line is None:
        return headers, [], start_idx

    spans = _spans_from_subheader(subheader_line)

    if len(spans) != len(headers):
        data_samples = []
        k = i
        while k < len(lines) and len(data_samples) < 80:
            if _is_omit(lines[k]):
                k += 1
                continue
            if reached_segment_boundary(lines[k]) or _is_totals_line(lines[k]):
                break
            if _is_data_row(lines[k]):
                data_samples.append(_normalize_fixed(lines[k]))
            k += 1

        spans = _build_spans_by_vertical_spaces_data_only(data_samples, ncols=len(headers))

    if not spans or len(spans) != len(headers):
        return headers, [], i

    while i < len(lines) and _is_omit(lines[i]):
        i += 1

    rows: list[dict] = []

    def _norm(v: str) -> str:
        parts = str(v).strip().split()
        return parts[-1] if parts else ""

    while i < len(lines):
        if _is_omit(lines[i]):
            i += 1
            continue

        if reached_segment_boundary(lines[i]) or _is_totals_line(lines[i]):
            break

        if not _is_data_row(lines[i]):
            i += 1
            continue

        row_line = _normalize_fixed(lines[i])

        mname = re.match(r"^\s*([A-Z0-9$#@]{3,})\b", row_line.strip())
        program_name = mname.group(1) if mname else ""

        middle_tokens = [row_line[a:b].strip() for (a, b) in spans[1:-2]]

        right_parts = re.findall(r"\S+", row_line.strip())
        prog_locn = right_parts[-1] if len(right_parts) >= 1 else ""
        program_size = right_parts[-2] if len(right_parts) >= 2 else ""

        tokens = [program_name] + middle_tokens + [program_size, prog_locn]

        if len(tokens) < len(headers):
            tokens += [""] * (len(headers) - len(tokens))
        elif len(tokens) > len(headers):
            tokens = tokens[:len(headers)]

        row = {headers[idx]: tokens[idx] for idx in range(len(headers))}

        # reconstrucción con tokens reales para evitar truncamientos
        parts = re.findall(r"\S+", row_line)

        if len(parts) >= 2:
            row["dataLocExecKey"] = parts[1].strip()

        if len(parts) >= 5:
            row["totalFecthTime"] = parts[4].strip()

        if len(parts) >= 6:
            row["AverageFetchTime"] = parts[5].strip()

        if len(parts) >= 7:
            row["libraryName"] = parts[6].strip()

        if len(parts) >= 8:
            row["libraryOffset"] = parts[7].strip()

        for kf in ("timesUsed", "timesFetched", "timesNewCopy", "timesRemoved"):
            row[kf] = _norm(row.get(kf, ""))

        row["programSize"] = str(row.get("programSize", "") or "").replace(",", "").strip()
        row["totalFecthTime"] = str(row.get("totalFecthTime", "") or "").strip()
        row["AverageFetchTime"] = str(row.get("AverageFetchTime", "") or "").strip()
        row["dataLocExecKey"] = str(row.get("dataLocExecKey", "") or "").strip()
        row["libraryName"] = str(row.get("libraryName", "") or "").strip()
        row["libraryOffset"] = str(row.get("libraryOffset", "") or "").strip()
        row["progLocn"] = str(row.get("progLocn", "") or "").strip()

        rows.append(row)
        i += 1

    return headers, rows, i




# Devuelve la lista de columnas forzadas para un segmento específico, en el orden esperado, o None si no hay columnas forzadas para ese segmento
def get_forced_table_columns(segment_title: str) -> list[str] | None:
    t = (segment_title or "").strip().lower()
    if t == "transactions":
        return [
            "tranId", "tranClass", "programName", "dynamic", "isolate",
            "taskDataLocationKey", "attachCount", "restartCount",
            "dynamicLocal", "remoteStarts", "storageViols", "abendCount",
        ]
    if t == "programs":
        return get_programs_forced_columns()
    return None

# Analiza una línea de un segmento Transactions, devolviendo un diccionario con los campos extraídos o None si no se puede parsear
def parse_transactions_row(line: str) -> dict | None:
    s = line.strip()
    if not s:
        return None
    if s.startswith("0 "):
        s = s[2:].lstrip()
    elif s.startswith("0") and len(s) > 1 and s[1].isspace():
        s = s[1:].lstrip()

    parts = re.split(r"\s+", s)
    if len(parts) < 8:
        return None
    if not re.fullmatch(r"[A-Z0-9]{4}", parts[0]):
        return None

    tranId = parts[0]
    dyn_idx = None
    for idx in range(1, len(parts)):
        if parts[idx] in ("Static", "Dynamic"):
            dyn_idx = idx
            break
    if dyn_idx is None or dyn_idx < 2:
        return None

    programName = parts[dyn_idx - 1]
    middle = parts[1:dyn_idx - 1]
    tranClass = middle[0] if len(middle) == 1 else (" ".join(middle) if len(middle) > 1 else "")
    dynamic = parts[dyn_idx]
    if dyn_idx + 2 >= len(parts):
        return None
    isolate = parts[dyn_idx + 1]
    taskDataLocationKey = parts[dyn_idx + 2]

    tail = parts[dyn_idx + 3:]
    if len(tail) < 6:
        return None
    if len(tail) > 6:
        tail = tail[:5] + [" ".join(tail[5:])]
    attachCount, restartCount, dynamicLocal, remoteStarts, storageViols, abendCount = [
        _normalize_counter(x) for x in tail
    ]

    return {
        "tranId": tranId,
        "tranClass": tranClass,
        "programName": programName,
        "dynamic": dynamic,
        "isolate": isolate,
        "taskDataLocationKey": taskDataLocationKey,
        "attachCount": attachCount,
        "restartCount": restartCount,
        "dynamicLocal": dynamicLocal,
        "remoteStarts": remoteStarts,
        "storageViols": storageViols,
        "abendCount": abendCount,
    }


# Analiza un segmento de tabla genérico, extrayendo los encabezados y las filas de datos basadas en líneas no vacías y no separadoras, 
# deteniéndose al alcanzar un límite de segmento o una línea de totales. 
# Si el título del segmento es "Transactions" o "Programs", se aplican reglas específicas para esos segmentos.
def parse_table_segment(lines: list[str], start_idx: int, segment_title: str | None = None) -> tuple[list[str], list[dict], int]:
    i = start_idx
    headers_raw = []
    while i < len(lines):
        if is_page_header(lines[i]) or lines[i].strip() == "" or is_separator_line(lines[i]):
            i += 1
            continue
        if reached_segment_boundary(lines[i]) or _is_totals_line(lines[i]):
            break
        headers_raw.append(lines[i])
        i += 1
        if len(headers_raw) >= 2:
            break

    if (segment_title or "").strip().lower() == "transactions":
        headers = get_forced_table_columns("transactions") or []
        rows = []
        while i < len(lines):
            if is_page_header(lines[i]) or lines[i].strip() == "" or is_separator_line(lines[i]):
                i += 1
                continue
            if reached_segment_boundary(lines[i]) or _is_totals_line(lines[i]):
                break
            row = parse_transactions_row(lines[i])
            if row:
                rows.append(row)
            i += 1
        return headers, rows, i

    if (segment_title or "").strip().lower() == "programs":
        return parse_programs_segment_fixed(lines, start_idx)
    
    
    if (segment_title or "").strip().lower() == "temporary storage queues":
        return parse_temporary_storage_queues_segment(lines, start_idx)

    return [], [], i


# Analiza un archivo CICSADM Lite, extrayendo solo los segmentos permitidos (Programs, Transactions, Temporary Storage Queues) y devolviendo un diccionario con los datos estructurados de esos segmentos.
def parse_cicsadm_lite(file_path: Path, allowed_segments: set[str] | None = None) -> dict:
    """
    Parser reducido:
    - Programs
    - Temporary Storage Queues
    - Files
    - Transactions
    """

    if allowed_segments is None:
        allowed_segments = {
            "programs",
            "temporary storage queues",
            "files",
            "transactions",
            "storage - domain subpools",
            "system status",
            "monitoring",
        }

    allowed_segments = {clean_segment_title(x).lower() for x in allowed_segments}

    lines = file_path.read_text(errors="ignore").splitlines()
    out: dict[str, dict] = {}
    debug_storage = _is_debug_storage_enabled()
    storage_seen = False
    storage_rows = 0
    storage_key_name = ""
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

            # segmento doble (ej. Monitoring / Statistics)
            split = split_two_columns(lines[j])
            if split and is_title_text(split[0]) and is_title_text(split[1]):
                left_title = clean_segment_title(split[0].lstrip("-").strip()).lower()

                if left_title == "monitoring" and left_title in allowed_segments:
                    title = "Monitoring"
                    j += 1

                    while j < len(lines) and (
                        lines[j].strip() == ""
                        or is_page_header(lines[j])
                        or is_separator_line(lines[j])
                        or lines[j].startswith("+_")
                    ):
                        j += 1

                    columnas, data, next_j = parse_monitoring_segment(lines, j)

                    key = unique_title(title, out)
                    out[key] = {
                        "nombre": title,
                        "tipo": "informacion",
                        "detalles": {
                            "columnas": columnas,
                            "datos": data
                        }
                    }

                    j = next_j
                    while j < len(lines) and not reached_segment_boundary(lines[j]) and not _is_totals_line(lines[j]):
                        j += 1

                    i = j
                    continue

                while j < len(lines) and not reached_segment_boundary(lines[j]):
                    j += 1
                i = j
                continue

            # título simple
            raw_title = lines[j].lstrip("-").strip()
            title = clean_segment_title(raw_title)
            title_key = title.lower()
            j += 1

            # saltar vacíos / headers / separadores
            while j < len(lines) and (
                lines[j].strip() == ""
                or is_page_header(lines[j])
                or is_separator_line(lines[j])
                or lines[j].startswith("+_")
            ):
                j += 1

            # si no está permitido, saltar segmento completo
            if title_key not in allowed_segments:
                while j < len(lines) and not reached_segment_boundary(lines[j]):
                    j += 1
                i = j
                continue

            # Programs
            if title_key == "programs":
                columnas, filas, next_j = parse_programs_segment_fixed(lines, j)

            # Temporary Storage Queues
            elif title_key == "temporary storage queues":
                columnas, filas, next_j = parse_temporary_storage_queues_segment(lines, j)

            # Files
            elif title_key == "files":
                columnas, filas, next_j = parse_files_segment(lines, j)

            # Transactions
            elif title_key == "transactions":
                columnas, filas, next_j = parse_table_segment(lines, j, title)
                
            
            # Storage - Domain Subpools
            elif ("storage" in title_key and "domain" in title_key and "subpool" in title_key):

                columnas, filas, next_j = parse_storage_domain_subpool_segment(lines, j)

                key = unique_title(title, out)

                out[key] = {
                    "nombre": title,
                    "tipo": "tabla",
                    "detalles": {
                        "columnas": columnas,
                        "filas": filas
                    }
                }

                storage_seen = True
                storage_rows = len(filas)
                storage_key_name = key

                if debug_storage:
                    print(
                        f"[DEBUG][{file_path.name}] Segmento Storage detectado -> "
                        f"key='{key}', columnas={len(columnas)}, filas={len(filas)}"
                    )

                j = next_j

                while (
                    j < len(lines)
                    and not reached_segment_boundary(lines[j])
                    and not _is_totals_line(lines[j])
                ):
                    j += 1

                i = j
                continue

            # System Status
            elif title_key == "system status":
                columnas, data, next_j = parse_system_status_segment(lines, j)

                key = unique_title(title, out)

                out[key] = {
                    "nombre": title,
                    "tipo": "informacion",
                    "detalles": {
                        "columnas": columnas,
                        "datos": data
                    }
                }

                j = next_j

                while j < len(lines) and not reached_segment_boundary(lines[j]) and not _is_totals_line(lines[j]):
                    j += 1

                i = j
                continue

            # fallback
            else:
                columnas, filas, next_j = parse_table_segment(lines, j, title)

            key = unique_title(title, out)
            out[key] = {
                "nombre": title,
                "tipo": "tabla",
                "detalles": {
                    "columnas": columnas,
                    "filas": filas
                }
            }

            j = next_j
            while j < len(lines) and not reached_segment_boundary(lines[j]) and not _is_totals_line(lines[j]):
                j += 1

            i = j
            continue

        i += 1

    if debug_storage:
        if storage_seen:
            print(
                f"[DEBUG][{file_path.name}] Storage - Domain Subpools presente en salida JSON "
                f"con key='{storage_key_name}' y filas={storage_rows}"
            )
        else:
            print(
                f"[DEBUG][{file_path.name}] Storage - Domain Subpools NO fue detectado "
                "en el parseo"
            )

    return out


# Conjunto de tablas requeridas en la base de datos para almacenar los segmentos extraídos de CICSADM Lite
_REQUIRED_TABLES = {
    "cics_archivos",
    "cics_segmento",
    "cics_programs",
    "cics_transactions",
    "cics_temporary_storage_queues",
    "cics_files",
    "cics_system_status",
    "cics_monitoring",
}


# Valida que existan las tablas requeridas en la base de datos, lanzando un error si alguna falta
def validar_tablas_requeridas(cursor) -> None:
    cursor.execute("""
        SELECT TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE = 'BASE TABLE'
                    AND TABLE_NAME IN (
                        'cics_archivos',
                        'cics_segmento',
                        'cics_programs',
                        'cics_transactions',
                        'cics_temporary_storage_queues',
                        'cics_files',
                        'cics_system_status',
                        'cics_monitoring'
                    )
    """)
    existentes = {row[0].lower() for row in cursor.fetchall()}
    faltantes = sorted(t for t in _REQUIRED_TABLES if t.lower() not in existentes)
    if faltantes:
        raise RuntimeError("No existen las tablas requeridas: " + ", ".join(faltantes))


# Inserta un archivo en cics_archivos si no existe y devuelve su id
def upsert_archivo(cursor, archivo_nombre: str) -> int:
    cursor.execute("SELECT id FROM cics_archivos WHERE UPPER(archivo) = ?", (archivo_nombre.upper(),))
    row = cursor.fetchone()
    if row and row[0] is not None:
        return int(row[0])

    cursor.execute("INSERT INTO cics_archivos (archivo) VALUES (?)", (archivo_nombre,))
    cursor.execute("SELECT id FROM cics_archivos WHERE UPPER(archivo) = ?", (archivo_nombre.upper(),))
    row = cursor.fetchone()
    if not row or row[0] is None:
        raise RuntimeError(f"No se pudo obtener id para archivo='{archivo_nombre}'")
    return int(row[0])


# Inserta un segmento en cics_segmento si no existe y devuelve su id
def upsert_segmento(cursor, segmento_nombre: str) -> int:
    cursor.execute("SELECT id FROM cics_segmento WHERE segmento = ?", (segmento_nombre,))
    row = cursor.fetchone()
    if row and row[0] is not None:
        return int(row[0])

    cursor.execute("INSERT INTO cics_segmento (segmento) VALUES (?)", (segmento_nombre,))
    cursor.execute("SELECT id FROM cics_segmento WHERE segmento = ?", (segmento_nombre,))
    row = cursor.fetchone()
    if not row or row[0] is None:
        raise RuntimeError(f"No se pudo obtener id para segmento='{segmento_nombre}'")
    return int(row[0])


# Inserta filas del segmento Programs en cics_programs usando executemany por lotes
def insert_programs_rows(cursor, archivo_id: int, fecha: str, rows: list[dict], batch_size: int = 1000) -> int:
    """
    Inserta filas del segmento Programs en cics_programs usando executemany por lotes.
    Adaptada para columnas INT.
    """

    def _guess_program_name_from_row(r: dict) -> str:
        v = str(r.get("programName", "") or "").strip()
        if v:
            return v

        for k in r.keys():
            if k and k.lower().replace("_", "").replace(" ", "") == "programname":
                v2 = str(r.get(k, "") or "").strip()
                if v2:
                    return v2

        prog_re = re.compile(r"^[A-Z0-9$#@]{4,12}$")
        for val in r.values():
            s = str(val or "").strip()
            if prog_re.match(s):
                return s

        return ""

    sql = """
    INSERT INTO cics_programs
    (
        archivo, fecha, programName, dataLocExecKey, timesUsed, timesFetched,
        totalFecthTime, AverageFetchTime, libraryName, libraryOffset,
        timesNewCopy, timesRemoved, programSize, progLocn
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    total_rows = 0
    inserted = 0
    skipped_empty_name = 0
    batch = []

    try:
        cursor.fast_executemany = True
    except Exception:
        pass

    for r in rows:
        total_rows += 1

        if not isinstance(r, dict):
            continue

        programName = _guess_program_name_from_row(r)
        if not programName:
            skipped_empty_name += 1
            continue

        dataLocExecKey = str(r.get("dataLocExecKey", "") or "").strip()

        timesUsed = to_int_or_none(_normalize_program_counter(str(r.get("timesUsed", "") or "")))
        timesFetched = to_int_or_none(_normalize_program_counter(str(r.get("timesFetched", "") or "")))

        totalFecthTime = str(r.get("totalFecthTime", "") or "").strip()
        AverageFetchTime = str(r.get("AverageFetchTime", "") or "").strip()
        libraryName = str(r.get("libraryName", "") or "").strip()

        libraryOffset = to_int_or_none(
            _normalize_program_counter(str(r.get("libraryOffset", "") or ""))
        )

        timesNewCopy = to_int_or_none(_normalize_program_counter(str(r.get("timesNewCopy", "") or "")))
        timesRemoved = to_int_or_none(_normalize_program_counter(str(r.get("timesRemoved", "") or "")))
        programSize = to_int_or_none(str(r.get("programSize", "") or ""))
        progLocn = str(r.get("progLocn", "") or "").strip()

        batch.append((
            archivo_id,
            fecha,
            programName,
            dataLocExecKey,
            timesUsed,
            timesFetched,
            totalFecthTime,
            AverageFetchTime,
            libraryName,
            libraryOffset,
            timesNewCopy,
            timesRemoved,
            programSize,
            progLocn
        ))

        if len(batch) >= batch_size:
            cursor.executemany(sql, batch)
            inserted += len(batch)
            batch.clear()

    if batch:
        cursor.executemany(sql, batch)
        inserted += len(batch)

    print(
        f"Programs: total_rows={total_rows}, inserted={inserted}, "
        f"skipped_empty_name={skipped_empty_name}"
    )

    return inserted


# Inserta filas del segmento Transactions en cics_transactions usando executemany por lotes
def insert_transactions_rows(cursor, archivo_id: int, fecha: str, rows: list[dict], batch_size: int = 1000) -> int:
    """
    Inserta filas del segmento Transactions en cics_transactions usando executemany por lotes.
    Adaptada para columnas INT.
    """

    sql = """
    INSERT INTO cics_transactions
    (
        archivo, fecha, tranId, tranClass, programName, dynamic, isolate, taskDataLocationKey,
        attachCount, restartCount, dynamicLocal, remoteStarts, storageViols, abendCount
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    total_rows = 0
    inserted = 0
    skipped_empty_tranid = 0
    batch = []

    try:
        cursor.fast_executemany = True
    except Exception:
        pass

    for r in rows:
        total_rows += 1

        if not isinstance(r, dict):
            continue

        tranId = str(r.get("tranId", "") or "")
        tranClass = str(r.get("tranClass", "") or "")
        programName = str(r.get("programName", "") or "")
        dynamic = str(r.get("dynamic", "") or "")
        isolate = str(r.get("isolate", "") or "")
        taskDataLocationKey = str(r.get("taskDataLocationKey", "") or "")

        attachCount = to_int_or_none(r.get("attachCount", ""))
        restartCount = to_int_or_none(r.get("restartCount", ""))
        dynamicLocal = to_int_or_none(r.get("dynamicLocal", ""))
        remoteStarts = to_int_or_none(r.get("remoteStarts", ""))
        storageViols = to_int_or_none(r.get("storageViols", ""))
        abendCount = to_int_or_none(r.get("abendCount", ""))

        tranId = re.sub(r"\s+", "", tranId).upper()
        tranClass = re.sub(r"\s+", "", tranClass).upper()
        programName = programName.strip()
        dynamic = dynamic.strip()
        isolate = isolate.strip()
        taskDataLocationKey = taskDataLocationKey.strip()

        if not tranId:
            skipped_empty_tranid += 1
            continue

        batch.append((
            archivo_id,
            fecha,
            tranId,
            tranClass,
            programName,
            dynamic,
            isolate,
            taskDataLocationKey,
            attachCount,
            restartCount,
            dynamicLocal,
            remoteStarts,
            storageViols,
            abendCount
        ))

        if len(batch) >= batch_size:
            cursor.executemany(sql, batch)
            inserted += len(batch)
            batch.clear()

    if batch:
        cursor.executemany(sql, batch)
        inserted += len(batch)

    print(
        f"Transactions: total_rows={total_rows}, inserted={inserted}, "
        f"skipped_empty_tranid={skipped_empty_tranid}"
    )

    return inserted


# Función principal para insertar la validación del sistema, que se encarga de validar las tablas requeridas, 
# insertar el archivo y los segmentos, y luego insertar las filas de cada segmento en sus respectivas tablas, 
# mostrando un resumen al final.
def insertarValidacionSistema(fechaActual: str, nombreArchivo: str, diccionarioSegmentos: dict) -> None:
    conn = conectar_base_datos()
    cursor = conn.cursor()

    # validar tablas requeridas
    validar_tablas_requeridas(cursor)

    archivo_nombre = nombreArchivo.replace(".TXT", "").replace(".JSON", "").strip().upper()
    archivo_id = upsert_archivo(cursor, archivo_nombre)
    conn.commit()

    # registrar segmentos
    upsert_segmento(cursor, "Programs")
    upsert_segmento(cursor, "Temporary Storage Queues")
    upsert_segmento(cursor, "Files")
    upsert_segmento(cursor, "Transactions")
    upsert_segmento(cursor, "Storage - Domain Subpools")
    upsert_segmento(cursor, "System Status")
    upsert_segmento(cursor, "Monitoring")
    conn.commit()

    # =====================================================
    # 1) INSERTAR PROGRAMS
    # =====================================================
    prog_payload = None
    for k, v in diccionarioSegmentos.items():
        if str(k).strip().lower() == "programs":
            prog_payload = v
            break

    prog_rows = []

    if isinstance(prog_payload, dict) and prog_payload.get("tipo") == "tabla":
        detalles = prog_payload.get("detalles") or {}
        prog_rows = detalles.get("filas") or []

    elif isinstance(prog_payload, dict) and "filas" in prog_payload:
        prog_rows = prog_payload.get("filas") or []

    inserted_prog = 0

    if isinstance(prog_rows, list) and prog_rows:

        rows_to_insert = (
            prog_rows[:cantidadRegistroPrueba]
            if boolPrueba
            else prog_rows
        )

        inserted_prog = insert_programs_rows(
            cursor,
            archivo_id,
            fechaActual,
            rows_to_insert,
            batch_size=1000
        )

        conn.commit()

    # =====================================================
    # 2) INSERTAR TEMPORARY STORAGE QUEUES
    # =====================================================
    tsq_payload = None

    for k, v in diccionarioSegmentos.items():
        if str(k).strip().lower() == "temporary storage queues":
            tsq_payload = v
            break

    tsq_rows = []

    if isinstance(tsq_payload, dict) and tsq_payload.get("tipo") == "tabla":
        detalles = tsq_payload.get("detalles") or {}
        tsq_rows = detalles.get("filas") or []

    elif isinstance(tsq_payload, dict) and "filas" in tsq_payload:
        tsq_rows = tsq_payload.get("filas") or []

    inserted_tsq = 0

    if isinstance(tsq_rows, list) and tsq_rows:

        rows_to_insert = (
            tsq_rows[:cantidadRegistroPrueba]
            if boolPrueba
            else tsq_rows
        )

        inserted_tsq = insert_temporary_storage_queues_rows(
            cursor,
            archivo_id,
            fechaActual,
            rows_to_insert,
            batch_size=1000
        )

        conn.commit()

    # =====================================================
    # 3) INSERTAR FILES
    # =====================================================
    files_payload = None

    for k, v in diccionarioSegmentos.items():
        if str(k).strip().lower() == "files":
            files_payload = v
            break

    files_rows = []

    if isinstance(files_payload, dict):

        if files_payload.get("tipo") == "tabla":
            detalles = files_payload.get("detalles") or {}
            files_rows = detalles.get("filas") or []

        elif "filas" in files_payload:
            files_rows = files_payload.get("filas") or []

    inserted_files = 0

    if isinstance(files_rows, list) and files_rows:

        rows_to_insert = (
            files_rows[:cantidadRegistroPrueba]
            if boolPrueba
            else files_rows
        )

        inserted_files = insert_files_rows(
            cursor,
            archivo_id,
            fechaActual,
            rows_to_insert,
            batch_size=1000
        )

        conn.commit()

    # =====================================================
    # 4) INSERTAR TRANSACTIONS
    # =====================================================
    tx_payload = None

    for k, v in diccionarioSegmentos.items():
        if str(k).strip().lower() == "transactions":
            tx_payload = v
            break

    tx_rows = []

    if isinstance(tx_payload, dict) and tx_payload.get("tipo") == "tabla":
        detalles = tx_payload.get("detalles") or {}
        tx_rows = detalles.get("filas") or []

    elif isinstance(tx_payload, dict) and "filas" in tx_payload:
        tx_rows = tx_payload.get("filas") or []

    inserted_tx = 0

    if isinstance(tx_rows, list) and tx_rows:

        rows_to_insert = (
            tx_rows[:cantidadRegistroPrueba]
            if boolPrueba
            else tx_rows
        )

        inserted_tx = insert_transactions_rows(
            cursor,
            archivo_id,
            fechaActual,
            rows_to_insert,
            batch_size=1000
        )

        conn.commit()

    # =====================================================
    # 5) INSERTAR STORAGE DOMAIN SUBPOOLS
    # =====================================================
    storage_domain_payload = None

    for k, v in diccionarioSegmentos.items():
        if str(k).strip().lower() == "storage - domain subpools":
            storage_domain_payload = v
            break

    storage_domain_rows = []

    if isinstance(storage_domain_payload, dict):

        if storage_domain_payload.get("tipo") == "tabla":
            detalles = storage_domain_payload.get("detalles") or {}
            storage_domain_rows = detalles.get("filas") or []

        elif "filas" in storage_domain_payload:
            storage_domain_rows = storage_domain_payload.get("filas") or []

    inserted_storage_domain = 0

    if isinstance(storage_domain_rows, list) and storage_domain_rows:

        rows_to_insert = (
            storage_domain_rows[:cantidadRegistroPrueba]
            if boolPrueba
            else storage_domain_rows
        )

        inserted_storage_domain = insert_storage_domain_subpool_rows(
            cursor,
            archivo_id,
            fechaActual,
            rows_to_insert,
            batch_size=1000
        )

        conn.commit()

    # =====================================================
    # 6) INSERTAR SYSTEM STATUS
    # =====================================================
    system_status_payload = None

    for k, v in diccionarioSegmentos.items():
        if str(k).strip().lower() == "system status":
            system_status_payload = v
            break

    system_status_data = {}

    if isinstance(system_status_payload, dict):

        if system_status_payload.get("tipo") == "informacion":
            detalles = system_status_payload.get("detalles") or {}
            system_status_data = detalles.get("datos") or {}

        elif "datos" in system_status_payload:
            system_status_data = system_status_payload.get("datos") or {}

    inserted_system_status = 0

    if isinstance(system_status_data, dict) and system_status_data:
        inserted_system_status = insert_system_status_row(
            cursor,
            archivo_id,
            fechaActual,
            system_status_data
        )

        conn.commit()

    # =====================================================
    # 7) INSERTAR MONITORING
    # =====================================================
    monitoring_payload = None

    for k, v in diccionarioSegmentos.items():
        if str(k).strip().lower() == "monitoring":
            monitoring_payload = v
            break

    monitoring_data = {}

    if isinstance(monitoring_payload, dict):

        if monitoring_payload.get("tipo") == "informacion":
            detalles = monitoring_payload.get("detalles") or {}
            monitoring_data = detalles.get("datos") or {}

        elif "datos" in monitoring_payload:
            monitoring_data = monitoring_payload.get("datos") or {}

    inserted_monitoring = 0

    if isinstance(monitoring_data, dict) and monitoring_data:
        inserted_monitoring = insert_monitoring_row(
            cursor,
            archivo_id,
            fechaActual,
            monitoring_data
        )

        conn.commit()

    print(
        f"Archivo: {archivo_nombre} (id={archivo_id}) | "
        f"Programs insertados: {inserted_prog} | "
        f"Temporary Storage Queues insertadas: {inserted_tsq} | "
        f"Files insertados: {inserted_files} | "
        f"Transactions insertadas: {inserted_tx} | "
        f"Storage Domain Subpools insertados: {inserted_storage_domain} | "
        f"System Status insertado: {inserted_system_status} | "
        f"Monitoring insertado: {inserted_monitoring}"
    )

    conn.close()


# Validación adicional para tabla cics_temporary_storage_queues, aunque no se inserta información en ella actualmente
def validar_tabla_temporary_storage_queues(cursor) -> None:
    """
    Valida que exista la tabla cics_temporary_storage_queues.
    """
    cursor.execute("""
        SELECT 1
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE = 'BASE TABLE'
          AND TABLE_NAME = 'cics_temporary_storage_queues'
    """)
    row = cursor.fetchone()
    if not row:
        raise RuntimeError("No existe la tabla requerida: cics_temporary_storage_queues")
    

# Aunque no se inserta información en esta tabla actualmente, definimos las columnas esperadas para futuras implementaciones
def get_temporary_storage_queues_forced_columns() -> list[str]:
    return [
        "tsQueueName",
        "tsqueueLocation",
        "numberOfItems",
        "minItemLength",
        "maxItemLength",
        "tsqueueFlength",
        "tranId",
        "lastusedInterval",
        "recoverable",
        "expiryInterval",
    ]
    
# Aunque no se inserta información en esta tabla actualmente, definimos la función de parseo para futuras implementaciones
def parse_temporary_storage_queues_segment(
    lines: list[str],
    start_idx: int
) -> tuple[list[str], list[dict], int]:
    """
    Parsea Temporary Storage Queues usando tokens.
    Más robusto para evitar truncamientos y permitir valores con comas.
    """
    headers = get_temporary_storage_queues_forced_columns()

    def _normalize_fixed(line: str) -> str:
        s = line.rstrip("\n\r")
        m = re.match(r"^(\s*)0(.*)$", s)
        if m:
            s = m.group(1) + m.group(2)
        return s

    def _is_omit(line: str) -> bool:
        if is_page_header(line) or line.strip() == "" or is_separator_line(line):
            return True
        if re.match(r"^\s*\+\s*_+", line):
            return True
        return False

    def _is_data_row(line: str) -> bool:
        s = _normalize_fixed(line).strip()
        if not s:
            return False

        low = s.lower()

        if "tsqueue name" in low or "location" in low or "interval" in low:
            return False
        if s.startswith("-"):
            return False

        return bool(re.match(r"^\S+", s))

    def _is_valid_tsq_row(row: dict) -> bool:
        tsq_name = str(row.get("tsQueueName", "") or "").strip()
        tsq_loc = str(row.get("tsqueueLocation", "") or "").strip()
        number_items = str(row.get("numberOfItems", "") or "").strip()
        min_len = str(row.get("minItemLength", "") or "").strip()
        max_len = str(row.get("maxItemLength", "") or "").strip()
        flength = str(row.get("tsqueueFlength", "") or "").strip()
        tran_id = str(row.get("tranId", "") or "").strip()
        last_used = str(row.get("lastusedInterval", "") or "").strip()
        recoverable = str(row.get("recoverable", "") or "").strip()
        expiry = str(row.get("expiryInterval", "") or "").strip()

        if not tsq_name:
            return False

        if " " in tsq_name and not tsq_name.startswith("�"):
            return False

        if tsq_loc and tsq_loc not in {"Main", "Auxiliary", "Aux"}:
            return False

        if number_items and not re.fullmatch(r"\d{1,3}(,\d{3})*|\d+", number_items):
            return False

        if min_len and not re.fullmatch(r"\d{1,3}(,\d{3})*|\d+", min_len):
            return False

        if max_len and not re.fullmatch(r"\d{1,3}(,\d{3})*|\d+", max_len):
            return False

        if flength and not re.fullmatch(r"\d{1,3}(,\d{3})*|\d+", flength):
            return False

        if tran_id and not re.fullmatch(r"[A-Z0-9]{3,4}", tran_id):
            return False

        if last_used and not re.fullmatch(r"\d{3}-\d{2}:\d{2}:\d{2}", last_used):
            return False

        if recoverable and recoverable not in {"Yes", "No"}:
            return False

        if expiry and not re.fullmatch(r"\d{3}-\d{2}", expiry):
            return False

        return True

    i = start_idx

    while i < len(lines):
        if _is_omit(lines[i]):
            i += 1
            continue

        low = _normalize_fixed(lines[i]).lower()
        if "tsqueue name" in low or "location" in low or "interval" in low:
            i += 1
            continue

        break

    rows: list[dict] = []

    while i < len(lines):
        if _is_omit(lines[i]):
            i += 1
            continue

        if reached_segment_boundary(lines[i]) or _is_totals_line(lines[i]):
            break

        if not _is_data_row(lines[i]):
            i += 1
            continue

        row_line = _normalize_fixed(lines[i]).strip()
        parts = re.findall(r"\S+", row_line)

        if len(parts) < 10:
            i += 1
            continue

        parts = parts[:10]

        row = {
            "tsQueueName": str(parts[0]).strip(),
            "tsqueueLocation": str(parts[1]).strip(),
            "numberOfItems": str(parts[2]).strip().replace(",", ""),
            "minItemLength": str(parts[3]).strip().replace(",", ""),
            "maxItemLength": str(parts[4]).strip().replace(",", ""),
            "tsqueueFlength": str(parts[5]).strip().replace(",", ""),
            "tranId": str(parts[6]).strip(),
            "lastusedInterval": str(parts[7]).strip(),
            "recoverable": str(parts[8]).strip(),
            "expiryInterval": str(parts[9]).strip(),
        }

        if not _is_valid_tsq_row(row):
            i += 1
            continue

        rows.append(row)
        i += 1

    return headers, rows, i




# Aunque no se inserta información en esta tabla actualmente, definimos la función de inserción para futuras implementaciones, usando executemany por lotes para mejor rendimiento
def insert_temporary_storage_queues_rows(
    cursor,
    archivo_id: int,
    fecha: str,
    rows: list[dict],
    batch_size: int = 1000
) -> int:
    """
    Inserta filas del segmento Temporary Storage Queues en cics_temporary_storage_queues.
    Adaptada para columnas INT.
    """
    sql = """
    INSERT INTO cics_temporary_storage_queues
    (
        archivo, fecha, tsQueueName, tsqueueLocation, numberOfItems,
        minItemLength, maxItemLength, tsqueueFlength, tranId,
        lastusedInterval, recoverable, expiryInterval
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    inserted = 0
    total_rows = 0
    skipped_empty_name = 0
    batch = []

    try:
        cursor.fast_executemany = True
    except Exception:
        pass

    for r in rows:
        total_rows += 1

        if not isinstance(r, dict):
            continue

        tsQueueName = str(r.get("tsQueueName", "") or "").strip()
        if not tsQueueName:
            skipped_empty_name += 1
            continue

        tsqueueLocation = str(r.get("tsqueueLocation", "") or "").strip()
        numberOfItems = to_int_or_none(r.get("numberOfItems", ""))
        minItemLength = to_int_or_none(r.get("minItemLength", ""))
        maxItemLength = to_int_or_none(r.get("maxItemLength", ""))
        tsqueueFlength = to_int_or_none(r.get("tsqueueFlength", ""))
        tranId = str(r.get("tranId", "") or "").strip()
        lastusedInterval = str(r.get("lastusedInterval", "") or "").strip()
        recoverable = str(r.get("recoverable", "") or "").strip()
        expiryInterval = str(r.get("expiryInterval", "") or "").strip()

        batch.append((
            archivo_id,
            fecha,
            tsQueueName,
            tsqueueLocation,
            numberOfItems,
            minItemLength,
            maxItemLength,
            tsqueueFlength,
            tranId,
            lastusedInterval,
            recoverable,
            expiryInterval
        ))

        if len(batch) >= batch_size:
            cursor.executemany(sql, batch)
            inserted += len(batch)
            batch.clear()

    if batch:
        cursor.executemany(sql, batch)
        inserted += len(batch)

    print(
        f"Temporary Storage Queues: total_rows={total_rows}, "
        f"inserted={inserted}, skipped_empty_name={skipped_empty_name}"
    )

    return inserted





def get_files_forced_columns() -> list[str]:
    return [
        "fileName",
        "accessMethod",
        "fileType",
        "remoteFileName",
        "remoteSystem",
        "lsrPool",
        "rls",
        "dataTableType",
        "cfdtPoolName",
        "recoveryStatus",
        "strings",
        "buffersIndex",
        "buffersData",
    ]


# definición de la función de inserción para el segmento Files
def parse_files_segment(
    lines: list[str],
    start_idx: int
) -> tuple[list[str], list[dict], int]:
    """
    Parsea el segmento Files usando tokens por espacios.
    Evita guardar encabezados como registros.
    """

    headers = get_files_forced_columns()

    def _normalize_fixed(line: str) -> str:
        s = line.rstrip("\n\r")
        m = re.match(r"^(\s*)0(.*)$", s)
        if m:
            s = m.group(1) + m.group(2)
        return s

    def _is_omit(line: str) -> bool:
        if is_page_header(line) or line.strip() == "" or is_separator_line(line):
            return True
        if re.match(r"^\s*\+\s*_+", line):
            return True
        return False

    def _looks_like_header_text(s: str) -> bool:
        low = s.lower()
        header_words = [
            "filename", "file name",
            "accessmethod", "access method", "access",
            "filetype", "file type", "file",
            "remotefilename", "remotefilename", "remote file", "remote",
            "remotesystem", "remote system",
            "lsrpool", "lsr pool",
            "datatabletype", "data table type",
            "cfdtpoolname", "cfdt pool name",
            "recoverystatus", "recovery status",
            "strings",
            "buffersindex", "buffers index",
            "buffersdata", "buffers data",
            "table", "data"
        ]
        return any(word in low for word in header_words)

    def _is_data_row(line: str) -> bool:
        s = _normalize_fixed(line).strip()
        if not s:
            return False

        if s.startswith("-"):
            return False

        # descartar encabezados
        if _looks_like_header_text(s):
            return False

        # una fila real debe empezar con nombre de archivo válido
        first = re.findall(r"\S+", s)
        if not first:
            return False

        first_token = first[0]

        # evita tomar textos de encabezado como "Access", "File", etc.
        if first_token.lower() in {
            "filename", "access", "file", "remote", "lsr",
            "table", "data", "buffers", "recovery"
        }:
            return False

        return True

    i = start_idx

    # saltar encabezados
    while i < len(lines):
        if _is_omit(lines[i]):
            i += 1
            continue

        low = _normalize_fixed(lines[i]).lower()
        if _looks_like_header_text(low):
            i += 1
            continue

        break

    rows: list[dict] = []

    while i < len(lines):
        if _is_omit(lines[i]):
            i += 1
            continue

        if reached_segment_boundary(lines[i]) or _is_totals_line(lines[i]):
            break

        row_line = _normalize_fixed(lines[i]).strip()

        if not _is_data_row(lines[i]):
            i += 1
            continue

        parts = re.findall(r"\S+", row_line)
        if len(parts) < 2:
            i += 1
            continue

        # primeros 2 obligatorios
        file_name = parts[0]
        access_method = parts[1]

        # últimos 6 obligatorios de la derecha
        tail = parts[2:]
        if len(tail) >= 6:
            lsr_pool = tail[-6]
            rls = tail[-5]
            recovery_status = tail[-4]
            strings = tail[-3]
            buffers_index = tail[-2]
            buffers_data = tail[-1]
            middle = tail[:-6]
        else:
            padded = ([""] * (6 - len(tail))) + tail
            lsr_pool, rls, recovery_status, strings, buffers_index, buffers_data = padded
            middle = []

        # columnas opcionales del medio
        file_type = middle[0] if len(middle) >= 1 else ""
        remote_file_name = middle[1] if len(middle) >= 2 else ""
        remote_system = middle[2] if len(middle) >= 3 else ""
        data_table_type = middle[3] if len(middle) >= 4 else ""
        cfdt_pool_name = middle[4] if len(middle) >= 5 else ""

        row = {
            "fileName": str(file_name).strip(),
            "accessMethod": str(access_method).strip(),
            "fileType": str(file_type).strip(),
            "remoteFileName": str(remote_file_name).strip(),
            "remoteSystem": str(remote_system).strip(),
            "lsrPool": str(lsr_pool).strip(),
            "rls": str(rls).strip(),
            "dataTableType": str(data_table_type).strip(),
            "cfdtPoolName": str(cfdt_pool_name).strip(),
            "recoveryStatus": str(recovery_status).strip(),
            "strings": str(strings).strip(),
            "buffersIndex": str(buffers_index).strip(),
            "buffersData": str(buffers_data).strip(),
        }

        # filtro final extra por si algún header se coló
        if _looks_like_header_text(" ".join(row.values())):
            i += 1
            continue

        rows.append(row)
        i += 1

    return headers, rows, i

# definición de la función de inserción para el segmento Files
def insert_files_rows(
    cursor,
    archivo_id: int,
    fecha: str,
    rows: list[dict],
    batch_size: int = 1000
) -> int:
    """
    Inserta filas del segmento Files en cics_files usando executemany por lotes.
    Adaptada para strings, buffersIndex y buffersData como INT.
    """
    sql = """
    INSERT INTO cics_files
    (
        archivo, fecha, fileName, accessMethod, fileType, remoteFileName,
        remoteSystem, lsrPool, rls, dataTableType, cfdtPoolName,
        recoveryStatus, strings, buffersIndex, buffersData
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    inserted = 0
    total_rows = 0
    skipped_empty_name = 0
    batch = []

    try:
        cursor.fast_executemany = True
    except Exception:
        pass

    for r in rows:
        total_rows += 1

        if not isinstance(r, dict):
            continue

        fileName = str(r.get("fileName", "") or "").strip()
        if not fileName:
            skipped_empty_name += 1
            continue

        accessMethod = str(r.get("accessMethod", "") or "").strip()
        fileType = str(r.get("fileType", "") or "").strip()
        remoteFileName = str(r.get("remoteFileName", "") or "").strip()
        remoteSystem = str(r.get("remoteSystem", "") or "").strip()
        lsrPool = str(r.get("lsrPool", "") or "").strip()
        rls = str(r.get("rls", "") or "").strip()
        dataTableType = str(r.get("dataTableType", "") or "").strip()
        cfdtPoolName = str(r.get("cfdtPoolName", "") or "").strip()
        recoveryStatus = str(r.get("recoveryStatus", "") or "").strip()

        strings = to_int_or_none(r.get("strings", ""))
        buffersIndex = to_int_or_none(r.get("buffersIndex", ""))
        buffersData = to_int_or_none(r.get("buffersData", ""))

        batch.append((
            archivo_id,
            fecha,
            fileName,
            accessMethod,
            fileType,
            remoteFileName,
            remoteSystem,
            lsrPool,
            rls,
            dataTableType,
            cfdtPoolName,
            recoveryStatus,
            strings,
            buffersIndex,
            buffersData
        ))

        if len(batch) >= batch_size:
            cursor.executemany(sql, batch)
            inserted += len(batch)
            batch.clear()

    if batch:
        cursor.executemany(sql, batch)
        inserted += len(batch)

    print(
        f"Files: total_rows={total_rows}, inserted={inserted}, "
        f"skipped_empty_name={skipped_empty_name}"
    )

    return inserted


# Función para obtener las carpetas de un directorio de entrada, filtrando solo aquellas que tengan un nombre con formato de fecha YYYY-MM-DD, y ordenándolas de forma descendente por fecha.
def obtener_carpetas_fecha_ordenadas(directorio_entrada: Path) -> list[tuple[str, Path]]:
    carpetas = []

    for item in directorio_entrada.iterdir():
        if not item.is_dir():
            continue

        nombre = item.name.strip()

        try:
            fecha = datetime.strptime(nombre, "%Y-%m-%d").date()
            carpetas.append((fecha.isoformat(), item))
        except ValueError:
            continue

    carpetas.sort(key=lambda x: x[0], reverse=True)
    return carpetas


# Función para validar si una carpeta ya fue procesada, consultando la tabla cics_cargas por una combinación de fecha, nombre de carpeta y estado 'PROCESADO'.
def carpeta_ya_procesada(fecha_carpeta: str, nombre_carpeta: str) -> bool:
    conn = conectar_base_datos()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM cics_cargas
        WHERE fecha = ? AND carpeta = ? AND estado = 'PROCESADO'
    """, (fecha_carpeta, nombre_carpeta))

    row = cursor.fetchone()
    conn.close()

    return (row[0] or 0) > 0


# Función para registrar una carpeta como procesada, insertando un nuevo registro en la tabla cics_cargas con la fecha, nombre de carpeta y estado 'PROCESADO'.
def registrar_carpeta_procesada(fecha_carpeta: str, nombre_carpeta: str) -> None:
    conn = conectar_base_datos()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO cics_cargas (fecha, carpeta, estado)
        VALUES (?, ?, 'PROCESADO')
    """, (fecha_carpeta, nombre_carpeta))

    conn.commit()
    conn.close()
    

def get_storage_domain_subpool_forced_columns():
    return [
        "subPoolName",
        "location",
        "access",
        "elementType",
        "elementLength",
        "initialFree",
        "currentElements",
        "currentElementStg",
        "currentPageStg",
        "percentOfDSA",
        "peakPageStg"
    ]
    


def parse_storage_domain_subpool_segment(lines, start_idx):

    headers = get_storage_domain_subpool_forced_columns()
    rows = []

    i = start_idx

    while i < len(lines):

        line = lines[i].rstrip("\n")

        # fin segmento
        if reached_segment_boundary(line) or _is_totals_line(line):
            break

        if is_page_header(line):
            i += 1
            continue

        if not line.strip():
            i += 1
            continue

        low = line.lower()

        # omitir headers multilinea
        if (
            "subpool" in low
            or "location" in low
            or "element" in low
            or "page stg" in low
            or "% of" in low
        ):
            i += 1
            continue

        # remover prefijo 0
        line = re.sub(r"^\s*0\s+", "", line)

        # split robusto
        parts = re.split(r"\s{2,}", line.strip())

        # mínimo esperado
        if len(parts) < 10:
            i += 1
            continue

        try:

            while len(parts) < 11:
                parts.append("")

            row = {
                "subPoolName": parts[0].strip(),
                "location": parts[1].strip(),
                "access": parts[2].strip(),
                "elementType": parts[3].strip(),
                "elementLength": parts[4].replace(",", "").strip(),
                "initialFree": parts[5].strip(),
                "currentElements": parts[6].replace(",", "").strip(),
                "currentElementStg": parts[7].replace(",", "").strip(),
                "currentPageStg": parts[8].replace(",", "").strip(),
                "percentOfDSA": parts[9].replace("%", "").strip(),
                "peakPageStg": parts[10].replace(",", "").strip()
            }

            # filtros defensivos
            if not row["subPoolName"]:
                i += 1
                continue

            if "subpool" in row["subPoolName"].lower():
                i += 1
                continue

            rows.append(row)

        except Exception:
            pass

        i += 1

    return headers, rows, i


def insert_storage_domain_subpool_rows(
    cursor,
    archivo_id: int,
    fecha: str,
    rows: list[dict],
    batch_size: int = 1000
) -> int:

    sql = """
    INSERT INTO cics_storage_domain_subpool
    (
        archivo,
        fecha,
        subPoolName,
        location,
        access,
        elementType,
        elementLength,
        initialFree,
        currentElements,
        currentElementStg,
        currentPageStg,
        percentOfDSA,
        peakPageStg
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    inserted = 0
    total_rows = 0
    skipped_empty_name = 0
    batch = []

    try:
        cursor.fast_executemany = True
    except Exception:
        pass

    for r in rows:

        total_rows += 1

        if not isinstance(r, dict):
            continue

        subPoolName = str(r.get("subPoolName", "") or "").strip()

        if not subPoolName:
            skipped_empty_name += 1
            continue

        location = str(r.get("location", "") or "").strip()
        access = str(r.get("access", "") or "").strip()
        elementType = str(r.get("elementType", "") or "").strip()

        elementLength = to_int_or_none(r.get("elementLength", ""))
        initialFree = str(r.get("initialFree", "") or "").strip()

        currentElements = to_int_or_none(r.get("currentElements", ""))
        currentElementStg = to_int_or_none(r.get("currentElementStg", ""))

        currentPageStg = str(r.get("currentPageStg", "") or "").strip()

        percentOfDSA_raw = str(r.get("percentOfDSA", "") or "").replace("%", "").strip()

        try:
            percentOfDSA = float(percentOfDSA_raw) if percentOfDSA_raw else None
        except Exception:
            percentOfDSA = None

        peakPageStg = str(r.get("peakPageStg", "") or "").strip()

        batch.append((
            archivo_id,
            fecha,
            subPoolName,
            location,
            access,
            elementType,
            elementLength,
            initialFree,
            currentElements,
            currentElementStg,
            currentPageStg,
            percentOfDSA,
            peakPageStg
        ))

        if len(batch) >= batch_size:
            cursor.executemany(sql, batch)
            inserted += len(batch)
            batch.clear()

    if batch:
        cursor.executemany(sql, batch)
        inserted += len(batch)

    print(
        f"Storage Domain Subpools: total_rows={total_rows}, "
        f"inserted={inserted}, skipped_empty_name={skipped_empty_name}"
    )

    return inserted


# Funciones para el segmento System Status
# Patrón: columnas forzadas -> parseo -> inserción

def get_system_status_forced_columns() -> list[str]:
    """
    Retorna la lista de columnas esperadas para el segmento System Status.
    """
    return [
        "mvsProductName",
        "cicsStartup",
        "cicsStatus",
        "cecMachineType",
        "vtamOpenStatus",
        "ircStatus",
        "ircXcfGroupName",
        "storageProtection",
        "transactionIsolation",
        "reentrantPrograms",
        "execStorageCommandChecking",
        "forceQuasiReentrant",
        "programAutoinstall",
        "terminalAutoinstall",
        "activityKeypointFrequency",
        "logstreamDeferredForceInterval",
        "rlsStatus",
        "rrmsMvsStatus",
        "db2ConnectionName",
        "cicsTsLevel",
        "wlmMode",
        "wlmServer",
        "wlmManageRegionGoals",
        "wlmWorkloadName",
        "wlmServiceClass",
        "wlmReportClass",
        "wlmResourceGroup",
        "wlmGoalType",
        "wlmGoalValue",
        "wlmGoalImportance",
        "wlmCpuCritical",
        "wlmStorageCritical",
        "tcpIpStatus",
        "maxIpSockets",
        "activeIpSockets",
        "webGarbageCollectionInterval",
        "terminalInputTimeoutInterval",
    ]


def parse_system_status_segment(lines: list[str], start_idx: int) -> tuple[list[str], dict, int]:
    """
    Parsea el segmento System Status (información de dos columnas con KV).
    Retorna: (columnas, diccionario_datos, índice_siguiente)
    """
    
    headers = get_system_status_forced_columns()
    data = {h: "" for h in headers}
    
    # Mapeo simplificado por palabras clave
    field_mapping = {
        "mvs product": "mvsProductName",
        "cics startup": "cicsStartup",
        "cics status": "cicsStatus",
        "cec machine": "cecMachineType",
        "vtam open": "vtamOpenStatus",
        "irc status": "ircStatus",
        "irc xcf": "ircXcfGroupName",
        "storage protection": "storageProtection",
        "transaction isolation": "transactionIsolation",
        "reentrant": "reentrantPrograms",
        "exec storage": "execStorageCommandChecking",
        "force quasi": "forceQuasiReentrant",
        "program autoinstall": "programAutoinstall",
        "terminal autoinstall": "terminalAutoinstall",
        "activity keypoint": "activityKeypointFrequency",
        "logstream deferred": "logstreamDeferredForceInterval",
        "rls status": "rlsStatus",
        "rrms/mvs": "rrmsMvsStatus",
        "db2 connection": "db2ConnectionName",
        "cics transaction server": "cicsTsLevel",
        "mvs workload manager": "wlmMode",
        "wlm server": "wlmServer",
        "wlm manage": "wlmManageRegionGoals",
        "wlm workload": "wlmWorkloadName",
        "wlm service": "wlmServiceClass",
        "wlm report": "wlmReportClass",
        "wlm resource": "wlmResourceGroup",
        "wlm goal type": "wlmGoalType",
        "wlm goal value": "wlmGoalValue",
        "wlm goal importance": "wlmGoalImportance",
        "wlm cpu": "wlmCpuCritical",
        "wlm storage": "wlmStorageCritical",
        "tcp/ip": "tcpIpStatus",
        "max ip": "maxIpSockets",
        "active ip": "activeIpSockets",
        "web garbage": "webGarbageCollectionInterval",
        "terminal input": "terminalInputTimeoutInterval",
    }
    
    i = start_idx
    
    while i < len(lines):
        line = lines[i]
        
        if line.strip().startswith("0----") or line.strip().startswith("+_"):
            break
        
        if not line.strip() or line.strip().startswith("Applid"):
            i += 1
            continue
        
        # Remover prefijo "0"
        line_clean = re.sub(r"^\s*0\s+", "", line)
        
        # Intentar dividir en dos columnas
        split_result = split_two_columns(line_clean)
        columns = [split_result[0], split_result[1]] if split_result else [line_clean]
        
        for col_text in columns:
            if not col_text or not col_text.strip():
                continue
            
            # Buscar todos los pares key: value en esta columna
            # Patrón: cualquier texto antes de ":" y cualquier texto después
            pattern = r"([^:]+?):\s+([^:]+?)(?=$|\s{3,})"
            matches = re.findall(pattern, col_text)
            
            for label_raw, value_raw in matches:
                label = label_raw.strip()
                value = value_raw.strip()
                
                # Limpiar puntos de relleno del label
                label = re.sub(r"\.+", " ", label).strip().lower()
                label = re.sub(r"\s+", " ", label)
                
                if not label or not value:
                    continue
                
                # Encontrar el campo correspondiente
                for pattern_key, column_name in field_mapping.items():
                    if pattern_key in label:
                        if data[column_name] == "":
                            data[column_name] = value
                        break
        
        i += 1
    
    return headers, data, i


def insert_system_status_row(
    cursor,
    archivo_id: int,
    fecha: str,
    data: dict
) -> int:
    """
    Inserta un registro del segmento System Status en cics_system_status.
    Retorna 1 si se insertó correctamente, 0 si se omitió.
    """
    
    sql = """
    INSERT INTO cics_system_status
    (
        archivo, fecha, mvsProductName, cicsStartup, cicsStatus, cecMachineType,
        vtamOpenStatus, ircStatus, ircXcfGroupName, storageProtection,
        transactionIsolation, reentrantPrograms, execStorageCommandChecking,
        forceQuasiReentrant, programAutoinstall, terminalAutoinstall,
        activityKeypointFrequency, logstreamDeferredForceInterval, rlsStatus,
        rrmsMvsStatus, db2ConnectionName, cicsTsLevel, wlmMode, wlmServer,
        wlmManageRegionGoals, wlmWorkloadName, wlmServiceClass, wlmReportClass,
        wlmResourceGroup, wlmGoalType, wlmGoalValue, wlmGoalImportance,
        wlmCpuCritical, wlmStorageCritical, tcpIpStatus, maxIpSockets,
        activeIpSockets, webGarbageCollectionInterval, terminalInputTimeoutInterval
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    
    if not isinstance(data, dict):
        print("System Status: data no es diccionario, se omite")
        return 0
    
    mvsProductName = str(data.get("mvsProductName", "") or "").strip()
    cicsStartup = str(data.get("cicsStartup", "") or "").strip()
    cicsStatus = str(data.get("cicsStatus", "") or "").strip()
    cecMachineType = str(data.get("cecMachineType", "") or "").strip()
    vtamOpenStatus = str(data.get("vtamOpenStatus", "") or "").strip()
    ircStatus = str(data.get("ircStatus", "") or "").strip()
    ircXcfGroupName = str(data.get("ircXcfGroupName", "") or "").strip()
    storageProtection = str(data.get("storageProtection", "") or "").strip()
    transactionIsolation = str(data.get("transactionIsolation", "") or "").strip()
    reentrantPrograms = str(data.get("reentrantPrograms", "") or "").strip()
    execStorageCommandChecking = str(data.get("execStorageCommandChecking", "") or "").strip()
    forceQuasiReentrant = str(data.get("forceQuasiReentrant", "") or "").strip()
    programAutoinstall = str(data.get("programAutoinstall", "") or "").strip()
    terminalAutoinstall = str(data.get("terminalAutoinstall", "") or "").strip()
    
    activityKeypointFrequency = to_int_or_none(data.get("activityKeypointFrequency", ""))
    logstreamDeferredForceInterval = to_int_or_none(data.get("logstreamDeferredForceInterval", ""))
    
    rlsStatus = str(data.get("rlsStatus", "") or "").strip()
    rrmsMvsStatus = str(data.get("rrmsMvsStatus", "") or "").strip()
    db2ConnectionName = str(data.get("db2ConnectionName", "") or "").strip()
    
    cicsTsLevel = str(data.get("cicsTsLevel", "") or "").strip()
    wlmMode = str(data.get("wlmMode", "") or "").strip()
    wlmServer = str(data.get("wlmServer", "") or "").strip()
    wlmManageRegionGoals = str(data.get("wlmManageRegionGoals", "") or "").strip()
    wlmWorkloadName = str(data.get("wlmWorkloadName", "") or "").strip()
    wlmServiceClass = str(data.get("wlmServiceClass", "") or "").strip()
    wlmReportClass = str(data.get("wlmReportClass", "") or "").strip()
    wlmResourceGroup = str(data.get("wlmResourceGroup", "") or "").strip()
    wlmGoalType = str(data.get("wlmGoalType", "") or "").strip()
    
    wlmGoalValue = to_int_or_none(data.get("wlmGoalValue", ""))
    wlmGoalImportance = to_int_or_none(data.get("wlmGoalImportance", ""))
    
    wlmCpuCritical = str(data.get("wlmCpuCritical", "") or "").strip()
    wlmStorageCritical = str(data.get("wlmStorageCritical", "") or "").strip()
    
    tcpIpStatus = str(data.get("tcpIpStatus", "") or "").strip()
    maxIpSockets = to_int_or_none(data.get("maxIpSockets", ""))
    activeIpSockets = to_int_or_none(data.get("activeIpSockets", ""))
    webGarbageCollectionInterval = to_int_or_none(data.get("webGarbageCollectionInterval", ""))
    terminalInputTimeoutInterval = to_int_or_none(data.get("terminalInputTimeoutInterval", ""))
    
    try:
        cursor.execute(sql, (
            archivo_id, fecha,
            mvsProductName, cicsStartup, cicsStatus, cecMachineType,
            vtamOpenStatus, ircStatus, ircXcfGroupName, storageProtection,
            transactionIsolation, reentrantPrograms, execStorageCommandChecking,
            forceQuasiReentrant, programAutoinstall, terminalAutoinstall,
            activityKeypointFrequency, logstreamDeferredForceInterval, rlsStatus,
            rrmsMvsStatus, db2ConnectionName, cicsTsLevel, wlmMode, wlmServer,
            wlmManageRegionGoals, wlmWorkloadName, wlmServiceClass, wlmReportClass,
            wlmResourceGroup, wlmGoalType, wlmGoalValue, wlmGoalImportance,
            wlmCpuCritical, wlmStorageCritical, tcpIpStatus, maxIpSockets,
            activeIpSockets, webGarbageCollectionInterval, terminalInputTimeoutInterval
        ))
        
        print(f"System Status: registro insertado correctamente")
        return 1
    
    except Exception as e:
        print(f"System Status: error al insertar - {e}")
        return 0


def get_monitoring_forced_columns() -> list[str]:
    return [
        "monitoring",
        "exceptionClass",
        "performanceClass",
        "resourceClass",
        "identityClass",
        "dataCompressionOption",
        "applicationNaming",
        "rmiOption",
        "converseOption",
        "syncpointOption",
        "timeOption",
        "frequency",
        "mctProgramName",
        "dplResourceLimit",
        "fileResourceLimit",
        "tsqueueResourceLimit",
        "urimapResourceLimit",
        "webserviceResourceLimit",
        "exceptionClassRecords",
        "exceptionRecordsSuppressed",
        "performanceClassRecords",
        "performanceRecordsSuppressed",
        "resourceClassRecords",
        "resourceRecordsSuppressed",
        "identityClassRecords",
        "identityRecordsSuppressed",
        "monitoringSmfRecords",
        "monitoringSmfErrors",
        "monitoringSmfRecordsCompressed",
        "monitoringSmfRecordsNotCompressed",
        "percentageSmfRecordsCompressed",
    ]


def parse_monitoring_segment(lines: list[str], start_idx: int) -> tuple[list[str], dict, int]:
    headers = get_monitoring_forced_columns()
    data = {h: "" for h in headers}

    field_mapping = {
        "monitoring smf records not compressed": "monitoringSmfRecordsNotCompressed",
        "monitoring smf records compressed": "monitoringSmfRecordsCompressed",
        "percentage of smf records compressed": "percentageSmfRecordsCompressed",
        "monitoring smf records": "monitoringSmfRecords",
        "monitoring smf errors": "monitoringSmfErrors",
        "exception records suppressed": "exceptionRecordsSuppressed",
        "exception class records": "exceptionClassRecords",
        "performance records suppressed": "performanceRecordsSuppressed",
        "performance class records": "performanceClassRecords",
        "resource records suppressed": "resourceRecordsSuppressed",
        "resource class records": "resourceClassRecords",
        "identity records suppressed": "identityRecordsSuppressed",
        "identity class records": "identityClassRecords",
        "data compression option": "dataCompressionOption",
        "application naming": "applicationNaming",
        "converse option": "converseOption",
        "syncpoint option": "syncpointOption",
        "mct program name": "mctProgramName",
        "dpl resource limit": "dplResourceLimit",
        "file resource limit": "fileResourceLimit",
        "tsqueue resource limit": "tsqueueResourceLimit",
        "urimap resource limit": "urimapResourceLimit",
        "webservice resource limit": "webserviceResourceLimit",
        "exception class": "exceptionClass",
        "performance class": "performanceClass",
        "resource class": "resourceClass",
        "identity class": "identityClass",
        "rmi option": "rmiOption",
        "time option": "timeOption",
        "frequency": "frequency",
        "monitoring": "monitoring",
    }

    i = start_idx
    while i < len(lines):
        line = lines[i]

        if line.strip().startswith("0----") or line.strip().startswith("+_"):
            break

        if not line.strip() or line.strip().startswith("Applid"):
            i += 1
            continue

        line_clean = re.sub(r"^\s*0\s+", "", line)
        split_result = split_two_columns(line_clean)
        columns = [split_result[0], split_result[1]] if split_result else [line_clean]

        for col_text in columns:
            if not col_text or not col_text.strip():
                continue

            matches = re.findall(r"([^:]+?):\s+([^:]+?)(?=$|\s{3,})", col_text)

            for label_raw, value_raw in matches:
                label = re.sub(r"\.+", " ", label_raw).strip().lower()
                label = re.sub(r"\s+", " ", label)
                value = value_raw.strip()

                if not label or value == "":
                    continue

                for pattern_key, column_name in field_mapping.items():
                    if pattern_key in label:
                        if data[column_name] == "":
                            data[column_name] = value
                        break

        i += 1

    return headers, data, i


def insert_monitoring_row(
    cursor,
    archivo_id: int,
    fecha: str,
    data: dict
) -> int:
    sql = """
    INSERT INTO cics_monitoring
    (
        archivo, fecha, monitoring, exceptionClass, performanceClass,
        resourceClass, identityClass, dataCompressionOption, applicationNaming,
        rmiOption, converseOption, syncpointOption, timeOption, frequency,
        mctProgramName, dplResourceLimit, fileResourceLimit, tsqueueResourceLimit,
        urimapResourceLimit, webserviceResourceLimit, exceptionClassRecords,
        exceptionRecordsSuppressed, performanceClassRecords, performanceRecordsSuppressed,
        resourceClassRecords, resourceRecordsSuppressed, identityClassRecords,
        identityRecordsSuppressed, monitoringSmfRecords, monitoringSmfErrors,
        monitoringSmfRecordsCompressed, monitoringSmfRecordsNotCompressed,
        percentageSmfRecordsCompressed
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    if not isinstance(data, dict):
        print("Monitoring: data no es diccionario, se omite")
        return 0

    monitoring = str(data.get("monitoring", "") or "").strip()
    exceptionClass = str(data.get("exceptionClass", "") or "").strip()
    performanceClass = str(data.get("performanceClass", "") or "").strip()
    resourceClass = str(data.get("resourceClass", "") or "").strip()
    identityClass = str(data.get("identityClass", "") or "").strip()
    dataCompressionOption = str(data.get("dataCompressionOption", "") or "").strip()
    applicationNaming = str(data.get("applicationNaming", "") or "").strip()
    rmiOption = str(data.get("rmiOption", "") or "").strip()
    converseOption = str(data.get("converseOption", "") or "").strip()
    syncpointOption = str(data.get("syncpointOption", "") or "").strip()
    timeOption = str(data.get("timeOption", "") or "").strip()
    frequency = str(data.get("frequency", "") or "").strip()
    mctProgramName = str(data.get("mctProgramName", "") or "").strip()

    dplResourceLimit = to_int_or_none(data.get("dplResourceLimit", ""))
    fileResourceLimit = to_int_or_none(data.get("fileResourceLimit", ""))
    tsqueueResourceLimit = to_int_or_none(data.get("tsqueueResourceLimit", ""))
    urimapResourceLimit = to_int_or_none(data.get("urimapResourceLimit", ""))
    webserviceResourceLimit = to_int_or_none(data.get("webserviceResourceLimit", ""))

    exceptionClassRecords = to_int_or_none(data.get("exceptionClassRecords", ""))
    exceptionRecordsSuppressed = to_int_or_none(data.get("exceptionRecordsSuppressed", ""))
    performanceClassRecords = to_int_or_none(data.get("performanceClassRecords", ""))
    performanceRecordsSuppressed = to_int_or_none(data.get("performanceRecordsSuppressed", ""))
    resourceClassRecords = to_int_or_none(data.get("resourceClassRecords", ""))
    resourceRecordsSuppressed = to_int_or_none(data.get("resourceRecordsSuppressed", ""))
    identityClassRecords = to_int_or_none(data.get("identityClassRecords", ""))
    identityRecordsSuppressed = to_int_or_none(data.get("identityRecordsSuppressed", ""))
    monitoringSmfRecords = to_int_or_none(data.get("monitoringSmfRecords", ""))
    monitoringSmfErrors = to_int_or_none(data.get("monitoringSmfErrors", ""))
    monitoringSmfRecordsCompressed = to_int_or_none(data.get("monitoringSmfRecordsCompressed", ""))
    monitoringSmfRecordsNotCompressed = to_int_or_none(data.get("monitoringSmfRecordsNotCompressed", ""))
    percentageSmfRecordsCompressed = to_float_or_none(data.get("percentageSmfRecordsCompressed", ""))

    try:
        cursor.execute(sql, (
            archivo_id,
            fecha,
            monitoring,
            exceptionClass,
            performanceClass,
            resourceClass,
            identityClass,
            dataCompressionOption,
            applicationNaming,
            rmiOption,
            converseOption,
            syncpointOption,
            timeOption,
            frequency,
            mctProgramName,
            dplResourceLimit,
            fileResourceLimit,
            tsqueueResourceLimit,
            urimapResourceLimit,
            webserviceResourceLimit,
            exceptionClassRecords,
            exceptionRecordsSuppressed,
            performanceClassRecords,
            performanceRecordsSuppressed,
            resourceClassRecords,
            resourceRecordsSuppressed,
            identityClassRecords,
            identityRecordsSuppressed,
            monitoringSmfRecords,
            monitoringSmfErrors,
            monitoringSmfRecordsCompressed,
            monitoringSmfRecordsNotCompressed,
            percentageSmfRecordsCompressed,
        ))

        print("Monitoring: registro insertado correctamente")
        return 1

    except Exception as e:
        print(f"Monitoring: error al insertar - {e}")
        return 0