# Recurring Charges Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `/recurring` page — auto-detects recurring monthly charges across all categories, shows per-group stats/timeline/alerts, and lets the user dismiss/merge/exclude/tag corrections.

**Architecture:** A standalone `source/RecurringCharges.py` module (mirrors `SpotifyTracker.py`) owns the fuzzy-clustering detection algorithm and stats as pure, DB-agnostic functions over plain dicts, tested without touching the database. `database.py` gets three new override tables plus thin CRUD wrappers, following the exact `ensure_spotify_tables()` pattern. `WebApp.py` gets a cached-HTML route (`/recurring`) matching the Organizer/Category-analysis regen convention (first-load auto-regen screen via the shared `_log_float_style/html/js` helpers, then a persistent floating regen button), plus action routes for dismiss/restore/merge/exclude/tag. A new `source/html/RecurringCharges.html` renders from a JSON blob embedded at generation time, using Chart.js (already a project dependency via `Bills.html`) for the 12-month trend chart.

**Tech Stack:** Python 3.10, Flask, psycopg2 (Postgres/Neon), Chart.js 4.4.0 (CDN, already used by `Bills.html`), vanilla JS (no framework, matching every other page in this app).

---

## File Structure

- **Create** `source/RecurringCharges.py` — normalization, fuzzy clustering, streak/alert/stats computation, next-expected estimate. Pure functions taking/returning plain dicts; no direct DB access except one `get_recurring_groups(db)` orchestration function at the bottom.
- **Create** `source/Testing/test_recurring_charges.py` — unit tests for the pure algorithm functions (no DB) + integration tests for the DB override CRUD (real DB, `RC_TEST_` prefixed data, cleaned up per test) — matching `test_spotify_tracker.py`'s exact style (plain `assert` + `print("PASS: ...")`, `if __name__ == '__main__':` runner).
- **Create** `source/html/RecurringCharges.html` — self-contained RTL page, same design tokens as `SpotifyTracker.html`/`Search.html`.
- **Modify** `source/database.py` — add `ensure_recurring_tables()` + CRUD methods for the 3 override tables (append near `ensure_spotify_tables()`, ~line 2799).
- **Modify** `source/WebApp.py` — add `/recurring` page route, `/api/recurring/*` routes, `_not_generated_recurring_html()` helper.
- **Modify** 7 sidebar files — add the new nav-item link: `Search.html`, `SpotifyTracker.html`, `Tagger.html`, `Bills.html`, `Base_template.html`, `Files.html`, `Organizer_Table.html`.
- **Modify** `VERSION` — bump patch after each commit, per project standing rule.

---

### Task 1: Database layer — override tables + CRUD

**Files:**
- Modify: `source/database.py` (insert after `ensure_spotify_tables()`, i.e. after the method ending at line 2799 in the version researched — search for `DataBase.__spotify_tables_ready = True` and insert the new method directly after it)
- Test: `source/Testing/test_recurring_charges.py`

- [ ] **Step 1: Add `ensure_recurring_tables()` and CRUD methods to `database.py`**

Add a new class-level flag next to `__spotify_tables_ready` (line 160):
```python
    __recurring_tables_ready = False
```

Then add these methods immediately after `ensure_spotify_tables()`:

```python
    def ensure_recurring_tables(self) -> None:
        """Create Recurring Charges override tables if they don't exist yet."""
        if DataBase.__recurring_tables_ready:
            return
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS RecurringDismissed (
                Group_Key    TEXT      PRIMARY KEY,
                Dismissed_At TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS RecurringMerges (
                ID            SERIAL    PRIMARY KEY,
                Secondary_Key TEXT      NOT NULL,
                Primary_Key   TEXT      NOT NULL,
                Created_At    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS RecurringExcludedTransactions (
                Table_Name   TEXT      NOT NULL,
                TX_ID        INTEGER   NOT NULL,
                Excluded_At  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (Table_Name, TX_ID)
            )
        """)
        self.connection.commit()
        DataBase.__recurring_tables_ready = True

    def get_recurring_dismissed(self) -> set:
        rows = self.cursor.execute("SELECT Group_Key FROM RecurringDismissed").fetchall()
        return {r[0] for r in rows}

    def dismiss_recurring_group(self, group_key: str) -> None:
        self.cursor.execute(
            "INSERT INTO RecurringDismissed (Group_Key) VALUES (%s) ON CONFLICT DO NOTHING",
            (group_key,)
        )
        self.connection.commit()

    def restore_recurring_group(self, group_key: str) -> None:
        self.cursor.execute("DELETE FROM RecurringDismissed WHERE Group_Key=%s", (group_key,))
        self.connection.commit()

    def get_recurring_merges(self) -> dict:
        """Returns {secondary_key: primary_key}."""
        rows = self.cursor.execute("SELECT Secondary_Key, Primary_Key FROM RecurringMerges").fetchall()
        return {r[0]: r[1] for r in rows}

    def add_recurring_merge(self, secondary_key: str, primary_key: str) -> None:
        self.cursor.execute(
            "DELETE FROM RecurringMerges WHERE Secondary_Key=%s", (secondary_key,)
        )
        self.cursor.execute(
            "INSERT INTO RecurringMerges (Secondary_Key, Primary_Key) VALUES (%s, %s)",
            (secondary_key, primary_key)
        )
        self.connection.commit()

    def get_recurring_excluded_tx(self) -> set:
        """Returns a set of (table_name, tx_id) tuples."""
        rows = self.cursor.execute(
            "SELECT Table_Name, TX_ID FROM RecurringExcludedTransactions"
        ).fetchall()
        return {(r[0], r[1]) for r in rows}

    def exclude_recurring_tx(self, table_name: str, tx_id: int) -> None:
        self.cursor.execute(
            "INSERT INTO RecurringExcludedTransactions (Table_Name, TX_ID) VALUES (%s, %s) "
            "ON CONFLICT DO NOTHING",
            (table_name, int(tx_id))
        )
        self.connection.commit()
```

- [ ] **Step 2: Write the failing test for table creation**

Create `source/Testing/test_recurring_charges.py` with this first test:

```python
"""Tests for Recurring Charges feature."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import DataBase


def test_recurring_tables_exist():
    db = DataBase()
    db.ensure_recurring_tables()
    for tbl in ('recurringdismissed', 'recurringmerges', 'recurringexcludedtransactions'):
        row = db.cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name=%s)",
            (tbl,)
        ).fetchone()
        assert row[0] is True, f"{tbl} table missing"
    print("PASS: recurring tables exist")


if __name__ == '__main__':
    test_recurring_tables_exist()
    print("\nAll tests passed")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd source && python Testing/test_recurring_charges.py`
Expected: FAIL with `AttributeError: 'DataBase' object has no attribute 'ensure_recurring_tables'` (method not added yet)

- [ ] **Step 4: Add the methods from Step 1, then re-run**

Run: `cd source && python Testing/test_recurring_charges.py`
Expected: `PASS: recurring tables exist` then `All tests passed`

- [ ] **Step 5: Write and run CRUD round-trip tests**

Append to `source/Testing/test_recurring_charges.py` (above the `if __name__` block):

```python
def test_dismiss_restore_roundtrip():
    db = DataBase()
    db.ensure_recurring_tables()
    key = 'RC_TEST_dismiss_key'
    db.cursor.execute("DELETE FROM RecurringDismissed WHERE Group_Key=%s", (key,))
    db.connection.commit()

    assert key not in db.get_recurring_dismissed()
    db.dismiss_recurring_group(key)
    assert key in db.get_recurring_dismissed()
    db.restore_recurring_group(key)
    assert key not in db.get_recurring_dismissed()
    print("PASS: dismiss/restore round-trip")


def test_merge_roundtrip():
    db = DataBase()
    db.ensure_recurring_tables()
    sec, prim = 'RC_TEST_secondary', 'RC_TEST_primary'
    db.cursor.execute("DELETE FROM RecurringMerges WHERE Secondary_Key=%s", (sec,))
    db.connection.commit()

    db.add_recurring_merge(sec, prim)
    merges = db.get_recurring_merges()
    assert merges.get(sec) == prim

    db.cursor.execute("DELETE FROM RecurringMerges WHERE Secondary_Key=%s", (sec,))
    db.connection.commit()
    print("PASS: merge round-trip")


def test_exclude_tx_roundtrip():
    db = DataBase()
    db.ensure_recurring_tables()
    db.cursor.execute(
        "DELETE FROM RecurringExcludedTransactions WHERE Table_Name=%s AND TX_ID=%s",
        ('BankTransactions', -999999)
    )
    db.connection.commit()

    assert ('BankTransactions', -999999) not in db.get_recurring_excluded_tx()
    db.exclude_recurring_tx('BankTransactions', -999999)
    assert ('BankTransactions', -999999) in db.get_recurring_excluded_tx()

    db.cursor.execute(
        "DELETE FROM RecurringExcludedTransactions WHERE Table_Name=%s AND TX_ID=%s",
        ('BankTransactions', -999999)
    )
    db.connection.commit()
    print("PASS: exclude-tx round-trip")
```

