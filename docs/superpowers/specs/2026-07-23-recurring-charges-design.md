# Recurring Charges — Design Spec
**Date:** 2026-07-23
**Status:** Approved

---

## Overview

A new page, accessible from the sidebar as "חיובים חוזרים" (Recurring Charges), that automatically detects recurring monthly charges across **every category** — not just the מנויים ("subscriptions") category — by clustering transactions on business-name similarity and monthly cadence. It surfaces, per recurring charge: current status, a 12-month timeline, full statistics, and alerts when a charge's amount suddenly changes or the charge appears to have stopped.

This differs from:
- **Bills page** (`Bills.html`): tracks known, user-configured recurring bills by type/group; this page auto-*discovers* recurring charges from raw transaction history, including ones the user never tagged.
- **מנויים category analysis**: only shows transactions already tagged with that category; this page finds recurring charges regardless of category, and unifies them with already-categorized subscriptions in one view.

---

## Detection Algorithm

Runs on regen, reading the last **13 months** of data (12 full months + current partial month, so the most recent complete month can be evaluated for a "missing" alert).

1. **Candidate pool**: all expense transactions — `BankTransactions.Out > 0` and `CardTransactions.Charge_Value > 0` — excluding:
   - `WHITDRAWAL_CATEGORY` and `EXCLUDED_CATEGORY` (existing reserved categories)
   - Housing categories already tracked on the Housing page (שכירות, דירת קבלן)
   - Any transaction manually excluded via `RecurringExcludedTransactions` (see Data Model)
2. **Normalize** each transaction's `Name` for comparison: strip digits/reference numbers, lowercase, collapse whitespace.
3. **Cluster** transactions across the whole window by fuzzy name similarity (`difflib.SequenceMatcher` ratio ≥ threshold, tuned during implementation — start ~0.82). Amount is **not** part of the grouping condition — a business's charge can change over time and still belong to the same group.
4. Within each cluster, find the **longest run of consecutive months** with at least one matching transaction. A cluster becomes an active **recurring group** once that streak reaches **≥ 3 consecutive months**.
5. **Amount-changed detection**: for each occurrence in an active group, compare it to the group's running median amount. A deviation beyond a threshold (start ~15%) flags that specific occurrence as "amount changed" — the streak is not broken.
6. **Missing-charge detection**: if the most recently *fully completed* calendar month has no matching occurrence for an active group, flag the group `possibly_stopped`. (The current, still-in-progress month is never evaluated for this — avoids false alarms early in the month.)
7. **Stats per group** (computed fresh every regen): average amount, total spent (sum of all matched occurrences in the window), first payment date, last payment date, occurrence count, min amount, max amount, next-expected date (see below).
8. **Next-expected estimate**: based on the most common day-of-month across the group's occurrences (mode; ties broken by most recent), projected onto the following month (clamped to that month's last day if it doesn't have that many days).

### Persisted overrides
Detection is fully recomputed from current transaction data on every regen — nothing about *membership* is persisted directly. Instead, three small override tables layer user corrections on top, the same pattern already used by `TransactionSplits` / `SpotifyDismissedPayments`:

| Table | Columns | Purpose |
|---|---|---|
| `RecurringDismissed` | `group_key` (PK) | Hides a detected group from the active view |
| `RecurringMerges` | `secondary_key`, `primary_key` | Folds one cluster into another before streak/stat computation |
| `RecurringExcludedTransactions` | `table_name`, `tx_id` (composite PK) | Removes one specific transaction from the candidate pool entirely, regardless of which cluster it would otherwise join |

`group_key` = the normalized form of the cluster's single most-frequent exact `Name` string. Derived from data, not a DB identity — stable across regens as long as the dominant name string doesn't change; a genuine rename is handled via manual merge.

---

## Data Model

Three new tables (`database.py`, same connection/pattern as the Spotify tables):

### `RecurringDismissed`
| Column | Type | Notes |
|---|---|---|
| `group_key` | TEXT PK | Normalized dominant name of the dismissed cluster |
| `dismissed_at` | TIMESTAMP | |

### `RecurringMerges`
| Column | Type | Notes |
|---|---|---|
| `id` | SERIAL PK | |
| `secondary_key` | TEXT NOT NULL | Group folded away |
| `primary_key` | TEXT NOT NULL | Group it's folded into |
| `created_at` | TIMESTAMP | |

### `RecurringExcludedTransactions`
| Column | Type | Notes |
|---|---|---|
| `table_name` | TEXT | `'BankTransactions'` \| `'CardTransactions'` |
| `tx_id` | INTEGER | |
| `excluded_at` | TIMESTAMP | |
| | | Composite PK: (`table_name`, `tx_id`) |

No table stores computed group membership, streaks, or stats — those are always derived fresh at regen time from live transaction data plus the three override tables above.

---

## Architecture

### New files
- `source/html/RecurringCharges.html` — self-contained RTL page, same design tokens/components as `Bills.html` / `SpotifyTracker.html` / `Search.html`
- `source/RecurringCharges.py` — detection algorithm, stats, and override application; keeps `WebApp.py` thin (mirrors `SpotifyTracker.py`)

### Routes added to `source/WebApp.py`

