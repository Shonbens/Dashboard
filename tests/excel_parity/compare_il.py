import json, sys
xl, st = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
S, T = st["summary"], st["secTotal"]; res = []
def x(c, k=100):
    v = xl.get(c); return v * k if isinstance(v, (int, float)) else v
def chk(lab, e, s, note=""):
    ok = None if not isinstance(e, (int, float)) else abs(e - (s or 0)) <= 1e-6 * max(1, abs(e))
    res.append((lab, e, s, ok, note))
chk('U5 מח"מ', x("U5", 1), S["duration"]); chk("U6 תשואה פנימית", x("U6"), S["irr"]); chk('U7 אג"ח', x("U7"), S["bonds"])
chk('U8 עו"ש', x("U8"), S["cash"]); chk("U9 קונצרני (מקור)", x("U9"), S["corp"], "תבנית: E68 במקום F68"); chk("U9 קונצרני (מתוקן)", x("AK68"), S["corp"])
chk("U10 צמוד", x("U10"), S["linked"]); chk("U11 שקלי (מקור)", x("U11"), S["shekel"], "תבנית: F67 ריק"); chk("U11 שקלי (מתוקן)", x("AK11"), S["shekel"])
chk('U12 מט"ח (מקור)', x("U12"), S["fx"], "תבנית: E במקום F"); chk('U12 מט"ח (מתוקן)', x("AK12"), S["fx"])
chk("U15 פוזיציה מנייתית", x("U15"), S["equityPosition"]); chk("U17 ישראל מסך המניות", x("U17"), S["ilEqShare"])
chk("U18 דמי ניהול קרנות", x("U18"), S["fundFees"]); chk('U19 סה"כ דמי ניהול', x("U19"), S["totalFees"])
chk("U20 הכנסות", x("U20"), S["revenue"]); chk('U21 ללא מע"מ', x("U21"), S["revenueExVat"])
for k, f in (("eq_il", "F23"), ("gov_cpi", "F28"), ("gov_usd", "F30"), ("gov_nominal", "F33"), ("gov_float", "F35"), ("corp_usd", "F38"),
             ("corp_cpi", "F53"), ("corp_nominal", "F63"), ("corp_float", "F65"), ("funds", "F89")):
    chk(f"{f} {k}", x(f), T[k]["F"])
for k, l, n in (("gov_cpi", "L28", "N28"), ("gov_nominal", "L33", "N33"), ("corp_cpi", "L53", "N53"), ("corp_nominal", "L63", "N63"), ("funds", "L89", "N89")):
    chk(f"{l} {k}", x(l), T[k]["L"]); chk(f"{n} {k}", x(n, 1), T[k]["N"])
for i, rr in enumerate(st["rating"]):
    note = "תבנית: B32=1 נשאר בשורת תרומת קרנות (ממשלתי שקלי)" if rr["key"] == 1 else ""
    chk(f"U{23 + i} דלי {rr['key']} (מקור)", x(f"U{23 + i}"), rr["F"], note)
    fixed = x(f"U{23 + i}") - (x("F32") if rr["key"] == 1 else 0)
    chk(f"U{23 + i} דלי {rr['key']} (בלי שורה 32)", fixed, rr["F"])
# Israeli sectors, evaluated the way Excel does (SUMIF resizes F6:F22 to F6:F23); AA = Z + X*X34 + W*W34 + V*V34 + U*U34 + Y*Y34
ils = {s["sector"]: s for s in st["ilSectors"]}
num = lambda c: xl.get(c) if isinstance(xl.get(c), (int, float)) else 0
w34 = {c: num(f"F{r}") for c, r in (("U", 7), ("V", 6), ("W", 83), ("X", 85), ("Y", 86))}
AA = {}
for r in list(range(35, 45)) + [46]:
    name = xl.get(f"T{r}")
    z = num("F16") if r == 46 else sum(num(f"F{q}") for q in range(6, 24) if xl.get(f"B{q}") == name)
    AA[r] = (name, (z + sum(num(f"{c}{r}") * w34[c] for c in "UVWXY")) * 100)
tot = sum(v for r, (n, v) in AA.items() if r != 46)
for r, (name, v) in AA.items():
    s = ils.get(name)
    if not s: continue
    chk(f"AA{r} {name}", v, s["total"])
    if r != 46:
        chk(f"AB{r} {name} יחסי", v / tot * 100, s["share"]); chk(f"AC{r} {name} פער", v / tot * 100 - num(f"U{r}") * 100, s["gap"])
bad = [r for r in res if r[3] is not True]
print(f"{len(res)} checks · {len(res) - len(bad)} match · {len(bad)} differ/n.a")
for lab, e, s, ok, note in bad:
    print(f"  {'✗' if ok is False else '?'} {lab}: excel {e} | site {s} {note}")
json.dump([list(r) for r in res], open(sys.argv[3], "w"), ensure_ascii=False)
