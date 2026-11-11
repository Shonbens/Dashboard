"""
Potential-client portfolio analysis ("ניתוח תיק פוטנציאלי").

A portfolio held at another investment house is uploaded, looked-through (Maya / Yahoo / X-Ray) and checked
against the managers' insight rules ("Report Insights.xlsx"):

  each rule = metric + range [min, max] + direction
     ABOVE -> the insight fires when the metric is above the max
     BELOW -> the insight fires when the metric is below the min
  RowType COND rows sharing a RuleID are AND-ed; the RowType INSIGHT row of that RuleID holds the text.
  "XX" / "YY" in the text are replaced with the portfolio's actual numbers.

The rules live in data/insights_rules.json and can be replaced by uploading a workbook in the same layout.
"""
from __future__ import annotations

import io
import json
import re
import time
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

RULES_PATH = Path(__file__).parent / "data" / "insights_rules.json"

# Metric keys -> label shown in the report and how the value is formatted
METRICS = {
    "Israel_Equity": ("חשיפה למניות ישראל מסך המניות", "pct"),
    "FX_Exposure": ("חשיפה למט״ח מכלל התיק", "pct"),
    "Managed_Funds": ("קרנות נאמנות ותעודות סל מנוהלות מסך התיק", "pct"),
    "Single_Security": ("משקל הנייר הישיר הגדול בתיק", "pct"),
    "Shekel_Bonds": ("אג״ח שקלי מסך החוב השקלי + הצמוד", "pct"),
    "Gov_Bonds": ("אג״ח ממשלתי מסך החוב הממשלתי + הקונצרני", "pct"),
    "Low_Rated": ("אג״ח בדירוג נמוך / ללא דירוג מסך הקונצרני", "pct"),
    "Duration": ("מח״מ תיק החוב", "years"),
    "Funds_Fee_Avg": ("דמי ניהול ממוצעים בקרנות ובתעודות הסל", "pct2"),
    "Funds_ETF_Share": ("קרנות ותעודות סל מסך התיק", "pct"),
    "Equity_Total": ("חשיפה כוללת למניות מסך התיק", "pct"),
    "Holdings_Count": ("מספר ניירות בתיק", "int"),
}
TITLES = {
    "Israel_Equity": "פילוח אפיק המניות", "FX_Exposure": "חשיפה למט״ח", "Managed_Funds": "קרנות נאמנות מנוהלות",
    "Single_Security": "ריכוזיות בנייר בודד", "Shekel_Bonds": "שקלי מול צמוד", "Gov_Bonds": "ממשלתי מול קונצרני",
    "Low_Rated": "סיכון אשראי", "Duration": "מח״מ תיק החוב", "Funds_Fee_Avg": "דמי ניהול בקרנות ובתעודות סל",
    "Funds_ETF_Share": "דמי ניהול בקרנות ובתעודות סל", "Equity_Total": "חשיפה מנייתית", "Holdings_Count": "מספר הניירות בתיק",
}

