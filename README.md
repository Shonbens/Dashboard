# IBI Portfolio Analytics & Rebalancing

A full-stack dashboard that prices Israeli (TASE) and US holdings, converts everything to ₪, and shows allocation analytics and rebalancing trades.

## Run

```bash
# Backend (FastAPI on :8000)
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn backend:app --port 8000

# Frontend (Vite on :5173, proxies /api to :8000)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The app opens on **Models (מודלים)**, where five demo house models (100, 80/20, 60/40, 40/60, 20/80) are created automatically on first run. The client-portfolio analyzer is under **ניתוח תיק לקוח**.

## Design & branding

- **IBI brand:** navy `#161932`, cyan `#00ADDC` and the logo (`frontend/public/ibi-logo.svg`), all taken from ibi.co.il. IBI's site font, Almoni Tzar, needs a commercial license, so the app uses Heebo (Google Fonts). If IBI has a license, swap the font in `tailwind.config.js`.
- **Theme:** every color is a CSS variable in `frontend/src/index.css`. Light and dark modes each have their own tested chart colors. The theme switch in the header offers light, system and dark.
- **Home screen:** a risk ladder, with models ordered from most conservative to most aggressive and colored by their actual equity share after looking through funds.

## PDF reports (`backend/report.py`)

The reports are drawn with ReportLab as vector graphics, so they stay sharp in print. Hebrew is laid out right to left using the bidi algorithm, and the Heebo font (OFL license, `backend/assets/fonts`) is embedded in the PDF.

- **Page 1:** IBI header and logo, key figures, the holdings table, the look-through breakdown, sectors and top underlying holdings.
- **Page 2:** stress scenarios, one-factor sensitivities, methodology and disclaimer.
- **Drafts:** draft models get a "טיוטה – לא מאושר" watermark.
- **Disclaimer:** the wording is in `DISCLAIMER` and should be approved by compliance before the reports are used with clients.

### Client report (`backend/client_report.py`)

A two-page report for retail clients, written in everyday Hebrew. Open it from **ניתוח תיק לקוח → דוח ללקוח**.

- **Page 1:**
  - Portfolio value, equity share and dollar exposure, each with a one-line explanation.
  - A generated summary paragraph and a 1–5 volatility meter.
  - Where the money is invested, and a plain description of every holding.
- **Page 2:**
  - Comparison with the closest IBI house model (closest look-through asset mix, approved models first), with the differences written out as sentences.
  - Four example scenarios in shekels, costs (with a clear note when fee data is partial), a short glossary and a disclaimer.

Privacy: the client name is used only inside the PDF. It's sent in the request body and never stored. As with the model reports, compliance should approve the disclaimer text (`PLAIN_DISCLAIMER`).

## Allocation sheets (גיליון הקצאה) – the house Excel, on the web

The Excel workbook ("אלוקציה פרימיום") is rebuilt as an interactive sheet. Open **מודלים → מודל חדש → גיליון הקצאה** (templates: *ישראל + חו״ל* = sheet "חדש מ.ק.20", *ישראל בלבד* = "חדש ישראל מ.ק 30"), or import the workbook itself.

- **Same structure as the Excel:**
  - Sections: Israeli and foreign equities; government bonds (CPI-linked, USD, shekel, floating); corporate bonds (USD-linked, CPI-linked, shekel, floating, foreign hedged); and funds.
  - Each section has its subtotal, a "תרומת קרנות" row, group totals and cash (עו״ש).
