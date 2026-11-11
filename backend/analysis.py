"""Core portfolio analysis shared by the portfolio and model endpoints."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import HTTPException

from ingestion import merge_duplicates
from pricing import engine

log = logging.getLogger("analysis")
CONCURRENCY = 10

# --------------------------------------------------------------------------- #
#  Core analysis
# --------------------------------------------------------------------------- #
async def price_all(ids: list[str], refresh: bool) -> dict[str, Any]:
    sem = asyncio.Semaphore(CONCURRENCY)

    async def one(i: str):
        async with sem:
            try:
                return i, await asyncio.to_thread(engine.quote, i, refresh)
            except Exception as e:  # engine already falls back, this is belt-and-braces
                log.exception("pricing crashed for %s: %s", i, e)
                return i, engine._fallback(i)

    # Warm the TASE directory once instead of racing it from every worker
    if any(i.isdigit() for i in ids):
        await asyncio.to_thread(engine.directory.ensure)
    return dict(await asyncio.gather(*(one(i) for i in ids)))


async def analyze(holdings: list[dict], aum: float | None, refresh: bool, warnings: list[str] | None = None) -> dict:
    t0 = time.time()
    warnings = list(warnings or [])
    holdings = merge_duplicates(holdings, warnings)
    ids = [h["id"] for h in holdings]
    quotes = await price_all(ids, refresh)

    currencies = {q.currency for q in quotes.values() if q.priced}
    fx = {c: await asyncio.to_thread(engine.fx_to_ils, c) for c in currencies | {"USD"}}
    fx["ILS"] = 1.0

    # --- weights: explicit weights, else derive from quantities, else equal weight
    has_weights = any(h.get("weight") is not None for h in holdings)
    has_qty = any(h.get("quantity") is not None for h in holdings)
    mode = "weights"
    if not has_weights and has_qty:
        mode = "quantities"
        values = {}
        for h in holdings:
            q = quotes[h["id"]]
            values[h["id"]] = (h.get("quantity") or 0) * q.price * fx.get(q.currency, 1.0)
        total = sum(values.values())
        if total <= 0:
            raise HTTPException(422, "לא ניתן לחשב שווי מכמויות – אין מחירים זמינים")
        for h in holdings:
            h["weight"] = values[h["id"]] / total * 100
        aum = total
        warnings.append("המשקלים חושבו מתוך הכמויות והמחירים העדכניים; היקף הנכסים נגזר משווי התיק")
    elif not has_weights:
        mode = "equal"
        for h in holdings:
            h["weight"] = 100 / len(holdings)
    aum = float(aum or 0)

    rows = []
    for h in holdings:
        q = quotes[h["id"]]
        rate = fx.get(q.currency, 1.0) if q.priced else 1.0
        price_ils = q.price * rate
        weight = float(h.get("weight") or 0)
        target = h.get("target_weight")
        value_ils = aum * weight / 100
        name = q.name if q.priced or not h.get("name") else h["name"]
        row = {
            **q.to_dict(),
            "name": name,
            "file_name": h.get("name"),
            "fx_rate": rate,
            "price_ils": round(price_ils, 4),
            "weight": round(weight, 4),
            "target_weight": None if target is None else round(float(target), 4),
            "value_ils": round(value_ils, 2),
            "units": int(value_ils // price_ils) if price_ils > 0 else None,
            "quantity": h.get("quantity"),
            "fee": h.get("fee"),
        }
        if target is not None:
            trade = aum * (float(target) - weight) / 100
            row["drift"] = round(weight - float(target), 4)
            row["trade_value_ils"] = round(trade, 2)
            row["trade_units"] = int(trade / price_ils) if price_ils > 0 else None
        rows.append(row)

    total_weight = sum(r["weight"] for r in rows)

    def exposure(key: str) -> dict[str, float]:
        out: dict[str, float] = {}
        for r in rows:
            out[r[key]] = round(out.get(r[key], 0) + r["weight"], 4)
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    unpriced = [r["input_id"] for r in rows if not r["priced"]]
    if unpriced:
        warnings.append(f"{len(unpriced)} ניירות לא תומחרו: {', '.join(unpriced)}")
    if abs(total_weight - 100) > 0.5:
        warnings.append(f"סך המשקלים הוא {total_weight:.2f}% (ולא 100%)")
    targets = [r["target_weight"] for r in rows if r["target_weight"] is not None]
    if targets and abs(sum(targets) - 100) > 0.5:
        warnings.append(f"סך משקלי היעד הוא {sum(targets):.2f}% (ולא 100%)")

    by_market = exposure("market")
    return {
        "holdings": rows,
        "summary": {
            "aum": round(aum, 2),
            "mode": mode,
            "total_weight": round(total_weight, 4),
            "cash_weight": round(100 - total_weight, 4),
            "il_exposure": by_market.get("IL", 0.0),
            "us_exposure": by_market.get("US", 0.0),
            "other_exposure": by_market.get("OTHER", 0.0),
            "by_market": by_market,
            "by_asset_class": exposure("asset_class"),
            "by_currency": exposure("currency"),
            "by_source": exposure("source"),
            "count": len(rows),
            "priced_count": len(rows) - len(unpriced),
            "unpriced": unpriced,
            "fx": {k: round(v, 4) for k, v in fx.items()},
            "priced_at": time.time(),
            "elapsed_ms": int((time.time() - t0) * 1000),
        },
        "warnings": warnings,
    }


