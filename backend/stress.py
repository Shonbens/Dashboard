"""
Macro scenario & stress-testing engine.

Each holding's look-through profile (xray.py) drives its sensitivity to:
  * equity_local_pct   – shock to Israeli equities (IL region)
  * equity_global_pct  – shock to all non-Israeli equities (x beta for single stocks, optional)
  * rate_il_bps        – parallel shift of Israeli yields -> ΔP ≈ -D · Δy   (gov + corp)
  * rate_global_bps    – parallel shift of foreign yields
  * credit_bps         – credit-spread widening on corporate bonds (-D · Δs)
  * fx_pct             – % change in USD/ILS (+ = shekel weakens) applied to the foreign-currency share

Return per holding (first-order, with the FX × foreign-asset cross term):
  r = r_eq_il + r_eq_global + r_rates + r_credit + fx · fx_exposure + fx · r_foreign_assets · fx_share
"""
from __future__ import annotations

from typing import Any

from xray import xray_engine

SHOCK_KEYS = ("equity_local_pct", "equity_global_pct", "rate_il_bps", "rate_global_bps", "credit_bps", "fx_pct")

FACTOR_LABEL = {
    "equity_local": "מניות ישראל",
    "equity_global": "מניות חו״ל",
    "rates": "ריבית",
    "credit": "מרווחי אשראי",
    "fx": "מטבע (USD/ILS)",
    "cross": "אפקט משולב מט״ח×נכס",
}

# Hypothetical scenarios – stylised calibrations for discussion, not historical replays.
PRESETS: list[dict[str, Any]] = [
    {
        "id": "global_crisis", "name": "משבר פיננסי עולמי", "icon": "🌍",
        "description": "ירידות חדות בשווקים, בריחה לאיכות, היחלשות השקל, הרחבת מרווחים",
        "shocks": {"equity_local_pct": -30, "equity_global_pct": -35, "rate_il_bps": -100, "rate_global_bps": -150, "credit_bps": 250, "fx_pct": 12},
    },
    {
        "id": "local_geopolitical", "name": "הסלמה ביטחונית מקומית", "icon": "🇮🇱",
        "description": "פגיעה בשוק המקומי, פיחות בשקל ועליית פרמיית הסיכון של ישראל",
        "shocks": {"equity_local_pct": -15, "equity_global_pct": 0, "rate_il_bps": 75, "rate_global_bps": 0, "credit_bps": 120, "fx_pct": 7},
    },
    {
        "id": "rate_hike", "name": "העלאת ריבית חדה", "icon": "📈",
        "description": "אינפלציה עיקשת: עליית תשואות של 200 נ״ב בארץ ובחו״ל ולחץ על מכפילים",
        "shocks": {"equity_local_pct": -8, "equity_global_pct": -10, "rate_il_bps": 200, "rate_global_bps": 200, "credit_bps": 50, "fx_pct": 0},
    },
    {
        "id": "shekel_strength", "name": "התחזקות חדה של השקל", "icon": "₪",
        "description": "ייסוף של 10% בשקל מול הדולר – פגיעה בנכסים לא מגודרים בחו״ל",
        "shocks": {"equity_local_pct": 0, "equity_global_pct": 0, "rate_il_bps": 0, "rate_global_bps": 0, "credit_bps": 0, "fx_pct": -10},
    },
    {
        "id": "tech_correction", "name": "תיקון בשוק המניות האמריקאי", "icon": "💻",
        "description": "ירידה של 20% במניות בחו״ל עם השפעה מתונה על השוק המקומי",
        "shocks": {"equity_local_pct": -6, "equity_global_pct": -20, "rate_il_bps": -25, "rate_global_bps": -50, "credit_bps": 60, "fx_pct": 3},
    },
    {
        "id": "soft_landing", "name": "נחיתה רכה / ראלי", "icon": "🚀",
        "description": "הורדות ריבית ועליות בשווקים, התחזקות מתונה של השקל",
        "shocks": {"equity_local_pct": 12, "equity_global_pct": 15, "rate_il_bps": -75, "rate_global_bps": -75, "credit_bps": -40, "fx_pct": -3},
    },
]

SENSITIVITIES = [
    ("מניות חו״ל ‎-10%", {"equity_global_pct": -10}),
    ("מניות ישראל ‎-10%", {"equity_local_pct": -10}),
    ("ריבית ‎+100 נ״ב", {"rate_il_bps": 100, "rate_global_bps": 100}),
    ("מרווחים ‎+100 נ״ב", {"credit_bps": 100}),
    ("דולר ‎+10%", {"fx_pct": 10}),
    ("דולר ‎-10%", {"fx_pct": -10}),
]


def _beta(p: dict, use_beta: bool) -> float:
    b = p.get("beta")
    if not use_beta or b is None:
        return 1.0
    try:
        return max(0.3, min(2.5, float(b)))
    except (TypeError, ValueError):
        return 1.0