| Method | Route | Purpose |
|---|---|---|
| GET | `/recurring` | Serve cached page, or the shared first-load regen screen (`_not_generated_html`-style) if no cached HTML exists yet |
| GET | `/api/recurring/regenerate` | SSE stream — single endpoint that both starts and streams progress (mirrors Organizer's `/api/organizer/regenerate`); used for both the automatic first-load run and the manual regen button |
| GET | `/api/recurring/groups` | List all active (non-dismissed) groups with stats + timeline + status |
| GET | `/api/recurring/groups/dismissed` | List dismissed groups (for the restore UI) |
| POST | `/api/recurring/groups/<key>/dismiss` | Hide a group |
| POST | `/api/recurring/groups/<key>/restore` | Un-hide a previously dismissed group |
| POST | `/api/recurring/groups/merge` | Body: `{secondary_key, primary_key}` |
| POST | `/api/recurring/groups/<key>/exclude-tx` | Body: `{table, tx_id}` — pop one transaction out of a group permanently |
| POST | `/api/recurring/groups/<key>/tag` | Body: `{category}` — bulk-apply a category to every transaction currently matched in the group |

Generated HTML cached at `Outputs/recurring_charges.html` with a `.manifest.json` sidecar (dependency + DB-mtime tracking), following the exact convention used by `Outputs/general_analysis/` and `Outputs/category_analysis/`.

### Sidebar entry
`<a class="nav-item" href="/recurring">חיובים חוזרים</a>` added to every page's sidebar nav, alongside the existing Spotify Tracker / Bills entries.

---

## Frontend Behavior

Single scrollable page (no tabs), same structural convention as `Bills.html` / `SpotifyTracker.html` / `Search.html`.

### KPI header row
- Total current monthly recurring commitment (sum of latest amount across all active groups)
- Count of active recurring groups
- Count needing attention (possibly-stopped or amount-changed)

Stacks into a grid on mobile, same pattern as existing KPI rows elsewhere in the app.

### Attention section
Rendered only when non-empty. Compact list of groups currently flagged `possibly_stopped` or `amount_changed`; clicking one scrolls to / expands its card below.

### 12-month trend chart
Total recurring spend per month for the last 12 months — the "total... looking a year back" view.

### By-business card list
- Search box + sort control (amount / name / status) above the list
- One card per group:
  - Name, category badge, current (latest) amount, status badge (active / amount changed / possibly stopped)
  - **12-month mini timeline strip** — kept **LTR** (oldest → newest, left → right) even on this RTL page, consistent with how this app already keeps dates/amounts/calendars LTR elsewhere (date-range picker, `.rc-amount`). Each of the 12 segments is colored: paid-as-expected / amount-changed / missing / before-group-started.
  - **Next-expected** label (e.g. "הבא: 5 באוג׳")
  - Expand toggle reveals:
    - Full stats block: average, total spent, first payment date, last payment date, occurrence count, min, max
    - Full matched-transaction history (date, amount, source table)
    - Action buttons: **Dismiss**, **Merge into…** (opens a picker over the other active groups), **Tag category…** (bulk-tag, with a confirmation showing how many transactions will change and how many already carry a different category), and a per-row **✕ remove from group** next to each transaction in the history (implements per-transaction exclusion)
- A small **"קבוצות מוסתרות" (hidden groups)** toggle/link surfaces dismissed groups with a Restore action, so a dismiss is never a silent dead end.

### Mobile adaptation
- KPI grid stacks vertically
- Trend chart shrinks to a simplified sparkline or scrolls horizontally (`overflow-x:auto`)
- Cards go full width (reusing the `Search.html` mobile card-stacking fix: the card container wraps, each block gets `flex-basis:100%` rather than relying on a non-existent wrapper class)
- The 12-month timeline strip scrolls horizontally inside its own `overflow-x:auto` container rather than shrinking illegibly

### Regen button
Reuses the Organizer page's `org-regen-btn` styling and behavior exactly: teal floating pill, bottom-corner, with a text label on desktop that collapses to a plain circle on mobile, showing live % while a regen is running. First visit with no cached file instead shows the shared `_not_generated_html()`-style full-page takeover (dark gradient background + floating log panel via the existing `_log_float_style()` / `_log_float_html()` / `_log_float_js()` helpers) — per the project's standing rule, these shared helpers are reused, never duplicated.

---

## Edge Cases

| Scenario | Behavior |
|---|---|
| Fuzzy match clusters two unrelated businesses together | User dismisses or, if only one transaction is the problem, removes that single transaction via per-transaction exclusion |
| Fuzzy match fails to cluster a renamed business (name changed too much) | User manually merges the two resulting groups |
| Group's amount changes permanently (e.g. price hike) | Streak stays intact; the changed occurrence is flagged, but subsequent occurrences at the new amount are normal (median naturally shifts over time) |
| Current (in-progress) month has no charge yet | Never flagged `possibly_stopped` — only fully completed months are evaluated |
| A dismissed group's underlying transactions later change enough to look genuinely different | Dismissal is keyed by `group_key` (normalized dominant name) — if the dominant name shifts enough to change the key, it can resurface as a new group; acceptable trade-off given manual dismiss/restore is one click either way |
| Bulk-tag applied to a group with mixed existing categories | Confirmation dialog shows counts before applying, so overwriting existing tags is never a surprise |
| Regen requested while one is already running | Same busy/409 handling pattern as the other regen endpoints (Organizer / Category) |
