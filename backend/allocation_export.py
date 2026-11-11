"""
Allocation sheet -> Excel workbook with live formulas.

The website sends only inputs (weights, market data, classifications, fund look-through). Every calculated cell is
written as an Excel formula that mirrors frontend/src/lib/allocation.js, so a manager can change the equity share,
a weight or a yield in Excel and the sheet recalculates exactly like the website. Inputs are shaded yellow.

Layout (RTL):  settings B4:B11 · holdings table A:R from row 14 · summary T:X beside it ·
               helper columns Y:AO (row type, section, sleeve, hedge flag, US %, fund look-through) grouped and collapsed.
"""
from __future__ import annotations

import io
import time

from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

SECTIONS = [  # same order / grouping as allocation.js
    ("eq_il", "מניות בארץ", "equity"), ("eq_foreign", "מניות בחו״ל", "equity"),
    ("gov_cpi", "ממשלתי צמוד", "gov"), ("gov_usd", "ממשלתי חו״ל דולר", "gov"), ("gov_nominal", "ממשלתי שקלי", "gov"),
    ("gov_float", "ממשלתי משתנה", "gov"),
    ("corp_usd", "קונצרני צמוד דולר", "corp"), ("corp_cpi", "קונצרני צמוד", "corp"), ("corp_nominal", "קונצרני שקלי", "corp"),
    ("corp_float", "קונצרני ריבית משתנה", "corp"), ("corp_hedged", "קונצרני חו״ל מנוטרל מטבע", "corp"),
    ("funds", "קרנות", "funds"),
]
GROUP_TOTAL = {"equity": "סה״כ מניות", "gov": "סה״כ ממשלתי", "corp": "סה״כ קונצרני"}
CPI = {"gov_cpi", "corp_cpi"}
LT_KEYS = ["eq_il", "eq_foreign", "gov_cpi", "gov_usd", "gov_nominal", "gov_float", "corp_usd", "corp_cpi", "corp_nominal",
           "corp_float", "corp_hedged", "cash"]
BUCKETS = [(1, "תחליף ממשלתי"), (2, "חזק"), (3, "בינוני"), (4, "סיכון גבוה")]

HEAD = ["מספר נייר", "שם נייר", "שיוך", "קבוצת סיכון", "אחוז ראשי", "אחוז יחסי", "תשואה ברוטו", "מתחילת חודש", "מתחילת שנה",
        "מרווח", "אינפלציה גלומה", "תשואה פנימית", "מח״מ", "מח״מ בתיק", "דמי ניהול", "דמי ניהול בתיק", "מעלות", "מידרוג"]
HELP = ["סוג שורה", "סעיף", "רכיב", "מנוטרל מט״ח", "ארה״ב %"] + [f"שיקוף: {k}" for k in LT_KEYS]
HELP0 = 25  # column Y

NAVY, CYAN = "161932", "00ADDC"
F_HEAD = PatternFill("solid", fgColor=NAVY)
F_INPUT = PatternFill("solid", fgColor="FFF7D6")
F_SEC = PatternFill("solid", fgColor="E6F6FB")
F_TOT = PatternFill("solid", fgColor="EEF0F4")
F_GTOT = PatternFill("solid", fgColor="DDE1E9")
PCT, PCT3, NUM2 = "0.00%", "0.000%", "0.00"
THIN = Side(style="thin", color="D5D9E2")


def col(i: int) -> str:
    return get_column_letter(i)


