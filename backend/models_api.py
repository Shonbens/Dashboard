"""REST API for base investment models: CRUD, version history, Excel import/export and model analytics."""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

import allocation_import
from allocation_export import build_allocation_xlsx
import model_io
import models_store as store
import secdata
from analysis import CONCURRENCY, analyze
from pricing import engine, normalize_identifier
from report import build_models_pdf
from stress import run_stress
from xray import xray_engine

log = logging.getLogger("models")
router = APIRouter(prefix="/api/models", tags=["models"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ModelHolding(BaseModel):
    id: str
    name: str | None = None
    weight: float = Field(0, ge=0, le=1000)
    fee: float | None = Field(None, ge=0, le=20)


class ModelCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    description: str = ""
    equity_target: float | None = Field(None, ge=0, le=100)
    status: Literal["draft", "approved"] = "draft"
    holdings: list[ModelHolding] = []
    config: dict | None = None
    user: str = ""
    note: str = ""


class ModelUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=80)
    description: str | None = None
    equity_target: float | None = Field(None, ge=0, le=100)
    clear_equity_target: bool = False
    status: Literal["draft", "approved", "archived"] | None = None
    holdings: list[ModelHolding] | None = None
    config: dict | None = None
    clear_config: bool = False
    user: str = ""
    note: str = ""


class DuplicateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    user: str = ""


class ImportItem(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    action: Literal["create", "update", "skip"]
    target_id: int | None = None
    holdings: list[ModelHolding]
    config: dict | None = None          # allocation-sheet import
    equity_target: float | None = None


class ImportCommit(BaseModel):
    items: list[ImportItem]
    user: str = ""
    note: str = "ייבוא מאקסל"


def _holdings(items: list[ModelHolding] | None) -> list[dict] | None:
    if items is None:
        return None
    return [{**h.model_dump(), "id": normalize_identifier(h.id)} for h in items if normalize_identifier(h.id)]


def seed_demo_models():
    store.init_db()
    if store.is_empty():
        for m in model_io.DEMO_MODELS:
            store.create_model(m["name"], m["holdings"], m["description"], status=m["status"], user="מערכת", note="מודל הדגמה")
        log.info("Seeded %d demo models", len(model_io.DEMO_MODELS))
    if not any(m.get("config") for m in store.list_models(include_archived=True)):
        for m in model_io.DEMO_ALLOCATIONS:
            if store.get_model_by_name(m["name"]):
                continue
            store.create_model(m["name"], m["holdings"], m["description"], equity_target=m["config"]["equity"],
                               status="draft", user="מערכת", note="גיליון הקצאה – הדגמה", config=m["config"])
        log.info("Seeded %d demo allocation sheets", len(model_io.DEMO_ALLOCATIONS))


# --------------------------------------------------------------------------- #
#  Analytics
# --------------------------------------------------------------------------- #
async def _priced_rows(holdings: list[dict], aum: float) -> list[dict]:
    if not holdings:
        return []
    res = await analyze([dict(h) for h in holdings], aum, False)
    return res["holdings"]


def _risk_rows(rows: list[dict]) -> list[dict]:
    keys = ("input_id", "ticker", "name", "name_en", "weight", "market", "asset_class", "currency", "sector", "fee")
    return [{k: r.get(k) for k in keys} for r in rows]


async def model_analytics(m: dict, aum: float, full: bool = False) -> dict:
    base = {k: m[k] for k in ("id", "name", "description", "status", "version", "updated_at", "updated_by",
                              "equity_target", "total_weight")}
    base["holdings_count"] = len(m["holdings"])
    base["kind"] = m.get("kind", "list")
    if not m["holdings"]:
        return {**base, "empty": True}
    rows = await _priced_rows(m["holdings"], aum)
    risk = _risk_rows(rows)
    sem = asyncio.Semaphore(CONCURRENCY)

    async def warm(h):
        async with sem:
            await asyncio.to_thread(xray_engine.profile, h)

    await asyncio.gather(*(warm(h) for h in risk))
    xr = await asyncio.to_thread(xray_engine.analyze, risk, aum)
    st = await asyncio.to_thread(run_stress, risk, aum, {}, True, True)
    eq = xr["metrics"]["equity_weight"]
    return {
        **base,
        "unpriced": [r["input_id"] for r in rows if not r["priced"]],
        "day_change_pct": round(sum((r.get("change_pct") or 0) * (r.get("weight") or 0) / 100 for r in rows), 3),
        "asset_classes": xr["asset_classes"],
        "geography": xr["geography"],
        "sectors": dict(list(xr["sectors"].items())[:6]),
        "metrics": xr["metrics"],
        "equity_drift": None if m["equity_target"] is None else round(eq - m["equity_target"], 2),
        "top_underlying": [{"name": u["name"], "total": u["total"]} for u in xr["top_underlying"][:5]],
        "scenarios": [{"id": s["id"], "name": s["name"], "icon": s["icon"], "pnl_pct": s["pnl_pct"]} for s in st["scenario_comparison"]],
        "sensitivities": st["sensitivities"],
        "holdings": [{"id": r["input_id"], "name": r["name"], "weight": r["weight"], "asset_class": r["asset_class"],
                      "market": r["market"], "priced": r["priced"]} for r in rows],
        # Extra detail used by the PDF report
        **({"report": {
            "sectors": xr["sectors"],
            "top_underlying": xr["top_underlying"][:10],
            "xray_holdings": xr["holdings"],
            "scenarios": st["scenario_comparison"],
            "rows": rows,
        }} if full else {}),
    }


# --------------------------------------------------------------------------- #
#  Routes
# --------------------------------------------------------------------------- #
@router.get("")
def list_models(include_archived: bool = False):
    return {"models": store.list_models(include_archived)}


@router.get("/overview")
async def overview(aum: float = Query(1_000_000, ge=0)):
    """Look-through analytics + stress results for every active model (for the comparison dashboard)."""
    t0 = time.time()
    models = store.list_models()
    await asyncio.to_thread(engine.directory.ensure)
    results = await asyncio.gather(*(model_analytics(m, aum) for m in models), return_exceptions=True)
    out = []
    for m, r in zip(models, results):
        if isinstance(r, Exception):
            log.exception("analytics failed for model %s", m["name"], exc_info=r)
            out.append({"id": m["id"], "name": m["name"], "status": m["status"], "version": m["version"], "error": str(r)})
        else:
            out.append(r)
    return {"models": out, "aum": aum, "elapsed_ms": int((time.time() - t0) * 1000)}


def _pdf_response(data: bytes, name: str) -> Response:
    name = re.sub(r"[/\\:*?\"<>|]+", "-", name)
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "_", name) or "report"
    return Response(data, media_type="application/pdf", headers={
        "Content-Disposition": f"inline; filename=\"{ascii_name}.pdf\"; filename*=UTF-8''{quote(name, safe='')}.pdf"})


async def _report_models(models: list[dict], aum: float) -> list[dict]:
    await asyncio.to_thread(engine.directory.ensure)
    out = await asyncio.gather(*(model_analytics(m, aum, full=True) for m in models))
    return [m for m in out if not m.get("empty")]


@router.get("/report.pdf")
async def models_book_pdf(ids: str | None = None, aum: float = Query(1_000_000, gt=0)):
    """All active models (or a subset): comparison cover page + a two-page sheet per model."""
    models = store.list_models()
    if ids:
        wanted = {int(x) for x in ids.split(",") if x.strip().isdigit()}
        models = [m for m in models if m["id"] in wanted]
    data = await _report_models(models, aum)
    if not data:
        raise HTTPException(404, "אין מודלים עם ניירות להפקת דוח")
    data.sort(key=lambda m: (m.get("equity_target") if m.get("equity_target") is not None else m["metrics"]["equity_weight"]))
    pdf = await asyncio.to_thread(build_models_pdf, data, aum, True, "סולם המודלים")
    return _pdf_response(pdf, f"IBI_models_{time.strftime('%Y-%m-%d')}")


@router.get("/{model_id}/report.pdf")
async def model_pdf(model_id: int, aum: float = Query(1_000_000, gt=0)):
    m = store.get_model(model_id)
    if not m:
        raise HTTPException(404, "המודל לא נמצא")
    data = await _report_models([m], aum)
    if not data:
        raise HTTPException(422, "המודל ריק – אין מה להציג בדוח")
    pdf = await asyncio.to_thread(build_models_pdf, data, aum, False)
    return _pdf_response(pdf, f"IBI_model_{m['name']}_v{m['version']}")


@router.get("/export")
async def export_models(ids: str | None = None):
    models = store.list_models()
    if ids:
        wanted = {int(x) for x in ids.split(",") if x.strip().isdigit()}
        models = [m for m in models if m["id"] in wanted]
    if not models:
        raise HTTPException(404, "אין מודלים לייצוא")
    all_ids = {h["id"] for m in models for h in m["holdings"]}
    quotes = await asyncio.gather(*(asyncio.to_thread(engine.quote, i) for i in all_ids))
    details = {q.input_id: {"name": q.name if q.priced else None, "asset_class": q.asset_class} for q in quotes}
    data = await asyncio.to_thread(model_io.export_workbook, models, details)
    stamp = time.strftime("%Y-%m-%d")
    return Response(data, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="models_{stamp}.xlsx"'})


@router.get("/demo-workbook")
def demo_workbook():
    demo = [{**m, "version": 1} for m in model_io.DEMO_MODELS]
    return Response(model_io.export_workbook(demo), media_type=XLSX,
                    headers={"Content-Disposition": 'attachment; filename="demo_models.xlsx"'})


class AllocationExport(BaseModel):
    name: str = Field("", max_length=200)
    template: Literal["global", "israel"] = "global"
    equity: float = Field(..., ge=0, le=100)
    settings: dict = Field(default_factory=dict)
    rows: list[dict] = Field(..., max_length=400)


@router.post("/allocation.xlsx")
def allocation_xlsx(req: AllocationExport):
    """Allocation sheet as a workbook with live Excel formulas (inputs come from the editor, formulas mirror allocation.js)."""
    data = build_allocation_xlsx(req.model_dump())
    name = f"{req.name or 'גיליון הקצאה'} – {time.strftime('%Y-%m-%d')}.xlsx"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename=\"allocation.xlsx\"; filename*=UTF-8''{quote(name, safe='')}"})


