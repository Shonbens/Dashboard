"""Israel-only template ("חדש ישראל מ.ק 30") test case - same idea as build.py, its own row layout."""
import json, os, random, sys
from pathlib import Path
import openpyxl
from openpyxl.utils import get_column_letter as L

SRC, OUT = Path(sys.argv[1]), Path(__file__).parent
SEED, EQ = int(sys.argv[2]), float(sys.argv[3])
rnd = random.Random(SEED)
wb = openpyxl.load_workbook(SRC)
for n in wb.sheetnames:
    if n != "חדש ישראל מ.ק 30":
        del wb[n]
ws = wb["חדש ישראל מ.ק 30"]
for row in ws.iter_rows():
    for c in row:
        if isinstance(c.value, str) and ("_xll." in c.value):
            c.value = None
ws["F3"], ws["T2"], ws["T4"] = EQ, 0.0065, 0.028
IL_SECTORS = ["טכנולוגיה", "בנקים", "שרותים פיננסים", "ביטוח", "נדלן ובנייה", "ביומד", "מסחר ושרותים", "תעשייה",
              "אנרגיה וחיפושי נפט וגז", "השקעה ואחזקות"]

def split(n, total):
    xs = [rnd.uniform(0.5, 1.5) for _ in range(n)]
    return [round(total * x / sum(xs), 4) for x in xs]

rows, data, fund_lt = [], {}, {}
il_slots = list(range(6, 22))
eq_funds = [83, 85, 86]   # W34=F83 (fund_eq), X34=F85 (יתר), Y34=F86 (MID)
w = split(len(il_slots) + len(eq_funds), 100); k = 0
for r in il_slots:
    sec = {6: 'ת"א90', 7: 'ת"א 125', 16: "ביטחונית"}.get(r) or rnd.choice(IL_SECTORS)
    rows.append({"section": "eq_il", "id": f"IL{r}", "weight": w[k], "sector": sec, "xl_row": r}); k += 1
for r in eq_funds:
    rid = f"FU{r}"
    rows.append({"section": "funds", "id": rid, "weight": w[k], "sleeve": "equity", "xl_row": r,
                 **({85: {"exposure": "יתר"}, 86: {"exposure": "MID"}}.get(r, {}))}); k += 1
    fund_lt[rid] = {"eq_il": 1.0}
bond_slots = [("gov_cpi", 25), ("gov_cpi", 26), ("gov_nominal", 31)] + [("corp_cpi", r) for r in range(39, 47)] + [("corp_nominal", r) for r in range(54, 60)]
bond_funds = list(range(69, 78))
bw = split(len(bond_slots) + len(bond_funds), 93); k = 0
for sec, r in bond_slots:
    row = {"section": sec, "id": f"B{r}", "weight": bw[k], "xl_row": r}
    if sec.startswith("corp"):
        row["bucket"] = rnd.randint(1, 4)
    rows.append(row); k += 1
KEYS = ["gov_cpi", "gov_usd", "gov_nominal", "gov_float", "corp_usd", "corp_cpi", "corp_nominal", "corp_float", "corp_hedged", "cash"]
for r in bond_funds:
    rid = f"FU{r}"
    rows.append({"section": "funds", "id": rid, "weight": bw[k], "sleeve": "bond", "bucket": rnd.randint(1, 4), "xl_row": r}); k += 1
    xs = [rnd.random() for _ in KEYS]
    fund_lt[rid] = {kk: round(x / sum(xs), 4) for kk, x in zip(KEYS, xs)}
for row in rows:
    d = {"name": row["id"]}
    if row["section"] != "eq_il":
        d["yield"], d["duration"] = round(rnd.uniform(1.5, 5.5), 3), round(rnd.uniform(0.5, 8), 2)
    if row["section"] == "funds":
        d.update(fee=round(rnd.uniform(0.3, 2.3), 3), lookthrough=fund_lt[row["id"]], kind="fund", us_share=0)
    data[row["id"]] = d

def put(r, col, v): ws[f"{col}{r}"] = v
for row in rows:
    r, sec, d = row["xl_row"], row["section"], data[row["id"]]
    put(r, "C", row["id"]); put(r, "D", row["id"]); put(r, "E", row["weight"] / 100)
    eq_sleeve = sec == "eq_il" or row.get("sleeve") == "equity"
    put(r, "F", f"=E{r}*$F$3" if eq_sleeve else f"=E{r}*(1-$F$3)")
    if sec == "eq_il": put(r, "B", row["sector"])
    elif "bucket" in row: put(r, "B", row["bucket"])
    if "yield" in d:
        put(r, "G", d["yield"] / 100); put(r, "M", d["duration"])
        if sec in ("gov_cpi", "corp_cpi"): put(r, "K", "=$T$4")
        put(r, "L", f"=(K{r}+G{r})*F{r}/$U$7"); put(r, "N", f"=M{r}*F{r}/(100%-$F$24)")
    put(r, "O", d["fee"] / 100 if sec == "funds" else "=$T$3"); put(r, "P", f"=O{r}*F{r}")
LT = {kk: L(34 + i) for i, kk in enumerate(["eq_il"] + KEYS)}
for row in rows:
    if row["section"] == "funds":
        for kk, col in LT.items(): put(row["xl_row"], col, data[row["id"]]["lookthrough"].get(kk, 0))
CONTRIB = {"eq_il": 22, "gov_cpi": 27, "gov_usd": 29, "gov_nominal": 32, "gov_float": 34, "corp_usd": 37, "corp_cpi": 52,
           "corp_nominal": 62, "corp_float": 64, "corp_hedged": 66}
for kk, r in CONTRIB.items():
    put(r, "F", f"=SUMPRODUCT($F$69:$F$88,{LT[kk]}69:{LT[kk]}88)")
# repaired cells next to the originals
ws["AK67"] = "=SUM(F66)"
ws["AK68"] = "=SUM($F$38,$F$53,$F$63,$F$65,$AK$67)"
ws["AK11"] = "=SUM($F$33,$F$35,$F$63,$F$65,$AK$67)"
ws["AK12"] = "=SUM($F$30,$F$38)"
xl = OUT / f"il{SEED}.xlsx"; wb.save(xl)
site_rows = [{kk: v for kk, v in r.items() if kk != "xl_row"} for r in rows]
cfg = {"template": "israel", "equity": EQ * 100, "rows": site_rows,
       "settings": {"contract_fee": 0.65, "vat": 17, "inflation": 2.8, "fund_cap": 100, "rev_share_bond": 78, "rev_share_equity": 65}}
(OUT / f"il{SEED}.json").write_text(json.dumps({"config": cfg, "data": data, "equity": EQ * 100}, ensure_ascii=False))
