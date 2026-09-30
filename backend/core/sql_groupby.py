"""
GROUP BY permisivo de SQLite → Postgres.

SQLite acepta columnas sin agregar que no están en el GROUP BY (toma la de una fila
cualquiera del grupo). Postgres lo rechaza. Se completa el GROUP BY con esas columnas:
cuando dependen funcionalmente de la clave agrupada, el resultado es idéntico.
No toca UNION/INTERSECT/EXCEPT, expresiones con subselect ni con placeholders '?'.
"""
import re
from typing import List, Optional, Tuple

_AGG_RE = re.compile(
    r"\b(COUNT|SUM|MIN|MAX|AVG|TOTAL|GROUP_CONCAT|STRING_AGG|ARRAY_AGG|EVERY|BOOL_AND|BOOL_OR)\s*\(", re.I)
_KW_RE = re.compile(
    r"\b(SELECT|FROM|WHERE|GROUP\s+BY|HAVING|ORDER\s+BY|LIMIT|OFFSET|UNION|INTERSECT|EXCEPT|WINDOW)\b", re.I)
_ALIAS_STOP = {"END", "DESC", "ASC", "NULL", "NOT", "AND", "OR", "IS", "THEN", "ELSE", "WHEN", "IN",
               "LIKE", "ILIKE", "BETWEEN"}
_LIT_RE = re.compile(r"'(?:[^']|'')*'")


def _literal_spans(sql: str) -> List[Tuple[int, int]]:
    return [(m.start(), m.end()) for m in _LIT_RE.finditer(sql)]


def _mask(sql: str) -> str:
    """Igual longitud; literales y contenido entre paréntesis reemplazados por espacios."""
    out: List[str] = []
    depth = 0
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch == "'":
            m = _LIT_RE.match(sql, i)
            end = m.end() if m else n
            out.append(" " * (end - i))
            i = end
            continue
        if ch == "(":
            out.append("(" if depth == 0 else " ")
            depth += 1
        elif ch == ")":
            depth -= 1
            out.append(")" if depth == 0 else " ")
        else:
            out.append(ch if depth == 0 else " ")
        i += 1
    return "".join(out)


def _split_top(masked: str, text: str) -> List[str]:
    parts, start = [], 0
    for i, ch in enumerate(masked):
        if ch == ",":
            parts.append(text[start:i].strip())
            start = i + 1
    parts.append(text[start:].strip())
    return [p for p in parts if p]


def _strip_subselects(text: str) -> str:
    out: List[str] = []
    i, n = 0, len(text)
    while i < n:
        if text[i] == "(" and re.match(r"\(\s*SELECT\b", text[i:], re.I):
            depth, j = 0, i
            while j < n:
                if text[j] == "(":
                    depth += 1
                elif text[j] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            out.append("(x)")
            i = j + 1
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def _item_expr_alias(item: str) -> Tuple[str, Optional[str]]:
    masked = _mask(item)
    m = None
    for m_ in re.finditer(r"\bAS\s+\"?(\w+)\"?\s*$", masked, re.I):
        m = m_
    if m:
        return item[:m.start()].strip(), m.group(1)
    m2 = re.match(r"^(.*?(?:\)|\w))\s+([A-Za-z_]\w*)\s*$", masked, re.S)
    if m2 and m2.group(2).upper() not in _ALIAS_STOP and not re.search(r"[+\-*/|<>=]\s*$", m2.group(1)):
        return item[:len(m2.group(1))].strip(), m2.group(2)
    return item.strip(), None


def _norm(e: str) -> str:
    return re.sub(r"\s+", "", e).lower()