# Transcription of the managers' "Report Insights.xlsx" (sheet "Insights")
DEFAULT_RULES = [
    {"id": "R001", "type": "SINGLE", "metric": "Israel_Equity", "name": 'סה"כ חשיפה למניות ישראל מסך המניות', "min": 0.5, "max": 0.6, "dir": "ABOVE",
     "text": "פילוח אפיק מניות-  מניתוח התיק עולה כי החשיפה למניות ישראל מסך המניות עומדת על XX. חשיפה זו גבוהה להערכתנו. על פי דעתנו המקצועית יש לשמור על איזון ברכיב המניות בין החשיפה המקומי לשווקים בעולם. אנו ממליצים לצמצם חשיפה למניות בישראל ולהגדיל מנגד את החשיפה למניות גלובליות."},
    {"id": "R002", "type": "SINGLE", "metric": "Israel_Equity", "name": 'סה"כ חשיפה למניות ישראל מסך המניות', "min": 0.5, "max": 0.6, "dir": "BELOW",
     "text": "פילוח אפיק מניות- מניתוח התיק עולה כי החשיפה למניות ישראל מסך המניות עומדת על XX. חשיפה זו נמוכה להערכתנו. על פי דעתנו המקצועית יש לשמור על איזון ברכיב המניות בין החשיפה המקומי לשווקים בעולם, אנו ממליצים להגדיל חשיפה למניות בישראל ולצמצם מנגד את החשיפה למניות גלובליות."},
    {"id": "R003", "type": "SINGLE", "metric": "FX_Exposure", "name": 'חשיפה למט"ח- אחוז מכלל התיק', "min": 0.1, "max": 0.2, "dir": "ABOVE",
     "text": 'מט"ח - מניתוח התיק עולה כי החשיפה למט"ח בתיק עומדת על XX. חשיפה זו גבוהה להערכתנו. על פי דעתנו המקצועית קיימים מספר לא מבוטל של משתנים שתומכים בהתחזקות השקל בעתיד הנראה לעין. אנו ממליצים לצמצם חשיפה למרכיב המט"ח בתיק, ומנגד להגדיל חשיפה לשקלים. ניתן לבצע זאת גם ע"י רכישת קרנות עוקבות מדד על מדדי מניות/אג"ח בחו"ל אשר מנטרלות את השפעת המט"ח באמצעות גידור.'},
    {"id": "R004", "type": "SINGLE", "metric": "FX_Exposure", "name": 'חשיפה למט"ח- אחוז מכלל התיק', "min": 0.1, "max": 0.2, "dir": "BELOW",
     "text": 'מניתוח התיק עולה כי החשיפה למט"ח בתיק עומדת על XX. חשיפה זו נמוכה להערכתנו.\nעל פי דעתנו המקצועית יש מקום ליצר פיזור מטבעי בכדי להקטין את התלות במטבע ובמשק המקומי.אנו ממליצים להגדיל חשיפה למרכיב המט"ח בתיק ומנגד להקטין חשיפה לשקלים. ניתן לבצע זאת ע"י רכישת קרנות עוקבות מדד על מדדי מניות/אג"ח בחו"ל אשר חשופות למט"ח.'},
    {"id": "R005", "type": "SINGLE", "metric": "Managed_Funds", "name": "אחוז חשיפה לקרנות נאמנות ותעודות סל מנוהלות מסך הנכסים בתיק", "min": 0, "max": 0.5, "dir": "ABOVE",
     "text": "מניתוח התיק עולה כי סך האחזקה בקרנות נאמנות מנוהלות עולה על XX מסך התיק. שימוש בקרנות נאמנות מייצר פיזור השקעות וניהול סיכונים נכון לטעמנו, אך מנגד עשוי לייצר עלויות גבוהות ללקוח ומעלה את דמי הניהול האפקטיבים של הלקוח.\nמבדיקה שערכנו דמי הניהול האפקטיבים  בתיק עומדים על YY. על פי דעתנו המקצועית יש מקום להקטין את החשיפה לקרנות מנוהלות ומנגד לשלב אחזקה בניירות ישירים או בקרנות מחקות אשר דמי הניהול בהם נמוכים יותר."},
    {"id": "R006", "type": "SINGLE", "metric": "Single_Security", "name": 'מגבלה לגבי נייר ישיר (מניה או אג"ח)', "min": 0, "max": 0.05, "dir": "ABOVE",
     "text": 'מניתוח סך הנכסים עולה כי קיימים בתיק XX ניירות ישירים (מניה או אג"ח) המהווים כל אחד מעל 5% מסך הנכסים.פיזור השקעות נכון בראייתנו בתיק מנוהל חייב להגביל אחזקה בנייר בודד כך שלא תיווצר תלות גבוהה מדי בחברה ספציפית.  על פי דעתנו המקצועית יש לצמצם חשיפה בניירות אלו ומנגד להגדיל את פיזור ההשקעות בניירות נוספים.'},
    {"id": "R007", "type": "SINGLE", "metric": "Shekel_Bonds", "name": 'הטייה לאג"ח שקלי מסך החוב השקלי+ צמוד', "min": 0.52, "max": 0.65, "dir": "BELOW",
     "text": "מניתוח התיק עולה כי סך אגרות החוב הצמודות בתיק גבוה ועומד על XX. לאורך השנים מנסיוננו המקצועי מרכיב אגרות החוב שאינן צמודות השיג ביצועי יתר על הרכיב הצמוד בשל התמתנות האינפלציה לאורך השנים במדינת ישראל. אנו חושבים כי יש מקום להקטין את הרכיב הצמוד בתיק על חשבון הרכיב השקלי."},
    {"id": "R008", "type": "SINGLE", "metric": "Shekel_Bonds", "name": 'הטייה לאג"ח שקלי מסך החוב השקלי+ צמוד', "min": 0.52, "max": 0.65, "dir": "ABOVE",
     "text": "מניתוח התיק עולה כי סך אגרות החוב השקליות בתיק עומד על XX. אנו חושבים כי חשוב לשמור בתיק גם על מרכיב צמוד מדד בהיקף גבוה יותר כהגנה מפני עליית האינפלציה ושמירה על ערך הכסף. על כן לדעתנו המקצועית יש מקום להגדיל את המרכיב הצמוד בתיק על חשבון אגרות החוב השקליות."},
    {"id": "R009", "type": "SINGLE", "metric": "Gov_Bonds", "name": 'חשיפה לאג"ח ממשלתי מסך החוב הממשלתי+ קונצרני', "min": 0.2, "max": 0.3, "dir": "ABOVE",
     "text": 'מניתוח של התיק עולה כי קיימת חשיפה של XX לאגרות חוב ממשלתיות מסך אגרות החוב. אנו סבורים כי בכדי לייצר תשואה שוטפת גבוהה יש מקום להסיט את החשיפה מאגרות חוב ממשלתית לאגרות חוב קונצרניות בדירוגים גבוהים, מבלי להגדיל את רמת הסיכון מהותי. על כן אנו סבורים שיש לשלב בתיק יותר אג"ח קונצרני על חשבון ממשלתי'},
    {"id": "R010", "type": "SINGLE", "metric": "Gov_Bonds", "name": 'חשיפה לאג"ח ממשלתי מסך החוב הממשלתי+ קונצרני', "min": 0.2, "max": 0.3, "dir": "BELOW",
     "text": 'מניתוח של התיק עולה כי קיימת חשיפה של XX לאגרות חוב קונצרני מסך אגרות החוב.\nאנו סבורים כי איזון נכון של התיק צריך לשלב אחוז גבוה יותר של אגרות חוב ממשלתיות אשר יהוו את העוגן בתיק ועשויים להיפגע פחות בעתות משבר. על כן אנו סבורים כי יש מקום להקטין את החשיפה לאג"ח קונצרני על חשבון אג"ח ממשלתי.'},
    {"id": "R011", "type": "SINGLE", "metric": "Low_Rated", "name": 'סך החשיפה באג"ח ללא דירוג, אג"ח מתחת לדירוג השקעה ואג"ח בין BBB ומטה', "min": 0, "max": 0.3, "dir": "ABOVE",
     "text": "מניתוח התיק עולה כי החשיפה לאגרות חוב קונצרניות בדירוגים נמוכים או לאגרות ללא דירוג עומדת על XX מסך החוב הקונצרני.  להערכתנו חשיפה זו גבוהה מדי בשל רמת הסיכון בסביבת דירוגים אלו. על כן יש מקום לצמצם את החשיפה לאגרות חוב בדירוגים נמוכים ."},
    {"id": "R012", "type": "SINGLE", "metric": "Duration", "name": 'מח"מ תיק החוב', "min": 3.5, "max": 4.5, "dir": "ABOVE",
     "text": 'מניתוח עולה עולה כי מח"מ תיק החוב עומד על XX.  להערכנו מח"מ זה ארוך מדי בשל התנודתיות הקיימת באגרות חוב ארוכות במח"מ זה. אנו חושבים כי יש מקום לקצר את מח"מ התיק בכדי להקטין את התנודתיות בתיק.'},
    {"id": "R013", "type": "SINGLE", "metric": "Duration", "name": 'מח"מ תיק החוב', "min": 3.5, "max": 4.5, "dir": "BELOW",
     "text": 'מניתוח עולה כי המח"מ החוב עומד על XX.  להערכתנו יש מקום לבצע הארכה של מח"מ בתיק בכדי לנסות לייצר רווחי הון עודפים בנוסף לתשואה השוטפת'},
    {"id": "R_AND_01", "type": "AND", "name": "דמי ניהול ממוצעים+ אחוז תעודות הסל והקרנות בתיק",
     "conditions": [{"metric": "Funds_Fee_Avg", "min": 0, "max": 0.008, "dir": "ABOVE"},
                    {"metric": "Funds_ETF_Share", "min": 0, "max": 0.5, "dir": "ABOVE"}],
     "text": "מניתוח התיק עולה כי קיימת בתיק חשיפה של XX לקרנות ותעודות סל מסך התיק.\nבניירות אלו דמי הניהול הממוצעים עומדים על YY . דמי ניהול אלו להערכתנו גבוהים מדי, אנו חושבים כי יש מקום לצמצם את החשיפה לקרנות אלו ובכך להוזיל דמי הניהול בתיק.\nבאמצעות פעולה אנו סבורים כי תשואת התיק עשויה להשתפר."},
    {"id": "R017", "type": "SINGLE", "metric": "Equity_Total", "name": "חשיפה כללית למניות מסך התיק", "min": 0.15, "max": 1, "dir": "BELOW",
     "text": "אנו סבורים כי החשיפה המנייתית בתיק שעומדת על XX הינה נמוכה. לאורך שנים רכיב המניות מייצר תשואה עודפת על פני מרכיבי השקעה אחרים. להערכתנו שילוב של רכיב מנייתית גבוה יותר עשוי לתרום לתשואת התיק ואף לאזן את סך ההשקעות בתיק. על כן אנו סבורים כי יש לשקול להגדיל ולו במעט את המרכיב המנייתי מסך התיק."},
    {"id": "R018", "type": "SINGLE", "metric": "Equity_Total", "name": "חשיפה כללית למניות מסך התיק", "min": 0, "max": 0.7, "dir": "ABOVE",
     "text": "מניתוח התיק עולה כי קיימת חשיפה כוללת למניות בהיקף של XX מסך התיק. מרכיב מנייתי המהווה משקל משמעותי מסך הנכסים מייצר תנודתיות גבוהה ומגדיל את רמת הסיכון בצורה משמעותית.  אנו חושבים כי  חשוב לבחון התאמת הסיכון לצרכי הלקוח, במיוחד בימים אלו. רצוי לשקול הקטנה של רכיב המניות ומעבר  לאגרות חוב אשר מייצרות שוטפת עם תנודתיות נמוכה יותר, ובכך לאזן יותר את הרכב התיק."},
    {"id": "R019", "type": "SINGLE", "metric": "Holdings_Count", "name": "תובנה כללית על התיק", "min": 0, "max": 50, "dir": "ABOVE",
     "text": "מניתוח התיק עולה כי קיימים בתיק מעל XX ניירות ערך. החזקה מרובה של ניירות בתיק לעיתים מייצרת פיזור יתר אשר חוטא למטרה של הורדת הסיכון ומסרבל את יכולת המעקב אחרי התיק. אנו סבורים כי יש לבצע טיוב ניירות בתיק ולהתכנס לכמות ניירות נמוכה יותר. להערכתנו ניתן לעשות זאת באופן שישמור ואף יגדיל את הפיזור בתיק."},
]

