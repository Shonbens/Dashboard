"""Excel import / export for base models. Convention: one worksheet per model, sheet name = model name."""
from __future__ import annotations

import io
import re

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from ingestion import parse_frame

INVALID_SHEET_CHARS = re.compile(r"[\[\]\*\?:/\\]")


def name_key(name: str) -> str:
    """'80/20', '80-20', '80\\20', ' 80 / 20 ' all map to the same key."""
    return re.sub(r"\s+", "", re.sub(r"[/\\\-]", "/", (name or "").strip())).lower()


def sheet_title(name: str, used: set[str]) -> str:
    base = INVALID_SHEET_CHARS.sub("-", name).strip()[:31] or "Model"
    title, i = base, 2
    while title.lower() in used:
        suffix = f" ({i})"
        title = base[: 31 - len(suffix)] + suffix
        i += 1
    used.add(title.lower())
    return title


def read_workbook(filename: str, content: bytes) -> list[dict]:
    """Returns [{sheet, holdings, warnings, error}] for every sheet in the workbook (or the single CSV)."""
    fname = (filename or "").lower()
    if fname.endswith(".csv"):
        from ingestion import _read_raw

        sheets = {re.sub(r"\.csv$", "", filename, flags=re.I): _read_raw(filename, content)}
    else:
        sheets = pd.read_excel(io.BytesIO(content), sheet_name=None, header=None, dtype=object)
    out = []
    for sheet, df in sheets.items():
        entry = {"sheet": str(sheet).strip(), "holdings": [], "warnings": [], "error": None}
        try:
            holdings, warnings = parse_frame(df)
            if all(h.get("weight") is None for h in holdings):
                raise ValueError("לא נמצאה עמודת משקל")
            entry["holdings"] = [
                {"id": h["id"], "name": h.get("name"), "weight": h.get("weight") or 0.0, "fee": h.get("fee")}
                for h in holdings
            ]
            entry["warnings"] = warnings
        except Exception as e:  # a bad sheet must not break the whole import
            entry["error"] = str(e)
        out.append(entry)
    return out


HEADERS = ["מספר נייר", "שם נייר", "סוג נכס", "משקל", "דמי ניהול"]


def export_workbook(models: list[dict], details: dict[str, dict] | None = None) -> bytes:
    """models: store dicts. details: optional {security id: {name, asset_class}} from pricing."""
    details = details or {}
    wb = Workbook()
    wb.remove(wb.active)
    used: set[str] = set()
    head_fill = PatternFill("solid", fgColor="1A3BAF")
    thin = Side(style="thin", color="D5DBE5")
    for m in models:
        ws = wb.create_sheet(sheet_title(m["name"], used))
        ws.sheet_view.rightToLeft = True
        ws["A1"] = f"מודל {m['name']}"
        ws["A1"].font = Font(bold=True, size=14, color="0F1F54")
        meta = f"גרסה {m.get('version', '')} · סטטוס: {m.get('status', '')}"
        if m.get("description"):
            meta += f" · {m['description']}"
        ws["A2"] = meta
        ws["A2"].font = Font(size=10, color="64748B")
        hr = 4
        for c, h in enumerate(HEADERS, 1):
            cell = ws.cell(row=hr, column=c, value=h)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = head_fill
            cell.alignment = Alignment(horizontal="center")
        r = hr
        for h in sorted(m["holdings"], key=lambda x: -(x.get("weight") or 0)):
            r += 1
            d = details.get(str(h["id"]), {})
            hid = int(h["id"]) if str(h["id"]).isdigit() else h["id"]
            vals = [hid, d.get("name") or h.get("name") or "", d.get("asset_class") or "", (h.get("weight") or 0) / 100, h.get("fee")]
            for c, v in enumerate(vals, 1):
                cell = ws.cell(row=r, column=c, value=v)
                cell.border = Border(bottom=thin)
            ws.cell(row=r, column=4).number_format = "0.00%"
            ws.cell(row=r, column=5).number_format = '0.00"%"'
        r += 1
        ws.cell(row=r, column=1, value="סה״כ").font = Font(bold=True)
        ws.cell(row=r, column=4, value=f"=SUM(D{hr + 1}:D{r - 1})").number_format = "0.00%"
        ws.cell(row=r, column=4).font = Font(bold=True)
        for col, width in zip("ABCDE", (14, 48, 16, 10, 12)):
            ws.column_dimensions[col].width = width
        ws.freeze_panes = ws.cell(row=hr + 1, column=1)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# Demo house models built from IBI ETFs / funds listed on TASE (equity/bond split in the name)
