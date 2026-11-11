"""
Fund look-through ("X-Ray") engine.

Every holding is decomposed into a normalised exposure *profile* (fractions of the holding's value):

    equity   {IL, US, EUROPE, ASIA, EM, OTHER}
    bonds    {il_gov, il_corp, foreign_gov, foreign_corp}  + duration per bucket
    cash, other
    fx_exposure   share of value exposed to foreign currency (for an ILS-based investor)
    sectors       {hebrew sector: fraction of holding}  (equity part)
    top_holdings  [{key, name, weight}]

Resolution order per holding
  1. Israeli mutual fund      -> live Maya disclosure tree + actual fund holdings (pymaya)
  2. Known ETF / index fund   -> static index profile (ticker / ISIN / name pattern), overlaid with live
                                 yfinance fund data (top holdings, sectors) from the profile's proxy ETF
  3. Unknown US ETF           -> live yfinance fund data
  4. Single security          -> 100% itself (stock: sector + region; bond: duration from redemption date)
  5. Default by asset class
"""
from __future__ import annotations

import logging
import re
import threading
import time
from copy import deepcopy
from typing import Any

import requests
import yfinance as yf

from pricing import engine as pricing_engine, is_tase_id, normalize_identifier

log = logging.getLogger("xray")

EQ_REGIONS = ("IL", "US", "EUROPE", "ASIA", "EM", "OTHER")
BOND_BUCKETS = ("il_gov", "il_corp", "foreign_gov", "foreign_corp")

REGION_LABEL = {"IL": "ישראל", "US": "ארה״ב", "EUROPE": "אירופה", "ASIA": "אסיה ופסיפיק", "EM": "שווקים מתעוררים", "OTHER": "אחר"}
ASSET_LABEL = {"equity": "מניות", "gov_bonds": "אג״ח ממשלתי", "corp_bonds": "אג״ח קונצרני", "cash": "מזומן ופיקדונות", "other": "אחר"}

# yfinance sector keys / names -> Hebrew
YF_SECTOR = {
    "technology": "טכנולוגיה", "financialservices": "פיננסים", "financial": "פיננסים", "healthcare": "בריאות",
    "consumercyclical": "צריכה מחזורית", "consumerdefensive": "צריכה בסיסית", "industrials": "תעשייה",
    "energy": "אנרגיה", "basicmaterials": "חומרי גלם", "realestate": "נדל״ן", "communicationservices": "תקשורת",
    "utilities": "תשתיות",
}
# Maya FullBranch keywords -> Hebrew sector (first match wins)
IL_BRANCH = [
    ("בנק", "פיננסים"), ("ביטוח", "פיננסים"), ("פיננס", "פיננסים"), ("נדל", "נדל״ן"), ("בינוי", "נדל״ן"),
    ("טכנולוג", "טכנולוגיה"), ("תוכנה", "טכנולוגיה"), ("מוליכים", "טכנולוגיה"), ("אלקטרוניקה", "טכנולוגיה"),
    ("ביומד", "בריאות"), ("פארמה", "בריאות"), ("נפט", "אנרגיה"), ("גז", "אנרגיה"), ("אנרגיה", "אנרגיה"),
    ("תקשורת", "תקשורת"), ("מזון", "צריכה בסיסית"), ("מסחר", "צריכה מחזורית"), ("שירותים", "צריכה מחזורית"),
    ("כימיה", "חומרי גלם"), ("תעשי", "תעשייה"), ("ביטחו", "תעשייה"), ("השקעה ואחזקות", "אחזקות"),
]


def sector_from_yf(s: str | None) -> str | None:
    if not s:
        return None
    return YF_SECTOR.get(re.sub(r"[^a-z]", "", s.lower()))


def sector_from_branch(branch: str | None) -> str | None:
    if not branch:
        return None
    for kw, label in IL_BRANCH:
        if kw in branch:
            return label
    return branch.split("-")[0].strip() or None


_SUFFIX = re.compile(
    r"\b(inc|corp|corporation|co|company|ltd|limited|plc|sa|nv|ag|holdings?|group|class [abc]|cl [abc]|the|adr|com|ord)\b\.?",
    re.I,
)


def name_key(name: str | None) -> str:
    """Normalise company names so 'NVIDIA CORP', 'NVIDIA Corporation' and 'NVIDIA Corp' collide."""
    s = (name or "").lower().replace("&", " and ")
    s = re.sub(r"[.,'\"()]", " ", s)
    s = _SUFFIX.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# --------------------------------------------------------------------------- #