@router.post("/import")
async def import_preview(file: UploadFile = File(...)):
    """Parse a workbook (one sheet per model) and return a preview. Nothing is saved until /import/commit."""
    if not (file.filename or "").lower().endswith((".xlsx", ".xlsm", ".xls", ".csv")):
        raise HTTPException(415, "יש להעלות קובץ Excel (xlsx) או CSV")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "הקובץ גדול מדי (מקסימום 10MB)")
    if file.filename.lower().endswith((".xlsx", ".xlsm")):
        try:
            alloc = await asyncio.to_thread(allocation_import.parse_allocation_workbook, content)
        except Exception as e:
            log.info("not an allocation workbook: %s", e)
            alloc = []
        if alloc:
            return await _allocation_preview(file.filename, alloc)
    try:
        sheets = await asyncio.to_thread(model_io.read_workbook, file.filename, content)
    except Exception as e:
        raise HTTPException(422, f"קריאת הקובץ נכשלה: {e}")

    existing = {model_io.name_key(m["name"]): m for m in store.list_models(include_archived=True)}
    all_ids = {h["id"] for s in sheets for h in s["holdings"]}
    await asyncio.to_thread(engine.directory.ensure)
    sem = asyncio.Semaphore(CONCURRENCY)

    async def q(i):
        async with sem:
            return await asyncio.to_thread(engine.quote, i)

    quotes = {qq.input_id: qq for qq in await asyncio.gather(*(q(i) for i in all_ids))}
    previews = []
    for s in sheets:
        match = existing.get(model_io.name_key(s["sheet"]))
        holdings = []
        for h in s["holdings"]:
            qt = quotes.get(h["id"])
            holdings.append({**h, "resolved_name": qt.name if qt and qt.priced else None,
                             "asset_class": qt.asset_class if qt else None, "priced": bool(qt and qt.priced)})
        changes = None
        if match:
            old = {h["id"]: h["weight"] for h in match["holdings"]}
            new = {h["id"]: h["weight"] for h in s["holdings"]}
            changes = {
                "added": sorted(set(new) - set(old)), "removed": sorted(set(old) - set(new)),
                "changed": sorted(i for i in set(new) & set(old) if abs(new[i] - old[i]) > 1e-6),
            }
        previews.append({
            "sheet": s["sheet"],
            "name": match["name"] if match else s["sheet"],
            "error": s["error"],
            "warnings": s["warnings"],
            "holdings": holdings,
            "total_weight": round(sum(h["weight"] for h in s["holdings"]), 4),
            "unpriced": [h["id"] for h in holdings if not h["priced"]],
            "equity_target": store.equity_target_from_name(s["sheet"]),
            "match": {"id": match["id"], "name": match["name"], "version": match["version"], "status": match["status"]} if match else None,
            "changes": changes,
            "suggested_action": "skip" if s["error"] or not s["holdings"] or (changes is not None and not any(changes.values()))
            else ("update" if match else "create"),
        })
    return {"file": file.filename, "sheets": previews}