_EQ = {"1148808": "ת״א 125", "1148162": "S&P 500", "1149772": "MSCI ACWI", "1200450": "Nasdaq 100"}
_BD = {"5111620": "ממשל שקלי קצר", "1148006": "תל בונד 60 צמודות", "1147966": "iBoxx US IG", "5103510": "כספית שקלית"}


def _mix(eq_total: float) -> list[dict]:
    eq_split = {"1148808": 0.30, "1148162": 0.40, "1149772": 0.20, "1200450": 0.10}
    bd_split = {"5111620": 0.40, "1148006": 0.35, "1147966": 0.15, "5103510": 0.10}
    if eq_total < 100 and eq_total >= 80:  # no cash sleeve in growth models
        bd_split = {"5111620": 0.45, "1148006": 0.40, "1147966": 0.15}
    rows = [{"id": k, "name": _EQ[k], "weight": round(eq_total * v, 2)} for k, v in eq_split.items() if eq_total]
    bonds = 100 - eq_total
    rows += [{"id": k, "name": _BD[k], "weight": round(bonds * v, 2)} for k, v in bd_split.items() if bonds]
    return rows


DEMO_MODELS = [
    {"name": "100", "description": "מנייתי מלא – חשיפה גלובלית ומקומית", "status": "approved", "holdings": _mix(100)},
    {"name": "80/20", "description": "צמיחה – 80% מניות, 20% אג״ח", "status": "approved", "holdings": _mix(80)},
    {"name": "60/40", "description": "מאוזן – 60% מניות, 40% אג״ח", "status": "approved", "holdings": _mix(60)},
    {"name": "40/60", "description": "סולידי-מאוזן – 40% מניות, 60% אג״ח", "status": "approved", "holdings": _mix(40)},
    {"name": "20/80", "description": "סולידי – 20% מניות, 80% אג״ח", "status": "draft", "holdings": _mix(20)},
]


# --------------------------------------------------------------------------- #
#  Demo allocation sheets (layout of the house Excel; weights are illustrative)
#  Each row: (section, security id, אחוז ראשי = weight inside its sleeve, extra row fields)
# --------------------------------------------------------------------------- #
EQUITY_SECTIONS = {"eq_il", "eq_foreign"}


def _alloc(template: str, equity: float, rows: list[tuple]) -> tuple[dict, list[dict]]:
    cfg_rows = [{"section": s, "id": i, "weight": w, **(x or {})} for s, i, w, x in rows]
    holdings: dict[str, float] = {}
    for r in cfg_rows:
        sleeve = "equity" if r["section"] in EQUITY_SECTIONS or r.get("sleeve") == "equity" else "bond"
        f = r["weight"] * (equity / 100 if sleeve == "equity" else 1 - equity / 100)
        holdings[r["id"]] = holdings.get(r["id"], 0) + f
    return ({"template": template, "equity": equity, "rows": cfg_rows},
            [{"id": k, "weight": round(v, 4), "fee": None} for k, v in holdings.items()])