And update the `if __name__ == '__main__':` block to call all four:
```python
if __name__ == '__main__':
    test_recurring_tables_exist()
    test_dismiss_restore_roundtrip()
    test_merge_roundtrip()
    test_exclude_tx_roundtrip()
    print("\nAll tests passed")
```

Run: `cd source && python Testing/test_recurring_charges.py`
Expected: all four `PASS:` lines, then `All tests passed`

- [ ] **Step 6: Commit**

```bash
git add source/database.py source/Testing/test_recurring_charges.py VERSION
git commit -m "feat(recurring): add override tables (dismiss/merge/exclude) with CRUD"
```
(Bump `VERSION` patch first, per project rule — see Task 8 for the exact bump step repeated at the end of every task's commit.)

---

### Task 2: Detection algorithm — normalization + fuzzy clustering

**Files:**
- Create: `source/RecurringCharges.py`
- Test: `source/Testing/test_recurring_charges.py`

- [ ] **Step 1: Write failing tests for `normalize_name` and `cluster_transactions`**

Append to `source/Testing/test_recurring_charges.py` (imports go at the top, alongside the existing `from database import DataBase`):

```python
from datetime import date
from RecurringCharges import normalize_name, cluster_transactions


def test_normalize_name():
    assert normalize_name('NETFLIX.COM 123456') == 'netflix com'
    assert normalize_name('  Health  Insurance  99') == 'health insurance'
    assert normalize_name('') == ''
    assert normalize_name(None) == ''
    print("PASS: normalize_name")


def test_cluster_transactions_groups_similar_names():
    txs = [
        {'table': 'CardTransactions', 'id': 1, 'date': date(2026, 1, 5), 'name': 'NETFLIX.COM', 'amount': 39.9, 'category': 'מנויים'},
        {'table': 'CardTransactions', 'id': 2, 'date': date(2026, 2, 5), 'name': 'NETFLIX.COM', 'amount': 39.9, 'category': 'מנויים'},
        {'table': 'CardTransactions', 'id': 3, 'date': date(2026, 3, 6), 'name': 'NETFLIX COM 998211', 'amount': 44.9, 'category': 'מנויים'},
        {'table': 'BankTransactions', 'id': 4, 'date': date(2026, 1, 10), 'name': 'ELECTRIC COMPANY', 'amount': 210.0, 'category': 'חשבונות'},
    ]
    clusters = cluster_transactions(txs)
    assert len(clusters) == 2, f"expected 2 clusters, got {len(clusters)}"
    netflix_cluster = next(c for c in clusters if len(c['members']) == 3)
    assert {m['id'] for m in netflix_cluster['members']} == {1, 2, 3}
    print("PASS: cluster_transactions groups similar names")


def test_cluster_transactions_keeps_unrelated_separate():
    txs = [
        {'table': 'BankTransactions', 'id': 1, 'date': date(2026, 1, 1), 'name': 'SUPERMARKET A', 'amount': 300.0, 'category': 'מצרכים'},
        {'table': 'BankTransactions', 'id': 2, 'date': date(2026, 1, 2), 'name': 'GYM MEMBERSHIP', 'amount': 150.0, 'category': 'בריאות וכושר'},
    ]
    clusters = cluster_transactions(txs)
    assert len(clusters) == 2
    print("PASS: cluster_transactions keeps unrelated separate")
```

- [ ] **Step 2: Run to verify failure**

Run: `cd source && python Testing/test_recurring_charges.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'RecurringCharges'`

- [ ] **Step 3: Create `source/RecurringCharges.py` with normalization + clustering**

```python
"""
Recurring Charges — detection algorithm and stats.

Pure functions operate on plain dicts with keys:
  table, id, date (datetime.date), name, amount (positive float), category
No DB access except in get_recurring_groups() at the bottom.
"""
import re
import statistics
from datetime import date as _date
from difflib import SequenceMatcher

SIMILARITY_THRESHOLD = 0.82
AMOUNT_CHANGE_THRESHOLD = 0.15
MIN_STREAK_MONTHS = 3


def normalize_name(name) -> str:
    """Lowercase, strip digits/reference numbers and punctuation, collapse whitespace."""
    if not name:
        return ''
    s = str(name).lower()
    s = re.sub(r'\d+', '', s)
    s = re.sub(r'[^\w\s֐-׿]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def cluster_transactions(transactions: list) -> list:
    """
    Greedily cluster transactions by fuzzy normalized-name similarity.
    Amount is NOT part of the grouping condition (price changes stay in-group).

    Returns: list of {'norm_key': str, 'members': [tx, ...]}
    """
    clusters = []
    for tx in sorted(transactions, key=lambda t: t['date']):
        norm = normalize_name(tx['name'])
        best_cluster = None
        best_ratio = 0.0
        for c in clusters:
            ratio = name_similarity(norm, c['norm_key'])
            if ratio > best_ratio:
                best_ratio = ratio
                best_cluster = c
        if best_cluster is not None and best_ratio >= SIMILARITY_THRESHOLD:
            best_cluster['members'].append(tx)
        else:
            clusters.append({'norm_key': norm, 'members': [tx]})
    return clusters
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd source && python Testing/test_recurring_charges.py`
Expected: `PASS: normalize_name`, `PASS: cluster_transactions groups similar names`, `PASS: cluster_transactions keeps unrelated separate`, plus the earlier DB tests, then `All tests passed`

- [ ] **Step 5: Commit**

```bash
git add source/RecurringCharges.py source/Testing/test_recurring_charges.py VERSION
git commit -m "feat(recurring): add name normalization and fuzzy clustering"
```

---

### Task 3: Streak detection, amount-change flags, stats, next-expected

**Files:**
- Modify: `source/RecurringCharges.py`
- Test: `source/Testing/test_recurring_charges.py`

- [ ] **Step 1: Write failing tests**

Append to `source/Testing/test_recurring_charges.py`:

```python
from RecurringCharges import (
    month_key, find_longest_run, build_group_from_cluster,
)


def test_month_key():
    assert month_key(date(2026, 3, 5)) == '2026-03'
    assert month_key(date(2026, 11, 30)) == '2026-11'
    print("PASS: month_key")


def test_find_longest_run():
    assert find_longest_run(['2026-01', '2026-02', '2026-03']) == ['2026-01', '2026-02', '2026-03']
    assert find_longest_run(['2026-01', '2026-03', '2026-04', '2026-05']) == ['2026-03', '2026-04', '2026-05']
    assert find_longest_run([]) == []
    assert find_longest_run(['2026-06']) == ['2026-06']
    print("PASS: find_longest_run")


def test_build_group_from_cluster_qualifies_and_stats():
    members = [
        {'table': 'CardTransactions', 'id': 1, 'date': date(2026, 1, 5), 'name': 'NETFLIX', 'amount': 39.9, 'category': 'מנויים'},
        {'table': 'CardTransactions', 'id': 2, 'date': date(2026, 2, 5), 'name': 'NETFLIX', 'amount': 39.9, 'category': 'מנויים'},
        {'table': 'CardTransactions', 'id': 3, 'date': date(2026, 3, 5), 'name': 'NETFLIX', 'amount': 39.9, 'category': 'מנויים'},
    ]
    cluster = {'norm_key': 'netflix', 'members': members}
    group = build_group_from_cluster(cluster, today=date(2026, 4, 15))
    assert group is not None
    assert group['occurrence_count'] == 3
    assert group['average_amount'] == 39.9
    assert group['total_spent'] == round(39.9 * 3, 2)
    assert group['min_amount'] == 39.9
    assert group['max_amount'] == 39.9
    assert group['first_payment_date'] == date(2026, 1, 5)
    assert group['last_payment_date'] == date(2026, 3, 5)
    assert group['possibly_stopped'] is False  # last complete month (March) has an occurrence
    print("PASS: build_group_from_cluster qualifies + stats")


def test_build_group_from_cluster_rejects_short_history():
    members = [
        {'table': 'CardTransactions', 'id': 1, 'date': date(2026, 1, 5), 'name': 'ONEOFF', 'amount': 39.9, 'category': 'מנויים'},
        {'table': 'CardTransactions', 'id': 2, 'date': date(2026, 2, 5), 'name': 'ONEOFF', 'amount': 39.9, 'category': 'מנויים'},
    ]
    cluster = {'norm_key': 'oneoff', 'members': members}
    group = build_group_from_cluster(cluster, today=date(2026, 4, 15))
    assert group is None
    print("PASS: build_group_from_cluster rejects <3 occurrences")


def test_build_group_flags_possibly_stopped():
    members = [
        {'table': 'CardTransactions', 'id': 1, 'date': date(2026, 1, 5), 'name': 'GYM', 'amount': 150.0, 'category': 'בריאות וכושר'},
        {'table': 'CardTransactions', 'id': 2, 'date': date(2026, 2, 5), 'name': 'GYM', 'amount': 150.0, 'category': 'בריאות וכושר'},
        {'table': 'CardTransactions', 'id': 3, 'date': date(2026, 3, 5), 'name': 'GYM', 'amount': 150.0, 'category': 'בריאות וכושר'},
    ]
    # today is May 15 — April (last complete month) has no occurrence
    cluster = {'norm_key': 'gym', 'members': members}
    group = build_group_from_cluster(cluster, today=date(2026, 5, 15))
    assert group['possibly_stopped'] is True
    print("PASS: build_group_from_cluster flags possibly_stopped")


def test_build_group_flags_amount_changed():
    members = [
        {'table': 'CardTransactions', 'id': 1, 'date': date(2026, 1, 5), 'name': 'INTERNET', 'amount': 100.0, 'category': 'חשבון אינטרנט'},
        {'table': 'CardTransactions', 'id': 2, 'date': date(2026, 2, 5), 'name': 'INTERNET', 'amount': 100.0, 'category': 'חשבון אינטרנט'},
        {'table': 'CardTransactions', 'id': 3, 'date': date(2026, 3, 5), 'name': 'INTERNET', 'amount': 140.0, 'category': 'חשבון אינטרנט'},
    ]
    cluster = {'norm_key': 'internet', 'members': members}
    group = build_group_from_cluster(cluster, today=date(2026, 4, 1))
    changed_months = [o['month'] for o in group['occurrences'] if o['status'] == 'changed']
    assert changed_months == ['2026-03']
    print("PASS: build_group_from_cluster flags amount_changed")
```

- [ ] **Step 2: Run to verify failure**

Run: `cd source && python Testing/test_recurring_charges.py`
Expected: FAIL with `ImportError: cannot import name 'month_key'` (functions not added yet)

- [ ] **Step 3: Add the implementation to `source/RecurringCharges.py`**

Append these functions (after `cluster_transactions`):

```python
def month_key(d: _date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _parse_month_key(mk: str) -> _date:
    y, m = mk.split('-')
    return _date(int(y), int(m), 1)


def _months_apart(a: str, b: str) -> int:
    da, db = _parse_month_key(a), _parse_month_key(b)
    return (db.year - da.year) * 12 + (db.month - da.month)


def find_longest_run(months_sorted: list) -> list:
    """months_sorted: sorted list of distinct 'YYYY-MM' strings.
    Returns the longest run of consecutive months anywhere in the list."""
    if not months_sorted:
        return []
    best_run = [months_sorted[0]]
    cur_run = [months_sorted[0]]
    for i in range(1, len(months_sorted)):
        if _months_apart(months_sorted[i - 1], months_sorted[i]) == 1:
            cur_run.append(months_sorted[i])
        else:
            if len(cur_run) > len(best_run):
                best_run = cur_run
            cur_run = [months_sorted[i]]
    if len(cur_run) > len(best_run):
        best_run = cur_run
    return best_run


def _last_complete_month_key(today: _date) -> str:
    """The most recently fully-completed calendar month relative to today."""
    first_of_this_month = today.replace(day=1)
    last_complete = first_of_this_month
    # step back one day into the previous month, then take its month key
    prev_month_last_day = first_of_this_month - _timedelta_days(1)
    return month_key(prev_month_last_day)


def _timedelta_days(n):
    from datetime import timedelta
    return timedelta(days=n)


def build_group_from_cluster(cluster: dict, today: _date) -> dict:
    """
    Given a cluster (from cluster_transactions), compute whether it qualifies
    as a recurring group (longest run >= MIN_STREAK_MONTHS), and if so return
    its full stats/occurrence/alert payload. Returns None if it doesn't qualify.
    """
    members = cluster['members']
    by_month = {}
    for m in members:
        mk = month_key(m['date'])
        # keep the largest-amount occurrence if more than one in the same month
        if mk not in by_month or m['amount'] > by_month[mk]['amount']:
            by_month[mk] = m

    distinct_months = sorted(by_month.keys())
    longest_run = find_longest_run(distinct_months)
    if len(longest_run) < MIN_STREAK_MONTHS:
        return None

    amounts = [by_month[mk]['amount'] for mk in distinct_months]
    median_amount = statistics.median(amounts)

    occurrences = []
    for mk in distinct_months:
        tx = by_month[mk]
        deviates = (
            median_amount > 0
            and abs(tx['amount'] - median_amount) / median_amount > AMOUNT_CHANGE_THRESHOLD
        )
        occurrences.append({
            'month': mk,
            'date': tx['date'],
            'amount': tx['amount'],
            'table': tx['table'],
            'id': tx['id'],
            'status': 'changed' if deviates else 'paid',
        })

    last_month = distinct_months[-1]
    last_complete = _last_complete_month_key(today)
    possibly_stopped = _months_apart(last_month, last_complete) > 0

    # day-of-month mode, for next-expected estimate
    days = [m['date'].day for m in by_month.values()]
    day_mode = statistics.mode(days)
    next_month_date = _parse_month_key(last_complete)
    next_month_num = next_month_date.month + 1
    next_year = next_month_date.year + (1 if next_month_num > 12 else 0)
    next_month_num = 1 if next_month_num > 12 else next_month_num
    import calendar as _cal
    last_day = _cal.monthrange(next_year, next_month_num)[1]
    next_expected = _date(next_year, next_month_num, min(day_mode, last_day))

    latest_tx = by_month[last_month]
    return {
        'group_key': cluster['norm_key'],
        'name': latest_tx['name'],
        'category': latest_tx['category'],
        'current_amount': latest_tx['amount'],
        'occurrence_count': len(distinct_months),
        'average_amount': round(sum(amounts) / len(amounts), 2),
        'total_spent': round(sum(amounts), 2),
        'min_amount': min(amounts),
        'max_amount': max(amounts),
        'first_payment_date': by_month[distinct_months[0]]['date'],
        'last_payment_date': by_month[last_month]['date'],
        'possibly_stopped': possibly_stopped,
        'amount_changed': any(o['status'] == 'changed' for o in occurrences),
        'next_expected': next_expected,
        'occurrences': occurrences,
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd source && python Testing/test_recurring_charges.py`
Expected: all prior `PASS:` lines plus `PASS: month_key`, `PASS: find_longest_run`, `PASS: build_group_from_cluster qualifies + stats`, `PASS: build_group_from_cluster rejects <3 occurrences`, `PASS: build_group_from_cluster flags possibly_stopped`, `PASS: build_group_from_cluster flags amount_changed`, then `All tests passed`

- [ ] **Step 5: Commit**

```bash
git add source/RecurringCharges.py source/Testing/test_recurring_charges.py VERSION
git commit -m "feat(recurring): add streak detection, stats, and alert flags"
```

---

### Task 4: 12-month timeline + DB-fetching orchestration

**Files:**
- Modify: `source/RecurringCharges.py`
- Test: `source/Testing/test_recurring_charges.py`

- [ ] **Step 1: Write failing test for the timeline builder**

Append to `source/Testing/test_recurring_charges.py`:

```python
from RecurringCharges import build_timeline


def test_build_timeline_marks_paid_missing_and_before_start():
    occurrences = [
        {'month': '2026-02', 'status': 'paid'},
        {'month': '2026-03', 'status': 'changed'},
    ]
    first_payment_date = date(2026, 2, 10)
    timeline = build_timeline(occurrences, first_payment_date, today=date(2026, 4, 1))
    assert len(timeline) == 12
    by_month = {t['month']: t for t in timeline}
    assert by_month['2026-02']['status'] == 'paid'
    assert by_month['2026-03']['status'] == 'changed'
    assert by_month['2026-01']['status'] == 'before_start'
    assert by_month['2025-05']['status'] == 'before_start'
    print("PASS: build_timeline")
```

- [ ] **Step 2: Run to verify failure**

Run: `cd source && python Testing/test_recurring_charges.py`
Expected: FAIL with `ImportError: cannot import name 'build_timeline'`

- [ ] **Step 3: Implement `build_timeline` and the DB orchestration function**

Append to `source/RecurringCharges.py`:

```python
def build_timeline(occurrences: list, first_payment_date: _date, today: _date) -> list:
    """
    Returns 12 slots for the trailing 12 full months (not including the
    current in-progress month), each: {'month': 'YYYY-MM', 'status': ...}
    status is one of: 'paid', 'changed', 'missing', 'before_start'.
    """
    by_month = {o['month']: o['status'] for o in occurrences}
    last_complete = _last_complete_month_key(today)
    slots = []
    cursor = _parse_month_key(last_complete)
    for _ in range(12):
        mk = month_key(cursor)
        if mk in by_month:
            status = by_month[mk]
        elif _months_apart(month_key(first_payment_date.replace(day=1)), mk) < 0:
            status = 'before_start'
        else:
            status = 'missing'
        slots.append({'month': mk, 'status': status})
        # step back one month
        prev_month_num = cursor.month - 1
        prev_year = cursor.year - (1 if prev_month_num < 1 else 0)
        prev_month_num = 12 if prev_month_num < 1 else prev_month_num
        cursor = _date(prev_year, prev_month_num, 1)
    slots.reverse()  # oldest -> newest, kept LTR in the UI regardless of page RTL
    return slots


# ── Candidate pool + exclusions ────────────────────────────────────────────────

EXCLUDED_CATEGORIES = {'withdrawal', 'Excluded', 'שכירות', 'דירת קבלן'}


def fetch_candidate_transactions(db, months_back: int = 13) -> list:
    """
    Pull expense transactions (bank Out>0, card Charge_Value>0) from the last
    `months_back` months, excluding withdrawal/excluded/housing categories and
    anything in RecurringExcludedTransactions.
    Returns list of dicts: table, id, date, name, amount, category.
    """
    from datetime import date as _d, timedelta as _td
    cutoff = (_d.today().replace(day=1) - _td(days=months_back * 31))
    excluded_tx = db.get_recurring_excluded_tx()

    results = []
    for row in db.cursor.execute("""
        SELECT ID, Date, Name, Out, Category
        FROM BankTransactions
        WHERE Out > 0 AND Date >= %s
    """, (cutoff,)).fetchall():
        tx_id, tx_date, name, amount, category = row
        if ('BankTransactions', tx_id) in excluded_tx:
            continue
        if (category or '') in EXCLUDED_CATEGORIES:
            continue
        results.append({
            'table': 'BankTransactions', 'id': tx_id, 'date': tx_date,
            'name': name, 'amount': float(amount or 0), 'category': category or '',
        })

    for row in db.cursor.execute("""
        SELECT ID, Executed_Date, Name, Charge_Value, Category
        FROM CardTransactions
        WHERE Charge_Value > 0 AND Executed_Date >= %s
    """, (cutoff,)).fetchall():
        tx_id, tx_date, name, amount, category = row
        if ('CardTransactions', tx_id) in excluded_tx:
            continue
        if (category or '') in EXCLUDED_CATEGORIES:
            continue
        results.append({
            'table': 'CardTransactions', 'id': tx_id, 'date': tx_date,
            'name': name, 'amount': float(amount or 0), 'category': category or '',
        })

    return results


def get_recurring_groups(db, today: _date = None) -> list:
    """
    Full pipeline: fetch candidates -> cluster -> apply manual merges ->
    build group stats/timeline -> drop dismissed groups.
    Returns list of group dicts (see build_group_from_cluster), each with an
    added 'timeline' key (list of 12 slots).
    """
    if today is None:
        today = _date.today()

    transactions = fetch_candidate_transactions(db)
    clusters = cluster_transactions(transactions)

    # Apply manual merges: fold secondary cluster's members into primary's.
    merges = db.get_recurring_merges()  # {secondary_key: primary_key}
    by_key = {c['norm_key']: c for c in clusters}
    for secondary_key, primary_key in merges.items():
        sec = by_key.get(secondary_key)
        prim = by_key.get(primary_key)
        if sec and prim and sec is not prim:
            prim['members'].extend(sec['members'])
            clusters.remove(sec)
            del by_key[secondary_key]

    dismissed = db.get_recurring_dismissed()
    groups = []
    for cluster in clusters:
        group = build_group_from_cluster(cluster, today=today)
        if group is None:
            continue
        if group['group_key'] in dismissed:
            continue
        group['timeline'] = build_timeline(
            group['occurrences'], group['first_payment_date'], today=today
        )
        groups.append(group)

    groups.sort(key=lambda g: g['current_amount'], reverse=True)
    return groups
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd source && python Testing/test_recurring_charges.py`
Expected: all prior tests plus `PASS: build_timeline`, then `All tests passed`

- [ ] **Step 5: Write an integration test for `get_recurring_groups` against the real DB**

Append to `source/Testing/test_recurring_charges.py`:

```python
from RecurringCharges import get_recurring_groups
from datetime import date as _date_cls


def test_get_recurring_groups_end_to_end():
    db = DataBase()
    db.ensure_recurring_tables()

    # Insert 3 months of a fake recurring charge into BankTransactions (no FK
    # constraints, unlike CardTransactions.CardID -> Card), future-dated +
    # prefixed to avoid colliding with real data.
    test_name = 'RC_TEST_STREAMING_SVC'
    ids = []
    for (y, m) in [(2099, 1), (2099, 2), (2099, 3)]:
        row = db.cursor.execute("""
            INSERT INTO BankTransactions
                (Date, Name, Out, Income, Source_file, Category)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING ID
        """, (_date_cls(y, m, 5), test_name, 39.9, 0, 'RC_TEST', 'מנויים')).fetchone()
        ids.append(row[0])
    db.connection.commit()

    groups = get_recurring_groups(db, today=_date_cls(2099, 4, 15))
    match = next((g for g in groups if g['name'] == test_name), None)
    assert match is not None, "expected the test streaming charge to be detected as recurring"
    assert match['occurrence_count'] == 3
    assert len(match['timeline']) == 12

    # Cleanup
    db.cursor.execute(
        "DELETE FROM BankTransactions WHERE ID = ANY(%s)", (ids,)
    )
    db.connection.commit()
    print("PASS: get_recurring_groups end-to-end")
```

Update the `if __name__ == '__main__':` block to also call `test_get_recurring_groups_end_to_end()`.

Run: `cd source && python Testing/test_recurring_charges.py`
Expected: all `PASS:` lines including `PASS: get_recurring_groups end-to-end`, then `All tests passed`

- [ ] **Step 6: Commit**

```bash
git add source/RecurringCharges.py source/Testing/test_recurring_charges.py VERSION
git commit -m "feat(recurring): add 12-month timeline and DB orchestration pipeline"
```

---

### Task 5: Flask routes — page + regen SSE + action endpoints

**Files:**
- Modify: `source/WebApp.py`

- [ ] **Step 1: Add constants and the cached-HTML directory near the other `_DIR` constants**

Find where `CATEGORY_ANALYSIS_DIR` is defined (around line 53-56) and add directly after it:

```python
if os.getenv('VERCEL'):
    RECURRING_HTML = '/tmp/recurring_charges.html'
else:
    RECURRING_HTML = os.path.join(_PROJECT_DIR, 'Outputs', 'recurring_charges.html')
```

- [ ] **Step 2: Add `_not_generated_recurring_html()` — reuses the shared log-float helpers**

Add this function near `_not_generated_html` (after it, e.g. after line ~2933):

```python
def _not_generated_recurring_html() -> str:
    return f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>חיובים חוזרים</title>
{_log_float_style()}
</head>
<body>
  <div class="box">
    <div class="badge">חיובים חוזרים</div>
    <h2>מנתח חיובים חוזרים</h2>
    <p>מריץ ניתוח ראשוני — זה עשוי לקחת מספר שניות…</p>
  </div>
  {_log_float_html()}
  <script>
{_log_float_js()}
    showLogFloat('מנתח חיובים חוזרים…');
    var es = new EventSource('/api/recurring/regenerate');
    es.onmessage = function(e) {{
      if (e.data === 'done') {{ es.close(); location.reload(); }}
      else if (e.data.indexOf('error') === 0) {{ es.close(); appendLog('✗ שגיאה — ' + e.data, 'err'); }}
      else if (!isNaN(parseInt(e.data))) {{ appendLog('התקדמות: ' + e.data + '%'); }}
    }};
    es.onerror = function() {{ es.close(); appendLog('✗ החיבור נותק', 'err'); }};
  </script>
</body>
</html>"""
```

- [ ] **Step 3: Add the page route and regen SSE route**

Add near the other page routes (e.g. right before the Spotify routes block):

```python
@app.route('/recurring')
def recurring_page():
    if os.path.exists(RECURRING_HTML):
        return send_file(RECURRING_HTML)
    return _not_generated_recurring_html()


@app.route('/api/recurring/regenerate')
def recurring_regenerate():
    import queue as _q
    from database import DataBase
    pq = _q.Queue()

    def _run():
        try:
            db = DataBase()
            db.ensure_recurring_tables()
            pq.put(10)

            from RecurringCharges import get_recurring_groups
            groups = get_recurring_groups(db)
            pq.put(60)

            html = _render_recurring_html(groups)
            os.makedirs(os.path.dirname(RECURRING_HTML), exist_ok=True)
            with open(RECURRING_HTML, 'w', encoding='utf-8') as f:
                f.write(html)
            pq.put(90)

            _save_manifest(RECURRING_HTML, {}, 0.0)
            pq.put('done')
        except Exception as exc:
            import traceback
            _log_error(exc, traceback.format_exc())
            pq.put(f'error:{exc}')

    threading.Thread(target=_run, daemon=True).start()

    def _generate():
        while True:
            val = pq.get()
            if val == 'done':
                yield 'data: 100\n\n'
                yield 'data: done\n\n'
                break
            elif isinstance(val, str) and val.startswith('error:'):
                yield f'data: {val}\n\n'
                break
            else:
                yield f'data: {val}\n\n'

    return Response(
        _generate(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )
```

Note: `_render_recurring_html(groups)` is implemented in Task 6 alongside the HTML template — this task will not fully run end-to-end until that function exists (expected; verified together at the end of Task 6).

- [ ] **Step 4: Add the action routes (dismiss/restore/merge/exclude/tag)**

```python
@app.route('/api/recurring/groups/<path:group_key>/dismiss', methods=['POST'])
def recurring_dismiss(group_key):
    from database import DataBase
    try:
        db = DataBase()
        db.ensure_recurring_tables()
        db.dismiss_recurring_group(group_key)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/recurring/groups/<path:group_key>/restore', methods=['POST'])
def recurring_restore(group_key):
    from database import DataBase
    try:
        db = DataBase()
        db.ensure_recurring_tables()
        db.restore_recurring_group(group_key)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/recurring/groups/merge', methods=['POST'])
def recurring_merge():
    from database import DataBase
    try:
        body = request.get_json(force=True) or {}
        secondary_key = (body.get('secondary_key') or '').strip()
        primary_key = (body.get('primary_key') or '').strip()
        if not secondary_key or not primary_key:
            return jsonify({'ok': False, 'error': 'missing keys'})
        db = DataBase()
        db.ensure_recurring_tables()
        db.add_recurring_merge(secondary_key, primary_key)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/recurring/groups/<path:group_key>/exclude-tx', methods=['POST'])
def recurring_exclude_tx(group_key):
    from database import DataBase
    try:
        body = request.get_json(force=True) or {}
        table = (body.get('table') or '').strip()
        tx_id = body.get('tx_id')
        if table not in ('BankTransactions', 'CardTransactions') or tx_id is None:
            return jsonify({'ok': False, 'error': 'invalid table/tx_id'})
        db = DataBase()
        db.ensure_recurring_tables()
        db.exclude_recurring_tx(table, int(tx_id))
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/recurring/groups/<path:group_key>/tag', methods=['POST'])
def recurring_tag(group_key):
    from database import DataBase
    try:
        body = request.get_json(force=True) or {}
        category = (body.get('category') or '').strip()
        if not category:
            return jsonify({'ok': False, 'error': 'missing category'})
        db = DataBase()
        db.ensure_recurring_tables()
        from RecurringCharges import get_recurring_groups
        groups = get_recurring_groups(db)
        match = next((g for g in groups if g['group_key'] == group_key), None)
        if not match:
            return jsonify({'ok': False, 'error': 'group not found — try regenerating first'})
        count = 0
        for occ in match['occurrences']:
            db.set_category_ui(occ['table'], occ['id'], category, is_auto=False)
            count += 1
        return jsonify({'ok': True, 'tagged': count})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})
```

- [ ] **Step 5: Manually smoke-test the routes with the dev server**

Run: `python -c "from source.WebApp import start; start(port=5050, open_browser=False)"` (or use the existing `BankDash` launch config)
Then: `curl -s -X POST http://localhost:5050/api/recurring/groups/nonexistent/dismiss` — Expected: `{"ok": true}` (dismissing a key that doesn't correspond to any live group is harmless — it just sits in the override table unused)
Then: `curl -s http://localhost:5050/recurring` — Expected: HTML response (either the not-generated screen, since `_render_recurring_html` doesn't exist until Task 6, or a 500 if the regen route is hit — acceptable at this stage; full smoke test happens at the end of Task 6)

- [ ] **Step 6: Commit**

```bash
git add source/WebApp.py VERSION
git commit -m "feat(recurring): add page route, regen SSE, and action endpoints"
```

---

### Task 6: Frontend page — HTML/CSS/JS + server-side render function

**Files:**
- Create: `source/html/RecurringCharges.html`
- Modify: `source/WebApp.py` (add `_render_recurring_html`)

- [ ] **Step 1: Build `source/html/RecurringCharges.html`**

Base the skeleton (sidebar nav, hamburger menu, version badge, design tokens, RTL setup) directly on `source/html/SpotifyTracker.html` lines 1-40 (CSS variables) and lines 296-333 (sidebar markup) — copy those blocks verbatim, changing only the page title and the `active` class to sit on the new `/recurring` nav-item. Then add the page-specific content:

```html
<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>חיובים חוזרים</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root {
  --teal:#1e9d8b; --teal-light:#e8f7f5; --teal-dark:#178878;
  --navy:#1e2a4a; --bg:#f4f6f9; --white:#fff;
  --border:#eef0f6; --text-sub:#555; --text-muted:#888;
  --red:#e74c3c; --green:#2ecc71; --amber:#f39c12;
  --shadow-sm:0 2px 10px rgba(0,0,0,.06);
  --radius:14px; --radius-sm:8px;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',Arial,sans-serif;background:var(--bg);display:flex;min-height:100vh;direction:rtl;color:var(--navy);font-size:14px}
.main{margin-right:0;flex:1;padding:0 28px 90px;min-width:0}
.page-header{display:flex;align-items:center;margin-bottom:24px;padding-top:26px;gap:12px;padding-right:62px}
.page-header h1{font-size:1.85em;font-weight:700;color:var(--navy)}

/* KPI row */
.kpi-row{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:20px}
.kpi-card{background:var(--white);border-radius:var(--radius);box-shadow:var(--shadow-sm);padding:16px 20px;flex:1;min-width:160px}
.kpi-label{font-size:.78em;color:var(--text-muted);margin-bottom:6px}
.kpi-value{font-size:1.5em;font-weight:700;color:var(--navy);direction:ltr;text-align:right}

/* Attention section */
.attn-card{background:#fff8ed;border:1px solid #fde3b0;border-radius:var(--radius);padding:14px 18px;margin-bottom:20px}
.attn-title{font-size:.85em;font-weight:700;color:#a86a00;margin-bottom:8px}
.attn-item{font-size:.85em;color:#7a5200;padding:4px 0;cursor:pointer}
.attn-item:hover{text-decoration:underline}

/* Trend chart */
.trend-card{background:var(--white);border-radius:var(--radius);box-shadow:var(--shadow-sm);padding:18px 22px;margin-bottom:20px}
.trend-card h3{font-size:.95em;font-weight:700;margin-bottom:12px}
.trend-chart-wrap{position:relative;height:220px;overflow-x:auto}

/* Search/sort bar */
.rc-toolbar{display:flex;gap:10px;margin-bottom:14px;flex-wrap:wrap}
.rc-search{flex:1;min-width:180px;padding:10px 14px;border:1.5px solid var(--border);border-radius:var(--radius-sm);font-size:.9em;font-family:inherit;direction:rtl}
.rc-sort{padding:10px 14px;border:1.5px solid var(--border);border-radius:var(--radius-sm);font-size:.85em;font-family:inherit;background:var(--white)}

/* Group cards */
.rc-cards{display:flex;flex-direction:column;gap:10px}
.rc-card{background:var(--white);border-radius:var(--radius);box-shadow:var(--shadow-sm);padding:16px 20px}
.rc-card-top{display:flex;flex-wrap:wrap;align-items:center;gap:10px;cursor:pointer}
.rc-card-name{font-weight:700;flex:1;min-width:0}
.rc-card-cat{background:var(--teal-light);color:var(--teal);border-radius:12px;padding:2px 10px;font-size:.75em;font-weight:600;white-space:nowrap}
.rc-card-amount{font-weight:700;font-size:1.1em;direction:ltr;white-space:nowrap}
.rc-status{font-size:.72em;font-weight:700;border-radius:12px;padding:2px 10px;white-space:nowrap}
.rc-status.active{background:#e8f7f5;color:var(--teal)}
.rc-status.changed{background:#fff3e0;color:var(--amber)}
.rc-status.stopped{background:#fdecea;color:var(--red)}
.rc-next{font-size:.75em;color:var(--text-muted);white-space:nowrap}

/* Timeline strip — kept LTR regardless of page RTL */
.rc-timeline{display:flex;gap:3px;direction:ltr;overflow-x:auto;padding:10px 0}
.rc-tl-seg{width:22px;height:22px;border-radius:5px;flex-shrink:0}
.rc-tl-seg.paid{background:var(--green)}
.rc-tl-seg.changed{background:var(--amber)}
.rc-tl-seg.missing{background:var(--red)}
.rc-tl-seg.before_start{background:var(--border)}

/* Expanded detail */
.rc-detail{display:none;margin-top:14px;padding-top:14px;border-top:1px solid var(--border)}
.rc-detail.open{display:block}
.rc-stats-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:14px}
.rc-stat{background:var(--bg);border-radius:var(--radius-sm);padding:10px 12px}
.rc-stat-label{font-size:.7em;color:var(--text-muted)}
.rc-stat-value{font-size:1em;font-weight:700;direction:ltr;text-align:right}
.rc-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.rc-btn{padding:7px 16px;border-radius:var(--radius-sm);border:1.5px solid var(--border);background:var(--white);font-size:.82em;cursor:pointer;font-family:inherit}
.rc-btn:hover{background:var(--teal-light);border-color:var(--teal);color:var(--teal)}
.rc-btn.danger:hover{background:#fdecea;border-color:var(--red);color:var(--red)}

/* Hidden groups toggle */
.rc-hidden-toggle{font-size:.82em;color:var(--text-muted);cursor:pointer;margin-top:12px;text-align:center}
.rc-hidden-toggle:hover{color:var(--teal)}

/* Regen button — mirrors Organizer's org-regen-btn exactly */
.rc-regen-fab{position:fixed;bottom:22px;right:18px;z-index:500}
.rc-regen-btn{height:52px;padding:0 22px;background:var(--teal);color:#fff;border:none;border-radius:26px;font-size:.85em;font-weight:700;cursor:pointer;display:flex;align-items:center;gap:8px;box-shadow:0 4px 18px rgba(30,157,139,.45);white-space:nowrap;transition:box-shadow .2s,opacity .2s}
.rc-regen-btn:hover{box-shadow:0 6px 24px rgba(30,157,139,.65)}
.rc-regen-btn:disabled{opacity:.65;cursor:wait}
.rc-regen-icon{font-size:1.6em;line-height:1;display:flex;align-items:center}
.rc-regen-btn.running .rc-regen-icon{display:none}
.rc-regen-pct{font-size:.65em;font-weight:700;color:rgba(255,255,255,.9);display:none;line-height:1;margin-top:2px}
.rc-regen-btn.running .rc-regen-pct{display:block}

@media(max-width:768px){
  .rc-regen-fab{bottom:14px;right:14px}
  .rc-regen-btn{width:52px;padding:0;border-radius:50%;justify-content:center}
  .rc-regen-label{display:none}
}
@media(max-width:600px){
  .main{padding:0 12px 90px !important}
  .page-header{padding-top:72px;padding-right:0 !important}
  .kpi-row{flex-direction:column}
  .rc-stats-grid{grid-template-columns:1fr 1fr}
  .rc-card-top{flex-wrap:wrap}
  .rc-card-amount{order:1}
  .trend-chart-wrap{overflow-x:auto}
}
</style>
<link rel="stylesheet" href="/design-system.css">
</head>
<body>
<!-- Sidebar / hamburger nav: copy verbatim from source/html/SpotifyTracker.html lines 298-332,
     with the /recurring link carrying class="nav-item active" instead of /spotify's -->

<div class="main">
  <div class="page-header"><h1>חיובים חוזרים</h1></div>

  <div class="kpi-row">
    <div class="kpi-card"><div class="kpi-label">סה"כ חיוב חודשי חוזר</div><div class="kpi-value" id="kpi-total">—</div></div>
    <div class="kpi-card"><div class="kpi-label">חיובים חוזרים פעילים</div><div class="kpi-value" id="kpi-count">—</div></div>
    <div class="kpi-card"><div class="kpi-label">טעונים תשומת לב</div><div class="kpi-value" id="kpi-attn">—</div></div>
  </div>

  <div class="attn-card" id="attn-card" style="display:none">
    <div class="attn-title">⚠ טעונים תשומת לב</div>
    <div id="attn-list"></div>
  </div>

  <div class="trend-card">
    <h3>מגמת חיובים חוזרים — 12 חודשים אחרונים</h3>
    <div class="trend-chart-wrap"><canvas id="trend-chart"></canvas></div>
  </div>

  <div class="rc-toolbar">
    <input class="rc-search" id="rc-search" type="text" placeholder="חיפוש לפי שם…" oninput="renderCards()"/>
    <select class="rc-sort" id="rc-sort" onchange="renderCards()">
      <option value="amount-desc">סכום (גבוה לנמוך)</option>
      <option value="amount-asc">סכום (נמוך לגבוה)</option>
      <option value="name">שם</option>
      <option value="status">סטטוס</option>
    </select>
  </div>

  <div class="rc-cards" id="rc-cards"></div>
  <div class="rc-hidden-toggle" id="rc-hidden-toggle" onclick="toggleHiddenGroups()">קבוצות מוסתרות (<span id="rc-hidden-count">0</span>)</div>
  <div class="rc-cards" id="rc-hidden-cards" style="display:none;margin-top:10px"></div>
</div>

<div class="rc-regen-fab">
  <button class="rc-regen-btn" id="regen-btn" onclick="regenerate()" title="חשב מחדש">
    <span class="rc-regen-icon">&#8635;</span>
    <span class="rc-regen-label">חשב מחדש</span>
    <span class="rc-regen-pct" id="regen-pct"></span>
  </button>
</div>

<script>
var RC_DATA = __RC_DATA_JSON__;   // replaced server-side at generation time
var state = { groups: RC_DATA.groups, hidden: RC_DATA.hidden_groups, kpis: RC_DATA.kpis, trend: RC_DATA.trend };

function fmt(n) {
  var isPos = n >= 0;
  return (isPos?'+':'') + Math.abs(n).toLocaleString('he-IL',{minimumFractionDigits:2,maximumFractionDigits:2}) + '₪';
}
function esc(s){ if(!s) return ''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

function statusOf(g) {
  if (g.possibly_stopped) return 'stopped';
  if (g.amount_changed) return 'changed';
  return 'active';
}
function statusLabel(s) {
  return s === 'stopped' ? 'נראה שהופסק' : (s === 'changed' ? 'הסכום השתנה' : 'פעיל');
}

function renderKpis() {
  document.getElementById('kpi-total').textContent = fmt(state.kpis.total_monthly);
  document.getElementById('kpi-count').textContent = state.groups.length;
  var attnCount = state.groups.filter(function(g){ return g.possibly_stopped || g.amount_changed; }).length;
  document.getElementById('kpi-attn').textContent = attnCount;

  var attnCard = document.getElementById('attn-card');
  var attnList = document.getElementById('attn-list');
  var flagged = state.groups.filter(function(g){ return g.possibly_stopped || g.amount_changed; });
  if (flagged.length) {
    attnCard.style.display = '';
    attnList.innerHTML = flagged.map(function(g) {
      return '<div class="attn-item" onclick="scrollToGroup(\'' + g.group_key + '\')">' +
             esc(g.name) + ' — ' + (g.possibly_stopped ? 'נראה שהופסק' : 'הסכום השתנה') + '</div>';
    }).join('');
  } else {
    attnCard.style.display = 'none';
  }
}

function scrollToGroup(key) {
  var el = document.getElementById('card-' + key);
  if (el) { el.scrollIntoView({behavior:'smooth', block:'center'}); toggleDetail(key, true); }
}

function renderTimeline(timeline) {
  return '<div class="rc-timeline">' + timeline.map(function(t) {
    return '<div class="rc-tl-seg ' + t.status + '" title="' + t.month + '"></div>';
  }).join('') + '</div>';
}

function toggleDetail(key, forceOpen) {
  var el = document.getElementById('detail-' + key);
  if (!el) return;
  if (forceOpen) el.classList.add('open');
  else el.classList.toggle('open');
}

function getSortedFilteredGroups() {
  var q = document.getElementById('rc-search').value.trim().toLowerCase();
  var sort = document.getElementById('rc-sort').value;
  var list = state.groups.filter(function(g) { return !q || g.name.toLowerCase().indexOf(q) !== -1; });
  if (sort === 'amount-desc') list.sort(function(a,b){ return b.current_amount - a.current_amount; });
  else if (sort === 'amount-asc') list.sort(function(a,b){ return a.current_amount - b.current_amount; });
  else if (sort === 'name') list.sort(function(a,b){ return a.name.localeCompare(b.name); });
  else if (sort === 'status') list.sort(function(a,b){ return (b.possibly_stopped||b.amount_changed?1:0) - (a.possibly_stopped||a.amount_changed?1:0); });
  return list;
}

function cardHtml(g) {
  var status = statusOf(g);
  var occRows = g.occurrences.map(function(o) {
    return '<div style="display:flex;justify-content:space-between;font-size:.82em;padding:4px 0;border-bottom:1px solid var(--border)">' +
      '<span>' + o.month + '</span><span style="direction:ltr">' + fmt(o.amount) + '</span>' +
      '<button class="rc-btn danger" style="padding:2px 8px" onclick="excludeTx(\'' + g.group_key + '\',\'' + o.table + '\',' + o.id + ')">✕ הסר</button>' +
    '</div>';
  }).join('');
  return '<div class="rc-card" id="card-' + g.group_key + '">' +
    '<div class="rc-card-top" onclick="toggleDetail(\'' + g.group_key + '\')">' +
      '<span class="rc-card-name">' + esc(g.name) + '</span>' +
      '<span class="rc-card-cat">' + esc(g.category) + '</span>' +
      '<span class="rc-status ' + status + '">' + statusLabel(status) + '</span>' +
      '<span class="rc-next">הבא: ' + g.next_expected + '</span>' +
      '<span class="rc-card-amount">' + fmt(g.current_amount) + '</span>' +
    '</div>' +
    renderTimeline(g.timeline) +
    '<div class="rc-detail" id="detail-' + g.group_key + '">' +
      '<div class="rc-stats-grid">' +
        '<div class="rc-stat"><div class="rc-stat-label">ממוצע</div><div class="rc-stat-value">' + fmt(g.average_amount) + '</div></div>' +
        '<div class="rc-stat"><div class="rc-stat-label">סה"כ שולם</div><div class="rc-stat-value">' + fmt(g.total_spent) + '</div></div>' +
        '<div class="rc-stat"><div class="rc-stat-label">מס\' תשלומים</div><div class="rc-stat-value">' + g.occurrence_count + '</div></div>' +
        '<div class="rc-stat"><div class="rc-stat-label">תשלום ראשון</div><div class="rc-stat-value">' + g.first_payment_date + '</div></div>' +
        '<div class="rc-stat"><div class="rc-stat-label">תשלום אחרון</div><div class="rc-stat-value">' + g.last_payment_date + '</div></div>' +
        '<div class="rc-stat"><div class="rc-stat-label">טווח</div><div class="rc-stat-value">' + fmt(g.min_amount) + ' – ' + fmt(g.max_amount) + '</div></div>' +
      '</div>' +
      occRows +
      '<div class="rc-actions">' +
        '<button class="rc-btn" onclick="openTagPrompt(\'' + g.group_key + '\')">תייג קטגוריה…</button>' +
        '<button class="rc-btn" onclick="openMergePrompt(\'' + g.group_key + '\')">מזג עם…</button>' +
        '<button class="rc-btn danger" onclick="dismissGroup(\'' + g.group_key + '\')">התעלם</button>' +
      '</div>' +
    '</div>' +
  '</div>';
}

function renderCards() {
  var list = getSortedFilteredGroups();
  document.getElementById('rc-cards').innerHTML = list.map(cardHtml).join('') ||
    '<div class="rc-card" style="text-align:center;color:var(--text-muted)">לא נמצאו חיובים חוזרים</div>';
  document.getElementById('rc-hidden-count').textContent = state.hidden.length;
  document.getElementById('rc-hidden-cards').innerHTML = state.hidden.map(function(g) {
    return '<div class="rc-card"><div class="rc-card-top">' +
      '<span class="rc-card-name">' + esc(g.name) + '</span>' +
      '<button class="rc-btn" onclick="restoreGroup(\'' + g.group_key + '\')">שחזר</button>' +
    '</div></div>';
  }).join('');
}

function toggleHiddenGroups() {
  var el = document.getElementById('rc-hidden-cards');
  el.style.display = el.style.display === 'none' ? '' : 'none';
}

function renderTrendChart() {
  var ctx = document.getElementById('trend-chart');
  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: state.trend.map(function(t){ return t.month; }),
      datasets: [{ label: 'סה"כ חיובים חוזרים', data: state.trend.map(function(t){ return t.total; }),
                   backgroundColor: '#1e9d8b' }]
    },
    options: { responsive: true, maintainAspectRatio: false, scales: { x: { reverse: true } } }
  });
}

// ── Actions ──
function dismissGroup(key) {
  fetch('/api/recurring/groups/' + encodeURIComponent(key) + '/dismiss', {method:'POST'})
    .then(function(r){return r.json();}).then(function(){ regenerate(); });
}
function restoreGroup(key) {
  fetch('/api/recurring/groups/' + encodeURIComponent(key) + '/restore', {method:'POST'})
    .then(function(r){return r.json();}).then(function(){ regenerate(); });
}
function excludeTx(key, table, txId) {
  fetch('/api/recurring/groups/' + encodeURIComponent(key) + '/exclude-tx', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({table:table, tx_id:txId})
  }).then(function(r){return r.json();}).then(function(){ regenerate(); });
}
function openTagPrompt(key) {
  var cat = prompt('קטגוריה לתיוג:');
  if (!cat) return;
  fetch('/api/recurring/groups/' + encodeURIComponent(key) + '/tag', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({category:cat})
  }).then(function(r){return r.json();}).then(function(res){
    if (res.ok) alert('תויגו ' + res.tagged + ' עסקאות'); else alert('שגיאה: ' + res.error);
  });
}
function openMergePrompt(key) {
  var target = prompt('מפתח הקבוצה למיזוג לתוכה:');
  if (!target) return;
  fetch('/api/recurring/groups/merge', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({secondary_key:key, primary_key:target})
  }).then(function(r){return r.json();}).then(function(){ regenerate(); });
}

function regenerate() {
  var btn = document.getElementById('regen-btn');
  var pct = document.getElementById('regen-pct');
  btn.disabled = true; btn.classList.add('running'); pct.textContent = '0%';
  var es = new EventSource('/api/recurring/regenerate');
  es.onmessage = function(e) {
    if (e.data === 'done') { es.close(); location.reload(); }
    else if (e.data.indexOf('error') === 0) { es.close(); location.reload(); }
    else { var p = parseInt(e.data); if (!isNaN(p)) pct.textContent = p + '%'; }
  };
  es.onerror = function() { es.close(); location.reload(); };
}

fetch('/api/version').then(function(r){return r.json();}).then(function(d){
  var b = document.getElementById('app-version-badge-2'); if (b && d.version) b.textContent = 'v' + d.version;
}).catch(function(){});

renderKpis();
renderCards();
renderTrendChart();
</script>
</body>
</html>
```

- [ ] **Step 2: Copy the sidebar block verbatim into the HTML comment placeholder**

Replace the `<!-- Sidebar / hamburger nav: ... -->` comment with the exact markup copied from `source/html/SpotifyTracker.html` lines 298-332 (hamburger button, nav-overlay, sidebar nav with all `nav-item` links, sidebar-footer with restart button + version badge), changing:
- The `/recurring` link gets `class="nav-item active"` (added in Task 7 to all other files' sidebars as a plain, non-active link)
- Keep `id="app-version-badge-2"` as-is (matches the JS at the bottom of the page already referencing that id)

- [ ] **Step 3: Add `_render_recurring_html(groups)` to `source/WebApp.py`**

Add this function near `_save_manifest` (e.g. directly after it):

```python
def _render_recurring_html(groups: list) -> str:
    """Serialize computed groups into the RecurringCharges.html template."""
    import json as _json_mod
    from datetime import date as _d

    def _default(o):
        if isinstance(o, _d):
            return o.isoformat()
        raise TypeError(f'not JSON serializable: {o!r}')

    total_monthly = sum(g['current_amount'] for g in groups)

    from database import DataBase
    db = DataBase()
    db.ensure_recurring_tables()
    dismissed_keys = db.get_recurring_dismissed()

    # Re-fetch dismissed groups' display info: since they're excluded from
    # get_recurring_groups(), recompute the full candidate set without the
    # dismissed-filter to list them for the "hidden groups" restore UI.
    from RecurringCharges import (
        fetch_candidate_transactions, cluster_transactions, build_group_from_cluster
    )
    all_transactions = fetch_candidate_transactions(db)
    all_clusters = cluster_transactions(all_transactions)
    hidden_groups = []
    for c in all_clusters:
        if c['norm_key'] not in dismissed_keys:
            continue
        g = build_group_from_cluster(c, today=_d.today())
        if g:
            hidden_groups.append({'group_key': g['group_key'], 'name': g['name']})

    # 12-month trend: total recurring spend per month across all active groups
    trend_totals = {}
    for g in groups:
        for occ in g['occurrences']:
            trend_totals[occ['month']] = trend_totals.get(occ['month'], 0) + occ['amount']
    trend_months = sorted(trend_totals.keys())[-12:]
    trend = [{'month': m, 'total': round(trend_totals[m], 2)} for m in trend_months]

    data = {
        'groups': groups,
        'hidden_groups': hidden_groups,
        'kpis': {'total_monthly': round(total_monthly, 2)},
        'trend': trend,
    }
    data_json = _json_mod.dumps(data, default=_default, ensure_ascii=False)

    html_path = os.path.join(_HERE, 'html', 'RecurringCharges.html')
    with open(html_path, encoding='utf-8') as f:
        template = f.read()
    return template.replace('__RC_DATA_JSON__', data_json)
```

- [ ] **Step 4: Run the algorithm test suite once more to confirm nothing broke**

Run: `cd source && python Testing/test_recurring_charges.py`
Expected: `All tests passed`

- [ ] **Step 5: Commit**

```bash
git add source/html/RecurringCharges.html source/WebApp.py VERSION
git commit -m "feat(recurring): add RecurringCharges.html page and server-side render"
```

---

### Task 7: Sidebar nav — add the link to all 7 files

**Files:**
- Modify: `source/html/Search.html`
- Modify: `source/html/SpotifyTracker.html`
- Modify: `source/html/Tagger.html`
- Modify: `source/html/Bills.html`
- Modify: `source/html/Base_template.html`
- Modify: `source/html/Files.html`
- Modify: `source/html/Organizer_Table.html`

- [ ] **Step 1: In each of the 7 files, find the sidebar's nav-item list and add the new link**

In every file, find this line (present verbatim in each, per the research):
```html
    <a class="nav-item" href="/spotify">Spotify Tracker</a>
```
Add directly after it:
```html
    <a class="nav-item" href="/recurring">חיובים חוזרים</a>
```
(In `SpotifyTracker.html` this line currently reads `class="nav-item active" href="/spotify"` — add the new link after it unchanged, i.e. `class="nav-item"` not `active`, since Spotify Tracker remains that file's active page.)

- [ ] **Step 2: Verify each file still has valid, matching HTML structure**

Run: `for f in source/html/Search.html source/html/SpotifyTracker.html source/html/Tagger.html source/html/Bills.html source/html/Base_template.html source/html/Files.html source/html/Organizer_Table.html; do grep -c 'href="/recurring"' "$f"; done`
Expected: `1` printed 7 times (one match per file)

- [ ] **Step 3: Commit**

```bash
git add source/html/Search.html source/html/SpotifyTracker.html source/html/Tagger.html source/html/Bills.html source/html/Base_template.html source/html/Files.html source/html/Organizer_Table.html VERSION
git commit -m "feat(recurring): add sidebar nav link to all pages"
```

---

### Task 8: Version bump convention (applies retroactively to every task above)

**Files:**
- Modify: `VERSION`

- [ ] **Step 1: Confirm the standing rule is followed**

Before every commit in Tasks 1-7, bump `VERSION`'s patch digit by 1 (e.g. `1.12.6` → `1.12.7` → `1.12.8` ...). This step exists as an explicit checklist item because the per-task commit commands above all include `VERSION` in `git add` — the bump itself must happen as a small edit immediately before each commit.

- [ ] **Step 2: Verify final version after all tasks**

Run: `cat VERSION`
Expected: patch version has incremented by exactly the number of commits made across Tasks 1-7 (7 commits → 7 patch bumps from the value at plan start).

---

### Task 9: End-to-end QA in the browser (desktop + mobile)

**Files:** none (verification only)

- [ ] **Step 1: Start the dev server and load `/recurring` fresh (no cached file)**

Delete any stale cached file first: `rm -f Outputs/recurring_charges.html Outputs/recurring_charges.manifest.json`
Start server, navigate to `http://localhost:5050/recurring`.
Expected: the shared regen screen appears (green/white card, floating log panel), progress advances, then auto-reloads into the real page.

- [ ] **Step 2: Verify KPIs, attention section, trend chart, and cards render with real data**

Read the page, confirm: KPI values are non-placeholder numbers, at least one recurring group card renders (if the real DB has ≥3-month recurring charges — likely true given `Outputs/category_analysis/cat_מנויים.html` exists), timeline strips show 12 colored segments in LTR order.

- [ ] **Step 3: Test dismiss, restore, merge, exclude-tx, and tag actions live**

Click dismiss on one group → confirm it disappears and shows under "קבוצות מוסתרות"; click restore → confirm it reappears after the auto-regen. Test tag and merge similarly. Test excluding one transaction from a group's history and confirm the group's stats update after regen.

- [ ] **Step 4: Resize to mobile (375px) and re-check every element**

Confirm: KPI row stacks, cards remain full-width with no overlap, timeline strip is scrollable/legible, trend chart doesn't overflow the viewport horizontally, regen button collapses to a circle in the bottom corner.

- [ ] **Step 5: Clean up any test data created during manual QA**

If any manual dismiss/merge/exclude/tag actions were tested against **real** transactions (not the `RC_TEST_`/2099-dated rows from the automated tests, which self-clean), reverse them: restore any dismissed real group, delete any `RecurringMerges` rows created during manual testing, delete any `RecurringExcludedTransactions` rows created during manual testing, and if any real transaction got tagged with a test category via the tag action, confirm its `Category` is reverted to what it was before (check via `git diff`-style before/after, or better — only exercise the tag/merge/exclude/dismiss actions against the same `RC_TEST_STREAMING_SVC` synthetic data used in Task 4's automated test, inserted temporarily and deleted after, rather than real data, to avoid needing any manual cleanup at all).

- [ ] **Step 6: Final full test suite + version confirmation**

Run: `cd source && python Testing/test_recurring_charges.py` — Expected: `All tests passed`
Run: `cat ../VERSION` — confirm it reflects all commits made.
