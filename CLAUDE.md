# BankDashBoard — Claude Context

## What this app is

A personal finance dashboard that parses raw Excel files downloaded from Bank Leumi, stores them in a PostgreSQL database (Neon, via psycopg2), and serves a Flask web app with monthly analysis, category breakdowns, a file organizer, and cash tracking.

---

## Repository layout

```
source/
  WebApp.py          — Flask app, all routes, HTML generation helpers
  AppManager.py      — CLI entry point, orchestrates parsing → DB → analysis
  database.py        — DataBase singleton (PostgreSQL via psycopg2, Neon-hosted)
  Constants.py       — All enums and reserved string constants
  src_utils/
    utils.py         — Core logic: generate_html, card_charge_validation,
                       handle_withdrawals, get_cash_transactions,
                       accumulate_cash_Balance, read_present_table, …
    calculations.py  — process_prices (classifies each transaction into Trans_Type)
  Configurations/
    Formats.py       — Per-bank-format config (column names, card numbers, tx names)
  routes/
    auth_routes.py   — Blueprint for /login /logout (separate from WebApp.py auth)
  html/              — Static HTML templates (Base_template.html, Files.html, …)
```

---

## Key domain concepts

### Transaction tables
- **BankTransactions** — direct bank debits/credits (transfers, CC charges, ATM debits)
- **CardTransactions** — individual credit card line items
- **CashTransactions** — manual cash entries created by the user

### Trans_Type (enum in Constants.py)
Each row in a processed DataFrame is classified by `process_prices()` in `calculations.py`:

| Value | Meaning |
|---|---|
| `payment` | instalment payment transaction |
| `flowing` | regular recurring expense |
| `payback` | refund |
| `withdrawl` | ATM cash withdrawal (note: intentional typo in codebase) |
| `excluded` | manually excluded or CC-charge rows |
| `default` | everything else |
| `bank` | bank-side transaction |

### ReservedNames (Constants.py)
| Constant | Value | Used for |
|---|---|---|
| `WITHDRAWAL` | `"משיכת מזומנים"` | Name of ATM withdrawal rows in CardTransactions |
| `WHITDRAWAL_CATEGORY` | `"withdrawal"` | Category tag applied to matched withdrawal rows |
| `EXCLUDED_CATEGORY` | `"Excluded"` | Manually excluded transactions |
| `CC_CHARGE_CATEGORY_NAME` | `"אשראי"` | Bank-side credit-card charge rows |

---

## ATM withdrawal handling — critical invariant

An ATM withdrawal creates **two rows**:
1. `CardTransactions` — name `"משיכת מזומנים"`, the card debit
2. `BankTransactions` — the matching bank debit the same month

`utils.handle_withdrawals()` matches them and tags **both** with `category = "withdrawal"`.

**Any function that sums money or counts transactions must exclude `WHITDRAWAL_CATEGORY`**, otherwise the same cash leaves is counted twice. The places that do (or must) apply this filter:

- `calculations.process_prices` — `is_withdrawals_transaction()` returns `Trans_Type.withdrawl`; these rows are excluded in general analysis
- `utils.card_charge_validation()` — filters `processed_df` by `Category != WHITDRAWAL_CATEGORY` before summing per-card totals (otherwise the card sum inflates and the charge validation fails)
- `utils.accumulate_cash_Balance()` — filters CashTransactions by `Category != WHITDRAWAL_CATEGORY` (bank-side debit already counted separately)
- `utils.get_cash_transactions()` — same filter on CashTransactions

---

## Housing (`/housing`) page — `process_prices` is inconsistently applied

Every housing-page number ultimately comes from one of these calls inside `AppManager.get_global_data()` (the function behind `/api/housing/data`, `AppManager.py` ~line 2357-2398):

| Data (rendered as) | Source | Runs `process_prices`? | Includes `CardTransactions`? |
|---|---|---|---|
| Balance/equity/milestones | `mortgage.full_schedule()` — pure amortization math | n/a (no DB) | n/a |
| `actual_payments()` | `database.get_mortgage_payments()` — raw SQL on `BankTransactions` | No | No |
| `actual_rental_income()` | `database.get_housing_income()` — raw SQL on `BankTransactions` | No | No |
| "This month" KPIs (`current_month_data()`: payment/rental/net/month_out/month_income) | raw SQL directly on `BankTransactions` | No | No |
| All-time KPIs (`alltime_category_data()`: alltime_out/alltime_income) | `get_housing_spending()` + `get_housing_income()` | Card slice only (`get_housing_spending`) | Card slice only |
| Transactions table **and** the spend/earn business-breakdown pies (`spending_pie_data`/`earning_pie_data`) | `database.get_all_category_transactions()` | Card slice only | Yes |