# Identify the metric of a rule from its "שם הנתון" when the MetricKey column is empty
NAME_TO_METRIC = [
    ("מניות ישראל", "Israel_Equity"), ('מט"ח', "FX_Exposure"), ("מנוהלות", "Managed_Funds"), ("נייר ישיר", "Single_Security"),
    ("שקלי", "Shekel_Bonds"), ("ממשלתי", "Gov_Bonds"), ("דירוג", "Low_Rated"), ('מח"מ', "Duration"),
    ("חשיפה כללית למניות", "Equity_Total"), ("תובנה כללית", "Holdings_Count"),
]


# --------------------------------------------------------------------------- #
#  Rules storage / import / export
# --------------------------------------------------------------------------- #
def load_rules() -> dict:
    if RULES_PATH.exists():
        try:
            return json.loads(RULES_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"rules": DEFAULT_RULES, "updated_at": None, "updated_by": "ברירת מחדל (Report Insights.xlsx)", "source": "Report Insights.xlsx"}


def save_rules(rules: list[dict], user: str, source: str) -> dict:
    doc = {"rules": rules, "updated_at": time.time(), "updated_by": user, "source": source}
    RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    RULES_PATH.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return doc


def validate_rules(rules: list[dict]) -> list[str]:
    """Problems that would stop a rule set edited on the site from being saved."""
    errs, ids = [], set()
    for i, r in enumerate(rules, 1):
        tag = r.get("id") or f"כלל {i}"
        if not r.get("id"):
            errs.append(f"{tag}: חסר מזהה")
        elif r["id"] in ids:
            errs.append(f"{tag}: המזהה מופיע פעמיים")
        ids.add(r.get("id"))
        if not str(r.get("text") or "").strip():
            errs.append(f"{tag}: חסר ניסוח להמלצה")
        conds = r.get("conditions", []) if r.get("type") == "AND" else [r]
        if r.get("type") == "AND" and len(conds) < 2:
            errs.append(f"{tag}: כלל משולב צריך לפחות שני תנאים")
        for c in conds:
            if c.get("metric") not in METRICS:
                errs.append(f"{tag}: נתון לא מוכר ({c.get('metric')})")
            if c.get("dir") not in ("ABOVE", "BELOW"):
                errs.append(f"{tag}: כיוון לא תקין")
            bound = c.get("max") if c.get("dir") == "ABOVE" else c.get("min")
            if not isinstance(bound, (int, float)):
                errs.append(f"{tag}: חסר סף")
    return errs


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "").replace("״", '"').replace("׳", "'")).strip()