#  Static look-through dictionary (approximate index compositions)
# --------------------------------------------------------------------------- #
def _p(equity=None, il_gov=0.0, il_corp=0.0, foreign_gov=0.0, foreign_corp=0.0, cash=0.0, other=0.0,
       dur=None, fx=0.0, sectors=None, proxy=None, label=""):
    return {
        "equity": {r: float((equity or {}).get(r, 0.0)) for r in EQ_REGIONS},
        "bonds": {"il_gov": il_gov, "il_corp": il_corp, "foreign_gov": foreign_gov, "foreign_corp": foreign_corp},
        "durations": {**{b: 0.0 for b in BOND_BUCKETS}, **(dur or {})},
        "cash": cash,
        "other": other,
        "fx_exposure": fx,
        "sectors": sectors or {},
        "top_holdings": [],
        "proxy": proxy,
        "label": label,
        "fee": None,  # annual cost in % (management + trustee / expense ratio); None = unknown
    }


IL_EQ_SECTORS = {"פיננסים": 0.36, "טכנולוגיה": 0.13, "נדל״ן": 0.12, "תעשייה": 0.09, "אנרגיה": 0.08,
                 "בריאות": 0.06, "חומרי גלם": 0.06, "תקשורת": 0.04, "צריכה בסיסית": 0.06}

INDEX_PROFILES: dict[str, dict] = {
    "sp500": _p({"US": 1}, fx=1, proxy="SPY", label="S&P 500"),
    "ndx100": _p({"US": 1}, fx=1, proxy="QQQ", label="Nasdaq-100"),
    "us_total": _p({"US": 1}, fx=1, proxy="VTI", label="US Total Market"),
    "msci_world": _p({"US": 0.72, "EUROPE": 0.15, "ASIA": 0.09, "OTHER": 0.04}, fx=1, proxy="URTH", label="MSCI World"),
    "acwi": _p({"US": 0.64, "EUROPE": 0.13, "ASIA": 0.08, "EM": 0.11, "OTHER": 0.04}, fx=1, proxy="ACWI", label="MSCI ACWI"),
    "intl_dev": _p({"EUROPE": 0.6, "ASIA": 0.32, "OTHER": 0.08}, fx=1, proxy="EFA", label="Developed ex-US"),
    "em": _p({"EM": 1}, fx=1, proxy="EEM", label="Emerging Markets"),
    "europe": _p({"EUROPE": 1}, fx=1, proxy="VGK", label="Europe"),
    "israel_eq": _p({"IL": 1}, fx=0, sectors=IL_EQ_SECTORS, label="Israel equities"),
    "ta35": _p({"IL": 1}, sectors=IL_EQ_SECTORS, label="ת״א 35"),
    "ta125": _p({"IL": 1}, sectors=IL_EQ_SECTORS, label="ת״א 125"),
    "il_gov": _p(il_gov=1, dur={"il_gov": 6.0}, label="אג״ח ממשלתי ישראלי"),
    "il_corp": _p(il_corp=1, dur={"il_corp": 3.5}, label="תל בונד / אג״ח קונצרני"),
    "il_money_market": _p(cash=0.6, il_gov=0.4, dur={"il_gov": 0.3}, label="קרן כספית"),
    "us_agg": _p(foreign_gov=0.72, foreign_corp=0.28, dur={"foreign_gov": 6.0, "foreign_corp": 6.8}, fx=1, proxy="AGG", label="US Aggregate Bonds"),
    "ust_long": _p(foreign_gov=1, dur={"foreign_gov": 16.0}, fx=1, proxy="TLT", label="US Treasuries 20Y+"),
    "ust_mid": _p(foreign_gov=1, dur={"foreign_gov": 7.0}, fx=1, proxy="IEF", label="US Treasuries 7-10Y"),
    "ust_short": _p(foreign_gov=1, dur={"foreign_gov": 1.9}, fx=1, proxy="SHY", label="US Treasuries 1-3Y"),
    "ust_bills": _p(foreign_gov=1, dur={"foreign_gov": 0.1}, fx=1, label="US T-Bills"),
    "us_ig": _p(foreign_corp=1, dur={"foreign_corp": 8.3}, fx=1, proxy="LQD", label="US IG Corporate"),
    "us_hy": _p(foreign_corp=1, dur={"foreign_corp": 3.2}, fx=1, proxy="HYG", label="US High Yield"),
    "gold": _p(other=1, fx=1, label="Gold"),
}

