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

- **Payments** come from the bank/card transactions tagged with the project's tag (the **"Mona"** category from `categories.json` — whatever is tagged
  Mona shows in the tab's payments table, where each payment's expense type is flipped by a click on its type button; the tag is editable in the tab and is saved
  spelled as in `categories.json`, since transactions match on the exact spelling; the older **"דירת קבלן"** tag is no longer read);
  the timeline is the category labelled MONA (found by label, then remembered).
- **Every payment has a kind:** `price` (goes into the apartment price → builds equity, comes back on a sale, an *investment* in the monthly analysis),
  `cost` (extra expense: fees, taxes — spent, never an asset), `income` (rent etc.) or `refund`. **The default is `cost`** (income for money in) —
  nothing is assumed to be part of the value (`classify_kind`); the user says so with a click on the type button on the housing page (flips price ↔ cost) (`HousingTxKinds`, key `Table:id` or
  `split:id`) or **in the tagger**: for an apartment category (Mona, שלום שבאזי 7 — `GET /api/tagger/apartment-categories`) the row shows a small switch
  "הוצאה נלווית / בשווי הנכס" and `POST /api/tagger/tag` (and `tag-all-by-name`, the search re-tag and the change-category dialog) carries `kind`;
  `housing_project_service.apply_tag_kind` stores it (only `price` is stored, only for money out), drops a choice when the payment is tagged to another
  category, and leaves it alone when a request has no `kind`.
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
- **"מידע חיוני" box** (both apartments): floating button bottom-left of `/housing` (`#housing-info-fab`, shown only on the housing panel) opening name : detail rows kept in table `HousingInfo` (`database.py`, seeded once on creation; שבזי got the details restored from the unmerged branch `claude/apartment-info-copy-button-mljshs`). Validation in `source/housing_info_service.py`, endpoints `GET/PUT /api/housing/info/<shabazi|mona>` in `housing_project_routes.py`, UI (`housingInfo*`) next to the Mona code in `Base_template.html`. Tests: `tests/test_housing_info.py`.
- **Monthly analysis:** a payment tagged with an apartment category is an expense by default, but one that went into the apartment's value is an
  *investment*: Mona payments of kind `price` (and `refund`s of such money) and any שבזי payment the user marks "בשווי הדירה (השקעה)" in the
  housing table (`HousingTxKinds`, project key `shabazi`; `POST /api/housing/shabazi/tx-kind`). `src_utils/property_investments.py` moves those rows to
  `INVESTMENT_CATEGORY` (the original category stays in `Property_Category`, shown on the investment item) inside
  `AppManagerUtils.retrieve_and_initialize_data(general_analysis=True)` and `SimpleMath.get_monthly_shifted` (no category/business filter), so the month's
  charts and the 12-month history agree. Keys are `Table:ID` / `split:ID` (`DataBase.get_all_category_transactions` returns them as `Key`).
  Changing a kind marks the DB changed (stale monthly pages). The housing page's session cache key is `hs_v2` — bump it when its payload shape changes.
- **Housing menus:** the apartments (שלום שבזי 7 / מונה) are the fixed top tab bar (`.hs-top`); סקירה כללית / ציר זמן are each
  apartment's in-flow sub-menu (`.hs-nav`). (`.hs-subtab-btn` is still used by the timeline category chips.)

---

## Files page — updating a stored credit-card file with a newer download

Credit-card formats are `Independent` (no cross-file `clean()`; that overlap logic is bank-only), and a file's identity is
`File(File_Name, Format, Card_Number)` plus its month. A statement downloaded before the charge date is partial; the full
one used to be thrown away (`/api/files/scan` deleted any input file whose name was stored) or inserted twice (other name).
Now (`source/file_update_service.py`, `source/src_utils/file_diff.py`, `source/routes/file_update_routes.py`, `Files.html`):

- **Scan:** a card file whose name is stored is deleted only when the archived copy (`Verified_…/<format>/<name>`) is byte-identical;
  otherwise it is listed as an update candidate ("השווה ועדכן"). A *new* name for a stored card+month (e.g. `… (1).xlsx`) is caught in the
  insert worker (`find_identity_conflict` → `__CONFLICT__:<stored name>`) and opens the same comparison.
- **Analyze (read-only, `POST /api/files/analyze`):** `Card.read_for_compare()` reads the file without any DB write (`File.dry_run`), `Card.records()`
  is the very mapping `insert()` stores, and `file_diff.compare()` matches those rows with `CardTransactions` of the stored file (amounts rounded like the
  INTEGER columns; same voucher serial + other values = *changed*). Status: `identical` / `new_transactions` / `missing_rows` / `other`.
  **`missing_rows` = any stored row absent from the new file** (a newer download only ever adds rows, so this is an anomaly to investigate: wrong
  file, truncated export, rows deleted or corrected by the issuer). It wins over every other difference except a different card/month/format (`other`).
  Its report carries an `investigation` block: each missing row in full (id, dates, amount, serial, extra info, category, description, links to other
  features, closest look-alikes among the new file's unmatched rows), both files' facts (rows, date range, total, size, mtime, when stored) and
  data-driven hints (are the missing rows the tail/head/a block/scattered, do they predate the new file's range, totals, work at stake).
  The page can copy it as a text report. Layout differences (header row, columns, header cells of both files when the archived copy exists, rows,
  tables) are listed for every status.
- **Decision (`POST /api/files/apply-update`, one DB transaction in `DataBase.apply_card_file_update`):** `update` keeps every row in place (same ID →
  category, description, splits, timeline/bill/recurring/Spotify/housing links survive), inserts only the new rows and corrects *changed* rows; it never
  deletes and is **refused while the status is `missing_rows`**. `replace` deletes all stored rows (and their splits) and inserts the new file — the only
  way forward after investigating. Afterwards the old archived copy moves to
  `Trash_ShmuelFamiliy_Inputs/<format>/<timestamp>_<name>` and the new file takes its place; `File.Updated_At/Update_Kind/Update_Added/_Changed/_Removed`
  drive the "⟳ עודכן" badge in the stored-files table.
- **History:** every update/replace writes a `FileUpdateHistory` row (keyed by format + card + month, since the file's name can change): the old file's
  name, rows, tagged rows, when it was stored, what the update added/changed/removed and whether the old copy went to the trash. Rows of an updated file
  never keep the old file's name (`Source_file` is the new name), so this table is the only trace of it; `/api/files/db-files` returns it per file
  (`history`) and the stored-files table shows it under the file. `DataBase.drop_file` deletes the history with the file (and deletes `TableMeta` before
  `File`, which it must because of the foreign key).
- `routes/file_update_routes._format_of` identifies the single file itself when `Parser`'s folder scan skipped it (Parser drops `x.xlsx` when `x (1).xlsx`
  is in the folder, because it treats a name contained in another as the same file with another extension).
- Never call `Card.insert()`-style code twice for the same month; when adding a card format, add its mapping in `Card.records()` only.

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
