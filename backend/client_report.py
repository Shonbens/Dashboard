"""
Plain-language client portfolio report (A4, Hebrew RTL).

Written for retail clients: short sentences, everyday words, every number explained,
a comparison to the closest IBI house model, and "what could happen" in shekels.
Reuses the drawing primitives and branding of report.py.
"""
from __future__ import annotations

import io
import time

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.pdfmetrics import stringWidth

from report import (
    ASSET_ORDER, B, BG, CW, CYAN, FAINT, GAIN, GEO_ORDER, H, INK, LINE, LOSS, M, MD, MUTED, NAVY, OTHER, R, RIGHT,
    SERIES, XB, NumberedCanvas, W, _fonts, ils, legend, logo, pct, section, stacked_bar, text, wrap,
)

# Everyday names for the asset classes shown to clients
PLAIN_ASSET = {
    "מניות": "מניות",
    "אג״ח ממשלתי": "אג״ח ממשלתי (הלוואה למדינה)",
    "אג״ח קונצרני": "אג״ח של חברות (הלוואה לחברות)",
    "מזומן ופיקדונות": "מזומן ופיקדונות",
    "אחר": "אחר",
}
# Friendly scenario titles + one-line story (ids from stress.PRESETS)
PLAIN_SCENARIO = {
    "global_crisis": ("משבר חריף בשווקים בעולם", "הבורסות בעולם ובישראל יורדות בחדות, כמו במשברים פיננסיים גדולים בעבר"),
    "rate_hike": ("עלייה חדה בריבית", "הריבית עולה בחדות כדי לבלום אינפלציה – אג״ח ומניות נפגעים"),
    "shekel_strength": ("השקל מתחזק מול הדולר", "הדולר נחלש ב-10% – השקעות בחו״ל שוות פחות בשקלים"),
    "local_geopolitical": ("אירוע ביטחוני בישראל", "הבורסה בתל אביב יורדת והשקל נחלש"),
    "tech_correction": ("ירידה במניות בארה״ב", "מניות בארה״ב יורדות ב-20%, ובישראל ירידה מתונה יותר"),
    "soft_landing": ("תקופה טובה בשווקים", "הריבית יורדת והבורסות עולות"),
}
SCENARIO_ORDER = ["global_crisis", "rate_hike", "shekel_strength", "soft_landing"]

# Plain explanation of what a holding is, from its look-through label / asset class
LABEL_PLAIN = {
    "S&P 500": "מחקה את 500 החברות הגדולות בארה״ב",
    "Nasdaq-100": "מחקה את 100 החברות הגדולות בנאסד״ק, בעיקר טכנולוגיה",
    "US Total Market": "מחקה את כל שוק המניות בארה״ב",
    "MSCI World": "מחקה אלפי חברות גדולות במדינות המפותחות",
    "MSCI ACWI": "מחקה אלפי חברות מכל העולם",
    "Developed ex-US": "מחקה חברות במדינות מפותחות מחוץ לארה״ב",
    "Emerging Markets": "מחקה חברות בשווקים מתעוררים (סין, הודו ועוד)",
    "Europe": "מחקה חברות גדולות באירופה",
    "Israel equities": "מחקה מניות של חברות ישראליות",
    "ת״א 35": "מחקה את 35 החברות הגדולות בבורסה בתל אביב",
    "ת״א 125": "מחקה את 125 החברות הגדולות בבורסה בתל אביב",
    "אג״ח ממשלתי ישראלי": "אג״ח של מדינת ישראל – נחשב יציב יחסית",
    "תל בונד / אג״ח קונצרני": "אג״ח של חברות ישראליות גדולות",
    "קרן כספית": "קרן כספית – חלופה לפיקדון, סיכון נמוך מאוד",
    "US Aggregate Bonds": "אג״ח של ממשלת ארה״ב וחברות אמריקאיות",
    "US Treasuries 20Y+": "אג״ח ארוך של ממשלת ארה״ב – רגיש לשינויי ריבית",
    "US Treasuries 7-10Y": "אג״ח של ממשלת ארה״ב לטווח בינוני",
    "US Treasuries 1-3Y": "אג״ח קצר של ממשלת ארה״ב – יציב יחסית",
    "US T-Bills": "פיקדון דולרי קצר מאוד של ממשלת ארה״ב",
    "US IG Corporate": "אג״ח של חברות אמריקאיות גדולות ויציבות",
    "US High Yield": "אג״ח של חברות אמריקאיות בסיכון גבוה יותר",
    "Gold": "השקעה בזהב",
}

