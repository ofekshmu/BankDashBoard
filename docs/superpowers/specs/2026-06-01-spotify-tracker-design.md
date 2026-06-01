# Spotify Tracker — Design Spec
**Date:** 2026-06-01  
**Status:** Approved

---

## Overview

A new page accessible from the sidebar named "Spotify Tracker". It helps the app owner (Ofek) track the monthly Spotify Premium Family subscription charge and the reimbursements received from family members. It calculates each member's running balance, shows who owes money and by how much (in ₪ and months), and generates PDF reports to share with family members.

---

## Data Model

Three new SQLite tables added to `ShmuelFamiliy.db` via `database.py`:

### `SpotifyMembers`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `name` | TEXT NOT NULL | Display name |
| `is_exempt` | INTEGER | 1 = owner or wife (counted in split, never tracked for balance) |
| `is_active` | INTEGER | 1 = active; soft-delete by setting to 0 |
| `created_at` | TEXT | ISO date |

### `SpotifyMonthlyCharge`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `month` | TEXT NOT NULL | Format: YYYY-MM, unique |
| `total_amount` | REAL NOT NULL | Full Spotify charge that month |
| `member_count` | INTEGER NOT NULL | Snapshot of active members that month |
| `tx_id` | INTEGER | Optional FK to source BankTransaction |
| `confirmed` | INTEGER | 0 = pending, 1 = confirmed by user |

`per_person_share` is always derived: `total_amount / member_count`. Never stored.

### `SpotifyMemberPayments`
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `member_id` | INTEGER NOT NULL | FK → SpotifyMembers |
| `amount` | REAL NOT NULL | |
| `payment_date` | TEXT NOT NULL | ISO date |
| `tx_id` | INTEGER | Optional FK to BankTransactions or CardTransactions |
| `note` | TEXT | Optional free text |
| `created_at` | TEXT | ISO date |

A `tx_id` can only be assigned to one `SpotifyMemberPayments` row (enforced in API logic).

---

## Balance Calculation

Computed on the fly, never stored. For each paying member (is_exempt = 0):

**Total debited** = sum of `per_person_share` for every confirmed month since member was active  
**Total credited** = sum of all `SpotifyMemberPayments.amount` for that member  
**Balance** = credited − debited

| Balance | Status | Display |
|---|---|---|
| < 0 | Owes | `₪|balance|` + `ceil(|balance| / current_share)` months |
| = 0 | Even | Balanced |
| > 0 | Ahead | `₪balance` + `floor(balance / current_share)` months ahead |

"Current share" = latest confirmed month's `per_person_share`.  
Months are always relative to the current date.

---

## Architecture

### New files
- `source/html/SpotifyTracker.html` — self-contained RTL page, same design tokens as `Bills.html`
- `source/SpotifyTracker.py` — all balance logic and PDF generation; keeps `WebApp.py` thin

### Routes added to `source/WebApp.py`

| Method | Route | Purpose |
|---|---|---|
| GET | `/spotify` | Serve SpotifyTracker.html |
| GET | `/api/spotify/members` | List members |
| POST | `/api/spotify/members` | Add member |
| PUT | `/api/spotify/members/<id>` | Edit name / toggle active |
| DELETE | `/api/spotify/members/<id>` | Soft delete |
| GET | `/api/spotify/charges` | List all monthly charges |
| POST | `/api/spotify/charges` | Add/confirm a charge |
| PUT | `/api/spotify/charges/<id>` | Edit a confirmed charge |
| GET | `/api/spotify/charges/suggestions` | Suggest Spotify charge from transactions |
| GET | `/api/spotify/payments` | List member payments |
| POST | `/api/spotify/payments` | Assign transaction or add manual payment |
| DELETE | `/api/spotify/payments/<id>` | Remove a payment |
| GET | `/api/spotify/unmatched` | Spotify-categorized txs not yet assigned |
| GET | `/api/spotify/balance` | Full balance summary for all members |
| GET | `/api/spotify/report` | Generate PDF (`?member_id=X` or `?all=1`) |

### Sidebar entry
`<a class="nav-item" href="/spotify">Spotify Tracker</a>` added to every HTML page that includes the sidebar nav (`output.html` and all standalone pages).

---

## Frontend Behavior

### Top bar (always visible)
- Current month's charge + per-person share
- Total outstanding (sum of negative balances across all paying members)
- Count of unmatched Spotify-categorized transactions
- PDF export button → opens export modal

### Member tabs
- One tab per active paying member (is_exempt = 0)
- Inline badge: `⚠️ חייב ₪X` / `— מאוזן` / `✅ +N חודשים`
- First tab: "Overview" — all members in a grid + unmatched payments queue

### Member detail — left card
- Member name
- Balance status card: color-coded (red/grey/green), shows ₪ + months relative to today
- Current per-person share
- "Assign payment" button

### Member detail — right panel
**Payment history table:** date | amount | month credited | source (tx name or "ידני") | remove  
**Assign payment modal:** shows unmatched Spotify-categorized transactions; user selects one to link, or enters manual amount + date  
**Subscription price history table:** when charge or member count changed | total | members | per-person share

### Monthly charge confirmation
Yellow banner if current month has no confirmed charge: "לא אושר חיוב לחודש זה" with "Confirm from transactions" button showing the auto-suggested transaction. User confirms or enters manually.

### PDF export modal
Radio: "All members" or individual member selector. Calls `/api/spotify/report` and triggers browser download.

---

## PDF Report

Generated server-side with `reportlab`. Hebrew, RTL.

**All-members report:**
- Header: report title + current month + generated date
- Summary table: name | total paid | total owed | balance status
- Per-member section: full payment history

**Single-member report:**
- Balance status prominently at top
- Full payment history
- Clean enough to forward directly to that person

---

## Charge Auto-Detection

`/api/spotify/charges/suggestions` queries BankTransactions for outgoing transactions whose `Name` or `Description` contains "Spotify" (case-insensitive), that recur monthly, and that have not yet been confirmed as a charge for their respective month. Returns the top candidate per unconfirmed month.

If the suggested amount differs from the previously confirmed month, the UI flags it as a potential price change.

---

## Edge Cases

| Scenario | Behaviour |
|---|---|
| Member count changes mid-history | Each `SpotifyMonthlyCharge` row snapshots its own `member_count`; balance always uses that row's count |
| Month with no confirmed charge | Excluded from balance calculations — no phantom debits |
| Paying member removed | Historical debits/credits remain; no new debits after deactivation |
| You and wife (is_exempt=1) | Included in `member_count` for correct share math; no tab, no balance tracking |
| Duplicate transaction assignment | A `tx_id` can only appear in one `SpotifyMemberPayments` row; unmatched queue excludes already-assigned transactions |
| Price change | Detected by comparing new suggestion to last confirmed amount; highlighted in UI |
