"""
Client-ready PDF for the potential-client portfolio review (A4, Hebrew RTL).

Written to be sent as-is to the prospect: personal greeting, plain-language labels and explanations,
the investment team's recommendations, next steps with the advisor's details, a short glossary and a disclaimer.
No internal wording (rule ids, data-coverage notes, source file names). Reuses report.py's primitives.
"""
from __future__ import annotations

import io
import time

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4

from report import (
    ASSET_ORDER, B, BG, CW, CYAN, FAINT, H, INK, LINE, LOSS, M, MD, MUTED, NAVY, R, RIGHT, SERIES, XB,
    NumberedCanvas, W, _fonts, ils, legend, logo, section, stacked_bar, text, wrap,
)

BOTTOM = 52
GREEN, GREEN_BG = HexColor("#1E7B34"), HexColor("#E6F4EA")
AMBER, AMBER_BG = HexColor("#B45309"), HexColor("#FFF4E0")
RED_BG = HexColor("#FDE8E8")

# How each checked figure is called in a document for the client
PLAIN_METRIC = {
    "Equity_Total": "חלק המניות בתיק",
    "Israel_Equity": "חלק המניות הישראליות מתוך המניות",
    "FX_Exposure": "חשיפה למטבע חוץ (דולר ואחרים)",
    "Single_Security": "משקל המניה / האג״ח הבודדת הגדולה",
    "Holdings_Count": "מספר ניירות הערך בתיק",
    "Gov_Bonds": "אג״ח ממשלתיות מתוך כלל האג״ח",
    "Shekel_Bonds": "אג״ח שקליות מתוך אג״ח שקליות וצמודות",
    "Duration": "משך ממוצע של האג״ח (מח״מ, בשנים)",
    "Low_Rated": "אג״ח בדירוג נמוך או ללא דירוג",
    "Managed_Funds": "קרנות נאמנות מנוהלות מתוך התיק",
    "Funds_ETF_Share": "קרנות ותעודות סל מתוך התיק",
    "Funds_Fee_Avg": "דמי ניהול ממוצעים בקרנות ובתעודות הסל",
}
ORDER = ["Equity_Total", "Israel_Equity", "FX_Exposure", "Single_Security", "Holdings_Count", "Gov_Bonds", "Shekel_Bonds",
         "Duration", "Low_Rated", "Managed_Funds", "Funds_ETF_Share", "Funds_Fee_Avg"]
STATE = {"ok": ("בטווח המומלץ", GREEN_BG, GREEN), "high": ("גבוה מהמומלץ", RED_BG, LOSS), "low": ("נמוך מהמומלץ", AMBER_BG, AMBER)}
KIND = {"cash": "פיקדון / מזומן", "equity": "מניה", "bond": "אג״ח", "etf": "תעודת סל", "other": "אחר"}

GLOSSARY = [
    ("אג״ח", "הלוואה למדינה (אג״ח ממשלתי) או לחברה (אג״ח קונצרני) תמורת ריבית."),
    ("צמוד מדד / שקלי", "אג״ח צמודה מתעדכנת לפי האינפלציה; אג״ח שקלית משלמת ריבית קבועה בשקלים."),
    ("מח״מ", "משך הזמן הממוצע עד החזר הכסף באג״ח. ככל שהוא ארוך יותר – האג״ח רגישות יותר לשינויי ריבית."),
    ("חשיפה למט״ח", "החלק בתיק שערכו מושפע משער הדולר ומטבעות זרים אחרים."),
    ("קרן מחקה / מנוהלת", "קרן מחקה עוקבת אחרי מדד בעלות נמוכה; בקרן מנוהלת מנהל בוחר את ההשקעות, ודמי הניהול גבוהים יותר."),
    ("דמי ניהול", "עלות שנתית שגובות הקרנות, באחוזים משווי ההשקעה. הם יורדים מהתשואה שלך מדי שנה."),
]
DISCLAIMER = (
    "סקירה זו הוכנה על בסיס פירוט האחזקות שמסרת לנו ועל נתונים ממקורות ציבוריים (מאי״ה, Yahoo Finance), לרבות הרכב הקרנות "
    "לפי הדיווח האחרון שלהן, וחלק מהנתונים מבוססים על הערכות. הסקירה נועדה לתת תמונה כללית בלבד, אינה מהווה ייעוץ השקעות "
    "ואינה מתחשבת בנתונים ובצרכים האישיים שלך. ההמלצות יותאמו לך במסגרת פגישת ייעוץ. ביצועי עבר אינם מעידים על ביצועים עתידיים."
)


