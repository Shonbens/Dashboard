"""
4-Tier "Waterfall" pricing engine for Israeli + global instruments.

Tier 1  yfinance            US tickers, and TASE shares/ETFs (7-digit ID -> SYMBOL.TA via the Maya directory)
Tier 2  pymaya (TASE Maya)  Mutual-fund NAV, plus any other TASE security Maya knows (bonds, ETFs, T-bills)
Tier 3  Bizportal scrape    Last resort for Israeli bonds / small caps
Tier 4  Fallback stub       "Unknown #ID", price 0.0 - never breaks a batch

All Israeli prices are quoted in agorot and are normalised to shekels (/100).
"""
from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any

import requests
import yfinance as yf
from bs4 import BeautifulSoup

log = logging.getLogger("pricing")

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
}

PRICE_TTL_SECONDS = 300          # live quotes
DIRECTORY_TTL_SECONDS = 12 * 3600  # TASE securities directory
FX_TTL_SECONDS = 600

# Optional manual overrides: TASE ID -> Yahoo ticker. The Maya directory resolves
# almost every listed share automatically; add entries here only for edge cases.
STATIC_TASE_MAP: dict[str, str] = {}

# Currencies quoted in minor units on Yahoo -> (major currency, divisor)
MINOR_CURRENCIES = {"ILA": ("ILS", 100.0), "GBp": ("GBP", 100.0), "GBX": ("GBP", 100.0), "ZAc": ("ZAR", 100.0)}

# Maya SubTypeDesc -> asset class (Hebrew label used across the UI)
ASSET_CLASS_RULES = [
    ("mutual fund", "קרנות נאמנות"),
    ("etf", "קרנות סל"),
    ("participating unit", "קרנות סל"),
    ("government bond", "אג\"ח ממשלתי"),
    ("treasury bill", "אג\"ח ממשלתי"),
    ("bond", "אג\"ח קונצרני"),
    ("warrant", "כתבי אופציה"),
    ("share", "מניות"),
]


def classify_subtype(subtype: str | None) -> str:
    s = (subtype or "").lower()
    for key, label in ASSET_CLASS_RULES:
        if key in s:
            return label
    return "אחר"


def normalize_identifier(raw: Any) -> str:
    """'604611.0' -> '604611', ' aapl ' -> 'AAPL', '05113428' -> '5113428'."""
    if raw is None:
        return ""
    if isinstance(raw, float) and raw.is_integer():
        raw = int(raw)
    s = str(raw).strip().upper()
    if re.fullmatch(r"\d+\.0+", s):
        s = s.split(".")[0]
    if s.isdigit():
        s = s.lstrip("0") or "0"
    return s


def is_tase_id(identifier: str) -> bool:
    return identifier.isdigit() and 3 <= len(identifier) <= 9


@dataclass
class Quote:
    input_id: str
    ticker: str
    name: str
    name_en: str = ""
    market: str = "OTHER"           # IL | US | OTHER
    asset_class: str = "אחר"
    sector: str = ""
    currency: str = "ILS"           # major currency of `price`
    price: float = 0.0              # in major currency (₪, $, ...)
    change_pct: float | None = None
    source: str = "fallback"
    tier: int = 4
    priced: bool = False
    as_of: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


class _TTLCache:
    def __init__(self, ttl: float):
        self.ttl = ttl
        self._d: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str):
        with self._lock:
            hit = self._d.get(key)
            if hit and time.time() - hit[0] < self.ttl:
                return hit[1]
            return None

    def set(self, key: str, value: Any):
        with self._lock:
            self._d[key] = (time.time(), value)

    def clear(self):
        with self._lock:
            self._d.clear()


