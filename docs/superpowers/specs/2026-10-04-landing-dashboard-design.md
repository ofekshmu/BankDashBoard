# Landing Dashboard (sign-in gate + status blocks) — Design

Date: 2026-10-04 · Branch: `Dev/GeneralFeatures` · Target version: 1.26.0

## Goal

Turn the public landing page (`/`, project-root `index.html`) into a private home screen:
nothing is visible until the user signs in; after sign-in it shows one status block per
menu item, each with a short description and (where agreed) a small piece of live status.

## Decisions (from brainstorming)

| Topic | Decision |
|---|---|
| Privacy | `/` shows **only a sign-in popup** to a visitor without a session. The dashboard appears after a successful sign-in. No financial data in the page markup; all status comes from authenticated endpoints. |
| Layout | **A KPI dashboard**: slim header + a grid of simple KPI blocks — nothing else. All marketing (hero, "features", sample numbers) is removed, and so is the month strip (the monthly block has its own month picker). |
| Data loading | **Approach A** — one small endpoint per block, each block loads independently, short server-side cache. |

## Page

### Gate
- On load the page calls the existing `GET /api/auth/check`.
  - Not authenticated → a centred sign-in popup on a neutral background (existing
    `/api/auth/verify` flow and password field). The dashboard markup stays hidden
    (`hidden` attribute, not merely covered) and no `/api/landing/*` request is made.
  - Authenticated (now or after a successful sign-in) → the popup fades out and the
    dashboard renders; blocks start loading.
- **התנתקות** (sign out) in the header calls the existing `/api/auth/logout`, clears the
  local flag and returns to the popup.
- The existing `?auth=required&next=…` redirect behaviour is kept: after sign-in the user
  is forwarded to `next` when present.

### Layout — a dashboard, not a marketing page
- **Header:** greeting by time of day (בוקר טוב / צהריים טובים / ערב טוב / לילה טוב),
  today's date (Hebrew), version badge, התנתקות.
- **KPI grid:** `repeat(auto-fill, minmax(240px, 1fr))` — 3–4 columns desktop, 1 on
  phones; no horizontal scroll at 320/375 px. Blocks with live data come first (in menu
  order), description-only blocks last, as compact link tiles.
- Nothing else on the page: the hero, the "features" section and the month strip are removed.
- Visual language: white cards, 16px radius, light shadow, app palette (navy `#1e2a4a`,
  teal `#1e9d8b`, bg `#f4f6f9`), RTL Hebrew, tabular numerals for KPI values.

### Block anatomy (simple KPI block)
- Top row: small icon (inline SVG outline) + title + colour dot — green (fine), amber
  (worth a look), red (act now), grey (no data).