async def _allocation_preview(filename: str, sheets: list[dict]) -> dict:
    """Preview for the house allocation workbook: one allocation model per sheet."""
    existing = {model_io.name_key(m["name"]): m for m in store.list_models(include_archived=True)}
    fund_ids = {r["id"] for s in sheets for r in s.get("rows", []) if r["section"] == "funds"}
    all_ids = {r["id"] for s in sheets for r in s.get("rows", [])}
    sem = asyncio.Semaphore(CONCURRENCY)

    async def look(i):
        async with sem:
            return await asyncio.to_thread(secdata.auto_data, i)

    data = {d["id"]: d for d in await asyncio.gather(*(look(i) for i in all_ids))}
    eq_share = {i: sum((data.get(i, {}).get("lookthrough") or {}).get(k, 0) for k in ("eq_il", "eq_foreign")) for i in fund_ids}
    previews = []
    for s in sheets:
        name = re.sub(r"\s+", " ", s["sheet"]).strip()[:80]
        match = existing.get(model_io.name_key(name))
        if s.get("error"):
            previews.append({"sheet": s["sheet"], "name": name, "error": s["error"], "warnings": [], "holdings": [], "kind": "allocation",
                             "hidden": s.get("hidden"), "unpriced": [], "total_weight": 0, "match": None, "changes": None,
                             "suggested_action": "skip"})
            continue
        config, holdings, eq = allocation_import.finalize(s, eq_share)
        for h in holdings:
            d = data.get(h["id"], {})
            h.update({"resolved_name": d.get("name") if d.get("priced") else None, "asset_class": d.get("asset_class"),
                      "priced": bool(d.get("priced"))})
        changes = None
        if match:
            old = {h["id"]: h["weight"] for h in match["holdings"]}
            new = {h["id"]: h["weight"] for h in holdings}
            changes = {"added": sorted(set(new) - set(old)), "removed": sorted(set(old) - set(new)),
                       "changed": sorted(i for i in set(new) & set(old) if abs(new[i] - old[i]) > 1e-6)}
        unpriced = sorted({r["id"] for r in config["rows"] if not data.get(r["id"], {}).get("priced")})
        previews.append({
            "sheet": s["sheet"], "name": match["name"] if match else name, "error": None, "warnings": s["warnings"],
            "kind": "allocation", "hidden": s["hidden"], "template": s["template"], "rows_count": len(config["rows"]),
            "holdings": holdings, "config": config, "equity_target": eq,
            "total_weight": round(sum(h["weight"] for h in holdings), 4), "unpriced": unpriced,
            "match": {"id": match["id"], "name": match["name"], "version": match["version"], "status": match["status"]} if match else None,
            "changes": changes,
            # visible sheets are the live templates; hidden sheets are older versions – opt-in
            "suggested_action": "skip" if s["hidden"] else ("update" if match else "create"),
        })
    return {"file": filename, "kind": "allocation", "sheets": previews}