So most bank-sourced housing numbers bypass `process_prices` entirely (raw `Out`/`Income` from `BankTransactions`), and only the two functions that also pull in `CardTransactions` (`get_housing_spending`, `get_all_category_transactions`) run that card slice through it — because `process_prices`'s payment/flowing/payback logic only exists on the `TableName == 'CardTransactions'` branch (`calculations.py`'s `classify_and_handle`); bank rows just get folded into a signed `Final_Value` with no magnitude change. This means **card-sourced housing transactions never appear in `current_month_data()`, `actual_payments()`, or `actual_rental_income()`** — only in the transactions table and the pies. This asymmetry predates the pie feature (added in a Claude session, commit `4eaad87` on `Dev/GeneralFeatures`) and was not introduced by it; it was flagged to the user and left as-is by their choice, pending a decision on whether bank-only is intentional for mortgage/rent tracking.

---

## Organizer page regeneration — progress bar

`/api/organizer/regenerate` streams numeric progress to the client.

**Work breakdown** (approximate):
- 0–75 % → `read_present_table()` row loop — the only place that calls `progress_callback`
- 75–88 % → untagged-cells detection loop + HTML string building + file write (inside `_build_organizer_page`)
- 88–95 % → `_save_manifest()`
- 95–100 % → `done` signal

The progress callback passed to `_build_organizer_page` must be **scaled to 0–75** so the bar does not freeze at ~75 % and then jump to 100.

```python
def _scaled(p):
    pq.put(int(p * 0.75))   # maps read_present_table 0-100 → 0-75

deps, db_mtime = _capture_deps_and_run(
    lambda: _build_organizer_page(progress_callback=_scaled)
)
pq.put(88)   # after HTML written to disk
_save_manifest(...)
pq.put(95)   # after manifest
pq.put('done')
```

---

## Page regeneration screen

When a monthly analysis doesn't exist yet, `_not_generated_html()` is shown. Its style/HTML/JS come from three shared helpers used by both monthly and category regeneration pages:

- `_log_float_style()` — `<style>` block (body background, `.box`, `.log-float`, `.lf-*`)
- `_log_float_html()` — the floating log panel markup
- `_log_float_js()` — `showLogFloat / hideLogFloat / appendLog / showCCPrompt`

**Do not add a separate copy of these helpers** — they are intentionally shared.

The log feed (`#lf-feed`) uses `flex-direction:column` with `appendChild` + `scrollTop = scrollHeight` so newest lines appear at the bottom. Do not switch back to `column-reverse` / `insertBefore`.

---

## Side menu — one list for every page

The menu links live only in `source/html/nav.js` (served publicly at `/nav.js`). Each page's sidebar
has an empty `<div class="sidebar-scroll" data-nav="KEY"></div>` followed by `<script src="/nav.js"></script>`;
`KEY` marks the current page (`""` on the landing page, `monthly-page` on `Base_template.html`, whose first
two items switch panels via `#nav-overview` / `#nav-accounts`). Add or rename a menu item in `nav.js`
only — never hard-code `class="nav-item"` links in a page (`tests/test_shared_nav.py` checks this).

---

## New-build apartment projects (Mona) — `/housing` tab + the "נכס מונה" asset

A second property next to שבזי on the housing page. Code: `source/src_utils/housing_projects.py` (pure money model),
`source/housing_project_service.py` (loading/validation over a `db`), `source/routes/housing_project_routes.py`
(`/api/housing/projects/<key>`), DB tables `HousingProjects` + `HousingTxKinds` (`database.py`, created on first use,
Mona seeded). Tests: `tests/test_housing_project*.py`, `tests/test_housing_projects_js.py`.

- **Payments** come from the bank/card transactions tagged with the project's tag (default **"דירת קבלן"**, editable in the tab);
  the timeline is the category labelled MONA (found by label, then remembered).
