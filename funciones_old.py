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


def is_separator_line(line: str) -> bool:
    """
    Detecta líneas tipo:
      +  ______________________
    o
      +________________________
    """
    s = line.rstrip("\n\r")
    if not s.startswith("+"):
        return False

    # quitar '+' y espacios
    rest = s[1:].strip()
    return rest and set(rest) == {"_"}


def segmento_to_table_name(segmento: str, max_len: int = 128) -> str:
    """
    Convierte el nombre del segmento a camelCase para usarlo como nombre de tabla SQL.
    Ej:
      "Storage - Task Subpools" -> "storageTaskSubpools"
      "Dispatcher TCB Pools"   -> "dispatcherTCBPools"
    """
    if not segmento:
        return "segmento"

    # quitar caracteres no alfanuméricos excepto espacios
    clean = re.sub(r"[^A-Za-z0-9 ]+", " ", segmento)
    parts = clean.strip().split()

    if not parts:
        return "segmento"

    # camelCase
    first = parts[0].lower()
    rest = [p.capitalize() for p in parts[1:]]
    name = first + "".join(rest)

    # SQL Server: no iniciar con número
    if name[0].isdigit():
        name = "t" + name

    return name[:max_len]


def evitar_colisiones_columnas(sql_cols: list[str]) -> list[str]:
    reservadas = {"id", "archivo", "fecha"}
    out = []
    for c in sql_cols:
        if c.lower() in reservadas:
            out.append(f"{c}_col")   # o f"col_{c}"
        else:
            out.append(c)
    return out


def get_forced_table_columns(segment_title: str) -> list[str] | None:
    t = (segment_title or "").strip().lower()

    if t == "transactions":
        return [
            "tranId",
            "tranClass",
            "programName",
            "dynamic",
            "isolate",
            "taskDataLocationKey",
            "attachCount",
            "restartCount",
            "dynamicLocal",
            "remoteStarts",
            "storageViols",
            "abendCount",
        ]

    if t == "temporary storage queues":
        return [
            "tsQueueName",
            "tsqueueLocation",
            "numberOfItems",
            "minItemLength",
            "maxItemLength",
            "tsqueueFlength",
            "tranID",
            "lastusedInterval",
            "recoverable",
            "expiryInterval",
        ]

    return None



def get_forced_table_name(segment_title: str) -> str | None:
    t = (segment_title or "").strip().lower()
    if t == "temporary storage queues":
        return "temporaryStorageQueues"
    if t == "transactions":
        return "transactions"
    return None


def _find_header_line_for_forced_table(lines: list[str], start_idx: int, max_scan: int = 15) -> str | None:
    """
    Busca la línea del encabezado real de la tabla (la que tiene nombres de columnas).
    Para Transactions suele contener 'Tranid' o 'Class' o 'Program'.
    """
    end = min(len(lines), start_idx + max_scan)
    for k in range(start_idx, end):
        s = lines[k].rstrip("\n\r")
        if not s.strip() or is_page_header(s) or is_separator_line(s) or ":" in s:
            continue
        low = s.lower()
        # heurística mínima
        if ("tran" in low and "id" in low) or "class" in low or "program" in low:
            return s
    return None


def _spans_from_header_runs(header_line: str, ncols: int) -> list[tuple[int, int]]:
    """
    Genera spans (start,end) desde los runs de texto del header.
    Esto NO depende de datos, por lo que preserva columnas vacías en filas.
    """
    s = header_line.rstrip("\n\r")
    # quitar un '0' inicial típico sin perder demasiado
    m = re.match(r"^(\s*)0(.*)$", s)
    if m:
        s = m.group(1) + m.group(2)

    runs = [m.start() for m in re.finditer(r"\S+", s)]
    if len(runs) < ncols:
        return []

    runs = runs[:ncols]
    spans = []
    for idx in range(ncols):
        a = runs[idx]
        b = runs[idx + 1] if idx + 1 < ncols else len(s)
        spans.append((a, b))
    return spans




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
    if not s.strip():
        return False
    if ":" in s:
        return False
    if is_separator_line(s):
        return False

    # Debe tener letras
    if not re.search(r"[A-Za-z]", s):
        return False

    # Header normalmente NO trae números, %, comas (eso es data)
    if re.search(r"[0-9]", s) or "%" in s or "," in s:
        return False

    # varias separaciones (2+ spaces)
    if len(re.findall(r"\s{2,}", s)) < 2:
        return False

    tokens = re.split(r"\s{2,}", s.strip())
    return len(tokens) >= 3



