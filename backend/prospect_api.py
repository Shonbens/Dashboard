"""REST API for "ניתוח תיק פוטנציאלי": upload a prospect's portfolio -> metrics, insights, branded PDF; manage the rules."""
from __future__ import annotations

import asyncio
import logging
import re
import time
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

import models_store
import prospect
import secdata
from analysis import CONCURRENCY, analyze
from ingestion import parse_portfolio
from pricing import normalize_identifier
from prospect_report import build_prospect_pdf
from xray import xray_engine

log = logging.getLogger("prospect")
router = APIRouter(prefix="/api/prospect", tags=["prospect"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class PHolding(BaseModel):
    id: str
    name: str | None = None
    weight: float | None = Field(None, ge=0)
    quantity: float | None = None
    fee: float | None = Field(None, ge=0, le=20)
    asset_type: str | None = Field(None, max_length=20)  # advisor's classification (prospect.ASSET_TYPES); "" = automatic


class PRequest(BaseModel):
    holdings: list[PHolding] = Field(..., min_length=1, max_length=500)
    aum: float | None = Field(None, ge=0)
    client_name: str = Field("", max_length=80)
    advisor_name: str = Field("", max_length=80)
    advisor_contact: str = Field("", max_length=120)
    source: str = Field("", max_length=120)
    exclude: list[str] = Field(default_factory=list, max_length=100)  # recommendations the advisor chose not to show the client


async def profile(holdings: list[dict], aum: float | None, warnings: list[str] | None = None, cash: float = 0.0) -> dict:
    """Price, look through and measure a list of holdings -> {comp, priced, rows}. Used for the prospect and for IBI models."""
    warnings = [] if warnings is None else warnings
    priced = await analyze([dict(h) for h in holdings], aum or 0, False, warnings)
    rows = priced["holdings"]
    ids = [r["input_id"] for r in rows]
    sem = asyncio.Semaphore(CONCURRENCY)

    async def look(i):
        async with sem:
            return await asyncio.to_thread(secdata.auto_data, i)

    autos = await asyncio.gather(*(look(i) for i in ids))
    manual = secdata.get_manual(ids)
    data = {a["id"]: secdata.merged(a, manual.get(a["id"])) for a in autos}
    stmt_name = {r["input_id"]: (r.get("file_name") or r.get("name") or "") for r in rows}

    # Type chosen by the advisor on the page (this analysis), else one saved earlier in the securities data
    chosen = {h["id"]: h.get("asset_type") for h in holdings if "asset_type" in h}
    for i, d in list(data.items()):
        key = chosen[i] if i in chosen else d.get("asset_type")
        if key in prospect.ASSET_TYPES:
            nm = d.get("name") or ""
            data[i] = prospect.apply_asset_type(d, key)
            if nm.startswith("Unknown #"):
                data[i]["name"] = stmt_name.get(i) or nm
        elif d.get("asset_type"):
            data[i] = {k: v for k, v in d.items() if k != "asset_type"}  # cleared on the page: back to automatic

    # TASE numbers the exchange no longer knows (delisted / suspended – names often end in "-ש"): classify from the
    # statement name so they still count as Israeli equity or corporate bonds, and tell the advisor. Names with an
    # expiry date and no bond word ("הרל.ULSTR 03/23") are structured / non-traded products – left unclassified.
    stmt = {r["input_id"]: (r.get("file_name") or r.get("name") or "") for r in rows}
    gone, unknown = [], []
    for i, d in data.items():
        if d.get("asset_type") or not (str(d.get("name", "")).startswith("Unknown #") and re.fullmatch(r"\d{5,9}", i) and not re.fullmatch(r"[67]\d{7}", i)):
            continue
        nm = re.sub(r"\s+", " ", stmt.get(i) or "").strip()
        bond = bool(re.search(r"אג[״\"']?ח|\bאג\b|אגא", nm))
        if not nm or (not bond and (re.search(r"\d{1,2}/\d{2}", nm) or re.search(r"[A-Za-z]", nm))):
            unknown.append(nm or i)
            continue
        data[i] = {**d, "name": nm, "kind": "bond" if bond else "equity", "country": "ישראל",
                   "delisted": True, "incomplete": False}
        gone.append(nm)
    if gone:
        warnings.append(f"{len(gone)} ניירות ללא נתוני מסחר בבורסה (כנראה נמחקו או הושעו): "
                        f"{', '.join(gone[:8])}{'…' if len(gone) > 8 else ''}. סווגו לפי השם (מניה ישראלית / אג״ח קונצרני).")
    if unknown:
        warnings.append(f"{len(unknown)} ניירות לא זוהו (מוצרים לא סחירים / מובנים?): {', '.join(unknown[:8])}. "
                        "הם נספרים בתיק אך לא בחשיפות – ניתן להשלים אותם ידנית בנתוני הניירות.")
    missing = [i for i, d in data.items() if d.get("incomplete")]
    if missing:
        warnings.append(f"מאי״ה (הבורסה) לא החזירה נתונים מלאים ל-{len(missing)} ניירות – ייתכן שהשירות אינו זמין כרגע. "
                        "דמי ניהול והרכב של קרנות אלו חסרים או מוערכים; מומלץ לנסות שוב בעוד כמה דקות לפני הפקת הסקירה.")
    risk = [{k: r.get(k) for k in ("input_id", "ticker", "name", "name_en", "weight", "market", "asset_class", "currency", "sector", "fee")}
            for r in rows]

    for r in risk:  # hand-classified papers: fixed X-Ray profile from their type
        key = data.get(r["input_id"], {}).get("asset_type")
        if key in prospect.ASSET_TYPES:
            r["profile_override"] = xray_engine.type_profile(prospect.ASSET_TYPES[key][2], prospect.ASSET_TYPES[key][0])

    async def warm(h):
        async with sem:
            await asyncio.to_thread(xray_engine.profile, h)

    await asyncio.gather(*(warm(h) for h in risk if not h.get("profile_override")))
    xr = await asyncio.to_thread(xray_engine.analyze, risk, aum or 1_000_000)
    xr.pop("_profiles", None)

    # Asset mix on a 100% base: look-through can overshoot (swap / leveraged funds) and the X-Ray
    # sees only the listed holdings, so rescale to them and put any cash remainder back.
    ac = xr.get("asset_classes") or {}
    tot = sum(ac.values()) or 1
    ac = {k: v / tot * (100 - cash) for k, v in ac.items()}
    if cash > 0:
        ac["מזומן ופיקדונות"] = ac.get("מזומן ופיקדונות", 0) + cash
    xr["asset_classes"] = ac
    hs = [{"id": r["input_id"], "name": r.get("file_name") or r.get("name"), "weight": r["weight"], "fee": r.get("fee")} for r in rows]
    comp = prospect.compute(hs, data, xr, cash)
    return {"comp": comp, "priced": priced, "rows": rows, "data": data}


# ---- which IBI model is closest ---------------------------------------------------------
_MODEL_CACHE: dict[tuple, tuple[float, dict]] = {}
MODEL_TTL = 3600


async def model_profile(m: dict) -> dict:
    """A saved model measured exactly like a prospect (same look-through and figures); cached per model version."""
    key = (m["id"], m["version"])
    hit = _MODEL_CACHE.get(key)
    if hit and time.time() - hit[0] < MODEL_TTL:
        return hit[1]
    cash = max(0.0, 100 - sum(h["weight"] for h in m["holdings"]))
    comp = (await profile(m["holdings"], 1_000_000, [], cash))["comp"]
    _MODEL_CACHE[key] = (time.time(), comp)
    return comp


async def model_matches(comp: dict) -> list[dict]:
    models = [m for m in models_store.list_models() if m["holdings"]]
    comps = await asyncio.gather(*(model_profile(m) for m in models))
    p = prospect.exposure_profile(comp)
    out = []
    for m, mc in zip(models, comps):
        e = prospect.exposure_profile(mc)
        mt = prospect.match(p, e)
        out.append({"id": m["id"], "name": m["name"], "status": m["status"], "kind": m.get("kind"),
                    "template": (m.get("config") or {}).get("template"), "equity_target": m["equity_target"],
                    "score": mt["score"], "gaps": mt["gaps"], "profile": e})
    out.sort(key=lambda x: -x["score"])
    return out


async def run(holdings: list[dict], aum: float | None, warnings: list[str] | None = None) -> dict:
    warnings = [] if warnings is None else warnings
    prof = await profile(holdings, aum, warnings)
    comp, priced, rows = prof["comp"], prof["priced"], prof["rows"]
    rules_doc = prospect.load_rules()
    ev = prospect.evaluate(comp, rules_doc["rules"])
    try:
        matches = await model_matches(comp)
    except Exception:  # an add-on: never block the analysis
        log.exception("model matching failed")
        matches = []
    return {
        "comp": comp, "eval": ev, "rules": rules_doc["rules"], "warnings": warnings,
        "matches": matches, "profile": prospect.exposure_profile(comp),
        "match_dims": [{"key": k, "label": lab, "weight": w} for k, lab, w in prospect.MATCH_DIMS],
        "aum": priced["summary"]["aum"] or aum, "unpriced": priced["summary"]["unpriced"],
        "holdings": [{"id": r["input_id"], "name": r.get("file_name") or r.get("name"), "weight": r["weight"], "fee": r.get("fee"),
                      "quantity": r.get("quantity"), "asset_type": (prof["data"].get(r["input_id"]) or {}).get("asset_type")} for r in rows],
        "asset_types": [{"key": k, "label": v[0]} for k, v in prospect.ASSET_TYPES.items()],
    }


def _public(res: dict) -> dict:
    return {k: v for k, v in res.items() if k != "rules"}


@router.post("/analyze")
async def analyze_file(file: UploadFile = File(...), aum: float | None = Form(None)):
    if not (file.filename or "").lower().endswith((".csv", ".xlsx", ".xlsm", ".xls")):
        raise HTTPException(415, "יש להעלות קובץ Excel או CSV")
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(413, "הקובץ גדול מדי (מקסימום 5MB)")
    try:
        holdings, warnings = await asyncio.to_thread(parse_portfolio, file.filename, content)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        log.exception("prospect parse failed")
        raise HTTPException(422, f"קריאת הקובץ נכשלה: {e}")
    if len(holdings) > 500:
        raise HTTPException(422, "יותר מדי ניירות בקובץ (מקסימום 500)")
    values = [h.get("value") for h in holdings if h.get("value")]
    if not aum and values:
        aum = float(sum(values))
    res = await run(holdings, aum, warnings)
    res["source_file"] = file.filename
    return _public(res)


@router.post("/analyze-json")
async def analyze_json(req: PRequest):
    hs = [{**h.model_dump(), "id": normalize_identifier(h.id)} for h in req.holdings if normalize_identifier(h.id)]
    return _public(await run(hs, req.aum))


@router.post("/report.pdf")
async def report_pdf(req: PRequest):
    hs = [{**h.model_dump(), "id": normalize_identifier(h.id)} for h in req.holdings if normalize_identifier(h.id)]
    res = await run(hs, req.aum)
    if req.exclude:  # advisor's choice: drop these recommendations, and their status mark when nothing else covers the metric
        ex = set(req.exclude)
        ins = res["eval"]["insights"]
        kept = [i for i in ins if i["id"] not in ex]
        res["eval"]["insights"] = kept
        res["eval"]["muted"] = sorted({i["metric"] for i in ins if i["id"] in ex} - {i["metric"] for i in kept})
    pdf = await asyncio.to_thread(build_prospect_pdf, res, req.client_name.strip(), req.advisor_name.strip(), req.aum or None, req.source,
                                  req.advisor_contact.strip())
    name = f"IBI – סקירת תיק השקעות – {req.client_name.strip()}.pdf" if req.client_name.strip() else "IBI – סקירת תיק השקעות.pdf"
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=\"prospect.pdf\"; filename*=UTF-8''{quote(name, safe='')}"})


