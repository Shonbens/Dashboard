"""
Import of the house allocation workbook ("אלוקציה פרימיום"): every sheet in that layout becomes an allocation model.

Layout (as in the Excel):
  header row        מספר נייר | שם נייר | אחוז ראשי [| אחוז יחסי] | תשואה ברוטו | ...
  section rows      securities, closed by a "סה"כ <section>" row (e.g. "סה"כ ממשלתי צמוד")
  "תרומת קרנות"     fund look-through rows – recalculated by the site, not imported
  side panel        "דמי ניהול חוזה", "אינפלציה גלומה" (+ red/green conditional formats = control bands)
  side tables       index sector weights (ת"א 125 / ת"א 90 / …, S&P / NASDAQ / …) and real-estate shares

Newer sheets have an "אחוז מנייתי" cell: אחוז ראשי is then the weight inside the sleeve (equity / bonds).
Older sheets hold portfolio weights; they are converted to sleeve weights using the equity share in the sheet name.
"""
from __future__ import annotations

import io
import re

from openpyxl import load_workbook

from pricing import normalize_identifier

SECTION_RULES = [  # order matters: more specific first
    ("מניות בארץ", "eq_il"), ("מניות בחו", "eq_foreign"),
    ("ממשלתי צמוד", "gov_cpi"), ("ממשלתי חו", "gov_usd"), ("ממשלתי שקלי", "gov_nominal"), ("ממשלתי משתנה", "gov_float"),
    ("קונצרני צמוד דולר", "corp_usd"), ("קונצרני צמוד", "corp_cpi"), ("קונצרני שקלי", "corp_nominal"),
    ("קונצרני ריבית משתנה", "corp_float"), ("קונצרני חו", "corp_hedged"), ("קרנות", "funds"),
]
EQUITY_SECTIONS = {"eq_il", "eq_foreign"}
IL_SECTOR_ALIASES = {"מדד 125": 'ת"א 125', 'ת"א 125': 'ת"א 125', 'ת"א125': 'ת"א 125', 'ת"א90': 'ת"א90', 'ת"א 90': 'ת"א90'}
FOREIGN_EXPOSURE = {"S&P 500": "S&P 500", "SP 500": "S&P 500", "NASDAQ": "NASDAQ", "RUSSELL": "RUSSELL", "STOXX 600": "STOXX 600",
                    "STOXX": "STOXX 600"}
GICS = ["Information Technology", "Health Care", "Financials", "Consumer Discretionary", "Communication Services", "Industrials",
        "Consumer Staples", "Energy", "Utilities", "Real Estate", "Materials"]
IL_SECTORS = ["טכנולוגיה", "בנקים", "שרותים פיננסים", "ביטוח", "נדלן ובנייה", "ביומד", "מסחר ושרותים", "תעשייה",
              "אנרגיה וחיפושי נפט וגז", "השקעה ואחזקות", "ביטחונית"]
IL_COL_KEYS = [('ת"א 125', "ta125"), ('ת"א 90', "ta90"), ('ת"א90', "ta90"), ("מניות", "fund_eq"), ("יתר", "fund_other"), ("MID", "mid")]
FOREIGN_COL_KEYS = [("s&p", "SP"), ("nasdaq", "NDX"), ("ndx", "NDX"), ("stoxx", "STOXX"), ("שאר העולם", "ROW"), ("kba", "ROW"),
                    ("ישיר גלובל", "GLOBAL"), ("russ", "RUSSELL")]
RE_HEADERS = [("תל בונד 60", "תלבונד 60|תל בונד 60|תל-בונד 60"), ("תל בונד שקלי", "תלבונד שקלי|תל בונד שקלי|תל-בונד שקלי"),
              ("ללא מניות", "ללא מניות"), ("חברות מדורג", "חברות מדורג"), ("תשואות", "תשואות|תשו "), ("תיק קונצרני", "תיק קונצרני"),
              ('אג"ח חברות', 'אג"ח חברות(?! מדורג)'), ("אג\"ח כללי", "כללי")]


def _txt(v) -> str:
    if v is None:
        return ""
    s = str(v).replace("״", '"').replace("׳", "'").replace("\n", " ")
    return re.sub(r"\s+", " ", s).strip()


def _num(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace("%", "").replace(",", "").strip())
    except ValueError:
        return None


def _section_of(label: str) -> str | None:
    for key, sec in SECTION_RULES:
        if key in label:
            return sec
    return None


def _find(ws, pred, max_row=None):
    for row in ws.iter_rows(max_row=max_row or ws.max_row):
        for c in row:
            if c.value is not None and pred(_txt(c.value)):
                return c
    return None


