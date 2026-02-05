from __future__ import annotations

from pathlib import Path
from conexionBD import *
import re


DSA_HEADERS = {"CDSA", "UDSA", "ECDSA", "EUDSA", "GCDSA", "GUDSA"}

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

# ============================================================
# PARSING UTILITIES (mínimo necesario)
# ============================================================

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

def is_separator_line(line: str) -> bool:
    s = line.rstrip("\n\r")
    if not s.startswith("+"):
        return False
    rest = s[1:].strip()
    return bool(rest) and set(rest) == {"_"}

def clean_field_name(name: str) -> str:
    n = str(name).replace(".", " ")
    n = re.sub(r"\s+", " ", n).strip()
    return n

def is_title_text(text: str) -> bool:
    t = text.strip()
    if not t or ":" in t:
        return False
    if t.startswith("-"):
        return True
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 \-]{0,50}", t))

def _is_totals_line(line: str) -> bool:
    s = line.strip()
    s2 = s.lstrip("0").strip()
    return s2.startswith("Totals")


def _split_tokens_2plus_spaces(line: str) -> list[str]:
    s = line.rstrip("\n\r").lstrip()
    if s.startswith("0"):
        s = s[1:].lstrip()
    parts = re.split(r"\s{2,}", s.strip())
    return [p.strip() for p in parts if p.strip()]


def _normalize_counter(v: str) -> str:
    """
    Convierte:
      '0 0'  -> '0'
      '0 46' -> '46'
      '46'   -> '46'
    """
    parts = v.strip().split()
    if not parts:
        return "0"
    return parts[-1]



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


def parse_transactions_row(line: str) -> dict | None:
    """
    Parsea una fila de Transactions preservando columnas vacías (tranClass).
    Retorna dict con las 12 columnas forzadas o None si no parece fila válida.
    """
    s = line.strip()
    if not s:
        return None

    # quitar posible "0" al inicio
    if s.startswith("0 "):
        s = s[2:].lstrip()
    elif s.startswith("0") and len(s) > 1 and s[1].isspace():
        s = s[1:].lstrip()

    parts = re.split(r"\s+", s)
    if len(parts) < 11:
        return None

    # 1) tranId
    if not re.fullmatch(r"[A-Z0-9]{4}", parts[0]):
        return None
    tranId = parts[0]

    idx = 1

    # 2) tranClass opcional
    tranClass = ""
    if idx < len(parts) and re.fullmatch(r"[A-Z0-9]{4}", parts[idx]):
        # ojo: programName también podría ser 7-8 chars, pero tranClass es 4 fijo.
        tranClass = parts[idx]
        idx += 1

    # 3) programName (token)
    if idx >= len(parts):
        return None
    programName = parts[idx]
    idx += 1

    # 4) dynamic
    if idx >= len(parts):
        return None
    dynamic = parts[idx]
    idx += 1

    # 5) isolate
    if idx >= len(parts):
        return None
    isolate = parts[idx]
    idx += 1

    # 6) taskDataLocationKey
    if idx >= len(parts):
        return None
    taskDataLocationKey = parts[idx]
    idx += 1

    # quedan 6 numéricos: attachCount restartCount dynamicLocal remoteStarts storageViols abendCount
    remaining = parts[idx:]
    if len(remaining) < 6:
        return None

    # si hay más de 6, juntamos extras al final (por seguridad)
    if len(remaining) > 6:
        remaining = remaining[:5] + [" ".join(remaining[5:])]

    attachCount, restartCount, dynamicLocal, remoteStarts, storageViols, abendCount = remaining

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


def _looks_like_subpool_name(line: str) -> bool:
    """
    En estos reportes el subpool suele venir como '-Loader', '-Something'
    """
    s = line.strip()
    s = s.lstrip("0").strip()
    return s.startswith("-") and ":" not in s


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