# ---- rules ------------------------------------------------------------------------
@router.get("/rules")
def get_rules():
    doc = prospect.load_rules()
    return {**doc, "metrics": {k: v[0] for k, v in prospect.METRICS.items()},
            "metric_kinds": {k: v[1] for k, v in prospect.METRICS.items()}, "titles": prospect.TITLES}


class RulesSave(BaseModel):
    rules: list[dict] = Field(..., min_length=1, max_length=200)
    user: str = Field(..., min_length=1, max_length=80)


@router.put("/rules")
def put_rules(req: RulesSave):
    """Save the rule set edited on the site (replaces the current rules; the Excel export/import keeps working)."""
    errs = prospect.validate_rules(req.rules)
    if errs:
        raise HTTPException(422, " · ".join(errs[:6]))
    return prospect.save_rules(req.rules, req.user.strip(), "עריכה באתר")


@router.get("/rules.xlsx")
def rules_xlsx():
    data = prospect.export_rules_workbook(prospect.load_rules()["rules"])
    return Response(data, media_type=XLSX, headers={"Content-Disposition": 'attachment; filename="Report Insights.xlsx"'})


@router.post("/rules/import")
async def import_rules(file: UploadFile = File(...), user: str = Form(""), commit: bool = Form(False)):
    try:
        rules, warnings = await asyncio.to_thread(prospect.parse_rules_workbook, await file.read())
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(422, f"קריאת הקובץ נכשלה: {e}")
    if not rules:
        raise HTTPException(422, "לא נמצאו כללים בקובץ")
    if commit:
        prospect.save_rules(rules, user, file.filename or "")
    return {"rules": rules, "warnings": warnings, "committed": commit}


