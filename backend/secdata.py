"""
Security reference data for the allocation sheet – the web replacement for the ACE add-in columns
(name, yield, duration, spread, ratings, sector, management fee) and the external "נתוני קרנות" workbook
(fund look-through by bond linkage / equity region).

Every field has a source:
  auto    – Maya (TASE securities and Israeli mutual funds), yfinance (foreign), or the X-Ray estimate
  manual  – entered by a portfolio manager (shared across all models, with author and timestamp)
Manual values always win. Fields Maya does not publish (gross yield, spread, ratings) are manual or imported.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import time
from datetime import date
from typing import Any

import models_store
from pricing import engine as pricing_engine, is_tase_id, normalize_identifier
from xray import xray_engine

log = logging.getLogger("secdata")
_lock = threading.Lock()
_cache: dict[str, tuple[float, dict]] = {}
TTL = 3600

# Fields a manager can override (all percentages are stored in %, e.g. 4.83 for 4.83%)
FIELDS = {
    "name": str, "yield": float, "duration": float, "spread": float, "maalot": str, "midroog": str,
    "sector": str, "industry": str, "country": str, "exposure": str, "fee": float, "mtd": float, "ytd": float,
    "linkage": str, "rating_bucket": int, "re_share": float, "us_share": float, "hedged": bool, "lookthrough": dict,
    "asset_type": str,  # advisor's classification of a non-traded / unidentified paper (prospect.ASSET_TYPES key)
}
LT_KEYS = ("eq_il", "eq_foreign", "gov_cpi", "gov_usd", "gov_nominal", "gov_float",
           "corp_usd", "corp_cpi", "corp_nominal", "corp_float", "corp_hedged", "cash")

# TASE "FullBranch" -> the sector names used in the house Excel
SECTOR_RULES = [
    ("בנקים", "בנקים"), ("ביטוח", "ביטוח"), ("שירותים פיננסיים", "שרותים פיננסים"), ("פיננסי", "שרותים פיננסים"),
    ("נדל", "נדלן ובנייה"), ("בניה", "נדלן ובנייה"), ("בנייה", "נדלן ובנייה"),
    ("ביומד", "ביומד"), ("פארמ", "ביומד"), ("ביוטכ", "ביומד"), ("ביטחו", "ביטחונית"),
    ("טכנולוג", "טכנולוגיה"), ("תוכנה", "טכנולוגיה"), ("אלקטרוניקה", "טכנולוגיה"), ("שבבים", "טכנולוגיה"),
    ("נפט", "אנרגיה וחיפושי נפט וגז"), ("אנרגיה", "אנרגיה וחיפושי נפט וגז"), ("גז", "אנרגיה וחיפושי נפט וגז"),
    ("השקעה", "השקעה ואחזקות"), ("אחזקות", "השקעה ואחזקות"),
    ("מסחר", "מסחר ושרותים"), ("שירותים", "מסחר ושרותים"), ("תקשורת", "מסחר ושרותים"),
    ("תעשי", "תעשייה"), ("מתכת", "תעשייה"), ("כימיה", "תעשייה"), ("מזון", "תעשייה"),
]
GICS_HE = {  # yfinance sector -> GICS label used in the Excel sector table
    "Technology": "Information Technology", "Healthcare": "Health Care", "Financial Services": "Financials",
    "Consumer Cyclical": "Consumer Discretionary", "Communication Services": "Communication Services",
    "Industrials": "Industrials", "Consumer Defensive": "Consumer Staples", "Energy": "Energy",
    "Utilities": "Utilities", "Real Estate": "Real Estate", "Basic Materials": "Materials",
}


# --------------------------------------------------------------------------- #
#  Storage of manual values
# --------------------------------------------------------------------------- #
def init_db():
    with _lock, models_store._conn:
        models_store._conn.execute(
            """CREATE TABLE IF NOT EXISTS security_data (
                   id         TEXT PRIMARY KEY,
                   data       TEXT NOT NULL,      -- JSON of manual field values
                   updated_at REAL NOT NULL,
                   updated_by TEXT DEFAULT ''
               )"""
        )


def _clean(fields: dict) -> dict:
    out = {}
    for k, v in fields.items():
        if k not in FIELDS:
            continue
        if v is None or v == "":
            out[k] = None
            continue
        t = FIELDS[k]
        try:
            if t is dict:
                out[k] = {lk: float(v.get(lk) or 0) for lk in LT_KEYS if v.get(lk) not in (None, "")} if isinstance(v, dict) else None
            elif t is bool:
                out[k] = bool(v)
            else:
                out[k] = t(v)
        except (TypeError, ValueError):
            raise ValueError(f"ערך לא חוקי בשדה {k}: {v}")
    return out


def get_manual(ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    with _lock:
        q = f"SELECT * FROM security_data WHERE id IN ({','.join('?' * len(ids))})"
        rows = models_store._conn.execute(q, ids).fetchall()
    return {r["id"]: {**json.loads(r["data"]), "_by": r["updated_by"], "_at": r["updated_at"]} for r in rows}


def set_manual(sid: str, fields: dict, user: str = "") -> dict:
    """Merge manual values for one security. A field set to null is cleared (falls back to the data source)."""
    sid = normalize_identifier(sid)
    fields = _clean(fields)
    now = time.time()
    with _lock, models_store._conn:
        r = models_store._conn.execute("SELECT data FROM security_data WHERE id=?", (sid,)).fetchone()
        data = json.loads(r["data"]) if r else {}
        for k, v in fields.items():
            if v is None:
                data.pop(k, None)
            else:
                data[k] = v
        models_store._conn.execute(
            "INSERT INTO security_data(id, data, updated_at, updated_by) VALUES (?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at, updated_by=excluded.updated_by",
            (sid, json.dumps(data, ensure_ascii=False), now, user),
        )
    return data


def bulk_set(rows: list[dict], user: str = "") -> int:
    n = 0
    for r in rows:
        sid = normalize_identifier(r.pop("id", ""))
        if sid and r:
            set_manual(sid, r, user)
            n += 1
    return n


# --------------------------------------------------------------------------- #
#  Automatic data
# --------------------------------------------------------------------------- #
def tase_sector(branch: str | None) -> str | None:
    b = branch or ""
    for key, sector in SECTOR_RULES:
        if key in b:
            return sector
    return None


def linkage_key(text: str | None) -> str | None:
    t = text or ""
    if "משתנה" in t:
        return "float"
    if "לא צמוד" in t or "שקלי" in t:
        return "nominal"
    if "מט" in t or "דולר" in t:
        return "usd"
    if "מדד" in t or "צמוד" in t:
        return "cpi"
    return None


def fund_lookthrough(d: dict) -> dict:
    """Maya disclosure chart -> exposure by the Excel's sections (fractions of the fund)."""
    lt = {k: 0.0 for k in LT_KEYS}
    chart = d.get("DisclosureChart") or []
    codes = {r.get("LevelCd") or "": (float(r.get("ExposureRate") or 0) / 100, r.get("LevelDesc") or "") for r in chart}
    rating = {2: 0.0, 3: 0.0, 4: 0.0}
    regions = {"US": 0.0, "EUROPE": 0.0, "ROW": 0.0}
    us = 0.0
    fx_total = 0.0
    seen_l4 = {"gov": 0.0, "corp": 0.0}
    for code, (rate, desc) in codes.items():
        if code == "0101":
            lt["eq_il"] += rate
        elif code.startswith("0102") and len(code) == 6:
            if "ישראל" in desc:
                lt["eq_il"] += rate
            else:
                lt["eq_foreign"] += rate
            if "צפון אמריקה" in desc:
                us += rate
                regions["US"] += rate
            elif "אירופה" in desc and "None-DM" not in desc:
                regions["EUROPE"] += rate
            elif "ישראל" not in desc:
                regions["ROW"] += rate
        elif code.startswith("030101") and len(code) == 8:  # government, by linkage
            seen_l4["gov"] += rate
            if "צמוד" in desc and "לא צמוד" not in desc and "מט" not in desc:
                lt["gov_cpi"] += rate
            elif "מט" in desc:
                lt["gov_usd"] += rate
            elif "משתנה" in desc:
                lt["gov_float"] += rate
            else:
                lt["gov_nominal"] += rate
        elif code.startswith("030102") and len(code) == 8:  # corporate, by linkage
            seen_l4["corp"] += rate
            if "מדד" in desc:
                lt["corp_cpi"] += rate
            elif "מט" in desc:
                lt["corp_usd"] += rate
            elif "משתנה" in desc:
                lt["corp_float"] += rate
            else:
                lt["corp_nominal"] += rate
        elif code.startswith("05") and len(code) == 4:
            lt["cash"] += rate
        elif code.startswith("06") and len(code) == 4:
            fx_total += rate
        elif code == "070101":
            rating[2] += rate
        elif code == "070102":
            rating[3] += rate
        elif code.startswith("0701") or code.startswith("0702"):
            rating[4] += rate
    # level-3 rows whose linkage split is missing
    if "030101" in codes and not seen_l4["gov"]:
        lt["gov_nominal"] += codes["030101"][0]
    if "030102" in codes and not seen_l4["corp"]:
        lt["corp_nominal"] += codes["030102"][0]
    if "0102" in codes and not any(c.startswith("0102") and len(c) == 6 for c in codes):
        lt["eq_foreign"] += codes["0102"][0]
    foreign_bonds = codes.get("0302", (0.0, ""))[0]
    if foreign_bonds:
        gov_f = sum(r for c, (r, desc) in codes.items() if c.startswith("0302") and len(c) == 6 and ("מדינ" in desc or "ממשל" in desc))
        lt["gov_usd"] += gov_f
        corp_f = max(0.0, foreign_bonds - gov_f)
        hedged = fx_total < corp_f * 0.5
        lt["corp_hedged" if hedged else "corp_usd"] += corp_f
    bucket = max(rating, key=rating.get) if sum(rating.values()) > 0 else None
    # rating split as reported by Maya: high = AA and up, medium = BBB to below AA, low = below BBB, unrated
    ratings = {"high": 0.0, "medium": 0.0, "low": 0.0, "unrated": 0.0}
    for code, (rate, desc) in codes.items():
        if code == "070101":
            ratings["high"] += rate
        elif code == "070102":
            ratings["medium"] += rate
        elif code.startswith("0701") and len(code) == 6:
            ratings["low"] += rate
        elif code.startswith("0702") and len(code) == 6:
            ratings["unrated" if "שאינן מדורגות" in desc or "לא מדורג" in desc else "low"] += rate
    return {"lookthrough": {k: round(v, 5) for k, v in lt.items() if v > 1e-6}, "us_share": round(us * 100, 3),
            "rating_bucket": bucket, "regions": {k: round(v, 5) for k, v in regions.items() if v > 1e-6},
            "ratings": {k: round(v, 5) for k, v in ratings.items() if v > 1e-6}}


