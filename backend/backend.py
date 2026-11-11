"""
IBI Portfolio Analytics & Rebalancing API.

Run:  uvicorn backend:app --reload --port 8000     (from /backend, inside .venv)
"""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from analysis import analyze
from models_api import portfolio_router, router as models_router, seed_demo_models
from allocation_api import router as secdata_router
from prospect_api import router as prospect_router
import secdata
from ingestion import SAMPLE_CSV, parse_portfolio
from pricing import engine, normalize_identifier
from stress import PRESETS, SHOCK_KEYS, run_stress
from xray import xray_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("pymaya").setLevel(logging.CRITICAL)
log = logging.getLogger("api")

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_HOLDINGS = 300
CONCURRENCY = 10

@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Load the TASE directory in the background so the first upload is fast
    seed_demo_models()
    secdata.init_db()
    asyncio.get_running_loop().run_in_executor(None, engine.directory.ensure)
    yield


app = FastAPI(title="IBI Portfolio Analytics API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(models_router)
app.include_router(portfolio_router)
app.include_router(secdata_router)
app.include_router(prospect_router)


# --------------------------------------------------------------------------- #
#  Models
# --------------------------------------------------------------------------- #
class HoldingIn(BaseModel):
    id: str
    name: str | None = None
    weight: float | None = None
    target_weight: float | None = None
    quantity: float | None = None
    fee: float | None = None


class AnalyzeRequest(BaseModel):
    holdings: list[HoldingIn] = Field(..., min_length=1, max_length=MAX_HOLDINGS)
    aum: float | None = Field(default=1_000_000, ge=0)
    refresh: bool = False


# --------------------------------------------------------------------------- #
#  Routes
# --------------------------------------------------------------------------- #
@app.get("/api/health")
def health():
    return {"status": "ok", "tase_directory_size": engine.directory.size, "time": time.time()}


@app.post("/api/analyze-portfolio")
async def analyze_portfolio(
    file: UploadFile = File(...),
    aum: float = Form(1_000_000),
    refresh: bool = Form(False),
):
    if not (file.filename or "").lower().endswith((".csv", ".xlsx", ".xlsm", ".xls")):
        raise HTTPException(415, "סוג קובץ לא נתמך – יש להעלות CSV או Excel")
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "הקובץ גדול מדי (מקסימום 5MB)")
    try:
        holdings, warnings = await asyncio.to_thread(parse_portfolio, file.filename, content)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        log.exception("parse failed")
        raise HTTPException(422, f"קריאת הקובץ נכשלה: {e}")
    if len(holdings) > MAX_HOLDINGS:
        raise HTTPException(422, f"יותר מדי נכסים ({len(holdings)}); המקסימום הוא {MAX_HOLDINGS}")
    result = await analyze(holdings, aum, refresh, warnings)
    result["source_file"] = file.filename
    return result


@app.post("/api/analyze")
async def analyze_json(req: AnalyzeRequest):
    """Re-analyse an edited holdings list (manual add/remove, target edits) without re-uploading."""
    holdings = [
        {**h.model_dump(), "id": normalize_identifier(h.id)} for h in req.holdings if normalize_identifier(h.id)
    ]
    if not holdings:
        raise HTTPException(422, "לא התקבלו נכסים")
    return await analyze(holdings, req.aum, req.refresh)


@app.get("/api/quote/{identifier}")
async def quote(identifier: str, refresh: bool = False):
    q = await asyncio.to_thread(engine.quote, identifier, refresh)
    d = q.to_dict()
    d["fx_rate"] = await asyncio.to_thread(engine.fx_to_ils, q.currency) if q.priced else 1.0
    d["price_ils"] = round(q.price * d["fx_rate"], 4)
    return d


@app.get("/api/search")
async def search(q: str = Query(..., min_length=1, max_length=50)):
    """Autocomplete over the TASE directory (Hebrew/English name, symbol, ID). Non-numeric input also offered as a US ticker."""
    results = await asyncio.to_thread(engine.directory.search, q)
    s = q.strip().upper()
    if s.isascii() and s.replace(".", "").replace("-", "").isalnum() and not s.isdigit() and len(s) <= 10:
        results.insert(0, {"id": s, "symbol": s, "name": f"{s} (Yahoo Finance)", "name_en": s, "asset_class": "", "market": "US"})
    return {"results": results[:12]}