GLOSSARY = [
    ("מניה", "חלק קטן בבעלות על חברה. יכולה לעלות או לרדת בחדות, ולאורך שנים צפויה לצמוח יותר."),
    ("אג״ח", "הלוואה שאתם נותנים למדינה או לחברה תמורת ריבית. בדרך כלל יציבה יותר ממניות."),
    ("קרן סל / קרן נאמנות", "סל שמחזיק הרבה ניירות ערך בבת אחת – דרך פשוטה לפזר את הסיכון."),
    ("חשיפה למט״ח", "החלק בתיק שמושפע משער הדולר ומטבעות זרים אחרים."),
    ("דמי ניהול", "עלות שנתית שגובות הקרנות, באחוזים משווי ההשקעה."),
]

PLAIN_DISCLAIMER = (
    "דוח זה נועד לתת תמונה כללית ופשוטה של התיק ואינו מהווה ייעוץ השקעות או המלצה לפעולה. הנתונים מבוססים על מחירים "
    "וגילויים ממקורות ציבוריים (מאי״ה, Yahoo Finance, ביזפורטל) ועל הנחות חישוב, ועשויים להיות לא מדויקים. התרחישים הם "
    "דוגמאות בלבד ואינם תחזית. ביצועי עבר אינם מעידים על ביצועים עתידיים. לכל שאלה ניתן לפנות למנהל התיק שלך."
)


def plain_holding(row: dict, xh: dict | None) -> str:
    label = (xh or {}).get("label") or ""
    if label in LABEL_PLAIN:
        prefix = "קרן סל ש" if (row.get("asset_class") == "קרנות סל") else ("קרן ש" if "קרנות" in (row.get("asset_class") or "") else "")
        txt = LABEL_PLAIN[label]
        return prefix + txt if prefix and txt.startswith("מחקה") else txt
    ac = row.get("asset_class") or ""
    lab = label
    if (xh or {}).get("method") == "maya":
        if "כספית" in lab or "כספי" in lab:
            return "קרן כספית – חלופה לפיקדון, סיכון נמוך מאוד"
        if "מניות" in lab and "חו״ל" in lab.replace('"', "״") or "מניות בחו" in lab:
            return "קרן נאמנות שמשקיעה במניות בחו״ל"
        if "מניות" in lab:
            return "קרן נאמנות שמשקיעה במניות"
        if "מדינה" in lab or "ממשל" in lab:
            return "קרן נאמנות שמשקיעה באג״ח של המדינה"
        if "אג" in lab:
            return "קרן נאמנות שמשקיעה באג״ח"
        return "קרן נאמנות"
    if ac == "מניות":
        where = {"IL": "ישראלית", "US": "אמריקאית"}.get(row.get("market"), "")
        return f"מניה של חברה {where}".strip()
    if ac.startswith("אג"):
        return "אג״ח של המדינה" if "ממשלתי" in ac else "אג״ח של חברה"
    if ac == "קרנות סל":
        return "קרן סל"
    return ac or "—"


def para(c, y, s, size=10, color=INK, width=CW, leading=None, font=R, x_right=RIGHT):
    leading = leading or size * 1.5
    for ln in wrap(s, font, size, width):
        text(c, x_right, y, ln, font, size, color)
        y -= leading
    return y