def _header_row(ws, must: list[tuple[str, ...]], max_row: int):
    """First row containing a cell for every group of alternatives in `must` (side tables' header rows)."""
    for row in ws.iter_rows(max_row=max_row):
        texts = [(_txt(c.value).lower(), c) for c in row if c.value is not None]
        hits = [next((c for t, c in texts if any(t == a or t.startswith(a) for a in alts)), None) for alts in must]
        if all(hits):
            return hits[0]
    return None


def _cf_band(ws, coord: str, scale: float = 1.0):
    lo = hi = None
    for rng in ws.conditional_formatting:
        if coord not in rng.sqref:
            continue
        for rule in rng.rules:
            if rule.type != "cellIs" or not rule.formula:
                continue
            try:
                val = float(rule.formula[0]) * scale
            except ValueError:
                continue
            # The Excel uses 0.4499 / 0.5001 as "< 45%" / "> 50%": keep 1 decimal for % bands
            if rule.operator == "lessThan":
                lo = round(val, 1 if scale > 1 else 2)
            elif rule.operator == "greaterThan":
                hi = round(val, 1 if scale > 1 else 2)
    return [lo, hi] if lo is not None and hi is not None else None


def _equity_from_name(name: str) -> float | None:
    m = re.findall(r"(\d{1,3})\s*%", name)
    return float(m[-1]) if m else None


def _fund_cap(name: str, title: str) -> float | None:
    for text in (name, title):
        m = re.search(r"(?:מ\.?\s*ק\.?|מוגבל(?: קרנות)?)\s*\(?\s*(\d{2})", text or "")
        if m:
            return float(m.group(1))
    return None


def _id_from(raw, name: str) -> tuple[str, str | None]:
    """Foreign securities appear with an 8-digit local code (e.g. 70961578) and the ticker as the name."""
    from pricing import engine as pricing_engine

    sid = normalize_identifier(raw)
    ticker_like = re.fullmatch(r"[A-Z][A-Z.]{0,6}( [A-Z]{2})?", name or "")
    if ticker_like and sid.isdigit() and (re.fullmatch(r"[67]\d{7}", sid) or not pricing_engine.directory.get(sid)):
        return name.split()[0], f"{sid} → {name.split()[0]}"
    return sid, None