# --------------------------------------------------------------------------- #
#  TASE directory (Maya): ID -> symbol, Hebrew/English names, security type
# --------------------------------------------------------------------------- #
class TaseDirectory:
    def __init__(self):
        self._lock = threading.Lock()
        self._loaded_at = 0.0
        self._by_id: dict[str, dict] = {}

    def _load(self):
        from pymaya.maya_security import MayaSecurity
        from pymaya.utils import Language

        ms = MayaSecurity(logger=logging.getLogger("pymaya"), session=requests.Session())
        en = ms.get_all_securities(Language.ENGLISH) or []
        he = ms.get_all_securities(Language.HEBREW) or []
        he_names = {(s.get("Id"), s.get("Type")): s.get("Name") for s in he}
        by_id: dict[str, dict] = {}
        for s in en:
            sid, typ = s.get("Id"), s.get("Type")
            # Only tradable instruments (1 = securities, 4 = mutual funds)
            if typ not in (1, 4) or not sid:
                continue
            by_id[normalize_identifier(sid)] = {
                "id": sid,
                "symbol": s.get("Smb"),
                "name_en": (s.get("Name") or "").strip(),
                "name_he": (he_names.get((sid, typ)) or s.get("Name") or "").strip(),
                "type": typ,
                "subtype": s.get("SubTypeDesc") or "",
                "isin": s.get("ISIN"),
            }
        self._by_id = by_id
        self._loaded_at = time.time()
        log.info("TASE directory loaded: %d instruments", len(by_id))

    def ensure(self):
        if self._by_id and time.time() - self._loaded_at < DIRECTORY_TTL_SECONDS:
            return
        with self._lock:
            if self._by_id and time.time() - self._loaded_at < DIRECTORY_TTL_SECONDS:
                return
            try:
                self._load()
            except Exception as e:  # directory is a best-effort enhancement
                log.warning("Could not load TASE directory: %s", e)
                self._loaded_at = time.time() - DIRECTORY_TTL_SECONDS + 120  # retry in 2 min

    def get(self, sid: str) -> dict | None:
        self.ensure()
        return self._by_id.get(normalize_identifier(sid))

    def search(self, q: str, limit: int = 12) -> list[dict]:
        self.ensure()
        q = q.strip()
        if not q:
            return []
        ql = q.lower()
        exact, starts, contains = [], [], []
        for e in self._by_id.values():
            fields = [e["id"], (e["symbol"] or "").lower(), e["name_en"].lower(), e["name_he"]]
            if ql in (e["id"], (e["symbol"] or "").lower()):
                exact.append(e)
            elif any(f.startswith(ql) for f in fields):
                starts.append(e)
            elif any(ql in f for f in fields):
                contains.append(e)
            if len(exact) + len(starts) >= limit:
                break
        out = (exact + starts + contains)[:limit]
        return [
            {
                "id": e["id"],
                "symbol": e["symbol"],
                "name": e["name_he"],
                "name_en": e["name_en"],
                "asset_class": classify_subtype("mutual fund" if e["type"] == 4 else e["subtype"]),
                "market": "IL",
            }
            for e in out
        ]

    @property
    def size(self) -> int:
        return len(self._by_id)


