# Plant Tracker (מעקב עציצים) — Design

Date: 2026-10-03 · Branch: `Dev/GeneralFeatures` · Target version: 1.17.0

## Goal

A new sidebar page, **מעקב עציצים**, listing every house plant with a 14-day daily
timeline showing irrigation status, irrigation mode and soil status, plus
rule-based care suggestions.

## Decisions (from brainstorming)

| Topic | Decision |
|---|---|
| Auto irrigation | ~~Schedule + confirm~~ → **automatic since v1.28.0**: every scheduled day is recorded as watered with no approval (see "Automatic irrigation" below) |
| Plant logo | Generated SVG icon per plant type, on a coloured badge, with the name's initial |
| Timeline span | Last 14 days |
| Suggestions | Rule-based (no AI) |
| v1 extras | Today summary bar · fertilize/repot/prune/pest log · seasonal interval adjust |
| Storage model | **Option B** — one materialized `PlantDays` row per plant per day, created on the first load of each day |

Out of scope for v1: room/location grouping, photo upload, hardware/sensor integration, AI advice.

## Data model

Created idempotently by `DataBase.ensure_plant_tables()` (same pattern as
`ensure_spotify_tables` / `ensure_timeline_tables`).

### `Plants`
| Column | Type | Notes |
|---|---|---|
| `id` | SERIAL PK | |
| `name` | TEXT NOT NULL | |
| `plant_type` | TEXT NOT NULL | `cactus`/`monstera`/`fern`/`succulent`/`herb`/`flower`/`tree`/`sprout` — selects SVG icon |
| `color` | TEXT NOT NULL | hex; auto-picked from palette on create, user-editable |
| `irrigation_mode` | TEXT NOT NULL | `manual` / `auto` |
| `interval_days` | INTEGER NOT NULL DEFAULT 3 | target watering interval (both modes; drives "due" and suggestions) |
| `auto_time` | TEXT NULL | `HH:MM`, auto mode only |
| `season_ack` | TEXT NULL | season key (`2026-summer` / `2026-winter`) the seasonal tip was applied or dismissed for |
| `created_at` | TIMESTAMP DEFAULT now() | |
| `deleted_at` | TIMESTAMP NULL | soft delete; restorable |

### `PlantEvents`
| Column | Type | Notes |
|---|---|---|
| `id` | SERIAL PK | |
| `plant_id` | INTEGER FK → Plants | |
| `event_type` | TEXT | `water` / `fertilize` / `repot` / `prune` / `pest` |
| `event_at` | TIMESTAMP | defaults to now in the UI; editable date + time |
| `source` | TEXT | `manual` / `auto` (recorded by the schedule, v1.28.0+) / `auto_confirmed` (confirmed by hand, before v1.28.0) |
| `note` | TEXT NULL | |

### `PlantDays`
| Column | Type | Notes |
|---|---|---|
| `plant_id` | INTEGER FK | PK part |
| `day` | DATE | PK part |
| `soil_status` | TEXT NULL | `dry` / `humid` / `wet` / NULL (unknown) |
| `watered` | BOOLEAN DEFAULT false | true if any `water` event that day |
| `auto_expected` | BOOLEAN DEFAULT false | auto plant scheduled to water this day |
| `auto_confirmed` | BOOLEAN DEFAULT false | the scheduled auto watering was recorded (automatically since v1.28.0) |

**Invariant:** `PlantDays` history is immutable with respect to schedule changes —
changing `interval_days`/`auto_time` affects only days not yet materialized
(today forward). Only explicit user edits (soil, water event, confirm) modify
past rows.

## Daily materialization

`materialize_plant_days(today)` — runs at the start of `GET /api/plants`:

1. For each active plant, find its last materialized day (or `created_at::date - 1`).
2. Insert rows for every missing day up to and including `today`
   (`INSERT ... ON CONFLICT DO NOTHING` → safe to run concurrently/repeatedly).
3. `auto_expected` for an auto plant = the day is on the schedule, i.e.
   `(day - anchor) % interval_days == 0`, where `anchor` is the date of the most
   recent `water` event (or `created_at` if none).
4. `soil_status` is **not** carried forward — unknown until the user sets it.

`watered` is recomputed for a day whenever a `water` event on that day is
added/deleted.