def profile_lookthrough(p: dict, names: tuple) -> dict:
    """X-Ray profile (ETFs / index products) -> Excel sections. Linkage is inferred from the name."""
    text = " ".join(n for n in names if n)
    eq = p["equity"]
    lt = {"eq_il": eq.get("IL", 0.0), "eq_foreign": sum(v for k, v in eq.items() if k != "IL"), "cash": p.get("cash", 0.0)}
    b = p["bonds"]
    shekel = "שקלי" in text or "לא צמוד" in text
    if b["il_gov"]:
        lt["gov_nominal" if shekel or "צמוד" not in text else "gov_cpi"] = b["il_gov"]
    if b["il_corp"]:
        lt["corp_nominal" if shekel else "corp_cpi"] = b["il_corp"]
    if b["foreign_gov"]:
        lt["gov_usd"] = b["foreign_gov"]
    if b["foreign_corp"]:
        lt["corp_hedged" if p.get("fx_exposure", 1) < 0.5 else "corp_usd"] = b["foreign_corp"]
    return {k: round(v, 5) for k, v in lt.items() if v > 1e-6}


def _years_to(datestr: str | None) -> float | None:
    try:
        d, m, y = (int(x) for x in (datestr or "").split("/"))
        return max(0.0, (date(y, m, d) - date.today()).days / 365.0)
    except Exception:
        return None