def unique_title(base: str, store: dict) -> str:
    if base not in store:
        return base
    i = 2
    while f"{base} ({i})" in store:
        i += 1
    return f"{base} ({i})"



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
        for m in re.finditer(r"\S(?:.*?\S)?(?=\s{2,}|$)", s):
            txt = m.group(0)
            if txt.strip():
                out.append((m.start(), m.end()))
        return out

    # ✅ helper: parser definitivo para Transactions (preserva tranClass vacío)
    def _parse_transactions_row(line: str) -> dict | None:
        s = _normalize_fixed(line).strip()
        if not s or ":" in s:
            return None

        parts = re.split(r"\s+", s)
        if len(parts) < 8:
            return None

        # tranId fijo (4)
        if not re.fullmatch(r"[A-Z0-9]{4}", parts[0]):
            return None
        tranId = parts[0]

        # localizar el token "dynamic" (Static/Dynamic)
        dyn_idx = None
        for idx in range(1, len(parts)):
            if parts[idx] in ("Static", "Dynamic"):
                dyn_idx = idx
                break

        if dyn_idx is None or dyn_idx < 2:
            return None

        # programName es el token inmediatamente antes de Static/Dynamic
        programName = parts[dyn_idx - 1]

        # tranClass son los tokens entre tranId y programName (puede ser 0 o 1 token en tu caso)
        middle = parts[1:dyn_idx - 1]
        tranClass = ""
        if len(middle) == 1:
            tranClass = middle[0]
        elif len(middle) > 1:
            # por si viniera con espacios (raro), los unimos
            tranClass = " ".join(middle)

        dynamic = parts[dyn_idx]

        # isolate, taskDataLocationKey
        if dyn_idx + 2 >= len(parts):
            return None
        isolate = parts[dyn_idx + 1]
        taskDataLocationKey = parts[dyn_idx + 2]

        # los últimos 6 numéricos deben venir al final
        tail = parts[dyn_idx + 3:]
        if len(tail) < 6:
            return None

        # si hay más de 6, unimos extras en el último
        if len(tail) > 6:
            tail = tail[:5] + [" ".join(tail[5:])]

        #attachCount, restartCount, dynamicLocal, remoteStarts, storageViols, abendCount = tail
        
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

    # ============================================================
    # ✅ CASO ESPECIAL 1: Transactions (parser determinístico)
    # ============================================================
    if (segment_title or "").strip().lower() == "transactions":
        forced = get_forced_table_columns("transactions") or []
        headers = [clean_field_name(h) for h in forced]
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

            row = _parse_transactions_row(lines[i])
            if row:
                rows.append(row)
            i += 1

        return headers, rows, i

    # ==========================================
    # ✅ CASO ESPECIAL 2: COLUMNAS FORZADAS (otros segmentos)
    # ==========================================
    forced = get_forced_table_columns(segment_title or "")
    if forced:
        headers = [clean_field_name(h) for h in forced]
        headers = [h if h else f"col{idx+1}" for idx, h in enumerate(headers)]
        headers = make_unique_numeric(headers)

        # recolectar SOLO filas de datos para detectar separadores reales
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







def parse_cicsadm_lite(file_path: Path, allowed_segments: set[str] | None = None) -> dict:
    """
    Parser reducido: SOLO crea segmentos permitidos (por defecto Transactions y Programs).
    No genera JSON con System Status, Monitoring, Dispatcher, etc.

    Retorna formato:
      {
        "Transactions": {"nombre": "...", "tipo":"tabla", "detalles": {"columnas":[...],"filas":[...]}},
        "Programs": {...}  # si existe
      }
    """
    if allowed_segments is None:
        allowed_segments = {"transactions", "programs"}

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

            # --- detectar título (simple o doble). Para lite, solo usaremos simple.
            # Si viniera doble, lo saltamos (no nos interesa).
            split = split_two_columns(lines[j])
            if split and is_title_text(split[0]) and is_title_text(split[1]):
                # segmento doble => no lo necesitamos, saltamos todo el bloque
                while j < len(lines) and not reached_segment_boundary(lines[j]):
                    j += 1
                i = j
                continue

            # --- título simple
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

            # --- si NO está permitido, saltar el segmento completo sin procesar
            if title_key not in allowed_segments:
                while j < len(lines) and not reached_segment_boundary(lines[j]):
                    j += 1
                i = j
                continue

            # --- si está permitido: lo tratamos como TABLA (Transactions/Programs)
            columnas, filas, next_j = parse_table_segment(lines, j, title)

            key = unique_title(title, out)
            out[key] = {
                "nombre": title,
                "tipo": "tabla",
                "detalles": {"columnas": columnas, "filas": filas}
            }

            # avanzar hasta fin real del segmento (o totals)
            j = next_j
            while j < len(lines) and not reached_segment_boundary(lines[j]) and not _is_totals_line(lines[j]):
                j += 1

            i = j
            continue

        i += 1

    return out


