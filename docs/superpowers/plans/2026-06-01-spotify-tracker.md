# Spotify Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Spotify Family Plan Tracker page to the BankProject Flask app that tracks monthly charges, family member reimbursements, running balances, and exports PDF reports.

**Architecture:** New self-contained HTML page (`SpotifyTracker.html`) served at `/spotify`, backed by Flask API routes in `WebApp.py`, business logic in a new `SpotifyTracker.py` module, and three new SQLite tables in the existing `ShmuelFamiliy.db`. Balance is always computed on the fly from charge snapshots and member payment records.

**Tech Stack:** Flask, SQLite (existing), reportlab (PDF), python-bidi (Hebrew RTL in PDF), vanilla JS (frontend), same CSS design tokens as Bills.html.

**Spec:** `docs/superpowers/specs/2026-06-01-spotify-tracker-design.md`

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Modify | `requirements.txt` | Add reportlab + python-bidi |
| Modify | `source/database.py:197-201` | Add 3 Spotify tables in `__new__` |
| Modify | `source/database.py:2669` | Add Spotify CRUD methods |
| Create | `source/SpotifyTracker.py` | Balance calculation + charge suggestions + unmatched txs + PDF generation |
| Modify | `source/WebApp.py:2992` | Add `/spotify` route + all `/api/spotify/*` routes (before `start()`) |
| Create | `source/html/SpotifyTracker.html` | Full RTL frontend page |
| Modify | `source/html/output.html:1549` | Add sidebar nav entry |
| Modify | `source/html/Bills.html:686` | Add sidebar nav entry |
| Modify | `source/html/Search.html:272` | Add sidebar nav entry |
| Modify | `source/html/Tagger.html:698` | Add sidebar nav entry |
| Modify | `source/html/Files.html:569` | Add sidebar nav entry |
| Create | `source/Testing/test_spotify_tracker.py` | Integration tests for balance logic |

---

## Task 1: Add Dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add reportlab and python-bidi to requirements.txt**

Open `requirements.txt` and append:
```
reportlab==4.2.0
python-bidi==0.4.2
```

- [ ] **Step 2: Install the new packages**

```bash
pip install reportlab==4.2.0 python-bidi==0.4.2
```

Expected: both packages install without errors.

- [ ] **Step 3: Verify import works**

```bash
python -c "import reportlab; from bidi.algorithm import get_display; print('ok')"
```