- **Every payment has a kind:** `price` (goes into the apartment price → builds equity, comes back on a sale), `cost` (fees/taxes:
  spent, never an asset), `income` (rent etc.: not an asset), `refund`. Defaults come from `classify_kind` (fee-like words such as
  ליווי / עו"ד → cost); the user flips any payment on the page (`HousingTxKinds`, key `Table:id` or `split:id`).
- **Financing plan (settings):** `down_pct` (initial payment, default 10 %) and `mortgage_pct` (share the mortgage covers at
  delivery, default 75 %). Own money before the loan = 100 − `mortgage_pct` (25 % = the 10 % now + another 15 % at delivery);
  `expected_mortgage` = price − max(paid so far, that share). `down_pct` may not exceed the own-money share.
- **Equity (the asset) = price payments − refunds + appreciation of the whole price**; growth is 0–15 %/yr (default 3, saved).
  Annual return is shown only after a year of history.
- **Accounts page:** the asset is added per request by `WebApp._accounts_with_projects` (not stored in the cached accounts
  payload, so edits show at once) and the Total series is shifted by it (`housing_projects.apply_overlay`).
  `Total` therefore already includes it wherever `/api/accounts/data` or `_landing_accounts` is used.
- **The page recomputes the money numbers in JS while the slider moves** (block between `MONA-CALC-BEGIN/END` in
  `Base_template.html`); `tests/test_housing_projects_js.py` runs it under node against the Python — change both together.
- The shared timeline engine got a `'project'` scope (`_tlScopeCategory`) so the tab can show/add events in its own category.
- **Landing block `mona`** (`landing_service.build_mona`, `landing_loaders.load_mona`): KPI = equity; its link carries `data-hs-prop`
  so `/housing` opens the Mona tab (the דיור block sets `shabazi`).
- **Settings form autosaves** on field `change` (no need to press שמירה).
- **Housing menus:** the apartments (שלום שבזי 7 / מונה) are the fixed top tab bar (`.hs-top`); סקירה כללית / ציר זמן are each
  apartment's in-flow sub-menu (`.hs-nav`). (`.hs-subtab-btn` is still used by the timeline category chips.)

---

## Color palette

| Token | Hex | Used for |
|---|---|---|
| Navy | `#1e2a4a` | Headings, sidebar background, body text |
| Teal | `#1e9d8b` | Accent, buttons, badges, links |
| Background | `#f4f6f9` | Dashboard page backgrounds |
| White | `#fff` | Card/panel backgrounds |
| Page regen bg | `linear-gradient(135deg, #0f1627 0%, #1a2e52 100%)` | Regeneration / loading screens only |

CSS variables used in the dashboard HTML: `var(--teal)`, `var(--navy)`, `var(--white)`, `var(--border)`, `var(--text-muted)`.

---

## Flask routes — duplicate-route pitfall

`WebApp.py` defines most routes inline. `source/routes/` contains Blueprints for newer features. **Never define the same route or endpoint name in both places.** Flask raises `AssertionError: View function mapping is overwriting an existing endpoint function` at startup if a route is registered twice. Check with:

```bash
grep -n "api/auth/verify\|api_auth_verify" source/WebApp.py
```

The canonical auth check endpoint is `POST /api/auth/verify` in `WebApp.py` — it uses `hmac.compare_digest` and falls back to `DASHBOARD_PASSWORD` → `'ofek'` if `ADMIN_PASSWORD` is not set.

---

## Database connection pools — "connection pool exhausted"

There are two psycopg2 pools, each capped at 10 connections: `DataBase` (`database.py`, connections
borrowed per thread) and `_pg_conn()` (`WebApp.py`, raw-SQL routes). psycopg2's pool **raises
immediately** when it is full, so both sit behind a `PoolGate` (`source/db_pool.py`,
`DataBase._gate` / `WebApp._pg_gate`): a borrower waits up to 30 s for a free connection instead of failing.
The landing page alone fires 11 requests at once.

- A `DataBase` connection is returned by `teardown_request` → `release_thread_connection()`. Background
  threads and streamed-response generators don't pass through teardown; a `_Lease` finalizer returns
  their connection when the thread ends. A long-lived thread that uses `DataBase` should still call
  `DataBase.release_thread_connection()` when done, since the lease only fires at thread exit.
- A `_pg_conn()` connection is returned by `close()` (idempotent); a wrapper dropped without `close()`
  returns it from `__del__`. Still close it in a `finally`.
- Every borrowed connection holds exactly one gate permit. Never call `getconn`/`putconn`
  directly; use `_checkout`/`_give_back` (`DataBase`) or `_pg_conn()`/`close()`.
  `tests/test_db_pool.py` checks the accounting with a fake pool.

---

## Branch conventions

| Branch | Purpose |
|---|---|
| `main` | Stable, deployed to Vercel |
| `Dev/Analysis2-0` | Active local development branch |
| `features-and-fixes` | Claude-assisted features and bug fixes (branch from `main`) |
| `claude/session-*` | Auto-created per Claude session (ephemeral, not for long-lived work) |

Always develop on `features-and-fixes` (or a named feature branch), not on `claude/session-*` branches.

---

## Versioning — standing rule

- The version number lives in `/VERSION` (semver, one line, e.g. `1.1.0`).
- **On every commit and push to this repo, increment the patch version** (e.g. `1.1.0` → `1.1.1`). Minor bumps for new features, major bumps for breaking changes.
- The version is served by `GET /api/version` and displayed in **all sidebar footers** via `<div id="app-version-badge-*">`. There are currently two badges (`app-version-badge-1` in the category page sidebar, `app-version-badge-2` in the organizer/monthly page sidebar). Each sidebar's `<script>` block fetches `/api/version` and populates its badge.
- This rule applies to every Claude session and every repo — always bump the version as part of each commit.

---

## Deployment

The app runs on Vercel (serverless). Entry point: `source/WebApp.py`. The database is PostgreSQL (Neon), connected via `psycopg2.connect(os.environ['DATABASE_URL'])` in `database.py` — the same `DATABASE_URL` is used both locally (loaded from `.env`) and on Vercel, there is no SQLite fallback. Generated-file output paths (e.g. `Outputs/general_analysis`, `Outputs/category_analysis`) still differ between local and Vercel — those branch on `os.getenv('VERCEL')`, not on `DATABASE_URL` (a similarly-named check based on `DATABASE_URL` presence is a known latent bug in a few spots in `utils.py` — `DATABASE_URL` no longer implies "running on Vercel" now that it's required locally too). `fill_missing.py` is a one-off SQLite→Postgres gap-filler used during the migration, not part of the live path-resolution logic. Do not hardcode local Windows paths (e.g. `C:\\Users\\ofeks\\...`).