@app.get("/api/fx")
async def fx():
    pairs = {}
    for c in ("USD", "EUR", "GBP"):
        pairs[c] = round(await asyncio.to_thread(engine.fx_to_ils, c), 4)
    return {"base": "ILS", "rates": pairs, "time": time.time()}


@app.post("/api/cache/clear")
def clear_cache():
    engine.clear_cache()
    return {"status": "cleared"}


# --------------------------------------------------------------------------- #
#  Risk modules: Fund X-Ray & Macro stress testing
# --------------------------------------------------------------------------- #
class RiskHolding(BaseModel):
    input_id: str
    ticker: str | None = None
    name: str | None = None
    name_en: str | None = None
    weight: float = 0
    market: str | None = None
    asset_class: str | None = None
    currency: str | None = "ILS"
    sector: str | None = None
    fee: float | None = None


class XRayRequest(BaseModel):
    holdings: list[RiskHolding] = Field(..., min_length=1, max_length=MAX_HOLDINGS)
    aum: float = Field(default=1_000_000, ge=0)


class Shocks(BaseModel):
    equity_local_pct: float = Field(0, ge=-100, le=100)
    equity_global_pct: float = Field(0, ge=-100, le=100)
    rate_il_bps: float = Field(0, ge=-1000, le=1000)
    rate_global_bps: float = Field(0, ge=-1000, le=1000)
    credit_bps: float = Field(0, ge=-1000, le=2000)
    fx_pct: float = Field(0, ge=-50, le=50)


class StressRequest(XRayRequest):
    shocks: Shocks = Shocks()
    scenario_id: str | None = None
    use_beta: bool = True
    compare_presets: bool = True


def _risk_holdings(items: list[RiskHolding]) -> list[dict]:
    out = []
    for h in items:
        d = h.model_dump()
        d["input_id"] = normalize_identifier(h.input_id)
        if d["input_id"]:
            out.append(d)
    if not out:
        raise HTTPException(422, "לא התקבלו נכסים")
    return out


@app.post("/api/fund-xray")
async def fund_xray(req: XRayRequest):
    """Look-through decomposition of the portfolio into underlying asset classes, regions, sectors and stocks."""
    holdings = _risk_holdings(req.holdings)
    await asyncio.to_thread(engine.directory.ensure)
    sem = asyncio.Semaphore(CONCURRENCY)

    async def warm(h):  # build per-holding profiles in parallel; analyze() then hits the cache
        async with sem:
            await asyncio.to_thread(xray_engine.profile, h)

    await asyncio.gather(*(warm(h) for h in holdings))
    result = await asyncio.to_thread(xray_engine.analyze, holdings, req.aum)
    result.pop("_profiles", None)
    return result


@app.get("/api/stress-scenarios")
def stress_scenarios():
    return {"scenarios": PRESETS, "shock_keys": list(SHOCK_KEYS)}


@app.post("/api/stress-test")
async def stress_test(req: StressRequest):
    holdings = _risk_holdings(req.holdings)
    shocks = req.shocks.model_dump()
    if req.scenario_id:
        preset = next((p for p in PRESETS if p["id"] == req.scenario_id), None)
        if not preset:
            raise HTTPException(404, f"תרחיש לא מוכר: {req.scenario_id}")
        shocks = {**shocks, **preset["shocks"]}
    await asyncio.to_thread(engine.directory.ensure)
    sem = asyncio.Semaphore(CONCURRENCY)

    async def warm(h):
        async with sem:
            await asyncio.to_thread(xray_engine.profile, h)

    await asyncio.gather(*(warm(h) for h in holdings))
    return await asyncio.to_thread(run_stress, holdings, req.aum, shocks, req.use_beta, req.compare_presets)


@app.get("/api/template")
def template():
    return Response(
        content="﻿" + SAMPLE_CSV,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="portfolio_template.csv"'},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend:app", host="127.0.0.1", port=8000, reload=False)
