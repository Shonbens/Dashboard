"""Compare Excel-engine results with the website engine for one test case."""
import json, sys

xl = json.load(open(sys.argv[1]))
st = json.load(open(sys.argv[2]))
S = st["summary"]
T = st["secTotal"]
TOL = 1e-6
res = []


def x(cell, scale=100):
    v = xl.get(cell)
    return v * scale if isinstance(v, (int, float)) else v


def chk(group, label, excel, site, note=""):
    if isinstance(excel, str) or excel is None:
        ok = None
    else:
        ok = abs((excel or 0) - (site or 0)) <= max(TOL, 1e-6 * abs(excel or 1))
    res.append((group, label, excel, site, ok, note))


# summary column
chk("סיכום", 'U5 מח"מ', x("U5", 1), S["duration"])
chk("סיכום", "U6 תשואה פנימית", x("U6"), S["irr"])
chk("סיכום", 'U7 סה"כ אג"ח', x("U7"), S["bonds"])
chk("סיכום", 'U8 עו"ש', x("U8"), S["cash"])
chk("סיכום", 'U9 קונצרני (מקור)', x("U9"), S["corp"], "תבנית: F77 ריק")
chk("סיכום", "U9 קונצרני (מתוקן)", x("AK9"), S["corp"])
chk("סיכום", "U10 צמוד", x("U10"), S["linked"])
chk("סיכום", "U11 שקלי (מקור)", x("U11"), S["shekel"], "תבנית: F43, F77 ריקים")
chk("סיכום", "U11 שקלי (מתוקן)", x("AK11"), S["shekel"])
chk("סיכום", 'V10 שיעור צמוד', x("V10"), S["linkedShare"])
chk("סיכום", 'U12 מט"ח (מקור)', x("U12"), S["fx"], "תבנית: F38 מדלג על שורה 36")
chk("סיכום", 'U12 מט"ח (מתוקן)', x("AK12"), S["fx"])
chk("סיכום", "U13 אמריקאיות – לוגיקת התבנית", x("AL13"), S["usFunds"], "תבנית: E במקום F, מדלגת על שורה 91")
chk("סיכום", "U13 אמריקאיות – מתוקן", x("AK13"), S["usFunds"])
chk("סיכום", "U15 פוזיציה מנייתית", x("U15"), S["equityPosition"])
chk("סיכום", 'U16 חו"ל מסך המניות (מקור)', x("U16"), S["foreignEqShare"], "תבנית: E30/E31 – ישיר בלבד")
chk("סיכום", 'U16 חו"ל מסך המניות (מתוקן)', x("AK16"), S["foreignEqShare"])
chk("סיכום", "U17 ישראל מסך המניות", x("U17"), S["ilEqShare"])
chk("סיכום", "U18 דמי ניהול קרנות", x("U18"), S["fundFees"])
chk("סיכום", 'U19 סה"כ דמי ניהול', x("U19"), S["totalFees"])
chk("סיכום", "U20 הכנסות", x("U20"), S["revenue"])
chk("סיכום", 'U21 הכנסות ללא מע"מ', x("U21"), S["revenueExVat"])

# section totals
SEC = [("eq_il", "F19", None, None), ("eq_foreign", "F30", None, None), ("gov_cpi", "F35", "L35", "N35"),
       ("gov_usd", "AJ38", "L38", "N38"), ("gov_nominal", "F41", "L41", "N41"), ("gov_float", "AJ43", None, None),
       ("corp_usd", "F47", "L47", "N47"), ("corp_cpi", "F61", "L61", "N61"), ("corp_nominal", "F73", "L73", "N73"),
       ("corp_float", "F75", None, None), ("corp_hedged", "AJ77", None, None), ("funds", "F99", "L99", "N99")]
chk("סעיפים", "F38 ממשלתי דולר (מקור)", x("F38"), T["gov_usd"]["F"], "תבנית: SUM(F37) בלבד")
for k, f, l, n in SEC:
    chk("סעיפים", f"{f} {k} – משקל", x(f), T[k]["F"])
    if l:
        chk("סעיפים", f"{l} {k} – תשואה", x(l), T[k]["L"])
        chk("סעיפים", f"{n} {k} – מח\"מ", x(n, 1), T[k]["N"])