Expected output: `ok`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore: add reportlab and python-bidi for Spotify Tracker PDF export"
```

---

## Task 2: Add Spotify DB Tables

**Files:**
- Modify: `source/database.py:197-201`

- [ ] **Step 1: Write the failing test**

Create `source/Testing/test_spotify_tracker.py` with just the table-existence check:

```python
"""Integration tests for Spotify Tracker feature."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import DataBase

def test_spotify_tables_exist():
    db = DataBase()
    tables = {r[0] for r in db.cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert 'SpotifyMembers' in tables, "SpotifyMembers table missing"
    assert 'SpotifyMonthlyCharge' in tables, "SpotifyMonthlyCharge table missing"
    assert 'SpotifyMemberPayments' in tables, "SpotifyMemberPayments table missing"

if __name__ == '__main__':
    test_spotify_tables_exist()
    print("PASS: all Spotify tables exist")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd source && python Testing/test_spotify_tracker.py
```

Expected: `AssertionError: SpotifyMembers table missing`

- [ ] **Step 3: Add the three tables to database.py**

In `source/database.py`, find the block ending at line 200 (the `BillSuggestionsDismissed` CREATE TABLE). Insert the three new tables **after** that block and **before** the `return cls.__instance` line (line 202).

Find this exact string:
```python
                cls.__instance.cursor.execute("""
                    CREATE TABLE IF NOT EXISTS BillSuggestionsDismissed (
                    ID                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    Transaction_Name    TEXT    NOT NULL UNIQUE,
                    Dismissed_At        TEXT    DEFAULT (datetime('now'))
                    );""")

        return cls.__instance
```

Replace with:
```python
                cls.__instance.cursor.execute("""
                    CREATE TABLE IF NOT EXISTS BillSuggestionsDismissed (
                    ID                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    Transaction_Name    TEXT    NOT NULL UNIQUE,
                    Dismissed_At        TEXT    DEFAULT (datetime('now'))
                    );""")

                cls.__instance.cursor.execute("""
                    CREATE TABLE IF NOT EXISTS SpotifyMembers (
                    ID          INTEGER PRIMARY KEY AUTOINCREMENT,
                    Name        TEXT    NOT NULL,
                    Is_Exempt   INTEGER NOT NULL DEFAULT 0,
                    Is_Active   INTEGER NOT NULL DEFAULT 1,
                    Created_At  TEXT    DEFAULT (datetime('now'))
                    );""")

                cls.__instance.cursor.execute("""
                    CREATE TABLE IF NOT EXISTS SpotifyMonthlyCharge (
                    ID           INTEGER PRIMARY KEY AUTOINCREMENT,
                    Month        TEXT    NOT NULL UNIQUE,
                    Total_Amount REAL    NOT NULL,
                    Member_Count INTEGER NOT NULL,
                    TX_ID        INTEGER,
                    Confirmed    INTEGER NOT NULL DEFAULT 0,
                    Created_At   TEXT    DEFAULT (datetime('now'))
                    );""")

                cls.__instance.cursor.execute("""
                    CREATE TABLE IF NOT EXISTS SpotifyMemberPayments (
                    ID           INTEGER PRIMARY KEY AUTOINCREMENT,
                    Member_ID    INTEGER NOT NULL,
                    Amount       REAL    NOT NULL,
                    Payment_Date TEXT    NOT NULL,
                    TX_ID        INTEGER,
                    Note         TEXT,
                    Created_At   TEXT    DEFAULT (datetime('now')),
                    FOREIGN KEY(Member_ID) REFERENCES SpotifyMembers(ID)
                    );""")

        return cls.__instance
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd source && python Testing/test_spotify_tracker.py
```

Expected: `PASS: all Spotify tables exist`

- [ ] **Step 5: Commit**

```bash
git add source/database.py source/Testing/test_spotify_tracker.py
git commit -m "feat(spotify): add SpotifyMembers, SpotifyMonthlyCharge, SpotifyMemberPayments tables"
```

---

## Task 3: Add Spotify DB Methods

**Files:**
- Modify: `source/database.py` (append after line 2668)
- Modify: `source/Testing/test_spotify_tracker.py`

- [ ] **Step 1: Write failing tests for DB methods**

Add to `source/Testing/test_spotify_tracker.py`:

```python
def test_member_crud():
    db = DataBase()
    # Clean up from previous runs
    db.cursor.execute("DELETE FROM SpotifyMembers WHERE Name = 'TestMember'")
    db.commit_changes()

    mid = db.add_spotify_member('TestMember', is_exempt=0)
    assert isinstance(mid, int) and mid > 0

    members = db.get_spotify_members()
    names = [m['name'] for m in members]
    assert 'TestMember' in names

    db.update_spotify_member(mid, name='TestMemberRenamed', is_exempt=0, is_active=1)
    members = db.get_spotify_members()
    assert any(m['name'] == 'TestMemberRenamed' for m in members)

    db.delete_spotify_member(mid)
    members = db.get_spotify_members()
    assert not any(m['name'] == 'TestMemberRenamed' for m in members)
    print("PASS: member CRUD")


def test_charge_crud():
    db = DataBase()
    db.cursor.execute("DELETE FROM SpotifyMonthlyCharge WHERE Month = '2099-01'")
    db.commit_changes()

    cid = db.add_spotify_charge(month='2099-01', total_amount=149.90, member_count=5, tx_id=None, confirmed=1)
    assert isinstance(cid, int)

    charges = db.get_spotify_charges()
    assert any(c['month'] == '2099-01' for c in charges)

    db.update_spotify_charge(cid, total_amount=159.90, member_count=5, confirmed=1)
    charges = db.get_spotify_charges()
    updated = next(c for c in charges if c['month'] == '2099-01')
    assert updated['total_amount'] == 159.90

    db.cursor.execute("DELETE FROM SpotifyMonthlyCharge WHERE ID = ?", (cid,))
    db.commit_changes()
    print("PASS: charge CRUD")


def test_payment_crud():
    db = DataBase()
    mid = db.add_spotify_member('PayTestMember', is_exempt=0)

    pid = db.add_spotify_payment(member_id=mid, amount=29.98, payment_date='2099-01-15', tx_id=None)
    assert isinstance(pid, int)

    payments = db.get_spotify_payments(member_id=mid)
    assert len(payments) == 1
    assert payments[0]['amount'] == 29.98

    db.delete_spotify_payment(pid)
    payments = db.get_spotify_payments(member_id=mid)
    assert len(payments) == 0

    db.delete_spotify_member(mid)
    print("PASS: payment CRUD")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd source && python Testing/test_spotify_tracker.py
```

Expected: `AttributeError: 'DataBase' object has no attribute 'add_spotify_member'`

- [ ] **Step 3: Add DB methods to database.py**

Append the following after the last line of `source/database.py` (after line 2668):

```python
    # ── Spotify tracker ────────────────────────────────────────────────────────

    def get_spotify_members(self) -> list:
        rows = self.cursor.execute(
            "SELECT ID, Name, Is_Exempt, Is_Active FROM SpotifyMembers ORDER BY ID"
        ).fetchall()
        return [{'id': r[0], 'name': r[1], 'is_exempt': r[2], 'is_active': r[3]} for r in rows]

    def add_spotify_member(self, name: str, is_exempt: int = 0) -> int:
        self.cursor.execute(
            "INSERT INTO SpotifyMembers (Name, Is_Exempt) VALUES (?, ?)",
            (name.strip(), int(is_exempt))
        )
        self.commit_changes()
        return self.cursor.lastrowid

    def update_spotify_member(self, member_id: int, name: str, is_exempt: int, is_active: int):
        self.cursor.execute(
            "UPDATE SpotifyMembers SET Name=?, Is_Exempt=?, Is_Active=? WHERE ID=?",
            (name.strip(), int(is_exempt), int(is_active), member_id)
        )
        self.commit_changes()

    def delete_spotify_member(self, member_id: int):
        self.cursor.execute("DELETE FROM SpotifyMemberPayments WHERE Member_ID = ?", (member_id,))
        self.cursor.execute("DELETE FROM SpotifyMembers WHERE ID = ?", (member_id,))
        self.commit_changes()

    def get_spotify_charges(self) -> list:
        rows = self.cursor.execute(
            "SELECT ID, Month, Total_Amount, Member_Count, TX_ID, Confirmed FROM SpotifyMonthlyCharge ORDER BY Month DESC"
        ).fetchall()
        return [{'id': r[0], 'month': r[1], 'total_amount': r[2], 'member_count': r[3],
                 'tx_id': r[4], 'confirmed': r[5]} for r in rows]

    def add_spotify_charge(self, month: str, total_amount: float, member_count: int,
                           tx_id=None, confirmed: int = 0) -> int:
        self.cursor.execute(
            "INSERT INTO SpotifyMonthlyCharge (Month, Total_Amount, Member_Count, TX_ID, Confirmed) VALUES (?,?,?,?,?)",
            (month, float(total_amount), int(member_count), tx_id, int(confirmed))
        )
        self.commit_changes()
        return self.cursor.lastrowid

    def update_spotify_charge(self, charge_id: int, total_amount: float, member_count: int, confirmed: int):
        self.cursor.execute(
            "UPDATE SpotifyMonthlyCharge SET Total_Amount=?, Member_Count=?, Confirmed=? WHERE ID=?",
            (float(total_amount), int(member_count), int(confirmed), charge_id)
        )
        self.commit_changes()

    def get_spotify_payments(self, member_id: int = None) -> list:
        if member_id is not None:
            rows = self.cursor.execute(
                "SELECT ID, Member_ID, Amount, Payment_Date, TX_ID, Note FROM SpotifyMemberPayments WHERE Member_ID=? ORDER BY Payment_Date DESC",
                (member_id,)
            ).fetchall()
        else:
            rows = self.cursor.execute(
                "SELECT ID, Member_ID, Amount, Payment_Date, TX_ID, Note FROM SpotifyMemberPayments ORDER BY Payment_Date DESC"
            ).fetchall()
        return [{'id': r[0], 'member_id': r[1], 'amount': r[2], 'payment_date': r[3],
                 'tx_id': r[4], 'note': r[5]} for r in rows]

    def add_spotify_payment(self, member_id: int, amount: float, payment_date: str,
                            tx_id=None, note: str = None) -> int:
        self.cursor.execute(
            "INSERT INTO SpotifyMemberPayments (Member_ID, Amount, Payment_Date, TX_ID, Note) VALUES (?,?,?,?,?)",
            (int(member_id), float(amount), payment_date, tx_id, note)
        )
        self.commit_changes()
        return self.cursor.lastrowid

    def delete_spotify_payment(self, payment_id: int):
        self.cursor.execute("DELETE FROM SpotifyMemberPayments WHERE ID = ?", (payment_id,))
        self.commit_changes()

    def get_spotify_assigned_tx_ids(self) -> set:
        rows = self.cursor.execute(
            "SELECT TX_ID FROM SpotifyMemberPayments WHERE TX_ID IS NOT NULL"
        ).fetchall()
        return {r[0] for r in rows}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd source && python Testing/test_spotify_tracker.py
```

Expected:
```
PASS: all Spotify tables exist
PASS: member CRUD
PASS: charge CRUD
PASS: payment CRUD
```

- [ ] **Step 5: Commit**

```bash
git add source/database.py source/Testing/test_spotify_tracker.py
git commit -m "feat(spotify): add Spotify CRUD methods to DataBase"
```

---

## Task 4: Create SpotifyTracker.py (Business Logic + PDF)

**Files:**
- Create: `source/SpotifyTracker.py`
- Modify: `source/Testing/test_spotify_tracker.py`

- [ ] **Step 1: Write failing tests for balance logic**

Add to `source/Testing/test_spotify_tracker.py`:

```python
def test_compute_balance_owes():
    from SpotifyTracker import compute_balance
    charges = [
        {'month': '2025-04', 'total_amount': 120.0, 'member_count': 4, 'confirmed': 1},
        {'month': '2025-05', 'total_amount': 120.0, 'member_count': 4, 'confirmed': 1},
        {'month': '2025-06', 'total_amount': 120.0, 'member_count': 4, 'confirmed': 1},
    ]
    payments = [{'amount': 30.0}]  # paid only one month
    result = compute_balance(payments, charges)
    assert result['status'] == 'owes'
    assert result['balance'] == round(30.0 - 90.0, 2)  # -60.0
    assert result['months_status'] == -2  # ceil(60/30) = 2
    print("PASS: compute_balance owes")


def test_compute_balance_ahead():
    from SpotifyTracker import compute_balance
    charges = [
        {'month': '2025-06', 'total_amount': 120.0, 'member_count': 4, 'confirmed': 1},
    ]
    payments = [{'amount': 90.0}]  # paid 3x the monthly share
    result = compute_balance(payments, charges)
    assert result['status'] == 'ahead'
    assert result['balance'] == 60.0  # 90 - 30 = 60
    assert result['months_status'] == 2  # floor(60/30) = 2
    print("PASS: compute_balance ahead")


def test_compute_balance_even():
    from SpotifyTracker import compute_balance
    charges = [
        {'month': '2025-06', 'total_amount': 120.0, 'member_count': 4, 'confirmed': 1},
    ]
    payments = [{'amount': 30.0}]
    result = compute_balance(payments, charges)
    assert result['status'] == 'even'
    assert result['months_status'] == 0
    print("PASS: compute_balance even")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd source && python Testing/test_spotify_tracker.py
```

Expected: `ModuleNotFoundError: No module named 'SpotifyTracker'`

- [ ] **Step 3: Create source/SpotifyTracker.py**

```python
"""
Spotify Family Plan Tracker — business logic and PDF generation.
"""
import math
import io
import os
import sqlite3

# ── Balance calculation ────────────────────────────────────────────────────────

def compute_balance(member_payments: list, charges: list) -> dict:
    """
    Compute running balance for one paying member.

    member_payments: list of dicts with at least {'amount': float}
    charges:         list of dicts {month, total_amount, member_count, confirmed}

    Returns:
        balance:       float  (positive = credit, negative = owes)
        current_share: float  (latest confirmed month's per-person share)
        months_status: int    (positive = months ahead, negative = months owed, 0 = even)
        status:        'ahead' | 'even' | 'owes'
    """
    confirmed = [c for c in charges if c.get('confirmed')]
    total_debited = sum(c['total_amount'] / c['member_count'] for c in confirmed)
    total_credited = sum(float(p['amount']) for p in member_payments)
    balance = round(total_credited - total_debited, 2)

    current_share = 0.0
    if confirmed:
        latest = max(confirmed, key=lambda c: c['month'])
        current_share = round(latest['total_amount'] / latest['member_count'], 2)

    months_status = 0
    if current_share > 0:
        if balance < -0.01:
            months_status = -math.ceil(abs(balance) / current_share)
        elif balance > 0.01:
            months_status = math.floor(balance / current_share)

    if balance < -0.01:
        status = 'owes'
    elif balance > 0.01:
        status = 'ahead'
    else:
        status = 'even'

    return {
        'balance': balance,
        'current_share': current_share,
        'months_status': months_status,
        'status': status,
    }


def compute_all_balances(db) -> list:
    """
    Return balance summary for every paying member (is_exempt=0).
    db: DataBase instance
    """
    members  = db.get_spotify_members()
    charges  = db.get_spotify_charges()
    payments = db.get_spotify_payments()

    result = []
    for m in members:
        if m['is_exempt'] or not m['is_active']:
            continue
        m_payments = [p for p in payments if p['member_id'] == m['id']]
        bal = compute_balance(m_payments, charges)
        last_payment = max((p['payment_date'] for p in m_payments), default=None)
        result.append({
            'member_id':    m['id'],
            'name':         m['name'],
            'balance':      bal['balance'],
            'current_share': bal['current_share'],
            'months_status': bal['months_status'],
            'status':       bal['status'],
            'last_payment': last_payment,
            'payment_count': len(m_payments),
        })
    return result


# ── Transaction suggestions ────────────────────────────────────────────────────

def get_charge_suggestions(db_path: str) -> list:
    """
    Find outgoing BankTransactions whose Name contains 'spotify' (case-insensitive)
    that have no confirmed SpotifyMonthlyCharge for that month yet.
    Returns list of {tx_id, date, name, amount, month}.
    """
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        confirmed_months = {
            r[0] for r in conn.execute(
                "SELECT Month FROM SpotifyMonthlyCharge WHERE Confirmed = 1"
            ).fetchall()
        }
        rows = conn.execute("""
            SELECT ID, Date, Name, Out
            FROM BankTransactions
            WHERE LOWER(Name) LIKE '%spotify%' AND Out > 0
            ORDER BY Date DESC LIMIT 24
        """).fetchall()

        by_month = {}
        for row in rows:
            month = (row['Date'] or '')[:7]
            if not month or month in confirmed_months:
                continue
            candidate = {
                'tx_id':  row['ID'],
                'date':   row['Date'],
                'name':   row['Name'],
                'amount': float(row['Out'] or 0),
                'month':  month,
            }
            if month not in by_month or candidate['amount'] > by_month[month]['amount']:
                by_month[month] = candidate

        return sorted(by_month.values(), key=lambda x: x['month'], reverse=True)
    finally:
        conn.close()


def get_unmatched_payments(db_path: str) -> list:
    """
    Return Spotify-categorized transactions (bank + card, income side) that have
    not yet been assigned to any SpotifyMemberPayment.
    """
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        assigned = {
            r[0] for r in conn.execute(
                "SELECT TX_ID FROM SpotifyMemberPayments WHERE TX_ID IS NOT NULL"
            ).fetchall()
        }

        results = []

        for row in conn.execute("""
            SELECT ID, Date, Name, Income AS amount
            FROM BankTransactions
            WHERE LOWER(Category) LIKE '%spotify%' AND Income > 0
            ORDER BY Date DESC LIMIT 200
        """).fetchall():
            if row['ID'] not in assigned:
                results.append({
                    'id':     row['ID'],
                    'date':   row['Date'],
                    'name':   row['Name'],
                    'amount': float(row['amount'] or 0),
                    'source': 'BankTransactions',
                })

        for row in conn.execute("""
            SELECT ID, Executed_Date AS date, Name,
                   ABS(Transaction_Value) AS amount
            FROM CardTransactions
            WHERE LOWER(Category) LIKE '%spotify%'
            ORDER BY date DESC LIMIT 200
        """).fetchall():
            if row['ID'] not in assigned:
                results.append({
                    'id':     row['ID'],
                    'date':   row['date'],
                    'name':   row['Name'],
                    'amount': float(row['amount'] or 0),
                    'source': 'CardTransactions',
                })

        results.sort(key=lambda x: x['date'] or '', reverse=True)
        return results
    finally:
        conn.close()


# ── PDF generation ─────────────────────────────────────────────────────────────

def _heb(text) -> str:
    """Apply bidi algorithm for correct visual RTL ordering in PDF."""
    try:
        from bidi.algorithm import get_display
        return get_display(str(text))
    except Exception:
        return str(text)


def _register_font() -> str:
    """Register a Unicode font supporting Hebrew. Returns font name."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    candidates = [
        r'C:\Windows\Fonts\arial.ttf',
        r'C:\Windows\Fonts\ARIAL.TTF',
        '/usr/share/fonts/truetype/msttcorefonts/Arial.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
    ]
    for fp in candidates:
        if os.path.exists(fp):
            try:
                pdfmetrics.registerFont(TTFont('HebFont', fp))
                return 'HebFont'
            except Exception:
                pass
    return 'Helvetica'