def parse_sheet(ws, ws_formulas) -> dict | None:
    header = _find(ws_formulas, lambda t: t == "מספר נייר", max_row=15)
    if header is None:
        return None
    hr = header.row
    cols = {}
    for c in ws_formulas[hr]:
        t = _txt(c.value)
        if t == "מספר נייר":
            cols["id"] = c.column
        elif t == "שם נייר":
            cols["name"] = c.column
        elif ("אחוז" in t and "ראשי" in t) or t == "אחזקה":
            cols["main"] = c.column
        elif "אחוז" in t and "יחסי" in t:
            cols["rel"] = c.column
    if "main" not in cols and "rel" not in cols:
        return None
    # need at least one section total row to call it an allocation sheet
    if not _find(ws_formulas, lambda t: t.startswith('סה"כ') and _section_of(t) is not None):
        return None

    title = _txt(ws.cell(hr - 1, cols.get("id", 3)).value) or _txt(ws.cell(hr - 1, cols.get("name", 4)).value)
    eq_cell = _find(ws_formulas, lambda t: t.startswith("אחוז מנייתי"), max_row=hr)
    eq_param = _num(ws.cell(eq_cell.row + 1, eq_cell.column).value) if eq_cell else None
    sleeve_weights = eq_param is not None
    equity = (eq_param * 100 if eq_param is not None and eq_param <= 1 else eq_param) if sleeve_weights else (
        _equity_from_name(ws.title) if _equity_from_name(ws.title) is not None else _equity_from_name(title))
    warnings = []

    # ---- rows by section
    rows, pending = [], []
    id_c, name_c = cols.get("id"), cols.get("name")
    w_c = cols.get("main") or cols.get("rel")
    for r in range(hr + 1, ws.max_row + 1):
        label = _txt(ws_formulas.cell(r, id_c).value) if id_c else ""
        label_n = _txt(ws_formulas.cell(r, name_c).value) if name_c else ""
        text = label if label.startswith('סה"כ') or label.startswith('עו"ש') else label_n
        if text.startswith('סה"כ') or text.startswith('עו"ש'):
            sec = _section_of(text)
            if sec:
                for p in pending:
                    p["section"] = sec
                rows.extend(pending)
            elif pending:
                warnings.append(f"{len(pending)} שורות לפני ״{text}״ לא שויכו לסעיף")
            pending = []
            if text.startswith('עו"ש'):
                break
            continue
        if "תרומת קרנות" in label_n or "תרומת קרנות" in label:
            continue
        raw_id = ws.cell(r, id_c).value
        if raw_id is None or str(raw_id).startswith("="):
            continue
        name = _txt(ws.cell(r, name_c).value) if name_c else ""
        if name.startswith("#") or name.startswith("="):
            name = ""
        sid, conv = _id_from(raw_id, name)
        if not sid or not re.search(r"[0-9A-Za-z]", sid) or not (any(ch.isdigit() for ch in sid) or sid.isascii()):
            continue
        if conv:
            warnings.append(f"קוד זר הומר לטיקר: {conv}")
        w = _num(ws.cell(r, w_c).value)
        if w is None and cols.get("rel") and w_c != cols["rel"]:
            w = _num(ws.cell(r, cols["rel"]).value)
        a, b = ws.cell(r, 1).value, ws.cell(r, 2).value
        pending.append({"id": sid, "name": name or None, "w": w or 0.0, "a": a, "b": b})

    # weights: fractions -> %
    ws_max = max([x["w"] for x in rows] or [0])
    scale = 100 if ws_max <= 1.5 else 1
    out_rows = []
    for x in rows:
        row = {"section": x["section"], "id": x["id"], "weight": round(x["w"] * scale, 6)}
        if x["name"]:
            row["name"] = x["name"]
        a, b = x["a"], x["b"]
        at, bt = _txt(a), _txt(b)
        if x["section"] == "eq_il":
            if bt in IL_SECTOR_ALIASES:
                row["sector"] = IL_SECTOR_ALIASES[bt]
            elif bt in IL_SECTORS:
                row["sector"] = bt
        elif x["section"] == "eq_foreign":
            if at:
                row["country"] = {'ארה"ב': "ארה״ב"}.get(at, at)
            if bt.upper() in FOREIGN_EXPOSURE:
                row["exposure"] = FOREIGN_EXPOSURE[bt.upper()]
            elif bt in GICS:
                row["exposure"] = bt
        else:
            for v in (a, b):
                n = _num(v)
                if n is not None and float(n).is_integer() and 1 <= n <= 4:
                    row["bucket"] = int(n)
            ind = bt if bt and _num(b) is None else (at if at and _num(a) is None else "")
            if ind and not ind.startswith("=") and ind not in ("ישראל", 'ארה"ב'):
                row["industry"] = ind
        out_rows.append(row)

    # ---- settings from the side panel
    settings: dict = {}
    for label, key, mult in (("דמי ניהול חוזה", "contract_fee", 100), ("אינפלציה גלומה", "inflation", 100)):
        c = _find(ws_formulas, lambda t, lb=label: t == lb, max_row=12)
        if c:
            v = _num(ws.cell(c.row, c.column + 1).value)
            if v is not None:
                settings[key] = round(v * mult if v < 1 else v, 4)
    cap = _fund_cap(ws.title, title)
    if cap:
        settings["fund_cap"] = cap
    bands = {}
    for label, key, col_off, scale_ in (('סה"כ מח"מ בתיק', "duration", 2, 1), ('סה"כ צמוד', "linked", 3, 100),
                                       ('סה"כ שקלי', "shekel", 3, 100), ('סה"כ חשיפה מנייתית לחו"ל', "foreign_eq", 2, 100)):
        c = _find(ws_formulas, lambda t, lb=label: t == lb, max_row=30)
        if c:
            band = _cf_band(ws_formulas, ws_formulas.cell(c.row, c.column + col_off).coordinate, scale_)
            if band:
                bands[key] = band
    if bands:
        settings["bands"] = bands

    # ---- assumption tables
    refs: dict = {}
    hdr = _header_row(ws_formulas, [('ת"א 125',), ('ת"א 90', 'ת"א90')], 80)
    if hdr:
        colmap = {}
        for c in ws_formulas[hdr.row]:
            t = _txt(c.value)
            for name_, key in IL_COL_KEYS:
                if t == name_ and key not in colmap.values():
                    colmap[c.column] = key
        table = {}
        for r in range(hdr.row + 1, hdr.row + 16):
            lab = _txt(ws_formulas.cell(r, hdr.column - 1).value)
            if lab in IL_SECTORS:
                vals = {k: _num(ws.cell(r, col).value) for col, k in colmap.items()}
                table[lab] = {k: round(v * 100, 10) for k, v in vals.items() if v is not None}
        if table:
            refs["il_sectors"] = table
    fhdr = _header_row(ws_formulas, [("s&p",), ("nasdaq", "ndx")], 120)
    if fhdr:
        colmap = {}
        for c in ws_formulas[fhdr.row]:
            t = _txt(c.value).lower()
            for name_, key in FOREIGN_COL_KEYS:
                if t.startswith(name_) and key not in colmap.values():
                    colmap[c.column] = key
        table = {}
        for r in range(fhdr.row + 1, fhdr.row + 16):
            lab = _txt(ws_formulas.cell(r, fhdr.column - 1).value)
            lab = "שבבים" if lab == "שבבים" else lab
            if lab in GICS or lab == "שבבים":
                vals = {k: _num(ws.cell(r, col).value) for col, k in colmap.items()}
                table[lab] = {k: round(v * 100, 10) for k, v in vals.items() if v is not None}
        if table:
            refs["foreign_sectors"] = table
    re_row = _find(ws_formulas, lambda t: t == "נדלן מניב בישראל", max_row=120)
    if re_row:
        header_row = re_row.row - 2 if _txt(ws_formulas.cell(re_row.row - 2, re_row.column + 1).value) else re_row.row - 1
        pats = []
        bench = None
        for c in ws_formulas[header_row]:
            t = _txt(c.value)
            v = _num(ws.cell(re_row.row, c.column).value)
            if not t or v is None or c.column <= re_row.column:
                continue
            for key, pattern in RE_HEADERS:
                if key in t:
                    pats.append({"label": t, "pattern": pattern, "share": round(v * 100, 2)})
                    if key == "תל בונד 60":
                        bench = round(v * 100, 2)
                    break
        if pats:
            refs["re_patterns"] = pats
        if bench:
            refs["re_benchmark"] = bench

    template = "israel" if "ישראל" in ws.title or "ישראל" in title else "global"
    return {
        "sheet": ws.title.strip(), "title": title, "hidden": ws.sheet_state != "visible", "template": template,
        "equity": equity, "sleeve_weights": sleeve_weights, "rows": out_rows, "settings": settings, "refs": refs,
        "warnings": warnings,
    }