- **One headline KPI** in large type (the block's main number or short value) with a
  one-line caption under it.
- Up to **3 small detail lines** (e.g. the names behind the number). Bills block is the
  exception at **5 detail lines** (all 5 bill types with their average). No paragraphs.
- Description-only blocks: icon + title + one-line description, rendered as compact tiles.
- Whole card is a link to the page wrapped in a stretched `<a class="card-link">`; some
  blocks add one extra control (month picker) **outside** the link.
- Numbers inside RTL captions/details are wrapped in `<span dir="ltr">` for correct
  positioning; numeric KPIs are LTR but right-aligned in the block.
- Loading: skeleton shimmer in the status area. Error: "לא זמין כרגע" on that block only
  (other blocks unaffected). Blocks without live data show description only.

## Blocks

Headline KPI per block (large number) → caption → details:

| Block | Headline KPI | Caption | Details (≤3 lines) |
|---|---|---|---|
| ניתוח חודשי | alerts this month (count) | "התראות ב<month name>" | month picker + פתח |
| חשבונות | total value of all accounts (₪) | "שווי כל החשבונות" | stale accounts (>30 days) with last-update date |
| כרטיסים | number of cards active this month | "כרטיסים פעילים החודש" | card label + month total, top 3 |
| דיור | annual return (%) | "תשואה שנתית (5% עליית ערך)" | total return on sale %, net profit ₪ |
| ציר זמן | last created event's title | "האירוע האחרון שנוצר" | its date |
| מעקב חשבונות | sum of the 5 averages (₪/month) | "ממוצע חודשי — 5 החשבונות הנפוצים" | all 5 types with their average (5 lines) |
| Spotify | total owed (₪) | "חובות פתוחים" | members in debt + amount (≤3, "+N" if more) |
| מעקב עציצים | plants needing water today+overdue | "עציצים להשקיה" | overdue count, auto pending confirmation |
| חיובים חוזרים | next expected charge amount (₪) | name + "ב-<date>" | — |
| תייגן | last tagged transaction amount (₪) | its name | category, date |
| קבצים | last updated file's date | "קובץ אחרון" | file name, format/type |

Data sources and dot rules:

| # | Block (link) | Live status | Source (same numbers as the page) | Dot |
|---|---|---|---|---|
| 1 | ניתוח חודשי (`/general/<current>`) | alert count for the current month; month picker (months from `/api/general/list`) + "פתח" | current month's cached general data: `alerts` + organizer alerts | green 0 · amber 1–2 · red ≥3 |
| 2 | חשבונות (`/general/<latest>?panel=accounts`) | **total value of all accounts** (as on the page) · accounts not updated > 30 days (names, oldest date) | accounts payload (`accounts['Total']` last point; per-account last-update dates) | green none stale · amber ≥1 stale |
| 3 | כרטיסים (`/card-analysis`) | **cards active in the current month** (card label + this month's charge total) | card-analysis data for the current month | grey if none |
| 4 | דיור (`/housing`) | **annual return** and **total return on sale** (5% yearly appreciation, as on the page) + net profit | housing `mortgage` payload: `annual_return_pct`, `total_return_pct`, computed profit | green ≥0 · red <0 |
| 5 | ציר זמן (`/timeline`) | **last created event** (title, its date) | timeline events, newest `Created_At` | — |
| 6 | ארגונית (`/organizer`) | none (description only) | — | — |
| 7 | מעקב חשבונות (`/bills`) | **average monthly payment for the 5 most common bill types** | bill types + entries exactly as `/api/bills/types` + `/api/bills/entries` serve them; per type the bills page's own monthly average (all-time view): entries with a transaction only, `abs(amount ?? tx_amount)`, entries with neither skipped, total ÷ merged half-month span (`calcSpanMonths`); top 5 types by number of counted entries | — |
| 8 | ניתוח קטגוריאלי (`/categories`) | none | — | — |
| 9 | חיפוש (`/search`) | none | — | — |
| 10 | Spotify (`/spotify`) | **only members in debt and how much** (name + amount); "אין חובות" when none | `compute_all_balances` (members with negative balance) | green none · amber ≥1 |
| 11 | מעקב עציצים (`/plants`) | due / overdue plants, auto waterings awaiting confirmation | plants payload `summary` | green all 0 · amber due/pending · red overdue |
| 12 | חיובים חוזרים (`/recurring`) | **next upcoming expected charge** (name, date, amount) | recurring data: earliest `next_expected` ≥ today | — |
| 13 | תייגן (`/tagger`) | **last tagged transaction** (name, amount, category, date) | `get_recently_tagged(limit=1)` | — |
| 14 | קבצים (`/files`) | **last updated file** (file name, format/type, date) | File table, newest `Last_update` | — |

Block order follows the sidebar menu.

## API

New blueprint `source/routes/landing_routes.py` (registered in `WebApp.py`; grep first to
avoid duplicate routes). Every route is behind the existing `_require_auth` gate (not in
`_PUBLIC_PATHS`) → 401 without a session.

- `GET /api/landing/<block>` for `block` in
  `monthly, accounts, cards, housing, timeline, bills, spotify, plants, recurring, tagger, files`
  → `{ok: true, dot: 'green'|'amber'|'red'|'grey'|null, kpi: str, caption: str, details: [str, ...], extra: {...}}`
  (block-specific details and captions; `extra` for the monthly month list). Unknown block → 404.
  Response headers: `Cache-Control: no-store`.
- Failure responses: `{ok: false, error: 'לא זמין כרגע'}` with HTTP 500. Not cached; each request
  re-fetches.
- Monthly block reads months straight from `BankTransactions` via `DataBase` (not from
  `general_list`, which silently falls back to disk files on pool exhaustion).
- Accounts block uses `_cash_balance_map(strict=True)` so DB errors surface as an unavailable
  block instead of returning a wrong total.
- Each block's computation lives in `source/landing_service.py` as one function per block,
  reusing existing functions (no duplicated business logic). Each is wrapped so a failure
  returns `{ok: false, error}` for that block only.
- Server-side cache: 5 minutes per block (process memory), so repeated home-screen visits
  are instant; invalidated naturally by TTL.

## Error handling
- Block endpoint exception → `{ok:false, error: 'לא זמין כרגע'}` + HTTP 500 + logged with
  traceback; the block shows "לא זמין כרגע". Not cached.
- Missing data (e.g. no current-month data yet) → `dot: 'grey'` with a short neutral detail.

## Testing
- `tests/test_landing_service.py`: each block function against small fakes/stubs of its
  data source (shape of `facts`, dot thresholds, "no data" cases).
- `tests/test_landing_routes.py`: 401 without session; 200 + shape with session (service
  monkeypatched); unknown block 404; one failing block doesn't affect another.
- Headless browser (harness): without session only the popup is visible and no
  `/api/landing` request fires; after sign-in the grid renders, blocks fill independently,
  a forced block failure shows "לא זמין כרגע", no horizontal scroll at 375 px.
- Real-data smoke (authenticated test client, read-only).

## Out of scope
- Live data for ארגונית, ניתוח קטגוריאלי, חיפוש (description only, by decision).
- Changing any feature page.