def _metric_of(name: str, key: str | None) -> str | None:
    if key and key in METRICS:
        return key
    n = _norm(name)
    for k, m in NAME_TO_METRIC:
        if k in n:
            return m
    return None


def parse_rules_workbook(content: bytes) -> tuple[list[dict], list[str]]:
    """Read a workbook in the "Report Insights" layout into rules. Returns (rules, warnings)."""
    ws = load_workbook(io.BytesIO(content), data_only=True).worksheets[0]
    header = {_norm(c.value): c.column for c in ws[1] if c.value}
    need = {"שם הנתון", "ניסוח התובנה"}
    if not need.issubset(header):
        raise ValueError("הקובץ אינו במבנה של תבנית התובנות (חסרות העמודות ״שם הנתון״ / ״ניסוח התובנה״)")
    col = lambda name: header.get(name)  # noqa: E731
    c_min, c_max, c_dir = col("טווח מינימום לבדיקה"), col("טווח מקסימום לבדיקה"), col("ערך מעל/מתחת")
    c_rid, c_type, c_cond, c_key = col("RuleID"), col("RowType"), col("ConditionID"), col("MetricKey")
    c_title, c_active = col("כותרת"), col("פעיל")  # optional columns (added when rules are edited on the site)

    def extras(r):
        out = {}
        if c_title and ws.cell(r, c_title).value:
            out["title"] = _norm(ws.cell(r, c_title).value)
        if c_active and _norm(ws.cell(r, c_active).value) in ("לא", "no", "NO", "0", "FALSE", "False"):
            out["active"] = False
        return out
    rules, groups, warnings = [], {}, []
    order: list = []  # keep the sheet's order (combined rules stay where they are, so numbering in reports doesn't move)
    for r in range(2, ws.max_row + 1):
        name = ws.cell(r, header["שם הנתון"]).value
        text = ws.cell(r, header["ניסוח התובנה"]).value
        if not name and not text:
            continue
        rid = _norm(ws.cell(r, c_rid).value) if c_rid else f"ROW{r}"
        rtype = (_norm(ws.cell(r, c_type).value) if c_type else "SINGLE").upper() or "SINGLE"
        lo = ws.cell(r, c_min).value if c_min else None
        hi = ws.cell(r, c_max).value if c_max else None
        direction = _norm(ws.cell(r, c_dir).value).upper() if c_dir else ""
        key = _norm(ws.cell(r, c_key).value) if c_key and ws.cell(r, c_key).value else None
        if rtype == "COND":
            metric = key if key in METRICS else ("Funds_Fee_Avg" if str(ws.cell(r, c_cond).value) == "1" else "Funds_ETF_Share") \
                if "דמי ניהול" in _norm(name) else _metric_of(name, key)
            if rid not in groups:
                order.append(("g", rid))
            g = groups.setdefault(rid, {"id": rid, "type": "AND", "name": _norm(name), "conditions": [], "text": ""})
            g["conditions"].append({"metric": metric, "min": lo, "max": hi, "dir": direction})
            continue
        if rtype == "INSIGHT":
            if rid not in groups:
                order.append(("g", rid))
            g = groups.setdefault(rid, {"id": rid, "type": "AND", "name": _norm(name), "conditions": [], "text": ""})
            g["text"] = str(text or "").strip()
            g.update(extras(r))
            continue
        metric = _metric_of(name, key)
        if not metric:
            warnings.append(f"שורה {r}: לא זוהה הנתון ״{_norm(name)}״ – הכלל דולג")
            continue
        if direction not in ("ABOVE", "BELOW"):
            warnings.append(f"שורה {r}: ערך מעל/מתחת לא חוקי – הכלל דולג")
            continue
        if rid in ("", "X") or any(x["id"] == rid for x in rules):
            new = f"ROW{r}"
            warnings.append(f"שורה {r}: RuleID ״{rid or 'ריק'}״ לא ייחודי – הוחלף ב-{new}")
            rid = new
        rule = {"id": rid, "type": "SINGLE", "metric": metric, "name": _norm(name), "min": lo, "max": hi, "dir": direction,
                "text": str(text or "").strip(), **extras(r)}
        rules.append(rule)
        order.append(("r", rule))
    out = []
    for kind, x in order:
        if kind == "r":
            out.append(x)
            continue
        g = groups[x]
        if g["conditions"] and g["text"]:
            out.append(g)
        else:
            warnings.append(f"כלל מצטבר {g['id']} חסר תנאים או ניסוח – דולג")
    return out, warnings