def parse_allocation_workbook(content: bytes) -> list[dict]:
    wb_v = load_workbook(io.BytesIO(content), data_only=True)
    wb_f = load_workbook(io.BytesIO(content), data_only=False)
    out = []
    for ws in wb_v.worksheets:
        try:
            parsed = parse_sheet(ws, wb_f[ws.title])
        except Exception as e:  # one odd sheet must not break the import
            parsed = {"sheet": ws.title.strip(), "error": f"קריאת הגיליון נכשלה: {e}", "rows": [], "hidden": ws.sheet_state != "visible"}
        if parsed:
            out.append(parsed)
    return out


def finalize(sheet: dict, fund_equity_share: dict[str, float]) -> tuple[dict, list[dict], float]:
    """Sleeve weights + portfolio holdings. fund_equity_share: id -> equity fraction (for funds' sleeve)."""
    rows = [dict(r) for r in sheet["rows"]]
    for r in rows:
        if r["section"] == "funds":
            r["sleeve"] = "equity" if fund_equity_share.get(r["id"], 0) >= 0.5 else "bond"
    sleeve = lambda r: "equity" if r["section"] in EQUITY_SECTIONS or r.get("sleeve") == "equity" else "bond"  # noqa: E731
    eq = sheet.get("equity")
    if not sheet.get("sleeve_weights"):
        # portfolio weights -> weights inside each sleeve
        eq_sum = sum(r["weight"] for r in rows if sleeve(r) == "equity")
        if eq is None:
            eq = round(eq_sum, 2)
        for r in rows:
            base = eq if sleeve(r) == "equity" else 100 - eq
            r["weight"] = round(r["weight"] / base * 100, 6) if base > 0 else 0.0
    eq = float(eq or 0)
    holdings: dict[str, float] = {}
    for r in rows:
        f = r["weight"] * (eq / 100 if sleeve(r) == "equity" else 1 - eq / 100)
        holdings[r["id"]] = holdings.get(r["id"], 0) + f
    config = {"template": sheet["template"], "equity": eq, "rows": rows}
    if sheet.get("settings"):
        config["settings"] = sheet["settings"]
    if sheet.get("refs"):
        config["refs"] = sheet["refs"]
    hs = [{"id": k, "name": next((r.get("name") for r in rows if r["id"] == k and r.get("name")), None),
           "weight": round(v, 4), "fee": None} for k, v in holdings.items() if v > 0]
    return config, hs, eq
