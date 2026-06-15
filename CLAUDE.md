# BankDash — Claude Project Context

## What this app is

BankDash is a **personal finance dashboard** for the Shmuel family. It ingests Israeli bank and credit-card Excel exports, stores them in a database, runs analysis, and serves a Hebrew RTL web dashboard on `http://localhost:5050`.

Key features: monthly spending/earnings/investment analysis, KPI summaries, smart alerts, mortgage tracking, cash-flow by currency, account status, category drill-down, bills tracker, Spotify cost splitter, gym session splitter.

---

## How to run

```bash
# From repo root
python source/main.py        # starts Flask on :5050 and opens browser
# OR
python source/WebApp.py      # same, without the atexit cleanup hook
```

The app runs with `flask run` equivalent via `WebApp.start(port=5050)`.

---

## Architecture overview

```
source/
  main.py              ← entrypoint; calls WebApp.start()
  WebApp.py            ← Flask app (~4000 lines); all routes + UI helper HTML
  AppManager.py        ← orchestrates analysis pipeline (parse → validate → generate)
  database.py          ← DataBase class; wraps SQLite (local) and PostgreSQL (prod)
  Bank.py / Card.py    ← models for bank / credit-card transaction records
  Parser.py            ← parses bank/card Excel exports into DataBase rows
  File.py              ← file tracking; knows which Excel files have been imported
  Constants.py         ← shared constants (reserved category names, column names)
  auth.py              ← HMAC-based password verification
  decorators.py        ← Flask auth decorator
  front/Graphics.py    ← generates chart images (matplotlib/plotly) → Outputs/
  Analysis/
    SmartAlerts.py     ← detects unusual spending patterns; returns alert list
  src_utils/
    utils.py           ← generate_html() — the main HTML report builder (~2700 lines)
    calculations.py    ← financial calculations (net, savings rate, etc.)
    mortgage.py        ← mortgage amortisation helpers
    AppManagerUtils.py ← helper functions for AppManager
    ExcelReader.py     ← openpyxl wrapper for reading bank Excel files
  routes/
    auth_routes.py     ← /login, /logout routes
    activity_routes.py ← /activity log routes
  html/
    Base_template.html ← HTML skeleton: all CSS + static JS (see rule below)
    output.html        ← GENERATED — last analysis output. DO NOT EDIT.
    Bills.html         ← bills tracker page template
    Search.html        ← search page template
    Tagger.html        ← category tagger page template
    Gym.html           ← gym splitter page template
    Organizer_Table.html ← file organizer template
    design-system.css  ← shared design tokens (colours, typography, spacing)
    index.html         ← landing page / auth gate
Outputs/
  general_analysis/    ← GENERATED monthly reports (2025_12.html, 2026_05.html…)
  category_analysis/   ← GENERATED category drill-down reports
  Graphics/            ← GENERATED chart images
fill_missing.py        ← one-shot SQLite → PostgreSQL gap-filler (idempotent)
```

---

## Database

### Two modes
| Environment | DB | Connection |
|---|---|---|
| Local dev | SQLite `ShmuelFamiliy.db` (repo root) | `DataBase()` — auto-detected |
| Vercel / prod | Neon PostgreSQL | `DATABASE_URL` env var in `.env` |

Detection: `os.getenv('DATABASE_URL')` — if set, use PostgreSQL; else SQLite.

### Tables (SQLite names; PostgreSQL names are all-lowercase)
| Table | Contents |
|---|---|
| `BankTransactions` | Bank account debit/credit rows |
| `CardTransactions` | Credit-card charge rows |
| `CashTransactions` | Manual cash entries |
| `DevisionTransactions` | Split-transaction child rows |
| `Card` | Credit card metadata (name, last4, owner) |
| `File` | Imported Excel file registry |
| `TableMeta` | Per-month metadata (month key, record counts) |
| `OtherAccountStatus` | Savings/investment account balances & FX rates |
| `BillTypes` / `BillEntries` | Bills tracker |
| `SpotifyMembers` / `SpotifyCharges` / `SpotifyPayments` | Spotify cost splitter |
| `GymParticipants` / `GymSessions` | Gym session splitter |

### PostgreSQL gotchas
- Table and column names in PostgreSQL queries must be **all-lowercase** (e.g. `banktransactions`, `executed_date`). SQLite is case-insensitive; PostgreSQL is not.
- `psycopg2` uses `%s` placeholders; SQLite uses `?`. `database.py` handles this via `_ChainableCursor` adapter.
- Always `connect_timeout=10` when calling `psycopg2.connect()` — without it, TCP hangs are silent and unrecoverable.
- Run `ALTER TABLE` DDL **once at startup** (`_run_acct_migrations()` in `WebApp.py`), never per-request — DDL locks the table and blocks all concurrent reads.

### Monthly query logic
- Bank rows belong to month **M** when `Executed_Date` is in month M.
- Card rows belong to month **M** when `Charge_Date` is in month **M+1** (Israeli banks charge the following month). Example: May 2026 analysis → `Charge_Date BETWEEN 2026-06-01 AND 2026-06-30`.

---

## HTML report generation — THE CRITICAL RULE

**Source files to edit:**

| File | When to edit |
|---|---|
| `source/html/Base_template.html` | Any CSS or static JS that should appear in generated reports |
| `source/src_utils/utils.py` — `generate_html()` | Programmatically-built HTML sections (KPI stat row, transaction lists, chart containers, etc.) |
| `source/WebApp.py` — `_log_float_style()` / `_not_generated_html()` / `_splash_html()` | The regeneration-in-progress screen and "no dashboard yet" splash |