# ============================================================
# Forced columns / names (solo las que vamos a usar)
# ============================================================

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

    if t == "programs":
        # Ajusta si tu segmento Programs tiene otro layout
        return ["programName"]

    return None

def get_forced_table_name(segment_title: str) -> str | None:
    t = (segment_title or "").strip().lower()
    if t == "transactions":
        return "transactions"
    if t == "programs":
        return "programs"
    return None


# ============================================================
# BASE DE DATOS: SOLO TABLAS core
#   - archivos
#   - segmento
#   - programs
#   - transactions
# ============================================================

def ensure_archivos_table(cursor) -> None:
    cursor.execute("""
    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='archivos' AND xtype='U')
    BEGIN
        CREATE TABLE archivos
        (
            id INT IDENTITY(1,1) PRIMARY KEY,
            archivo NVARCHAR(255) NOT NULL
        );
    END
    """)
    cursor.execute("""
    IF NOT EXISTS (
        SELECT * FROM sys.indexes
        WHERE name = 'UX_archivos_archivo' AND object_id = OBJECT_ID('archivos')
    )
    CREATE UNIQUE INDEX UX_archivos_archivo ON archivos(archivo);
    """)

def ensure_segmento_table(cursor) -> None:
    cursor.execute("""
    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='segmento' AND xtype='U')
    BEGIN
        CREATE TABLE segmento
        (
            id INT IDENTITY(1,1) PRIMARY KEY,
            segmento NVARCHAR(255) NOT NULL
        );
    END
    """)
    cursor.execute("""
    IF NOT EXISTS (
        SELECT * FROM sys.indexes
        WHERE name = 'UX_segmento_segmento' AND object_id = OBJECT_ID('segmento')
    )
    CREATE UNIQUE INDEX UX_segmento_segmento ON segmento(segmento);
    """)

def ensure_programs_table(cursor) -> None:
    cursor.execute("""
    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='programs' AND xtype='U')
    BEGIN
        CREATE TABLE programs
        (
            id INT IDENTITY(1,1) PRIMARY KEY,
            programName NVARCHAR(255) NOT NULL
        );
    END
    """)
    cursor.execute("""
    IF NOT EXISTS (
        SELECT * FROM sys.indexes
        WHERE name = 'UX_programs_programName' AND object_id = OBJECT_ID('programs')
    )
    CREATE UNIQUE INDEX UX_programs_programName ON programs(programName);
    """)

def ensure_transactions_table(cursor) -> None:
    cursor.execute("""
    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='transactions' AND xtype='U')
    BEGIN
        CREATE TABLE transactions
        (
            id INT IDENTITY(1,1) PRIMARY KEY,
            archivo INT NOT NULL,
            fecha DATE NOT NULL,
            tranId NVARCHAR(50) NULL,
            tranClass NVARCHAR(50) NULL,
            programName NVARCHAR(255) NULL,
            dynamic NVARCHAR(50) NULL,
            isolate NVARCHAR(50) NULL,
            taskDataLocationKey NVARCHAR(255) NULL,
            attachCount NVARCHAR(50) NULL,
            restartCount NVARCHAR(50) NULL,
            dynamicLocal NVARCHAR(50) NULL,
            remoteStarts NVARCHAR(50) NULL,
            storageViols NVARCHAR(50) NULL,
            abendCount NVARCHAR(50) NULL
        );
    END
    """)
    cursor.execute("""
    IF NOT EXISTS (
        SELECT * FROM sys.indexes
        WHERE name = 'UX_transactions_archivo_fecha_tranId' AND object_id = OBJECT_ID('transactions')
    )
    CREATE UNIQUE INDEX UX_transactions_archivo_fecha_tranId
    ON transactions(archivo, fecha, tranId);
    """)

def upsert_archivo(cursor, archivo_nombre: str) -> int:
    cursor.execute("SELECT id FROM archivos WHERE archivo = ?", (archivo_nombre,))
    row = cursor.fetchone()
    if row and row[0] is not None:
        return int(row[0])

    cursor.execute("INSERT INTO archivos (archivo) VALUES (?)", (archivo_nombre,))

    # ✅ más confiable que SCOPE_IDENTITY con algunos drivers
    cursor.execute("SELECT id FROM archivos WHERE archivo = ?", (archivo_nombre,))
    row = cursor.fetchone()
    if not row or row[0] is None:
        raise RuntimeError(f"No se pudo obtener id para archivo='{archivo_nombre}'")
    return int(row[0])