## API — `source/routes/plant_routes.py` (Blueprint `plants_bp`, registered in `WebApp.py`)

Before adding, grep `WebApp.py` for `/plants` and `api_plants` to avoid the
duplicate-endpoint pitfall. All responses `{ok: bool, ...}`; errors `{ok:false, error}`.

| Method & path | Purpose |
|---|---|
| `GET /plants` | serve `source/html/PlantTracker.html` |
| `GET /api/plants` | materialize, then return `{plants, days (14), events (14d), suggestions, summary, today}` |
| `POST /api/plants` | create plant |
| `PUT /api/plants/<id>` | edit plant (name/type/color/mode/interval/auto_time) |
| `DELETE /api/plants/<id>` | soft delete |
| `POST /api/plants/<id>/restore` | restore |
| `GET /api/plants/deleted` | list soft-deleted plants |
| `POST /api/plants/<id>/events` | add event `{event_type, event_at?, note?}`; `event_at` defaults to now |
| `DELETE /api/plants/events/<event_id>` | remove a mistaken event |
| `PUT /api/plants/<id>/soil` | `{day, soil_status}` |
| `POST /api/plants/<id>/dismiss-season` | set `season_ack` to the current season key |
| `POST /api/plants/water-due` | water every plant currently due/overdue (UI confirms first) |

Every mutating endpoint returns the same payload as `GET /api/plants` so the
client can refresh its cache in one round trip.

## Suggestions engine — `source/src_utils/plant_suggestions.py`

Pure functions over (plant, days, events, today) → list of
`{plant_id, level: info|warn|alert, text_he, action?}`. `action` is an optional
one-click fix, e.g. `{type:'set_interval', value:2}`.