@router.post("/import/commit")
def import_commit(req: ImportCommit):
    created, updated, skipped, errors = [], [], [], []
    for it in req.items:
        try:
            hs = _holdings(it.holdings)
            if it.action == "skip":
                skipped.append(it.name)
            elif it.action == "update":
                if not it.target_id:
                    raise ValueError("חסר מזהה מודל לעדכון")
                m = store.update_model(it.target_id, holdings=hs, user=req.user, note=req.note,
                                       status=None if store.get_model(it.target_id)["status"] != "archived" else "draft",
                                       **({"config": it.config, "equity_target": it.equity_target} if it.config else {}))
                updated.append({"id": m["id"], "name": m["name"], "version": m["version"]})
            else:
                m = store.create_model(it.name, hs, user=req.user, note=req.note, config=it.config,
                                       equity_target=it.equity_target if it.config else None)
                created.append({"id": m["id"], "name": m["name"]})
        except Exception as e:
            errors.append({"name": it.name, "error": str(e)})
    return {"created": created, "updated": updated, "skipped": skipped, "errors": errors}


@router.post("")
def create_model(req: ModelCreate):
    try:
        return store.create_model(req.name, _holdings(req.holdings), req.description, req.equity_target, req.status,
                                  req.user, req.note or "יצירת מודל", config=req.config)
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.get("/{model_id}")
def get_model(model_id: int):
    m = store.get_model(model_id)
    if not m:
        raise HTTPException(404, "המודל לא נמצא")
    return m


