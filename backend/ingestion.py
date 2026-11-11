"""Portfolio file ingestion: CSV / XLSX parsing, Hebrew+English header detection, weight normalisation."""
from __future__ import annotations

import io
import re
from typing import Any

import pandas as pd

from pricing import normalize_identifier

# Canonical field -> accepted header aliases (compared after normalisation)
COLUMN_ALIASES: dict[str, list[str]] = {
    "id": [
        "מספר נייר", "מס נייר", "מס' נייר", "קוד נייר", "מספר ני\"ע", "מס' ני\"ע", "מספר נייר ערך",
        "סימול", "מספר קרן", "ticker", "symbol", "security id", "security", "id", "isin", "code",
    ],
    "name": ["שם נייר", "שם הנייר", "שם", "שם נייר ערך", "שם ני\"ע", "שם קרן", "שם הקרן", "name", "security name", "description"],
    "weight": ["משקל", "משקל נוכחי", "אחוז", "% מהתיק", "שיעור מהתיק", "weight", "weight %", "allocation", "pct", "%"],
    "target_weight": ["משקל יעד", "יעד", "target", "target weight", "target %", "model weight"],
    "fee": ["דמי ניהול", "דמי ניהול %", "עלות שנתית", "fee", "fee %", "expense ratio", "ter", "mer"],
    "value": ["שווי", "שווי בש\"ח", "שווי שוק", "שווי נוכחי", "שווי אחזקה", "שווי בשקלים", "market value", "value", "value ils"],
    "quantity": ["כמות", "כמות יחידות", "יחידות", "quantity", "qty", "units", "shares", "holdings"],
}


def _norm_header(h: Any) -> str:
    s = str(h).strip().lower()
    s = s.replace("״", '"').replace("׳", "'")
    s = re.sub(r"\s+", " ", s)
    return s


_ALIAS_LOOKUP = {_norm_header(a): field for field, aliases in COLUMN_ALIASES.items() for a in aliases}


def _match_columns(headers: list[Any]) -> dict[str, int]:
    found: dict[str, int] = {}
    for idx, h in enumerate(headers):
        key = _norm_header(h)
        field = _ALIAS_LOOKUP.get(key)
        if field is None and key.endswith(":"):
            continue  # a label in a summary line ("מס' ניירות:", "שווי תיק:"), not a column header
        if field is None:
            # fuzzy: header contains an alias (e.g. "משקל בתיק (%)")
            for alias, f in _ALIAS_LOOKUP.items():
                if len(alias) >= 3 and alias in key:
                    # don't let "משקל יעד" be swallowed by "משקל"
                    if f == "weight" and any(t in key for t in ("יעד", "target")):
                        f = "target_weight"
                    field = f
                    break
        if field and field not in found:
            found[field] = idx
    return found


def _read_raw(filename: str, content: bytes) -> pd.DataFrame:
    """Decide by the file's contents, not its name: bank / broker exports named .xls are often HTML or tab-separated text."""
    head = content[:8]
    if head.startswith(b"PK"):                       # .xlsx / .xlsm
        return pd.read_excel(io.BytesIO(content), header=None, dtype=object)
    if head.startswith(b"\xd0\xcf\x11\xe0"):          # Excel 97-2003 .xls
        return pd.read_excel(io.BytesIO(content), header=None, dtype=object, engine="calamine")
    for enc in ("utf-8-sig", "utf-16", "cp1255", "latin-1"):
        try:
            text = content.decode(enc)
            if enc == "utf-16" and not content.startswith((b"\xff\xfe", b"\xfe\xff")):
                continue
            break
        except UnicodeDecodeError:
            continue
    if "<table" in text[:200_000].lower():           # HTML table saved as .xls
        tables = pd.read_html(io.StringIO(text), header=None)
        if not tables:
            raise ValueError("לא נמצאה טבלה בקובץ")
        return max(tables, key=len).astype(object)
    counts = {sep: text.count(sep) for sep in ("\t", ";", ",")}
    sep = max(counts, key=counts.get)
    return pd.read_csv(io.StringIO(text), header=None, dtype=object, sep=sep, skip_blank_lines=True)


# Bloomberg-style exchange codes in statement names -> Yahoo Finance suffix ("ACWD LN" -> ACWD.L)
_EXCH = {"LN": ".L", "US": "", "UN": "", "UW": "", "UQ": "", "UR": "", "UP": "", "GY": ".DE", "GR": ".DE", "GF": ".F",
         "FP": ".PA", "NA": ".AS", "SW": ".SW", "SE": ".SW", "VX": ".SW", "IM": ".MI", "SM": ".MC", "JP": ".T", "JT": ".T",
         "HK": ".HK", "CN": ".TO", "CT": ".TO", "AU": ".AX", "AT": ".AX", "ID": ".IR", "BB": ".BR", "GA": ".AT",
         "SS": ".ST", "DC": ".CO", "NO": ".OL", "FH": ".HE", "PL": ".LS", "AV": ".VI", "PW": ".WA", "SP": ".SI",
         "KS": ".KS", "TT": ".TW", "IT": ".TA"}


