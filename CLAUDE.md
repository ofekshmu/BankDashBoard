# BankDashBoard — Claude Context

## What this app is

A personal finance dashboard that parses raw Excel files downloaded from Bank Leumi, stores them in a local SQLite database, and serves a Flask web app with monthly analysis, category breakdowns, a file organizer, and cash tracking.

---

## Repository layout

```
source/
  WebApp.py          — Flask app, all routes, HTML generation helpers
  AppManager.py      — CLI entry point, orchestrates parsing → DB → analysis
  database.py        — DataBase singleton (SQLite via sqlite3)
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

The app runs on Vercel (serverless). Entry point: `source/WebApp.py`. The database is SQLite; the Vercel path differs from local — see `fill_missing.py` and `database.py` for path resolution. Do not hardcode local Windows paths (e.g. `C:\\Users\\ofeks\\...`).