def export_rules_workbook(rules: list[dict]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Insights"
    ws.sheet_view.rightToLeft = True
    head = ["שם הנתון", "טווח מינימום לבדיקה", "טווח מקסימום לבדיקה", "ערך מעל/מתחת", "ניסוח התובנה", "RuleID", "RowType", "ConditionID", "MetricKey",
            "כותרת", "פעיל"]
    ws.append(head)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="161932")
    for r in rules:
        if r["type"] == "AND":
            for i, cond in enumerate(r["conditions"], 1):
                ws.append([r.get("name"), cond["min"], cond["max"], cond["dir"], f"תנאי מצטבר {i}", r["id"], "COND", i, cond["metric"]])
            ws.append([r.get("name"), None, None, None, r["text"], r["id"], "INSIGHT", None, None, r.get("title") or None,
                       "לא" if r.get("active") is False else "כן"])
        else:
            ws.append([r.get("name"), r["min"], r["max"], r["dir"], r["text"], r["id"], "SINGLE", 1, r["metric"], r.get("title") or None,
                       "לא" if r.get("active") is False else "כן"])
    for col, w in zip("ABCDEFGHIJK", (42, 12, 12, 10, 110, 11, 9, 11, 16, 24, 7)):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=2):
        row[4].alignment = Alignment(wrap_text=True, vertical="top")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
#  Metrics
# --------------------------------------------------------------------------- #
_RATING_ORDER = ["AAA", "AA", "A", "BBB", "BB", "B", "CCC", "CC", "C", "D"]
_MIDROOG = {"AAA": "AAA", "AA": "AA", "A": "A", "BAA": "BBB", "BA": "BB", "B": "B", "CAA": "CCC", "CA": "CC", "C": "C"}


def rating_rank(text: str | None) -> int | None:
    """'AA-' / 'ilAA' / 'Aa2.il' / 'BBB+' -> index in _RATING_ORDER (higher = riskier). None when unknown."""
    if not text:
        return None
    t = re.sub(r"(?i)\.?il|\(.*?\)|[+\-\d\s]", "", str(text)).upper()
    if t in _RATING_ORDER:
        return _RATING_ORDER.index(t)
    if t in _MIDROOG:
        return _RATING_ORDER.index(_MIDROOG[t])
    return None