# --------------------------------------------------------------------------- #
#  Pricing engine
# --------------------------------------------------------------------------- #
class PricingEngine:
    def __init__(self):
        self.directory = TaseDirectory()
        self._cache = _TTLCache(PRICE_TTL_SECONDS)
        self._fx_cache = _TTLCache(FX_TTL_SECONDS)
        self._meta_cache = _TTLCache(24 * 3600)   # yfinance .info (names/sectors)
        self._http = requests.Session()
        self._http.headers.update(HTTP_HEADERS)
        self._maya_funds = None
        self._maya_sec = None

    # ---- public ------------------------------------------------------------
    def quote(self, raw_id: Any, refresh: bool = False) -> Quote:
        ident = normalize_identifier(raw_id)
        if not ident:
            return self._fallback(str(raw_id))
        if not refresh:
            cached = self._cache.get(ident)
            if cached:
                return cached
        q = None
        for tier in (self._tier1_yfinance, self._tier2_maya, self._tier3_bizportal):
            try:
                q = tier(ident)
            except Exception as e:
                log.info("%s failed for %s: %s", tier.__name__, ident, e)
                q = None
            if q and q.price > 0:
                break
            q = None
        q = q or self._fallback(ident)
        if q.priced:
            self._cache.set(ident, q)
        return q

    def fx_to_ils(self, currency: str) -> float:
        """Units of ILS per 1 unit of `currency`."""
        currency = (currency or "ILS").upper()
        if currency == "ILS":
            return 1.0
        cached = self._fx_cache.get(currency)
        if cached:
            return cached
        rate = None
        for pair in (f"{currency}ILS=X", "ILS=X" if currency == "USD" else None):
            if not pair:
                continue
            try:
                rate = float(yf.Ticker(pair).fast_info.last_price)
                if rate and rate > 0:
                    break
            except Exception as e:
                log.info("FX %s failed: %s", pair, e)
                rate = None
        if not rate:
            rate = {"USD": 3.7, "EUR": 4.0, "GBP": 4.7}.get(currency, 1.0)
            log.warning("Using static FX fallback for %s: %s", currency, rate)
            return rate  # don't cache fallbacks
        self._fx_cache.set(currency, rate)
        return rate

    def clear_cache(self):
        self._cache.clear()
        self._fx_cache.clear()

    # ---- tiers ---------------------------------------------------------------
    def _tier1_yfinance(self, ident: str) -> Quote | None:
        entry = None
        if is_tase_id(ident):
            entry = self.directory.get(ident)
            yf_symbol = STATIC_TASE_MAP.get(ident)
            if not yf_symbol:
                sym = (entry or {}).get("symbol")
                # Yahoo only carries TASE shares/ETFs with simple symbols (bonds look like "ABOU.B1")
                if not entry or entry["type"] != 1 or not sym or "." in sym or " " in sym:
                    return None
                yf_symbol = f"{sym}.TA"
        else:
            yf_symbol = ident

        t = yf.Ticker(yf_symbol)
        fi = t.fast_info
        price = fi.last_price
        if price is None or not price == price or price <= 0:  # None / NaN / 0
            return None
        prev = fi.previous_close
        raw_ccy = fi.currency or "USD"
        ccy, div = MINOR_CURRENCIES.get(raw_ccy, (raw_ccy.upper(), 1.0))
        if yf_symbol.upper().endswith(".TA"):
            ccy, div = "ILS", 100.0  # TASE quotes are always in agorot
        price = float(price) / div
        change = (float(fi.last_price) / float(prev) - 1) * 100 if prev else None

        is_il = yf_symbol.upper().endswith(".TA")
        meta = self._yf_meta(yf_symbol) if not entry else {}
        if entry:
            name, name_en = entry["name_he"], entry["name_en"]
            asset_class = classify_subtype(entry["subtype"])
        else:
            name = meta.get("name") or yf_symbol
            name_en = name
            asset_class = {"ETF": "קרנות סל", "MUTUALFUND": "קרנות נאמנות"}.get(meta.get("quote_type"), "מניות")
        market = "IL" if is_il else ("US" if ccy == "USD" and "." not in yf_symbol else "OTHER")
        return Quote(
            input_id=ident,
            ticker=yf_symbol,
            name=name,
            name_en=name_en,
            market=market,
            asset_class=asset_class,
            sector=meta.get("sector", ""),
            currency=ccy,
            price=round(price, 4),
            change_pct=round(change, 2) if change is not None else None,
            source="yfinance",
            tier=1,
            priced=True,
        )

    def _yf_meta(self, symbol: str) -> dict:
        cached = self._meta_cache.get(symbol)
        if cached is not None:
            return cached
        meta = {}
        try:
            info = yf.Ticker(symbol).info or {}
            meta = {
                "name": info.get("longName") or info.get("shortName"),
                "sector": info.get("sector") or info.get("category") or "",
                "quote_type": info.get("quoteType"),
            }
        except Exception as e:
            log.info("yfinance info failed for %s: %s", symbol, e)
        self._meta_cache.set(symbol, meta)
        return meta

    def _maya(self):
        if self._maya_funds is None:
            from pymaya.maya_funds import MayaFunds
            from pymaya.maya_security import MayaSecurity

            lg = logging.getLogger("pymaya")
            self._maya_funds = MayaFunds(logger=lg, session=requests.Session())
            self._maya_sec = MayaSecurity(logger=lg, session=requests.Session())
        return self._maya_funds, self._maya_sec

    def _tier2_maya(self, ident: str) -> Quote | None:
        if not is_tase_id(ident):
            return None
        funds, secs = self._maya()
        entry = self.directory.get(ident)
        from_date = date.today() - timedelta(days=14)
        is_fund = entry is None or entry["type"] == 4

        if is_fund:
            rows = funds.get_price_history_chunk(ident, from_date=from_date, to_date=date.today(), page=1)
            rows = [r for r in (rows or []) if r.get("purchasePrice")]
            if not rows:
                if entry is not None:
                    return None
            else:
                rows.sort(key=lambda r: r.get("tradeDate", ""), reverse=True)
                last = float(rows[0]["sellPrice"] or rows[0]["purchasePrice"])
                prev = float(rows[1]["sellPrice"] or rows[1]["purchasePrice"]) if len(rows) > 1 else None
                name, name_en = (entry["name_he"], entry["name_en"]) if entry else self._maya_fund_names(ident)
                return Quote(
                    input_id=ident,
                    ticker=ident,
                    name=name or f"קרן {ident}",
                    name_en=name_en,
                    market="IL",
                    asset_class="קרנות נאמנות",
                    currency="ILS",
                    price=round(last / 100.0, 4),
                    change_pct=round((last / prev - 1) * 100, 2) if prev else None,
                    source="pymaya (NAV)",
                    tier=2,
                    priced=True,
                )

        # Non-fund TASE security (bond, ETF, T-bill...) - Maya end-of-day trading data
        data = secs.get_price_history_chunk(ident, from_date, date.today(), 1)
        items = (data or {}).get("Items") or []
        items = [i for i in items if i.get("CloseRate")]
        if not items:
            return None
        last = float(items[0]["CloseRate"])
        change = items[0].get("Change")
        return Quote(
            input_id=ident,
            ticker=(entry or {}).get("symbol") or ident,
            name=(entry or {}).get("name_he") or ident,
            name_en=(entry or {}).get("name_en") or "",
            market="IL",
            asset_class=classify_subtype((entry or {}).get("subtype")),
            currency="ILS",
            price=round(last / 100.0, 4),
            change_pct=float(change) if change is not None else None,
            source="pymaya (TASE)",
            tier=2,
            priced=True,
        )

    def _maya_fund_names(self, ident: str) -> tuple[str, str]:
        from pymaya.utils import Language

        funds, _ = self._maya()
        try:
            he = funds.get_details(ident, Language.HEBREW) or {}
            en = funds.get_details(ident, Language.ENGLISH) or {}
            return he.get("FundLongName") or he.get("FundShortName") or "", en.get("FundLongName") or ""
        except Exception:
            return "", ""

    def _tier3_bizportal(self, ident: str) -> Quote | None:
        if not is_tase_id(ident):
            return None
        url = f"https://www.bizportal.co.il/capitalmarket/quote/generalview/{ident}"
        r = self._http.get(url, timeout=12)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "lxml")
        h1 = soup.select_one("h1.paper_h1")
        rate = soup.select_one("#paper_rate .num, .paper_rate .num")
        if not h1 or not rate:  # unknown IDs redirect to a search page
            return None
        price_txt = rate.get_text(strip=True).replace(",", "")
        try:
            price = float(price_txt)
        except ValueError:
            return None
        if price <= 0:
            return None
        name = re.sub(r"^(מניית|קרן|תעודת סל)\s+", "", h1.get_text(" ", strip=True))
        change = None
        ch = soup.select_one("#paper_change .num")
        if ch:
            try:
                change = float(ch.get_text(strip=True).replace("%", "").replace(",", ""))
            except ValueError:
                pass
        path = r.url.lower()
        asset_class = "אג\"ח קונצרני" if "/bonds/" in path else ("קרנות נאמנות" if "/mutualfunds/" in path else "מניות")
        return Quote(
            input_id=ident,
            ticker=ident,
            name=name,
            market="IL",
            asset_class=asset_class,
            currency="ILS",
            price=round(price / 100.0, 4),
            change_pct=change,
            source="Bizportal",
            tier=3,
            priced=True,
        )

    @staticmethod
    def _fallback(ident: str) -> Quote:
        return Quote(
            input_id=ident,
            ticker=ident,
            name=f"Unknown #{ident}",
            market="IL" if is_tase_id(ident) else "OTHER",
            price=0.0,
            source="fallback",
            tier=4,
            priced=False,
        )


engine = PricingEngine()