def upsert_segmento(cursor, segmento_nombre: str) -> int:
    cursor.execute("SELECT id FROM segmento WHERE segmento = ?", (segmento_nombre,))
    row = cursor.fetchone()
    if row and row[0] is not None:
        return int(row[0])

    cursor.execute("INSERT INTO segmento (segmento) VALUES (?)", (segmento_nombre,))

    cursor.execute("SELECT id FROM segmento WHERE segmento = ?", (segmento_nombre,))
    row = cursor.fetchone()
    if not row or row[0] is None:
        raise RuntimeError(f"No se pudo obtener id para segmento='{segmento_nombre}'")
    return int(row[0])


def upsert_program(cursor, program_name: str) -> None:
    if not program_name:
        return
    cursor.execute("SELECT 1 FROM programs WHERE programName = ?", (program_name,))
    if cursor.fetchone():
        return
    cursor.execute("INSERT INTO programs (programName) VALUES (?)", (program_name,))




def insert_transactions_rows(cursor, archivo_id: int, fecha: str, rows: list[dict]) -> int:
    inserted = 0
    sql = """
    INSERT INTO transactions
    (archivo, fecha, tranId, tranClass, programName, dynamic, isolate, taskDataLocationKey,
     attachCount, restartCount, dynamicLocal, remoteStarts, storageViols, abendCount)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    errores = 0

    for r in rows:
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

        # limpieza fuerte
        tranId = re.sub(r"\s+", "", tranId).upper()
        tranClass = re.sub(r"\s+", "", tranClass).upper()
        programName = programName.strip()
        dynamic = dynamic.strip()
        isolate = isolate.strip()
        taskDataLocationKey = taskDataLocationKey.strip()

        if not tranId:
            continue

        # Registrar programa
        upsert_program(cursor, programName)

        try:
            cursor.execute(sql, (
                archivo_id, fecha, tranId, tranClass, programName, dynamic, isolate,
                taskDataLocationKey, attachCount, restartCount, dynamicLocal,
                remoteStarts, storageViols, abendCount
            ))
            inserted += 1

        except Exception as e:
            errores += 1
            # muestra los primeros 5 errores para diagnosticar
            if errores <= 5:
                print("❌ Error insertando Transactions:", e)
                print("   archivo_id:", archivo_id, "fecha:", fecha, "tranId:", tranId)
                print("   fila:", r)

    return inserted





# ============================================================
# INSERT PRINCIPAL (SOLO programs + transactions)
# ============================================================

def insertarValidacionSistema(fechaActual: str, nombreArchivo: str, diccionarioSegmentos: dict) -> None:
    """
    En esta versión nos centramos SOLO en:
      - archivos
      - segmento
      - programs
      - transactions

    Ignora validacion_sistema y cualquier otra tabla dinámica por segmento.
    """

    conn = conectar_base_datos()
    cursor = conn.cursor()

    # Crear tablas core
    ensure_archivos_table(cursor)
    ensure_segmento_table(cursor)
    ensure_programs_table(cursor)
    ensure_transactions_table(cursor)
    conn.commit()

    archivo_nombre = nombreArchivo.replace(".TXT", "").replace(".JSON", "").strip().upper()

    archivo_id = upsert_archivo(cursor, archivo_nombre)
    conn.commit()

    # Catálogo de segmentos (opcional, pero lo pediste)
    upsert_segmento(cursor, "Programs")
    upsert_segmento(cursor, "Transactions")
    conn.commit()

    # Obtener Transactions del JSON
    tx_payload = diccionarioSegmentos.get("Transactions") or diccionarioSegmentos.get("transactions")
    tx_rows = []

    if isinstance(tx_payload, dict) and tx_payload.get("tipo") == "tabla":
        detalles = tx_payload.get("detalles") or {}
        tx_rows = detalles.get("filas") or []
    elif isinstance(tx_payload, dict) and "filas" in tx_payload:
        tx_rows = tx_payload.get("filas") or []

    inserted_tx = 0
    if isinstance(tx_rows, list) and tx_rows:
        inserted_tx = insert_transactions_rows(cursor, archivo_id, fechaActual, tx_rows)
        conn.commit()

    print(f"Archivo: {archivo_nombre} (id={archivo_id}) | Transactions insertadas: {inserted_tx}")
    conn.close()