def generate_pdf_report(member_ids: list, db) -> bytes:
    """
    Generate a PDF report for the given member IDs.
    member_ids: list of int member IDs. Pass None or [] for all paying members.
    Returns bytes of the PDF.
    """
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm

    font = _register_font()

    members  = db.get_spotify_members()
    charges  = db.get_spotify_charges()
    payments = db.get_spotify_payments()

    paying = [m for m in members if not m['is_exempt'] and m['is_active']]
    if member_ids:
        paying = [m for m in paying if m['id'] in member_ids]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)

    title_style = ParagraphStyle('title', fontName=font, fontSize=16, spaceAfter=6)
    sub_style   = ParagraphStyle('sub',   fontName=font, fontSize=10, spaceAfter=12, textColor=colors.grey)
    head_style  = ParagraphStyle('head',  fontName=font, fontSize=12, spaceAfter=6, spaceBefore=14)

    from datetime import date
    story = [
        Paragraph(_heb('Spotify Family Tracker — Report'), title_style),
        Paragraph(_heb(f'Generated: {date.today().strftime("%d/%m/%Y")}'), sub_style),
    ]

    teal = colors.HexColor('#1e9d8b')

    # Summary table
    story.append(Paragraph(_heb('Balance Summary'), head_style))
    summary_data = [[_heb('Member'), _heb('Total Paid'), _heb('Balance'), _heb('Status')]]
    for m in paying:
        m_payments = [p for p in payments if p['member_id'] == m['id']]
        bal = compute_balance(m_payments, charges)
        status_str = {
            'owes':  f"Owes ₪{abs(bal['balance']):.2f} ({abs(bal['months_status'])} mo.)",
            'even':  'Even',
            'ahead': f"Ahead ₪{bal['balance']:.2f} ({bal['months_status']} mo.)",
        }[bal['status']]
        total_paid = sum(p['amount'] for p in m_payments)
        summary_data.append([
            _heb(m['name']),
            f"₪{total_paid:.2f}",
            f"₪{bal['balance']:+.2f}",
            _heb(status_str),
        ])

    summary_table = Table(summary_data, colWidths=[5*cm, 3.5*cm, 3.5*cm, 5*cm])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), teal),
        ('TEXTCOLOR',  (0,0), (-1,0), colors.white),
        ('FONTNAME',   (0,0), (-1,-1), font),
        ('FONTSIZE',   (0,0), (-1,-1), 9),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f4f6f9')]),
        ('GRID',       (0,0), (-1,-1), 0.5, colors.HexColor('#eef0f6')),
        ('ALIGN',      (0,0), (-1,-1), 'CENTER'),
        ('VALIGN',     (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(summary_table)

    # Per-member payment history
    for m in paying:
        m_payments = [p for p in payments if p['member_id'] == m['id']]
        story.append(Spacer(1, 0.4*cm))
        story.append(Paragraph(_heb(f'Payment History — {m["name"]}'), head_style))

        pdata = [[_heb('Date'), _heb('Amount'), _heb('Note')]]
        for p in sorted(m_payments, key=lambda x: x['payment_date'] or '', reverse=True):
            pdata.append([
                p['payment_date'] or '—',
                f"₪{p['amount']:.2f}",
                _heb(p['note'] or ''),
            ])
        if len(pdata) == 1:
            pdata.append([_heb('No payments recorded'), '', ''])

        ptable = Table(pdata, colWidths=[4*cm, 4*cm, 9*cm])
        ptable.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), teal),
            ('TEXTCOLOR',  (0,0), (-1,0), colors.white),
            ('FONTNAME',   (0,0), (-1,-1), font),
            ('FONTSIZE',   (0,0), (-1,-1), 9),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f4f6f9')]),
            ('GRID',       (0,0), (-1,-1), 0.5, colors.HexColor('#eef0f6')),
            ('VALIGN',     (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
        story.append(ptable)

    doc.build(story)
    return buf.getvalue()
```

- [ ] **Step 4: Run tests to verify balance tests pass**

```bash
cd source && python Testing/test_spotify_tracker.py
```

Expected:
```
PASS: all Spotify tables exist
PASS: member CRUD
PASS: charge CRUD
PASS: payment CRUD
PASS: compute_balance owes
PASS: compute_balance ahead
PASS: compute_balance even
```

- [ ] **Step 5: Commit**

```bash
git add source/SpotifyTracker.py source/Testing/test_spotify_tracker.py
git commit -m "feat(spotify): add SpotifyTracker module with balance logic, suggestions, and PDF export"
```

---

## Task 5: Add WebApp Routes

**Files:**
- Modify: `source/WebApp.py` (insert before the `start()` function at line 2994)

- [ ] **Step 1: Add the HTML path constant and all routes**

In `source/WebApp.py`, find the line:
```python
def start(port: int = 5050, open_browser: bool = True):
```

Insert the following block immediately before it:

```python
SPOTIFY_HTML = os.path.join(_HERE, 'html', 'SpotifyTracker.html')

# ── Spotify Tracker routes ─────────────────────────────────────────────────────

@app.route('/spotify')
def spotify_page():
    if os.path.exists(SPOTIFY_HTML):
        return send_file(SPOTIFY_HTML)
    return "Spotify Tracker page not found", 404


@app.route('/api/spotify/members', methods=['GET', 'POST'])
def api_spotify_members():
    from database import DataBase
    db = DataBase()
    if request.method == 'GET':
        return jsonify({'ok': True, 'members': db.get_spotify_members()})
    body = request.get_json(force=True) or {}
    name = (body.get('name') or '').strip()
    if not name:
        return jsonify({'ok': False, 'error': 'name required'})
    try:
        mid = db.add_spotify_member(name, is_exempt=int(body.get('is_exempt', 0)))
        return jsonify({'ok': True, 'id': mid})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/spotify/members/<int:member_id>', methods=['PUT', 'DELETE'])
def api_spotify_member(member_id):
    from database import DataBase
    db = DataBase()
    if request.method == 'DELETE':
        try:
            db.delete_spotify_member(member_id)
            return jsonify({'ok': True})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)})
    body = request.get_json(force=True) or {}
    try:
        db.update_spotify_member(
            member_id,
            name=body.get('name', '').strip(),
            is_exempt=int(body.get('is_exempt', 0)),
            is_active=int(body.get('is_active', 1)),
        )
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/spotify/charges', methods=['GET', 'POST'])
def api_spotify_charges():
    from database import DataBase
    db = DataBase()
    if request.method == 'GET':
        return jsonify({'ok': True, 'charges': db.get_spotify_charges()})
    body = request.get_json(force=True) or {}
    try:
        members = db.get_spotify_members()
        active_count = sum(1 for m in members if m['is_active'])
        cid = db.add_spotify_charge(
            month=body.get('month', ''),
            total_amount=float(body.get('total_amount', 0)),
            member_count=int(body.get('member_count', active_count)),
            tx_id=body.get('tx_id'),
            confirmed=int(body.get('confirmed', 1)),
        )
        return jsonify({'ok': True, 'id': cid})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/spotify/charges/<int:charge_id>', methods=['PUT'])
def api_spotify_charge(charge_id):
    from database import DataBase
    db = DataBase()
    body = request.get_json(force=True) or {}
    try:
        db.update_spotify_charge(
            charge_id,
            total_amount=float(body.get('total_amount', 0)),
            member_count=int(body.get('member_count', 1)),
            confirmed=int(body.get('confirmed', 1)),
        )
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/spotify/charges/suggestions')
def api_spotify_charge_suggestions():
    import sys as _sys
    _sys.path.insert(0, _HERE)
    from SpotifyTracker import get_charge_suggestions
    try:
        suggestions = get_charge_suggestions(_DB_PATH)
        return jsonify({'ok': True, 'suggestions': suggestions})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/spotify/payments', methods=['GET', 'POST'])
def api_spotify_payments():
    from database import DataBase
    db = DataBase()
    if request.method == 'GET':
        member_id = request.args.get('member_id', type=int)
        return jsonify({'ok': True, 'payments': db.get_spotify_payments(member_id)})
    body = request.get_json(force=True) or {}
    try:
        pid = db.add_spotify_payment(
            member_id=int(body.get('member_id', 0)),
            amount=float(body.get('amount', 0)),
            payment_date=(body.get('payment_date') or '').strip(),
            tx_id=body.get('tx_id'),
            note=(body.get('note') or '').strip() or None,
        )
        return jsonify({'ok': True, 'id': pid})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/spotify/payments/<int:payment_id>', methods=['DELETE'])
