# General (Non-Mortgage) Timeline — Design Spec
**Date:** 2026-08-26
**Status:** Approved

---

## Overview

Extends the existing mortgage-scoped Timeline feature (housing panel's "ציר זמן" sub-tab) into a general-purpose life-events timeline, reachable from its own new sidebar nav item. The same underlying vertical-timeline widget, event modal (view/add/edit), and transaction-linking UI are reused unchanged — only the data is now scoped by a new `Category` field, and the housing sub-tab becomes an implicit `category='mortgage'` filter on top of the same shared engine, rather than a separate feature.

This does **not** duplicate the timeline widget into a new standalone HTML page (the way `Bills.html`/`SpotifyTracker.html` are separate files). Instead, a new panel (`panel-timeline`) is added inside `Base_template.html`'s existing SPA structure, alongside `panel-housing`/`panel-accounts`, reusing the exact same `_tl*` JS functions already built for the housing timeline. This avoids maintaining two copies of ~800 lines of widget code.

---

## Data Model

One column added to the existing `TimelineEvents` table (`source/database.py`):

```sql
ALTER TABLE TimelineEvents ADD COLUMN IF NOT EXISTS Category TEXT NOT NULL DEFAULT 'mortgage';
```

- `'mortgage'` — an event tied to the mortgage/housing panel (all pre-existing rows keep this value via the `DEFAULT`, since the mortgage timeline is the only thing that has ever created rows in this table).
- `'general'` — a life event created from the new standalone timeline page, unrelated to the mortgage.

No new table. `TimelineEventTransactions` (the transaction-linking join table) is untouched — linking works identically regardless of an event's category.

**Tagging is automatic, not user-facing.** There is no category dropdown in the add-event form. Which value gets written is determined entirely by which UI surface the "add" action was triggered from:
- Adding from the housing panel's "ציר זמן" sub-tab → `category='mortgage'`.
- Adding from the new top-level "ציר זמן" page → `category='general'`.

---

## Backend API changes (`source/WebApp.py`, `source/database.py`)

- `GET /api/timeline/events` gains an optional `?category=mortgage|general` query parameter. When present, `get_timeline_events()` filters `WHERE Category = %s`. When absent, all events are returned regardless of category (used by the new general page's default "show all" view).
- `POST /api/timeline/events` accepts an optional `category` field in the JSON body (`'mortgage'` or `'general'`), validated against that fixed set; defaults to `'general'` if omitted (a defensive fallback only — every real caller in this app always sends an explicit value; direct API use without one is the only path that would hit the default).
- `PUT /api/timeline/events/<id>` does **not** allow changing `category` — an event's category is fixed at creation and immutable via the API. (Editing an event never lets the user move it between categories; if that's ever needed, the user deletes and recreates it. This keeps the edit form identical between mortgage and general events.)
- No other route changes. Transaction-linking routes are category-agnostic (they operate on `Event_ID`, not category).

---

## Frontend changes (`source/html/Base_template.html`)

### New sidebar nav item and panel
A new `<a class="nav-item" onclick="showPanel('timeline', this)">ציר זמן</a>`-style entry is added to the sidebar (matching the existing `nav-item` pattern used for Accounts/Housing/etc.), and a new empty `<div id="panel-timeline" class="panel"></div>` shell, following the same lazy client-rendered pattern as `panel-housing`.

### Shared rendering engine, now scope-aware
The existing `_tl*` functions (`_renderTimeline`, `_tlDrawAxis`, `_tlBuildModal`, `_tlOpenAddModal`, `_tlOpenViewModal`, `_tlSubmitEvent`, etc.) are generalized to operate against whichever container/context is currently active, controlled by a new module-level `_tlActiveScope` variable (`'mortgage'` when driven from the housing sub-tab, `'all'` when driven from the new top-level panel). This variable determines:
- What `?category=` (if any) is appended to `GET /api/timeline/events` when loading data for that context.
- What `category` value is sent on `POST /api/timeline/events` when adding a new event from that context (`'mortgage'` when `_tlActiveScope==='mortgage'`, `'general'` when adding from the top-level panel — even though that panel's fetch may currently be showing "all" or "mortgage" via its filter toggle, new events added from it are always tagged `'general'`, since that's the surface for general events).

### New top-level panel content
`panel-timeline` builds the same axis-wrap/toolbar/modal markup as the housing timeline (via the shared functions), plus one new UI element specific to this panel: a 3-way filter toggle above the axis — "הכל" (all, default) / "משכנתא" (mortgage) / "כללי" (general) — implemented as pill buttons matching the existing `.hs-subtab-btn` visual style. Selecting a filter re-fetches (or client-side re-filters, whichever is simpler given the small expected data volume for a personal app — implementation detail for the plan to decide) and re-renders the axis with only matching events. The housing sub-tab keeps no such control — it always implicitly filters to `category='mortgage'` with no visible toggle.

### No visual badge
Per the approved design, there is no per-event visual marker distinguishing mortgage vs. general events on the timeline itself — the filter toggle is the only mechanism for telling them apart, and when "הכל" (all) is selected, mortgage and general events render identically, indistinguishable by appearance.

---

## Out of scope
- A category picker in the add/edit form (tagging is fully automatic by page).
- Changing an event's category after creation.
- A visual badge/icon distinguishing categories when the "all" filter is active.
- Any new database table — this is a single-column addition to the existing schema.