def _fix_one(sql: str) -> str:
    masked = _mask(sql)
    kws = [(m.start(), re.sub(r"\s+", " ", m.group(1).upper())) for m in _KW_RE.finditer(masked)]
    if not kws or kws[0][1] != "SELECT":
        return sql
    if any(k in ("UNION", "INTERSECT", "EXCEPT") for _, k in kws):
        return sql
    pos = {}
    for p, k in kws:
        pos.setdefault(k, p)
    if "GROUP BY" not in pos or "FROM" not in pos:
        return sql
    sel_start = pos["SELECT"] + len("SELECT")
    sel_masked = masked[sel_start:pos["FROM"]]
    sel_txt = sql[sel_start:pos["FROM"]]
    off = re.match(r"\s*(DISTINCT\s+)?", sel_txt, re.I).end()
    items = _split_top(sel_masked[off:], sel_txt[off:])
    g_start = pos["GROUP BY"] + len("GROUP BY")
    ends = [p for p, k in kws if p > pos["GROUP BY"] and k in ("HAVING", "ORDER BY", "LIMIT", "OFFSET", "WINDOW")]
    g_end = min(ends) if ends else len(sql)
    g_txt, g_mask = sql[g_start:g_end], masked[g_start:g_end]
    groups = _split_top(g_mask, g_txt)
    grouped = {_norm(g) for g in groups}
    parsed = [_item_expr_alias(it) for it in items]
    for g in groups:
        if g.isdigit() and 1 <= int(g) <= len(parsed):
            grouped.add(_norm(parsed[int(g) - 1][0]))
    for g in groups:
        for e, a in parsed:
            if a and a.lower() == g.lower():
                grouped.add(_norm(e))
    alias_names = {al.lower() for _, al in parsed if al}
    plain_names = {e.strip().split('.')[-1].lower() for e, _ in parsed if re.fullmatch(r'(?:\w+\.)?\w+', e.strip())}
    changed = False
    new_items = list(items)
    for idx, (expr, alias) in enumerate(parsed):
        if re.fullmatch(r"(\w+\.)?\*", expr.strip()):
            continue
        core = _strip_subselects(_LIT_RE.sub("''", expr))
        if _AGG_RE.search(core) or re.search(r"\bOVER\s*\(", core, re.I):
            continue
        if "(x)" in core or not re.search(r"[A-Za-z_]", core.replace("''", "")):
            continue
        if _norm(expr) in grouped:
            continue
        if re.search(r"(<=|>=|<>|!=|(?<![<>])=|<|>)", _mask(expr)) and not re.search(r"\bCASE\b", core, re.I):
            continue  # booleana: MIN() no aplica
        plain = re.fullmatch(r"(?:\w+\.)?(\w+)", expr.strip())
        name = alias or (plain.group(1) if plain else '"' + expr.strip().replace('"', "") + '"')
        new_items[idx] = f"MIN({expr}) AS {name}"
        changed = True
    # ORDER BY con columnas planas no agrupadas (SQLite lo permite)
    o_txt_new = None
    if "ORDER BY" in pos:
        o_start = pos["ORDER BY"] + len("ORDER BY")
        o_ends = [p for p, k in kws if p > pos["ORDER BY"] and k in ("LIMIT", "OFFSET")]
        o_end = min(o_ends) if o_ends else len(sql)
        o_items = _split_top(masked[o_start:o_end], sql[o_start:o_end])
        fixed = []
        for it in o_items:
            m = re.match(r"^(\w+\.\w+|\w+)(\s+(?:ASC|DESC))?(\s+NULLS\s+(?:FIRST|LAST))?\s*$", it, re.I)
            if m and not m.group(1).isdigit() and _norm(m.group(1)) not in grouped                     and m.group(1).lower() not in alias_names and m.group(1).lower() not in plain_names:
                it = f"MIN({m.group(1)}){m.group(2) or ''}{m.group(3) or ''}"
                changed = True
            fixed.append(it)
        o_txt_new = " " + ", ".join(fixed) + " "
    if not changed:
        return sql
    distinct = "DISTINCT " if re.match(r"\s*DISTINCT\b", sel_txt, re.I) else ""
    out = sql[:sel_start] + " " + distinct + ", ".join(new_items) + " " + sql[pos["FROM"]:]
    if o_txt_new is not None:
        shift = len(out) - len(sql)
        out = out[:o_start + shift] + o_txt_new + out[o_end + shift:]
    return out