# ---- demo -------------------------------------------------------------------------
DEMO_ROWS = [  # a typical statement from another house (illustrative values, ₪)
    ("לאומי", 604611, 120000), ("פועלים", 662577, 95000), ("טבע", 629014, 60000), ("אלביט מערכות", 1081124, 70000),
    ("איביאי מניות", 5102132, 90000), ("איביאי 4D גלובל אקוויטי", 5100482, 80000), ('איביאי אג"ח חברות מדורג', 5117577, 110000),
    ("איביאי תיק קונצרני", 5128434, 70000), ("הראל מחקה תל-גוב צמוד 5-10", 5116785, 40000), ("עזריאלי אגח ו", 1156611, 45000),
    ("מז טפ הנ אגח 62", 2310498, 35000), ("אינבסקו S&P 500", 1183441, 60000), ("Apple", "AAPL", 40000), ("Microsoft", "MSFT", 25000),
]


@router.get("/demo.xlsx")
def demo_file():
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "אחזקות"
    ws.sheet_view.rightToLeft = True
    ws.append(["פירוט אחזקות – בית השקעות אחר (קובץ הדגמה)"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append(["תאריך: " + __import__("time").strftime("%d/%m/%Y")])
    ws.append([])
    ws.append(["שם נייר", "מספר נייר", 'שווי בש"ח'])
    for c in ws[4]:
        c.font = Font(bold=True)
    for name, sid, val in DEMO_ROWS:
        ws.append([name, sid, val])
    ws.append(['סה"כ', None, sum(v for _, _, v in DEMO_ROWS)])
    for col, w in zip("ABC", (34, 14, 14)):
        ws.column_dimensions[col].width = w
    import io as _io
    buf = _io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(), media_type=XLSX, headers={"Content-Disposition": 'attachment; filename="demo_prospect_portfolio.xlsx"'})
