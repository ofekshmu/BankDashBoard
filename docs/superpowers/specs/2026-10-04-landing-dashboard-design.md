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
| מעקב עציצים | plants needing water today+overdue | "עציצים להשקיה" | overdue count, plants watered automatically today (v1.28.0) |
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
| 11 | מעקב עציצים (`/plants`) | due / overdue plants, automatic waterings today (info) | plants payload `summary` | green none due · amber due · red overdue |
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

## Additions — v1.27.0

### Attention strip
- A card between the header and the grid, titled **דורש תשומת לב**, with one line per
  amber/red block: dot · block title · the block's `attention` text · `‹`. Red first, then
  amber, each in layout order. Clicking a line opens that block's page (the monthly line opens
  the block's current month).
- `attention` is a new field on every block (`landing_service.block(..., attention=)`), kept only
  when the dot is amber or red, otherwise `null`:
  monthly "N התראות ב<month>", accounts "N חשבונות לא עודכנו מעל 30 יום", housing
  "תשואה שנתית שלילית <pct>", Spotify "N חברים בחוב · <total>", plants: overdue / due today /
  each only when non-zero (automatic waterings need no action and are not listed), joined with " · ". Singular forms for 1 (`count_text`).
- Only visible (not hidden) blocks count. When every visible block has answered and none is
  flagged, the strip shows "הכל תקין — אין דברים שדורשים טיפול"; while blocks are still loading
  it stays hidden. Hidden in edit mode. Lines wrap under 480 px.

### Refresh + freshness
- Every successful `/api/landing/<block>` response carries `age`: whole seconds since the data
  was computed (the cached copy itself is stored without it).
- `?fresh=1` skips the cached copy and recomputes; the new result replaces the cache. A failed
  fresh request is not cached and leaves the previous cached copy in place.
- Header refresh button (↻) reloads every visible live block with `fresh=1`; it spins and is
  disabled while running, and the blocks show "מרענן…" in place of their age.
- Each live block shows "עודכן עכשיו / לפני N דק׳ / לפני N שעות" at its bottom, from
  `Date.now() - age`, repainted every 30 s.

### Customize layout
- **סידור** in the header enters edit mode (button turns into **סיום**, a banner explains the
  controls and offers **איפוס**). In edit mode all blocks are shown, hidden ones dimmed with a
  dashed border; card links and the month picker are inactive.
- Per block: drag to reorder (HTML5 drag-and-drop, desktop), → / ← to move one place earlier /
  later (touch and keyboard; focus stays on the control), and an eye button to hide/show.
- Saved per browser in `localStorage['landing_layout_v1'] = {order: [ids], hidden: [ids]}`,
  every access in try/catch. Unknown ids are dropped and blocks added later are appended, so
  the layout survives new blocks. Default: live blocks in menu order, then the tiles.
- Hidden blocks are not rendered and not fetched. Showing one again fetches it.
- If every block is hidden the grid says so and points to **סידור**.

## Out of scope
- Live data for ארגונית, ניתוח קטגוריאלי, חיפוש (description only, by decision).
- Changing any feature page.

## Additions — v1.29.0

- **Shortcut tiles:** the description-only blocks (ארגונית, ניתוח קטגוריאלי, חיפוש) render as compact
  tiles in their own "קיצורי דרך" row under the KPI grid (`#tiles`, `minmax(180px, 1fr)`, ~50 px tall).
  Layout editing keeps one saved `order` list, but arrows and drag move a block only within its group
  (KPI blocks or tiles); the saved order is KPI blocks first, then tiles.
- **Colour:** header band `linear-gradient(120deg, #1e2a4a → #1f4a62 → #1e9d8b)` with white text and
  translucent buttons; soft teal/navy radial tint on the page background; block icons in a teal-light
  badge; a 3 px strip on top of each KPI card coloured by its dot (`data-dot`); the attention box has a
  right border (amber, red when any item is red, teal when all is fine).
- **Monthly block — net income and net investments:** `extra.flow` = `[previous month, current month]`,
  each `{key, label, net, invest}`, from the monthly payload exactly as the monthly page's general chart
  uses it: `net` = `general_net[0]` / `general_current_net` (cash included), `invest` =
  `general_investments_out − general_investments_in` (index 0 / current). These `general_*` figures are
  relative to the real current month, whatever month the payload is for. Rendered as a 2×2 table
  (נטו / השקעות נטו × month); net coloured teal/red by sign, investments in the page's amber `#e8a020`.
  `landing_service.month_flow(payload, today)`; `build_monthly(..., today)` (no date → empty flow).
- **Month picker:** the dropdown is replaced by a horizontal strip of months (newest on the right),
  scroll-snapped so the centred month is the selected one, with a "פתח את <month>" button.
  Finger swipe = native scroll; a vertical mouse-wheel notch steps one month (past either end the page
  scrolls normally); ← → Home End step / jump, Enter opens; tapping another month centres it, tapping
  the selected month opens it. The choice survives a refresh repaint. On ≥560 px the monthly block spans
  two grid rows so its neighbours keep their natural height.