def compute(holdings: list[dict], data: dict[str, dict], xray: dict, cash: float = 0.0) -> dict:
    """holdings: [{id, name, weight (%), fee?}] ; data: secdata per id ; xray: xray_engine.analyze output.
    cash: % held in cash outside the holdings list (allocation models keep the remainder in cash)."""
    cash = max(0.0, cash or 0.0)
    total_w = (sum(max(0.0, h.get("weight") or 0) for h in holdings) + cash) or 1.0
    eq_il = eq_f = 0.0
    linked = shekel = 0.0
    gov = corp = 0.0
    dur_num = dur_den = 0.0
    low = corp_rated = 0.0
    managed = funds_etf = 0.0
    fee_num = fee_cov = 0.0           # whole portfolio, direct securities count as 0 cost
    ffee_num = ffee_cov = 0.0         # funds + ETFs only
    big_direct, rows = [], []
    for h in holdings:
        w = max(0.0, h.get("weight") or 0) / total_w  # fraction of the portfolio
        d = data.get(h["id"], {})
        kind = d.get("kind") or "other"
        lt = d.get("lookthrough") or {}
        fee = h.get("fee") if h.get("fee") is not None else d.get("fee")
        # the name as it appears in the client's own statement (TASE short names are truncated); market name as fallback
        row = {"id": h["id"], "name": h.get("name") or d.get("name") or h["id"],
               "weight": w * 100, "kind": kind, "fee": fee, "tracker": d.get("tracker"), "priced": bool(d.get("priced")),
               "asset_class": d.get("asset_class"), "asset_type": d.get("asset_type")}
        if kind == "equity":
            if d.get("market") == "IL" or d.get("country") == "ישראל":
                eq_il += w
            else:
                eq_f += w
            fee_cov += w
        elif kind == "bond":
            is_gov = "ממשלתי" in (d.get("asset_class") or "")
            lk = d.get("linkage")
            if is_gov:
                gov += w
            else:
                corp += w
                rk = rating_rank(d.get("maalot")) if d.get("maalot") else rating_rank(d.get("midroog"))
                if rk is not None:
                    corp_rated += w
                    if rk >= _RATING_ORDER.index("BBB"):
                        low += w
            if lk == "cpi":
                linked += w
            elif lk in ("nominal", "float"):
                shekel += w
            if d.get("duration") is not None:
                dur_num += w * float(d["duration"])
                dur_den += w
            fee_cov += w
        elif kind in ("fund", "etf"):
            funds_etf += w
            if kind == "fund" and not d.get("tracker"):
                managed += w
            eq_il += w * lt.get("eq_il", 0)
            eq_f += w * lt.get("eq_foreign", 0)
            g = sum(lt.get(k, 0) for k in ("gov_cpi", "gov_usd", "gov_nominal", "gov_float"))
            c = sum(lt.get(k, 0) for k in ("corp_usd", "corp_cpi", "corp_nominal", "corp_float", "corp_hedged"))
            gov += w * g
            corp += w * c
            linked += w * (lt.get("gov_cpi", 0) + lt.get("corp_cpi", 0))
            shekel += w * sum(lt.get(k, 0) for k in ("gov_nominal", "gov_float", "corp_nominal", "corp_float", "corp_hedged"))
            if d.get("duration") is not None and g + c > 0:
                dur_num += w * (g + c) * float(d["duration"])
                dur_den += w * (g + c)
            rt = d.get("ratings") or {}
            if c > 0 and rt:
                bonds_total = sum(rt.values()) or 1
                corp_rated += w * c
                low += w * c * (rt.get("low", 0) + rt.get("unrated", 0)) / bonds_total
            if fee is not None:
                fee_num += w * float(fee)
                fee_cov += w
                ffee_num += w * float(fee)
                ffee_cov += w
        else:
            if fee is not None:
                fee_num += w * float(fee)
                fee_cov += w
        if kind in ("equity", "bond") and w * 100 > 0:
            big_direct.append(row)
        rows.append(row)

    xm = xray.get("metrics", {})
    equity = eq_il + eq_f
    m = {
        "Israel_Equity": eq_il / equity if equity > 0.001 else None,
        "FX_Exposure": (xm.get("fx_exposure") or 0) / 100,
        "Managed_Funds": managed,
        "Single_Security": max((r["weight"] for r in big_direct), default=0) / 100,
        "Shekel_Bonds": shekel / (shekel + linked) if shekel + linked > 0.001 else None,
        "Gov_Bonds": gov / (gov + corp) if gov + corp > 0.001 else None,
        "Low_Rated": low / corp_rated if corp_rated > 0.001 else None,
        "Duration": dur_num / dur_den if dur_den > 0.001 else None,
        "Funds_Fee_Avg": (ffee_num / ffee_cov) / 100 if ffee_cov > 0.001 else None,
        "Funds_ETF_Share": funds_etf,
        "Equity_Total": equity,
        "Holdings_Count": len(holdings),
    }
    extras = {
        "effective_fee": fee_num / fee_cov if fee_cov > 0.001 else None,  # % per year over the part with known cost
        "fee_coverage": fee_cov * 100,
        "funds_fee_coverage": (ffee_cov / funds_etf * 100) if funds_etf > 0.001 else None,
        "low_rated_coverage": (corp_rated / corp * 100) if corp > 0.001 else None,
        "bonds": (gov + corp) * 100, "gov": gov * 100, "corp": corp * 100, "linked": linked * 100, "shekel": shekel * 100,
        "eq_il": eq_il * 100, "eq_foreign": eq_f * 100, "cash": cash / total_w * 100,
        "asset_classes": xray.get("asset_classes", {}), "geography": xray.get("geography", {}),
        "big_direct": sorted([r for r in big_direct if r["weight"] > 0], key=lambda r: -r["weight"]),
    }
    return {"metrics": m, "extras": extras, "rows": sorted(rows, key=lambda r: -r["weight"])}


