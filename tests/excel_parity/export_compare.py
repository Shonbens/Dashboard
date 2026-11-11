"""Calculate the exported workbook (as is, and with B4 changed to the alternative equity share) and compare with the website."""
import json, sys
from pathlib import Path
import formulas, openpyxl

out = Path(sys.argv[1]); site = json.load(open(out / "site.json"))
wb = openpyxl.load_workbook(out / "export.xlsx")
ws = wb.active
labels = {ws.cell(r, 20).value: r for r in range(15, 60) if ws.cell(r, 20).value}
tot_rows = {ws.cell(r, 26).value: r for r in range(15, ws.max_row + 1) if ws.cell(r, 25).value == "סה״כ" and ws.cell(r, 26).value}
rb = labels["תחליף ממשלתי"]
ws["B4"] = site["alt"] / 100
wb.save(out / "export_alt.xlsx")

def calc(path):
    sol = formulas.ExcelModel().loads(str(path)).finish().calculate()
    v = {}
    for k, x in sol.items():
        ref = k.split("!")[-1].upper()
        if ":" in ref: continue
        try: v[ref] = x.value[0][0]
        except Exception: pass
    return v

KEYS = {"duration": ('סה"כ מח"מ בתיק', 1), "irr": ("תשואה פנימית של התיק", 100), "bonds": ('סה"כ אג"ח', 100), "cash": ('עו"ש התיק', 100),
        "equity": ('סה"כ מניות (כולל שיקוף קרנות)', 100), "gov": ('סה"כ ממשלתי', 100), "corp": ('סה"כ קונצרני', 100), "funds": ('סה"כ קרנות', 100),
        "linked": ('סה"כ צמוד', 100), "shekel": ('סה"כ שקלי', 100), "linkedShare": ("שיעור הצמוד מהצמוד + השקלי", 100),
        "shekelShare": ("שיעור השקלי מהצמוד + השקלי", 100), "fx": ('סה"כ מט"ח', 100), "us": ('סה"כ ארה"ב (כולל קרנות)', 100),
        "equityPosition": ("פוזיציה מנייתית", 100), "foreignEqShare": ('חשיפה מנייתית לחו"ל מסך המניות', 100),
        "ilEqShare": ("חשיפה מנייתית לארץ מסך המניות", 100), "fundFees": ("דמי ניהול של הקרנות בתיק", 100),
        "totalFees": ('סה"כ דמי ניהול בתיק', 100), "revenue": ('סה"כ הכנסות לבית', 100), "revenueExVat": ('הכנסות ללא מע"מ', 100)}
for tag, path, s in (("as exported", out / "export.xlsx", site["base"]), (f"equity changed in Excel to {site['alt']}%", out / "export_alt.xlsx", site["altres"])):
    v = calc(path); n = bad = 0
    def chk(lab, e, w):
        global n, bad
        n += 1
        e = None if isinstance(e, str) or e is None else float(e)
        if w is None and e in (None, 0.0): return
        if e is None or w is None or abs(e - w) > 1e-6 * max(1, abs(w)):
            bad += 1; print(f"   ✗ {lab}: excel {e} | site {w}")
    for k, (lab, sc) in KEYS.items():
        e = v.get(f"U{labels[lab]}")
        chk(k, None if isinstance(e, str) else (e * sc if e is not None else None), s["summary"][k])
    for i in range(4):
        e = v.get(f"U{rb + i}"); chk(f"bucket {i + 1}", e * 100 if isinstance(e, (int, float)) else e, s["rating"][i])
    for key, r in tot_rows.items():
        t = s["totals"].get(key)
        if not t: continue
        for c, sc, k in (("F", 100, "F"), ("L", 100, "L"), ("N", 1, "N"), ("P", 100, "P"), ("G", 100, "G"), ("M", 1, "M")):
            e = v.get(f"{c}{r}")
            if isinstance(e, (int, float)): chk(f"{key}.{k}", e * sc, t[k] if t[k] is not None else 0)
    print(f"{tag}: {n} checks · {n - bad} match · {bad} differ")