Rules (v1):
1. **Overdue** — days since last water > `interval_days` → alert "באיחור של N ימים".
2. **Dries too fast** — soil `dry` within ≤1 day after watering, twice in 14 days → suggest `interval_days - 1` (min 1).
3. **Overwatering risk** — soil `wet` 3+ consecutive days → warn, suggest skipping next watering / `interval_days + 1`.
4. ~~**Auto not confirmed**~~ — removed in v1.28.0 (automatic waterings are recorded without approval).
5. **Seasonal** — season key = `YYYY-summer` (Jun–Sep) or `YYYY-winter` (Dec–Feb; Dec counts toward the next year's key). If the plant's `season_ack` ≠ current key: summer → suggest `max(1, round(interval_days * 0.75))` (only if it differs); winter → suggest `round(interval_days * 1.25)` (only if it differs). Applying or dismissing sets `season_ack` = current key, so the tip appears once per season.
6. **Fertilize reminder** — no `fertilize` event in 30 days during Mar–Sep → info.
7. **No soil data** — no soil status recorded in the last 7 days → info "עדכן מצב אדמה".

## Today summary

`{due_today, overdue, auto_today}` counts (`auto_today`: automatic plants the schedule watered today; was `auto_pending_confirm` before v1.28.0), plus the "השקה לכל הממתינים"
button → confirm dialog → `POST /api/plants/water-due`.

## Front end — `source/html/PlantTracker.html`

Standalone page, RTL, uses the dashboard palette (navy `#1e2a4a`, teal `#1e9d8b`,
bg `#f4f6f9`) and the same sidebar markup as other pages, with
`<a class="nav-item active" href="/plants">מעקב עציצים</a>`. The new nav link is
added to **every** sidebar copy (Base_template.html, Bills.html, Files.html,
CardAnalysis.html, SpotifyTracker.html, RecurringCharges.html, Search.html,
Tagger.html, WebApp.py inline sidebars, …) — find them with
`grep -rn 'href="/card-analysis"'`. Version badge populated from `/api/version`.

Layout:
1. Header — title, `+ עציץ חדש`, deleted/restore button.
2. Summary bar.
3. Suggestions panel (collapsible; action buttons apply the fix via `PUT /api/plants/<id>`).
4. Plant rows — SVG badge · name · mode badge (`ידני` / `אוטומטי · כל N ימים · HH:MM`) · 14 day cells (today at the leading edge).
   Each cell: drop icon (filled = watered, outlined dashed = auto expected not
   confirmed, none = not watered), soil colour strip (dry = sand, humid = light
   teal, wet = deep blue, unknown = grey), tiny markers for fertilize/repot/prune/pest.
5. Day editor popover (click a cell): soil buttons, "הושקה ב-" datetime input
   (default now for today, the day's noon otherwise), add other event types,
   confirm-auto button when applicable, list/delete that day's events.
6. Plant modal: name, type picker (icon grid), colour, mode, interval, auto time, delete.

Plant SVG icons: one inline `<symbol>` per type, rendered in white on the
coloured rounded badge, with the plant initial in a small corner chip.

### Caching (once per day)
- `localStorage['plants_cache']` = `{date, payload}`, all access in try/catch.
- On load: if `cache.date === today` → render from cache, no request.
  Otherwise → `GET /api/plants`, store, render.
- Any mutation response replaces the cache.
- If storage is unavailable, fall back to fetching every load.

## Error handling
- Validation (unknown type/mode/soil, interval < 1, bad `HH:MM`) → 400 `{ok:false,error}`.
- Unknown/deleted plant id → 404.
- Path params decoded defensively (Vercel percent-encoding gotcha).
- Client shows a toast on `ok:false` and keeps the last good render.

## Testing
- `tests/test_plant_materialize.py` — gap filling, idempotency, auto schedule
  anchor, interval change does not rewrite past rows, watered recompute.
- `tests/test_plant_suggestions.py` — one test per rule, including seasonal months.
- `tests/test_plant_routes.py` — Flask test client: CRUD, events default time,
  soil update, confirm-auto, water-due, soft delete/restore, validation errors.
- Manual run in the browser pane: create plants of several types, water, set
  soil, confirm auto, reload same day (no request), mobile width.
- Tests run with global Python310 (venv lacks psycopg2/dotenv).

## Versioning
Feature commit bumps minor: → **1.17.0**.

## Addition — search & sort (v1.27.0)

Client-side only (`PlantTracker.html`), above the room chips; hidden when there are no plants.

- **Search** — matches the plant name, its type's Hebrew label or its room name
  (case-insensitive substring). `/` focuses the box (not while typing or with a popup open),
  Esc or ✕ clears it. A "N מתוך M" count shows while anything is filtered; no match →
  "לא נמצאו עציצים התואמים ל"…"" with a clear button. Not persisted.
- **Sort** (`localStorage['plants_sort']`):
  - `status` (default, "לפי דחיפות") — overdue, due, ok, auto; within a status the most days
    past the interval first (never-watered counts as most urgent); ties by name.
  - `last_water` — never watered first, then longest since the last watering.
  - `name` — Hebrew locale order. `type` — by type label, then name.
- **קיבוץ לפי חדר** (`localStorage['plants_grouped']`, default on) — on: room groups as before,
  sorted inside each group; off: one flat sorted list. The room chips filter in both modes and
  keep their all-plants counts while searching.

## Change — automatic irrigation without approval (v1.28.0)

- `plant_service.record_auto_waterings(store, today)` runs at the end of every `materialize`:
  each automatic plant's scheduled (`auto_expected`), not yet recorded day in the 14-day window,
  up to and including today, gets a `water` event at the plan's time (config time → plant
  `auto_time` → 07:00) with `source='auto'`, and the day is marked `watered` + `auto_confirmed`.
  Today counts for the whole day, even before its time passes. Days older than the window are
  not backfilled.
- **Skipping:** deleting an automatic watering (`auto` or legacy `auto_confirmed`) sets the day's
  `auto_expected` to false, so it is never recorded again. The page asks "לבטל את ההשקה
  האוטומטית של יום זה? היא לא תירשם שוב."
- **Realign** (`realign_config`): waterings with `source='auto'` move with the plan (removed from
  days the plan no longer waters; newly scheduled days are recorded by the next materialize).
  Days with a watering the user entered (`manual`) or confirmed by hand (`auto_confirmed`) are
  never changed.
- Removed: `POST /api/plants/<id>/confirm-auto`, `confirm_auto`, the "auto_unconfirmed"
  suggestion, the day popup's confirm button, the dashed "ממתין לאישור" drop and its legend item.
- Summary: the "אוטומטי ממתין לאישור" stat became "N הושקו אוטומטית היום" (`auto_today`).
- Landing plants block: automatic waterings no longer make it amber; `auto_today` is an info
  detail line ("N עציצים הושקו אוטומטית היום") and is not part of the attention line.
