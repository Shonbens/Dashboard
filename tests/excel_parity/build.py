"""
Build a test workbook from the house template ("חדש מ.ק.20"), fill a synthetic portfolio in the slots the
template expects, add the per-row formulas the hidden sheets use, and compute it with the `formulas` engine.
Also writes the same portfolio as a website config (case.json) so allocation.js can compute it.

Two formula sets are evaluated side by side:
  - "orig": the template's own summary formulas, as they are
  - "fixed": the same formulas with the template defects repaired (only where a cell is broken)
"""
import json, random, sys, shutil
from pathlib import Path
import openpyxl
from openpyxl.utils import get_column_letter as L

SRC = Path(sys.argv[1])
OUT = Path(__file__).parent
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 1
EQ = float(sys.argv[3]) if len(sys.argv) > 3 else 0.5
rnd = random.Random(SEED)

wb = openpyxl.load_workbook(SRC)
import os
IL = bool(os.environ.get("ILT"))
SHEET = "חדש ישראל מ.ק 30" if IL else "חדש מ.ק.20"
for name in wb.sheetnames:
    if name != SHEET:
        del wb[name]
ws = wb[SHEET]

# clear add-in formulas (ACE/ACEX) - they cannot calculate outside the house Excel
for row in ws.iter_rows():
    for c in row:
        if isinstance(c.value, str) and "_xll." in c.value:
            c.value = None

ws["F3"] = EQ
T2, INFL = 0.0065, 0.028
ws["T2"], ws["T4"] = T2, INFL

IL_SECTORS = ["טכנולוגיה", "בנקים", "שרותים פיננסים", "ביטוח", "נדלן ובנייה", "ביומד", "מסחר ושרותים", "תעשייה",
              "אנרגיה וחיפושי נפט וגז", "השקעה ואחזקות"]
GICS = ["Information Technology", "Health Care", "Financials", "Consumer Discretionary", "Industrials"]


def split(n, total):
    xs = [rnd.uniform(0.5, 1.5) for _ in range(n)]
    s = sum(xs)
    return [round(total * x / s, 4) for x in xs]


rows = []  # website rows: dict(section, id, weight, sector/exposure/country/bucket/industry, hedged, sleeve, name, xl_row)
data = {}  # website per-id data

# ---- equity sleeve: direct IL 6-17, foreign 20-28, equity funds 93/95 (rows 92/94 deliberately 0 - hard-coded splits)
il_slots = list(range(6, 18))
f_slots = list(range(20, 29))
eq_fund_rows = [93, 95, 96]
weights = split(len(il_slots) + len(f_slots) + len(eq_fund_rows), 100)
k = 0
for r in il_slots:
    sec = {9: 'ת"א90', 11: 'ת"א 125', 13: "ביטחונית"}.get(r) or rnd.choice(IL_SECTORS)
    rows.append({"section": "eq_il", "id": f"IL{r}", "weight": weights[k], "sector": sec, "xl_row": r}); k += 1
FOREIGN = {20: ("S&P 500", None), 21: ("RUSSELL", None), 22: ("S&P 500", None), 23: ("NASDAQ", None), 24: ("Information Technology", "ארה״ב"),
           25: ("Health Care", "ארה״ב"), 26: ("Financials", "ארה״ב"), 27: ("Industrials", "ארה״ב"), 28: ("שאר העולם", None)}
for r in f_slots:
    exp, country = FOREIGN[r]
    row = {"section": "eq_foreign", "id": f"FO{r}", "weight": weights[k], "exposure": exp, "xl_row": r, "hedged": r in (21, 22, 24)}
    if r == 24:
        row["site_exposure"] = "שבבים"   # the template reads row 24 as the direct semiconductor holding
    if country:
        row["country"] = country
    rows.append(row); k += 1
