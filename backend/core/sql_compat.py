"""
sql_compat — traduce el dialecto SQLite (el que usa todo el código de repositorios)
a PostgreSQL al vuelo, para no reescribir cientos de queries.

Cubre: placeholders, funciones de fecha (strftime/date/datetime), INSERT OR IGNORE/REPLACE,
IFNULL, LIKE (case-insensitive como SQLite), PRAGMA table_info, DDL (AUTOINCREMENT, tipos).
Las fechas se guardan como TEXT ISO ('YYYY-MM-DD[ HH:MM:SS]') igual que en SQLite,
así la lógica de negocio sigue comparando/ordenando strings sin cambios.
"""
import re
from typing import List, Optional, Tuple

from .sql_groupby import add_implicit_order, fix_group_by

TZ_LOCAL = "America/Santiago"

# Tablas donde INSERT OR REPLACE necesita una clave de conflicto conocida
REPLACE_KEYS = {
    "ajustes": ["clave"],
    "notificaciones_areas": ["area"],
}

_STRF_MAP = [
    ("%Y", "YYYY"), ("%m", "MM"), ("%d", "DD"),
    ("%H", "HH24"), ("%M", "MI"), ("%S", "SS"),
]


def strip_comments(sql: str) -> str:
    """Quita '-- ...' y '/* ... */' respetando literales (los apóstrofes en comentarios rompían todo)."""
    out, i, n = [], 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch == "'":
            j = i + 1
            while j < n:
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            out.append(sql[i:j + 1])
            i = j + 1
        elif sql.startswith("--", i):
            j = sql.find(chr(10), i)
            i = n if j == -1 else j
        elif sql.startswith("/*", i):
            j = sql.find("*/", i + 2)
            i = n if j == -1 else j + 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


# ─────────────────────────── utilidades de tokenizado ───────────────────────────

def _literal_spans(sql: str) -> List[Tuple[int, int]]:
    """Rangos [ini, fin) de literales entre comillas simples (con '' escapado)."""
    spans, i, n = [], 0, len(sql)
    while i < n:
        if sql[i] == "'":
            j = i + 1
            while j < n:
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            spans.append((i, min(j + 1, n)))
            i = j + 1
        else:
            i += 1
    return spans


def _sub_outside_literals(sql: str, pattern: str, repl, flags=re.IGNORECASE) -> str:
    spans = _literal_spans(sql)
    out, last = [], 0
    for s, e in spans + [(len(sql), len(sql))]:
        seg = sql[last:s]
        out.append(re.sub(pattern, repl, seg, flags=flags))
        out.append(sql[s:e])
        last = e
    return "".join(out)


def _split_args(s: str) -> List[str]:
    args, depth, cur, i = [], 0, [], 0
    in_lit = False
    while i < len(s):
        ch = s[i]
        if in_lit:
            cur.append(ch)
            if ch == "'":
                if i + 1 < len(s) and s[i + 1] == "'":
                    cur.append("'")
                    i += 1
                else:
                    in_lit = False
        elif ch == "'":
            in_lit = True
            cur.append(ch)
        elif ch == "(":
            depth += 1
            cur.append(ch)
        elif ch == ")":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            args.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
        i += 1
    if cur or args:
        args.append("".join(cur).strip())
    return args


def _find_call(sql: str, name: str, start: int = 0) -> Optional[Tuple[int, int, str]]:
    """Primera llamada name( ... ) fuera de literales. Devuelve (ini, fin, contenido)."""
    spans = _literal_spans(sql)
    pat = re.compile(r"(?<![\w.])" + name + r"\s*\(", re.IGNORECASE)
    pos = start
    while True:
        m = pat.search(sql, pos)
        if not m:
            return None
        if any(s <= m.start() < e for s, e in spans):
            pos = m.end()
            continue
        i, depth = m.end(), 1
        in_lit = False
        while i < len(sql) and depth:
            ch = sql[i]
            if in_lit:
                if ch == "'":
                    if i + 1 < len(sql) and sql[i + 1] == "'":
                        i += 1
                    else:
                        in_lit = False
            elif ch == "'":
                in_lit = True
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            i += 1
        return m.start(), i, sql[m.end():i - 1]


def _lit(a: str) -> Optional[str]:
    a = a.strip()
    if len(a) >= 2 and a[0] == "'" and a[-1] == "'":
        return a[1:-1].replace("''", "'")
    return None


# ─────────────────────────── fechas ───────────────────────────