# --------------------------------------------------------------------------- #
#  Security type chosen by the advisor (non-traded funds, structured products, unidentified papers)
# --------------------------------------------------------------------------- #
# key -> (label, fields for compute(), X-Ray profile: equity regions / bond buckets / cash / other, fx, duration)
ASSET_TYPES = {
    "eq_il":        ("מניה ישראלית", {"kind": "equity", "country": "ישראל"}, {"equity": {"IL": 1}}),
    "eq_foreign":   ("מניה בחו״ל", {"kind": "equity", "country": "חו״ל"}, {"equity": {"OTHER": 1}, "fx": 1}),
    "gov_cpi":      ("אג״ח ממשלתי צמוד", {"kind": "bond", "asset_class": "אג״ח ממשלתי", "linkage": "cpi", "duration": 6.0},
                     {"il_gov": 1, "dur": 6.0}),
    "gov_nominal":  ("אג״ח ממשלתי שקלי", {"kind": "bond", "asset_class": "אג״ח ממשלתי", "linkage": "nominal", "duration": 6.0},
                     {"il_gov": 1, "dur": 6.0}),
    "corp_cpi":     ("אג״ח קונצרני צמוד", {"kind": "bond", "asset_class": "אג״ח קונצרני", "linkage": "cpi", "duration": 3.5},
                     {"il_corp": 1, "dur": 3.5}),
    "corp_nominal": ("אג״ח קונצרני שקלי", {"kind": "bond", "asset_class": "אג״ח קונצרני", "linkage": "nominal", "duration": 3.5},
                     {"il_corp": 1, "dur": 3.5}),
    "bond_foreign": ("אג״ח בחו״ל (מט״ח)", {"kind": "bond", "asset_class": "אג״ח קונצרני", "duration": 5.0},
                     {"foreign_corp": 1, "fx": 1, "dur": 5.0}),
    "fund_eq_il":   ("קרן מניות ישראל", {"kind": "fund", "tracker": False, "lookthrough": {"eq_il": 1.0}}, {"equity": {"IL": 1}}),
    "fund_eq_f":    ("קרן מניות חו״ל", {"kind": "fund", "tracker": False, "lookthrough": {"eq_foreign": 1.0}},
                     {"equity": {"OTHER": 1}, "fx": 1}),
    "fund_bond_cpi": ("קרן אג״ח צמודה", {"kind": "fund", "tracker": False, "lookthrough": {"corp_cpi": 1.0}, "duration": 3.5},
                      {"il_corp": 1, "dur": 3.5}),
    "fund_bond_nom": ("קרן אג״ח שקלית", {"kind": "fund", "tracker": False, "lookthrough": {"corp_nominal": 1.0}, "duration": 3.5},
                      {"il_corp": 1, "dur": 3.5}),
    "fund_bond_f":  ("קרן אג״ח חו״ל", {"kind": "fund", "tracker": False, "lookthrough": {"corp_usd": 1.0}, "duration": 5.0},
                     {"foreign_corp": 1, "fx": 1, "dur": 5.0}),
    "alt":          ("קרן גידור / השקעה אלטרנטיבית", {"kind": "fund", "tracker": False, "lookthrough": {}}, {"other": 1}),
    "structured":   ("מוצר מובנה / אחר", {"kind": "other"}, {"other": 1}),
    "cash":         ("פיקדון / מזומן", {"kind": "cash"}, {"cash": 1}),
}


def apply_asset_type(d: dict, key: str) -> dict:
    """Security data with the advisor's chosen type on top (fee and name kept)."""
    _, fields, _ = ASSET_TYPES[key]
    out = {k: v for k, v in d.items() if k not in ("lookthrough", "linkage", "tracker", "country", "market", "duration", "asset_class")}
    return {**out, **fields, "asset_type": key, "asset_type_label": ASSET_TYPES[key][0], "incomplete": False}


# --------------------------------------------------------------------------- #
#  Which IBI model is closest to a portfolio
# --------------------------------------------------------------------------- #
# Exposures compared (all in % of the portfolio, duration in years) and how much each counts in the match score.
MATCH_DIMS = [
    ("equity", "מניות (סה״כ)", 3.0), ("eq_il", "מניות ישראל", 1.5), ("eq_foreign", "מניות חו״ל", 1.5),
    ("gov", "אג״ח ממשלתי", 1.0), ("corp", "אג״ח קונצרני", 1.0), ("linked", "צמוד מדד", 1.0), ("shekel", "שקלי", 1.0),
    ("fx", "חשיפה למט״ח", 1.5), ("cash", "מזומן", 0.5), ("duration", "מח״מ (שנים)", 1.0),
]
DURATION_PP = 10  # one year of duration difference counts like a 10-point exposure gap (capped at 30)


def exposure_profile(comp: dict) -> dict:
    """The figures used to match a portfolio to a model, from compute()'s output."""
    m, ex = comp["metrics"], comp["extras"]
    ac = ex.get("asset_classes") or {}
    return {
        "equity": (m.get("Equity_Total") or 0) * 100, "eq_il": ex.get("eq_il") or 0, "eq_foreign": ex.get("eq_foreign") or 0,
        "gov": ex.get("gov") or 0, "corp": ex.get("corp") or 0, "linked": ex.get("linked") or 0, "shekel": ex.get("shekel") or 0,
        "fx": (m.get("FX_Exposure") or 0) * 100, "cash": ac.get("מזומן ופיקדונות", 0) or 0, "duration": m.get("Duration"),
        "bonds": ex.get("bonds") or 0,
    }


def match(p: dict, m: dict) -> dict:
    """Match score 0–100: 100 minus the weighted average gap over MATCH_DIMS; also returns each gap."""
    gaps, num, den = {}, 0.0, 0.0
    for key, _, w in MATCH_DIMS:
        a, b = p.get(key), m.get(key)
        if key == "duration":
            if a is None or b is None or min(p.get("bonds", 0), m.get("bonds", 0)) < 5:
                continue
            gaps[key] = b - a
            num += w * min(30.0, abs(b - a) * DURATION_PP)
        else:
            gaps[key] = (b or 0) - (a or 0)
            num += w * abs(gaps[key])
        den += w
    return {"score": round(max(0.0, 100 - num / den), 1) if den else 0.0, "gaps": gaps}