fund_lt = {}
for r in eq_fund_rows:
    rid = f"FU{r}"
    rows.append({"section": "funds", "id": rid, "weight": weights[k], "sleeve": "equity", "xl_row": r,
                 **({"exposure": "יתר"} if r == 95 else {})}); k += 1
    # 93/95: Israeli equity funds (the template reads their whole weight into the IL sector table)
    # 96: 90% IL equity + 10% cash -> shows the look-through without touching the foreign table
    import os
    fund_lt[rid] = {"eq_il": 1.0} if r != 96 else ({"cash": 1.0} if os.environ.get("NO96") else {"eq_il": 0.9, "cash": 0.1})

# ---- bond sleeve (sum of E < 100 -> the rest is cash)
bond_slots = [("gov_cpi", 32), ("gov_cpi", 33), ("gov_usd", 36), ("gov_nominal", 39), ("corp_usd", 45)] + \
             [("corp_cpi", r) for r in range(48, 56)] + [("corp_nominal", r) for r in range(62, 69)]
bond_fund_rows = list(range(79, 88))
bw = split(len(bond_slots) + len(bond_fund_rows), 92)  # 8% of the bond sleeve stays in cash
k = 0
for sec, r in bond_slots:
    row = {"section": sec, "id": f"B{r}", "weight": bw[k], "xl_row": r}
    if sec.startswith("corp"):
        row["bucket"] = rnd.randint(1, 4)
    rows.append(row); k += 1
BOND_LT_KEYS = ["gov_cpi", "gov_usd", "gov_nominal", "gov_float", "corp_usd", "corp_cpi", "corp_nominal", "corp_float", "corp_hedged", "cash"]
for r in bond_fund_rows:
    rid = f"FU{r}"
    rows.append({"section": "funds", "id": rid, "weight": bw[k], "sleeve": "bond", "bucket": rnd.randint(1, 4), "xl_row": r}); k += 1
    xs = [rnd.random() for _ in BOND_LT_KEYS]
    s = sum(xs)
    fund_lt[rid] = {key: round(x / s, 4) for key, x in zip(BOND_LT_KEYS, xs)}

# ---- per-security inputs
for row in rows:
    d = {"name": row["id"]}
    sec = row["section"]
    if sec not in ("eq_il", "eq_foreign"):
        d["yield"] = round(rnd.uniform(1.5, 5.5), 3)       # %
        d["duration"] = round(rnd.uniform(0.5, 8), 2)
    if sec == "funds":
        d["fee"] = round(rnd.uniform(0.3, 2.3), 3)          # %
        d["lookthrough"] = fund_lt[row["id"]]
        d["us_share"] = round(rnd.uniform(0, 40), 2) if row["sleeve"] == "bond" else 0
        d["kind"] = "fund"
    data[row["id"]] = d

# ---- write the sheet
def put(r, col, v):
    ws[f"{col}{r}"] = v

for row in rows:
    r, sec = row["xl_row"], row["section"]
    d = data[row["id"]]
    put(r, "C", row["id"])
    put(r, "D", row["id"])
    put(r, "E", row["weight"] / 100)
    sleeve = "equity" if sec in ("eq_il", "eq_foreign") or row.get("sleeve") == "equity" else "bond"
    put(r, "F", f"=E{r}*$F$3" if sleeve == "equity" else f"=E{r}*(1-$F$3)")
    if sec == "eq_il":
        put(r, "B", row["sector"])
    elif sec == "eq_foreign":
        put(r, "B", row["exposure"])
    elif "bucket" in row:
        put(r, "B", row["bucket"])
    if "yield" in d:
        put(r, "G", d["yield"] / 100)
        put(r, "M", d["duration"])
        if sec in ("gov_cpi", "corp_cpi"):
            put(r, "K", "=$T$4")
        put(r, "L", f"=(K{r}+G{r})*F{r}/$U$7")
        put(r, "N", f"=M{r}*F{r}/(100%-$F$31)")
    put(r, "O", d["fee"] / 100 if sec == "funds" else "=$T$3")
    put(r, "P", f"=O{r}*F{r}")