def _ts_expr(base: str, mods: List[str]) -> str:
    """Expresión timestamp (sin tz) a partir de base + modificadores estilo SQLite."""
    b = base.strip()
    localtime = any((_lit(m) or "").lower() == "localtime" for m in mods)
    if (_lit(b) or "").lower() == "now":
        if localtime:
            e = f"(now() AT TIME ZONE '{TZ_LOCAL}')"
        else:
            e = "(now() AT TIME ZONE 'UTC')"
    else:
        e = f"NULLIF(CAST({b} AS TEXT), '')::timestamp"
    for m in mods:
        v = _lit(m)
        if v is None or v.lower() == "localtime":
            continue
        mm = re.match(r"^([+-]?\d+)\s+(day|days|month|months|year|years|hour|hours|minute|minutes)$", v.strip(), re.I)
        if mm:
            e = f"({e} + INTERVAL '{mm.group(1)} {mm.group(2)}')"
        elif v.lower() == "start of month":
            e = f"date_trunc('month', {e})"
        elif v.lower() == "start of year":
            e = f"date_trunc('year', {e})"
    return e


def _rewrite_dates(sql: str) -> str:
    while True:
        found = None
        for fn in ("strftime", "datetime", "date"):
            f = _find_call(sql, fn)
            if f and (found is None or f[0] < found[1][0]):
                found = (fn, f)
        if not found:
            return sql
        fn, (s, e, inner) = found
        args = [_rewrite_dates(a) for a in _split_args(inner)]
        if fn == "strftime":
            fmt = _lit(args[0]) or "%Y-%m-%d"
            ts = _ts_expr(args[1], args[2:])
            if fmt == "%w":
                rep = f"CAST(EXTRACT(DOW FROM {ts}) AS INTEGER)::text"
            else:
                pg = fmt
                for a, b in _STRF_MAP:
                    pg = pg.replace(a, b)
                rep = f"to_char({ts}, '{pg}')"
        elif fn == "datetime":
            ts = _ts_expr(args[0] if args else "'now'", args[1:])
            rep = f"to_char({ts}, 'YYYY-MM-DD HH24:MI:SS')"
        else:  # date
            ts = _ts_expr(args[0] if args else "'now'", args[1:])
            rep = f"to_char({ts}, 'YYYY-MM-DD')"
        sql = sql[:s] + rep + sql[e:]


def _rewrite_minmax(sql: str) -> str:
    """MAX(a, b) / MIN(a, b) escalares de SQLite -> GREATEST / LEAST (los agregados de 1 argumento no se tocan)."""
    for fn, repl in (("max", "GREATEST"), ("min", "LEAST")):
        pos = 0
        while True:
            f = _find_call(sql, fn, pos)
            if not f:
                break
            s0, e0, inner = f
            args = _split_args(inner)
            if len(args) >= 2:
                new = repl + "(" + ", ".join(_rewrite_minmax(a) for a in args) + ")"
                sql = sql[:s0] + new + sql[e0:]
                pos = s0 + len(new)
            else:
                pos = s0 + len(fn) + 1
    return sql


# ─────────────────────────── DDL ───────────────────────────