def looks_like_table_row(line: str) -> bool:
    s = line.rstrip()
    if not s.strip():
        return False
    if ":" in s:
        return False
    if is_separator_line(s):
        return False

    # Debe tener separaciones de columnas
    if len(re.findall(r"\s{2,}", s)) < 2:
        return False

    # Row puede tener números, %, etc.
    tokens = re.split(r"\s{2,}", s.strip())
    return len(tokens) >= 2



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

DSA_HEADERS = {"CDSA", "UDSA", "ECDSA", "EUDSA", "GCDSA", "GUDSA"}

def _split_tokens_2plus_spaces(line: str) -> list[str]:
    s = line.rstrip("\n\r").lstrip()
    if s.startswith("0"):
        s = s[1:].lstrip()
    parts = re.split(r"\s{2,}", s.strip())
    return [p.strip() for p in parts if p.strip()]


def _is_totals_line(line: str) -> bool:
    s = line.strip()
    s2 = s.lstrip("0").strip()
    return s2.startswith("Totals")


def _looks_like_subpool_name(line: str) -> bool:
    """
    En estos reportes el subpool suele venir como '-Loader', '-Something'
    """
    s = line.strip()
    s = s.lstrip("0").strip()
    return s.startswith("-") and ":" not in s



def _detect_matrix_table_headers(header_tokens: list[str]) -> tuple[str, list[str]] | None:
    """
    Espera algo como:
      ["Subpool Name", "CDSA", "UDSA", "ECDSA", "EUDSA", "GCDSA", "GUDSA"]
    Retorna: ("Subpool Name", ["CDSA","UDSA",...])
    """
    if len(header_tokens) < 3:
        return None

    first = header_tokens[0]
    rest = header_tokens[1:]

    # Debe contener varios DSA conocidos (al menos 3 para estar seguro)
    hits = [x for x in rest if x in DSA_HEADERS]
    if len(hits) >= 3:
        return first, rest

    return None



def parse_matrix_table_segment(lines: list[str], start_idx: int) -> tuple[list[str], list[dict], int] | None:
    """
    Parsea tablas tipo matriz (Storage - Task Subpools, etc).

    Formato típico:
      Header: "Subpool Name  CDSA UDSA ECDSA EUDSA ..."
      Subpool: "-Loader"
      Métricas:
        "Getmain Access    CICS  USER  CICS  USER ..."
        "Getmain Requests  13,323 52,432 852,912 ..."
        "Freemain Requests 0 0 0 ..."
        ...

    Salida:
      columnas: ["Subpool Name","DSA", <lista métricas>]
      filas: una fila por DSA por subpool
    """
    i = start_idx

    # 1) header principal (una línea)
    while i < len(lines) and (is_page_header(lines[i]) or lines[i].strip() == "" or is_separator_line(lines[i])):
        i += 1
    if i >= len(lines) or reached_segment_boundary(lines[i]) or _is_totals_line(lines[i]):
        return None

    header_tokens = _split_tokens_2plus_spaces(lines[i])
    hdr = _detect_matrix_table_headers(header_tokens)
    if not hdr:
        return None

    first_col_name, dsa_cols = hdr
    i += 1

    # 2) leer subpool name
    while i < len(lines) and (is_page_header(lines[i]) or lines[i].strip() == "" or is_separator_line(lines[i])):
        i += 1
    if i >= len(lines) or reached_segment_boundary(lines[i]) or _is_totals_line(lines[i]):
        return None

    if not _looks_like_subpool_name(lines[i]):
        # si no es subpool tipo "-X", igual podemos tomar primer token como nombre
        subpool_name = _split_tokens_2plus_spaces(lines[i])[0] if _split_tokens_2plus_spaces(lines[i]) else lines[i].strip()
    else:
        subpool_name = lines[i].strip().lstrip("0").strip()

    i += 1

    # 3) leer métricas hasta Totals o boundary o próximo subpool
    metrics: dict[str, list[str]] = {}  # metric -> valores por dsa
    metric_order: list[str] = []

    while i < len(lines):
        if is_page_header(lines[i]) or lines[i].strip() == "" or is_separator_line(lines[i]):
            i += 1
            continue

        if reached_segment_boundary(lines[i]) or _is_totals_line(lines[i]):
            break

        # si aparece otro subpool, detenemos (por si hay varios subpools en el mismo segmento)
        if _looks_like_subpool_name(lines[i]):
            break

        if ":" in lines[i]:
            # no debería haber, pero por seguridad
            i += 1
            continue

        tokens = _split_tokens_2plus_spaces(lines[i])
        if len(tokens) < 2:
            i += 1
            continue

        metric_name = tokens[0]
        values = tokens[1:]

        # Ajustar valores a cantidad de DSAs
        if len(values) < len(dsa_cols):
            values = values + [""] * (len(dsa_cols) - len(values))
        elif len(values) > len(dsa_cols):
            values = values[:len(dsa_cols)-1] + [" ".join(values[len(dsa_cols)-1:])]

        metrics[metric_name] = values
        metric_order.append(metric_name)

        i += 1

    # 4) construir filas: una por DSA
    columnas = [first_col_name, "DSA"] + metric_order
    filas: list[dict] = []

    for idx, dsa in enumerate(dsa_cols):
        row = {first_col_name: subpool_name, "DSA": dsa}
        for mname in metric_order:
            row[mname] = metrics.get(mname, [""] * len(dsa_cols))[idx]
        filas.append(row)

    return columnas, filas, i