for cell, keys in (("P31", ["eq_il", "eq_foreign"]), ("P44", ["gov_cpi", "gov_usd", "gov_nominal", "gov_float"]),
                   ("P78", ["corp_usd", "corp_cpi", "corp_nominal", "corp_float", "corp_hedged"]), ("P99", ["funds"])):
    chk("סעיפים", f"{cell} דמי ניהול", x(cell), sum(T[k]["P"] for k in keys))

# ratings – Excel's SUMIF resizes sum_range to the criteria range from its top-left cell (the template's ranges are shifted)
def sumif(b0, b1, f0, crit):
    tot = 0.0
    for i in range(b1 - b0 + 1):
        b = xl.get(f"B{b0 + i}")
        if isinstance(b, (int, float)) and b == crit:
            v = xl.get(f"F{f0 + i}")
            tot += v if isinstance(v, (int, float)) else 0
    return tot * 100
ORIG = {1: (32, 92, 32), 2: (34, 93, 34), 3: (34, 94, 35), 4: (35, 95, 37)}
chk("סיכום", "V10 שיעור צמוד (מתוקן)", xl["AK10"] / (xl["AK10"] + xl["AK11"]) * 100, S["linkedShare"])
for i, rr in enumerate(st["rating"]):
    chk("דירוג", f"U{23 + i} דלי {rr['key']} (מקור)", sumif(*ORIG[rr["key"]], rr["key"]), rr["F"], "תבנית: טווחי SUMIF מוזזים")
    chk("דירוג", f"U{23 + i} דלי {rr['key']} (מתוקן)", x(f"AK{23 + i}"), rr["F"])

# Israeli sectors
ils = {s["sector"]: s for s in st["ilSectors"]}
for r in range(35, 45):
    name = xl.get(f"T{r}")
    s = ils.get(name)
    if s:
        chk("ענפים ישראל", f"Z{r} {name}", x(f"Z{r}"), s["total"])
        chk("ענפים ישראל", f"AA{r} {name} יחסי", x(f"AA{r}"), s["share"])
        chk("ענפים ישראל", f"AB{r} {name} פער", x(f"AB{r}"), s["gap"])
chk("ענפים ישראל", "Z46 ביטחונית", x("Z46"), ils["ביטחונית"]["total"])

# foreign
fe = st["fexp"]
for cell, k in (("V52", "SP"), ("W52", "NDX"), ("X52", "STOXX"), ("Y52", "ROW"), ("Z52", "GLOBAL"), ("AA52", "RUSSELL")):
    chk('ענפים חו"ל', f"{cell} {k}", x(cell), fe[k])
fs = {s["sector"]: s for s in st["foreignSectors"]}
for r in range(53, 64):
    name = xl.get(f"U{r}")
    if name in fs:
        chk('ענפים חו"ל', f"AC{r} {name}", x(f"AC{r}"), fs[name]["total"])
        chk('ענפים חו"ל', f"AD{r} {name} יחסי", x(f"AD{r}"), fs[name]["share"])
chk('ענפים חו"ל', "AC65 שבבים", x("AC65"), fs["שבבים"]["total"])
geo = {g["key"]: g for g in st["geography"]}
for cell, k in (("Z23", "IL"), ("Z24", "US"), ("Z25", "EUROPE"), ("Z26", "EM")):
    chk("גיאוגרפיה", f"{cell} {k}", x(cell), geo[k]["F"], "תבנית: RUSSELL לא נספר בשום אזור" if k == "US" else "")

bad = [r for r in res if r[4] is False]
na = [r for r in res if r[4] is None]
print(f"{len(res)} checks · {len(res) - len(bad) - len(na)} match · {len(bad)} differ · {len(na)} n/a")
for g, lab, e, s, ok, note in res:
    if ok is not True:
        es = f"{e:.6f}" if isinstance(e, float) else str(e)
        ss = f"{s:.6f}" if isinstance(s, (int, float)) else str(s)
        print(f"  {'✗' if ok is False else '?'} [{g}] {lab}: excel {es} | site {ss}  {note}")
json.dump([list(r) for r in res], open(sys.argv[3], "w"), ensure_ascii=False)