**Files to NEVER edit directly:**

| File | Why |
|---|---|
| `source/html/output.html` | Overwritten on every `generate_html()` call. Any edit is lost immediately. |
| `Outputs/general_analysis/*.html` | Overwritten when user clicks "חשב מחדש". Any edit is lost on next regeneration. |

**History:** Commits `eadd163`–`876c7ef` patched the generated files directly. All fixes disappeared on next analysis. They were backported to `Base_template.html` and `utils.py` in commits `78a6e8d` and `56d1796`.

After any change to `Base_template.html` or `utils.py`, regenerate the cached month HTML by calling:
```
POST /api/analysis   body: {"month":"pick","date":"YYYY-MM-01"}
```

---

## Flask app key facts

- **Port:** 5050 (local). Vercel uses serverless.
- **Auth:** `DASHBOARD_PASSWORD` (read-only) and `ADMIN_PASSWORD` (upload/admin). Verified via HMAC in `auth.py`. Set in `.env`.
- **`.env` must NEVER be committed.** It is gitignored. A prior accidental commit exposed the Neon password — rotate in Neon console before any prod deploy.
- **Threaded:** `app.run(threaded=True)` — concurrent requests are supported.
- **FX rates:** fetched from `api.exchangerate-api.com` in a daemon thread with `join(timeout=4)`. Never use bare `urlopen` (TCP hangs with no timeout).
- **VERCEL env detection:**
  - `os.getenv('VERCEL')` → write HTML to `/tmp/`, not `Outputs/`
  - `os.getenv('DATABASE_URL')` → use PostgreSQL, write logs/db to `/tmp/`

### Key routes
| Route | What it does |
|---|---|
| `GET /` | Landing page / auth gate (`source/html/index.html`) |
| `GET /general/<yyyy_mm>` | Serves monthly analysis HTML; triggers regeneration if stale or missing |
| `POST /api/analysis` | Starts analysis in background thread. Body: `{"month":"current"/"last"/"pick", "date":"YYYY-MM-DD"}` |
| `GET /api/analysis-stream` | SSE stream of analysis log lines → drives the regen screen progress |
| `GET /api/stale/<yyyy_mm>` | Returns whether cached HTML is stale vs DB |
| `GET /api/accounts/rates` | FX rates + account balances for the Accounts panel |
| `GET /api/accounts/cash-by-currency` | Cash breakdown by currency |
| `POST /admin/upload-db` | Upload a local SQLite DB to the server (Vercel workaround) |

---

## Analysis pipeline

`POST /api/analysis` → background thread → `AppManager.__init__()` → runs in order:

1. **Parse** — `Parser.py` reads new Excel files from `ShmuelFamiliy_Inputs/`
2. **Validate** — format checks, withdrawal detection, constants validation
3. **Generate charts** — `front/Graphics.py` writes PNGs to `Outputs/Graphics/`
4. **Smart alerts** — `Analysis/SmartAlerts.py` returns alert list
5. **Mortgage analysis** — `src_utils/mortgage.py`
6. **Generate HTML** — `src_utils/utils.py::generate_html()` reads `Base_template.html`, fills in data, writes to `Outputs/general_analysis/<yyyy_mm>.html` and `source/html/output.html`

---

## Deployment

- **Branch:** `deployment2_0` (active deployment debug branch, off `main`)
- **Platform:** Vercel (serverless Python)
- **DB:** Neon PostgreSQL (free tier). Connection string in `.env` as `DATABASE_URL`.
- **`fill_missing.py`** — run from repo root to sync SQLite rows into PostgreSQL. Uses per-row savepoints so FK violations skip one row without rolling back the whole transaction.

---

## Design system

- **Colour tokens** defined in `source/html/design-system.css` and mirrored as CSS vars in `Base_template.html`: `--navy`, `--teal`, `--teal-light`, `--red`, `--green`, `--border`, `--bg`, `--white`, `--text-muted`, etc.
- **RTL** — all pages are `dir="rtl" lang="he"` (Hebrew).
- **Mobile-first** — sidebar collapses behind a hamburger (`ham-btn`), panels stack vertically at ≤900px, transaction rows lose non-essential columns at ≤560px.
- **Month roller** — horizontal carousel at the top of each analysis page; touch/swipe supported via Pointer Events API.

---

## Common pitfalls

| Symptom | Root cause | Fix |
|---|---|---|
| Analysis hangs at "Generating linear plots" | `urlopen` for FX rates blocks on TCP with no timeout | Use daemon thread + `join(timeout=4)` |
| `KeyError: 'DATABASE_URL'` in `_pg_conn()` | `load_dotenv` not called before WebApp imports | Call `load_dotenv` at module top in `WebApp.py` |
| `AssertionError: View function mapping is overwriting an existing endpoint` | Duplicate `@app.route` definition | Search for the duplicate and remove it |
| Chart panel empty / hanging | `ALTER TABLE` DDL in per-request `_acct_db()` locks table | Move DDL to one-time `_run_acct_migrations()` at startup |
| UI fix disappears after regeneration | Fix was applied to `output.html` or `Outputs/*.html`, not `Base_template.html` | Port CSS/JS to `Base_template.html` or `utils.py` |
| PostgreSQL FK violation rolling back all rows | `pg.rollback()` in the FK handler rolls back the whole transaction | Use savepoints: `SAVEPOINT sp / ROLLBACK TO SAVEPOINT sp / RELEASE SAVEPOINT sp` |
