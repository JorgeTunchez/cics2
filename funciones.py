from __future__ import annotations

from pathlib import Path
from conexionBD import *
import re

boolPrueba = False
cantidadRegistroPrueba = 5

# Valida si ya existen registros en la base de datos para la fecha indicada
def validarCargaFecha(fecha_str):
    conn = conectar_base_datos()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM cics_programs WHERE fecha = ?", (fecha_str,))
    countProgramas = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM cics_transactions WHERE fecha = ?", (fecha_str,))
    countTransacciones = cursor.fetchone()[0]
    
    conteoTotal = countProgramas + countTransacciones
    conn.close()
    return countProgramas, countTransacciones, conteoTotal


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

        # validar que empiece con nombre de programa
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

    # ---------------------------------------------------
    # 1) Encontrar la línea subheader correcta
    # ---------------------------------------------------
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
    # ---------------------------------------------------
    # 2) Si spans no salen 12, recalcular por data_samples
    # ---------------------------------------------------
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

    # saltar separadores posteriores al header
    while i < len(lines) and _is_omit(lines[i]):
        i += 1

    # ---------------------------------------------------
    # 3) Parsear filas fixed-width
    # ---------------------------------------------------
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

        # programName por regex
        mname = re.match(r"^\s*([A-Z0-9$#@]{3,})\b", row_line.strip())
        program_name = mname.group(1) if mname else ""

        # 2) columnas intermedias por spans, pero las últimas 2 desde la derecha
        middle_tokens = [row_line[a:b].strip() for (a, b) in spans[1:-2]]

        # extraer programSize y progLocn desde la derecha
        right_parts = re.findall(r"\S+", row_line.strip())

        prog_locn = right_parts[-1] if len(right_parts) >= 1 else ""
        program_size = right_parts[-2] if len(right_parts) >= 2 else ""

        tokens = [program_name] + middle_tokens + [program_size, prog_locn]

        # asegurar largo exacto
        if len(tokens) < len(headers):
            tokens += [""] * (len(headers) - len(tokens))
        elif len(tokens) > len(headers):
            tokens = tokens[:len(headers)]

        row = {headers[idx]: tokens[idx] for idx in range(len(headers))}

        for kf in ("timesUsed", "timesFetched", "timesNewCopy", "timesRemoved"):
            row[kf] = _norm(row.get(kf, ""))

        row["programSize"] = str(row.get("programSize", "") or "").strip()
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
        }

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

            # si viene segmento doble, lo saltamos
            split = split_two_columns(lines[j])
            if split and is_title_text(split[0]) and is_title_text(split[1]):
                while j < len(lines) and not reached_segment_boundary(lines[j]):
                    j += 1
                i = j
                continue

            # título simple
            title = lines[j].lstrip("-").strip()
            title_key = title.strip().lower()
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

    return out


# Conjunto de tablas requeridas en la base de datos para almacenar los segmentos extraídos de CICSADM Lite
_REQUIRED_TABLES = {"cics_archivos", "cics_segmento", "cics_programs", "cics_transactions", "cics_temporary_storage_queues", "cics_files"}