def holding_return(p: dict, s: dict, use_beta: bool = True) -> dict[str, float]:
    eq_l = s.get("equity_local_pct", 0) / 100
    eq_g = s.get("equity_global_pct", 0) / 100
    r_il = s.get("rate_il_bps", 0) / 10_000
    r_gl = s.get("rate_global_bps", 0) / 10_000
    cr = s.get("credit_bps", 0) / 10_000
    fx = s.get("fx_pct", 0) / 100
    beta = _beta(p, use_beta)

    eq, b, d = p["equity"], p["bonds"], p["durations"]
    foreign_eq = sum(v for k, v in eq.items() if k != "IL")
    c_eq_l = eq.get("IL", 0) * eq_l * beta
    c_eq_g = foreign_eq * eq_g * beta
    rates_il = -(b["il_gov"] * d["il_gov"] + b["il_corp"] * d["il_corp"]) * r_il
    rates_gl = -(b["foreign_gov"] * d["foreign_gov"] + b["foreign_corp"] * d["foreign_corp"]) * r_gl
    credit = -(b["il_corp"] * d["il_corp"] + b["foreign_corp"] * d["foreign_corp"]) * cr
    c_fx = p["fx_exposure"] * fx

    # Cross term: foreign assets that also carry currency exposure
    foreign_share = foreign_eq + b["foreign_gov"] + b["foreign_corp"]
    foreign_ret = c_eq_g + rates_gl - b["foreign_corp"] * d["foreign_corp"] * cr
    fx_share = min(1.0, p["fx_exposure"] / foreign_share) if foreign_share > 1e-9 else 0.0
    cross = fx * foreign_ret * fx_share

    total = c_eq_l + c_eq_g + rates_il + rates_gl + credit + c_fx + cross
    total = max(total, -1.0)  # cannot lose more than the position
    return {
        "equity_local": c_eq_l, "equity_global": c_eq_g, "rates": rates_il + rates_gl,
        "credit": credit, "fx": c_fx, "cross": cross, "total": total,
    }


def run_stress(holdings: list[dict], aum: float, shocks: dict, use_beta: bool = True, compare_presets: bool = True) -> dict:
    shocks = {k: float(shocks.get(k, 0) or 0) for k in SHOCK_KEYS}
    xr = xray_engine.analyze(holdings, aum)
    profiles = xr["_profiles"]

    def portfolio(sh: dict) -> tuple[float, dict, list]:
        attrib = {k: 0.0 for k in FACTOR_LABEL}
        rows, pnl_total = [], 0.0
        for h in holdings:
            value = aum * float(h.get("weight") or 0) / 100
            r = holding_return(profiles[h["input_id"]], sh, use_beta)
            pnl = value * r["total"]
            pnl_total += pnl
            for k in attrib:
                attrib[k] += value * r[k]
            rows.append({
                "input_id": h["input_id"], "ticker": h.get("ticker"), "name": h.get("name"), "weight": h.get("weight"),
                "value_ils": round(value, 2), "stressed_value_ils": round(value + pnl, 2), "pnl_ils": round(pnl, 2),
                "return_pct": round(r["total"] * 100, 3),
                "contributions": {k: round(value * r[k], 2) for k in FACTOR_LABEL},
            })
        return pnl_total, attrib, rows

    invested = sum(aum * float(h.get("weight") or 0) / 100 for h in holdings)
    cash_outside = aum - invested  # unallocated weight is treated as ILS cash (no shock)
    pnl, attrib, rows = portfolio(shocks)
    baseline = aum
    stressed = baseline + pnl

    result = {
        "shocks": shocks,
        "use_beta": use_beta,
        "baseline_value": round(baseline, 2),
        "stressed_value": round(stressed, 2),
        "pnl_ils": round(pnl, 2),
        "pnl_pct": round(pnl / baseline * 100, 4) if baseline else 0.0,
        "unallocated_ils": round(cash_outside, 2),
        "attribution": [{"factor": k, "label": FACTOR_LABEL[k], "pnl_ils": round(v, 2)} for k, v in attrib.items()],
        "holdings": sorted(rows, key=lambda r: r["pnl_ils"]),
        "risk_metrics": xr["metrics"],
    }

    if compare_presets:
        comp = []
        for pr in PRESETS:
            p_pnl, _, _ = portfolio(pr["shocks"])
            comp.append({"id": pr["id"], "name": pr["name"], "icon": pr["icon"], "baseline_value": round(baseline, 2),
                         "stressed_value": round(baseline + p_pnl, 2), "pnl_ils": round(p_pnl, 2),
                         "pnl_pct": round(p_pnl / baseline * 100, 3) if baseline else 0.0})
        result["scenario_comparison"] = comp
        sens = []
        for label, sh in SENSITIVITIES:
            s_pnl, _, _ = portfolio({k: sh.get(k, 0) for k in SHOCK_KEYS})
            sens.append({"label": label, "pnl_ils": round(s_pnl, 2), "pnl_pct": round(s_pnl / baseline * 100, 3) if baseline else 0.0})
        result["sensitivities"] = sens
    return result