ETF_MAP = {
    **dict.fromkeys(["SPY", "VOO", "IVV", "SPLG", "CSPX", "CSPX.L", "SXR8.DE", "VUAA.L", "VUSA.L", "IUSA.L"], "sp500"),
    **dict.fromkeys(["QQQ", "QQQM", "CNDX.L", "EQQQ.L", "SXRV.DE"], "ndx100"),
    **dict.fromkeys(["VTI", "ITOT", "SCHB"], "us_total"),
    **dict.fromkeys(["URTH", "IWDA.L", "SWDA.L", "EUNL.DE"], "msci_world"),
    **dict.fromkeys(["ACWI", "VT", "SSAC.L", "VWRA.L", "VWRL.L"], "acwi"),
    **dict.fromkeys(["EFA", "VEA", "IEFA"], "intl_dev"),
    **dict.fromkeys(["EEM", "VWO", "IEMG"], "em"),
    **dict.fromkeys(["VGK", "IEUR", "EZU"], "europe"),
    "EIS": "israel_eq",
    **dict.fromkeys(["AGG", "BND", "IUSB"], "us_agg"),
    **dict.fromkeys(["TLT", "VGLT", "EDV"], "ust_long"),
    **dict.fromkeys(["IEF", "VGIT"], "ust_mid"),
    **dict.fromkeys(["SHY", "VGSH"], "ust_short"),
    **dict.fromkeys(["BIL", "SGOV", "SHV"], "ust_bills"),
    **dict.fromkeys(["LQD", "VCIT", "IGIB"], "us_ig"),
    **dict.fromkeys(["HYG", "JNK"], "us_hy"),
    **dict.fromkeys(["GLD", "IAU", "SGOL"], "gold"),
}
ISIN_MAP = {
    "IE00B5BMR087": "sp500",   # iShares Core S&P 500 UCITS (CSPX)
    "IE00B3YCGJ38": "sp500",   # Invesco S&P 500 UCITS
    "IE00B4L5Y983": "msci_world",  # iShares Core MSCI World UCITS (IWDA)
    "IE00B53SZB19": "ndx100",  # iShares Nasdaq 100 UCITS (CNDX)
    "IE00BK5BQT80": "acwi",    # Vanguard FTSE All-World UCITS Acc (VWRA)
    "US78462F1030": "sp500",   # SPY
}
# Hebrew / English fund-name patterns -> index profile (TASE ETFs and fund fallbacks)
NAME_PATTERNS = [
    (r"S&P\s?500|SP\s?500|אס אנד פי", "sp500"),
    (r"NDX|NASDAQ|נאסד", "ndx100"),
    (r"ACWI|AC WORLD|ALL.?WORLD|כל העולם", "acwi"),
    (r"MSCI WORLD|עולמי|WORLD", "msci_world"),
    (r"שווקים מתעוררים|EMERGING|\bEM\b", "em"),
    (r"אירופה|EUROPE|STOXX|EURO", "europe"),
    (r"ת\"?א.?35|TA.?35", "ta35"),
    (r"ת\"?א.?(125|90)|TA.?125", "ta125"),
    (r"תל.?בונד|TEL.?BOND|קונצרני", "il_corp"),
    (r"תל.?גוב|TEL.?GOV|ממשלתי|מדינה|שקלי", "il_gov"),
    (r"כספית|MONEY", "il_money_market"),
    (r"זהב|GOLD", "gold"),
    (r"IBOXX|INVESTMENT GRADE|קונצרני.*ארה", "us_ig"),
    (r"HIGH YIELD|תשואה גבוהה", "us_hy"),
]


HEDGED = re.compile(r"מנוטרל|HEDGED", re.I)
TASE_EXPOSURE_CODE = re.compile(r"\((\d)([0A-FX])\)")


def fx_from_name(*names: str | None) -> float | None:
    """TASE fund names carry an exposure code: (shares digit)(FX letter). 0 = no FX, A = up to 10%, D = >120%.
    'מנוטרלת מט"ח' marks a currency-hedged fund."""
    for n in names:
        if not n:
            continue
        if HEDGED.search(n):
            return 0.0
        m = TASE_EXPOSURE_CODE.search(n)
        if m:
            return {"0": 0.0, "A": 0.05, "D": 1.0}.get(m.group(2).upper())
    return None


def match_name_pattern(*names: str | None) -> str | None:
    for n in names:
        if not n:
            continue
        for pat, key in NAME_PATTERNS:
            if re.search(pat, n, re.I):
                return key
    return None


