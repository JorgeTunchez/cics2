from pathlib import Path
import re

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