def api_spotify_payment(payment_id):
    from database import DataBase
    db = DataBase()
    try:
        db.delete_spotify_payment(payment_id)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/spotify/unmatched')
def api_spotify_unmatched():
    import sys as _sys
    _sys.path.insert(0, _HERE)
    from SpotifyTracker import get_unmatched_payments
    try:
        return jsonify({'ok': True, 'transactions': get_unmatched_payments(_DB_PATH)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/spotify/balance')
def api_spotify_balance():
    import sys as _sys
    _sys.path.insert(0, _HERE)
    from database import DataBase
    from SpotifyTracker import compute_all_balances
    try:
        db = DataBase()
        return jsonify({'ok': True, 'balances': compute_all_balances(db)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/spotify/report')
def api_spotify_report():
    import sys as _sys
    _sys.path.insert(0, _HERE)
    from database import DataBase
    from SpotifyTracker import generate_pdf_report
    raw = request.args.get('member_id', '')
    if raw == 'all' or not raw:
        member_ids = []
    else:
        try:
            member_ids = [int(x) for x in raw.split(',') if x.strip()]
        except ValueError:
            return jsonify({'ok': False, 'error': 'invalid member_id'}), 400
    try:
        db = DataBase()
        pdf_bytes = generate_pdf_report(member_ids, db)
        from flask import Response
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={'Content-Disposition': 'attachment; filename="spotify_report.pdf"'},
        )
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

```

- [ ] **Step 2: Verify the server starts without import errors**

```bash
cd source && python -c "import WebApp; print('WebApp imports OK')"
```

Expected: `WebApp imports OK`

- [ ] **Step 3: Smoke-test the routes with the server running**

Start the server: `python AppManager.py`

Then in another terminal:
```bash
curl http://localhost:5050/api/spotify/members
```
Expected: `{"ok": true, "members": []}`

```bash
curl http://localhost:5050/api/spotify/charges
```
Expected: `{"ok": true, "charges": []}`

```bash
curl http://localhost:5050/api/spotify/balance
```
Expected: `{"ok": true, "balances": []}`

- [ ] **Step 4: Commit**

```bash
git add source/WebApp.py
git commit -m "feat(spotify): add /spotify route and all /api/spotify/* endpoints"
```

---

## Task 6: Create SpotifyTracker.html

**Files:**
- Create: `source/html/SpotifyTracker.html`

- [ ] **Step 1: Create the full frontend page**

Create `source/html/SpotifyTracker.html` with the following content:

```html
<!DOCTYPE html>
<html dir="rtl" lang="he">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Spotify Tracker</title>
<style>
:root {
  --teal:       #1e9d8b;
  --teal-light: #e8f7f5;
  --navy:       #1e2a4a;
  --bg:         #f4f6f9;
  --white:      #ffffff;
  --border:     #eef0f6;
  --text-muted: #888;
  --text-sub:   #555;
  --red:        #e74c3c;
  --amber:      #f0b429;
  --green:      #2ecc71;
  --shadow-sm:  0 2px 10px rgba(0,0,0,.06);
  --shadow-md:  0 6px 20px rgba(0,0,0,.10);
  --radius:     14px;
  --radius-sm:  8px;
}
*,*::before,*::after { box-sizing: border-box; margin:0; padding:0; }
body {
  font-family: 'Segoe UI', Arial, sans-serif;
  background: var(--bg);
  min-height: 100vh;
  direction: rtl;
  color: var(--navy);
  font-size: 14px;
  display: flex;
  flex-direction: column;
}

/* ── Hamburger + sidebar ─────────────────────────────────── */
.ham-btn {
  position: fixed; top: 14px; right: 14px; z-index: 500;
  width: 36px; height: 36px; background: var(--white);
  border: 1.5px solid var(--border); border-radius: 9px;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; color: var(--navy); box-shadow: var(--shadow-sm);
  transition: background .15s, color .15s;
}
.ham-btn:hover { background: var(--teal); border-color: var(--teal); color: #fff; }
.ham-btn.open  { opacity: 0; pointer-events: none; }
.nav-overlay {
  position: fixed; inset: 0; background: rgba(15,22,45,.26);
  z-index: 490; opacity: 0; pointer-events: none; transition: opacity .22s;
}
.nav-overlay.open { opacity: 1; pointer-events: all; }
.nav-sidebar {
  position: fixed; top: 0; right: 0; height: 100vh; width: 230px;
  background: var(--white); z-index: 495;
  transform: translate3d(100%,0,0);
  transition: transform .22s cubic-bezier(.4,0,.2,1);
  box-shadow: -4px 0 24px rgba(0,0,0,.09);
  display: flex; flex-direction: column;
}
.nav-sidebar.open { transform: translate3d(0,0,0); }
.nav-sidebar-hdr {
  display: flex; align-items: center; padding: 18px 18px 14px;
  border-bottom: 1px solid var(--border); flex-shrink: 0;
}
.nav-sidebar-hdr span { font-size: .95em; font-weight: 700; color: var(--navy); }
.nav-close-btn {
  margin-right: auto; background: none; border: none; cursor: pointer;
  font-size: 1.1em; color: #555; padding: 4px 6px; border-radius: 6px;
}
.nav-close-btn:hover { background: var(--teal-light); color: var(--teal); }
.nav-scroll { flex: 1; overflow-y: auto; padding: 8px 0 16px; }
.sidebar-footer { padding: 12px 16px; border-top: 1px solid var(--border); flex-shrink: 0; }
.nav-restart-btn {
  width: 100%; padding: 8px 12px; border: 1.5px dashed var(--border); border-radius: 8px;
  background: none; color: var(--text-muted); font-size: .78em; font-weight: 600;
  cursor: pointer; font-family: inherit; display: flex; align-items: center;
  gap: 7px; justify-content: center; transition: background .15s, color .15s;
}
.nav-restart-btn:hover { background: #fff3f3; color: #e53935; border-color: #e53935; }
.nav-item {
  display: flex; align-items: center; padding: 10px 20px;
  text-decoration: none; color: var(--text-sub);
  font-size: .875em; font-weight: 500; transition: background .1s, color .1s;
  position: relative;
}
.nav-item::before {
  content: ''; position: absolute; right: 0; top: 22%; height: 56%;
  width: 3px; border-radius: 3px 0 0 3px; background: transparent;
}
.nav-item:hover { background: var(--teal-light); color: var(--teal); }
.nav-item:hover::before { background: var(--teal); }
.nav-item.active { color: #b8c0d0; cursor: default; pointer-events: none; }
.nav-sep { height: 1px; background: var(--border); margin: 8px 16px; }

/* ── Page header ─────────────────────────────────────────── */
.page-header {
  display: flex; align-items: center; gap: 10px;
  padding: 9px 60px 9px 14px;
  border-bottom: 1.5px solid var(--border); flex-shrink: 0;
  background: var(--white);
}
.page-title { font-size: 1em; font-weight: 700; }

/* ── Top summary bar ─────────────────────────────────────── */
.summary-bar {
  display: flex; gap: 12px; align-items: center; flex-wrap: wrap;
  padding: 12px 20px; background: var(--navy); color: #fff;
  flex-shrink: 0;
}
.summary-chip {
  background: rgba(255,255,255,.1); border-radius: 8px;
  padding: 6px 14px; font-size: .82em; line-height: 1.5;
}
.summary-chip .val { font-size: 1.15em; font-weight: 700; display: block; }
.summary-chip .lbl { opacity: .7; font-size: .85em; }
.summary-chip .val.red  { color: #ff8080; }
.summary-chip .val.amber{ color: #ffd43b; }

/* ── Charge banner ───────────────────────────────────────── */
.charge-banner {
  background: #fffbea; border-bottom: 2px solid var(--amber);
  padding: 10px 20px; font-size: .84em; color: #7a5700;
  display: flex; align-items: center; gap: 12px;
}
.charge-banner button {
  background: var(--amber); color: #fff; border: none; border-radius: 6px;
  padding: 5px 12px; font-size: .85em; cursor: pointer; font-family: inherit;
}

/* ── Member tabs ─────────────────────────────────────────── */
.tabs-bar {
  background: var(--white); border-bottom: 2px solid var(--border);
  display: flex; overflow-x: auto; flex-shrink: 0;
}
.tab-btn {
  padding: 10px 16px; border: none; border-bottom: 2px solid transparent;
  background: none; color: var(--text-sub); font-size: .82em; font-weight: 500;
  cursor: pointer; white-space: nowrap; font-family: inherit;
  transition: color .1s;
  margin-bottom: -2px;
}
.tab-btn:hover { color: var(--teal); }
.tab-btn.active { color: var(--teal); border-bottom-color: var(--teal); font-weight: 700; }
.status-badge {
  display: inline-block; border-radius: 4px; padding: 1px 7px;
  font-size: .8em; margin-right: 5px;
}
.status-badge.owes  { background: #fff3f3; color: var(--red); }
.status-badge.even  { background: #f4f6f9; color: var(--text-muted); }
.status-badge.ahead { background: var(--teal-light); color: var(--teal); }

/* ── Tab panels ──────────────────────────────────────────── */
.tab-panel { display: none; flex: 1; overflow-y: auto; }
.tab-panel.active { display: flex; }

/* Overview panel */
.overview-panel { flex-direction: column; padding: 20px; gap: 20px; }
.member-grid { display: grid; grid-template-columns: repeat(auto-fill,minmax(200px,1fr)); gap: 12px; }
.member-card {
  background: var(--white); border-radius: var(--radius); padding: 16px;
  box-shadow: var(--shadow-sm); border: 1.5px solid var(--border);
  display: flex; flex-direction: column; gap: 8px;
}
.member-card .mname { font-weight: 700; font-size: .95em; }
.member-card .mbal  { font-size: 1.1em; font-weight: 700; }
.member-card .mbal.red  { color: var(--red); }
.member-card .mbal.green{ color: var(--teal); }
.member-card .msub  { font-size: .78em; color: var(--text-muted); }
.member-card .mlast { font-size: .75em; color: var(--text-muted); margin-top: 4px; }

/* Unmatched payments table */
.section-title { font-size: .8em; font-weight: 700; color: var(--text-muted); letter-spacing: .05em; margin-bottom: 8px; }
.data-table { width: 100%; border-collapse: collapse; font-size: .83em; }
.data-table th { background: var(--bg); color: var(--text-muted); font-size: .78em; font-weight: 600; padding: 7px 10px; text-align: right; }
.data-table td { padding: 8px 10px; border-bottom: 1px solid var(--border); }
.data-table tr:last-child td { border-bottom: none; }
.data-table tr:hover td { background: var(--teal-light); }

/* Member detail panel */
.member-panel { gap: 0; }
.detail-left {
  width: 220px; flex-shrink: 0; border-left: 1px solid var(--border);
  padding: 18px 16px; background: #fafbfc;
  display: flex; flex-direction: column; gap: 12px;
}
.detail-right { flex: 1; padding: 16px 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 20px; }
.balance-card {
  border-radius: 10px; padding: 12px; border: 1.5px solid;
}
.balance-card.owes  { background: #fff3f3; border-color: #fcc; }
.balance-card.even  { background: var(--bg);  border-color: var(--border); }
.balance-card.ahead { background: var(--teal-light); border-color: #b2e8e2; }
.balance-card .bal-label { font-size: .72em; color: var(--text-muted); margin-bottom: 3px; }
.balance-card .bal-val   { font-size: 1.3em; font-weight: 700; }
.balance-card .bal-val.red   { color: var(--red); }
.balance-card .bal-val.green { color: var(--teal); }
.balance-card .bal-sub   { font-size: .75em; margin-top: 2px; }
.balance-card .bal-sub.red   { color: var(--red); }
.balance-card .bal-sub.green { color: var(--teal); }
.info-chip {
  background: var(--white); border: 1px solid var(--border); border-radius: 8px;
  padding: 10px; font-size: .75em; color: var(--text-sub);
}
.info-chip .ic-lbl { color: var(--text-muted); margin-bottom: 4px; }
.info-chip .ic-val { font-weight: 600; }

/* Buttons */
.btn-primary {
  padding: 8px 14px; background: var(--teal); color: #fff;
  border: none; border-radius: 8px; font-size: .82em; font-weight: 600;
  cursor: pointer; font-family: inherit; transition: filter .15s;
}
.btn-primary:hover { filter: brightness(1.1); }
.btn-ghost {
  padding: 5px 10px; background: none; border: 1.5px solid var(--border);
  border-radius: 6px; font-size: .78em; color: var(--text-sub);
  cursor: pointer; font-family: inherit;
}
.btn-ghost:hover { border-color: var(--teal); color: var(--teal); }
.btn-danger {
  padding: 4px 8px; background: none; border: 1px solid #fcc;
  border-radius: 5px; font-size: .75em; color: var(--red); cursor: pointer;
}
.btn-danger:hover { background: #fff3f3; }

/* ── Modals ──────────────────────────────────────────────── */
.modal-backdrop {
  position: fixed; inset: 0; background: rgba(15,22,45,.45);
  z-index: 800; display: none; align-items: center; justify-content: center;
}
.modal-backdrop.open { display: flex; }
.modal {
  background: var(--white); border-radius: var(--radius); width: 460px;
  max-width: calc(100vw - 32px); max-height: 90vh; overflow-y: auto;
  box-shadow: var(--shadow-md); padding: 24px;
  display: flex; flex-direction: column; gap: 16px;
}
.modal-title { font-size: 1em; font-weight: 700; }
.modal-body  { display: flex; flex-direction: column; gap: 12px; }
.field-row   { display: flex; flex-direction: column; gap: 4px; }
.field-label { font-size: .78em; color: var(--text-muted); font-weight: 600; }
.field-input {
  padding: 8px 10px; border: 1.5px solid var(--border); border-radius: 8px;
  font-size: .88em; font-family: inherit; color: var(--navy);
  background: var(--white);
}
.field-input:focus { outline: none; border-color: var(--teal); }
.modal-footer { display: flex; gap: 8px; justify-content: flex-end; padding-top: 4px; }

/* ── Unmatched list in assign modal ─────────────────────── */
.tx-list { display: flex; flex-direction: column; gap: 6px; max-height: 260px; overflow-y: auto; }
.tx-item {
  display: flex; align-items: center; gap: 10px; padding: 8px 10px;
  border: 1.5px solid var(--border); border-radius: 8px; cursor: pointer;
  transition: border-color .1s, background .1s;
}
.tx-item:hover, .tx-item.selected { border-color: var(--teal); background: var(--teal-light); }
.tx-item .tx-name  { font-weight: 600; font-size: .84em; flex: 1; }
.tx-item .tx-date  { font-size: .76em; color: var(--text-muted); }
.tx-item .tx-amt   { font-weight: 700; color: var(--teal); font-size: .9em; }

@media(max-width:640px) {
  .member-panel { flex-direction: column; }
  .detail-left  { width: 100%; border-left: none; border-bottom: 1px solid var(--border); }
}
</style>
</head>
<body>

<!-- Hamburger -->
<button class="ham-btn" id="hamBtn" onclick="openNav()" aria-label="פתח תפריט">
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round">
    <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>
  </svg>
</button>
<div class="nav-overlay" id="navOverlay" onclick="closeNav()"></div>
<nav class="nav-sidebar" id="navSidebar">
  <div class="nav-sidebar-hdr">
    <span>Menu</span>
    <button class="nav-close-btn" onclick="closeNav()" aria-label="סגור">✕</button>
  </div>
  <div class="nav-scroll">
    <a class="nav-item" href="/">ניתוח חודשי</a>
    <div class="nav-sep"></div>
    <a class="nav-item" href="/accounts">חשבונות</a>
    <a class="nav-item" href="/housing">דיור</a>
    <a class="nav-item" href="/organizer">ארגונית</a>
    <a class="nav-item" href="/bills">מעקב חשבונות</a>
    <a class="nav-item" href="/categories">ניתוח קטגוריאלי</a>
    <a class="nav-item" href="/search">חיפוש</a>
    <a class="nav-item active" href="/spotify">Spotify Tracker</a>
    <div class="nav-sep"></div>
    <a class="nav-item" href="/tagger">תייגן</a>
    <a class="nav-item" href="/files">קבצים</a>
  </div>
  <div class="sidebar-footer">
    <button class="nav-restart-btn" onclick="restartServer(this)">
      <svg fill="none" height="13" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2.2" viewBox="0 0 24 24" width="13"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-4.07"/></svg>
      Restart Server
    </button>
  </div>
</nav>

<!-- Page header -->
<header class="page-header">
  <span style="font-size:1.2em">🎵</span>
  <span class="page-title">Spotify Tracker</span>
  <div style="margin-right:auto;display:flex;gap:8px;">
    <button class="btn-ghost" onclick="openAddMemberModal()">+ חבר</button>
    <button class="btn-primary" onclick="openExportModal()">📄 ייצוא PDF</button>
  </div>
</header>

<!-- Charge confirmation banner -->
<div class="charge-banner" id="chargeBanner" style="display:none">
  <span>⚠️ לא אושר חיוב Spotify לחודש <strong id="bannerMonth"></strong></span>
  <button onclick="openConfirmChargeModal()">אשר חיוב</button>
</div>

<!-- Summary bar -->
<div class="summary-bar" id="summaryBar">
  <div class="summary-chip">
    <span class="lbl">חיוב חודשי נוכחי</span>
    <span class="val" id="sumCharge">—</span>
  </div>
  <div class="summary-chip">
    <span class="lbl">חלק לאדם</span>
    <span class="val" id="sumShare">—</span>
  </div>
  <div class="summary-chip">
    <span class="lbl">סה"כ חוב פתוח</span>
    <span class="val red" id="sumOwed">₪0</span>
  </div>
  <div class="summary-chip">
    <span class="lbl">תשלומים לא משויכים</span>
    <span class="val amber" id="sumUnmatched">0</span>
  </div>
</div>

<!-- Tabs -->
<div class="tabs-bar" id="tabsBar">
  <button class="tab-btn active" data-tab="overview" onclick="switchTab('overview',this)">📋 סקירה כללית</button>
</div>

<!-- Overview panel -->
<div class="tab-panel active overview-panel" id="panel-overview">
  <div>
    <div class="section-title">סטטוס חברים</div>
    <div class="member-grid" id="memberGrid"></div>
  </div>
  <div>
    <div class="section-title">תשלומים ממתינים לשיוך (<span id="unmatchedCount">0</span>)</div>
    <div style="background:var(--white);border-radius:var(--radius);box-shadow:var(--shadow-sm);overflow:hidden;">
      <table class="data-table">
        <thead><tr>
          <th>תאריך</th><th>שם</th><th>סכום</th><th>מקור</th><th></th>
        </tr></thead>
        <tbody id="unmatchedBody"></tbody>
      </table>
    </div>
  </div>
</div>

<!-- Member panels rendered dynamically by JS -->

<!-- ── Modals ───────────────────────────────────────────── -->

<!-- Assign payment modal -->
<div class="modal-backdrop" id="assignModal">
  <div class="modal">
    <div class="modal-title">שייך תשלום — <span id="assignMemberName"></span></div>
    <div class="modal-body">
      <div style="font-size:.8em;color:var(--text-muted);margin-bottom:4px;">בחר עסקת Spotify קיימת:</div>
      <div class="tx-list" id="txList"></div>
      <div style="font-size:.78em;color:var(--text-muted);text-align:center;padding:4px 0;">— או הכנס ידנית —</div>
      <div class="field-row">
        <label class="field-label">סכום (₪)</label>
        <input class="field-input" type="number" step="0.01" id="assignAmount" placeholder="0.00">
      </div>
      <div class="field-row">
        <label class="field-label">תאריך תשלום</label>
        <input class="field-input" type="date" id="assignDate">
      </div>
      <div class="field-row">
        <label class="field-label">הערה (אופציונלי)</label>
        <input class="field-input" type="text" id="assignNote" placeholder="הערה...">
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn-ghost" onclick="closeModal('assignModal')">ביטול</button>
      <button class="btn-primary" onclick="submitAssignPayment()">שמור</button>
    </div>
  </div>
</div>

<!-- Add/edit member modal -->
<div class="modal-backdrop" id="memberModal">
  <div class="modal">
    <div class="modal-title" id="memberModalTitle">הוסף חבר</div>
    <div class="modal-body">
      <div class="field-row">
        <label class="field-label">שם</label>
        <input class="field-input" type="text" id="memberName" placeholder="שם החבר...">
      </div>
      <div class="field-row" style="flex-direction:row;align-items:center;gap:8px;">
        <input type="checkbox" id="memberExempt" style="width:16px;height:16px;">
        <label class="field-label" for="memberExempt" style="margin:0;">פטור מתשלום (בעל/ת החשבון)</label>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn-ghost" onclick="closeModal('memberModal')">ביטול</button>
      <button class="btn-primary" onclick="submitMember()">שמור</button>
    </div>
  </div>
</div>

<!-- Confirm charge modal -->
<div class="modal-backdrop" id="chargeModal">
  <div class="modal">
    <div class="modal-title">אשר חיוב Spotify</div>
    <div class="modal-body">
      <div id="chargeSuggestionBox" style="background:var(--bg);border-radius:8px;padding:12px;font-size:.84em;margin-bottom:4px;"></div>
      <div class="field-row">
        <label class="field-label">חודש (YYYY-MM)</label>
        <input class="field-input" type="month" id="chargeMonth">
      </div>
      <div class="field-row">
        <label class="field-label">סכום כולל (₪)</label>
        <input class="field-input" type="number" step="0.01" id="chargeAmount" placeholder="0.00">
      </div>
      <div class="field-row">
        <label class="field-label">מספר חברים</label>
        <input class="field-input" type="number" id="chargeMemberCount" min="1">
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn-ghost" onclick="closeModal('chargeModal')">ביטול</button>
      <button class="btn-primary" onclick="submitCharge()">אשר</button>
    </div>
  </div>
</div>

<!-- Export PDF modal -->
<div class="modal-backdrop" id="exportModal">
  <div class="modal">
    <div class="modal-title">ייצוא דוח PDF</div>
    <div class="modal-body">
      <div class="field-row">
        <label class="field-label">בחר חברים לדוח:</label>
        <label style="display:flex;align-items:center;gap:8px;font-size:.85em;margin-top:6px;">
          <input type="radio" name="exportMode" value="all" checked onchange="toggleExportPicker(false)"> כל החברים
        </label>
        <label style="display:flex;align-items:center;gap:8px;font-size:.85em;margin-top:4px;">
          <input type="radio" name="exportMode" value="single" onchange="toggleExportPicker(true)"> חבר ספציפי
        </label>
      </div>
      <div id="exportPickerRow" class="field-row" style="display:none;">
        <label class="field-label">בחר חבר</label>
        <select class="field-input" id="exportMemberSelect"></select>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn-ghost" onclick="closeModal('exportModal')">ביטול</button>
      <button class="btn-primary" onclick="doExportPDF()">הורד PDF</button>
    </div>
  </div>
</div>

<script>
// ── State ─────────────────────────────────────────────────
let _members  = [];
let _charges  = [];
let _balances = [];
let _unmatched = [];
let _payments  = {};    // member_id → array
let _activeTab = 'overview';
let _assignMemberId = null;
let _selectedTxId   = null;
let _editMemberId   = null;
let _pendingSuggestion = null;

// ── Nav ───────────────────────────────────────────────────
function openNav()  { document.getElementById('navSidebar').classList.add('open'); document.getElementById('navOverlay').classList.add('open'); document.getElementById('hamBtn').classList.add('open'); }
function closeNav() { document.getElementById('navSidebar').classList.remove('open'); document.getElementById('navOverlay').classList.remove('open'); document.getElementById('hamBtn').classList.remove('open'); }
function restartServer(btn) {
  btn.disabled = true; btn.textContent = 'Restarting...';
  fetch('/api/restart', {method:'POST'}).then(() => setTimeout(() => location.reload(), 2000));
}

// ── Init ──────────────────────────────────────────────────
async function init() {
  await Promise.all([loadMembers(), loadCharges(), loadBalances(), loadUnmatched()]);
  renderSummaryBar();
  renderMemberTabs();
  renderOverview();
  checkChargeBanner();
}

async function loadMembers()  { const r = await fetch('/api/spotify/members');  const d = await r.json(); _members  = d.members  || []; }
async function loadCharges()  { const r = await fetch('/api/spotify/charges');  const d = await r.json(); _charges  = d.charges  || []; }
async function loadBalances() { const r = await fetch('/api/spotify/balance');  const d = await r.json(); _balances = d.balances || []; }
async function loadUnmatched(){ const r = await fetch('/api/spotify/unmatched');const d = await r.json(); _unmatched= d.transactions || []; }

async function loadPaymentsForMember(memberId) {
  const r = await fetch(`/api/spotify/payments?member_id=${memberId}`);
  const d = await r.json();
  _payments[memberId] = d.payments || [];
}

// ── Summary bar ───────────────────────────────────────────
function renderSummaryBar() {
  const confirmed = _charges.filter(c => c.confirmed);
  let charge = 0, share = 0;
  if (confirmed.length) {
    const latest = confirmed.reduce((a,b) => a.month > b.month ? a : b);
    charge = latest.total_amount;
    share  = charge / latest.member_count;
  }
  const totalOwed = _balances.reduce((s, b) => b.balance < 0 ? s + Math.abs(b.balance) : s, 0);
  document.getElementById('sumCharge').textContent   = charge  ? `₪${charge.toFixed(2)}`  : '—';
  document.getElementById('sumShare').textContent    = share   ? `₪${share.toFixed(2)}`   : '—';
  document.getElementById('sumOwed').textContent     = `₪${totalOwed.toFixed(2)}`;
  document.getElementById('sumUnmatched').textContent = _unmatched.length;
}

// ── Charge banner ─────────────────────────────────────────
async function checkChargeBanner() {
  const now    = new Date();
  const curMon = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}`;
  const hasConf = _charges.some(c => c.month === curMon && c.confirmed);
  if (!hasConf) {
    document.getElementById('bannerMonth').textContent = curMon;
    document.getElementById('chargeBanner').style.display = 'flex';
  }
}

// ── Tabs ──────────────────────────────────────────────────
function renderMemberTabs() {
  const bar = document.getElementById('tabsBar');
  // Remove old member tabs (keep overview btn)
  bar.querySelectorAll('[data-tab^="member-"]').forEach(el => el.remove());
  // Remove old member panels
  document.querySelectorAll('.tab-panel[id^="panel-member-"]').forEach(el => el.remove());

  const paying = _members.filter(m => !m.is_exempt && m.is_active);
  paying.forEach(m => {
    const bal = _balances.find(b => b.member_id === m.id);
    const status = bal ? bal.status : 'even';
    const badge = statusBadge(bal);

    // Tab button
    const btn = document.createElement('button');
    btn.className = 'tab-btn';
    btn.dataset.tab = `member-${m.id}`;
    btn.innerHTML = `${m.name} ${badge}`;
    btn.onclick = () => switchTab(`member-${m.id}`, btn, m.id);
    bar.appendChild(btn);

    // Panel
    const panel = document.createElement('div');
    panel.className = 'tab-panel member-panel';
    panel.id = `panel-member-${m.id}`;
    panel.innerHTML = memberPanelHTML(m, bal);
    document.body.appendChild(panel);
  });
}

function statusBadge(bal) {
  if (!bal) return `<span class="status-badge even">— מאוזן</span>`;
  if (bal.status === 'owes')  return `<span class="status-badge owes">⚠️ חייב ₪${Math.abs(bal.balance).toFixed(0)}</span>`;
  if (bal.status === 'ahead') return `<span class="status-badge ahead">✅ +${bal.months_status} חודש</span>`;
  return `<span class="status-badge even">— מאוזן</span>`;
}

async function switchTab(tabId, btnEl, memberId) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  btnEl.classList.add('active');
  document.getElementById(`panel-${tabId}`).classList.add('active');
  _activeTab = tabId;

  if (memberId) {
    await loadPaymentsForMember(memberId);
    renderMemberDetail(memberId);
  }
}

// ── Overview rendering ────────────────────────────────────
function renderOverview() {
  const grid = document.getElementById('memberGrid');
  grid.innerHTML = '';
  const paying = _members.filter(m => !m.is_exempt && m.is_active);
  paying.forEach(m => {
    const bal = _balances.find(b => b.member_id === m.id);
    const card = document.createElement('div');
    card.className = 'member-card';
    const last = bal && bal.last_payment ? bal.last_payment : null;
    const color = !bal ? '' : bal.status === 'owes' ? 'red' : bal.status === 'ahead' ? 'green' : '';
    const balText = !bal ? '—'
      : bal.status === 'owes'  ? `חייב ₪${Math.abs(bal.balance).toFixed(2)}`
      : bal.status === 'ahead' ? `+₪${bal.balance.toFixed(2)}`
      : 'מאוזן';
    const monthsText = !bal ? '' : bal.status === 'owes' ? `${Math.abs(bal.months_status)} חודשים`
      : bal.status === 'ahead' ? `${bal.months_status} חודשים קדימה` : '';
    card.innerHTML = `
      <div class="mname">${m.name}</div>
      <div class="mbal ${color}">${balText}</div>
      <div class="msub">${monthsText}</div>
      <div class="mlast">${last ? 'תשלום אחרון: ' + last : 'אין תשלומים'}</div>
    `;
    grid.appendChild(card);
  });

  // Unmatched payments
  document.getElementById('unmatchedCount').textContent = _unmatched.length;
  const tbody = document.getElementById('unmatchedBody');
  tbody.innerHTML = '';
  if (!_unmatched.length) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-muted);padding:16px;">אין תשלומים ממתינים</td></tr>';
    return;
  }
  _unmatched.forEach(tx => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${tx.date || '—'}</td>
      <td>${tx.name}</td>
      <td style="font-weight:700;color:var(--teal);">₪${parseFloat(tx.amount).toFixed(2)}</td>
      <td style="font-size:.78em;color:var(--text-muted);">${tx.source}</td>
      <td>
        <select class="field-input" style="padding:4px 6px;font-size:.78em;" onchange="quickAssign(${tx.id},'${tx.source}',${tx.amount},'${tx.date}',this.value)">
          <option value="">שייך ל...</option>
          ${_members.filter(m=>!m.is_exempt&&m.is_active).map(m=>`<option value="${m.id}">${m.name}</option>`).join('')}
        </select>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

async function quickAssign(txId, source, amount, date, memberId) {
  if (!memberId) return;
  await fetch('/api/spotify/payments', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({member_id: parseInt(memberId), amount: parseFloat(amount), payment_date: date, tx_id: txId})
  });
  await Promise.all([loadUnmatched(), loadBalances(), loadPaymentsForMember(parseInt(memberId))]);
  renderSummaryBar(); renderOverview(); renderMemberTabs();
}

// ── Member detail rendering ───────────────────────────────
function memberPanelHTML(m, bal) {
  return `
    <div class="detail-left" id="detail-left-${m.id}">
      <div style="font-weight:700;font-size:.95em;">${m.name}</div>
      <div id="bal-card-${m.id}"></div>
      <div class="info-chip">
        <div class="ic-lbl">חלק חודשי נוכחי</div>
        <div class="ic-val" id="cur-share-${m.id}">—</div>
      </div>
      <button class="btn-primary" style="margin-top:auto;" onclick="openAssignModal(${m.id},'${m.name}')">+ שייך תשלום</button>
      <button class="btn-ghost" style="font-size:.76em;" onclick="openEditMemberModal(${m.id},'${m.name}',${m.is_exempt})">✏️ ערוך חבר</button>
    </div>
    <div class="detail-right">
      <div>
        <div class="section-title">היסטוריית תשלומים</div>
        <div style="background:var(--white);border-radius:var(--radius);box-shadow:var(--shadow-sm);overflow:hidden;">
          <table class="data-table">
            <thead><tr><th>תאריך</th><th>סכום</th><th>מקור</th><th>הערה</th><th></th></tr></thead>
            <tbody id="payments-body-${m.id}"></tbody>
          </table>
        </div>
      </div>
      <div>
        <div class="section-title">היסטוריית מחיר מנוי</div>
        <div style="background:var(--white);border-radius:var(--radius);box-shadow:var(--shadow-sm);overflow:hidden;">
          <table class="data-table">
            <thead><tr><th>חודש</th><th>סה"כ מנוי</th><th>מס׳ חברים</th><th>חלק לאדם</th></tr></thead>
            <tbody id="charges-body-${m.id}"></tbody>
          </table>
        </div>
      </div>
    </div>
  `;
}

function renderMemberDetail(memberId) {
  const bal = _balances.find(b => b.member_id === memberId);
  const payments = _payments[memberId] || [];

  // Balance card
  const bc = document.getElementById(`bal-card-${memberId}`);
  if (bc && bal) {
    const cls  = bal.status;
    const valColor = bal.status === 'owes' ? 'red' : bal.status === 'ahead' ? 'green' : '';
    const valText  = bal.status === 'owes'  ? `חייב ₪${Math.abs(bal.balance).toFixed(2)}`
                   : bal.status === 'ahead' ? `+₪${bal.balance.toFixed(2)}`
                   : 'מאוזן';
    const subText  = bal.status === 'owes'  ? `${Math.abs(bal.months_status)} חודשים לא שולמו`
                   : bal.status === 'ahead' ? `${bal.months_status} חודשים קדימה`
                   : '';
    bc.innerHTML = `
      <div class="balance-card ${cls}">
        <div class="bal-label">יתרה נוכחית</div>
        <div class="bal-val ${valColor}">${valText}</div>
        ${subText ? `<div class="bal-sub ${valColor}">${subText}</div>` : ''}
        <div style="font-size:.72em;color:#aaa;margin-top:6px;">נכון לחודש הנוכחי</div>
      </div>`;
  }
  const shareEl = document.getElementById(`cur-share-${memberId}`);
  if (shareEl && bal) shareEl.textContent = `₪${bal.current_share.toFixed(2)} / חודש`;

  // Payments table
  const pb = document.getElementById(`payments-body-${memberId}`);
  if (pb) {
    pb.innerHTML = '';
    if (!payments.length) {
      pb.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-muted);padding:16px;">אין תשלומים רשומים</td></tr>';
    } else {
      payments.forEach(p => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${p.payment_date || '—'}</td>
          <td style="font-weight:700;">₪${parseFloat(p.amount).toFixed(2)}</td>
          <td style="font-size:.8em;color:var(--text-muted);">${p.tx_id ? 'עסקה' : 'ידני'}</td>
          <td style="font-size:.8em;color:var(--text-muted);">${p.note || ''}</td>
          <td><button class="btn-danger" onclick="deletePayment(${p.id},${memberId})">✕</button></td>
        `;
        pb.appendChild(tr);
      });
    }
  }

  // Charges table
  const cb = document.getElementById(`charges-body-${memberId}`);
  if (cb) {
    cb.innerHTML = '';
    const sorted = [..._charges].filter(c => c.confirmed).sort((a,b) => b.month.localeCompare(a.month));
    if (!sorted.length) {
      cb.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--text-muted);padding:16px;">אין חיובים מאושרים</td></tr>';
    } else {
      sorted.forEach(c => {
        const share = (c.total_amount / c.member_count).toFixed(2);
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${c.month}</td>
          <td style="font-weight:600;">₪${parseFloat(c.total_amount).toFixed(2)}</td>
          <td>${c.member_count}</td>
          <td style="color:var(--teal);font-weight:600;">₪${share}</td>
        `;
        cb.appendChild(tr);
      });
    }
  }
}

// ── Assign payment modal ──────────────────────────────────
function openAssignModal(memberId, memberName) {
  _assignMemberId = memberId;
  _selectedTxId   = null;
  document.getElementById('assignMemberName').textContent = memberName;
  document.getElementById('assignAmount').value = '';
  document.getElementById('assignDate').value   = new Date().toISOString().split('T')[0];
  document.getElementById('assignNote').value   = '';

  const list = document.getElementById('txList');
  list.innerHTML = '';
  if (!_unmatched.length) {
    list.innerHTML = '<div style="font-size:.8em;color:var(--text-muted);text-align:center;padding:8px;">אין עסקאות ממתינות</div>';
  } else {
    _unmatched.forEach(tx => {
      const div = document.createElement('div');
      div.className = 'tx-item';
      div.dataset.txId = tx.id;
      div.dataset.amount = tx.amount;
      div.dataset.date   = tx.date;
      div.innerHTML = `<div class="tx-name">${tx.name}</div><div class="tx-date">${tx.date}</div><div class="tx-amt">₪${parseFloat(tx.amount).toFixed(2)}</div>`;
      div.onclick = () => selectTx(div, tx);
      list.appendChild(div);
    });
  }
  openModal('assignModal');
}

function selectTx(el, tx) {
  document.querySelectorAll('#txList .tx-item').forEach(i => i.classList.remove('selected'));
  el.classList.add('selected');
  _selectedTxId = tx.id;
  document.getElementById('assignAmount').value = tx.amount;
  document.getElementById('assignDate').value   = tx.date || '';
}

async function submitAssignPayment() {
  const amount = parseFloat(document.getElementById('assignAmount').value);
  const date   = document.getElementById('assignDate').value;
  const note   = document.getElementById('assignNote').value;
  if (!amount || !date) { alert('נא למלא סכום ותאריך'); return; }
  await fetch('/api/spotify/payments', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({member_id: _assignMemberId, amount, payment_date: date, tx_id: _selectedTxId || null, note: note || null})
  });
  closeModal('assignModal');
  await Promise.all([loadUnmatched(), loadBalances(), loadPaymentsForMember(_assignMemberId)]);
  renderSummaryBar(); renderOverview(); renderMemberTabs();
  renderMemberDetail(_assignMemberId);
}

async function deletePayment(paymentId, memberId) {
  if (!confirm('למחוק תשלום זה?')) return;
  await fetch(`/api/spotify/payments/${paymentId}`, {method:'DELETE'});
  await Promise.all([loadUnmatched(), loadBalances(), loadPaymentsForMember(memberId)]);
  renderSummaryBar(); renderOverview(); renderMemberTabs();
  renderMemberDetail(memberId);
}

// ── Add/edit member modal ─────────────────────────────────
function openAddMemberModal() {
  _editMemberId = null;
  document.getElementById('memberModalTitle').textContent = 'הוסף חבר';
  document.getElementById('memberName').value    = '';
  document.getElementById('memberExempt').checked = false;
  openModal('memberModal');
}

function openEditMemberModal(id, name, isExempt) {
  _editMemberId = id;
  document.getElementById('memberModalTitle').textContent = 'ערוך חבר';
  document.getElementById('memberName').value    = name;
  document.getElementById('memberExempt').checked = !!isExempt;
  openModal('memberModal');
}

async function submitMember() {
  const name     = document.getElementById('memberName').value.trim();
  const isExempt = document.getElementById('memberExempt').checked ? 1 : 0;
  if (!name) { alert('נא להכניס שם'); return; }
  if (_editMemberId) {
    await fetch(`/api/spotify/members/${_editMemberId}`, {
      method:'PUT', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({name, is_exempt: isExempt, is_active: 1})
    });
  } else {
    await fetch('/api/spotify/members', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({name, is_exempt: isExempt})
    });
  }
  closeModal('memberModal');
  await Promise.all([loadMembers(), loadBalances()]);
  renderMemberTabs(); renderOverview(); renderSummaryBar();
}

// ── Confirm charge modal ──────────────────────────────────
async function openConfirmChargeModal() {
  const now    = new Date();
  const curMon = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}`;
  const activeCount = _members.filter(m => m.is_active).length;

  // Fetch suggestions
  const r = await fetch('/api/spotify/charges/suggestions');
  const d = await r.json();
  const suggestions = (d.suggestions || []);
  _pendingSuggestion = suggestions[0] || null;

  const box = document.getElementById('chargeSuggestionBox');
  if (_pendingSuggestion) {
    box.innerHTML = `<strong>עסקה מוצעת:</strong> ${_pendingSuggestion.name} — ₪${_pendingSuggestion.amount.toFixed(2)} (${_pendingSuggestion.date})`;
    document.getElementById('chargeAmount').value = _pendingSuggestion.amount;
  } else {
    box.innerHTML = '<span style="color:var(--text-muted);">לא נמצאה עסקת Spotify אוטומטית — הכנס ידנית.</span>';
  }

  document.getElementById('chargeMonth').value       = curMon;
  document.getElementById('chargeMemberCount').value = activeCount;
  openModal('chargeModal');
}

async function submitCharge() {
  const month       = document.getElementById('chargeMonth').value;
  const amount      = parseFloat(document.getElementById('chargeAmount').value);
  const memberCount = parseInt(document.getElementById('chargeMemberCount').value);
  if (!month || !amount || !memberCount) { alert('נא למלא את כל השדות'); return; }
  await fetch('/api/spotify/charges', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({month, total_amount: amount, member_count: memberCount, tx_id: _pendingSuggestion ? _pendingSuggestion.tx_id : null, confirmed: 1})
  });
  closeModal('chargeModal');
  document.getElementById('chargeBanner').style.display = 'none';
  await loadCharges();
  renderSummaryBar();
  // Re-render open member tab if any
  if (_activeTab.startsWith('member-')) {
    const mid = parseInt(_activeTab.split('-')[1]);
    renderMemberDetail(mid);
  }
}

// ── Export PDF modal ──────────────────────────────────────
function openExportModal() {
  const sel = document.getElementById('exportMemberSelect');
  sel.innerHTML = _members.filter(m => !m.is_exempt && m.is_active)
    .map(m => `<option value="${m.id}">${m.name}</option>`).join('');
  openModal('exportModal');
}

function toggleExportPicker(show) {
  document.getElementById('exportPickerRow').style.display = show ? 'flex' : 'none';
}

function doExportPDF() {
  const mode = document.querySelector('input[name="exportMode"]:checked').value;
  let url = '/api/spotify/report?member_id=all';
  if (mode === 'single') {
    const mid = document.getElementById('exportMemberSelect').value;
    url = `/api/spotify/report?member_id=${mid}`;
  }
  window.open(url, '_blank');
  closeModal('exportModal');
}

// ── Modal helpers ─────────────────────────────────────────
function openModal(id)  { document.getElementById(id).classList.add('open'); }
function closeModal(id) { document.getElementById(id).classList.remove('open'); }

// ── Boot ──────────────────────────────────────────────────
init();
</script>
</body>
</html>
```

- [ ] **Step 2: Verify the page loads**

Start the server: `python AppManager.py`

Open `http://localhost:5050/spotify` in the browser.

Expected: Page loads with the Spotify Tracker UI, top summary bar shows dashes, "📋 סקירה כללית" tab is active with empty member grid.

- [ ] **Step 3: Smoke-test core interactions**

1. Click "+ חבר" → modal opens → enter a name → click "שמור" → member tab appears
2. Open the sidebar → "Spotify Tracker" entry is active
3. Click "📄 ייצוא PDF" → export modal opens with radio buttons

- [ ] **Step 4: Commit**

```bash
git add source/html/SpotifyTracker.html
git commit -m "feat(spotify): add SpotifyTracker.html frontend page"
```

---

## Task 7: Add Sidebar Entry to All Pages

**Files:**
- Modify: `source/html/output.html:1549`
- Modify: `source/html/Bills.html:686`
- Modify: `source/html/Search.html:272`
- Modify: `source/html/Tagger.html:698`
- Modify: `source/html/Files.html:569`

- [ ] **Step 1: output.html — insert after the /search nav-item**

Find:
```html
    <a class="nav-item" href="/search">
     חיפוש
    </a>
    <div class="nav-sep">
```

Replace with:
```html
    <a class="nav-item" href="/search">
     חיפוש
    </a>
    <a class="nav-item" href="/spotify">
     Spotify Tracker
    </a>
    <div class="nav-sep">
```

- [ ] **Step 2: Bills.html — insert after the /search nav-link**

Find:
```html
    <a class="nav-link" href="/search">חיפוש</a>
```

Replace with:
```html
    <a class="nav-link" href="/search">חיפוש</a>
    <a class="nav-link" href="/spotify">Spotify Tracker</a>
```

- [ ] **Step 3: Search.html — insert after the /search nav-item**

Find:
```html
    <a class="nav-item" href="/search">חיפוש</a>
```

Replace with:
```html
    <a class="nav-item" href="/search">חיפוש</a>
    <a class="nav-item" href="/spotify">Spotify Tracker</a>
```

- [ ] **Step 4: Tagger.html — insert after the /search nav-item**

Find:
```html
    <a class="nav-item" href="/search">חיפוש</a>
```

Replace with:
```html
    <a class="nav-item" href="/search">חיפוש</a>
    <a class="nav-item" href="/spotify">Spotify Tracker</a>
```

- [ ] **Step 5: Files.html — insert after the /search nav-item**

Find:
```html
    <a class="nav-item" href="/search">חיפוש</a>
```

Replace with:
```html
    <a class="nav-item" href="/search">חיפוש</a>
    <a class="nav-item" href="/spotify">Spotify Tracker</a>
```

- [ ] **Step 6: Verify sidebar appears on all pages**

Open each of these URLs and check the sidebar contains "Spotify Tracker":
- `http://localhost:5050/` (output.html)
- `http://localhost:5050/bills`
- `http://localhost:5050/search`
- `http://localhost:5050/tagger`
- `http://localhost:5050/files`

- [ ] **Step 7: Commit**

```bash
git add source/html/output.html source/html/Bills.html source/html/Search.html source/html/Tagger.html source/html/Files.html
git commit -m "feat(spotify): add Spotify Tracker sidebar entry to all nav pages"
```

---

## Task 8: End-to-End Integration Test

**Files:**
- Modify: `source/Testing/test_spotify_tracker.py`

- [ ] **Step 1: Add end-to-end test for full balance flow**

Append to `source/Testing/test_spotify_tracker.py`:

```python
def test_full_balance_flow():
    from SpotifyTracker import compute_all_balances
    db = DataBase()

    # Setup: 3 members (1 exempt, 2 paying), 2 months of charges
    db.cursor.execute("DELETE FROM SpotifyMemberPayments WHERE Member_ID IN (SELECT ID FROM SpotifyMembers WHERE Name LIKE 'E2E_%')")
    db.cursor.execute("DELETE FROM SpotifyMembers WHERE Name LIKE 'E2E_%'")
    db.cursor.execute("DELETE FROM SpotifyMonthlyCharge WHERE Month IN ('2099-03','2099-04')")
    db.commit_changes()

    owner_id = db.add_spotify_member('E2E_Owner', is_exempt=1)
    alice_id = db.add_spotify_member('E2E_Alice', is_exempt=0)
    bob_id   = db.add_spotify_member('E2E_Bob',   is_exempt=0)

    # 2 months, 3 members → share = 120/3 = 40 per person
    db.add_spotify_charge('2099-03', total_amount=120.0, member_count=3, confirmed=1)
    db.add_spotify_charge('2099-04', total_amount=120.0, member_count=3, confirmed=1)

    # Alice pays for both months (80 total — even)
    db.add_spotify_payment(alice_id, 80.0, '2099-03-10')

    # Bob pays only once (40 — owes 1 month)
    db.add_spotify_payment(bob_id, 40.0, '2099-03-15')

    balances = compute_all_balances(db)
    bal_by_name = {b['name']: b for b in balances}

    assert 'E2E_Owner' not in bal_by_name, "Exempt member must not appear in balances"
    assert bal_by_name['E2E_Alice']['status'] == 'even',  f"Alice should be even, got {bal_by_name['E2E_Alice']}"
    assert bal_by_name['E2E_Bob']['status']   == 'owes',  f"Bob should owe, got {bal_by_name['E2E_Bob']}"
    assert bal_by_name['E2E_Bob']['months_status'] == -1, f"Bob should owe 1 month, got {bal_by_name['E2E_Bob']['months_status']}"

    # Cleanup
    db.cursor.execute("DELETE FROM SpotifyMemberPayments WHERE Member_ID IN (?,?)", (alice_id, bob_id))
    db.cursor.execute("DELETE FROM SpotifyMembers WHERE ID IN (?,?,?)", (owner_id, alice_id, bob_id))
    db.cursor.execute("DELETE FROM SpotifyMonthlyCharge WHERE Month IN ('2099-03','2099-04')")
    db.commit_changes()
    print("PASS: full balance flow e2e")


if __name__ == '__main__':
    test_spotify_tables_exist()
    test_member_crud()
    test_charge_crud()
    test_payment_crud()
    test_compute_balance_owes()
    test_compute_balance_ahead()
    test_compute_balance_even()
    test_full_balance_flow()
    print("\nAll tests passed ✓")
```

- [ ] **Step 2: Run all tests**

```bash
cd source && python Testing/test_spotify_tracker.py
```

Expected:
```
PASS: all Spotify tables exist
PASS: member CRUD
PASS: charge CRUD
PASS: payment CRUD
PASS: compute_balance owes
PASS: compute_balance ahead
PASS: compute_balance even
PASS: full balance flow e2e

All tests passed ✓
```

- [ ] **Step 3: Commit**

```bash
git add source/Testing/test_spotify_tracker.py
git commit -m "test(spotify): add full integration test suite for Spotify Tracker"
```