# Valida que existan las tablas requeridas en la base de datos, lanzando un error si alguna falta
def validar_tablas_requeridas(cursor) -> None:
    cursor.execute("""
        SELECT TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE = 'BASE TABLE'
          AND TABLE_NAME IN ('cics_archivos', 'cics_segmento', 'cics_programs', 'cics_transactions','cics_temporary_storage_queues','cics_files')
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
        timesUsed = _normalize_program_counter(str(r.get("timesUsed", "") or ""))
        timesFetched = _normalize_program_counter(str(r.get("timesFetched", "") or ""))
        totalFecthTime = str(r.get("totalFecthTime", "") or "").strip()
        AverageFetchTime = str(r.get("AverageFetchTime", "") or "").strip()
        libraryName = str(r.get("libraryName", "") or "").strip()

        libraryOffset_raw = str(r.get("libraryOffset", "") or "").strip()
        libraryOffset = _normalize_program_counter(libraryOffset_raw) if libraryOffset_raw else ""

        timesNewCopy = _normalize_program_counter(str(r.get("timesNewCopy", "") or ""))
        timesRemoved = _normalize_program_counter(str(r.get("timesRemoved", "") or ""))

        programSize_raw = str(r.get("programSize", "") or "").strip()
        programSize = programSize_raw.replace(",", "") if programSize_raw else ""

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
        attachCount = str(r.get("attachCount", "") or "")
        restartCount = str(r.get("restartCount", "") or "")
        dynamicLocal = str(r.get("dynamicLocal", "") or "")
        remoteStarts = str(r.get("remoteStarts", "") or "")
        storageViols = str(r.get("storageViols", "") or "")
        abendCount = str(r.get("abendCount", "") or "")

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
        rows_to_insert = prog_rows[:cantidadRegistroPrueba] if boolPrueba else prog_rows
        inserted_prog = insert_programs_rows(
            cursor, archivo_id, fechaActual, rows_to_insert, batch_size=1000
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
        rows_to_insert = tsq_rows[:cantidadRegistroPrueba] if boolPrueba else tsq_rows
        inserted_tsq = insert_temporary_storage_queues_rows(
            cursor, archivo_id, fechaActual, rows_to_insert, batch_size=1000
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
        rows_to_insert = files_rows[:cantidadRegistroPrueba] if boolPrueba else files_rows
        inserted_files = insert_files_rows(
            cursor, archivo_id, fechaActual, rows_to_insert, batch_size=1000
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
        rows_to_insert = tx_rows[:cantidadRegistroPrueba] if boolPrueba else tx_rows
        inserted_tx = insert_transactions_rows(
            cursor, archivo_id, fechaActual, rows_to_insert, batch_size=1000
        )
        conn.commit()

    print(
        f"Archivo: {archivo_nombre} (id={archivo_id}) | "
        f"Programs insertados: {inserted_prog} | "
        f"Temporary Storage Queues insertadas: {inserted_tsq} | "
        f"Files insertados: {inserted_files} | "
        f"Transactions insertadas: {inserted_tx}"
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
    Parsea el segmento Temporary Storage Queues como tabla fixed-width.

    Columnas esperadas:
      TSQueue Name
      Tsqueue Location
      Number of Items
      Min Item Length
      Max Item Length
      Tsqueue Flength
      Tranid
      Lastused Interval
      Recoverable
      Expiry Interval
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
        s = _normalize_fixed(line)
        if not s.strip():
            return False
        return bool(re.match(r"^\s*\S+", s))

    def _spans_from_subheader(sub: str) -> list[tuple[int, int]]:
        s = _normalize_fixed(sub)
        spans = []
        for m in re.finditer(r"\S(?:.*?\S)?(?=\s{2,}|$)", s):
            if m.group(0).strip():
                spans.append((m.start(), m.end()))
        return spans

    i = start_idx
    subheader_line = None
    scan_limit = min(len(lines), start_idx + 30)

    # 1) Buscar línea de encabezados
    while i < scan_limit:
        if _is_omit(lines[i]):
            i += 1
            continue

        line = lines[i]
        if ("TSQueue Name" in line) and ("Tranid" in line):
            subheader_line = line
            i += 1
            break

        i += 1

    if subheader_line is None:
        return headers, [], start_idx

    spans = _spans_from_subheader(subheader_line)

    # 2) Si no salen 10 columnas, recalcular con data lines
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

    # saltar líneas omitibles posteriores al header
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

        # ✅ tsQueueName por regex, para no perder primeras filas
        mname = re.match(r"^\s*(\S+)", row_line.strip())
        tsqueue_name = mname.group(1) if mname else ""

        # base por spans
        tokens = [row_line[a:b].strip() for (a, b) in spans]

        # izquierda: ignoramos el primer span y usamos tsQueueName manual
        left_tokens = tokens[1:6]  # location, items, min, max, flength

        # derecha: desde el final de la línea
        right_parts = re.findall(r"\S+", row_line.strip())
        expiry_interval = right_parts[-1] if len(right_parts) >= 1 else ""
        recoverable = right_parts[-2] if len(right_parts) >= 2 else ""
        lastused_interval = right_parts[-3] if len(right_parts) >= 3 else ""
        tran_id = right_parts[-4] if len(right_parts) >= 4 else ""

        tokens = [tsqueue_name] + left_tokens + [tran_id, lastused_interval, recoverable, expiry_interval]

        if len(tokens) < len(headers):
            tokens += [""] * (len(headers) - len(tokens))
        elif len(tokens) > len(headers):
            tokens = tokens[:len(headers)]

        row = {headers[idx]: tokens[idx] for idx in range(len(headers))}

        row["tsQueueName"] = str(row.get("tsQueueName", "") or "").strip()
        row["tsqueueLocation"] = str(row.get("tsqueueLocation", "") or "").strip()
        row["numberOfItems"] = _norm(row.get("numberOfItems", ""))
        row["minItemLength"] = _norm(row.get("minItemLength", ""))
        row["maxItemLength"] = _norm(row.get("maxItemLength", ""))
        row["tsqueueFlength"] = _norm(row.get("tsqueueFlength", ""))
        row["tranId"] = str(row.get("tranId", "") or "").strip()
        row["lastusedInterval"] = str(row.get("lastusedInterval", "") or "").strip()
        row["recoverable"] = str(row.get("recoverable", "") or "").strip()
        row["expiryInterval"] = str(row.get("expiryInterval", "") or "").strip()

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
    Usa executemany por lotes para mejor rendimiento.
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
        numberOfItems = str(r.get("numberOfItems", "") or "").strip()
        minItemLength = str(r.get("minItemLength", "") or "").strip()
        maxItemLength = str(r.get("maxItemLength", "") or "").strip()
        tsqueueFlength = str(r.get("tsqueueFlength", "") or "").strip()
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
    Más robusto cuando muchas columnas vienen vacías.
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

    def _is_data_row(line: str) -> bool:
        s = _normalize_fixed(line).strip()
        if not s:
            return False

        low = s.lower()

        # descartar encabezados
        if "filename" in low or "accessmethod" in low or "access method" in low:
            return False
        if "recoverystatus" in low or "buffersindex" in low or "buffersdata" in low:
            return False
        if s.startswith("-"):
            return False

        return bool(re.match(r"^\S+", s))

    i = start_idx

    # saltar encabezados
    while i < len(lines):
        if _is_omit(lines[i]):
            i += 1
            continue

        low = _normalize_fixed(lines[i]).lower()

        # líneas de encabezado del bloque Files
        if (
            "filename" in low
            or "access method" in low
            or "accessmethod" in low
            or "buffersindex" in low
            or "recoverystatus" in low
        ):
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
            # fallback por si la fila viene incompleta
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
        strings = str(r.get("strings", "") or "").strip()
        buffersIndex = str(r.get("buffersIndex", "") or "").strip()
        buffersData = str(r.get("buffersData", "") or "").strip()

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