def risk_word(eq: float) -> tuple[int, str]:
    level = max(1, min(5, int((eq + 19.999) // 20)))
    return level, {1: "יציב מאוד", 2: "יציב", 3: "מאוזן", 4: "צומח", 5: "צומח ותנודתי"}[level]


def approx(v: float) -> str:
    """Round percentages the way people talk: 'כ-60%'."""
    return f"כ-{round(v):.0f}%"


def summary_sentence(p: dict) -> str:
    ac = p["asset_classes"]
    eq = ac.get("מניות", 0)
    bonds = ac.get("אג״ח ממשלתי", 0) + ac.get("אג״ח קונצרני", 0)
    cash = ac.get("מזומן ופיקדונות", 0)
    geo = sorted(((k, v) for k, v in p["geography"].items() if k != "אחר"), key=lambda kv: -kv[1])
    where = " ו".join(k for k, v in geo[:2] if v >= 10) or "במגוון מקומות"
    parts = [f"התיק שלך מחולק ל-{p['holdings_count']} השקעות."]
    parts.append(f"{approx(eq)} מהכסף מושקע במניות – החלק שצפוי לצמוח יותר לאורך זמן, אבל גם לעלות ולרדת יותר בדרך.")
    if bonds + cash >= 1:
        parts.append(f"{approx(bonds + cash)} נמצאים באג״ח ובמזומן – החלק היציב יותר של התיק.")
    parts.append(f"רוב הכסף מושקע ב{where}.")
    fx = p["metrics"]["fx_exposure"]
    if fx >= 5:
        parts.append(f"{approx(fx)} מהתיק מושפעים משער הדולר: כשהדולר מתחזק התיק מרוויח, וכשהוא נחלש – מפסיד.")
    return " ".join(parts)


def comparison_sentences(p: dict, m: dict) -> list[str]:
    out = []
    for key in ("מניות", "אג״ח ממשלתי", "אג״ח קונצרני", "מזומן ופיקדונות"):
        a, b = p["asset_classes"].get(key, 0), m["asset_classes"].get(key, 0)
        d = a - b
        if abs(d) >= 3:
            more = "יותר" if d > 0 else "פחות"
            out.append(f"יש בתיק שלך {more} {PLAIN_ASSET[key].split(' (')[0]} מאשר במודל ({round(a):.0f}% לעומת {round(b):.0f}%).")
    fa, fb = p["metrics"]["fx_exposure"], m["metrics"]["fx_exposure"]
    if abs(fa - fb) >= 5:
        out.append(f"התיק שלך {'יותר' if fa > fb else 'פחות'} מושפע משער הדולר ({round(fa):.0f}% לעומת {round(fb):.0f}%).")
    if not out:
        out.append("החלוקה בתיק שלך קרובה מאוד למודל – אין הבדלים משמעותיים.")
    return out


# --------------------------------------------------------------------------- #
def big_tile(c, x_right, y, w, h, label, value, caption, value_color=NAVY):
    c.setFillColor(BG)
    c.roundRect(x_right - w, y - h, w, h, 8, stroke=0, fill=1)
    text(c, x_right - 12, y - 18, label, MD, 9.5, MUTED)
    text(c, x_right - 12, y - 46, value, XB, 24, value_color)
    yy = y - 64
    for ln in wrap(caption, R, 8.2, w - 24)[:3]:
        text(c, x_right - 12, yy, ln, R, 8.2, MUTED)
        yy -= 11.5


def risk_meter(c, y, eq):
    level, word = risk_word(eq)
    text(c, RIGHT, y, "עד כמה התיק שלך תנודתי?", B, 11, NAVY)
    text(c, M, y, f"{word} ({level} מתוך 5)", B, 11, NAVY, "left")
    y -= 22
    n, gap = 5, 6
    sw = (CW - gap * (n - 1)) / n
    shades = ["#BFEAF6", "#7FD3EC", "#2FB6DF", "#1F6FB0", "#1F3C96"]
    for i in range(n):
        x = RIGHT - i * (sw + gap)
        c.setFillColor(HexColor(shades[i]) if i < level else LINE)
        c.roundRect(x - sw, y - 4, sw, 10, 3, stroke=0, fill=1)
    text(c, RIGHT, y - 18, "יציב יותר", R, 8, MUTED)
    text(c, M, y - 18, "תנודתי יותר", R, 8, MUTED, "left")
    return y - 36


def compare_bars(c, y, p, m):
    rows = [k for k, _ in ASSET_ORDER if k != "אחר"]
    yours, model = SERIES[0], OTHER
    label_w = 175
    bar_w = CW - label_w - 50
    for k in rows:
        a, b = p["asset_classes"].get(k, 0), m["asset_classes"].get(k, 0)
        if a < 0.5 and b < 0.5:
            continue
        text(c, RIGHT, y - 4, PLAIN_ASSET[k], MD, 9, INK, width=label_w - 8)
        for j, (v, col) in enumerate(((a, yours), (b, model))):
            yy = y - j * 11
            w = bar_w * min(100, v) / 100
            c.setFillColor(col)
            c.roundRect(RIGHT - label_w - w, yy - 3, max(1, w), 8, 2, stroke=0, fill=1)
            text(c, RIGHT - label_w - w - 4, yy - 2, f"{v:.0f}%", B if j == 0 else R, 7.8, INK if j == 0 else MUTED)
        y -= 32
    legend(c, RIGHT - label_w, y + 6, [("התיק שלך", yours), (f"מודל {m['name']}", model)], size=8)
    return y - 14


def build_client_pdf(p: dict, closest: dict | None, aum: float, client_name: str = "", advisor: str = "") -> bytes:
    _fonts()
    buf = io.BytesIO()
    c = NumberedCanvas(buf, pagesize=A4, footer_title="הדוח האישי שלך")
    c.setTitle("הדוח האישי שלך – IBI")
    c.setAuthor("IBI בית השקעות")
    rep = p["report"]
    eq = p["metrics"]["equity_weight"]
    today = time.strftime("%d.%m.%Y")

    # ------------------------------------------------------------ Page 1
    band = 118
    c.setFillColor(NAVY)
    c.rect(0, H - band, W, band, stroke=0, fill=1)
    c.setFillColor(CYAN)
    c.rect(0, H - band - 3, W, 3, stroke=0, fill=1)
    logo(c, M, H - 80, 46)
    text(c, RIGHT, H - 36, "הדוח האישי שלך", MD, 10, CYAN)
    text(c, RIGHT, H - 72, f"שלום {client_name}," if client_name else "סקירת התיק שלך", XB, 28, white)
    sub = f"מצב התיק נכון ליום {today}" + (f" · הוכן עבורך על ידי {advisor}" if advisor else "")
    text(c, RIGHT, H - 96, sub, R, 10, HexColor("#C9CCDA"))
    y = H - band - 30

    y = section(c, y, "התיק שלך במבט אחד")
    y -= 4
    gap = 10
    tw = (CW - 2 * gap) / 3
    th = 100
    big_tile(c, RIGHT, y, tw, th, "שווי התיק", ils(aum), f"סך הכסף שמושקע בתיק, לפי המחירים האחרונים בבורסה.")
    big_tile(c, RIGHT - tw - gap, y, tw, th, "מושקע במניות", pct(eq, 0),
             "מניות צפויות לצמוח יותר לאורך זמן, אבל עולות ויורדות יותר בדרך.")
    big_tile(c, RIGHT - 2 * (tw + gap), y, tw, th, "מושפע משער הדולר", pct(p["metrics"]["fx_exposure"], 0),
             "החלק בתיק שעולה כשהדולר מתחזק ויורד כשהדולר נחלש.")
    y -= th + 20

    y = para(c, y, summary_sentence(p), 10.5, INK, leading=16)
    y -= 12
    y = risk_meter(c, y, eq)
    y -= 6

    y = section(c, y, "איפה הכסף שלך מושקע?", "לאחר בדיקה של מה שיש בתוך כל קרן")
    y -= 6
    plain_order = [(PLAIN_ASSET[k].split(" (")[0], col) for k, col in ASSET_ORDER]
    plain_data = {PLAIN_ASSET[k].split(" (")[0]: v for k, v in p["asset_classes"].items()}
    text(c, RIGHT, y, "לפי סוג השקעה", MD, 9.5, INK)
    stacked_bar(c, RIGHT - 95, y - 5, CW - 95, 18, plain_data, plain_order)
    legend(c, RIGHT - 95, y - 23, plain_order, plain_data, size=8)
    y -= 46
    text(c, RIGHT, y, "לפי אזור בעולם", MD, 9.5, INK)
    stacked_bar(c, RIGHT - 95, y - 5, CW - 95, 18, p["geography"], GEO_ORDER)
    legend(c, RIGHT - 95, y - 23, GEO_ORDER, p["geography"], size=8)
    y -= 50

    # Holdings in plain words
    y = section(c, y, "ממה מורכב התיק?")
    c.setFillColor(BG)
    c.rect(M, y - 5, CW, 17, stroke=0, fill=1)
    text(c, RIGHT - 6, y, "ההשקעה", MD, 8, MUTED)
    text(c, RIGHT - 196, y, "מה זה בשפה פשוטה", MD, 8, MUTED)
    text(c, M + 90, y, "חלק מהתיק", MD, 8, MUTED, "right")
    text(c, M + 6, y, "שווי", MD, 8, MUTED, "left")
    y -= 19
    xh_by = {h["input_id"]: h for h in rep["xray_holdings"]}
    rows = sorted(rep["rows"], key=lambda r: -(r.get("weight") or 0))
    for i, r in enumerate(rows):
        if y < 56:
            text(c, RIGHT - 6, y, f"ועוד {len(rows) - i} השקעות קטנות", R, 8.5, MUTED)
            break
        if i % 2:
            c.setFillColor(HexColor("#FAFBFC"))
            c.rect(M, y - 7, CW, 20, stroke=0, fill=1)
        name = r["name"] if r.get("priced") else (r.get("file_name") or r["name"])
        text(c, RIGHT - 6, y, name, MD, 8.6, INK, width=184)
        text(c, RIGHT - 196, y, plain_holding(r, xh_by.get(r["input_id"])), R, 8.4, MUTED, width=CW - 196 - 150)
        text(c, M + 90, y, pct(r.get("weight") or 0, 1), B, 8.8, NAVY, "right")
        text(c, M + 6, y, ils(r.get("value_ils")), R, 8.6, INK, "left")
        y -= 20
    c.showPage()

    # ------------------------------------------------------------ Page 2
    c.setFillColor(NAVY)
    c.rect(0, H - 46, W, 46, stroke=0, fill=1)
    c.setFillColor(CYAN)
    c.rect(0, H - 49, W, 3, stroke=0, fill=1)
    logo(c, M, H - 38, 28)
    text(c, RIGHT, H - 30, "השוואה, תרחישים ועלויות", B, 13, white)
    y = H - 82

    if closest:
        y = section(c, y, f"איך התיק שלך בהשוואה למודל {closest['name']} של IBI?")
        y = para(c, y, f"מבין מודלי ההשקעה של IBI, התיק שלך הכי קרוב למודל {closest['name']}"
                       f"{' – ' + closest['description'] if closest.get('description') else ''}. "
                       "כך נראית החלוקה שלך לעומת המודל:", 9.8, INK, leading=14.5)
        y -= 6
        y = compare_bars(c, y, p, closest)
        for s in comparison_sentences(p, closest):
            c.setFillColor(CYAN)
            c.circle(RIGHT - 3, y + 3, 2.2, stroke=0, fill=1)
            y = para(c, y, s, 9.5, INK, width=CW - 14, x_right=RIGHT - 10, leading=14)
        y -= 14

    y = section(c, y, "מה יכול לקרות לתיק שלך?", "תרחישים לדוגמה – לא תחזית")
    y -= 2
    scen = {s["id"]: s for s in rep["scenarios"]}
    chosen = [scen[i] for i in SCENARIO_ORDER if i in scen]
    maxabs = max((abs(s["pnl_ils"]) for s in chosen), default=1) or 1
    bar_zone = 130
    for s in chosen:
        title, story = PLAIN_SCENARIO.get(s["id"], (s["name"], ""))
        up = s["pnl_ils"] >= 0
        text(c, RIGHT, y, title, B, 10, INK)
        text(c, RIGHT, y - 13, story, R, 8.2, MUTED, width=CW - bar_zone - 140)
        verb = "לעלות" if up else "לרדת"
        text(c, M + bar_zone + 120, y, f"התיק עשוי {verb} בכ-", R, 8.5, MUTED, "right")
        text(c, M + bar_zone + 120, y - 14, f"{ils(abs(s['pnl_ils']))}  ({pct(abs(s['pnl_pct']), 1)})", B, 10.5,
             GAIN if up else LOSS, "right")
        bw = (bar_zone - 6) * abs(s["pnl_ils"]) / maxabs
        c.setFillColor(GAIN if up else LOSS)
        c.roundRect(M, y - 10, max(2, bw), 12, 3, stroke=0, fill=1)
        c.setStrokeColor(LINE)
        c.line(M, y - 22, RIGHT, y - 22)
        y -= 36
    y -= 6

    fee = p["metrics"].get("weighted_fee")
    y = section(c, y, "כמה זה עולה לך?")
    if fee is not None:
        cov = p["metrics"]["fee_coverage"]
        cost = p["metrics"]["annual_cost_ils"]
        if cov >= 99:
            msg = f"דמי הניהול בתיק מסתכמים בממוצע בכ-{fee:.2f}% בשנה – בערך {ils(cost)} בשנה על התיק שלך."
        else:
            msg = (f"עבור {cov:.0f}% מהתיק יש לנו נתוני עלויות: דמי הניהול שם הם בממוצע כ-{fee:.2f}% בשנה, "
                   f"בערך {ils(cost)} בשנה. את העלויות של שאר ההשקעות ישמח מנהל התיק לפרט.")
    else:
        msg = "אין לנו כרגע נתוני דמי ניהול לקרנות שבתיק. מנהל התיק ישמח לפרט את העלויות."
    y = para(c, y, msg, 9.8, INK, leading=14.5)
    y -= 10

    y = section(c, y, "מילון קצר")
    for term, expl in GLOSSARY:
        text(c, RIGHT, y, term, B, 9, NAVY)
        y = para(c, y, expl, 8.8, MUTED, width=CW - 110, x_right=RIGHT - 105, leading=12.5)
        y -= 3

    box_h = 64
    y = 44 + box_h if y - box_h > 44 else y - 6
    c.setFillColor(BG)
    c.roundRect(M, y - box_h, CW, box_h, 6, stroke=0, fill=1)
    yy = y - 15
    for ln in wrap(PLAIN_DISCLAIMER, R, 7.2, CW - 20)[:5]:
        text(c, RIGHT - 10, yy, ln, R, 7.2, MUTED)
        yy -= 10
    c.showPage()
    c.save()
    return buf.getvalue()