def _translate_ddl(sql: str) -> str:
    sql = _sub_outside_literals(sql, r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b", "SERIAL PRIMARY KEY")
    sql = _sub_outside_literals(sql, r"\bINTEGER\s+PRIMARY\s+KEY\b", "SERIAL PRIMARY KEY")
    sql = _sub_outside_literals(sql, r"\bAUTOINCREMENT\b", "")
    sql = _sub_outside_literals(sql, r"\b(DATETIME|TIMESTAMP|DATE|TIME)\b(?!\s*\()", "TEXT")
    sql = _sub_outside_literals(sql, r"\b(REAL|FLOAT|DOUBLE)\b", "NUMERIC")
    sql = _sub_outside_literals(sql, r"\bBOOLEAN\b", "INTEGER")
    # SQLite guarda decimales en columnas declaradas INTEGER (afinidad flexible: 4.4667 queda REAL).
    # Para no truncar datos, todo INTEGER que no sea id / *_id pasa a NUMERIC (las FK van por *_id).
    fk_cols = set()
    for fk in re.finditer(r"FOREIGN\s+KEY\s*\(([^)]*)\)", sql, re.I):
        fk_cols.update(c.strip().strip('"').lower() for c in fk.group(1).split(","))
    sql = _sub_outside_literals(
        sql, r"(?<![\w.])(\w+)(\s+)INTEGER\b(?![^,]*\bREFERENCES\b)",
        lambda m: m.group(0) if (m.group(1).lower() == "id" or m.group(1).lower().endswith("_id")
                                 or m.group(1).lower() in fk_cols)
        else f"{m.group(1)}{m.group(2)}NUMERIC")
    sql = _sub_outside_literals(
        sql, r"\bDEFAULT\s+CURRENT_TIMESTAMP\b",
        "DEFAULT (to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'))")
    sql = _sub_outside_literals(sql, r"\bDEFAULT\s+TRUE\b", "DEFAULT 1")
    sql = _sub_outside_literals(sql, r"\bDEFAULT\s+FALSE\b", "DEFAULT 0")
    sql = _sub_outside_literals(
        sql, r"\bADD\s+COLUMN\s+(?!IF\s+NOT\s+EXISTS)", "ADD COLUMN IF NOT EXISTS ")
    return sql


# ─────────────────────────── INSERT OR ... ───────────────────────────

def _strip_tail(sql: str) -> str:
    return sql.rstrip().rstrip(";").rstrip()


def _rewrite_insert_or(sql: str) -> str:
    m = re.match(r"^\s*INSERT\s+OR\s+(IGNORE|REPLACE)\s+INTO\s+", sql, re.IGNORECASE)
    if not m:
        return sql
    kind = m.group(1).upper()
    body = re.sub(r"^\s*INSERT\s+OR\s+(IGNORE|REPLACE)\s+INTO", "INSERT INTO", sql, count=1, flags=re.IGNORECASE)
    body = _strip_tail(body)
    if kind == "IGNORE":
        return body + " ON CONFLICT DO NOTHING"
    tm = re.match(r"^\s*INSERT\s+INTO\s+\"?(\w+)\"?\s*\(([^)]*)\)", body, re.IGNORECASE)
    if not tm:
        return body + " ON CONFLICT DO NOTHING"
    table = tm.group(1).lower()
    cols = [c.strip().strip('"') for c in tm.group(2).split(",")]
    key = REPLACE_KEYS.get(table)
    if not key:
        raise ValueError(f"INSERT OR REPLACE sobre '{table}' sin clave conocida en sql_compat.REPLACE_KEYS")
    sets = [f"{c}=EXCLUDED.{c}" for c in cols if c not in key]
    if not sets:
        return body + " ON CONFLICT DO NOTHING"
    return f"{body} ON CONFLICT ({', '.join(key)}) DO UPDATE SET {', '.join(sets)}"


# ─────────────────────────── entrada principal ───────────────────────────

def translate_sql(sql: str) -> str:
    """SQLite → PostgreSQL (un solo statement). Placeholders siguen como '?'."""
    s = strip_comments(sql).strip()
    up = s.upper()

    if up.startswith("PRAGMA"):
        m = re.match(r"^PRAGMA\s+table_info\(\s*\"?(\w+)\"?\s*\)", s, re.IGNORECASE)
        if m:
            return (f"SELECT column_name AS name FROM information_schema.columns "
                    f"WHERE table_schema = current_schema() AND table_name = '{m.group(1).lower()}' "
                    f"ORDER BY ordinal_position")
        return "SELECT 1"  # PRAGMA foreign_keys etc.: no-op

    if re.match(r"^SELECT\s+sql\s+FROM\s+sqlite_master", s, re.IGNORECASE):
        # migraciones SQLite que inspeccionan el DDL guardado: en Postgres ya nacen con CASCADE
        return "SELECT 'ON DELETE CASCADE' AS sql"

    if re.match(r"^SELECT\s+name\s+FROM\s+sqlite_master", s, re.IGNORECASE):
        m = re.search(r"name\s*=\s*\?", s, re.IGNORECASE)
        if m:
            return ("SELECT table_name AS name FROM information_schema.tables "
                    "WHERE table_schema = current_schema() AND table_type='BASE TABLE' AND table_name = ?")
        return ("SELECT table_name AS name FROM information_schema.tables "
                "WHERE table_schema = current_schema() AND table_type='BASE TABLE'")

    if up.startswith(("CREATE TABLE", "ALTER TABLE")):
        s = _translate_ddl(s)  # antes de fechas: TIMESTAMP→TEXT no debe tocar el '::timestamp' generado
    s = _rewrite_dates(s)
    s = _rewrite_minmax(s)
    s = _sub_outside_literals(s, r"\bIFNULL\s*\(", "COALESCE(")
    s = _sub_outside_literals(s, r"\bINSTR\s*\(", "strpos(")
    s = _sub_outside_literals(s, r"\bLIKE\b", "ILIKE")
    s = _sub_outside_literals(s, r"\bAS\s+REAL\b", "AS NUMERIC")
    s = _sub_outside_literals(s, r"(\?)(\s+IS\s+(?:NOT\s+)?NULL)", r"CAST(? AS TEXT)\2")
    s = _sub_outside_literals(s, r"\s+COLLATE\s+NOCASE\b", "")

    s = _sub_outside_literals(s, r"\s+INDEXED\s+BY\s+\w+", "")
    s = _sub_outside_literals(s, r"\s+NOT\s+INDEXED\b", "")
    s = fix_group_by(s)
    s = add_implicit_order(s)
    s = _rewrite_insert_or(s)
    return s


def convert_placeholders(sql: str) -> str:
    """'?' → $1, $2... fuera de literales."""
    counter = [0]

    def _r(_m):
        counter[0] += 1
        return f"${counter[0]}"

    return _sub_outside_literals(sql, r"\?", _r, flags=0)


def split_statements(script: str) -> List[str]:
    script = strip_comments(script)
    spans = _literal_spans(script)
    out, cur, start = [], 0, 0
    for i, ch in enumerate(script):
        if ch == ";" and not any(s <= i < e for s, e in spans):
            stmt = script[start:i].strip()
            if stmt:
                out.append(stmt)
            start = i + 1
    tail = script[start:].strip()
    if tail:
        out.append(tail)
    return out
