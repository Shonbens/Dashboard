"""
Branded PDF reports for base models (A4, Hebrew RTL, vector graphics).

  build_models_pdf(models, book=False)  -> bytes
    models: list of model_analytics(..., full=True) dicts
    book=True adds a comparison cover page ("סולם המודלים") before the per-model pages.

Hebrew is laid out right-to-left with the Unicode bidi algorithm (python-bidi); Heebo (OFL) is embedded.
"""
from __future__ import annotations

import io
import re
import time
from pathlib import Path

from bidi.algorithm import get_display
from reportlab.graphics import renderPDF
from reportlab.lib.colors import Color, HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from svglib.svglib import svg2rlg

from stress import PRESETS

ASSETS = Path(__file__).parent / "assets"
W, H = A4
M = 36  # page margin
CW = W - 2 * M  # content width
RIGHT = W - M

# IBI brand + UI palette
NAVY = HexColor("#161932")
CYAN = HexColor("#00ADDC")
INK = HexColor("#20263A")
MUTED = HexColor("#687288")
FAINT = HexColor("#9AA1B4")
LINE = HexColor("#E2E6ED")
BG = HexColor("#F4F5F8")
GAIN = HexColor("#2A78D6")
LOSS = HexColor("#E34948")
AMBER = HexColor("#B45309")
SERIES = [HexColor(c) for c in ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")]
OTHER = HexColor("#a3a3a0")

ASSET_ORDER = [("מניות", SERIES[0]), ("אג״ח ממשלתי", SERIES[1]), ("אג״ח קונצרני", SERIES[2]),
               ("מזומן ופיקדונות", SERIES[3]), ("אחר", OTHER)]
GEO_ORDER = [("ישראל", SERIES[0]), ("ארה״ב", SERIES[1]), ("אירופה", SERIES[2]), ("אסיה ופסיפיק", SERIES[3]),
             ("שווקים מתעוררים", SERIES[4]), ("אחר", OTHER)]
DARK_INK = {"מזומן ופיקדונות", "אסיה ופסיפיק"}  # yellow segments get navy text
STATUS = {"approved": "מאושר", "draft": "טיוטה", "archived": "בארכיון"}
LISTING = {"IL": "ת״א", "US": "ארה״ב", "OTHER": "חו״ל"}
REGION = {"IL": "ישראל", "US": "ארה״ב", "EUROPE": "אירופה", "ASIA": "אסיה", "EM": "מתעוררים", "OTHER": "גלובלי"}
PRESET_DESC = {p["id"]: p["description"] for p in PRESETS}

DISCLAIMER = (
    "המידע במסמך זה הינו כללי בלבד ואינו מהווה ייעוץ השקעות, שיווק השקעות או תחליף לייעוץ המתחשב בנתונים ובצרכים "
    "המיוחדים של כל אדם. ניתוח החשיפות מבוסס על נתוני מאי״ה, Yahoo Finance וביזפורטל ועל הנחות מודל, ועשוי להיות "
    "לא מדויק. תרחישי הקיצון הם היפותטיים, מחושבים בקירוב ליניארי ואינם מהווים תחזית. ביצועי עבר אינם מעידים על ביצועים עתידיים."
)

_fonts_ready = False


def _fonts():
    global _fonts_ready
    if _fonts_ready:
        return
    for name in ("Regular", "Medium", "Bold", "ExtraBold"):
        pdfmetrics.registerFont(TTFont(f"Heebo-{name}", str(ASSETS / "fonts" / f"Heebo-{name}.ttf")))
    _fonts_ready = True


R, MD, B, XB = "Heebo-Regular", "Heebo-Medium", "Heebo-Bold", "Heebo-ExtraBold"


# --------------------------------------------------------------------------- #
#  Drawing primitives
# --------------------------------------------------------------------------- #
_HEB = re.compile(r"[֐-׿]")
_SIGN = re.compile(r"(?:(?<=\s)|^)([-+])(?=₪?\d)")


def vis(s) -> str:
    """Logical (typed) order -> visual order for LTR drawing.
    Pure numbers/English stay as typed; inside Hebrew, a leading +/- is pinned to its number with an LRM
    so '-10%' never renders as '10%-'."""
    s = str(s)
    if not _HEB.search(s):
        return s
    v = get_display(_SIGN.sub("‎\\1", s), base_dir="R")
    return v.replace("‎", "").replace("‏", "")


def fit(s: str, font: str, size: float, width: float) -> str:
    s = str(s or "")
    if stringWidth(s, font, size) <= width:
        return s
    while s and stringWidth(s + "…", font, size) > width:
        s = s[:-1]
    return s.rstrip() + "…"


def text(c, x, y, s, font=R, size=9, color=INK, align="right", width=None):
    s = fit(s, font, size, width) if width else str(s)
    c.setFont(font, size)
    c.setFillColor(color)
    v = vis(s)
    if align == "right":
        c.drawRightString(x, y, v)
    elif align == "center":
        c.drawCentredString(x, y, v)
    else:
        c.drawString(x, y, v)


def wrap(s: str, font: str, size: float, width: float) -> list[str]:
    """Greedy word wrap in logical order (each line is reordered separately when drawn)."""
    lines, cur = [], ""
    for word in str(s).split():
        trial = f"{cur} {word}".strip()
        if stringWidth(trial, font, size) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def pct(v, d=1, signed=False):
    if v is None:
        return "—"
    sign = "+" if signed and v > 0 else ""
    return f"{sign}{v:.{d}f}%"


def ils(v):
    if v is None:
        return "—"
    return f"₪{abs(v):,.0f}" if v >= 0 else f"-₪{abs(v):,.0f}"


def section(c, y, title, sub=None):
    c.setFillColor(CYAN)
    c.rect(RIGHT - 3, y - 2, 3, 13, stroke=0, fill=1)
    text(c, RIGHT - 9, y, title, B, 11.5, NAVY)
    if sub:
        text(c, RIGHT - 9 - stringWidth(title, B, 11.5) - 8, y + 0.5, sub, R, 8, MUTED)
    return y - 16


def stacked_bar(c, x_right, y, width, height, data: dict, order, labels=True):
    total = sum(max(0, data.get(k, 0)) for k, _ in order) or 1
    x = x_right
    gap = 1.2
    for k, col in order:
        v = max(0, data.get(k, 0))
        if v <= 0.05:
            continue
        w = width * v / total
        c.setFillColor(col)
        c.rect(x - w + gap / 2, y, max(0.5, w - gap), height, stroke=0, fill=1)
        if labels and w > 26:
            text(c, x - w / 2, y + height / 2 - 3, f"{v:.0f}%", B, 7.5, NAVY if k in DARK_INK else white, "center")
        x -= w


def legend(c, x_right, y, items: list[tuple[str, Color]], data: dict | None = None, size=7.5):
    x = x_right
    for k, col in items:
        if data is not None and not data.get(k):
            continue
        label = f"{k} {data[k]:.1f}%" if data is not None else k
        c.setFillColor(col)
        c.roundRect(x - 7, y - 0.5, 7, 7, 1.5, stroke=0, fill=1)
        text(c, x - 10, y, label, R, size, MUTED)
        x -= 10 + stringWidth(label, R, size) + 12


def logo(c, x, y, height):
    try:
        d = svg2rlg(str(ASSETS / "ibi-logo.svg"))
        s = height / d.height
        d.width, d.height = d.width * s, d.height * s
        d.scale(s, s)
        renderPDF.draw(d, c, x, y)
    except Exception:
        text(c, x, y + 4, "IBI", XB, height * 0.6, white, "left")


def exposure_label(xh: dict | None) -> str:
    if not xh:
        return "—"
    regions = sorted((xh.get("regions") or {}).items(), key=lambda kv: -kv[1])
    if regions:
        top, w = regions[0]
        total = sum(v for _, v in regions) or 1
        return REGION.get(top, top) if w / total >= 0.7 else "גלובלי"
    if (xh.get("gov_bonds", 0) + xh.get("corp_bonds", 0) + xh.get("cash", 0)) > 0:
        return "חו״ל" if (xh.get("fx_exposure") or 0) > 50 else "ישראל"
    return "—"


# --------------------------------------------------------------------------- #
#  Page furniture
# --------------------------------------------------------------------------- #
class NumberedCanvas(rl_canvas.Canvas):
    """Two-pass canvas so every footer can say 'page x of y'."""

    def __init__(self, *a, footer_title="", **kw):
        super().__init__(*a, **kw)
        self._saved = []
        self._footer_title = footer_title

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        n = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            self._footer(n)
            super().showPage()
        super().save()

    def _footer(self, total):
        self.setStrokeColor(LINE)
        self.setLineWidth(0.6)
        self.line(M, 30, RIGHT, 30)
        text(self, RIGHT, 18, f"IBI בית השקעות · {self._footer_title}", R, 7.5, FAINT)
        text(self, M, 18, f"עמוד {self._pageNumber} מתוך {total}", R, 7.5, FAINT, "left")
        text(self, W / 2, 18, time.strftime("הופק %d.%m.%Y %H:%M"), R, 7.5, FAINT, "center")


def header_band(c, eyebrow, title, subtitle, meta_right=None, meta_left=None):
    band = 104
    c.setFillColor(NAVY)
    c.rect(0, H - band, W, band, stroke=0, fill=1)
    c.setFillColor(CYAN)
    c.rect(0, H - band - 3, W, 3, stroke=0, fill=1)
    logo(c, M, H - 74, 44)
    text(c, RIGHT, H - 34, eyebrow, MD, 9, CYAN)
    text(c, RIGHT, H - 66, title, XB, 28, white)
    if subtitle:
        text(c, RIGHT, H - 86, subtitle, R, 9.5, HexColor("#C9CCDA"), width=CW - 140)
    y = H - band - 20
    if meta_right:
        text(c, RIGHT, y, meta_right, R, 8.5, MUTED)
    if meta_left:
        text(c, M, y, meta_left, R, 8.5, MUTED, "left")
    return y - 18


def draft_watermark(c):
    c.saveState()
    c.setFillColor(Color(0.89, 0.29, 0.28, alpha=0.07))
    c.translate(W / 2, H / 2)
    c.rotate(35)
    c.setFont(XB, 70)
    c.drawCentredString(0, 0, vis("טיוטה – לא מאושר"))
    c.restoreState()


def kpi_tiles(c, y, tiles):
    n = len(tiles)
    gap = 8
    w = (CW - gap * (n - 1)) / n
    h = 50
    x = RIGHT
    for label, value, sub, color in tiles:
        c.setFillColor(BG)
        c.roundRect(x - w, y - h, w, h, 6, stroke=0, fill=1)
        text(c, x - 9, y - 14, label, R, 7.5, MUTED, width=w - 14)
        text(c, x - 9, y - 33, value, B, 15, color or NAVY)
        if sub:
            text(c, x - 9, y - 44, sub, R, 6.8, FAINT, width=w - 14)
        x -= w + gap
    return y - h - 18


# --------------------------------------------------------------------------- #
#  Model pages
# --------------------------------------------------------------------------- #
def model_pages(c, m: dict, aum: float):
    rep = m["report"]
    mt = m["metrics"]
    xh_by_id = {h["input_id"]: h for h in rep["xray_holdings"]}
    worst = min(m["scenarios"], key=lambda s: s["pnl_pct"]) if m["scenarios"] else None
    priced_at = max((r.get("as_of") or 0) for r in rep["rows"]) if rep["rows"] else time.time()

    # ---------------- Page 1 ----------------
    if m["status"] == "draft":
        draft_watermark(c)
    eq_target = f" · יעד מניות {m['equity_target']:.0f}%" if m.get("equity_target") is not None else ""
    y = header_band(
        c, "דף מודל השקעה", f"מודל {m['name']}", m.get("description") or "",
        meta_right=f"גרסה {m['version']} · {STATUS.get(m['status'], m['status'])}{eq_target} · עודכן {time.strftime('%d.%m.%Y', time.localtime(m['updated_at']))}",
        meta_left=f"מחירים נכון ליום {time.strftime('%d.%m.%Y, %H:%M', time.localtime(priced_at))}",
    )
    fee = mt.get("weighted_fee")
    y = kpi_tiles(c, y, [
        ("מניות בפועל (לאחר שיקוף)", pct(mt["equity_weight"], 1),
         None if m.get("equity_drift") is None else f"סטייה מהיעד {pct(m['equity_drift'], 1, True)}", None),
        ("חשיפה למט״ח", pct(mt["fx_exposure"], 0), "לאחר שיקוף קרנות", None),
        ("מח״מ רכיב האג״ח", f"{mt['bond_duration']:.2f}" if mt.get("bond_duration") else "—", f"אג״ח {pct(mt['bond_weight'], 0)} מהמודל", None),
        ("דמי ניהול משוקללים", f"{fee:.2f}%" if fee is not None else "—",
         f"נתונים עבור {mt['fee_coverage']:.0f}% מהמודל" if fee is not None else "אין נתונים", None),
        ("הפסד בתרחיש הגרוע", pct(worst["pnl_pct"], 1, True) if worst else "—", worst["name"] if worst else None, LOSS),
    ])

    # Holdings table
    y = section(c, y, "הרכב המודל", f"{len(rep['rows'])} ניירות")
    cols = [  # (title, offset of the column's right edge from RIGHT)
        ("שם הנייר", 0), ("מספר נייר", 178), ("סוג נכס", 236), ("מסחר · חשיפה", 300), ("דמי ניהול", 378),
    ]
    weight_x0 = M  # weight column: value + bar in the remaining width on the left
    weight_w = CW - 430
    c.setFillColor(BG)
    c.rect(M, y - 5, CW, 17, stroke=0, fill=1)
    for title, off in cols:
        text(c, RIGHT - off - 4, y, title, MD, 7.5, MUTED)
    text(c, weight_x0 + weight_w, y, "משקל", MD, 7.5, MUTED)
    y -= 18
    rows = sorted(rep["rows"], key=lambda r: -(r.get("weight") or 0))
    maxw = max((r.get("weight") or 0) for r in rows) or 1
    row_h = 19
    for i, r in enumerate(rows):
        if y < 250:
            text(c, RIGHT - 4, y, f"ועוד {len(rows) - i} ניירות – ראו ייצוא אקסל", R, 7.5, MUTED)
            y -= row_h
            break
        if i % 2:
            c.setFillColor(HexColor("#FAFBFC"))
            c.rect(M, y - 6, CW, row_h, stroke=0, fill=1)
        xh = xh_by_id.get(r["input_id"])
        name = r["name"] if r.get("priced") else (r.get("file_name") or r["name"])
        text(c, RIGHT - 4, y, name, MD, 8.2, INK, width=170)
        text(c, RIGHT - 178 - 4, y, r["input_id"], R, 7.6, MUTED, width=52)
        text(c, RIGHT - 236 - 4, y, r.get("asset_class") or "—", R, 7.8, INK, width=60)
        text(c, RIGHT - 300 - 4, y, f"{LISTING.get(r.get('market'), '')} · {exposure_label(xh)}", R, 7.8, INK, width=74)
        f = (xh or {}).get("fee")
        text(c, RIGHT - 378 - 4, y, f"{f:.2f}%" if f is not None else "—", R, 7.8, INK if f is not None else FAINT)
        w = r.get("weight") or 0
        bar_w = (weight_w - 46) * w / maxw
        c.setFillColor(CYAN)
        c.roundRect(weight_x0 + weight_w - 4 - bar_w, y - 1, max(1, bar_w), 7, 2, stroke=0, fill=1)
        text(c, weight_x0 + 2, y, pct(w, 2), B, 8.2, NAVY, "left")
        y -= row_h
    c.setStrokeColor(LINE)
    c.line(M, y + 12, RIGHT, y + 12)
    total = sum((r.get("weight") or 0) for r in rows)
    text(c, RIGHT - 4, y, "סה״כ", B, 8.5, NAVY)
    text(c, weight_x0 + 2, y, pct(total, 2), B, 8.5, NAVY if abs(total - 100) < 0.01 else AMBER, "left")
    y -= 28

    def breakdown(y):
        # Two columns: sectors (right) and top underlying (left)
        col_w = (CW - 20) / 2
        top_y = y
        y = section(c, y, "חשיפה סקטוריאלית", "מניות, % מהמודל")
        sectors = list(rep["sectors"].items())[:9]
        smax = max((v for _, v in sectors), default=1) or 1
        for name, v in sectors:
            text(c, RIGHT, y, name, R, 8, INK, width=80)
            bw = (col_w - 130) * v / smax
            c.setFillColor(OTHER if name == "לא מסווג" else SERIES[0])
            c.roundRect(RIGHT - 88 - bw, y - 1.5, max(1, bw), 7, 2, stroke=0, fill=1)
            text(c, RIGHT - 92 - bw, y, pct(v, 1), MD, 7.8, INK)
            y -= 16
        left_right = M + col_w
        y2 = top_y
        c.setFillColor(CYAN)
        c.rect(left_right - 3, y2 - 2, 3, 13, stroke=0, fill=1)
        text(c, left_right - 9, y2, "נכסי הבסיס הגדולים", B, 11.5, NAVY)
        y2 -= 16
        text(c, left_right - 4, y2, "נכס", MD, 7.5, MUTED)
        text(c, M + 70, y2, "ישירה+עקיפה", MD, 7.5, MUTED, "right")
        text(c, M + 4, y2, "סה״כ", MD, 7.5, MUTED, "left")
        y2 -= 14
        for u in rep["top_underlying"][:10]:
            text(c, left_right - 4, y2, u["name"], R, 8, INK, width=col_w - 110)
            via = "ישירה" if u["indirect"] == 0 else ("דרך קרנות" if u["direct"] == 0 else "משולבת")
            text(c, M + 70, y2, via, R, 7.5, MUTED, "right")
            text(c, M + 4, y2, pct(u["total"], 1), B, 8, NAVY, "left")
            c.setStrokeColor(LINE)
            c.line(M, y2 - 5, left_right, y2 - 5)
            y2 -= 16
        y = min(y, y2) - 10
        return y

    # Look-through composition
    y = section(c, y, "פיזור לאחר שיקוף", "החשיפה בפועל לנכסי הבסיס, לאחר פירוק קרנות ותעודות סל")
    for label, data, order in (("סוגי נכסים", m["asset_classes"], ASSET_ORDER), ("גיאוגרפיה", m["geography"], GEO_ORDER)):
        text(c, RIGHT, y, label, MD, 8.5, INK)
        stacked_bar(c, RIGHT - 70, y - 4, CW - 70, 15, data, order)
        legend(c, RIGHT - 70, y - 20, order, data)
        y -= 40
    n_rows = min(10, max(len(rep["top_underlying"]), len(list(rep["sectors"].items())[:9])))
    breakdown_on_p1 = y - (40 + 16 * n_rows) > 44
    if breakdown_on_p1:
        y = breakdown(y - 6)
    c.showPage()

    # ---------------- Page 2 ----------------
    if m["status"] == "draft":
        draft_watermark(c)
    c.setFillColor(NAVY)
    c.rect(0, H - 46, W, 46, stroke=0, fill=1)
    c.setFillColor(CYAN)
    c.rect(0, H - 49, W, 3, stroke=0, fill=1)
    logo(c, M, H - 38, 28)
    text(c, RIGHT, H - 30, f"מודל {m['name']} · סיכונים ותרחישים", B, 13, white)
    y = H - 80

    # Stress scenarios
    y = section(c, y, "מבחני קיצון", f"השפעה משוערת על תיק של {ils(aum)}")
    scen = rep["scenarios"]
    maxabs = max((abs(s["pnl_pct"]) for s in scen), default=1) or 1
    bar_zone_w = 150
    center = M + bar_zone_w / 2
    for s in scen:
        text(c, RIGHT, y, s["name"], B, 8.8, INK, width=150)
        text(c, RIGHT, y - 11, PRESET_DESC.get(s["id"], ""), R, 7, MUTED, width=230)
        text(c, RIGHT - 250, y - 4, pct(s["pnl_pct"], 1, True), B, 10, GAIN if s["pnl_pct"] >= 0 else LOSS, "right")
        text(c, RIGHT - 312, y - 4, ils(s["pnl_ils"]), R, 8.5, INK, "right")
        c.setStrokeColor(LINE)
        c.line(center, y - 10, center, y + 8)
        bw = (bar_zone_w / 2 - 4) * abs(s["pnl_pct"]) / maxabs
        c.setFillColor(GAIN if s["pnl_pct"] >= 0 else LOSS)
        if s["pnl_pct"] >= 0:
            c.roundRect(center, y - 4, bw, 9, 2, stroke=0, fill=1)
        else:
            c.roundRect(center - bw, y - 4, bw, 9, 2, stroke=0, fill=1)
        c.setStrokeColor(LINE)
        c.line(M, y - 17, RIGHT, y - 17)
        y -= 30
    y -= 4

    # Sensitivities
    y = section(c, y, "רגישויות", "שינוי בשווי התיק לזעזוע בודד")
    sens = m["sensitivities"]
    per_row = 3
    gap = 8
    tw = (CW - gap * (per_row - 1)) / per_row
    for i, s in enumerate(sens):
        col, row = i % per_row, i // per_row
        x = RIGHT - col * (tw + gap)
        yy = y - row * 36
        c.setFillColor(BG)
        c.roundRect(x - tw, yy - 26, tw, 30, 5, stroke=0, fill=1)
        text(c, x - 8, yy - 8, s["label"], R, 7.8, MUTED)
        text(c, x - tw + 8, yy - 12, f"{pct(s['pnl_pct'], 2, True)}   {ils(s['pnl_ils'])}", B, 9, GAIN if s["pnl_ils"] >= 0 else LOSS, "left")
    y -= 36 * ((len(sens) + per_row - 1) // per_row) + 12
    if not breakdown_on_p1:
        y = breakdown(y)


    # Methodology + disclaimer
    box_h = 92
    y = 44 + box_h if y - box_h > 44 else max(y, 40 + box_h)  # anchor to the page bottom when there is room
    c.setFillColor(BG)
    c.roundRect(M, y - box_h, CW, box_h, 6, stroke=0, fill=1)
    text(c, RIGHT - 10, y - 15, "מתודולוגיה וגילוי נאות", B, 8.5, NAVY)
    lines = wrap(
        "החשיפות מחושבות בשיקוף (Look-Through): קרנות נאמנות לפי דיווחי מאי״ה, תעודות סל לפי המדד שהן עוקבות אחריו. "
        "מבחני הקיצון מחושבים בקירוב ליניארי – מניות לפי חשיפה גיאוגרפית, אג״ח לפי מח״מ, מט״ח לפי שיעור החשיפה. "
        + DISCLAIMER, R, 7.1, CW - 20)
    yy = y - 28
    for ln in lines[:7]:
        text(c, RIGHT - 10, yy, ln, R, 7.1, MUTED)
        yy -= 9.5
    c.showPage()


# --------------------------------------------------------------------------- #
#  Comparison cover (book)
# --------------------------------------------------------------------------- #
def cover_page(c, models: list[dict], aum: float):
    y = header_band(c, "מודלי הבית", "סולם המודלים", f"{len(models)} מודלים, מהסולידי למנייתי · ניתוח לאחר שיקוף קרנות",
                    meta_right=f"ניתוח לפי תיק של {ils(aum)}", meta_left=time.strftime("%d.%m.%Y"))
    n = len(models)
    label_w = 120
    col_w = (CW - label_w) / max(n, 1)

    def col_x(i):  # center x of model column i (RTL: first model on the right)
        return RIGHT - label_w - col_w * i - col_w / 2

    # Header row with model names
    c.setFillColor(BG)
    c.rect(M, y - 8, CW, 24, stroke=0, fill=1)
    text(c, RIGHT - 6, y, "מדד", MD, 8, MUTED)
    for i, m in enumerate(models):
        text(c, col_x(i), y - 1, m["name"], XB, 12, NAVY, "center")
    y -= 26

    rows = [
        ("סטטוס", lambda m: STATUS.get(m["status"], m["status"])),
        ("מניות בפועל", lambda m: pct(m["metrics"]["equity_weight"], 1)),
        ("חשיפה לישראל", lambda m: pct(m["geography"].get("ישראל", 0), 1)),
        ("חשיפה למט״ח", lambda m: pct(m["metrics"]["fx_exposure"], 0)),
        ("מח״מ אג״ח", lambda m: f"{m['metrics']['bond_duration']:.2f}" if m["metrics"].get("bond_duration") else "—"),
        ("דמי ניהול משוקללים", lambda m: f"{m['metrics']['weighted_fee']:.2f}%" if m["metrics"].get("weighted_fee") is not None else "—"),
        ("מספר ניירות", lambda m: str(m["holdings_count"])),
    ]
    for label, f in rows:
        text(c, RIGHT - 6, y, label, R, 8.5, INK)
        for i, m in enumerate(models):
            text(c, col_x(i), y, f(m), MD, 9, INK, "center")
        c.setStrokeColor(LINE)
        c.line(M, y - 6, RIGHT, y - 6)
        y -= 19
    y -= 14

    # Composition bars
    y = section(c, y, "הרכב לאחר שיקוף", "סוגי נכסים")
    for m in models:
        text(c, RIGHT, y, m["name"], B, 9, NAVY)
        stacked_bar(c, RIGHT - 50, y - 4, CW - 50, 14, m["asset_classes"], ASSET_ORDER)
        y -= 21
    legend(c, RIGHT - 50, y + 2, ASSET_ORDER)
    y -= 26

    # Scenario heatmap
    y = section(c, y, "מבחני קיצון לפי מודל", "תרחישים היפותטיים · כחול = רווח, אדום = הפסד")
    scen_names = [s["name"] for s in models[0]["scenarios"]] if models else []
    maxabs = max((abs(s["pnl_pct"]) for m in models for s in m["scenarios"]), default=1) or 1
    for j, name in enumerate(scen_names):
        text(c, RIGHT - 6, y, name, R, 8.5, INK, width=label_w - 10)
        for i, m in enumerate(models):
            v = m["scenarios"][j]["pnl_pct"]
            a = min(1, abs(v) / maxabs) * 0.55 + 0.06
            base = (0.165, 0.47, 0.84) if v >= 0 else (0.89, 0.286, 0.282)
            c.setFillColor(Color(*base, alpha=a))
            c.roundRect(col_x(i) - col_w / 2 + 3, y - 6, col_w - 6, 18, 3, stroke=0, fill=1)
            text(c, col_x(i), y, pct(v, 1, True), B, 8.8, INK, "center")
        y -= 22
    y -= 10
    lines = wrap(DISCLAIMER, R, 7, CW)
    for ln in lines[:4]:
        text(c, RIGHT, y, ln, R, 7, FAINT)
        y -= 9
    c.showPage()


def build_models_pdf(models: list[dict], aum: float, book: bool = False, title: str = "") -> bytes:
    _fonts()
    buf = io.BytesIO()
    footer = title or (f"דף מודל {models[0]['name']}" if len(models) == 1 else "סולם המודלים")
    c = NumberedCanvas(buf, pagesize=A4, footer_title=footer)
    c.setTitle(footer)
    c.setAuthor("IBI בית השקעות – מערכת מודלי השקעה")
    if book:
        cover_page(c, models, aum)
    for m in models:
        model_pages(c, m, aum)
    c.save()
    return buf.getvalue()