def guess_exposure(name: str) -> str | None:
    n = (name or "").upper()
    if re.search(r"NASDAQ|נאסד|NDX|QQQ", n):
        return "NASDAQ"
    if re.search(r"S&P|SP ?500|500 ", n) or "אס אנד פי" in n:
        return "S&P 500"
    if re.search(r"RUSSELL|ראסל", n):
        return "RUSSELL"
    if re.search(r"STOXX|EURO|אירופ", n):
        return "STOXX 600"
    if re.search(r"EMERGING|מתעוררים|\bEM\b", n):
        return "שאר העולם"
    return None


def _auto(sid: str) -> dict:
    q = pricing_engine.quote(sid)
    qd = q.to_dict()
    out: dict[str, Any] = {"id": sid, "name": q.name, "priced": q.priced, "asset_class": q.asset_class,
                           "market": q.market, "currency": q.currency, "price": q.price, "ticker": q.ticker}
    src: dict[str, str] = {"name": q.source}
    tase = is_tase_id(sid)
    entry = pricing_engine.directory.get(sid) if tase else None
    h = {"input_id": sid, **{k: qd.get(k) for k in ("ticker", "name", "name_en", "market", "asset_class", "currency", "sector")}}

    is_fund = tase and (q.asset_class == "קרנות נאמנות" or (entry and entry.get("type") == 4))
    is_tase_etf = tase and not is_fund and q.asset_class == "קרנות סל"
    if is_fund or is_tase_etf:
        d = xray_engine._maya_fund(sid) or {}
        if d:
            out["kind"] = "etf" if (is_tase_etf or d.get("IsEtf")) else "fund"
            ft = fund_lookthrough(d)
            out.update(ft)
            src.update({"lookthrough": "maya", "us_share": "maya", "rating_bucket": "maya"})
            for k, mk in (("mtd", "MonthYield"), ("ytd", "YearYield"), ("duration", "MachamTotal")):
                if d.get(mk) not in (None, ""):
                    out[k] = float(d[mk])
                    src[k] = "maya"
            try:  # management fee only, as the ACE "management_fee" column; trustee fee kept separately
                out["fee"] = round(float(d.get("ManagementFee") or 0), 4)
                out["trustee_fee"] = round(float(d.get("TrusteeFee") or 0), 4)
                src["fee"] = "maya"
            except (TypeError, ValueError):
                pass
            # index-tracking fund: Maya's flag, or the naming convention of tracking funds (מחקה / KTF / MTF / TTF)
            out["tracker"] = out["kind"] == "etf" or bool(d.get("IsImitatingFund")) or bool(re.search(r"מחקה|מחקות|\b[KMT]TF\b|KTF|MTF|TTF", f"{q.name} {d.get('FundLongName') or ''}"))
            out["fund_label"] = " · ".join(x for x in (d.get("MainClassification"), d.get("SecondaryClassification")) if x)
            lt = out["lookthrough"]
            eq = lt.get("eq_il", 0) + lt.get("eq_foreign", 0)
            total = sum(lt.values())
            if eq >= 0.5 and total > 1.05:
                # Swap/TTF-style index funds report the index exposure AND the collateral; keep the exposure.
                rest = max(0.0, 1 - eq)
                other = total - eq
                out["lookthrough"] = {k: round(v if k in ("eq_il", "eq_foreign") else v * rest / other, 5) for k, v in lt.items()
                                      if k in ("eq_il", "eq_foreign") or rest > 0}
            text = f"{q.name} {d.get('FundLongName') or ''} {out['fund_label']}"
            if out["lookthrough"].get("eq_foreign"):
                out["hedged"] = bool(re.search(r"מנוטרל", text))
                ex = guess_exposure(text)
                if ex:
                    out["exposure"] = ex
                    src["exposure"] = "name"
            return {**out, "sources": src}

    if tase:
        det = xray_engine._maya_sec_details(sid)
        if det:
            for k, mk in (("mtd", "MonthYield"), ("ytd", "AnnualYield")):
                if det.get(mk) is not None:
                    out[k] = float(det[mk])
                    src[k] = "maya"
            if (det.get("Type") or "").strip().startswith("איגרות"):
                out["kind"] = "bond"
                lk = linkage_key(det.get("Linkage"))
                if lk:
                    out["linkage"] = lk
                    src["linkage"] = "maya"
                yrs = _years_to(det.get("RedemptionDate"))
                if yrs is not None:
                    out["duration"] = round(yrs * 0.85, 2)
                    src["duration"] = "estimate"
                    out["maturity"] = det.get("RedemptionDate")
                out["issuer"] = det.get("CompanyName")
            elif "מני" in (det.get("Type") or ""):
                out["kind"] = "equity"
                out["country"] = "ישראל"
                sec = tase_sector(det.get("FullBranch"))
                if sec:
                    out["sector"] = sec
                    src["sector"] = "maya"

    if out.get("kind") is None:
        p = xray_engine.profile(h)
        eq = sum(p["equity"].values())
        bonds = sum(p["bonds"].values())
        if is_fund:
            # A mutual fund whose Maya details could not be fetched (e.g. Maya is down): still a mutual fund.
            # Tracker or managed from its name; fee and holdings are missing until Maya answers again.
            out["incomplete"] = True
        if q.asset_class in ("קרנות סל", "קרנות נאמנות") or p["method"] == "static":
            out["kind"] = "fund" if is_fund else "etf"
            out["tracker"] = (not is_fund) or bool(re.search(r"מחקה|KTF|MTF|TTF|ATF|\bסל\b|index|אינדקס", f"{q.name} {q.name_en}", re.I))
            out["lookthrough"] = profile_lookthrough(p, (q.name, q.name_en))
            src["lookthrough"] = "estimate"
            eqr = p["equity"]
            out["regions"] = {k: round(v, 5) for k, v in {"US": eqr.get("US", 0.0), "EUROPE": eqr.get("EUROPE", 0.0),
                              "ROW": eqr.get("ASIA", 0.0) + eqr.get("EM", 0.0) + eqr.get("OTHER", 0.0)}.items() if v > 1e-6}
            ex = guess_exposure(f"{q.name} {q.name_en}")
            if ex:
                out["exposure"] = ex
                src["exposure"] = "name"
            if out["lookthrough"].get("eq_foreign"):
                out["hedged"] = bool(re.search(r"מנוטרל|hedged|\(4A\)", f"{q.name} {q.name_en}", re.I))
            us = p["equity"].get("US", 0.0) + p["bonds"].get("foreign_gov", 0.0) + p["bonds"].get("foreign_corp", 0.0)
            out["us_share"] = round(us * 100, 2)
        elif eq >= 0.5:
            out["kind"] = "equity"
            if q.market == "US":
                out["country"] = "ארה״ב"
                info = xray_engine._yf_info(q.ticker)
                gics = GICS_HE.get(info.get("sector") or q.sector or "")
                if gics:
                    out["exposure"] = gics
                    src["exposure"] = "yfinance"
        elif bonds >= 0.5:
            out["kind"] = "bond"
        else:
            out["kind"] = "other"
        if p.get("fee") is not None and out["kind"] == "etf":
            out["fee"] = p["fee"]
            src["fee"] = "estimate"
        if bonds and out.get("duration") is None:
            d = sum(p["bonds"][b] * p["durations"][b] for b in p["bonds"]) / bonds
            out["duration"] = round(d, 2)
            src["duration"] = "estimate"
    if q.market == "US" and out.get("ytd") is None:
        perf = _yf_perf(q.ticker)
        out.update(perf)
        src.update({k: "yfinance" for k in perf})
    return {**out, "sources": src}