_BONDS_COMMON = [
    ("gov_cpi", "5117379", 12, None), ("gov_cpi", "5135405", 4, None),
    ("gov_nominal", "5113444", 12, None), ("gov_nominal", "5129192", 3, None),
    ("corp_cpi", "2310498", 6, {"bucket": 1, "industry": "בנקים"}), ("corp_cpi", "1156611", 4, {"bucket": 2, "industry": "נדלן מניב בישראל"}),
    ("corp_cpi", "1194638", 1, {"bucket": 3, "industry": "נדלן מניב בישראל"}), ("corp_cpi", "1196799", 1, {"bucket": 1, "industry": "תשתיות ואנרגיה"}),
    ("corp_cpi", "7670284", 5, {"bucket": 3, "industry": "ביטוח"}), ("corp_cpi", "5118021", 5, {"bucket": 3}),
    ("corp_cpi", "1227032", 2, {"bucket": 3, "industry": "נדלן מניב בישראל"}),
    ("corp_nominal", "6620488", 4, {"bucket": 1, "industry": "בנקים"}), ("corp_nominal", "7480163", 5, {"bucket": 2, "industry": "בנקים"}),
    ("corp_nominal", "2300309", 1, {"bucket": 3, "industry": "מסחר ושרותים"}), ("corp_nominal", "7460421", 1, {"bucket": 2, "industry": "תעשייה"}),
    ("corp_nominal", "5127709", 7, {"bucket": 3}), ("corp_nominal", "1195346", 2, {"bucket": 4, "industry": "תעשייה"}),
]

DEMO_ALLOCATIONS = [
    {
        "name": "פרימיום מ.ק.20 – 50% מניות", "description": "הדגמה – תבנית ישראל + חו״ל (גיליון ״חדש מ.ק.20״)",
        **dict(zip(("config", "holdings"), _alloc("global", 50, [
            ("eq_il", "1148808", 12, {"sector": 'ת"א 125'}), ("eq_il", "604611", 4, None), ("eq_il", "662577", 4, None),
            ("eq_il", "1081124", 3, None), ("eq_il", "273011", 2, None), ("eq_il", "629014", 2, None), ("eq_il", "1119478", 2, None),
            ("eq_il", "230011", 2, None),
            ("eq_foreign", "1183441", 23, {"exposure": "S&P 500", "country": "ארה״ב"}),
            ("eq_foreign", "1200450", 10, {"exposure": "NASDAQ", "country": "ארה״ב"}),
            ("eq_foreign", "5137203", 6, {"exposure": "STOXX 600", "country": "אירופה"}),
            ("eq_foreign", "5128079", 4, {"exposure": "RUSSELL", "country": "ארה״ב"}),
            ("eq_foreign", "MSFT", 3, {"country": "ארה״ב"}), ("eq_foreign", "GOOGL", 3, {"country": "ארה״ב"}),
            ("eq_foreign", "V", 2, {"country": "ארה״ב"}),
            *_BONDS_COMMON,
            ("corp_usd", "5127667", 3, {"bucket": 2}),
            ("funds", "5100482", 13, {"sleeve": "equity"}), ("funds", "5102132", 5, {"sleeve": "equity"}),
            ("funds", "5117577", 5, {"sleeve": "bond"}), ("funds", "5119839", 4, {"sleeve": "bond"}),
            ("funds", "5128434", 3, {"sleeve": "bond"}), ("funds", "5111620", 8, {"sleeve": "bond"}),
        ]))),
    },
    {
        "name": "פרימיום ישראל מ.ק.30 – 30% מניות", "description": "הדגמה – תבנית ישראל בלבד (גיליון ״חדש ישראל מ.ק 30״)",
        **dict(zip(("config", "holdings"), _alloc("israel", 30, [
            ("eq_il", "1148808", 35, {"sector": 'ת"א 125'}), ("eq_il", "604611", 8, None), ("eq_il", "662577", 8, None),
            ("eq_il", "691212", 5, None), ("eq_il", "1081124", 6, None), ("eq_il", "273011", 5, None), ("eq_il", "629014", 5, None),
            ("eq_il", "1119478", 5, None), ("eq_il", "230011", 4, None), ("eq_il", "281014", 4, None),
            *_BONDS_COMMON,
            ("funds", "5102132", 10, {"sleeve": "equity"}), ("funds", "5100144", 5, {"sleeve": "equity", "exposure": "יתר"}),
            ("funds", "5117577", 5, {"sleeve": "bond"}), ("funds", "5128434", 4, {"sleeve": "bond"}),
            ("funds", "5111620", 10, {"sleeve": "bond"}),
        ]))),
    },
]