def _pad_right(s: str, n: int) -> str:
    return s + (" " * max(0, n - len(s)))

def _build_spans_by_vertical_spaces(sample_lines: list[str], ncols: int) -> list[tuple[int, int]]:
    """
    Construye spans (start,end) detectando separadores verticales de espacios:
    - Toma varias líneas (header + filas) ya normalizadas
    - Encuentra posiciones que son ESPACIO en TODAS las líneas (separadores)
    - Usa los 'runs' largos de separador para definir cortes entre columnas
    """
    if not sample_lines or ncols < 2:
        return []

    max_len = max(len(x) for x in sample_lines)
    norm = [_pad_right(x, max_len) for x in sample_lines]

    # mask[j] = True si en esa columna j TODAS las líneas tienen espacio
    mask = []
    for j in range(max_len):
        mask.append(all(line[j] == " " for line in norm))

    # detectar runs de separador (>=2 espacios continuos)
    runs = []
    j = 0
    while j < max_len:
        if mask[j]:
            start = j
            while j < max_len and mask[j]:
                j += 1
            end = j  # [start, end)
            if end - start >= 2:
                runs.append((start, end))
        else:
            j += 1

    if not runs:
        return []

    # Convertir runs en "cortes" usando el centro del run
    cut_points = [ (a + b) // 2 for a, b in runs ]

    # Necesitamos ncols-1 cortes. Si hay demasiados, preferimos los runs más anchos.
    if len(cut_points) > ncols - 1:
        runs_sorted = sorted(runs, key=lambda ab: (ab[1] - ab[0]), reverse=True)
        cut_points = sorted({ (a + b)//2 for a,b in runs_sorted[: (ncols - 1)] })
    else:
        cut_points = sorted(set(cut_points))

    # Si aún faltan cortes, no se puede armar bien
    if len(cut_points) != ncols - 1:
        return []

    # Construir spans a partir de cortes
    spans = []
    prev = 0
    for c in cut_points:
        spans.append((prev, c))
        prev = c
    spans.append((prev, max_len))
    return spans




def _build_spans_by_vertical_spaces_data_only(data_lines: list[str], ncols: int) -> list[tuple[int, int]]:
    """
    Construye spans (start,end) detectando separadores verticales de espacios,
    usando SOLO filas de datos (no headers).
    Esto preserva columnas vacías sin desplazar.
    """
    if not data_lines or ncols < 2:
        return []

    max_len = max(len(x) for x in data_lines)
    norm = [(x + " " * (max_len - len(x))) for x in data_lines]

    # mask[j] = True si en esa columna j TODAS las líneas tienen espacio
    mask = [all(line[j] == " " for line in norm) for j in range(max_len)]

    # runs de separador (>=2 espacios continuos)
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

    # elegir los (ncols-1) runs más anchos como cortes
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





def parse_table_segment(
    lines: list[str],
    start_idx: int,
    segment_title: str | None = None
) -> tuple[list[str], list[dict], int]:
    """
    Intenta parsear como:
      1) tabla matriz (Storage - Task Subpools, etc)
      2) tabla clásica
         - si header tiene 2 niveles (2 líneas): parsea filas por POSICIONES (fixed-width)
         - si header tiene 1 nivel: parsea filas por split 2+ espacios

    Extras:
      - omite líneas separadoras tipo '+_____'
      - columnas únicas con sufijo numérico (_2, _3, ...)
      - columnas forzadas por segmento (ej. Transactions) cuando el header del reporte no es confiable

    Requisitos: existan estas funciones en tu archivo:
      - parse_matrix_table_segment
      - is_page_header, is_separator_line, reached_segment_boundary, _is_totals_line
      - looks_like_table_header, _split_tokens_2plus_spaces
      - build_headers_two_level, clean_field_name, make_unique_numeric
      - get_forced_table_columns (para casos especiales como Transactions)
    """
    # 1) intentar tabla matriz
    matrix = parse_matrix_table_segment(lines, start_idx)
    if matrix:
        cols, rows, next_i = matrix

        cols = [clean_field_name(c) if c else f"col{idx+1}" for idx, c in enumerate(cols)]
        cols = make_unique_numeric(cols)

        fixed_rows: list[dict] = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            nr = {}
            # Copiar solo columnas conocidas
            for c in cols:
                nr[c] = r.get(c, "")
            fixed_rows.append(nr)

        return cols, fixed_rows, next_i

    # ---------- helpers internos ----------
    def _normalize_fixed(line: str) -> str:
        """
        Normaliza línea sin destruir espacios (fixed-width).
        Quita un '0' inicial típico del reporte si existe, conservando indent.
        """
        s = line.rstrip("\n\r")
        m = re.match(r"^(\s*)0(.*)$", s)
        if m:
            s = m.group(1) + m.group(2)
        return s.rstrip("\n\r")

    def _subheader_spans(line_sub: str) -> list[tuple[int, int]]:
        """
        Obtiene spans (start,end) de subheaders usando 2+ espacios como separador,
        conservando posiciones reales.
        """
        s = _normalize_fixed(line_sub)
        out: list[tuple[int, int]] = []
        # Captura cada grupo separado por 2+ espacios
        for m in re.finditer(r"\S(?:.*?\S)?(?=\s{2,}|$)", s):
            txt = m.group(0)
            if txt.strip():
                out.append((m.start(), m.end()))
        return out

    # 2) capturar 1-2 líneas de header (raw)
    headers_raw: list[str] = []
    i = start_idx
    header_lines_taken = 0

    while i < len(lines):
        if is_page_header(lines[i]) or lines[i].strip() == "" or is_separator_line(lines[i]):
            i += 1
            continue
        if reached_segment_boundary(lines[i]) or _is_totals_line(lines[i]):
            break

        if looks_like_table_header(lines[i]):
            headers_raw.append(lines[i])
            header_lines_taken += 1
            i += 1
            if header_lines_taken >= 2:
                break
            continue

        if headers_raw:
            break

        i += 1

    if not headers_raw:
        return [], [], i

    # ==========================================
    # ✅ CASO ESPECIAL: COLUMNAS FORZADAS (Transactions, Temporary Storage Queues, etc.)
    # ==========================================
    forced = get_forced_table_columns(segment_title or "")
    if forced:
        headers = [clean_field_name(h) for h in forced]
        headers = [h if h else f"col{idx+1}" for idx, h in enumerate(headers)]
        headers = make_unique_numeric(headers)

        # ✅ recolectar SOLO filas de datos para detectar separadores reales
        data_samples = []
        k = i
        while k < len(lines) and len(data_samples) < 50:
            if is_page_header(lines[k]) or lines[k].strip() == "" or is_separator_line(lines[k]):
                k += 1
                continue
            if reached_segment_boundary(lines[k]) or _is_totals_line(lines[k]):
                break
            if ":" in lines[k]:
                k += 1
                continue

            data_samples.append(_normalize_fixed(lines[k]))
            k += 1

        spans = _build_spans_by_vertical_spaces_data_only(data_samples, ncols=len(headers))

        rows: list[dict] = []
        while i < len(lines):
            if is_page_header(lines[i]) or lines[i].strip() == "" or is_separator_line(lines[i]):
                i += 1
                continue
            if reached_segment_boundary(lines[i]) or _is_totals_line(lines[i]):
                break
            if ":" in lines[i]:
                i += 1
                continue

            row_line = _normalize_fixed(lines[i])

            if spans and len(spans) == len(headers):
                # ✅ slicing por spans preserva vacíos: tranClass="" si está vacío
                tokens = [row_line[a:b].strip() for (a, b) in spans]
            else:
                # fallback (solo si spans falla)
                tokens = _split_tokens_2plus_spaces(lines[i])

            if not tokens:
                i += 1
                continue

            if len(tokens) < len(headers):
                tokens += [""] * (len(headers) - len(tokens))
            elif len(tokens) > len(headers):
                tokens = tokens[:len(headers) - 1] + [" ".join(tokens[len(headers) - 1:])]

            rows.append({headers[idx]: tokens[idx] for idx in range(len(headers))})
            i += 1

        return headers, rows, i

   



    # ==========================================
    # HEADERS 2 NIVELES (por spans)
    # ==========================================
    if len(headers_raw) >= 2:
        top = _normalize_fixed(headers_raw[0])
        sub = _normalize_fixed(headers_raw[1])

        headers = build_headers_two_level(top, sub)
        headers = [clean_field_name(h) if h else f"col{idx+1}" for idx, h in enumerate(headers)]
        headers = make_unique_numeric(headers)

        spans = _subheader_spans(sub)
        if len(spans) != len(headers):
            spans = []  # fallback a split

        rows: list[dict] = []
        while i < len(lines):
            if is_page_header(lines[i]) or lines[i].strip() == "" or is_separator_line(lines[i]):
                i += 1
                continue
            if reached_segment_boundary(lines[i]) or _is_totals_line(lines[i]):
                break
            if ":" in lines[i]:
                i += 1
                continue

            row_line = _normalize_fixed(lines[i])

            if spans:
                tokens = [row_line[a:b].strip() for (a, b) in spans]
            else:
                tokens = _split_tokens_2plus_spaces(lines[i])

            if not tokens:
                i += 1
                continue

            if len(tokens) < len(headers):
                tokens += [""] * (len(headers) - len(tokens))
            elif len(tokens) > len(headers):
                tokens = tokens[:len(headers) - 1] + [" ".join(tokens[len(headers) - 1:])]

            rows.append({headers[idx]: tokens[idx] for idx in range(len(headers))})
            i += 1

        return headers, rows, i

    # ==========================================
    # HEADER 1 NIVEL (clásico)
    # ==========================================
    headers = [clean_field_name(h) for h in _split_tokens_2plus_spaces(headers_raw[0])]
    headers = [h if h else f"col{idx+1}" for idx, h in enumerate(headers)]
    headers = make_unique_numeric(headers)

    rows: list[dict] = []
    while i < len(lines):
        if is_page_header(lines[i]) or lines[i].strip() == "" or is_separator_line(lines[i]):
            i += 1
            continue
        if reached_segment_boundary(lines[i]) or _is_totals_line(lines[i]):
            break
        if ":" in lines[i]:
            i += 1
            continue

        tokens = _split_tokens_2plus_spaces(lines[i])
        if not tokens:
            i += 1
            continue

        if len(tokens) < len(headers):
            tokens += [""] * (len(headers) - len(tokens))
        elif len(tokens) > len(headers):
            tokens = tokens[:len(headers) - 1] + [" ".join(tokens[len(headers) - 1:])]

        rows.append({headers[idx]: tokens[idx] for idx in range(len(headers))})
        i += 1

    return headers, rows, i




def parse_cicsadm(file_path: Path) -> dict:
    lines = file_path.read_text(errors="ignore").splitlines()
    out: dict[str, dict] = {}
    i = 0

    # ✅ Segmentos que SIEMPRE deben procesarse como TABLA
    forced_table_segments = {
        "transactions",
        "dispatcher tcb modes",
        "temporary storage queues",
    }

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

            # ===== DOBLE (2 títulos en la misma línea)
            split = split_two_columns(lines[j])
            if split and is_title_text(split[0]) and is_title_text(split[1]):
                tL = split[0].lstrip("-").strip()
                tR = split[1].lstrip("-").strip()
                j += 1

                left, right = {}, {}
                while j < len(lines) and not reached_segment_boundary(lines[j]):
                    # ✅ saltar headers, vacíos y separadores
                    if is_page_header(lines[j]) or lines[j].strip() == "" or is_separator_line(lines[j]):
                        j += 1
                        continue

                    parts = split_two_columns(lines[j])
                    if parts:
                        add_kvs_from_piece(parts[0], left)
                        add_kvs_from_piece(parts[1], right)
                    else:
                        add_kvs_from_piece(lines[j], left)

                    j += 1

                keyL = unique_title(tL, out)
                out[keyL] = {"nombre": tL, "tipo": "doble", "detalles": left}

                keyR = unique_title(tR, out)
                out[keyR] = {"nombre": tR, "tipo": "doble", "detalles": right}

                i = j
                continue

            # ===== ÚNICO (simple)
            title = lines[j].lstrip("-").strip()
            j += 1

            while j < len(lines) and (
                lines[j].strip() == ""
                or is_page_header(lines[j])
                or is_separator_line(lines[j])
                or lines[j].startswith("+_")
            ):
                j += 1

            # ===== TABLA (forzado o detectado)
            title_key = title.strip().lower()

            if j < len(lines) and (title_key in forced_table_segments or is_table_segment(lines, j)):
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

                # avanzar hasta donde terminó el parse de tabla (o boundary)
                j = next_j
                while j < len(lines) and not reached_segment_boundary(lines[j]) and not _is_totals_line(lines[j]):
                    j += 1

                i = j
                continue

            # ===== ÚNICO normal: detalle kv (1 o 2 columnas, multi-kv)
            fields = {}
            while j < len(lines) and not reached_segment_boundary(lines[j]):
                # ✅ omitir separadores también aquí
                if is_page_header(lines[j]) or lines[j].strip() == "" or is_separator_line(lines[j]):
                    j += 1
                    continue

                add_kvs_from_line(lines[j], fields)
                j += 1

            key = unique_title(title, out)
            out[key] = {"nombre": title, "tipo": "unico", "detalles": fields}

            i = j
            continue

        i += 1

    return out







def _sanitize_sql_identifier(name: str, max_len: int = 128) -> str:
    """
    Convierte un texto en un identificador válido para SQL Server.
    - Reemplaza caracteres no permitidos por '_'
    - No permite que empiece con número
    - Trunca a 128 chars
    """
    if name is None:
        name = ""
    s = str(name).strip()

    # reemplazar espacios y signos raros por underscore
    s = re.sub(r"[^\w]", "_", s, flags=re.UNICODE)  # deja letras, números, _
    s = re.sub(r"_+", "_", s).strip("_")

    if not s:
        s = "col"

    # no iniciar con número
    if s[0].isdigit():
        s = "c_" + s

    return s[:max_len]



def _make_unique(names: list[str]) -> list[str]:
    """
    Asegura nombres únicos: si se repite, agrega sufijo _2, _3, ...
    """
    seen = {}
    out = []
    for n in names:
        base = n
        if base not in seen:
            seen[base] = 1
            out.append(base)
        else:
            seen[base] += 1
            out.append(f"{base}_{seen[base]}")
    return out


def make_unique_numeric(names: list[str]) -> list[str]:
    """
    Si hay repetidos, agrega sufijo _2, _3, ...
    Ej: ["buffers","buffers","buffers"] -> ["buffers","buffers_2","buffers_3"]
    """
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



def _create_table_for_segment(cursor, table_name: str, sql_cols: list[str]) -> None:
    """
    Crea tabla si no existe:
      - id identity
      - archivo INT
      - fecha DATE
      - columnas dinámicas NVARCHAR(MAX)
    """
    # QUOTENAME para tabla/columnas
    qt = lambda x: f"[{x.replace(']', ']]')}]"

    cols_ddl = ",\n        ".join(f"{qt(c)} NVARCHAR(MAX) NULL" for c in sql_cols)

    ddl = f"""
    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name = '{table_name}' AND xtype='U')
    BEGIN
        CREATE TABLE {qt(table_name)}
        (
            id INT IDENTITY(1,1) PRIMARY KEY,
            archivo INT NULL,
            fecha DATE NULL,
            {cols_ddl}
        );
    END
    """
    cursor.execute(ddl)




def _insert_rows_into_segment_table(cursor, table_name: str, sql_cols: list[str], rows: list[dict], archivo_id: int, fechaActual: str) -> int:
    """
    Inserta filas en tabla del segmento.
    Espera que cada row venga como dict {col_original: valor}.
    """
    qt = lambda x: f"[{x.replace(']', ']]')}]"

    # columnas fijas + dinámicas
    all_cols = ["archivo", "fecha"] + sql_cols
    cols_sql = ", ".join(qt(c) for c in all_cols)

    placeholders = ", ".join(["?"] * len(all_cols))
    insert_sql = f"INSERT INTO {qt(table_name)} ({cols_sql}) VALUES ({placeholders})"

    inserted = 0
    for row in rows:
        # row puede venir con keys = nombres originales de columnas
        # aquí asumimos que en parse_table_segment generaste row usando exactamente los nombres de "columnas"
        # entonces row.get(colname) debe funcionar

        values = [archivo_id, fechaActual]
        for c in sql_cols:
            # c es nombre SQL saneado; necesitamos el valor por columna ORIGINAL,
            # por eso manejaremos un mapeo en la función principal (col_map_sql_to_orig)
            # y aquí se inyectará vía closure en la principal.
            # Esta función se llamará desde la principal con rows ya "transformadas".
            values.append(row.get(c, ""))

        cursor.execute(insert_sql, values)
        inserted += 1

    return inserted


def _spans_tokens(line: str) -> list[tuple[int, int, str]]:
    """
    Devuelve [(start, end, token)] para cada 'palabra/grupo' visible en la línea
    usando runs de no-espacios. Conserva posiciones para mapear por alineación.
    """
    raw = line.rstrip("\n\r")
    if raw.lstrip().startswith("0"):
        # quitar prefijo 0 típico del reporte sin perder demasiada alineación
        # (solo recorta 1 char si es literal al inicio)
        raw = raw[1:] if raw.startswith("0") else raw
    out = []
    for m in re.finditer(r"\S+", raw):
        out.append((m.start(), m.end(), m.group(0)))
    return out


def _clean_header_token(tok: str) -> str:
    """
    Limpia tokens tipo flechas/dashes/ruido:
      '<----' '---->' '<-' '->' '->>' etc
    """
    t = tok.strip()
    # remover flechas y símbolos comunes del layout
    t = t.replace("<", "").replace(">", "")
    t = t.replace("-", " ")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def build_headers_two_level(line_top: str, line_sub: str) -> list[str]:
    """
    Construye headers combinando 2 niveles por alineación (spans).
    - line_top: grupos (ej 'TCBs Attached', 'Op. System', 'Total TCB', ...)
    - line_sub: subheaders (ej 'Current', 'Peak', 'Waits', 'Wait Time', ...)
    """
    top = _spans_tokens(line_top)
    sub = _spans_tokens(line_sub)

    # unir tokens contiguos del TOP en "grupos" por espacios grandes (2+)
    # Aquí en vez de split por espacios, reconstruimos agrupando runs separados por 2+ espacios.
    # Para eso, tomamos la cadena original y partimos por 2+ espacios.
    top_groups = []
    raw_top = line_top.rstrip("\n\r")
    # no tocar alineación para spans; usamos spans de runs para bounds,
    # pero el texto del grupo lo tomamos por split 2+ spaces
    parts = re.split(r"\s{2,}", raw_top.strip())
    # Para bounds de cada grupo, aproximamos usando find incremental
    idx_cursor = 0
    for p in parts:
        if not p.strip():
            continue
        pos = raw_top.find(p, idx_cursor)
        if pos == -1:
            continue
        start = pos
        end = pos + len(p)
        idx_cursor = end
        top_groups.append((start, end, p))

    # subheaders también pueden ser "Wait Time" (2 palabras) separados por 1 espacio,
    # pero como vienen alineados, preferimos reconstruir subheaders por split 2+ spaces
    raw_sub = line_sub.rstrip("\n\r")
    sub_parts = re.split(r"\s{2,}", raw_sub.strip())
    sub_groups = []
    idx_cursor = 0
    for p in sub_parts:
        if not p.strip():
            continue
        pos = raw_sub.find(p, idx_cursor)
        if pos == -1:
            continue
        start = pos
        end = pos + len(p)
        idx_cursor = end
        sub_groups.append((start, end, p))

    headers = []
    for s0, s1, sub_txt in sub_groups:
        sub_txt_clean = _clean_header_token(sub_txt)
        if not sub_txt_clean:
            continue

        # buscar grupo TOP que cubra el centro del subheader
        center = (s0 + s1) // 2
        parent = ""
        for t0, t1, top_txt in top_groups:
            if t0 <= center <= t1:
                parent = _clean_header_token(top_txt)
                break

        # reglas: si parent vacío o parent==sub => usar sub
        if not parent or parent.lower() == sub_txt_clean.lower():
            col = sub_txt_clean
        else:
            col = f"{parent} {sub_txt_clean}"

        col = re.sub(r"\s+", " ", col).strip()
        headers.append(col)

    # A veces la primera columna ("TCB Mode") viene solo en top/sub como "TCB" + "Mode"
    # Con la lógica anterior quedará "TCB Mode" (bien).
    return headers




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
    Soporta 2 formatos:
      1) Nuevo JSON:
         {
           "Titulo": {"nombre": "...", "tipo": "unico|doble|tabla", "detalles": {...}}
         }
      2) Formato anterior:
         { "Titulo": {campo:valor} }

    Reglas:
      - unico/doble => insert a validacion_sistema (igual que antes)
      - tabla => crear tabla propia por segmento e insertar filas
    """

    conn_sqlserver = conectar_base_datos()
    cursor = conn_sqlserver.cursor()

    # --- tabla validacion_sistema base (igual)
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

    cursor.execute("""
    IF NOT EXISTS (
        SELECT * FROM sys.indexes
        WHERE name = 'IX_validacion_sistema_fecha'
          AND object_id = OBJECT_ID('validacion_sistema')
    )
    CREATE INDEX IX_validacion_sistema_fecha ON validacion_sistema(fecha);
    """)
    conn_sqlserver.commit()

    # --- obtener archivo_id desde tabla archivos
    archivoNombre = nombreArchivo.replace(".TXT", "")
    cursor.execute("SELECT id FROM archivos WHERE archivo = ?", (archivoNombre,))
    archivo_id_row = cursor.fetchone()
    archivo_id = archivo_id_row[0] if archivo_id_row else None

    print(f"Archivo ID para {archivoNombre}: {archivo_id}")

    # --- validar duplicado por archivo+fecha
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
    filas_tablas_insertadas = 0

    for titulo, payload in diccionarioSegmentos.items():
        # Detectar formato nuevo vs viejo
        if isinstance(payload, dict) and "detalles" in payload and "tipo" in payload:
            tipo = payload.get("tipo", "").lower().strip()
            detalles = payload.get("detalles") or {}
        else:
            tipo = "unico"  # formato viejo lo tratamos como unico
            detalles = payload or {}

        # ==========================
        # CASO TABLA
        # ==========================
        if tipo == "tabla":
            # detalles esperado:
            # { "columnas": [...], "filas": [ {col:val,...}, ... ] }
            columnas = detalles.get("columnas") if isinstance(detalles, dict) else None
            filas = detalles.get("filas") if isinstance(detalles, dict) else None

            if not columnas or not isinstance(columnas, list):
                # sin columnas => no se crea tabla
                continue
            if not filas or not isinstance(filas, list):
                # sin filas => crea tabla igual? tú decides. Por ahora no.
                continue

            # Nombre de tabla por segmento (sanitizado). Sugerencia: prefijo fijo
            # y opcionalmente usar id del segmento para evitar colisiones
            forced_name = get_forced_table_name(titulo)
            table_name = forced_name if forced_name else segmento_to_table_name(titulo)


            # 1) Normalizar columnas a nombres SQL seguros
            sql_cols_raw = [_sanitize_sql_identifier(c, max_len=120) for c in columnas]

            # 2) Hacer únicas con sufijo numérico
            sql_cols = make_unique_numeric(sql_cols_raw)

            # ✅ NUEVO: evitar colisiones con columnas fijas
            sql_cols = evitar_colisiones_columnas(sql_cols)

            # 3) Mapear índice a columna SQL para preservar duplicados correctamente
            # (porque dict(zip()) pierde duplicados)
            col_map_indexed = list(zip(sql_cols, columnas))  # [(sql_col, original_col), ...]


            # Crear tabla si no existe
            _create_table_for_segment(cursor, table_name, sql_cols)
            conn_sqlserver.commit()

            # Transformar filas: crear dict con keys = sql_cols (ya saneadas)
            filas_transformadas = []
            for row in filas:
                if not isinstance(row, dict):
                    continue
                new_row = {}
                # row se espera que tenga keys == columnas originales (cuando no hay duplicados)
                # pero en duplicados, la forma correcta es tomar el valor por posición.
                for idx, (sql_c, orig_c) in enumerate(col_map_indexed):
                    # Si tu parser de tablas produce row como dict, no hay forma de distinguir duplicados.
                    # Por eso: para tablas con duplicados, es mejor que el parser genere cada fila como LISTA
                    # alineada a columnas. Mientras tanto, hacemos fallback:
                    val = row.get(orig_c, "")
                    new_row[sql_c] = "" if val is None else str(val)

                filas_transformadas.append(new_row)

            inserted = _insert_rows_into_segment_table(
                cursor,
                table_name,
                sql_cols,
                filas_transformadas,
                archivo_id,
                fechaActual
            )
            filas_tablas_insertadas += inserted
            conn_sqlserver.commit()
            continue

        # ==========================
        # CASO UNICO / DOBLE (igual)
        # ==========================
        # detalles debe ser dict campo->valor
        if not detalles or not isinstance(detalles, dict) or len(detalles) == 0:
            continue

        segmento_id = obtenerIdSegmento(titulo)

        for campo, valor in detalles.items():
            valor = "" if valor is None else str(valor)
            cursor.execute(insert_sql, (archivo_id, segmento_id, str(campo), valor, fechaActual))
            filas_insertadas += 1

    conn_sqlserver.commit()
    conn_sqlserver.close()

    print(f"Inserción completada. Filas insertadas validacion_sistema: {filas_insertadas}")
    print(f"Filas insertadas en tablas por segmento (tipo tabla): {filas_tablas_insertadas}")







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


def imprimir_listado_segmentos_tabla(DIRECTORIO_SALIDA, devolver_lista: bool = False):
    archivos_json = os.listdir(DIRECTORIO_SALIDA)
    lista_segmentos_tabla = []

    for archivo_json in archivos_json:
        archivo_json = archivo_json.upper()

        if not archivo_json.endswith(".JSON"):
            continue

        json_path = DIRECTORIO_SALIDA / archivo_json

        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))

            print(f"Archivo: {archivo_json}")
            print(f"{'Segmento':<50} | {'Tipo':<10}")
            print("-" * 65)

            for segmento, detalles in data.items():
                tipo = detalles.get("tipo", "N/A") if isinstance(detalles, dict) else "N/A"
                if tipo == "tabla":
                    print(f"{segmento:<50} | {tipo:<10}")
                    lista_segmentos_tabla.append(segmento)

            print("\n")

        except Exception as e:
            print(f"❌ Error leyendo {archivo_json}: {e}")

    if devolver_lista:
        return lista_segmentos_tabla
    


    