def _yf_perf(symbol: str) -> dict:
    try:
        import yfinance as yf
        hist = yf.Ticker(symbol).history(period="ytd", auto_adjust=True)["Close"]
        if hist.empty:
            return {}
        last = float(hist.iloc[-1])
        first = float(hist.iloc[0])
        month = hist[hist.index.month == hist.index[-1].month]
        prev = hist[hist.index < month.index[0]]
        base_m = float(prev.iloc[-1]) if len(prev) else float(month.iloc[0])
        return {"ytd": round((last / first - 1) * 100, 2), "mtd": round((last / base_m - 1) * 100, 2)}
    except Exception as e:
        log.info("yfinance perf failed for %s: %s", symbol, e)
        return {}


def auto_data(sid: str, refresh: bool = False) -> dict:
    hit = _cache.get(sid)
    if hit and not refresh and time.time() - hit[0] < TTL:
        return hit[1]
    try:
        d = _auto(sid)
    except Exception as e:  # never break the sheet because one security failed
        log.warning("secdata auto failed for %s: %s", sid, e)
        d = {"id": sid, "name": f"Unknown #{sid}", "priced": False, "kind": "other", "sources": {}, "incomplete": True}
    # incomplete answers (source outage) are kept only ~2 minutes so the next run retries
    _cache[sid] = (time.time() - (TTL - 120 if d.get("incomplete") else 0), d)
    return d


def merged(auto: dict, manual: dict | None) -> dict:
    out = dict(auto)
    src = dict(auto.get("sources") or {})
    for k, v in (manual or {}).items():
        if k.startswith("_"):
            continue
        out[k] = v
        src[k] = "manual"
    out["sources"] = src
    if manual:
        out["manual_by"] = manual.get("_by")
        out["manual_at"] = manual.get("_at")
    return out
