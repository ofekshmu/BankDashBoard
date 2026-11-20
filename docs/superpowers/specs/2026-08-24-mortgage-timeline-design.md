# Mortgage/Housing Timeline — Design Spec
**Date:** 2026-08-24
**Status:** Approved

---

## Overview

A new "Timeline" view inside the existing housing/mortgage panel (`panel-housing` in `Base_template.html`, rendered by `source/src_utils/mortgage.py`) that lets the user log important events over the life of the mortgage — payments, milestones, anything they consider worth remembering — and optionally link each event to one or more transactions from `BankTransactions`/`CardTransactions`, with a per-transaction note.

This does **not** add a new right-menu nav item. The housing panel gains two small pill sub-tabs at its top — "Overview" (the existing KPI content) and "Timeline" (new) — that toggle client-side within the same panel.

This is single-property scoped: no apartment/mortgage ID column anywhere, since the app currently tracks one mortgage.

---

## Data Model

Two new tables in `database.py`, created lazily via `db.ensure_timeline_tables()` (same `CREATE TABLE IF NOT EXISTS` convention as `ensure_bill_tables()`), called wherever the housing panel is generated/regenerated.

### `TimelineEvents`
| Column | Type | Notes |
|---|---|---|
| `ID` | SERIAL PK | |
| `Name` | TEXT NOT NULL | Not unique — duplicate name+date combinations are allowed |
| `Event_Date` | DATE NOT NULL | |
| `Description` | TEXT | Optional |
| `Color` | TEXT | Hex string, picked from the shared swatch palette |
| `Created_At` | TIMESTAMP DEFAULT now() | |

### `TimelineEventTransactions`
| Column | Type | Notes |
|---|---|---|
| `ID` | SERIAL PK | |
| `Event_ID` | INTEGER REFERENCES `TimelineEvents(ID)` ON DELETE CASCADE | |
| `Transaction_Table` | TEXT NOT NULL | `'BankTransactions'` or `'CardTransactions'` |
| `Transaction_ID` | INTEGER NOT NULL | Row id in that table |
| `Note` | TEXT | Optional, per-link |

Unlike `BillEntries` (which caps at two fixed transaction-slot columns), this is a proper join table since an event can link an arbitrary number of transactions. `get_timeline_events()` fetches events with their linked transactions via a `LEFT JOIN` against `TimelineEventTransactions`, resolving each link's actual transaction row with a `CASE WHEN Transaction_Table = ...` join against both `BankTransactions` and `CardTransactions`, following the same resolution pattern as `get_bill_entries()`.

---

## Backend API (`WebApp.py`)

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/timeline/events` | List all events with linked transactions |
| POST | `/api/timeline/events` | Create event (`name`, `event_date`, `description`, `color`) |
| PUT | `/api/timeline/events/<id>` | Edit event fields |
| DELETE | `/api/timeline/events/<id>` | Delete event (cascades link rows) |
| POST | `/api/timeline/events/<id>/transactions` | Link a transaction (`table`, `transaction_id`, `note`) |
| DELETE | `/api/timeline/events/<id>/transactions/<link_id>` | Unlink one transaction |
| GET | `/api/timeline/nearby-transactions?date=YYYY-MM-DD` | Transactions from both tables within ±30 days of `date`, for the linking picker |

All routes require the existing auth check used by other API routes in `WebApp.py`.

---

## Frontend

### Sub-tabs
Two pill buttons injected at the top of `panel-housing`'s markup (built server-side alongside the rest of the panel in `mortgage.py`): "Overview" and "Timeline". Client-side JS shows/hides two inner containers (`#housing-overview`, `#housing-timeline`) — a local toggle, independent of the page-level `showPanel()` mechanism used for right-menu nav.

### Timeline widget
Custom-built vanilla JS/CSS (no external timeline library), consistent with the app's no-build-step, CDN-script architecture (Chart.js is already loaded this way for other charts).

- **Axis**: horizontal, rolling window sized to fit currently-visible events. Scroll-wheel/pinch + `+`/`−` buttons to zoom; drag to pan. Mobile gets a simplified, touch-friendly layout (fewer ticks, larger targets) via existing responsive breakpoints.
- **Markers**: each event renders as a dot on the axis with a speech-bubble box colored by `Color`, pointing to its date. Events on the same/nearby date stack vertically above the point.
- **Minimize/expand toggle**: a switch above the timeline (persisted in `localStorage`) controls whether bubbles always show full text, or minimize to a colored dot and expand to show name+date only on hover.
- **Add event**: (a) click empty timeline space → form opens pre-filled with that date; (b) "Add event" button above the timeline → same form, blank. Fields: name, date, description, color swatches (reusing the `COLORS`/`.c-opt` pattern from `Bills.html`), and a transaction-linking section.
- **Transaction linking UI**: calls `/api/timeline/nearby-transactions?date=...` (±30 days around the event's date), lets the user search/select multiple transactions, add a short note per link — modeled visually on the linked-transaction section in `Bills.html`.
- **Edit/delete**: clicking an existing bubble reopens the same form pre-filled, with a delete button. Editing supports changing any field and adding/removing linked transactions.

---

## Out of scope
- Multiple properties/mortgages (single-property app currently)
- Recurring/templated events
- Notifications or reminders triggered by event dates (the user described this as a memory/reference aid, not an alerting feature)