def foreign_ticker(sid: str, name: str | None) -> str | None:
    """Foreign securities appear in Israeli statements under an 8-digit bank code (6xxxxxxx / 7xxxxxxx) with the
    ticker somewhere in the name: "(Spdr Msci All Country World Ucits ETF) ACWD LN", "(Meta Platforms Inc) META",
    "AAPL", "MSFT US". A ticker with no exchange code is a US listing."""
    if not re.fullmatch(r"[67]\d{7}", sid or "") or not name:
        return None
    n = re.sub(r"\s+", " ", str(name).strip())
    m = re.search(r"\b([A-Z0-9]{1,8}(?:[./][A-Z])?) (" + "|".join(_EXCH) + r")$", n) or \
        re.search(r"\b([A-Z0-9]{1,8}(?:[./][A-Z])?) (" + "|".join(_EXCH) + r")\b", n)
    if m:
        return m.group(1).replace("/", "-") + _EXCH[m.group(2)]
    m = re.search(r"\)\s*([A-Z][A-Z0-9]{0,5}(?:[./][A-Z])?)$", n)  # "(Company name) TICKER"
    if m:
        return m.group(1).replace("/", "-")
    if re.fullmatch(r"[A-Z][A-Z.]{0,6}", n):
        return n
    return None


_SYM_CACHE: dict[str, str | None] = {}
# Bloomberg short names in statements ("Ishr Stoxx Eur 600 Banks De") -> words Yahoo's search understands
_ABBR = {"ishr": "iShares", "ishs": "iShares", "eur": "Europe", "em": "Emerging Markets", "glb": "Global", "gbl": "Global",
         "wld": "World", "intl": "International", "corp": "Corporate", "govt": "Government", "div": "Dividend"}
_NOISE = {"de", "dist", "acc", "etf", "ucits", "plc", "ltd", "inc", "sa", "ag", "nv", "adr", "unsp", "sp", "-a", "-d"}


def _name_queries(raw: str) -> list[str]:
    words = [w for w in re.split(r"\s+", raw.strip()) if w]
    full = [_ABBR.get(w.lower(), w) for w in words if w.lower() not in _NOISE]
    qs = [raw, " ".join(full)] + [" ".join(full[i:]) for i in (1, 2) if len(full) - i >= 2]
    return [q for i, q in enumerate(qs) if q and q not in qs[:i]]


def yahoo_symbol(tk: str, name: str | None) -> str | None:
    """Check a non-US ticker exists on Yahoo; Bloomberg-only codes (e.g. SX7PEX GR) are looked up by the
    company/fund name in the statement instead. None when neither works."""
    if tk in _SYM_CACHE:
        return _SYM_CACHE[tk]
    out = None
    try:
        import yfinance as yf
        if not yf.Ticker(tk).history(period="5d").empty:
            out = tk
        else:
            m = re.search(r"\(([^()]*[A-Za-z][^()]*)\)", name or "")
            suffix = tk[tk.index("."):] if "." in tk else ""
            for q in _name_queries(m.group(1) if m else ""):
                quotes = [x for x in (yf.Search(q, max_results=6).quotes or []) if x.get("symbol")]
                pick = next((x for x in quotes if suffix and x["symbol"].endswith(suffix)), quotes[0] if quotes else None)
                if pick:
                    out = pick["symbol"]
                    break
    except Exception:
        out = None
    _SYM_CACHE[tk] = out
    return out