def fix_group_by(sql: str) -> str:
    """Aplica la corrección al SELECT externo y, recursivamente, a cada subselect."""
    if not re.search(r"\bGROUP\s+BY\b", sql, re.I):
        return sql
    spans = _literal_spans(sql)

    def in_lit(k: int) -> bool:
        return any(s <= k < e for s, e in spans)

    out: List[str] = []
    i, n = 0, len(sql)
    while i < n:
        if sql[i] == "(" and not in_lit(i) and re.match(r"\(\s*SELECT\b", sql[i:], re.I):
            depth, j = 0, i
            while j < n:
                if not in_lit(j):
                    if sql[j] == "(":
                        depth += 1
                    elif sql[j] == ")":
                        depth -= 1
                        if depth == 0:
                            break
                j += 1
            out.append("(" + fix_group_by(sql[i + 1:j]) + ")")
            i = j + 1
        else:
            out.append(sql[i])
            i += 1
    return _fix_one("".join(out))


def _top_parts(sql: str):
    masked = _mask(sql)
    kws = [(m.start(), re.sub(r"\s+", " ", m.group(1).upper())) for m in _KW_RE.finditer(masked)]
    return masked, kws


def add_implicit_order(sql: str) -> str:
    """
    SQLite devuelve los grupos ordenados por la clave del GROUP BY aunque no haya ORDER BY;
    Postgres (HashAggregate) no. Se agrega ese ORDER BY implícito. Además, en SELECT DISTINCT
    las expresiones del ORDER BY que no están en la lista se agregan como columnas ocultas
    (__ordN) porque Postgres lo exige.
    """
    masked, kws = _top_parts(sql)
    if not kws or kws[0][1] != "SELECT" or any(k in ("UNION", "INTERSECT", "EXCEPT") for _, k in kws):
        return sql
    pos = {}
    for p, k in kws:
        pos.setdefault(k, p)
    sel_start = pos["SELECT"] + len("SELECT")
    is_distinct = re.match(r"\s*DISTINCT\b", sql[sel_start:], re.I) is not None

    if "ORDER BY" not in pos:
        if "GROUP BY" not in pos or "?" in sql[pos["GROUP BY"]:]:
            return sql
        g_start = pos["GROUP BY"] + len("GROUP BY")
        ends = [p for p, k in kws if p > pos["GROUP BY"] and k in ("HAVING", "LIMIT", "OFFSET", "WINDOW")]
        g_end = min(ends) if ends else len(sql)
        # HAVING va antes de ORDER BY; el ORDER BY se inserta antes de LIMIT/OFFSET
        lim = [p for p, k in kws if p > pos["GROUP BY"] and k in ("LIMIT", "OFFSET")]
        at = min(lim) if lim else len(sql)
        gtxt = sql[g_start:g_end].strip().rstrip(";")
        if not gtxt or "(SELECT" in gtxt.upper():
            return sql
        return sql[:at].rstrip().rstrip(";") + " ORDER BY " + gtxt + " " + sql[at:]

    if not is_distinct or "FROM" not in pos:
        return sql
    o_start = pos["ORDER BY"] + len("ORDER BY")
    ends = [p for p, k in kws if p > pos["ORDER BY"] and k in ("LIMIT", "OFFSET")]
    o_end = min(ends) if ends else len(sql)
    order_items = _split_top(masked[o_start:o_end], sql[o_start:o_end])
    sel_masked = masked[sel_start:pos["FROM"]]
    sel_txt = sql[sel_start:pos["FROM"]]
    off = re.match(r"\s*(DISTINCT\s+)?", sel_txt, re.I).end()
    parsed = [_item_expr_alias(it) for it in _split_top(sel_masked[off:], sel_txt[off:])]
    have = {_norm(e) for e, _ in parsed} | {a.lower() for _, a in parsed if a}
    missing = []
    for it in order_items:
        expr = re.sub(r"\s+(ASC|DESC)\s*$", "", it, flags=re.I).strip()
        if expr.isdigit() or _norm(expr) in have or expr.lower() in have or "?" in expr:
            continue
        missing.append(expr)
        have.add(_norm(expr))
    if not missing:
        return sql
    extra = ", " + ", ".join(f"{e} AS __ord{i}" for i, e in enumerate(missing, 1)) + " "
    return sql[:pos["FROM"]].rstrip() + extra + sql[pos["FROM"]:]