def kind_label(r: dict) -> str:
    if r.get("asset_type") in ("alt", "structured"):
        return "השקעה אלטרנטיבית" if r["asset_type"] == "alt" else "מוצר מובנה"
    if r["kind"] == "fund":
        return "קרן מחקה" if r.get("tracker") else "קרן נאמנות מנוהלת"
    return KIND.get(r["kind"], "אחר")


def fmt_value(key, v) -> str:
    if v is None:
        return "—"
    if key == "Duration":
        return f"{v:.1f}"
    if key == "Holdings_Count":
        return str(int(v))
    if key == "Funds_Fee_Avg":
        return f"{v * 100:.2f}%"
    return f"{v * 100:.0f}%"


def range_text(key, lo, hi) -> str:
    f = lambda x: fmt_value(key, x)  # noqa: E731
    lo = None if lo in (None, 0) else lo
    hi = None if hi is None or (key == "Equity_Total" and hi >= 1) else hi
    if lo is not None and hi is not None:
        return f"{f(lo)} – {f(hi)}"
    if hi is not None:
        return f"עד {f(hi)}"
    if lo is not None:
        return f"לפחות {f(lo)}"
    return "—"


class Flow:
    """Keeps the current y and opens a continuation page (with a slim branded header) when space runs out."""

    def __init__(self, c, title):
        self.c, self.title, self.y = c, title, 0

    def new_page(self):
        c = self.c
        c.showPage()
        c.setFillColor(NAVY)
        c.rect(0, H - 46, W, 46, stroke=0, fill=1)
        c.setFillColor(CYAN)
        c.rect(0, H - 49, W, 3, stroke=0, fill=1)
        logo(c, M, H - 38, 28)
        text(c, RIGHT, H - 30, self.title, B, 13, white)
        self.y = H - 80

    def need(self, h):
        if self.y - h < BOTTOM:
            self.new_page()

    def para(self, s, size=9.8, color=INK, width=CW, leading=None, font=R, x_right=RIGHT):
        leading = leading or size * 1.5
        for block in str(s).split("\n"):
            for ln in wrap(block.strip(), font, size, width):
                self.need(leading)
                text(self.c, x_right, self.y, ln, font, size, color)
                self.y -= leading
        return self.y


def tile(c, x_right, y, w, h, label, value, caption):
    c.setFillColor(BG)
    c.roundRect(x_right - w, y - h, w, h, 8, stroke=0, fill=1)
    text(c, x_right - 11, y - 17, label, MD, 9, MUTED, width=w - 20)
    text(c, x_right - 11, y - 42, value, XB, 21, NAVY)
    yy = y - 58
    for ln in wrap(caption, R, 7.8, w - 22)[:3]:
        text(c, x_right - 11, yy, ln, R, 7.8, MUTED)
        yy -= 10.5


def intro_text(res: dict, n_insights: int) -> str:
    m, ex = res["comp"]["metrics"], res["comp"]["extras"]
    parts = [
        "לבקשתך, בחנו את תיק ההשקעות שלך כפי שהוא מנוהל היום. בדקנו איך הכסף מפוזר, מה רמת הסיכון ומה העלויות, "
        "והשווינו את התיק לעקרונות שלפיהם צוות ההשקעות של IBI בונה תיקים ללקוחותיו."
    ]
    eq = m["Equity_Total"] * 100
    parts.append(f"כ-{eq:.0f}% מהתיק מושקע במניות" + (f", מתוכן כ-{m['Israel_Equity'] * 100:.0f}% בישראל" if m.get("Israel_Equity") is not None else "")
                 + f", וכ-{ex['bonds']:.0f}% באג״ח.")
    if n_insights:
        parts.append(f"מצאנו {n_insights} נקודות שלדעתנו כדאי לבחון – הן מפורטות בהמשך, יחד עם ההמלצות שלנו.")
    else:
        parts.append("התיק עומד בכל הקריטריונים שבדקנו – בהמשך תמצא את הפירוט המלא.")
    return " ".join(parts)