def parse_number(v: Any) -> tuple[float | None, bool]:
    """Returns (value, had_percent_sign)."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None, False
    if isinstance(v, (int, float)):
        return float(v), False
    s = str(v).strip()
    if not s:
        return None, False
    pct = "%" in s
    s = s.replace("%", "").replace(",", "").replace("₪", "").replace("$", "").strip()
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s), pct
    except ValueError:
        return None, pct


def normalize_weights(values: list[Any]) -> list[float | None]:
    """'15%', '15', 15, 0.15 -> 15.0. A column is treated as fractions if every value <= 1 and they sum <= ~1."""
    parsed = [parse_number(v) for v in values]
    nums = [p[0] for p in parsed if p[0] is not None]
    any_pct = any(p[1] for p in parsed)
    as_fraction = bool(nums) and not any_pct and all(abs(n) <= 1 for n in nums) and sum(nums) <= 1.0001
    out = []
    for val, _ in parsed:
        if val is None:
            out.append(None)
        else:
            out.append(round(val * 100 if as_fraction else val, 6))
    return out


def parse_portfolio(filename: str, content: bytes) -> tuple[list[dict], list[str]]:
    """Parse an uploaded file into holdings: [{id, name, weight, target_weight, quantity}], warnings."""
    return parse_frame(_read_raw(filename, content))


def parse_frame(raw: pd.DataFrame) -> tuple[list[dict], list[str]]:
    """Parse one sheet (header row anywhere in the first 20 rows) into holdings + warnings."""
    raw = raw.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)
    if raw.empty:
        raise ValueError("הקובץ ריק")

    # Header row may not be the first row (bank exports often have title and summary rows):
    # take the row that matches the most columns, preferring exact header names over partial matches.
    header_row, cols, best = None, {}, -1.0
    for i in range(min(20, len(raw))):
        cells = list(raw.iloc[i].values)
        m = _match_columns(cells)
        if "id" not in m:
            continue
        exact = sum(1 for idx in m.values() if _ALIAS_LOOKUP.get(_norm_header(cells[idx])))
        has_amount = any(k in m for k in ("weight", "quantity", "target_weight", "value"))
        score = len(m) + 0.5 * exact + (2 if has_amount else 0)
        if score > best:
            header_row, cols, best = i, m, score
    if header_row is None:
        raise ValueError(
            "לא נמצאה עמודת מזהה נייר. כותרות נתמכות: מספר נייר / קוד נייר / ticker / symbol"
        )

    body = raw.iloc[header_row + 1:].reset_index(drop=True)
    warnings: list[str] = []

    def col(field):
        return list(body.iloc[:, cols[field]].values) if field in cols else [None] * len(body)

    ids = [normalize_identifier(v) if v is not None and not (isinstance(v, float) and pd.isna(v)) else "" for v in col("id")]
    names = col("name")
    weights = normalize_weights(col("weight")) if "weight" in cols else [None] * len(body)
    values = [parse_number(v)[0] for v in col("value")]
    line = [i for i, x in enumerate(ids) if x and x not in ("NAN", "NONE") and not x.startswith(("סה", "TOTAL"))]
    value_complete = "value" in cols and line and all(values[i] for i in line)
    if ("weight" not in cols and "value" in cols) or value_complete:
        # statement exports list market value (₪) per line -> weights from value
        # (also when a % column exists: statements round it, the ₪ values are exact)
        valid = [values[i] for i in line if values[i]]
        tot = sum(valid)
        if tot > 0:
            weights = [round(v / tot * 100, 6) if v else None for v in values]
    targets = normalize_weights(col("target_weight")) if "target_weight" in cols else [None] * len(body)
    qtys = [parse_number(v)[0] for v in col("quantity")]
    fees = [parse_number(v)[0] for v in col("fee")]

    holdings: list[dict] = []
    for i, ident in enumerate(ids):
        if not ident or ident in ("NAN", "NONE") or ident.startswith(("סה", "TOTAL")):
            continue
        name = names[i]
        tk = foreign_ticker(ident, None if name is None or (isinstance(name, float) and pd.isna(name)) else str(name))
        if tk and "." in tk:  # non-US listing: make sure Yahoo knows the symbol, else search by name
            tk = yahoo_symbol(tk, str(name)) or tk
        if tk:
            warnings.append(f"קוד זר {ident} זוהה לפי השם כ-{tk}")
            ident = tk
        holdings.append({
            "id": ident,
            "name": None if name is None or (isinstance(name, float) and pd.isna(name)) else str(name).strip(),
            "weight": weights[i],
            "target_weight": targets[i],
            "quantity": qtys[i],
            "fee": fees[i],
            "value": values[i],
        })

    if not holdings:
        raise ValueError("לא נמצאו שורות נכסים בקובץ")
    if "weight" not in cols and "quantity" not in cols and "value" not in cols:
        warnings.append("לא נמצאה עמודת משקל או כמות – הוקצה משקל שווה לכל הנכסים")
    return merge_duplicates(holdings, warnings), warnings


def merge_duplicates(holdings: list[dict], warnings: list[str]) -> list[dict]:
    merged: dict[str, dict] = {}
    for h in holdings:
        if h["id"] in merged:
            m = merged[h["id"]]
            for k in ("weight", "target_weight", "quantity", "value"):
                if h.get(k) is not None:
                    m[k] = (m.get(k) or 0) + h[k]
            warnings.append(f"הנייר {h['id']} הופיע יותר מפעם אחת – השורות אוחדו")
        else:
            merged[h["id"]] = dict(h)
    return list(merged.values())


SAMPLE_CSV = """מספר נייר,שם נייר,משקל,משקל יעד
604611,לאומי,12%,10%
662577,הפועלים,8%,10%
5113428,קסם קרן כספית,10%,10%
1183441,אינבסקו S&P 500,15%,15%
1231687,אבו מגורים אג"ח א,5%,5%
AAPL,Apple,15%,15%
NVDA,NVIDIA,12%,15%
MSFT,Microsoft,10%,10%
SPY,SPDR S&P 500 ETF,8%,10%
1101864,נייר לא מזוהה,5%,0%
"""