def build_allocation_xlsx(p: dict) -> bytes:
    rows_in = p["rows"]
    template = p.get("template") or "global"
    st = p.get("settings") or {}
    secs = [s for s in SECTIONS if not (template == "israel" and s[0] == "eq_foreign")]

    wb = Workbook()
    ws = wb.active
    ws.title = "גיליון הקצאה"
    ws.sheet_view.rightToLeft = True

    # ------------------------------------------------------------------ settings
    ws["A1"] = p.get("name") or "גיליון הקצאה"
    ws["A1"].font = Font(bold=True, size=15, color=NAVY)
    ws["A2"] = (f"יוצא מהאתר {time.strftime('%d/%m/%Y %H:%M')} · תאים צהובים = נתוני קלט, כל השאר נוסחאות "
                "(אותן נוסחאות כמו באתר) · שינוי אחוז מנייתי / משקל / תשואה מחשב מחדש את כל הגיליון")
    ws["A2"].font = Font(italic=True, size=9, color="687288")
    settings = [
        ("אחוז מנייתי", (p.get("equity") or 0) / 100, PCT),
        ("דמי ניהול חוזה", (st.get("contract_fee") or 0) / 100, PCT3),
        ("מע״מ", (st.get("vat") or 0) / 100, PCT),
        ("דמי ניהול כולל מע״מ", "=B5*(1+B6)", PCT3),
        ("אינפלציה גלומה", (st.get("inflation") or 0) / 100, PCT),
        ("חלק הבית בדמי קרנות אג״ח", (st.get("rev_share_bond") or 0) / 100, PCT),
        ("חלק הבית בדמי קרנות מניות", (st.get("rev_share_equity") or 0) / 100, PCT),
        ("מגבלת קרנות", (st.get("fund_cap") or 0) / 100, PCT),
    ]
    for i, (lab, v, fmt) in enumerate(settings):
        r = 4 + i
        ws.cell(r, 1, lab).font = Font(bold=True, size=10)
        c = ws.cell(r, 2, v)
        c.number_format = fmt
        if not (isinstance(v, str) and v.startswith("=")):
            c.fill = F_INPUT
    EQ, FEEV, INFL, RSB, RSE, CAP, VAT = "$B$4", "$B$7", "$B$8", "$B$9", "$B$10", "$B$11", "$B$6"

    # ------------------------------------------------------------------ plan the table rows
    HR = 14
    plan: list[tuple] = []
    by_sec = {k: [r for r in rows_in if r["section"] == k] for k, _, _ in secs}
    for gi, group in enumerate(["equity", "gov", "corp", "funds"]):
        gsecs = [s for s in secs if s[2] == group]
        for key, label, _ in gsecs:
            plan.append(("head", key, label))
            for r in by_sec[key]:
                plan.append(("row", key, r))
            if key != "funds":
                plan.append(("contrib", key, None))
            plan.append(("total", key, label))
        if len(gsecs) > 1:
            plan.append(("gtotal", group, [s[0] for s in gsecs]))
    plan.append(("cash", None, None))
    pos = {}
    r0 = HR + 1
    for i, e in enumerate(plan):
        pos[i] = r0 + i
    last = r0 + len(plan) - 1
    fund_rows = [pos[i] for i, e in enumerate(plan) if e[0] == "row" and e[1] == "funds"]
    fa, fb = (min(fund_rows), max(fund_rows)) if fund_rows else (None, None)
    total_row = {e[1]: pos[i] for i, e in enumerate(plan) if e[0] == "total"}
    gtotal_row = {e[1]: pos[i] for i, e in enumerate(plan) if e[0] == "gtotal"}

    def rng(c: str) -> str:  # holdings table without the cash row (which points back at the summary)
        return f"${c}${r0}:${c}${last - 1}"

    Y, Z, AA, AB, AC = (col(HELP0 + i) for i in range(5))
    LTC = {k: col(HELP0 + 5 + i) for i, k in enumerate(LT_KEYS)}

    # summary cell addresses (column U), fixed rows so the row formulas can point at them
    S = {}
    srow = HR
    summary_spec = [
        ("duration", 'סה"כ מח"מ בתיק', NUM2), ("irr", "תשואה פנימית של התיק", PCT3), ("bonds", 'סה"כ אג"ח', PCT),
        ("cash", 'עו"ש התיק', PCT), ("equity", 'סה"כ מניות (כולל שיקוף קרנות)', PCT), ("gov", 'סה"כ ממשלתי', PCT),
        ("corp", 'סה"כ קונצרני', PCT), ("funds", 'סה"כ קרנות', PCT), ("linked", 'סה"כ צמוד', PCT), ("shekel", 'סה"כ שקלי', PCT),
        ("linkedShare", "שיעור הצמוד מהצמוד + השקלי", PCT), ("shekelShare", "שיעור השקלי מהצמוד + השקלי", PCT),
        ("fx", 'סה"כ מט"ח', PCT), ("us", 'סה"כ ארה"ב (כולל קרנות)', PCT), ("equityPosition", "פוזיציה מנייתית", PCT),
        ("foreignEqShare", 'חשיפה מנייתית לחו"ל מסך המניות', PCT), ("ilEqShare", "חשיפה מנייתית לארץ מסך המניות", PCT),
        ("fundFees", "דמי ניהול של הקרנות בתיק", PCT3), ("directFees", "דמי ניהול חוזה על ניירות ישירים", PCT3),
        ("cashFee", 'דמי ניהול על העו"ש', PCT3), ("totalFees", 'סה"כ דמי ניהול בתיק', PCT3),
        ("revenue", 'סה"כ הכנסות לבית', PCT3), ("revenueExVat", 'הכנסות ללא מע"מ', PCT3),
        ("hedged", 'מניות חו"ל מנוטרלות מט"ח', PCT), ("fundFeesEq", "מתוכם דמי קרנות מניות", PCT3),
    ]
    for i, (k, _, _) in enumerate(summary_spec):
        S[k] = f"$U${srow + 1 + i}"

    # ------------------------------------------------------------------ header
    for j, h in enumerate(HEAD, 1):
        c = ws.cell(HR, j, h)
        c.fill, c.font = F_HEAD, Font(bold=True, color="FFFFFF", size=10)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for j, h in enumerate(HELP):
        c = ws.cell(HR, HELP0 + j, h)
        c.fill, c.font = F_TOT, Font(bold=True, size=9, color="687288")
    ws.row_dimensions[HR].height = 30

    def tsum(key, c):
        return f"{c}{total_row[key]}" if key in total_row else "0"

    # ------------------------------------------------------------------ rows
    for i, (kind, key, x) in enumerate(plan):
        r = pos[i]
        if kind == "head":
            ws.cell(r, 1, x).font = Font(bold=True, color=NAVY)
            for j in range(1, 19):
                ws.cell(r, j).fill = F_SEC
            continue
        if kind == "row":
            group = next(s[2] for s in secs if s[0] == key)
            ws.cell(r, 1, x["id"])
            ws.cell(r, 2, x.get("name") or x["id"])
            if x.get("label"):
                ws.cell(r, 3, x["label"])
            if x.get("bucket"):
                ws.cell(r, 4, int(x["bucket"]))
            e = ws.cell(r, 5, (x.get("E") or 0) / 100)
            e.number_format, e.fill = PCT, F_INPUT
            eq_sleeve = x.get("sleeve") == "equity"
            ws.cell(r, 6, f"=E{r}*{EQ}" if eq_sleeve else f"=E{r}*(1-{EQ})").number_format = PCT
            for cc, k, fmt in ((7, "G", PCT), (8, "H", PCT), (9, "I", PCT), (10, "J", PCT)):
                if x.get(k) is not None:
                    c = ws.cell(r, cc, x[k] / 100)
                    c.number_format, c.fill = fmt, F_INPUT
            if key in CPI:
                ws.cell(r, 11, f"={INFL}").number_format = PCT
            if x.get("M") is not None:
                c = ws.cell(r, 13, x["M"])
                c.number_format, c.fill = NUM2, F_INPUT
            if group != "equity":
                if x.get("G") is not None or key in CPI:
                    ws.cell(r, 12, f"=IF({S['bonds']}>0,(K{r}+G{r})*F{r}/{S['bonds']},\"\")").number_format = PCT3
                if x.get("M") is not None:
                    ws.cell(r, 14, f"=IF(1-{S['equity']}>0,M{r}*F{r}/(1-{S['equity']}),\"\")").number_format = NUM2
            if key == "funds":
                if x.get("fee") is not None:
                    c = ws.cell(r, 15, x["fee"] / 100)
                    c.number_format, c.fill = PCT3, F_INPUT
                    ws.cell(r, 16, f"=O{r}*F{r}").number_format = PCT3
            else:
                ws.cell(r, 15, f"={FEEV}").number_format = PCT3
                ws.cell(r, 16, f"=O{r}*F{r}").number_format = PCT3
            if x.get("Q"):
                ws.cell(r, 17, x["Q"])
            if x.get("R"):
                ws.cell(r, 18, x["R"])
            ws.cell(r, HELP0, "נייר")
            ws.cell(r, HELP0 + 1, key)
            ws.cell(r, HELP0 + 2, "equity" if eq_sleeve else "bond")
            ws.cell(r, HELP0 + 3, 1 if x.get("hedged") else 0)
            ws.cell(r, HELP0 + 4, x.get("us") or 0)
            for k2, cl in LTC.items():
                if x.get("lt"):
                    ws[f"{cl}{r}"] = x["lt"].get(k2, 0)
            continue
        if kind == "contrib":
            ws.cell(r, 2, "תרומת קרנות").font = Font(italic=True, color="687288")
            f = f"=SUMPRODUCT($F${fa}:$F${fb},{LTC[key]}{fa}:{LTC[key]}{fb})" if fa else "=0"
            c = ws.cell(r, 6, f)
            c.number_format, c.font = PCT, Font(italic=True, color="687288")
            ws.cell(r, HELP0, "תרומה")
            ws.cell(r, HELP0 + 1, key)
            continue
        if kind == "total":
            own = [pos[j] for j, e in enumerate(plan) if e[0] == "row" and e[1] == key]
            contrib = next((pos[j] for j, e in enumerate(plan) if e[0] == "contrib" and e[1] == key), None)
            a, b = (min(own), max(own)) if own else (r, r - 1)
            ws.cell(r, 1, f"סה״כ {x}")
            if own:
                ws.cell(r, 5, f"=SUM(E{a}:E{b})").number_format = PCT
                ws.cell(r, 6, f"=SUM(F{a}:F{b})" + (f"+F{contrib}" if contrib else "")).number_format = PCT
                for cc in ("G", "M"):
                    ws[f"{cc}{r}"] = f'=IFERROR(SUMPRODUCT({cc}{a}:{cc}{b},F{a}:F{b})/SUMPRODUCT(--ISNUMBER({cc}{a}:{cc}{b}),F{a}:F{b}),"")'
                    ws[f"{cc}{r}"].number_format = PCT if cc == "G" else NUM2
                for cc in ("H", "I"):
                    ws[f"{cc}{r}"] = f"=SUMPRODUCT({cc}{a}:{cc}{b},F{a}:F{b})"
                    ws[f"{cc}{r}"].number_format = PCT3
                for cc, fmt in (("L", PCT3), ("N", NUM2), ("P", PCT3)):
                    ws[f"{cc}{r}"] = f"=SUM({cc}{a}:{cc}{b})"
                    ws[f"{cc}{r}"].number_format = fmt
            else:
                ws.cell(r, 6, f"=F{contrib}" if contrib else "=0").number_format = PCT
            for j in range(1, 19):
                ws.cell(r, j).fill = F_TOT
                ws.cell(r, j).font = Font(bold=True)
            ws.cell(r, HELP0, "סה״כ")
            ws.cell(r, HELP0 + 1, key)
            continue
        if kind == "gtotal":
            ws.cell(r, 1, GROUP_TOTAL[key])
            for cc, fmt in (("F", PCT), ("L", PCT3), ("N", NUM2), ("P", PCT3)) + ((("E", PCT),) if key == "equity" else ()):
                ws[f"{cc}{r}"] = "=" + "+".join(f"{cc}{total_row[k]}" for k in x)
                ws[f"{cc}{r}"].number_format = fmt
            for j in range(1, 19):
                ws.cell(r, j).fill = F_GTOT
                ws.cell(r, j).font = Font(bold=True)
            ws.cell(r, HELP0, "סה״כ")
            continue
        if kind == "cash":
            ws.cell(r, 1, "עו״ש")
            ws.cell(r, 6, f"={S['cash']}").number_format = PCT
            ws.cell(r, 15, f"={FEEV}").number_format = PCT3
            ws.cell(r, 16, f"=MAX(0,F{r})*O{r}").number_format = PCT3
            for j in range(1, 19):
                ws.cell(r, j).fill = F_GTOT
                ws.cell(r, j).font = Font(bold=True)
            ws.cell(r, HELP0, "עו״ש")

    # ------------------------------------------------------------------ summary (T:U) + bands (V:X)
    ws.cell(HR, 20, "סיכום התיק").font = Font(bold=True, color="FFFFFF")
    ws.cell(HR, 20).fill = F_HEAD
    for cc, h in ((21, "ערך"), (22, "מינימום"), (23, "מקסימום"), (24, "בדיקה")):
        c = ws.cell(HR, cc, h)
        c.fill, c.font = F_HEAD, Font(bold=True, color="FFFFFF")
    fund_feq = (f"SUMPRODUCT($F${fa}:$F${fb},${AB}${fa}:${AB}${fb},${LTC['eq_foreign']}${fa}:${LTC['eq_foreign']}${fb})" if fa else "0")
    F = {
        "duration": f'=SUMIF({rng(Y)},"נייר",{rng("N")})',
        "irr": f'=SUMIF({rng(Y)},"נייר",{rng("L")})',
        "bonds": f"=1-{S['equity']}-{S['cash']}",
        "cash": f'=1-SUMIF({rng(Y)},"נייר",{rng("F")})',
        "equity": f"={tsum('eq_il', 'F')}+{tsum('eq_foreign', 'F')}",
        "gov": "=" + "+".join(tsum(k, "F") for k in ("gov_cpi", "gov_usd", "gov_nominal", "gov_float")),
        "corp": "=" + "+".join(tsum(k, "F") for k in ("corp_usd", "corp_cpi", "corp_nominal", "corp_float", "corp_hedged")),
        "funds": f'=SUMIFS({rng("F")},{rng(Y)},"נייר",{rng(Z)},"funds")',
        "linked": f"={tsum('gov_cpi', 'F')}+{tsum('corp_cpi', 'F')}",
        "shekel": "=" + "+".join(tsum(k, "F") for k in ("gov_nominal", "gov_float", "corp_nominal", "corp_float", "corp_hedged")),
        "linkedShare": f"=IF({S['linked']}+{S['shekel']}>0,{S['linked']}/({S['linked']}+{S['shekel']}),\"\")",
        "shekelShare": f"=IF({S['linked']}+{S['shekel']}>0,{S['shekel']}/({S['linked']}+{S['shekel']}),\"\")",
        "hedged": f'=SUMIFS({rng("F")},{rng(Y)},"נייר",{rng(Z)},"eq_foreign",{rng(AB)},1)+{fund_feq}',
        "fx": f"={tsum('eq_foreign', 'F')}+{tsum('gov_usd', 'F')}+{tsum('corp_usd', 'F')}-{S['hedged']}",
        "us": f'=SUMPRODUCT(({rng(Y)}="נייר")*{rng("F")}*{rng(AC)})/100',
        "equityPosition": f"=IF({EQ}>0,{S['equity']}/{EQ},\"\")",
        "foreignEqShare": f"=IF({S['equity']}>0,{tsum('eq_foreign', 'F')}/{S['equity']},\"\")",
        "ilEqShare": f"=IF({S['equity']}>0,{tsum('eq_il', 'F')}/{S['equity']},\"\")",
        "fundFees": f'=SUMIFS({rng("P")},{rng(Y)},"נייר",{rng(Z)},"funds")',
        "directFees": f'=SUMIFS({rng("P")},{rng(Y)},"נייר",{rng(Z)},"<>funds")',
        "cashFee": f"=MAX(0,{S['cash']})*{FEEV}",
        "totalFees": f"={S['directFees']}+{S['fundFees']}+{S['cashFee']}",
        "fundFeesEq": f'=SUMIFS({rng("P")},{rng(Y)},"נייר",{rng(Z)},"funds",{rng(AA)},"equity")',
        "revenue": f"={S['directFees']}+{S['cashFee']}+{RSB}*({S['fundFees']}-{S['fundFeesEq']})+{RSE}*{S['fundFeesEq']}",
        "revenueExVat": f"={S['revenue']}/(1+{VAT})",
    }
    bands = (st.get("bands") or {})
    band_of = {"duration": ("duration", 1), "linkedShare": ("linked", 100), "shekelShare": ("shekel", 100)}
    if template != "israel":
        band_of["foreignEqShare"] = ("foreign_eq", 100)
    for i, (k, label, fmt) in enumerate(summary_spec):
        r = srow + 1 + i
        ws.cell(r, 20, label)
        c = ws.cell(r, 21, F[k])
        c.number_format = fmt
        c.font = Font(bold=True)
        if k in band_of and bands.get(band_of[k][0]):
            lo, hi = bands[band_of[k][0]]
            sc = band_of[k][1]
            for cc, v in ((22, lo / sc), (23, hi / sc)):
                b = ws.cell(r, cc, v)
                b.number_format, b.fill = fmt, F_INPUT
            ws.cell(r, 24, f'=IF(U{r}="","",IF(AND(U{r}>=V{r}-1E-9,U{r}<=W{r}+1E-9),"✓ בטווח","✗ מחוץ לטווח"))')
            ws.conditional_formatting.add(f"U{r}", FormulaRule(formula=[f'AND(U{r}<>"",OR(U{r}<V{r}-1E-9,U{r}>W{r}+1E-9))'],
                                                                 font=Font(color="C62828", bold=True), fill=PatternFill("solid", fgColor="FDE8E8")))
        if k == "funds":
            ws.cell(r, 23, f"={CAP}").number_format = PCT
            ws.cell(r, 24, f'=IF(U{r}<=W{r}+1E-9,"✓ בטווח","✗ מעל המגבלה")')
            ws.conditional_formatting.add(f"U{r}", FormulaRule(formula=[f"U{r}>W{r}+1E-9"], font=Font(color="C62828", bold=True),
                                                                 fill=PatternFill("solid", fgColor="FDE8E8")))

    # rating buckets
    rb = srow + len(summary_spec) + 3
    ws.cell(rb - 1, 20, "קונצרני וקרנות לפי קבוצת סיכון").font = Font(bold=True, color=NAVY)
    for cc, h in ((21, "משקל"), (22, "יחסי")):
        ws.cell(rb - 1, cc, h).font = Font(bold=True)
    for i, (k, label) in enumerate(BUCKETS):
        r = rb + i
        ws.cell(r, 20, label)
        ws.cell(r, 21, f"=SUMIF({rng('D')},{k},{rng('F')})").number_format = PCT
        ws.cell(r, 22, f"=IF(SUM($U${rb}:$U${rb + 3})>0,U{r}/SUM($U${rb}:$U${rb + 3}),0)").number_format = PCT
    ws.cell(rb + 4, 20, "סה״כ").font = Font(bold=True)
    ws.cell(rb + 4, 21, f"=SUM(U{rb}:U{rb + 3})").number_format = PCT

    # ------------------------------------------------------------------ cosmetics
    widths = {1: 12, 2: 34, 3: 18, 4: 9, 5: 10, 6: 10, 7: 10, 8: 10, 9: 10, 10: 9, 11: 10, 12: 11, 13: 8, 14: 10, 15: 10, 16: 11,
              17: 9, 18: 9, 19: 3, 20: 36, 21: 12, 22: 10, 23: 10, 24: 13}
    for j, w in widths.items():
        ws.column_dimensions[col(j)].width = w
    for j in range(HELP0, HELP0 + len(HELP)):
        ws.column_dimensions[col(j)].width = 11
    ws.column_dimensions.group(col(HELP0), col(HELP0 + len(HELP) - 1), hidden=True, outline_level=1)
    ws.freeze_panes = ws.cell(HR + 1, 3)
    for row in ws.iter_rows(min_row=HR, max_row=last, max_col=18):
        for c in row:
            c.border = Border(bottom=THIN)

    # notes sheet
    nt = wb.create_sheet("הסבר")
    nt.sheet_view.rightToLeft = True
    notes = [
        "איך הגיליון בנוי",
        "אחוז ראשי (E) = משקל הנייר בתוך הרכיב שלו (מניות / אג״ח). אחוז יחסי (F) = E × אחוז מנייתי, או E × (1 − אחוז מנייתי) לרכיב האג״ח.",
        "תשואה פנימית (L) = (אינפלציה גלומה + תשואה ברוטו) × F ÷ סה״כ אג״ח.   מח״מ בתיק (N) = מח״מ × F ÷ (100% − סה״כ מניות).",
        "דמי ניהול (O) = דמי ניהול חוזה כולל מע״מ לניירות ישירים ולעו״ש, ודמי הניהול של הקרן לקרנות.   דמי ניהול בתיק (P) = O × F.",
        "תרומת קרנות = Σ (משקל הקרן × חלק הקרן בסעיף), לפי עמודות השיקוף המקובצות (Y:AO) – אפשר לפתוח אותן בכפתור ה-+ מעל העמודות.",
        "עו״ש = 100% − סכום המשקלים של כל הניירות.   הכנסות לבית = דמי ניהול חוזה + עו״ש + חלק הבית בדמי הקרנות (אג״ח / מניות).",
        "קבוצת סיכון (D): 1 תחליף ממשלתי · 2 חזק · 3 בינוני · 4 סיכון גבוה.",
        "הגיליון חושב באותן נוסחאות כמו האתר; ערכים שיוזנו כאן לא חוזרים לאתר אוטומטית.",
    ]
    for i, t in enumerate(notes, 1):
        nt.cell(i, 1, t).font = Font(bold=(i == 1), size=12 if i == 1 else 10)
    nt.column_dimensions["A"].width = 130

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