# --------------------------------------------------------------------------- #
#  Rule evaluation
# --------------------------------------------------------------------------- #
def fmt(metric: str, v) -> str:
    if v is None:
        return "—"
    kind = METRICS.get(metric, ("", "pct"))[1]
    if kind == "years":
        return f"{v:.2f}"
    if kind == "int":
        return f"{int(round(v))}"
    if kind == "pct2":
        return f"{v * 100:.2f}%"
    return f"{v * 100:.1f}%"


def _check(v, lo, hi, direction) -> bool | None:
    if v is None:
        return None
    if direction == "ABOVE":
        return hi is not None and v > float(hi) + 1e-12
    if direction == "BELOW":
        return lo is not None and v < float(lo) - 1e-12
    return None


def _strip_prefix(text: str) -> str:
    # e.g. "פילוח אפיק מניות-  מניתוח התיק..." / 'מט"ח - מניתוח...' – the report shows its own title
    return re.sub(r"^\s*[^.\n]{2,30}?\s*-\s+(?=מניתוח)", "", text).strip()


def _xx(rule: dict, comp: dict) -> tuple[str, str | None]:
    m, ex = comp["metrics"], comp["extras"]
    metric, d = rule.get("metric"), rule.get("dir")
    if rule["type"] == "AND":
        conds = [c["metric"] for c in rule.get("conditions", [])]
        if set(conds) == {"Funds_Fee_Avg", "Funds_ETF_Share"}:  # the managers' rule: XX = share, YY = fee
            return fmt("Funds_ETF_Share", m["Funds_ETF_Share"]), fmt("Funds_Fee_Avg", m["Funds_Fee_Avg"])
        vals = [fmt(k, m.get(k)) for k in conds]  # rules added on the site: XX = first condition, YY = second
        return (vals[0] if vals else "—"), (vals[1] if len(vals) > 1 else None)
    v = m.get(metric)
    if metric == "Single_Security":
        lim = float(rule.get("max") or 0) * 100
        return str(sum(1 for r in ex["big_direct"] if r["weight"] > lim + 1e-9)), None
    if metric == "Shekel_Bonds" and d == "BELOW" and v is not None:
        return fmt(metric, 1 - v), None  # the text talks about the CPI-linked share
    if metric == "Gov_Bonds" and d == "BELOW" and v is not None:
        return fmt(metric, 1 - v), None  # the text talks about the corporate share
    if metric == "Managed_Funds":
        eff = ex["effective_fee"]
        return fmt(metric, v), (f"{eff:.2f}%" if eff is not None else "—")
    return fmt(metric, v), None


def evaluate(comp: dict, rules: list[dict]) -> dict:
    m = comp["metrics"]
    insights, checks = [], []
    for r in rules:
        if r.get("active") is False:
            continue
        if r["type"] == "AND":
            states = [_check(m.get(c["metric"]), c.get("min"), c.get("max"), c.get("dir")) for c in r["conditions"]]
            fired = all(s is True for s in states)
            unknown = any(s is None for s in states)
            metric = r["conditions"][0]["metric"]
        else:
            fired = _check(m.get(r["metric"]), r.get("min"), r.get("max"), r.get("dir"))
            unknown = fired is None
            fired = bool(fired)
            metric = r["metric"]
        if fired:
            xx, yy = _xx(r, comp)
            text = _strip_prefix(r["text"]).replace("XX", xx)
            if yy is not None:
                text = text.replace("YY", yy)
            insights.append({"id": r["id"], "metric": metric, "title": r.get("title") or TITLES.get(metric, r.get("name", "")), "text": text,
                             "direction": r.get("dir") or "AND"})
        checks.append({"id": r["id"], "metric": metric, "fired": fired, "unknown": unknown})
    # status per metric for the summary table: value vs the range from its rules
    status = []
    seen = set()
    rules = [r for r in rules if r.get("active") is not False]
    for r in rules:
        conds = r["conditions"] if r["type"] == "AND" else [r]
        for c in conds:
            key = c["metric"]
            if key in seen:
                continue
            seen.add(key)
            # the recommended range comes from the stand-alone rules on this figure; a figure that only appears inside a
            # combined (AND) rule is not a criterion by itself, so it gets no range or verdict of its own
            related = [x for x in rules if x.get("metric") == key and x.get("type") != "AND"]
            lo = next((x.get("min") for x in related if x.get("dir") == "BELOW"), None)
            hi = next((x.get("max") for x in related if x.get("dir") == "ABOVE"), None)
            v = m.get(key)
            state = None if v is None or (lo is None and hi is None) else ("high" if hi is not None and v > float(hi) + 1e-12 else
                                            "low" if lo is not None and v < float(lo) - 1e-12 else "ok")
            status.append({"metric": key, "label": METRICS[key][0], "value": v, "display": fmt(key, v), "min": lo, "max": hi,
                           "range": _range_text(key, lo, hi), "state": state})
    return {"insights": insights, "checks": checks, "status": status}


def _range_text(key, lo, hi) -> str:
    f = lambda x: fmt(key, x)  # noqa: E731
    if lo is not None and hi is not None:
        return f"{f(lo)} – {f(hi)}"
    if hi is not None:
        return f"עד {f(hi)}"
    if lo is not None:
        return f"מעל {f(lo)}"
    return "—"
