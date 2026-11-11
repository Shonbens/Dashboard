"""REST API for the allocation sheet: security reference data (lookup / manual edits / bulk import)."""
from __future__ import annotations

import asyncio
import io
import logging

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

import secdata
from analysis import CONCURRENCY
from pricing import normalize_identifier

log = logging.getLogger("allocation")
router = APIRouter(prefix="/api/secdata", tags=["allocation"])


class LookupRequest(BaseModel):
    ids: list[str] = Field(default_factory=list, max_length=400)
    refresh: bool = False


class ManualUpdate(BaseModel):
    fields: dict
    user: str = ""


@router.post("/lookup")
async def lookup(req: LookupRequest):
    ids = list(dict.fromkeys(normalize_identifier(i) for i in req.ids if normalize_identifier(i)))
    sem = asyncio.Semaphore(CONCURRENCY)

    async def one(sid):
        async with sem:
            return await asyncio.to_thread(secdata.auto_data, sid, req.refresh)

    autos = await asyncio.gather(*(one(s) for s in ids))
    manual = secdata.get_manual(ids)
    return {a["id"]: secdata.merged(a, manual.get(a["id"])) for a in autos}


@router.put("/{sid}")
async def update(sid: str, req: ManualUpdate):
    try:
        secdata.set_manual(sid, req.fields, req.user)
    except ValueError as e:
        raise HTTPException(422, str(e))
    sid = normalize_identifier(sid)
    auto = await asyncio.to_thread(secdata.auto_data, sid)
    return secdata.merged(auto, secdata.get_manual([sid]).get(sid))


# Column headers accepted when importing market data exported from the ACE add-in / any Excel
IMPORT_ALIASES = {
    "id": ("מספר נייר", "מס' נייר", "מספר ני\"ע", "קוד נייר", "id", "security id", "ticker", "symbol"),
    "yield": ("תשואה ברוטו", "תשואה לפדיון", "yield_bruto", "yield", "ytm"),
    "duration": ("מחמ", "מח\"מ", "מח״מ", "duration", "duration_bruto", "fd_duration_total"),
    "spread": ("מרווח", "syn_diff", "spread"),
    "maalot": ("דירוג מעלות", "maalot_rating", "s&p maalot"),
    "midroog": ("דירוג מידרוג", "midroog_rating", "midroog"),
    "sector": ("ענף", "sector_tase", "סקטור", "sector"),
    "industry": ("ענף אג\"ח", "industry"),
    "fee": ("דמי ניהול", "management_fee", "fee"),
    "rating_bucket": ("קבוצת סיכון", "דרגת סיכון", "risk bucket"),
}
PCT_FIELDS = ("yield", "spread", "fee")


def _norm(s) -> str:
    return str(s).strip().lower().replace("״", '"').replace("׳", "'")


def parse_market_data(raw: bytes, filename: str) -> tuple[list[dict], list[str]]:
    if filename.lower().endswith((".csv", ".txt")):
        df = pd.read_csv(io.BytesIO(raw), header=None, dtype=object)
    else:
        df = pd.read_excel(io.BytesIO(raw), header=None, dtype=object)
    alias = {_norm(a): k for k, al in IMPORT_ALIASES.items() for a in al}
    header_row, mapping = None, {}
    for i in range(min(25, len(df))):
        m = {j: alias[_norm(v)] for j, v in enumerate(df.iloc[i]) if v is not None and _norm(v) in alias}
        if "id" in m.values() and len(m) >= 2:
            header_row, mapping = i, m
            break
    if header_row is None:
        raise ValueError("לא נמצאה שורת כותרות עם 'מספר נייר' ולפחות עמודת נתונים אחת")
    body = df.iloc[header_row + 1:]
    cols = {f: j for j, f in mapping.items()}
    # Percent columns stored as fractions in Excel (0.0483) are converted to % (4.83)
    scale = {}
    for f in PCT_FIELDS:
        if f in cols:
            vals = pd.to_numeric(body[cols[f]], errors="coerce").dropna()
            scale[f] = 100 if len(vals) and vals.abs().max() <= 0.3 else 1
    rows = []
    for _, r in body.iterrows():
        sid = normalize_identifier(r[cols["id"]]) if r[cols["id"]] is not None else ""
        if not sid or not (any(ch.isdigit() for ch in sid) or sid.isascii() and sid.isalpha()):
            continue  # skip totals / section titles
        out = {"id": sid}
        for f, j in cols.items():
            if f == "id":
                continue
            v = r[j]
            if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() in ("", "#N/A", "N/A"):
                continue
            if f in ("maalot", "midroog", "sector", "industry"):
                out[f] = str(v).strip()
            else:
                try:
                    num = float(v)
                except (TypeError, ValueError):
                    continue
                out[f] = int(num) if f == "rating_bucket" else round(num * scale.get(f, 1), 6)
        if len(out) > 1:
            rows.append(out)
    return rows, sorted(set(mapping.values()) - {"id"})


@router.post("/import")
async def import_market_data(file: UploadFile = File(...), user: str = Form(""), commit: bool = Form(False)):
    raw = await file.read()
    try:
        rows, fields = parse_market_data(raw, file.filename or "")
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        log.warning("market data import failed: %s", e)
        raise HTTPException(422, "לא ניתן לקרוא את הקובץ")
    if commit:
        n = secdata.bulk_set([dict(r) for r in rows], user)
        return {"updated": n, "fields": fields}
    return {"rows": rows[:500], "count": len(rows), "fields": fields}