- **Same formulas** (`frontend/src/lib/allocation.js`):

  | Column | Formula |
  |---|---|
  | F | F = E × equity % (equity sleeve) or E × (1 − equity %) (bond sleeve) |
  | L | L = (embedded inflation + gross yield) × F ÷ total bonds |
  | N | N = duration × F ÷ (100% − equities) |
  | O | Contract fee incl. VAT, or the fund's management fee |
  | P | P = O × F |

  - **Summary column:**
    - Duration and IRR.
    - Total bonds, cash, corporate, CPI-linked vs. shekel, FX, US.
    - Equity position vs. target, and foreign/Israeli share of equities.
    - Fund fees, total fees, and house revenue (bond funds 78%, equity funds 65%), with and without VAT.
  - **Tables:**
    - Corporate risk buckets.
    - Israeli / foreign sector tables, built from the index-composition assumptions, with the gap vs. TA-125 / S&P.
    - Income real-estate share in corporate bonds vs. Tel-Bond 60.
- **One equity % for the whole model:**
  - Weights are entered as **אחוז ראשי** (inside the equity or bond sleeve), as in the newest template.
  - Changing the equity % rescales the model, so one sheet replaces the per-percentage copies (20%, 25%, 30%…).
- **Control bands** (the Excel's red conditional formats): duration 3.29–3.81, CPI-linked 45–50%, shekel 50–55%, foreign equity 60–65%, and the fund cap (מוגבל קרנות 20/30).
  - Also checked: duplicate securities, a negative cash balance, and an equity sleeve that doesn't total 100%.
  - All of these are editable in **הגדרות**, together with the contract fee, VAT, embedded inflation, revenue shares and the assumption tables.
- **Charts:**
  - Equity geography.
  - Israeli and foreign sectors (actual vs. index).
  - Corporate risk buckets.
  - Real-estate exposure.
  - The existing X-Ray and stress tests, run on the portfolio weights.

### Market data (replaces the ACE add-in) – `backend/secdata.py`
| Field | Source |
|---|---|
| Name, MTD, YTD, linkage, maturity | Maya (TASE) / Yahoo (foreign) |
| Duration | Maya `MachamTotal` for funds; estimate (0.85 × years to maturity) for single bonds, shown in italics |
| Fund look-through by section, US share, rating bucket, management fee | Maya fund disclosure (replaces the "נתוני קרנות" workbook) |
| Israeli equity sector | Maya branch, mapped to the Excel's sector names |
| Gross yield, spread, Maalot / Midroog ratings | **Manual or imported** – Maya doesn't publish them |

- **Manual values:** click a cell to enter one. It's shared by all models, stored with the editor's name, and always overrides the data source.
- **Bulk update:** **ייבוא נתוני שוק** loads an Excel/CSV with `מספר נייר` plus columns such as `תשואה ברוטו`, `מחמ`, `מרווח`, `דירוג מעלות` and `דירוג מידרוג`, for example an ACE export.
  - Fractions (0.0483) are converted to %.

### Importing the allocation workbook – `backend/allocation_import.py`
**ייבוא מאקסל** recognises the layout automatically.

- **Each sheet becomes one allocation model.** The import reads:
  - Section rows and weights.
  - Classification columns: sector, index, country, risk bucket, industry.
  - Fee and inflation cells.
  - Control bands, read from the conditional formats.
  - The index-composition and real-estate tables.
- **Older sheets** hold portfolio weights. They're converted to sleeve weights using the equity % in the sheet name.
- **Foreign securities** that appear with local 8-digit codes (e.g. `70961578`) and a ticker name are converted to the ticker.
- **Hidden sheets** are listed but set to "skip" by default.

## Potential-client analysis (ניתוח תיק פוטנציאלי) – `backend/prospect.py`

Upload the holdings statement a prospect received from another investment house (Excel/CSV). The file needs `מספר נייר` plus one of `משקל`, `שווי` or `כמות`; title rows and a total row are fine. The site then:

1. Looks through every fund using Maya disclosures, the X-Ray engine and the market data from the allocation sheet.
2. Computes the rule metrics:
   - Israeli share of equities.
   - FX exposure.
   - Managed funds (Maya's tracker flag, or a tracker-style name, marks index funds).
   - The largest direct security.
   - Shekel vs. CPI-linked bonds, and government vs. corporate.
   - Low-rated / unrated corporate bonds.
   - Bond duration.
   - Average fund/ETF fee, and the funds+ETF share.
   - Total equity and the number of holdings.
3. Checks them against the managers' rules from **Report Insights.xlsx**.
   - `ABOVE` fires above the max, `BELOW` fires below the min, and `COND` rows sharing a RuleID are AND-ed.
   - `XX` / `YY` in the wording are replaced with the portfolio's numbers.
4. Produces a branded PDF report (`backend/prospect_report.py`) with:
   - Key figures, composition, and the metrics table vs. target ranges.
   - The triggered insights in the managers' wording.
   - The holdings, with direct securities above the limit highlighted.

Missing fund fees (TASE ETFs aren't on Maya) can be typed in on the page before downloading the PDF.

**כללי התובנות** shows the active rules. Managers can download them as Excel, edit ranges and wording, and upload them back (with a preview first). The rules are stored in `backend/data/insights_rules.json`; until a file is uploaded, the built-in transcription of the template is used.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/prospect/analyze` | multipart `file` → metrics, rule status, insights, holdings |
| POST | `/api/prospect/analyze-json` | Re-run with edited holdings/fees |
| POST | `/api/prospect/report.pdf` | `{holdings, aum, client_name, advisor_name, source}` → PDF |
| GET | `/api/prospect/rules`, `/api/prospect/rules.xlsx` | Active rules (JSON / Excel in the template layout) |
| POST | `/api/prospect/rules/import` | Upload a rules workbook (`commit=false` = preview) |

## Base models

The website is the official copy of the house models. Excel is used only to bring models in and to export them.

- **Storage:** `backend/data/models.db` (SQLite). Every save adds a new version that can't be changed later, with the editor's name, a note and a timestamp. Archiving hides a model but keeps its history.
- **Excel import:** **one sheet = one model**, and the sheet name is the model name. Excel doesn't allow `/` in sheet names, so `80-20` is matched to the model `80/20`. Columns: `מספר נייר`/ticker, `משקל`, and optionally `שם נייר` and `דמי ניהול`. The header row can sit below title rows. The import shows a preview first (new vs. update, added / removed / changed holdings, unrecognized IDs), and nothing is saved until you confirm.
- **Export:** an RTL Excel workbook in the same layout, so files can be re-imported.
- **Editor:** inline weights and fees, search to add securities, paste from Excel, normalize to 100% (rounded to 2 decimals), and a live summary (actual equity vs. the target in the model's name, asset classes, geography, FX exposure, duration, fees). It also includes the X-Ray and stress-test views, version history with comparison and restore, duplicate, and archive. A model marked "approved" can't be saved unless its weights total 100%.
- **Dashboard:** model cards, a comparison of each model's composition after looking through funds, a heatmap of stress scenarios by model, and a risk and cost table.
- **Fees:** taken from Maya (management + trustee fee) for mutual funds and from yfinance for US ETFs. Maya doesn't publish fees for TASE-listed ETFs, so those are entered in the editor. A fee entered by hand overrides the data source.

## Pricing waterfall (`backend/pricing.py`)

| Tier | Source | Used for |
|---|---|---|
| 1 | yfinance | US tickers; TASE shares/ETFs (ID → `SYMBOL.TA` resolved from the Maya directory). Agorot ÷ 100 → ₪ |
| 2 | pymaya | Mutual fund NAV, plus TASE bonds/ETFs/T-bills that Yahoo doesn't carry |
| 3 | Bizportal scrape | Last resort for Israeli securities (`h1.paper_h1`, `#paper_rate .num`) |
| 4 | Fallback | `Unknown #ID`, price 0 — the batch keeps going |

Results are cached for 5 minutes (24h for names and sectors, 12h for the TASE directory). Use "רענון מחירים" or `refresh=true` to skip the cache.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/analyze-portfolio` | multipart `file` (.csv/.xlsx) + `aum` |
| POST | `/api/analyze` | JSON `{holdings:[{id,weight,target_weight,quantity}], aum, refresh}` |
| GET | `/api/quote/{id}` | Price a single security |
| GET | `/api/search?q=` | Search by Hebrew/English name, symbol or ID (TASE directory + US tickers) |
| GET | `/api/fx` | USD/EUR/GBP → ILS |
| GET | `/api/template` | Sample CSV |
| POST | `/api/cache/clear` | Clear the price cache |
| GET/POST | `/api/models` | List models / create a model |
| GET/PUT/DELETE | `/api/models/{id}` | Get / save a new version / archive |
| GET | `/api/models/{id}/versions/{v}` | Holdings of a past version |
| POST | `/api/models/{id}/duplicate` | Copy a model as a new draft |
| GET | `/api/models/overview` | Look-through, stress and cost analytics for every model |
| POST | `/api/models/import` → `/api/models/import/commit` | Excel import: preview, then confirm |
| GET | `/api/models/export`, `/api/models/demo-workbook` | Excel export / demo workbook |
| GET | `/api/models/{id}/report.pdf` | Branded two-page model report (A4) |
| GET | `/api/models/report.pdf?ids=` | Comparison cover page plus a report for each model |
| POST | `/api/portfolio/client-report.pdf` | Plain-language client report `{holdings, aum, client_name, advisor_name}` |
| POST | `/api/fund-xray` | Look-through breakdown: actual asset classes, geography, sectors, top underlying stocks, duration, DV01 |
| GET | `/api/stress-scenarios` | Preset macro scenarios |
| POST | `/api/secdata/lookup` | Market data for the allocation sheet `{ids, refresh}` (auto + manual, with source per field) |
| PUT | `/api/secdata/{id}` | Manual values for a security `{fields, user}` (null clears a field) |
| POST | `/api/secdata/import` | Bulk market-data upload (`commit=false` = preview) |
| POST | `/api/stress-test` | `{holdings, aum, shocks, scenario_id?, use_beta}` → stressed value, P&L by risk factor, scenario comparison, sensitivities |

## Fund X-Ray (`backend/xray.py`)

Each holding is broken down into equities by region, bonds (Israeli/foreign, government/corporate, each with a duration), cash, foreign-currency exposure, sectors and top underlying holdings. Sources, in order:

1. **Israeli mutual funds**: Maya's live disclosure data (exposure tree plus the fund's actual holdings).
2. **ETFs and index products**: a look-through table matched by ticker (`SPY`, `CSPX.L`, `QQQ`, `AGG`, …), ISIN, or Hebrew/English name pattern (`תל בונד`, `S&P 500`, `ת״א 35`, …). Top holdings and sectors are filled in from live yfinance data for a proxy ETF.
3. **Other US ETFs**: live yfinance fund data.
4. **Single stocks and bonds**: the security itself. Israeli sectors come from Maya's branch field. Bond duration is estimated from the redemption date.

Underlying stocks are matched across sources by normalized company name, so "NVIDIA CORP" in a fund and a direct NVDA position count as the same exposure.

## Stress testing (`backend/stress.py`)

The model is first-order (linear) and uses each holding's X-Ray profile:
- **Equities:** shocked by region (Israel / abroad), multiplied by beta for single stocks (optional).
- **Bonds:** `−D·Δy` for rates and `−D·Δs` for credit spreads.
- **Currency:** USD/ILS moves apply to the foreign-currency share, plus an FX × foreign-asset cross term.

The preset scenarios are hypothetical calibrations, not replays of historical events.

## File format

The header row is found automatically, even below title rows. Supported columns, in Hebrew or English:

- **ID** (required): `מספר נייר`, `קוד נייר`, `ticker`, `symbol`, …
- **Weight**: `משקל`, `weight` — accepts `15%`, `15` or `0.15`
- **Target weight** (optional): `משקל יעד`, `target` — turns on the rebalancing columns
- **Quantity** (optional): `כמות`, `quantity` — if there is no weight column, weights and AUM are calculated from quantity × live price

Duplicate IDs are merged automatically.
