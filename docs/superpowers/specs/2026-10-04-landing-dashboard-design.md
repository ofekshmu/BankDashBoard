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
| Layout | Slim header + blocks grid + the existing month strip. The marketing hero and "features" sections (with their sample numbers) are removed. |
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

### Layout
- **Header:** greeting by time of day (בוקר טוב / צהריים טובים / ערב טוב / לילה טוב),
  today's date (Hebrew), version badge, התנתקות.
- **Blocks grid:** `repeat(auto-fill, minmax(260px, 1fr))` — 3–4 columns desktop, 1 on
  phones; no horizontal scroll at 320/375 px.
- **Month strip:** the existing "Jump to Any Month" strip, unchanged in behaviour, below
  the grid.
- Visual language: white cards, 16px radius, light shadow, app palette (navy `#1e2a4a`,
  teal `#1e9d8b`, bg `#f4f6f9`), RTL Hebrew.

### Block anatomy
- Icon (inline SVG outline, white-stroke style consistent with the app), title, one-line
  description.
- Status area (only for blocks with live data): a colour dot — green (fine), amber (worth a
  look), red (act now), grey (no data) — plus 1–3 short facts.
- Whole card is a link to the page; some blocks add one extra control (month picker).
- Loading: skeleton shimmer in the status area. Error: "לא זמין כרגע" on that block only
  (other blocks unaffected). Blocks without live data show description only.

## Blocks

| # | Block (link) | Live status | Source (same numbers as the page) | Dot |
|---|---|---|---|---|
| 1 | ניתוח חודשי (`/general/<current>`) | alert count for the current month; month picker (months from `/api/general/list`) + "פתח" | current month's cached general data: `alerts` + organizer alerts | green 0 · amber 1–2 · red ≥3 |
| 2 | חשבונות (`/general/<latest>?panel=accounts`) | **total value of all accounts** (as on the page) · accounts not updated > 30 days (names, oldest date) | accounts payload (`accounts['Total']` last point; per-account last-update dates) | green none stale · amber ≥1 stale |
| 3 | כרטיסים (`/card-analysis`) | **cards active in the current month** (card label + this month's charge total) | card-analysis data for the current month | grey if none |
| 4 | דיור (`/housing`) | **annual return** and **total return on sale** (5% yearly appreciation, as on the page) + net profit | housing `mortgage` payload: `annual_return_pct`, `total_return_pct`, computed profit | green ≥0 · red <0 |
| 5 | ציר זמן (`/timeline`) | **last created event** (title, its date) | timeline events, newest `Created_At` | — |
| 6 | ארגונית (`/organizer`) | none (description only) | — | — |
| 7 | מעקב חשבונות (`/bills`) | **average monthly payment for the 5 most common bill types** | bill entries: top 5 types by entry count; mean amount per month | — |
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
  → `{ok: true, dot: 'green'|'amber'|'red'|'grey'|null, facts: [...], extra: {...}}`
  (block-specific `facts`; `extra` for the monthly month list). Unknown block → 404.
- Each block's computation lives in `source/landing_service.py` as one function per block,
  reusing existing functions (no duplicated business logic). Each is wrapped so a failure
  returns `{ok: false, error}` for that block only.
- Server-side cache: 5 minutes per block (process memory), so repeated home-screen visits
  are instant; invalidated naturally by TTL.

## Error handling
- Block endpoint exception → `{ok:false}` + logged with traceback; the block shows
  "לא זמין כרגע".
- Missing data (e.g. no current-month data yet) → `dot: 'grey'` with a short neutral fact.

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