@router.get("/{model_id}/versions/{version}")
def get_version(model_id: int, version: int):
    v = store.get_version(model_id, version)
    if not v:
        raise HTTPException(404, "הגרסה לא נמצאה")
    return v


@router.put("/{model_id}")
def update_model(model_id: int, req: ModelUpdate):
    eq = None if req.clear_equity_target else (req.equity_target if req.equity_target is not None else "__keep__")
    try:
        cfg = None if req.clear_config else (req.config if req.config is not None else "__keep__")
        return store.update_model(model_id, holdings=_holdings(req.holdings), name=req.name, description=req.description,
                                  equity_target=eq, status=req.status, user=req.user, note=req.note, config=cfg)
    except KeyError:
        raise HTTPException(404, "המודל לא נמצא")
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.post("/{model_id}/duplicate")
def duplicate_model(model_id: int, req: DuplicateRequest):
    src = store.get_model(model_id)
    if not src:
        raise HTTPException(404, "המודל לא נמצא")
    try:
        return store.create_model(req.name, src["holdings"], src["description"],
                                  src["equity_target"] if src.get("config") else None, "draft", req.user,
                                  f"שוכפל ממודל {src['name']} (גרסה {src['version']})", config=src.get("config"))
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.delete("/{model_id}/permanent")
def delete_model(model_id: int, user: str = ""):
    m = store.get_model(model_id)
    if not m:
        raise HTTPException(404, "המודל לא נמצא")
    store.delete_model(model_id)
    log.info("Model %s (%s) permanently deleted by %s", model_id, m["name"], user or "?")
    return {"deleted": model_id, "name": m["name"]}


@router.delete("/{model_id}")
def archive_model(model_id: int, user: str = ""):
    """Soft delete: the model is archived and keeps its full history."""
    try:
        return store.archive_model(model_id, user)
    except KeyError:
        raise HTTPException(404, "המודל לא נמצא")


# --------------------------------------------------------------------------- #
#  Client report (plain-language PDF for a client portfolio)
# --------------------------------------------------------------------------- #
from client_report import build_client_pdf  # noqa: E402

portfolio_router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


class ClientReportRequest(BaseModel):
    holdings: list[ModelHolding] = Field(..., min_length=1, max_length=300)
    aum: float = Field(..., gt=0)
    client_name: str = Field("", max_length=80)
    advisor_name: str = Field("", max_length=80)


def _mix_distance(a: dict, b: dict) -> float:
    keys = set(a["asset_classes"]) | set(b["asset_classes"])
    return sum(abs(a["asset_classes"].get(k, 0) - b["asset_classes"].get(k, 0)) for k in keys)


@portfolio_router.post("/client-report.pdf")
async def client_report(req: ClientReportRequest):
    """Plain-language client report. Nothing is stored; the client name only appears inside the PDF."""
    holdings = _holdings(req.holdings)
    if not holdings:
        raise HTTPException(422, "לא התקבלו נכסים")
    await asyncio.to_thread(engine.directory.ensure)
    pseudo = {"id": 0, "name": "התיק", "description": "", "status": "draft", "version": 0, "updated_at": time.time(),
              "updated_by": "", "equity_target": None, "total_weight": sum(h["weight"] for h in holdings), "holdings": holdings}
    models = [m for m in store.list_models() if m["holdings"]]
    approved = [m for m in models if m["status"] == "approved"] or models
    results = await asyncio.gather(model_analytics(pseudo, req.aum, full=True),
                                   *(model_analytics(m, req.aum) for m in approved))
    p, candidates = results[0], [m for m in results[1:] if not m.get("empty")]
    closest = min(candidates, key=lambda m: _mix_distance(p, m)) if candidates else None
    pdf = await asyncio.to_thread(build_client_pdf, p, closest, req.aum, req.client_name.strip(), req.advisor_name.strip())
    return _pdf_response(pdf, f"IBI_client_report_{time.strftime('%Y-%m-%d')}")