def build_prospect_pdf(res: dict, client_name: str = "", advisor: str = "", aum: float | None = None, source: str = "",
                       contact: str = "") -> bytes:
    _fonts()
    buf = io.BytesIO()
    c = NumberedCanvas(buf, pagesize=A4, footer_title="סקירת תיק השקעות")
    c.setTitle("סקירת תיק השקעות – IBI")
    c.setAuthor("IBI בית השקעות")
    flow = Flow(c, "סקירת תיק ההשקעות שלך")
    comp, ev = res["comp"], res["eval"]
    m, ex = comp["metrics"], comp["extras"]
    today = time.strftime("%d.%m.%Y")

    # ------------------------------------------------------------ header
    band = 118
    c.setFillColor(NAVY)
    c.rect(0, H - band, W, band, stroke=0, fill=1)
    c.setFillColor(CYAN)
    c.rect(0, H - band - 3, W, 3, stroke=0, fill=1)
    logo(c, M, H - 80, 46)
    text(c, RIGHT, H - 36, "סקירת תיק השקעות אישית", MD, 10, CYAN)
    text(c, RIGHT, H - 72, f"שלום {client_name}," if client_name else "סקירת תיק ההשקעות שלך", XB, 28, white)
    sub = f"מצב התיק נכון ליום {today}" + (f" · הוכנה עבורך על ידי {advisor}" if advisor else "")
    text(c, RIGHT, H - 96, sub, R, 10, HexColor("#C9CCDA"), width=CW - 150)
    flow.y = H - band - 30

    flow.para(intro_text(res, len(ev["insights"])), 10.3, INK, leading=16)
    flow.y -= 12

    # ------------------------------------------------------------ key figures
    flow.y = section(c, flow.y, "התיק שלך במבט אחד")
    flow.y -= 4
    eff = ex.get("effective_fee")
    tiles = []
    if aum:
        tiles.append(("שווי התיק", ils(aum), f"{m['Holdings_Count']} ניירות ערך, לפי המחירים האחרונים."))
    tiles += [
        ("מושקע במניות", f"{m['Equity_Total'] * 100:.0f}%", "מניות צפויות לצמוח יותר לאורך זמן, אך תנודתיות יותר בדרך."),
        ("מושפע ממטבע חוץ", f"{m['FX_Exposure'] * 100:.0f}%", "החלק בתיק שעולה כשהדולר מתחזק ויורד כשהוא נחלש."),
    ]
    if eff is not None:
        tiles.append(("עלות שנתית משוקללת", f"{eff:.2f}%", "דמי הניהול של הקרנות בתיק, כאחוז מכלל התיק – בערך "
                      + (f"{ils(aum * eff / 100)} בשנה." if aum else "בכל שנה.")))
    n, gap, th = len(tiles), 9, 96
    tw = (CW - gap * (n - 1)) / n
    x = RIGHT
    for t in tiles:
        tile(c, x, flow.y, tw, th, *t)
        x -= tw + gap
    flow.y -= th + 22

    # ------------------------------------------------------------ composition
    flow.y = section(c, flow.y, "איך התיק שלך בנוי?", "לאחר בדיקה של מה שיש בתוך כל קרן")
    flow.y -= 8
    ac = ex["asset_classes"]
    stacked_bar(c, RIGHT, flow.y - 16, CW, 16, ac, ASSET_ORDER)
    legend(c, RIGHT, flow.y - 32, ASSET_ORDER, ac, size=8)
    flow.y -= 52
    pairs = [
        ("המניות שלך", [("בישראל", ex["eq_il"]), ("בחו״ל", ex["eq_foreign"])]),
        ("האג״ח שלך לפי מנפיק", [("ממשלתי", ex["gov"]), ("חברות", ex["corp"])]),
        ("האג״ח שלך לפי הצמדה", [("שקלי", ex["shekel"]), ("צמוד מדד", ex["linked"])]),
    ]
    colw = (CW - 2 * 14) / 3
    x = RIGHT
    for name, parts in pairs:
        tot = sum(v for _, v in parts)
        text(c, x, flow.y, name, MD, 9, INK)
        if tot > 0.05:
            bx = x
            for i, (_, v) in enumerate(parts):
                w = colw * v / tot
                c.setFillColor(SERIES[i])
                c.rect(bx - w + 0.5, flow.y - 16, max(0.5, w - 1), 9, stroke=0, fill=1)
                bx -= w
            text(c, x, flow.y - 28, "  ·  ".join(f"{lab} {v / tot * 100:.0f}%" for lab, v in parts), R, 7.8, MUTED, width=colw)
        else:
            text(c, x, flow.y - 16, "אין בתיק", R, 8, FAINT)
        x -= colw + 14
    flow.y -= 48

    # ------------------------------------------------------------ what we checked
    muted = set(ev.get("muted") or [])  # metrics whose recommendation the advisor left out: show the value, no verdict
    status = {s["metric"]: ({**s, "state": None} if s["metric"] in muted else s) for s in ev["status"] if s["value"] is not None}
    keys = [k for k in ORDER if k in status]
    flow.need(40 + 19 * len(keys))
    flow.y = section(c, flow.y, "מה בדקנו בתיק שלך", "בהשוואה לטווחים שאנו ממליצים עליהם")
    flow.y -= 4
    cols = [RIGHT - 8, RIGHT - 292, RIGHT - 372, M + 8]
    c.setFillColor(BG)
    c.rect(M, flow.y - 13, CW, 17, stroke=0, fill=1)
    for xx, h, al in zip(cols, ("מה בדקנו", "בתיק שלך", "הטווח המומלץ", ""), ("right", "right", "right", "left")):
        text(c, xx, flow.y - 8, h, B, 8, MUTED, al)
    flow.y -= 19
    for k in keys:
        st = status[k]
        label, fill, ink = STATE.get(st["state"], ("—", BG, MUTED))
        text(c, cols[0], flow.y - 9, PLAIN_METRIC.get(k, st["label"]), R, 9, INK, width=280)
        text(c, cols[1], flow.y - 9, fmt_value(k, st["value"]), B, 9.2, NAVY)
        text(c, cols[2], flow.y - 9, range_text(k, st["min"], st["max"]), R, 8.5, MUTED)
        if st["state"]:
            c.setFillColor(fill)
            c.roundRect(M + 6, flow.y - 13.5, 74, 14, 7, stroke=0, fill=1)
            text(c, M + 43, flow.y - 10, label, B, 7.8, ink, "center")
        c.setStrokeColor(LINE)
        c.setLineWidth(0.5)
        c.line(M, flow.y - 17.5, RIGHT, flow.y - 17.5)
        flow.y -= 19.5
    flow.y -= 14

    # ------------------------------------------------------------ recommendations
    flow.need(90)
    flow.y = section(c, flow.y, "ההמלצות שלנו")
    flow.y -= 6
    if not ev["insights"]:
        flow.para("התיק שלך עומד בכל הטווחים שבדקנו. נשמח לבחון יחד איתך את התאמתו למטרות ולצרכים שלך.", 10, INK, leading=15)
        flow.y -= 8
    for i, ins in enumerate(ev["insights"], 1):
        lines = []
        for block in ins["text"].split("\n"):
            if block.strip():
                lines += wrap(block.strip(), R, 9.6, CW - 42)
                lines.append("")
        lines = lines[:-1]
        h = 30 + sum(14 if ln else 5 for ln in lines) + 8
        flow.need(h)
        top = flow.y
        c.setFillColor(BG)
        c.roundRect(M, top - h, CW, h, 7, stroke=0, fill=1)
        c.setFillColor(CYAN)
        c.roundRect(RIGHT - 4, top - h, 4, h, 2, stroke=0, fill=1)
        c.setFillColor(NAVY)
        c.circle(RIGHT - 22, top - 16, 8.5, stroke=0, fill=1)
        text(c, RIGHT - 22, top - 19.5, str(i), B, 9, white, "center")
        text(c, RIGHT - 38, top - 20, ins["title"], B, 11, NAVY)
        yy = top - 40
        for ln in lines:
            if ln:
                text(c, RIGHT - 20, yy, ln, R, 9.6, INK)
            yy -= 14 if ln else 5
        flow.y = top - h - 10

    # ------------------------------------------------------------ next steps
    box_lines = wrap("נשמח להיפגש איתך כדי להכיר את המטרות, טווח ההשקעה והעדפות הסיכון שלך, ולהציג תיק מותאם אישית "
                     "שמיישם את ההמלצות שבסקירה.", R, 9.8, CW - 40)
    contact_line = " · ".join(x for x in (advisor, contact) if x)
    bh = 34 + len(box_lines) * 15 + (18 if contact_line else 0)
    flow.y -= 4
    flow.need(bh + 10)
    top = flow.y
    c.setFillColor(NAVY)
    c.roundRect(M, top - bh, CW, bh, 8, stroke=0, fill=1)
    text(c, RIGHT - 16, top - 20, "השלב הבא", B, 12, CYAN)
    yy = top - 38
    for ln in box_lines:
        text(c, RIGHT - 16, yy, ln, R, 9.8, white)
        yy -= 15
    if contact_line:
        text(c, RIGHT - 16, yy - 2, f"ליצירת קשר: {contact_line}", B, 9.8, white)
    flow.y = top - bh - 18

    # ------------------------------------------------------------ holdings
    rows = comp["rows"]
    flow.need(80)
    flow.y = section(c, flow.y, "פירוט האחזקות שלך", f"{len(rows)} ניירות ערך, מהגדול לקטן")
    hx = [RIGHT - 8, RIGHT - 262, RIGHT - 380, M + 90, M + 8]
    lim = next((float(r.get("max") or 0.05) for r in res.get("rules", []) if r.get("metric") == "Single_Security"), 0.05) * 100

    def head():
        c.setFillColor(BG)
        c.rect(M, flow.y - 13, CW, 17, stroke=0, fill=1)
        for xx, h, al in zip(hx, ("נייר ערך", "סוג", "דמי ניהול", "חלק מהתיק", "שווי"), ("right", "right", "right", "right", "left")):
            if h == "שווי" and not aum:
                continue
            text(c, xx, flow.y - 8, h, B, 8, MUTED, al)
        flow.y -= 19

    head()
    for i, r in enumerate(rows):
        if flow.y - 16 < BOTTOM:
            flow.new_page()
            head()
        flag = r["kind"] in ("equity", "bond") and r["weight"] > lim
        if flag:
            c.setFillColor(RED_BG)
            c.rect(M, flow.y - 12, CW, 15, stroke=0, fill=1)
        elif i % 2:
            c.setFillColor(HexColor("#FAFBFC"))
            c.rect(M, flow.y - 12, CW, 15, stroke=0, fill=1)
        text(c, hx[0], flow.y - 8, r["name"] or r["id"], MD, 8.5, INK, width=245)
        text(c, hx[1], flow.y - 8, kind_label(r), R, 8.2, MUTED, width=110)
        text(c, hx[2], flow.y - 8, "—" if r.get("fee") is None else f"{float(r['fee']):.2f}%", R, 8.2, MUTED)
        text(c, hx[3], flow.y - 8, f"{r['weight']:.1f}%", B, 8.6, LOSS if flag else NAVY)
        if aum:
            text(c, hx[4], flow.y - 8, ils(aum * r["weight"] / 100), R, 8.4, INK, "left")
        flow.y -= 16
    if any(r["kind"] in ("equity", "bond") and r["weight"] > lim for r in rows):
        flow.y -= 2
        text(c, RIGHT, flow.y - 6, f"מסומן: מניה או אג״ח בודדת שמהווה יותר מ-{lim:.0f}% מהתיק", R, 7.6, LOSS)
        flow.y -= 18

    # ------------------------------------------------------------ glossary + disclaimer
    flow.y -= 6
    flow.need(40 + len(GLOSSARY) * 24)
    flow.y = section(c, flow.y, "מילון קצר")
    for term, expl in GLOSSARY:
        flow.need(26)
        text(c, RIGHT, flow.y, term, B, 9, NAVY)
        flow.para(expl, 8.8, MUTED, width=CW - 120, x_right=RIGHT - 115, leading=12.5)
        flow.y -= 4
    lines = wrap(DISCLAIMER, R, 7.3, CW - 20)
    bh = 14 + len(lines) * 10
    flow.y -= 8
    flow.need(bh + 4)
    c.setFillColor(BG)
    c.roundRect(M, flow.y - bh, CW, bh, 6, stroke=0, fill=1)
    yy = flow.y - 13
    for ln in lines:
        text(c, RIGHT - 10, yy, ln, R, 7.3, MUTED)
        yy -= 10
    c.showPage()
    c.save()
    return buf.getvalue()