# fund look-through helper columns AH.. on the fund rows (replaces the deleted lookup sheet)
LT_COL = {key: L(34 + i) for i, key in enumerate(["eq_il", "eq_foreign"] + BOND_LT_KEYS)}
for row in rows:
    if row["section"] == "funds":
        for key, col in LT_COL.items():
            put(row["xl_row"], col, data[row["id"]]["lookthrough"].get(key, 0))
        put(row["xl_row"], "AF", data[row["id"]]["us_share"])  # US % (VLOOKUP col 4 in the template)
CONTRIB_ROW = {"eq_il": 18, "eq_foreign": 29, "gov_cpi": 34, "gov_usd": 37, "gov_nominal": 40, "gov_float": 42, "corp_usd": 46,
               "corp_cpi": 60, "corp_nominal": 72, "corp_float": 74, "corp_hedged": 76}
for key, r in CONTRIB_ROW.items():
    put(r, "F", f"=SUMPRODUCT($F$79:$F$98,{LT_COL[key]}79:{LT_COL[key]}98)")

# ---- repaired copies of broken template cells, in spare columns (originals stay where they are)
fixes = {
    "AJ38": "=SUM(F36:F37)",            # F38 = SUM(F37) skips the direct row 36
    "AJ43": "=SUM(F42)",                # F43 has no formula (E only)
    "AJ77": "=SUM(F76)",                # F77 has no formula; E76 points at a fund row
}
for cell, f in fixes.items():
    ws[cell] = f
# summary rows that depend on the broken totals: rebuild them from the repaired cells
ws["AK44"] = "=SUM($F$35,$AJ$38,$F$41,$AJ$43)"
ws["AK78"] = "=SUM($F$47,$F$61,$F$73,$F$75,$AJ$77)"
ws["AK31"] = "=F31"
ws["AK8"] = "=U8"
ws["AK7"] = "=100%-$F$31-$U$8"
ws["AK11"] = "=SUM($F$41,$AJ$43,$F$73,$F$75,$AJ$77)"
ws["AK10"] = "=SUM($F$35,$F$61)"
ws["AK12"] = "=SUM($F$30,$AJ$38,$F$47)-F22-F24-F21"
ws["AK13"] = "=SUMPRODUCT($F$79:$F$98,$AF$79:$AF$98)/100"   # template: E (sleeve %) instead of F, and skips row 91
ws["AL13"] = "=SUMPRODUCT($E$79:$E$90,$AF$79:$AF$90)/100+SUMPRODUCT($E$92:$E$98,$AF$92:$AF$98)/100"  # the template's own logic
ws["AK16"] = "=$F$30/$F$31"          # template uses E30/E31 (direct only, sleeve %)
ws["AK9"] = "=AK78"
for i, w in enumerate((1, 2, 3, 4)):
    ws[f"AK{23 + i}"] = f"=SUMIF($B$32:$B$98,{w},$F$32:$F$98)"   # template SUMIF ranges are shifted 0-2 rows
ws["AK69"] = "=SUMIF($A$48:$A$72,T69,$F$48:$F$72)"
OUT.mkdir(exist_ok=True)
xl = OUT / f"case{SEED}.xlsx"
wb.save(xl)

# ---- website config
site_rows = []
for row in rows:
    x = {k: v for k, v in row.items() if k not in ("xl_row", "site_exposure")}
    if "site_exposure" in row:
        x["exposure"] = row["site_exposure"]
    site_rows.append(x)
config = {"template": "global", "equity": EQ * 100, "rows": site_rows,
          "settings": {"contract_fee": T2 * 100, "vat": 17, "inflation": INFL * 100, "fund_cap": 100,
                       "rev_share_bond": 78, "rev_share_equity": 65}}
(OUT / f"case{SEED}.json").write_text(json.dumps({"config": config, "data": data, "equity": EQ * 100}, ensure_ascii=False))
print(xl)