# --------------------------------------------------------------------------- #
#  Engine
# --------------------------------------------------------------------------- #
class XRayEngine:
    TTL = 24 * 3600

    def __init__(self):
        self._cache: dict[str, tuple[float, dict]] = {}
        self._lock = threading.Lock()
        self._maya_funds = None
        self._maya_sec = None

    # ---- cache helpers ----
    def _cached(self, key: str, fn):
        with self._lock:
            hit = self._cache.get(key)
            if hit and time.time() - hit[0] < self.TTL:
                return hit[1]
        val = fn()
        if val is not None:
            with self._lock:
                self._cache[key] = (time.time(), val)
        return val

    # Circuit breaker: when Maya keeps failing (e.g. 503 during an outage) stop calling it for a while,
    # instead of waiting on every security in the portfolio.
    _maya_fail = 0
    _maya_down_until = 0.0

    def _maya_ok(self) -> bool:
        return time.time() >= self._maya_down_until

    def _maya_result(self, ok: bool):
        if ok:
            self._maya_fail = 0
        else:
            self._maya_fail += 1
            if self._maya_fail >= 3:
                self._maya_down_until = time.time() + 120
                log.warning("Maya unavailable – pausing Maya calls for 2 minutes")

    def maya_down(self) -> bool:
        return not self._maya_ok()

    def _maya(self):
        if self._maya_funds is None:
            from pymaya.maya_funds import MayaFunds
            from pymaya.maya_security import MayaSecurity

            lg = logging.getLogger("pymaya")
            self._maya_funds = MayaFunds(logger=lg, session=requests.Session())
            self._maya_sec = MayaSecurity(logger=lg, session=requests.Session())
        return self._maya_funds, self._maya_sec

    # ---- data fetchers ----
    def _yf_fund_data(self, symbol: str) -> dict | None:
        def fetch():
            try:
                fd = yf.Ticker(symbol).funds_data
                top = []
                th = fd.top_holdings
                if th is not None and len(th):
                    for sym, row in th.iterrows():
                        top.append({"key": name_key(row.get("Name")), "symbol": sym, "name": row.get("Name"), "weight": float(row.get("Holding Percent") or 0)})
                sectors = {}
                for k, v in (fd.sector_weightings or {}).items():
                    lab = sector_from_yf(k)
                    if lab and v:
                        sectors[lab] = sectors.get(lab, 0) + float(v)
                ac = fd.asset_classes or {}
                return {"top": top, "sectors": sectors, "asset_classes": ac}
            except Exception as e:
                log.info("yfinance funds_data failed for %s: %s", symbol, e)
                return {}
        return self._cached(f"yf_fund:{symbol}", fetch) or None

    def _yf_info(self, symbol: str) -> dict:
        def fetch():
            try:
                info = yf.Ticker(symbol).info or {}
                return {
                    "sector": info.get("sector"), "beta": info.get("beta"), "quote_type": info.get("quoteType"),
                    "name": info.get("longName") or info.get("shortName"), "country": info.get("country"),
                    "expense_ratio": info.get("netExpenseRatio") or info.get("annualReportExpenseRatio"),
                }
            except Exception:
                return {}
        return self._cached(f"yf_info:{symbol}", fetch) or {}

    MAYA_V1 = "https://maya.tase.co.il/api/v1/funds"

    def _maya_fund_v1(self, sid: str) -> dict | None:
        """Maya's current fund API (Nov 2026), converted to the field names of the older API the rest of the code uses.
        /funds/mutual/{id} or /funds/etf/{id}: fees, type, classification · /funds/{id}/distribution-graph: the disclosure
        breakdown (same codes: 01 equity, 0301.. bonds by type/linkage, 05 cash, 06 FX, 07 ratings, 08 duration) ·
        POST /funds/{id}/assets: holdings (for the top-holdings look-through). Returns None on failure, {} when not a fund."""
        sess = getattr(self, "_v1_session", None) or requests.Session()
        self._v1_session = sess
        hdr = {"Accept": "application/json", "User-Agent": "Mozilla/5.0", "Accept-Language": "he-IL"}
        info, is_etf = None, False
        for kind in ("mutual", "etf"):
            r = sess.get(f"{self.MAYA_V1}/{kind}/{sid}", headers=hdr, timeout=15)
            if r.status_code == 404:
                continue
            r.raise_for_status()
            info, is_etf = r.json(), kind == "etf"
            break
        if info is None:
            return {}
        chart: list[dict] = []
        try:
            g = sess.get(f"{self.MAYA_V1}/{sid}/distribution-graph", headers=hdr, timeout=15)
            g.raise_for_status()

            def walk(node):
                for it in node.get("items") or []:
                    chart.append({"LevelCd": it.get("key") or "", "ExposureRate": it.get("value"), "LevelDesc": it.get("name") or ""})
                    walk(it)
            walk((g.json() or {}).get("fundGraphItem") or {})
        except Exception as e:
            log.info("Maya distribution-graph failed for %s: %s", sid, e)
        assets = []
        try:
            a = sess.post(f"{self.MAYA_V1}/{sid}/assets", json={}, headers=hdr, timeout=15)
            if a.ok:
                assets = [{"AssetName": x.get("assetName"), "FundPercentage": x.get("fundPercentage"), "AssetTypeName": x.get("assetTypeName")}
                          for x in a.json() or []]
        except Exception as e:
            log.info("Maya assets failed for %s: %s", sid, e)
        cls = info.get("classification") or {}
        yl = info.get("yields") or {}
        dur = next((c["ExposureRate"] for c in chart if c["LevelCd"] == "0801"), None)
        imitating = any("מחקה" in (f.get("title") or "") and f.get("enabled") for f in info.get("features") or [])
        return {
            "FundId": info.get("fundId"), "FundName": info.get("name"), "FundLongName": info.get("longName"),
            "ManagementFee": info.get("managementFee"), "TrusteeFee": info.get("trusteeFee"), "VariableFee": info.get("variableFee"),
            "IsImitatingFund": imitating or is_etf, "IsEtf": is_etf,
            "MainClassification": cls.get("main"), "SecondaryClassification": cls.get("secondary"), "MajorClassification": cls.get("major"),
            "MonthYield": yl.get("monthYield"), "YearYield": yl.get("yearYield"), "MachamTotal": dur,
            "DisclosureChart": chart, "AssetCompostion": {"Assets": assets}, "_source": "maya_v1",
        }

    def _maya_fund(self, sid: str) -> dict | None:
        from pymaya.utils import Language

        def fetch():
            if not self._maya_ok():
                return None
            try:
                d = self._maya_fund_v1(sid)
                if d:
                    self._maya_result(True)
                    return d
                if d == {}:
                    return {}  # Maya knows no fund with this number
            except Exception as e:
                log.info("Maya v1 fund failed for %s: %s – trying the older API", sid, e)
            funds, _ = self._maya()
            try:
                d = funds.get_details(sid, Language.HEBREW) or {}
                self._maya_result(True)
                return d
            except Exception as e:
                log.info("Maya fund details failed for %s: %s", sid, e)
                self._maya_result(False)
                return None  # not cached: Maya outages (503) must not stick for an hour
        return self._cached(f"maya_fund:{sid}", fetch) or None

    def _maya_sec_details(self, sid: str) -> dict:
        from pymaya.utils import Language

        def fetch():
            if not self._maya_ok():
                return None
            _, secs = self._maya()
            try:
                d = secs.get_details(sid, Language.HEBREW) or {}
                self._maya_result(True)
                return d
            except Exception as e:
                log.info("Maya security details failed for %s: %s", sid, e)
                self._maya_result(False)
                return None  # not cached
        return self._cached(f"maya_sec:{sid}", fetch) or {}

    # ---- profile builders ----
    def _from_maya_fund(self, d: dict) -> dict | None:
        chart = d.get("DisclosureChart") or []
        if not chart:
            return None
        p = _p()
        dur_dom_gov, dur_dom_corp, dur_foreign = [], [], []
        foreign_bond_gov_share = None
        for r in chart:
            code, rate, desc = r.get("LevelCd") or "", float(r.get("ExposureRate") or 0) / 100, r.get("LevelDesc") or ""
            if code.startswith("08"):
                val = float(r.get("ExposureRate") or 0)
                if "חו\"ל" in desc:
                    dur_foreign.append(val)
                elif "ממשלתי" in desc:
                    dur_dom_gov.append(val)
                else:
                    dur_dom_corp.append(val)
                continue
            if len(code) == 4:
                if code == "0101":
                    p["equity"]["IL"] += rate
                elif code.startswith("01"):
                    pass  # foreign equity is split by level-2 regions below
                elif code == "0301":
                    pass  # split below
                elif code == "0302":
                    pass
                elif code.startswith("05"):
                    p["cash"] += rate
                elif code.startswith("06"):
                    p["fx_exposure"] += rate
                elif code.startswith("07"):
                    pass  # credit ratings
                else:
                    p["other"] += rate
            elif len(code) == 6:
                if code.startswith("0102"):
                    if "ישראל" in desc:
                        p["equity"]["IL"] += rate
                    elif "צפון אמריקה" in desc:
                        p["equity"]["US"] += rate
                    elif "None-DM" in desc or "מתעוררים" in desc:
                        p["equity"]["EM"] += rate
                    elif "אירופה" in desc:
                        p["equity"]["EUROPE"] += rate
                    elif "אסיה" in desc or "אוסטרליה" in desc or "יפן" in desc:
                        p["equity"]["ASIA"] += rate
                    else:
                        p["equity"]["OTHER"] += rate
                elif code.startswith("0301"):
                    if code == "030101":
                        p["bonds"]["il_gov"] += rate
                    else:
                        p["bonds"]["il_corp"] += rate
                elif code.startswith("0302"):
                    if "מדינה" in desc or "ממשל" in desc:
                        p["bonds"]["foreign_gov"] += rate
                    else:
                        p["bonds"]["foreign_corp"] += rate
        # level-1 rows whose level-2 split was missing
        lvl1 = {r.get("LevelCd"): float(r.get("ExposureRate") or 0) / 100 for r in chart if len(r.get("LevelCd") or "") == 4}
        foreign_eq_split = sum(v for k, v in p["equity"].items() if k != "IL") + 0
        for code, val in lvl1.items():
            if code.startswith("01") and code != "0101" and foreign_eq_split == 0:
                p["equity"]["OTHER"] += val
        if "0301" in lvl1 and p["bonds"]["il_gov"] + p["bonds"]["il_corp"] == 0:
            p["bonds"]["il_corp"] += lvl1["0301"]
        if "0302" in lvl1 and p["bonds"]["foreign_gov"] + p["bonds"]["foreign_corp"] == 0:
            p["bonds"]["foreign_corp"] += lvl1["0302"]

        avg = lambda xs: sum(xs) / len(xs) if xs else 0.0  # noqa: E731
        p["durations"]["il_gov"] = avg(dur_dom_gov) or (avg(dur_dom_corp) if p["bonds"]["il_gov"] else 0) or (5.0 if p["bonds"]["il_gov"] else 0)
        p["durations"]["il_corp"] = avg(dur_dom_corp) or (3.5 if p["bonds"]["il_corp"] else 0)
        p["durations"]["foreign_gov"] = avg(dur_foreign) or (6.0 if p["bonds"]["foreign_gov"] else 0)
        p["durations"]["foreign_corp"] = avg(dur_foreign) or (6.0 if p["bonds"]["foreign_corp"] else 0)
        p["fx_exposure"] = max(0.0, min(p["fx_exposure"], 2.0))

        assets = (d.get("AssetCompostion") or {}).get("Assets") or []
        top = sorted((a for a in assets if (a.get("FundPercentage") or 0) > 0), key=lambda a: -(a["FundPercentage"]))[:10]
        p["top_holdings"] = [
            {"key": name_key(a.get("AssetName")), "name": (a.get("AssetName") or "").strip(), "weight": float(a["FundPercentage"]) / 100,
             "type": a.get("AssetTypeName")}
            for a in top
        ]
        p["label"] = " · ".join(x for x in (d.get("MainClassification"), d.get("SecondaryClassification")) if x)
        try:
            p["fee"] = round(float(d.get("ManagementFee") or 0) + float(d.get("TrusteeFee") or 0), 4)
        except (TypeError, ValueError):
            p["fee"] = None
        total = sum(p["equity"].values()) + sum(p["bonds"].values()) + p["cash"] + p["other"]
        return p if total > 0.05 else None

    def _overlay_live(self, p: dict, symbol: str | None):
        """Fill top holdings / sectors from live yfinance fund data (direct ticker or proxy)."""
        if not symbol:
            return False
        live = self._yf_fund_data(symbol)
        if not live:
            return False
        eq_total = sum(p["equity"].values())
        if live.get("top") and not p["top_holdings"]:
            p["top_holdings"] = [dict(t) for t in live["top"]]
        if live.get("sectors") and not p["sectors"] and eq_total:
            s = sum(live["sectors"].values()) or 1
            p["sectors"] = {k: v / s for k, v in live["sectors"].items()}
        return bool(live.get("top") or live.get("sectors"))

    def profile(self, h: dict) -> dict:
        """h: holding dict from the analysis (input_id, ticker, name, market, asset_class, currency, sector)."""
        ident = normalize_identifier(h.get("input_id") or h.get("id"))
        ticker = (h.get("ticker") or ident).upper()
        key = f"profile:{ident}:{ticker}"
        return deepcopy(self._cached(key, lambda: self._build_profile(ident, ticker, h)))

    def _build_profile(self, ident: str, ticker: str, h: dict) -> dict:
        entry = pricing_engine.directory.get(ident) if is_tase_id(ident) else None
        names = (h.get("name"), h.get("name_en"), (entry or {}).get("name_he"), (entry or {}).get("name_en"))
        asset_class = h.get("asset_class") or ""

        # 1. Israeli mutual fund -> Maya disclosure
        if is_tase_id(ident) and (entry is None or entry["type"] == 4 or asset_class == "קרנות נאמנות"):
            d = self._maya_fund(ident)
            if d:
                p = self._from_maya_fund(d)
                if p:
                    return self._finish(p, "maya", "מאי״ה – גילוי נאות של הקרן", h)

        # 2. Known ETF / index product
        index_key = ETF_MAP.get(ticker) or ETF_MAP.get(ident)
        if not index_key and entry and entry.get("isin"):
            index_key = ISIN_MAP.get(entry["isin"])
        is_fund_like = asset_class in ("קרנות סל", "קרנות נאמנות") or (entry and "etf" in (entry.get("subtype") or "").lower())
        if not index_key and is_fund_like:
            index_key = match_name_pattern(*names)
        if index_key:
            p = deepcopy(INDEX_PROFILES[index_key])
            fx_code = fx_from_name(*names)
            if fx_code is not None and sum(v for k, v in p["equity"].items() if k != "IL") + p["bonds"]["foreign_gov"] + p["bonds"]["foreign_corp"] + p["other"] > 0:
                p["fx_exposure"] = fx_code
            live_sym = ticker if ticker in ETF_MAP else p.get("proxy")
            live = self._overlay_live(p, live_sym)
            if ticker in ETF_MAP:
                er = self._yf_info(ticker).get("expense_ratio")
                p["fee"] = float(er) if er is not None else None
            src = f"מיפוי מדד: {p['label']}" + (f" + נתונים חיים ({live_sym})" if live else "")
            return self._finish(p, "static", src, h)

        # 3. US ETF not in the dictionary -> live yfinance fund data
        if h.get("market") == "US" and asset_class == "קרנות סל":
            live = self._yf_fund_data(ticker)
            if live and (live.get("asset_classes") or live.get("top")):
                ac = live.get("asset_classes") or {}
                stock, bond, cash = ac.get("stockPosition", 1.0), ac.get("bondPosition", 0.0), ac.get("cashPosition", 0.0)
                p = _p({"US": stock}, foreign_corp=bond * 0.4, foreign_gov=bond * 0.6, cash=cash,
                       other=max(0.0, 1 - stock - bond - cash), dur={"foreign_gov": 6.0, "foreign_corp": 6.0}, fx=1)
                self._overlay_live(p, ticker)
                er = self._yf_info(ticker).get("expense_ratio")
                p["fee"] = float(er) if er is not None else None
                return self._finish(p, "live", f"yfinance ({ticker})", h)

        # 4. Single securities
        if asset_class == "מניות" or (h.get("market") == "US" and asset_class != "קרנות סל"):
            if h.get("market") == "US" or not is_tase_id(ident):
                info = self._yf_info(ticker)
                region = "US" if h.get("market") == "US" else "OTHER"
                p = _p({region: 1}, fx=1 if h.get("currency") != "ILS" else 0)
                sec = sector_from_yf(info.get("sector") or h.get("sector"))
                p["sectors"] = {sec: 1.0} if sec else {}
                p["beta"] = info.get("beta")
            else:
                det = self._maya_sec_details(ident)
                p = _p({"IL": 1})
                sec = sector_from_branch(det.get("FullBranch"))
                p["sectors"] = {sec: 1.0} if sec else {}
            p["top_holdings"] = [{"key": name_key(h.get("name_en") or h.get("name")), "name": h.get("name"), "weight": 1.0, "self": True}]
            p["fee"] = 0.0
            return self._finish(p, "direct", "נייר בודד", h)

        if asset_class.startswith("אג"):
            det = self._maya_sec_details(ident) if is_tase_id(ident) else {}
            days = det.get("DaysUntilRedemption")
            years = (float(days) / 365.0) if days else None
            # Duration approximation: ~85% of time-to-maturity for a coupon bond
            dur = round(years * 0.85, 2) if years else (6.0 if "ממשלתי" in asset_class else 3.5)
            bucket = "il_gov" if "ממשלתי" in asset_class else "il_corp"
            p = _p(**{bucket: 1.0}, dur={bucket: dur})
            p["top_holdings"] = [{"key": name_key(h.get("name")), "name": h.get("name"), "weight": 1.0, "self": True}]
            p["fee"] = 0.0
            return self._finish(p, "direct", "אג״ח בודדת" + (f" · מח״מ משוער {dur}" if years else ""), h)

        # 5. Defaults
        if asset_class == "קרנות סל":
            region = "IL" if h.get("market") == "IL" else "US"
            fx_code = fx_from_name(*names)
            if region == "IL" and fx_code and fx_code >= 1:
                region = "OTHER"  # foreign-exposed TASE ETF of unknown index
            p = _p({region: 1}, fx=fx_code if fx_code is not None else (0 if region == "IL" else 1))
            return self._finish(p, "default", "הנחת ברירת מחדל (קרן סל מנייתית)", h)
        p = _p(other=1.0, fx=0 if h.get("currency", "ILS") == "ILS" else 1)
        return self._finish(p, "default", "לא סווג", h)

    @staticmethod
    def _finish(p: dict, method: str, source: str, h: dict) -> dict:
        p["method"] = method
        p["source"] = source
        p.pop("proxy", None)
        return p

    @staticmethod
    def type_profile(spec: dict, label: str) -> dict:
        """X-Ray profile for a security type the advisor chose by hand (see prospect.ASSET_TYPES)."""
        dur = spec.get("dur", 0.0)
        bk = {b: spec.get(b, 0.0) for b in BOND_BUCKETS}
        p = _p(spec.get("equity"), cash=spec.get("cash", 0.0), other=spec.get("other", 0.0), fx=spec.get("fx", 0.0),
               dur={b: dur for b, v in bk.items() if v}, **bk)
        p["method"], p["source"] = "manual", f"סיווג ידני: {label}"
        p.pop("proxy", None)
        return p

    # ---- portfolio aggregation ----
    def analyze(self, holdings: list[dict], aum: float) -> dict:
        rows, profiles = [], {}
        asset = {k: 0.0 for k in ASSET_LABEL}
        geo = {r: 0.0 for r in EQ_REGIONS}
        sectors: dict[str, float] = {}
        unclassified_equity = 0.0
        fx_total, dur_weighted, bond_total = 0.0, 0.0, 0.0
        underlying: dict[str, dict] = {}
        covered = 0.0
        fee_weighted, fee_covered = 0.0, 0.0

        for h in holdings:
            w = float(h.get("weight") or 0) / 100
            p = deepcopy(h["profile_override"]) if h.get("profile_override") else self.profile(h)
            profiles[h["input_id"]] = p
            eq = sum(p["equity"].values())
            gov = p["bonds"]["il_gov"] + p["bonds"]["foreign_gov"]
            corp = p["bonds"]["il_corp"] + p["bonds"]["foreign_corp"]
            asset["equity"] += w * eq
            asset["gov_bonds"] += w * gov
            asset["corp_bonds"] += w * corp
            asset["cash"] += w * p["cash"]
            asset["other"] += w * p["other"]
            for r, v in p["equity"].items():
                geo[r] += w * v
            geo["IL"] += w * (p["bonds"]["il_gov"] + p["bonds"]["il_corp"] + p["cash"])
            geo["US"] += w * (p["bonds"]["foreign_gov"] + p["bonds"]["foreign_corp"])  # foreign bonds are predominantly US
            geo["OTHER"] += w * p["other"]
            sec_sum = 0.0
            for s, v in p["sectors"].items():
                sectors[s] = sectors.get(s, 0) + w * eq * v
                sec_sum += v
            unclassified_equity += w * eq * max(0.0, 1 - sec_sum)
            fx_total += w * p["fx_exposure"]
            for b in BOND_BUCKETS:
                dur_weighted += w * p["bonds"][b] * p["durations"][b]
                bond_total += w * p["bonds"][b]
            if p["method"] != "default":
                covered += w
            fee = h.get("fee") if h.get("fee") is not None else p.get("fee")
            if fee is not None:
                fee_weighted += w * float(fee)
                fee_covered += w

            for t in p["top_holdings"]:
                k = t.get("key") or name_key(t.get("name"))
                if not k:
                    continue
                u = underlying.setdefault(k, {"name": t.get("name"), "direct": 0.0, "indirect": 0.0, "via": []})
                contrib = w * t["weight"]
                if t.get("self"):
                    u["direct"] += contrib
                    u["name"] = h.get("name") or u["name"]
                else:
                    u["indirect"] += contrib
                    u["via"].append({"fund": h.get("name"), "weight": round(contrib * 100, 4)})

            rows.append({
                "input_id": h["input_id"], "ticker": h.get("ticker"), "name": h.get("name"), "weight": h.get("weight"),
                "method": p["method"], "source": p["source"], "label": p.get("label", ""),
                "equity": round(eq * 100, 2), "gov_bonds": round(gov * 100, 2), "corp_bonds": round(corp * 100, 2),
                "cash": round(p["cash"] * 100, 2), "other": round(p["other"] * 100, 2),
                "fx_exposure": round(p["fx_exposure"] * 100, 2),
                "fee": None if fee is None else round(float(fee), 4),
                "fee_source": "manual" if h.get("fee") is not None else ("data" if p.get("fee") is not None else None),
                "duration": round(sum(p["bonds"][b] * p["durations"][b] for b in BOND_BUCKETS) / max(1e-9, sum(p["bonds"].values())), 2) if sum(p["bonds"].values()) > 0.001 else None,
                "regions": {r: round(v * 100, 2) for r, v in p["equity"].items() if v},
                "top_holdings": [{"name": t["name"], "weight": round(t["weight"] * 100, 2)} for t in p["top_holdings"][:10] if not t.get("self")],
            })

        if unclassified_equity > 0.0005:
            sectors["לא מסווג"] = sectors.get("לא מסווג", 0) + unclassified_equity
        top = sorted(
            ({"key": k, "name": v["name"], "direct": round(v["direct"] * 100, 4), "indirect": round(v["indirect"] * 100, 4),
              "total": round((v["direct"] + v["indirect"]) * 100, 4), "value_ils": round((v["direct"] + v["indirect"]) * aum, 2),
              "via": v["via"]} for k, v in underlying.items()),
            key=lambda x: -x["total"],
        )[:20]

        pct = lambda d: {k: round(v * 100, 4) for k, v in sorted(d.items(), key=lambda kv: -kv[1]) if abs(v) > 1e-6}  # noqa: E731
        portfolio_duration = dur_weighted / bond_total if bond_total else 0.0
        return {
            "asset_classes": {ASSET_LABEL[k]: v for k, v in pct(asset).items()},
            "geography": {REGION_LABEL[k]: v for k, v in pct(geo).items()},
            "sectors": pct(sectors),
            "top_underlying": top,
            "holdings": rows,
            "metrics": {
                "fx_exposure": round(fx_total * 100, 2),
                "bond_weight": round(bond_total * 100, 2),
                "bond_duration": round(portfolio_duration, 2),
                "portfolio_duration": round(dur_weighted, 3),  # bond duration diluted by bond weight
                "dv01_ils": round(dur_weighted * aum / 10_000, 2),  # ₪ change per 1bp parallel move
                "coverage": round(covered * 100, 2),
                "equity_weight": round(asset["equity"] * 100, 2),
                # weighted annual cost over the part of the portfolio with a known fee
                "weighted_fee": round(fee_weighted / fee_covered, 4) if fee_covered else None,
                "fee_coverage": round(fee_covered * 100, 2),
                "annual_cost_ils": round(fee_weighted * aum / 100, 2),
            },
            "_profiles": profiles,
        }


xray_engine = XRayEngine()
