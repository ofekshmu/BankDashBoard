# Landing Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the marketing landing page (`/`) with a sign-in gate followed by a Hebrew RTL KPI dashboard: one block per menu item, 11 of them with one live headline KPI from `GET /api/landing/<block>`.

**Architecture:** Pure builders in `source/landing_service.py` turn raw data into a block dict. Loaders fetch the raw data: most live in `source/landing_loaders.py`. Three of them (monthly, accounts, housing) need WebApp internals, so they are registered from `WebApp.py`. A blueprint, `source/routes/landing_routes.py`, holds the loader registry, serves `/api/landing/<block>` with a 5-minute cache per block and keeps a failure in one block from affecting the others. `index.html` is rewritten as the gate plus the dashboard.

**Tech Stack:** Flask blueprints, psycopg2 via the `DataBase()` singleton, pytest, vanilla JS/CSS, Playwright for headless checks.

**Spec:** `docs/superpowers/specs/2026-10-04-landing-dashboard-design.md`

## Global Constraints

- Branch `Dev/GeneralFeatures`. Never switch branch.
- Every commit bumps the patch in `/VERSION` (CRLF line ending: `printf '1.25.6\r\n' > VERSION`). The final task sets `1.26.0`.
- Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
- Run tests with global Python 3.10 from the repo root: `python -m pytest tests/<file> -q`. The root `conftest.py` puts both `.` and `source/` on `sys.path`. Do NOT use `venv/`.
- No `/api/landing/*` path may be added to `_PUBLIC_PATHS`. The global `_require_auth` returns 401 for these paths when the session is missing.
- Never define a route twice. Before registering, run `grep -n "api/landing" source/WebApp.py` and expect no match.
- Palette: navy `#1e2a4a`, teal `#1e9d8b`, bg `#f4f6f9`, white cards, 16px radius. RTL Hebrew. Tabular numerals for KPIs.
- Money format: `money(v)` → `'12,345₪'` (rounded, minus sign for negatives). Percent: `pct(v)` → `'+4.2%'` / `'-1.3%'`.
- Block JSON: `{ok: true, dot: 'green'|'amber'|'red'|'grey'|null, kpi: str, caption: str, details: [str, …], extra: {…}}`; failure: `{ok: false, error: str}` with HTTP 500. Unknown block: 404.
- `details` holds at most 3 lines. Bills is the exception at 5, because the user asked for "the most common 5".
- Before touching the network, the page shows only the sign-in popup. `#dash` keeps the `hidden` attribute until authenticated.
- After every code change: clear `source/**/__pycache__`, restart the Flask preview ("BankDash", port 5050) and check `curl http://localhost:5050/api/version`.

---

## File Structure

| File | Responsibility |
|---|---|
| `source/landing_service.py` (create) | Formatting helpers + one pure `build_<block>()` per block; no I/O |
| `source/landing_loaders.py` (create) | DB-backed loaders `load_<block>(today)` for cards, timeline, bills, spotify, plants, recurring, tagger, files + `register_default_loaders()` |
| `source/routes/landing_routes.py` (create) | Blueprint `landing_bp`, `BLOCKS`, `LOADERS`, `register_loader()`, cache, error isolation |
| `source/WebApp.py` (modify, next to `plants_bp` registration ~line 5918) | Register blueprint + default loaders + monthly/accounts/housing loaders |
| `index.html` (rewrite) | Gate + KPI dashboard |
| `tests/test_landing_service.py` (create) | Builder unit tests |
| `tests/test_landing_loaders.py` (create) | Loader tests against a fake DB cursor |
| `tests/test_landing_routes.py` (create) | Blueprint tests |
| `docs/superpowers/specs/2026-10-04-landing-dashboard-design.md` (modify) | Block JSON shape = kpi/caption/details; bills shows all 5 |

---

### Task 1: Builders — formatting + monthly, accounts, cards, housing

**Files:**
- Create: `source/landing_service.py`
- Test: `tests/test_landing_service.py`

**Interfaces:**
- Produces: `money(v)->str`, `pct(v)->str`, `as_date(v)->date|None`, `short_date(v)->str`, `month_label('YYYY_MM')->str`, `block(kpi, caption, details=(), dot=None, extra=None)->dict`, `cap(lines, n=3)->list`, `pick_month(months, today)->str|None`, `build_monthly(months, key, payload)`, `accounts_total(accounts, cash_map, rates)->float|None`, `build_accounts(payload, cash_map, rates, today)`, `build_cards(cards)`, `build_housing(mortgage)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_landing_service.py
from datetime import date, datetime

import landing_service as ls

TODAY = date(2026, 10, 4)


# ── helpers ────────────────────────────────────────────────────────────────
def test_money_and_pct():
    assert ls.money(12345.6) == '12,346₪'
    assert ls.money(-50.4) == '-50₪'
    assert ls.money(None) == '0₪'
    assert ls.pct(4.21) == '+4.2%'
    assert ls.pct(-1.26) == '-1.3%'
    assert ls.pct(0) == '+0.0%'


def test_dates():
    assert ls.as_date('2026-09-10') == date(2026, 9, 10)
    assert ls.as_date('2026-09-10T08:00:00') == date(2026, 9, 10)
    assert ls.as_date(datetime(2026, 9, 10, 8)) == date(2026, 9, 10)
    assert ls.as_date('') is None and ls.as_date('junk') is None
    assert ls.short_date('2026-09-10') == '10.09.26'
    assert ls.month_label('2026_10') == 'אוקטובר 2026'


def test_cap():
    assert ls.cap(['a', 'b']) == ['a', 'b']
    assert ls.cap(['a', 'b', 'c', 'd', 'e']) == ['a', 'b', '+3 נוספים']


def test_block_shape():
    b = ls.block('3', 'cap', ['x', None, ''], dot='red')
    assert b == {'ok': True, 'dot': 'red', 'kpi': '3', 'caption': 'cap', 'details': ['x'], 'extra': {}}


# ── monthly ────────────────────────────────────────────────────────────────
MONTHS = [{'key': '2026_08'}, {'key': '2026_09'}, {'key': '2026_10'}]


def test_pick_month_prefers_today_else_latest():
    assert ls.pick_month(MONTHS, TODAY) == '2026_10'
    assert ls.pick_month(MONTHS[:2], TODAY) == '2026_09'
    assert ls.pick_month([], TODAY) is None


def test_monthly_counts_both_alert_lists_and_dots():
    b = ls.build_monthly(MONTHS, '2026_10', {'alerts': [1, 2], 'organizer_alerts': [3]})
    assert b['kpi'] == '3' and b['dot'] == 'red' and b['caption'] == 'התראות באוקטובר 2026'
    assert ls.build_monthly(MONTHS, '2026_10', {'alerts': [], 'organizer_alerts': None})['dot'] == 'green'
    assert ls.build_monthly(MONTHS, '2026_10', {'alerts': [1, 2]})['dot'] == 'amber'


def test_monthly_extra_lists_months_newest_first():
    b = ls.build_monthly(MONTHS, '2026_10', {'alerts': []})
    assert b['extra']['current'] == '2026_10'
    assert [m['key'] for m in b['extra']['months']] == ['2026_10', '2026_09', '2026_08']
    assert b['extra']['months'][0]['label'] == 'אוקטובר 2026'


def test_monthly_no_data():
    b = ls.build_monthly(MONTHS, '2026_10', None)
    assert b['dot'] == 'grey' and b['kpi'] == '—' and 'אוקטובר' in b['caption']
    assert ls.build_monthly([], None, None)['dot'] == 'grey'


# ── accounts ───────────────────────────────────────────────────────────────
ACCTS = {'accounts': {
    'Main Bank': [['2026-09-10', 20000.0]],
    'Cash': [['2026-09-26', 4000.0]],
    'Old': [['2026-07-01', 500.0]],
    'Closed': [['2026-01-01', 0]],
    'Total': [['2026-09-01', 1.0], ['2026-09-26', 24500.0]],
}}


def test_accounts_total_matches_page_cash_adjustment():
    # page: Total + (sum(round(balance * rate)) - Cash last value)
    total = ls.accounts_total(ACCTS['accounts'], {'ILS': 3000, 'USD': 1000}, {'USD': 3.7})
    assert total == 24500 + (3000 + 3700 - 4000)
    assert ls.accounts_total(ACCTS['accounts'], None, {}) == 24500
    assert ls.accounts_total({}, {}, {}) is None


def test_accounts_block_lists_stale_accounts():
    b = ls.build_accounts(ACCTS, None, {}, TODAY)
    assert b['kpi'] == '24,500₪' and b['caption'] == 'שווי כל החשבונות'
    assert b['dot'] == 'amber' and b['details'] == ['Old · עודכן 01.07.26']   # zero-balance 'Closed' skipped


def test_accounts_block_all_fresh_and_empty():
    fresh = {'accounts': {'A': [['2026-10-01', 5]], 'Total': [['2026-10-01', 5]]}}
    b = ls.build_accounts(fresh, None, {}, TODAY)
    assert b['dot'] == 'green' and b['details'] == ['כל החשבונות מעודכנים']
    assert ls.build_accounts(None, None, {}, TODAY)['dot'] == 'grey'


# ── cards ──────────────────────────────────────────────────────────────────
def test_cards_counts_active_and_lists_top3():
    cards = [{'card_id': '1111', 'network': 'Visa', 'current_charge': 100},
             {'card_id': '2222', 'network': 'Max', 'current_charge': 900},
             {'card_id': '3333', 'network': 'Isracard', 'current_charge': 0},
             {'card_id': '4444', 'network': '', 'current_charge': 50},
             {'card_id': '5555', 'network': 'Visa', 'current_charge': 10}]
    b = ls.build_cards(cards)
    assert b['kpi'] == '4' and b['caption'] == 'כרטיסים פעילים החודש' and b['dot'] is None
    assert b['details'] == ['Max ·2222 · 900₪', 'Visa ·1111 · 100₪', '·4444 · 50₪']


def test_cards_none_active():
    b = ls.build_cards([{'card_id': '1', 'current_charge': 0}])
    assert b['kpi'] == '0' and b['dot'] == 'grey'


# ── housing ────────────────────────────────────────────────────────────────
def test_housing_block():
    m = {'annual_return_pct': 4.21, 'total_return_pct': 31.0, 'default_rate': 5,
         'equity_appreciated': 500000, 'alltime_income': 120000, 'net_invested': 400000}
    b = ls.build_housing(m)
    assert b['kpi'] == '+4.2%' and b['caption'] == 'תשואה שנתית (5% עליית ערך)' and b['dot'] == 'green'
    assert b['details'] == ['תשואה כוללת במכירה +31.0%', 'רווח נקי 220,000₪']
    assert ls.build_housing(dict(m, annual_return_pct=-2))['dot'] == 'red'
    assert ls.build_housing({})['dot'] == 'grey'
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_landing_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'landing_service'`

- [ ] **Step 3: Implement**

```python
# source/landing_service.py
"""Landing dashboard — one pure builder per KPI block.

Every builder turns raw data (loaded by landing_loaders.py or WebApp.py) into
{ok, dot, kpi, caption, details, extra}. Nothing here touches the DB, so each
block is unit-testable with plain dicts and lists.
"""
from datetime import date, datetime

HEB_MONTHS = ('ינואר', 'פברואר', 'מרץ', 'אפריל', 'מאי', 'יוני',
              'יולי', 'אוגוסט', 'ספטמבר', 'אוקטובר', 'נובמבר', 'דצמבר')
STALE_DAYS = 30          # same threshold as the accounts page (_STALE_DAYS)
MAX_DETAILS = 3


# ── Formatting ─────────────────────────────────────────────────────────────
def money(v):
    n = round(float(v or 0))
    return ('-' if n < 0 else '') + f'{abs(n):,}₪'


def pct(v):
    v = float(v)
    return ('+' if v >= 0 else '') + f'{v:.1f}%'


def as_date(v):
    if v is None or v == '':
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def short_date(v):
    d = as_date(v)
    return f'{d.day:02d}.{d.month:02d}.{d.year % 100:02d}' if d else ''


def month_label(key):
    return f'{HEB_MONTHS[int(key[5:7]) - 1]} {int(key[:4])}'


def block(kpi, caption, details=(), dot=None, extra=None):
    return {'ok': True, 'dot': dot, 'kpi': kpi, 'caption': caption,
            'details': [d for d in details if d], 'extra': extra or {}}


def cap(lines, n=MAX_DETAILS):
    """At most n lines; the last one becomes '+K נוספים' when lines are dropped."""
    lines = list(lines)
    return lines if len(lines) <= n else lines[:n - 1] + [f'+{len(lines) - n + 1} נוספים']


# ── Monthly analysis ───────────────────────────────────────────────────────
def pick_month(months, today):
    """Today's month when it has data, else the latest month with data."""
    keys = sorted(m['key'] for m in months or [] if m.get('key'))
    if not keys:
        return None
    k = f'{today.year:04d}_{today.month:02d}'
    return k if k in keys else keys[-1]


def build_monthly(months, key, payload):
    keys = sorted({m['key'] for m in months or [] if m.get('key')}, reverse=True)
    extra = {'months': [{'key': k, 'label': month_label(k)} for k in keys], 'current': key}
    if not key:
        return block('—', 'אין ניתוחים חודשיים', dot='grey', extra=extra)
    if payload is None:
        return block('—', f'אין ניתוח ל{month_label(key)}', dot='grey', extra=extra)
    n = len(payload.get('alerts') or []) + len(payload.get('organizer_alerts') or [])
    dot = 'green' if n == 0 else ('amber' if n <= 2 else 'red')
    return block(str(n), f'התראות ב{month_label(key)}', dot=dot, extra=extra)


# ── Accounts ───────────────────────────────────────────────────────────────
def accounts_total(accounts, cash_map, rates):
    """Same figure as the accounts page grand total: the Total series' last point,
    with the Cash account replaced by the cash-by-currency total in ILS."""
    total = (accounts or {}).get('Total') or []
    if not total:
        return None
    value = float(total[-1][1] or 0)
    cash = accounts.get('Cash') or []
    if cash_map is not None and cash:
        ils = sum(round(float(bal) * float((rates or {}).get(cur) or 1.0)) for cur, bal in cash_map.items())
        value += ils - float(cash[-1][1] or 0)
    return value


def _stale_accounts(accounts, today):
    out = []
    for name, series in (accounts or {}).items():
        if name == 'Total' or not series or not series[-1][1]:
            continue
        d = as_date(series[-1][0])
        if d and (today - d).days > STALE_DAYS:
            out.append((d, name))
    return sorted(out)


def build_accounts(payload, cash_map, rates, today):
    accounts = (payload or {}).get('accounts') or {}
    total = accounts_total(accounts, cash_map, rates)
    if total is None:
        return block('—', 'שווי כל החשבונות', dot='grey')
    stale = _stale_accounts(accounts, today)
    details = cap(f'{name} · עודכן {short_date(d)}' for d, name in stale) or ['כל החשבונות מעודכנים']
    return block(money(total), 'שווי כל החשבונות', details, dot='amber' if stale else 'green')


# ── Cards ──────────────────────────────────────────────────────────────────
def build_cards(cards):
    active = sorted((c for c in cards or [] if float(c.get('current_charge') or 0) > 0),
                    key=lambda c: -float(c['current_charge']))
    details = [f"{(c.get('network') or '').strip()} ·{c.get('card_id')} · {money(c['current_charge'])}".strip()
               for c in active[:MAX_DETAILS]]
    return block(str(len(active)), 'כרטיסים פעילים החודש', details, dot=None if active else 'grey')


# ── Housing ────────────────────────────────────────────────────────────────
def build_housing(m):
    m = m or {}
    if m.get('annual_return_pct') is None:
        return block('—', 'תשואה שנתית', dot='grey')
    rate = m.get('default_rate', 5)
    rate = int(rate) if float(rate).is_integer() else rate
    profit = (m.get('equity_appreciated') or 0) + (m.get('alltime_income') or 0) - (m.get('net_invested') or 0)
    details = [f"תשואה כוללת במכירה {pct(m['total_return_pct'])}" if m.get('total_return_pct') is not None else None,
               f'רווח נקי {money(profit)}']
    return block(pct(m['annual_return_pct']), f'תשואה שנתית ({rate}% עליית ערך)', details,
                 dot='green' if m['annual_return_pct'] >= 0 else 'red')
```

- [ ] **Step 4: Run tests — expect PASS**

Run: `python -m pytest tests/test_landing_service.py -q`

- [ ] **Step 5: Commit** (bump VERSION 1.25.5 → 1.25.6)

```bash
printf '1.25.6\r\n' > VERSION
git add source/landing_service.py tests/test_landing_service.py VERSION
git commit -m "feat(landing): KPI builders for monthly, accounts, cards, housing

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Builders — timeline, bills, spotify, plants, recurring, tagger, files

**Files:**
- Modify: `source/landing_service.py` (append)
- Test: `tests/test_landing_service.py` (append)

**Interfaces:**
- Consumes: `block`, `cap`, `money`, `short_date`, `as_date` from Task 1.
- Produces: `build_timeline(event)`, `bill_averages(rows)->list[(name, avg)]`, `build_bills(rows)`, `build_spotify(members)`, `build_plants(summary)`, `build_recurring(groups, today)`, `build_tagger(tx)`, `build_files(f)`.
  - `event`: dict `{name, event_date, created_at}` or None
  - `rows` (bills): list of `(type_id, name, start_month 'YYYY-MM', end_month 'YYYY-MM'|None, amount)` (fillers already excluded)
  - `members`: list of `{name, balance}` (negative = owes)
  - `summary`: plants `{due_today, overdue, auto_pending_confirm, …}`
  - `groups`: recurring groups `{name, current_amount, next_expected, possibly_stopped}`
  - `tx`: tagger dict `{name, exec_date, charge_value, transaction_value, category}` or None
  - `f`: file dict `{file_name, format, date, last_update}` or None

- [ ] **Step 1: Append failing tests**

```python
# ── timeline ───────────────────────────────────────────────────────────────
def test_timeline():
    b = ls.build_timeline({'name': 'חתונה', 'event_date': '2026-11-02', 'created_at': datetime(2026, 10, 1)})
    assert b['kpi'] == 'חתונה' and b['caption'] == 'האירוע האחרון שנוצר' and b['details'] == ['02.11.26']
    assert ls.build_timeline(None)['dot'] == 'grey'


# ── bills ──────────────────────────────────────────────────────────────────
BILL_ROWS = [
    (1, 'חשמל', '2026-01', '2026-02', 600),     # 2 months → 300/month
    (1, 'חשמל', '2026-03', '2026-04', 400),     # avg over 4 months = 250
    (1, 'חשמל', '2026-05', None, 250),          # single month → total 1250 / 5 = 250
    (2, 'מים', '2026-01', '2026-02', 200),
    (2, 'מים', '2026-03', '2026-04', 100),      # 300 / 4 = 75
    (3, 'ארנונה', '2026-01', '2026-01', 500),
    (4, 'גז', '2026-01', '2026-01', 50),
    (5, 'אינטרנט', '2026-01', '2026-01', 100),
    (6, 'ועד', '2026-01', '2026-01', 30),
    (7, 'סלולר', '2026-01', '2026-01', 60),
]


def test_bill_averages_top5_by_entry_count():
    avgs = ls.bill_averages(BILL_ROWS)
    assert avgs[0] == ('חשמל', 250) and avgs[1] == ('מים', 75)
    assert len(avgs) == 5                     # top 5 types by entry count (ties → name)


def test_bills_block_shows_all_five():
    b = ls.build_bills(BILL_ROWS)
    assert b['caption'] == 'ממוצע חודשי — 5 החשבונות הנפוצים'
    assert len(b['details']) == 5 and b['details'][0] == 'חשמל · 250₪'
    assert b['kpi'] == ls.money(sum(a for _, a in ls.bill_averages(BILL_ROWS)))
    assert ls.build_bills([])['dot'] == 'grey'


# ── spotify ────────────────────────────────────────────────────────────────
def test_spotify_only_debtors():
    b = ls.build_spotify([{'name': 'דנה', 'balance': -30}, {'name': 'יוסי', 'balance': 20},
                          {'name': 'רון', 'balance': -60}])
    assert b['kpi'] == '90₪' and b['caption'] == 'חובות פתוחים' and b['dot'] == 'amber'
    assert b['details'] == ['רון · 60₪', 'דנה · 30₪']


def test_spotify_caps_and_no_debt():
    many = [{'name': f'm{i}', 'balance': -10 - i} for i in range(5)]
    assert ls.build_spotify(many)['details'][-1] == '+3 נוספים'
    b = ls.build_spotify([{'name': 'יוסי', 'balance': 0}])
    assert b['kpi'] == '0₪' and b['dot'] == 'green' and b['details'] == ['אין חובות']


# ── plants ─────────────────────────────────────────────────────────────────
def test_plants():
    b = ls.build_plants({'due_today': 2, 'overdue': 1, 'auto_pending_confirm': 3})
    assert b['kpi'] == '3' and b['caption'] == 'עציצים להשקיה' and b['dot'] == 'red'
    assert b['details'] == ['1 באיחור', '3 השקיות אוטומטיות ממתינות לאישור']
    assert ls.build_plants({'due_today': 0, 'overdue': 0, 'auto_pending_confirm': 1})['dot'] == 'amber'
    assert ls.build_plants({'due_today': 0, 'overdue': 0, 'auto_pending_confirm': 0})['dot'] == 'green'


# ── recurring ──────────────────────────────────────────────────────────────
def test_recurring_next_upcoming_non_stopped():
    groups = [{'name': 'נטפליקס', 'current_amount': 55, 'next_expected': '2026-10-09', 'possibly_stopped': False},
              {'name': 'חדר כושר', 'current_amount': 199, 'next_expected': '2026-10-05', 'possibly_stopped': True},
              {'name': 'ביטוח', 'current_amount': 310.4, 'next_expected': date(2026, 10, 6), 'possibly_stopped': False},
              {'name': 'ישן', 'current_amount': 10, 'next_expected': '2026-09-01', 'possibly_stopped': False}]
    b = ls.build_recurring(groups, TODAY)
    assert b['kpi'] == '310₪' and b['caption'] == 'ביטוח · ב-06.10.26'
    assert ls.build_recurring([], TODAY)['dot'] == 'grey'


# ── tagger ─────────────────────────────────────────────────────────────────
def test_tagger():
    tx = {'name': 'שופרסל', 'exec_date': '2026-10-02', 'charge_value': 212.5,
          'transaction_value': 300, 'category': 'סופר'}
    b = ls.build_tagger(tx)
    assert b['kpi'] == '212₪' and b['caption'] == 'שופרסל' and b['details'] == ['סופר · 02.10.26']
    assert ls.build_tagger(dict(tx, charge_value=None))['kpi'] == '300₪'
    assert ls.build_tagger(None)['dot'] == 'grey'


# ── files ──────────────────────────────────────────────────────────────────
def test_files():
    b = ls.build_files({'file_name': 'leumi_10.xlsx', 'format': 'Leumi Bank',
                        'date': '2026-10-01', 'last_update': datetime(2026, 10, 3, 9)})
    assert b['kpi'] == '03.10.26' and b['caption'] == 'קובץ אחרון'
    assert b['details'] == ['leumi_10.xlsx', 'Leumi Bank']
    assert ls.build_files(None)['dot'] == 'grey'
```

- [ ] **Step 2: Run — expect FAIL** (`AttributeError: module 'landing_service' has no attribute 'build_timeline'`)

Run: `python -m pytest tests/test_landing_service.py -q`

- [ ] **Step 3: Append implementation to `source/landing_service.py`**

```python
# ── Timeline ───────────────────────────────────────────────────────────────
def build_timeline(event):
    if not event:
        return block('—', 'אין אירועים', dot='grey')
    return block(event['name'], 'האירוע האחרון שנוצר', [short_date(event.get('event_date'))])


# ── Bills ──────────────────────────────────────────────────────────────────
TOP_BILLS = 5


def _months_covered(start, end):
    s = as_date(f'{start}-01')
    e = as_date(f'{end or start}-01') or s
    return max(1, (e.year - s.year) * 12 + e.month - s.month + 1)


def bill_averages(rows):
    """[(name, average per month)] for the TOP_BILLS types with the most entries."""
    by_type = {}
    for type_id, name, start, end, amount in rows or []:
        t = by_type.setdefault(type_id, {'name': name, 'n': 0, 'total': 0.0, 'months': 0})
        t['n'] += 1
        t['total'] += float(amount or 0)
        t['months'] += _months_covered(start, end)
    top = sorted(by_type.values(), key=lambda t: (-t['n'], t['name']))[:TOP_BILLS]
    return [(t['name'], t['total'] / t['months']) for t in top]


def build_bills(rows):
    avgs = bill_averages(rows)
    if not avgs:
        return block('—', 'אין חשבונות', dot='grey')
    return block(money(sum(a for _, a in avgs)), f'ממוצע חודשי — {len(avgs)} החשבונות הנפוצים',
                 [f'{name} · {money(a)}' for name, a in avgs])


# ── Spotify ────────────────────────────────────────────────────────────────
def build_spotify(members):
    debtors = sorted((m for m in members or [] if float(m.get('balance') or 0) < 0),
                     key=lambda m: float(m['balance']))
    owed = -sum(float(m['balance']) for m in debtors)
    details = cap(f"{m['name']} · {money(-float(m['balance']))}" for m in debtors) or ['אין חובות']
    return block(money(owed), 'חובות פתוחים', details, dot='amber' if debtors else 'green')


# ── Plants ─────────────────────────────────────────────────────────────────
def build_plants(summary):
    s = summary or {}
    due, overdue, pending = s.get('due_today', 0), s.get('overdue', 0), s.get('auto_pending_confirm', 0)
    dot = 'red' if overdue else ('amber' if due or pending else 'green')
    details = [f'{overdue} באיחור' if overdue else None,
               f'{pending} השקיות אוטומטיות ממתינות לאישור' if pending else None]
    return block(str(due + overdue), 'עציצים להשקיה', details, dot=dot)


# ── Recurring charges ──────────────────────────────────────────────────────
def build_recurring(groups, today):
    upcoming = [(as_date(g.get('next_expected')), g) for g in groups or [] if not g.get('possibly_stopped')]
    upcoming = sorted(((d, g) for d, g in upcoming if d and d >= today), key=lambda x: x[0])
    if not upcoming:
        return block('—', 'אין חיובים צפויים', dot='grey')
    d, g = upcoming[0]
    return block(money(g.get('current_amount')), f"{g['name']} · ב-{short_date(d)}")


# ── Tagger ─────────────────────────────────────────────────────────────────
def build_tagger(tx):
    if not tx:
        return block('—', 'עוד לא תויגו עסקאות', dot='grey')
    amount = tx.get('charge_value')
    if amount is None:
        amount = tx.get('transaction_value')
    details = [' · '.join(x for x in (tx.get('category'), short_date(tx.get('exec_date'))) if x)]
    return block(money(amount), tx.get('name') or '', details)


# ── Files ──────────────────────────────────────────────────────────────────
def build_files(f):
    if not f:
        return block('—', 'אין קבצים', dot='grey')
    return block(short_date(f.get('last_update') or f.get('date')), 'קובץ אחרון',
                 [f.get('file_name'), f.get('format')])
```

- [ ] **Step 4: Run — expect PASS**

Run: `python -m pytest tests/test_landing_service.py -q`

- [ ] **Step 5: Commit** (VERSION → 1.25.7)

```bash
printf '1.25.7\r\n' > VERSION
git add source/landing_service.py tests/test_landing_service.py VERSION
git commit -m "feat(landing): KPI builders for timeline, bills, spotify, plants, recurring, tagger, files

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Blueprint — registry, cache, error isolation

**Files:**
- Create: `source/routes/landing_routes.py`
- Test: `tests/test_landing_routes.py`

**Interfaces:**
- Produces: `landing_bp` (Blueprint), `BLOCKS` (tuple of 11 names, menu order), `LOADERS` (dict), `register_loader(name, fn)` where `fn(today: date) -> block dict`, `clear_cache()`, `CACHE_TTL = 300`, `_server_today()` (monkeypatchable).

- [ ] **Step 1: Write failing tests**

```python
# tests/test_landing_routes.py
from datetime import date

import pytest
from flask import Flask

from routes import landing_routes as lr


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(lr, 'LOADERS', {})
    monkeypatch.setattr(lr, '_server_today', lambda: date(2026, 10, 4))
    lr.clear_cache()
    app = Flask(__name__)
    app.register_blueprint(lr.landing_bp)
    return app.test_client()


def test_blocks_are_the_eleven_live_blocks():
    assert lr.BLOCKS == ('monthly', 'accounts', 'cards', 'housing', 'timeline', 'bills',
                         'spotify', 'plants', 'recurring', 'tagger', 'files')


def test_ok_block_passes_today_and_returns_json(client):
    seen = []
    lr.register_loader('plants', lambda today: seen.append(today) or {'ok': True, 'kpi': '2'})
    r = client.get('/api/landing/plants')
    assert r.status_code == 200 and r.get_json()['kpi'] == '2' and seen == [date(2026, 10, 4)]


def test_unknown_block_404(client):
    assert client.get('/api/landing/nope').status_code == 404


def test_block_without_loader_is_an_isolated_failure(client):
    r = client.get('/api/landing/files')
    assert r.status_code == 500 and r.get_json() == {'ok': False, 'error': 'לא זמין כרגע'}


def test_failing_block_does_not_affect_another(client):
    lr.register_loader('cards', lambda today: 1 / 0)
    lr.register_loader('bills', lambda today: {'ok': True, 'kpi': '5'})
    assert client.get('/api/landing/cards').status_code == 500
    assert client.get('/api/landing/bills').get_json()['kpi'] == '5'


def test_cache_for_ttl_and_failures_not_cached(client, monkeypatch):
    calls = []
    lr.register_loader('timeline', lambda today: calls.append(1) or {'ok': True, 'kpi': str(len(calls))})
    now = [1000.0]
    monkeypatch.setattr(lr, '_now', lambda: now[0])
    assert client.get('/api/landing/timeline').get_json()['kpi'] == '1'
    now[0] += lr.CACHE_TTL - 1
    assert client.get('/api/landing/timeline').get_json()['kpi'] == '1'
    now[0] += 2
    assert client.get('/api/landing/timeline').get_json()['kpi'] == '2'

    boom = {'fail': True}
    def flaky(today):
        if boom['fail']:
            raise RuntimeError('db down')
        return {'ok': True, 'kpi': 'x'}
    lr.register_loader('tagger', flaky)
    assert client.get('/api/landing/tagger').status_code == 500
    boom['fail'] = False
    assert client.get('/api/landing/tagger').get_json()['kpi'] == 'x'


def test_responses_are_not_browser_cached(client):
    lr.register_loader('plants', lambda today: {'ok': True})
    assert client.get('/api/landing/plants').headers['Cache-Control'] == 'no-store'
```

- [ ] **Step 2: Run — expect FAIL** (`ImportError: cannot import name 'landing_routes'`)

Run: `python -m pytest tests/test_landing_routes.py -q`

- [ ] **Step 3: Implement**

```python
# source/routes/landing_routes.py
"""Landing dashboard API: GET /api/landing/<block> → one KPI block.

Loaders are registered by name (landing_loaders.register_default_loaders() and
WebApp.py for blocks that need its internals). Each block is cached for
CACHE_TTL seconds in process memory, and one block's failure never affects
another. The global _require_auth gate in WebApp.py protects every route here.
"""
import logging
import time
from datetime import date

from flask import Blueprint, jsonify

logger = logging.getLogger(__name__)
landing_bp = Blueprint('landing', __name__)

BLOCKS = ('monthly', 'accounts', 'cards', 'housing', 'timeline', 'bills',
          'spotify', 'plants', 'recurring', 'tagger', 'files')
CACHE_TTL = 300
LOADERS = {}
_cache = {}          # block -> (timestamp, data)


def register_loader(name, fn):
    LOADERS[name] = fn


def clear_cache():
    _cache.clear()


def _now():
    return time.time()


def _server_today():
    return date.today()


def _json(data, status=200):
    resp = jsonify(data)
    resp.status_code = status
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@landing_bp.route('/api/landing/<block>')
def api_landing_block(block):
    if block not in BLOCKS:
        return _json({'ok': False, 'error': 'unknown block'}, 404)
    hit = _cache.get(block)
    if hit and _now() - hit[0] < CACHE_TTL:
        return _json(hit[1])
    try:
        data = LOADERS[block](_server_today())
    except Exception:
        logger.exception('landing block failed: %s', block)
        return _json({'ok': False, 'error': 'לא זמין כרגע'}, 500)
    _cache[block] = (_now(), data)
    return _json(data)
```

- [ ] **Step 4: Run — expect PASS**

Run: `python -m pytest tests/test_landing_routes.py -q`

- [ ] **Step 5: Commit** (VERSION → 1.25.8)

```bash
printf '1.25.8\r\n' > VERSION
git add source/routes/landing_routes.py tests/test_landing_routes.py VERSION
git commit -m "feat(landing): /api/landing/<block> blueprint with 5-min cache and per-block isolation

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: DB loaders

**Files:**
- Create: `source/landing_loaders.py`
- Test: `tests/test_landing_loaders.py`

**Interfaces:**
- Consumes: builders from Tasks 1–2; `register_loader` from Task 3.
- Produces: `load_cards, load_timeline, load_bills, load_spotify, load_plants, load_recurring, load_tagger, load_files` (each `(today) -> block dict`), `register_default_loaders()`. Each loader calls `_db()` (monkeypatchable, returns `DataBase()`).

Existing functions reused (do not re-implement):
- Cards: `db.ensure_card_limits_table()`; `CardAnalysis.get_card_analysis_data(db)['cards']`
- Spotify: `db.ensure_spotify_tables()`; `SpotifyTracker.compute_all_balances(db)`
- Plants: `routes.plant_routes.get_store()` + `plant_service.build_payload(store, today)['summary']`
- Recurring: `db.ensure_recurring_tables()`; `db.get_recurring_cache()` → `{'data_json': str, …}` or None; JSON key `groups`
- Tagger: `db.get_recently_tagged(limit=1)`
- Timeline / bills / files: SQL below via `db.cursor.execute(sql).fetchall()` (`db.ensure_timeline_tables()` first for timeline)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_landing_loaders.py
import json
from datetime import date, datetime

import landing_loaders as ll

TODAY = date(2026, 10, 4)


class FakeCursor:
    def __init__(self, rows_by_table):
        self.rows_by_table, self.sql = rows_by_table, []

    def execute(self, sql, params=None):
        self.sql.append(sql)
        self._rows = next((rows for key, rows in self.rows_by_table.items() if key in sql), [])
        return self

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class FakeDB:
    def __init__(self, rows_by_table=None, **attrs):
        self.cursor = FakeCursor(rows_by_table or {})
        self.ensured = []
        for k, v in attrs.items():
            setattr(self, k, v)

    def __getattr__(self, name):
        if name.startswith('ensure_'):
            return lambda: self.ensured.append(name)
        raise AttributeError(name)


def use(monkeypatch, db):
    monkeypatch.setattr(ll, '_db', lambda: db)
    return db


def test_timeline_reads_newest_created_event(monkeypatch):
    db = use(monkeypatch, FakeDB({'TimelineEvents': [('חתונה', date(2026, 11, 2), datetime(2026, 10, 1))]}))
    b = ll.load_timeline(TODAY)
    assert b['kpi'] == 'חתונה' and 'ensure_timeline_tables' in db.ensured
    sql = db.cursor.sql[-1]
    assert 'Deleted_At IS NULL' in sql and 'ORDER BY e.Created_At DESC' in sql
    use(monkeypatch, FakeDB({}))
    assert ll.load_timeline(TODAY)['dot'] == 'grey'


def test_bills_excludes_fillers(monkeypatch):
    db = use(monkeypatch, FakeDB({'BillEntries': [(1, 'חשמל', '2026-01', '2026-02', 600)]}))
    b = ll.load_bills(TODAY)
    assert b['kpi'] == '300₪' and 'Is_Filler' in db.cursor.sql[-1]


def test_files_newest(monkeypatch):
    use(monkeypatch, FakeDB({'FROM File': [('a.xlsx', 'Leumi Bank', date(2026, 10, 1), datetime(2026, 10, 3))]}))
    assert ll.load_files(TODAY)['details'] == ['a.xlsx', 'Leumi Bank']


def test_tagger(monkeypatch):
    use(monkeypatch, FakeDB(get_recently_tagged=lambda limit: [
        {'name': 'שופרסל', 'charge_value': 10, 'category': 'סופר', 'exec_date': '2026-10-02'}][:limit]))
    assert ll.load_tagger(TODAY)['caption'] == 'שופרסל'
    use(monkeypatch, FakeDB(get_recently_tagged=lambda limit: []))
    assert ll.load_tagger(TODAY)['dot'] == 'grey'


def test_recurring_reads_cached_groups(monkeypatch):
    data = {'groups': [{'name': 'ביטוח', 'current_amount': 300, 'next_expected': '2026-10-06'}]}
    use(monkeypatch, FakeDB(get_recurring_cache=lambda: {'data_json': json.dumps(data)}))
    assert ll.load_recurring(TODAY)['kpi'] == '300₪'
    use(monkeypatch, FakeDB(get_recurring_cache=lambda: None))
    assert ll.load_recurring(TODAY)['dot'] == 'grey'


def test_cards_spotify_plants_use_existing_functions(monkeypatch):
    db = use(monkeypatch, FakeDB())
    monkeypatch.setattr(ll, '_card_data', lambda d: {'cards': [{'card_id': '1', 'network': 'Visa', 'current_charge': 5}]})
    monkeypatch.setattr(ll, '_spotify_balances', lambda d: [{'name': 'דנה', 'balance': -30}])
    monkeypatch.setattr(ll, '_plants_summary', lambda today: {'due_today': 1, 'overdue': 0, 'auto_pending_confirm': 0})
    assert ll.load_cards(TODAY)['kpi'] == '1' and 'ensure_card_limits_table' in db.ensured
    assert ll.load_spotify(TODAY)['kpi'] == '30₪' and 'ensure_spotify_tables' in db.ensured
    assert ll.load_plants(TODAY)['kpi'] == '1'


def test_register_default_loaders(monkeypatch):
    from routes import landing_routes as lr
    monkeypatch.setattr(lr, 'LOADERS', {})
    ll.register_default_loaders()
    assert set(lr.LOADERS) == {'cards', 'timeline', 'bills', 'spotify', 'plants', 'recurring', 'tagger', 'files'}
```

- [ ] **Step 2: Run — expect FAIL** (`ModuleNotFoundError: No module named 'landing_loaders'`)

Run: `python -m pytest tests/test_landing_loaders.py -q`

- [ ] **Step 3: Implement**

```python
# source/landing_loaders.py
"""DB loaders for the landing dashboard blocks that need only the database.

Each loader reuses the feature's own data function (same numbers as its page)
and hands the raw data to the matching landing_service builder. Monthly,
accounts and housing need WebApp internals and are registered from WebApp.py.
"""
import json

import landing_service as ls


def _db():
    from database import DataBase
    return DataBase()


# Thin wrappers around feature modules, so tests can stub them.
def _card_data(db):
    from CardAnalysis import get_card_analysis_data
    return get_card_analysis_data(db)


def _spotify_balances(db):
    from SpotifyTracker import compute_all_balances
    return compute_all_balances(db)


def _plants_summary(today):
    import plant_service
    from routes.plant_routes import get_store
    return plant_service.build_payload(get_store(), today)['summary']


def load_cards(today):
    db = _db()
    db.ensure_card_limits_table()
    return ls.build_cards(_card_data(db).get('cards'))


def load_timeline(today):
    db = _db()
    db.ensure_timeline_tables()
    rows = db.cursor.execute(
        'SELECT e.Name, e.Event_Date, e.Created_At FROM TimelineEvents e '
        'LEFT JOIN TimelineCategories tc ON tc.Key = e.Category '
        'WHERE e.Deleted_At IS NULL AND tc.Deleted_At IS NULL '
        'ORDER BY e.Created_At DESC NULLS LAST, e.ID DESC LIMIT 1').fetchall()
    if not rows:
        return ls.build_timeline(None)
    name, event_date, created_at = rows[0]
    return ls.build_timeline({'name': name, 'event_date': event_date, 'created_at': created_at})


def load_bills(today):
    rows = _db().cursor.execute(
        'SELECT t.ID, t.Name, e.Start_Month, e.End_Month, e.Amount FROM BillEntries e '
        'JOIN BillTypes t ON t.ID = e.BillType_ID '
        'WHERE NOT COALESCE(e.Is_Filler, FALSE)').fetchall()
    return ls.build_bills([tuple(r) for r in rows])


def load_spotify(today):
    db = _db()
    db.ensure_spotify_tables()
    return ls.build_spotify(_spotify_balances(db))


def load_plants(today):
    return ls.build_plants(_plants_summary(today))


def load_recurring(today):
    db = _db()
    db.ensure_recurring_tables()
    cache = db.get_recurring_cache()
    groups = json.loads(cache['data_json']).get('groups') if cache and cache.get('data_json') else []
    return ls.build_recurring(groups, today)


def load_tagger(today):
    rows = _db().get_recently_tagged(limit=1)
    return ls.build_tagger(rows[0] if rows else None)


def load_files(today):
    rows = _db().cursor.execute(
        'SELECT File_Name, Format, Date, Last_update FROM File '
        'ORDER BY Last_update DESC NULLS LAST, Date DESC LIMIT 1').fetchall()
    if not rows:
        return ls.build_files(None)
    name, fmt, d, last_update = rows[0]
    return ls.build_files({'file_name': name, 'format': fmt, 'date': d, 'last_update': last_update})


def register_default_loaders():
    from routes.landing_routes import register_loader
    for name, fn in (('cards', load_cards), ('timeline', load_timeline), ('bills', load_bills),
                     ('spotify', load_spotify), ('plants', load_plants), ('recurring', load_recurring),
                     ('tagger', load_tagger), ('files', load_files)):
        register_loader(name, fn)
```

- [ ] **Step 4: Run — expect PASS**

Run: `python -m pytest tests/test_landing_loaders.py tests/test_landing_service.py tests/test_landing_routes.py -q`

- [ ] **Step 5: Commit** (VERSION → 1.25.9)

```bash
printf '1.25.9\r\n' > VERSION
git add source/landing_loaders.py tests/test_landing_loaders.py VERSION
git commit -m "feat(landing): DB loaders reusing each feature's own data functions

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Wire into WebApp (blueprint + monthly/accounts/housing loaders) + real-data smoke

**Files:**
- Modify: `source/WebApp.py` (right after `app.register_blueprint(plants_bp)`, ~line 5919)

**Interfaces:**
- Consumes: `landing_bp`, `register_loader` (Task 3), `register_default_loaders` (Task 4), `pick_month`, `build_monthly`, `build_accounts`, `build_housing` (Task 1).
- Uses these WebApp internals as they are: `general_list()` (view → JSON list of `{key,…}`), `monthly_data_api(yyyy_mm)` (view → `(Response, status, headers)` or `(Response, 404, …)` for no data), `_accounts_cached_payload()`, `_compute_accounts()`, `_cash_balance_map()`, `_get_fx_rates()`, `housing_data_api()` (view → Response or `(Response, 500)`).

- [ ] **Step 1: Check that no route is duplicated**

Run: `grep -n "api/landing\|landing_bp" source/WebApp.py`
Expected: no output.

- [ ] **Step 2: Add the wiring after the plants blueprint**

```python
from routes.landing_routes import landing_bp, register_loader as _landing_register
import landing_service as _landing_svc
from landing_loaders import register_default_loaders as _landing_defaults
app.register_blueprint(landing_bp)
_landing_defaults()


def _view_json(rv):
    """(json, status) from a view's return value: Response or (Response, status[, headers])."""
    resp, status = (rv[0], rv[1]) if isinstance(rv, tuple) else (rv, rv.status_code)
    return resp.get_json(), status


def _landing_monthly(today):
    months, _ = _view_json(general_list())
    key = _landing_svc.pick_month(months, today)
    payload = None
    if key:
        data, status = _view_json(monthly_data_api(key))
        payload = data if status == 200 else None
    return _landing_svc.build_monthly(months, key, payload)


def _landing_accounts(today):
    payload = _accounts_cached_payload() or _compute_accounts()
    try:
        cash_map = _cash_balance_map()
    except Exception:
        cash_map = None
    return _landing_svc.build_accounts(payload, cash_map, _get_fx_rates(), today)


def _landing_housing(today):
    data, status = _view_json(housing_data_api())
    if status != 200:
        raise RuntimeError((data or {}).get('error', 'housing data failed'))
    return _landing_svc.build_housing(data.get('mortgage'))


_landing_register('monthly', _landing_monthly)
_landing_register('accounts', _landing_accounts)
_landing_register('housing', _landing_housing)
```

> Note: `_compute_accounts()` returns the same `{'accounts', 'accounts_meta'}` dict as `_accounts_cached_payload()`. Read its tail (`grep -n "return payload" source/WebApp.py` near line 120–150) and confirm before relying on it.

- [ ] **Step 3: Real-data smoke (read-only, real Neon DB)**

Write `C:\Users\ofeks\AppData\Local\Temp\claude\c--Users-ofeks-OneDrive-Ofek-BankProject\21444322-fc3f-4691-b4eb-671e49bc22b7\scratchpad\landing_smoke.py`:

```python
"""Read-only smoke: every landing block against the real DB, plus the auth gate."""
import os, sys, json
ROOT = r'C:\Users\ofeks\OneDrive\Ofek\BankProject'
sys.path[:0] = [ROOT, os.path.join(ROOT, 'source')]
os.chdir(os.path.join(ROOT, 'source'))
from dotenv import load_dotenv; load_dotenv(os.path.join(ROOT, '.env'))
import WebApp
from routes.landing_routes import BLOCKS

c = WebApp.app.test_client()
assert c.get('/api/landing/plants').status_code == 401, 'must be 401 without a session'
with c.session_transaction() as s:
    s['authenticated'] = True
bad = 0
for b in BLOCKS:
    r = c.get(f'/api/landing/{b}')
    d = r.get_json()
    ok = r.status_code == 200 and d.get('ok') and isinstance(d.get('kpi'), str)
    bad += not ok
    print(('PASS ' if ok else 'FAIL ') + b, json.dumps(d, ensure_ascii=False)[:220])
print('unknown →', c.get('/api/landing/nope').status_code)
sys.exit(1 if bad else 0)
```

Run: `PYTHONIOENCODING=utf-8 python "<scratchpad>/landing_smoke.py"`
Expected: `401` assertion passes, 11× `PASS`, `unknown → 404`. Cross-check two numbers by hand against the live pages: the accounts KPI against the grand total on the accounts page, and the housing % against the `/housing` page.

- [ ] **Step 4: Restart server** (clear `source/**/__pycache__`, stop preview, kill listener on 5050, `preview_start` "BankDash", `curl http://localhost:5050/api/version`)

- [ ] **Step 5: Commit** (VERSION → 1.25.10)

```bash
printf '1.25.10\r\n' > VERSION
git add source/WebApp.py VERSION
git commit -m "feat(landing): register landing blueprint and monthly/accounts/housing loaders

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: `index.html` — sign-in gate + KPI dashboard

**Files:**
- Rewrite: `index.html` (project root; served by `@app.route('/')`)

**Interfaces:**
- Consumes: `GET /api/auth/check` → `{authenticated}`, `POST /api/auth/verify` `{password}` → `{ok}`, `POST /api/auth/logout`, `GET /api/version` → `{version}`, `GET /api/landing/<block>` → block JSON (Global Constraints).
- Keeps: `localStorage['bankdash_auth'] = {token:'ok', exp}` (7-day TTL; other pages may read it), `?next=` same-origin forwarding (`/^\/(?!\/)/`), `?auth=required` URL tidy with `history.replaceState`.

- [ ] **Step 1: Replace `index.html` with:**

```html
<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>BankDash</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;600;700;800&display=swap" rel="stylesheet" />
  <style>
    :root { --navy:#1e2a4a; --teal:#1e9d8b; --bg:#f4f6f9; --white:#fff; --border:#e3e7ee;
            --muted:#6b7590; --green:#22a06b; --amber:#e8a317; --red:#d64545; --grey:#b7bfcc; }
    * { box-sizing:border-box; margin:0; padding:0; }
    html, body { background:var(--bg); color:var(--navy); font-family:'Heebo',system-ui,sans-serif; }
    body { min-height:100vh; overflow-x:hidden; }
    [hidden] { display:none !important; }

    /* ── Gate ── */
    #gate { position:fixed; inset:0; display:flex; align-items:center; justify-content:center; padding:16px;
            background:linear-gradient(135deg,#0f1627 0%,#1a2e52 100%); transition:opacity .3s; z-index:10; }
    #gate.fade { opacity:0; pointer-events:none; }
    .gate-box { width:100%; max-width:360px; background:var(--white); border-radius:16px; padding:28px 24px;
                box-shadow:0 20px 50px rgba(0,0,0,.35); text-align:center; }
    .gate-logo { width:48px; height:48px; border-radius:14px; background:var(--teal); margin:0 auto 14px;
                 display:flex; align-items:center; justify-content:center; }
    .gate-box h1 { font-size:20px; font-weight:700; margin-bottom:4px; }
    .gate-box p { font-size:13px; color:var(--muted); margin-bottom:18px; }
    #pwInput { width:100%; padding:12px 14px; border:1.5px solid var(--border); border-radius:10px; font:inherit;
               font-size:15px; outline:none; direction:ltr; text-align:center; }
    #pwInput:focus { border-color:var(--teal); }
    #pwInput.err { border-color:var(--red); animation:shake .4s ease; }
    #formErr { min-height:18px; font-size:12px; color:var(--red); margin:6px 0 4px; }
    #signinBtn { width:100%; padding:12px; border:0; border-radius:10px; background:var(--teal); color:#fff;
                 font:inherit; font-weight:600; font-size:15px; cursor:pointer; }
    #signinBtn:disabled { opacity:.6; cursor:default; }
    @keyframes shake { 20%,60%{transform:translateX(-6px)} 40%,80%{transform:translateX(6px)} }

    /* ── Dashboard ── */
    .dash-head { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap;
                 max-width:1200px; margin:0 auto; padding:22px 16px 6px; }
    .dash-head h1 { font-size:22px; font-weight:800; }
    .dash-head .sub { font-size:13px; color:var(--muted); margin-top:2px; }
    .head-actions { display:flex; align-items:center; gap:10px; }
    #versionBadge { font-size:11px; color:var(--muted); background:var(--white); border:1px solid var(--border);
                    border-radius:999px; padding:3px 9px; direction:ltr; }
    #signOutBtn { border:1px solid var(--border); background:var(--white); color:var(--navy); border-radius:10px;
                  padding:7px 12px; font:inherit; font-size:13px; cursor:pointer; }
    #signOutBtn:hover { border-color:var(--teal); color:var(--teal); }
    .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); gap:14px;
            max-width:1200px; margin:0 auto; padding:14px 16px 32px; }
    .card { position:relative; display:flex; flex-direction:column; gap:6px; min-width:0; background:var(--white);
            border-radius:16px; padding:16px; box-shadow:0 1px 3px rgba(30,42,74,.08); color:inherit;
            text-decoration:none; border:1px solid transparent; transition:border-color .15s, transform .15s; }
    .card:hover { border-color:var(--teal); transform:translateY(-1px); }
    .card-top { display:flex; align-items:center; gap:8px; font-size:14px; font-weight:600; }
    .card-top svg { flex:none; width:20px; height:20px; stroke:var(--teal); fill:none; stroke-width:1.8;
                    stroke-linecap:round; stroke-linejoin:round; }
    .card-top .title { flex:1; min-width:0; }
    .dot { width:9px; height:9px; border-radius:50%; flex:none; }
    .dot.green{background:var(--green)} .dot.amber{background:var(--amber)} .dot.red{background:var(--red)} .dot.grey{background:var(--grey)}
    .kpi { font-size:28px; font-weight:800; line-height:1.15; font-variant-numeric:tabular-nums;
           overflow:hidden; text-overflow:ellipsis; white-space:nowrap; margin-top:4px; }
    .kpi-ltr { direction:ltr; unicode-bidi:isolate; }
    .caption { font-size:13px; color:var(--muted); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .details { list-style:none; display:flex; flex-direction:column; gap:3px; margin-top:4px; font-size:12.5px;
               border-top:1px solid var(--border); padding-top:8px; }
    .details li { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .card .err { font-size:13px; color:var(--muted); margin-top:6px; }
    .skel { height:30px; width:60%; border-radius:8px; margin-top:6px;
            background:linear-gradient(90deg,#eef1f5 25%,#e2e7ee 50%,#eef1f5 75%); background-size:200% 100%;
            animation:shimmer 1.2s infinite; }
    .skel.s2 { height:12px; width:85%; }
    @keyframes shimmer { to { background-position:-200% 0; } }
    .month-row { display:flex; gap:8px; margin-top:8px; }
    .month-row select { flex:1; min-width:0; padding:6px 8px; border:1px solid var(--border); border-radius:8px;
                        font:inherit; font-size:13px; background:var(--white); color:var(--navy); }
    .month-row button { padding:6px 12px; border:0; border-radius:8px; background:var(--teal); color:#fff;
                        font:inherit; font-size:13px; cursor:pointer; }
    .card.tile { flex-direction:row; align-items:center; gap:10px; }
    .card.tile .desc { font-size:12.5px; color:var(--muted); font-weight:400; }
  </style>
</head>
<body>

<!-- Sign-in gate: the only thing a visitor without a session sees -->
<div id="gate" hidden>
  <form class="gate-box" onsubmit="handleSignIn(event)" autocomplete="off">
    <div class="gate-logo"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg></div>
    <h1>BankDash</h1>
    <p>יש להתחבר כדי להמשיך</p>
    <input id="pwInput" type="password" placeholder="סיסמה" aria-label="סיסמה" />
    <div id="formErr" role="alert"></div>
    <button id="signinBtn" type="submit">כניסה</button>
  </form>
</div>

<!-- Dashboard: stays hidden (not just covered) until authenticated -->
<main id="dash" hidden>
  <header class="dash-head">
    <div>
      <h1 id="greeting"></h1>
      <div class="sub" id="today"></div>
    </div>
    <div class="head-actions">
      <span id="versionBadge"></span>
      <button id="signOutBtn" type="button" onclick="signOut()">התנתקות</button>
    </div>
  </header>
  <section class="grid" id="grid"></section>
</main>

<script>
  /* ── AUTH (same contract as before: server session is the truth) ── */
  const SESSION_KEY = 'bankdash_auth';
  const SESSION_TTL = 7 * 24 * 60 * 60 * 1000;
  let _pendingUrl = null;

  function setLocalFlag(on) {
    try {
      if (on) localStorage.setItem(SESSION_KEY, JSON.stringify({ token: 'ok', exp: Date.now() + SESSION_TTL }));
      else localStorage.removeItem(SESSION_KEY);
    } catch (e) {}
  }

  async function serverAuthenticated() {
    try {
      const r = await fetch('/api/auth/check', { headers: { 'Accept': 'application/json' } });
      return r.ok && (await r.json()).authenticated === true;
    } catch (e) { return false; }
  }

  async function trySignIn(pw) {
    try {
      const r = await fetch('/api/auth/verify', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password: pw }),
      });
      if ((await r.json()).ok) { setLocalFlag(true); return true; }
    } catch (e) {}
    return false;
  }

  function showGate() {
    document.getElementById('dash').hidden = true;
    document.getElementById('grid').innerHTML = '';
    const gate = document.getElementById('gate');
    gate.hidden = false;
    gate.classList.remove('fade');
    setTimeout(() => document.getElementById('pwInput').focus(), 50);
  }

  function enterDashboard() {
    if (_pendingUrl && _pendingUrl !== '/') { window.location.href = _pendingUrl; return; }
    const gate = document.getElementById('gate');
    gate.classList.add('fade');
    setTimeout(() => { gate.hidden = true; }, 300);
    document.getElementById('dash').hidden = false;
    renderDashboard();
  }

  async function handleSignIn(e) {
    e.preventDefault();
    const inp = document.getElementById('pwInput'), err = document.getElementById('formErr');
    const btn = document.getElementById('signinBtn');
    inp.classList.remove('err'); err.textContent = '';
    if (!inp.value) { inp.classList.add('err'); err.textContent = 'נא להזין סיסמה'; return; }
    btn.disabled = true;
    const ok = await trySignIn(inp.value);
    btn.disabled = false;
    if (ok) { inp.value = ''; enterDashboard(); return; }
    inp.value = '';
    void inp.offsetWidth;
    inp.classList.add('err');
    err.textContent = 'סיסמה שגויה, נסו שוב';
  }

  function signOut() {
    setLocalFlag(false);
    fetch('/api/auth/logout', { method: 'POST' }).catch(() => {});
    _pendingUrl = null;
    showGate();
  }

  /* ── BLOCKS (menu order: live blocks first, description-only tiles last) ── */
  const ICONS = {
    monthly:   '<rect x="3" y="4" width="18" height="17" rx="2"/><path d="M3 9h18M8 2v4M16 2v4"/>',
    accounts:  '<path d="M3 10l9-6 9 6"/><path d="M5 10v9M19 10v9M9 10v9M15 10v9M3 21h18"/>',
    cards:     '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20M6 15h4"/>',
    housing:   '<path d="M3 11l9-7 9 7"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/>',
    timeline:  '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    organizer: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    bills:     '<path d="M6 2h12v20l-3-2-3 2-3-2-3 2z"/><path d="M9 7h6M9 11h6M9 15h4"/>',
    categories:'<path d="M21 12A9 9 0 1 1 12 3v9z"/><path d="M15 3.5A9 9 0 0 1 20.5 9H15z"/>',
    search:    '<circle cx="11" cy="11" r="7"/><path d="M21 21l-5-5"/>',
    spotify:   '<circle cx="12" cy="12" r="9"/><path d="M7.5 10c3-1 6.5-.7 9 .8M8 13.2c2.4-.7 5-.5 7 .7M8.5 16c1.9-.5 3.8-.3 5.4.5"/>',
    plants:    '<path d="M12 21v-8"/><path d="M12 13c0-4 3-7 7-7 0 4-3 7-7 7z"/><path d="M12 15c0-3-2.5-5.5-6-5.5 0 3 2.5 5.5 6 5.5z"/><path d="M8 21h8"/>',
    recurring: '<path d="M20 11a8 8 0 0 0-14.9-4M4 13a8 8 0 0 0 14.9 4"/><path d="M5 3v4h4M19 21v-4h-4"/>',
    tagger:    '<path d="M3 12V4a1 1 0 0 1 1-1h8l9 9-9 9z"/><circle cx="8" cy="8" r="1.5"/>',
    files:     '<path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z"/><path d="M14 3v5h5"/>',
  };
  const BLOCKS = [
    { id: 'monthly',   title: 'ניתוח חודשי',      live: true },
    { id: 'accounts',  title: 'חשבונות',          live: true, href: '/accounts' },
    { id: 'cards',     title: 'כרטיסים',          live: true, href: '/card-analysis' },
    { id: 'housing',   title: 'דיור',             live: true, href: '/housing' },
    { id: 'timeline',  title: 'ציר זמן',          live: true, href: '/timeline' },
    { id: 'organizer', title: 'ארגונית',          desc: 'סידור ותיוג קבצים',          href: '/organizer' },
    { id: 'bills',     title: 'מעקב חשבונות',     live: true, href: '/bills' },
    { id: 'categories',title: 'ניתוח קטגוריאלי',  desc: 'הוצאות לפי קטגוריה',         href: '/categories' },
    { id: 'search',    title: 'חיפוש',            desc: 'חיפוש בכל העסקאות',          href: '/search' },
    { id: 'spotify',   title: 'Spotify',          live: true, href: '/spotify' },
    { id: 'plants',    title: 'מעקב עציצים',      live: true, href: '/plants' },
    { id: 'recurring', title: 'חיובים חוזרים',    live: true, href: '/recurring' },
    { id: 'tagger',    title: 'תייגן',            live: true, href: '/tagger' },
    { id: 'files',     title: 'קבצים',            live: true, href: '/files' },
  ];

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
  function icon(id) { return '<svg viewBox="0 0 24 24" aria-hidden="true">' + ICONS[id] + '</svg>'; }

  function renderDashboard() {
    const h = new Date().getHours();
    document.getElementById('greeting').textContent =
      h >= 5 && h < 12 ? 'בוקר טוב' : h >= 12 && h < 17 ? 'צהריים טובים' : h >= 17 && h < 22 ? 'ערב טוב' : 'לילה טוב';
    document.getElementById('today').textContent =
      new Date().toLocaleDateString('he-IL', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
    fetch('/api/version').then(r => r.json()).then(d => {
      if (d.version) document.getElementById('versionBadge').textContent = 'v' + d.version;
    }).catch(() => {});

    const grid = document.getElementById('grid');
    const live = BLOCKS.filter(b => b.live), tiles = BLOCKS.filter(b => !b.live);
    grid.innerHTML = live.map(b =>
      '<a class="card" id="blk-' + b.id + '" href="' + (b.href || '#') + '">' +
        '<div class="card-top">' + icon(b.id) + '<span class="title">' + esc(b.title) + '</span><span class="dot"></span></div>' +
        '<div class="body"><div class="skel"></div><div class="skel s2"></div></div>' +
      '</a>').join('') +
      tiles.map(b =>
      '<a class="card tile" id="blk-' + b.id + '" href="' + b.href + '">' + icon(b.id) +
        '<div><div class="card-top"><span class="title">' + esc(b.title) + '</span></div>' +
        '<div class="desc">' + esc(b.desc) + '</div></div>' +
      '</a>').join('');
    live.forEach(b => loadBlock(b.id));
  }

  async function loadBlock(id) {
    const el = document.getElementById('blk-' + id);
    let d = null;
    try {
      const r = await fetch('/api/landing/' + id, { headers: { 'Accept': 'application/json' } });
      if (r.status === 401) { setLocalFlag(false); showGate(); return; }
      d = await r.json();
    } catch (e) {}
    if (!el || !el.isConnected) return;
    const body = el.querySelector('.body'), dot = el.querySelector('.dot');
    if (!d || !d.ok) {
      body.innerHTML = '<div class="err">לא זמין כרגע</div>';
      dot.className = 'dot grey';
      return;
    }
    dot.className = d.dot ? 'dot ' + d.dot : 'dot';
    const ltr = /^[-+\d]/.test(d.kpi || '') ? ' kpi-ltr' : '';
    body.innerHTML =
      '<div class="kpi' + ltr + '" title="' + esc(d.kpi) + '">' + esc(d.kpi) + '</div>' +
      '<div class="caption" title="' + esc(d.caption) + '">' + esc(d.caption) + '</div>' +
      ((d.details || []).length ? '<ul class="details">' + d.details.map(x => '<li title="' + esc(x) + '">' + esc(x) + '</li>').join('') + '</ul>' : '');
    if (id === 'monthly') renderMonthPicker(el, d.extra || {});
  }

  function renderMonthPicker(el, extra) {
    const months = extra.months || [];
    el.href = extra.current ? '/general/' + extra.current : '#';
    if (!months.length) return;
    const row = document.createElement('div');
    row.className = 'month-row';
    row.innerHTML = '<select aria-label="בחירת חודש">' + months.map(m =>
      '<option value="' + esc(m.key) + '"' + (m.key === extra.current ? ' selected' : '') + '>' + esc(m.label) + '</option>').join('') +
      '</select><button type="button">פתח</button>';
    // The card itself is a link — keep picker clicks from navigating.
    row.addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); });
    row.querySelector('select').addEventListener('click', e => e.stopPropagation());
    row.querySelector('button').addEventListener('click', () => {
      window.location.href = '/general/' + row.querySelector('select').value;
    });
    el.querySelector('.body').appendChild(row);
  }

  /* ── INIT ── */
  (async function init() {
    const params = new URLSearchParams(location.search);
    const rawNext = params.get('next') || '';
    if (/^\/(?!\/)/.test(rawNext)) _pendingUrl = rawNext;    /* same-origin paths only */
    if (params.has('auth') || params.has('next')) history.replaceState(null, '', location.pathname);

    if (await serverAuthenticated()) { setLocalFlag(true); enterDashboard(); }
    else { setLocalFlag(false); showGate(); }
  })();
</script>
</body>
</html>
```

> The `select` inside an `<a>` needs `preventDefault` on the row so that choosing a month doesn't follow the card link. `stopPropagation` on the select's own click keeps the native dropdown working.

- [ ] **Step 2: Headless checks**

Write the harness `<scratchpad>/landing_harness.py`. It is a Flask app on port 5077 that serves the real `index.html` at `/` and fakes the auth endpoints and `/api/landing/<block>`. `files` always fails with a 500, and every `/api/landing` hit is counted.

```python
"""Harness for index.html: fake auth + fake landing blocks (port 5077)."""
import os
from flask import Flask, jsonify, request, send_file, session

ROOT = r'C:\Users\ofeks\OneDrive\Ofek\BankProject'
app = Flask(__name__)
app.secret_key = 'harness'
HITS = []

@app.route('/')
def index():
    return send_file(os.path.join(ROOT, 'index.html'))

@app.route('/api/version')
def version():
    return jsonify({'version': '9.9.9'})

@app.route('/api/auth/check')
def check():
    return jsonify({'authenticated': bool(session.get('a'))})

@app.route('/api/auth/verify', methods=['POST'])
def verify():
    ok = (request.get_json() or {}).get('password') == 'pw'
    if ok:
        session['a'] = True
    return jsonify({'ok': ok})

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'ok': True})

@app.route('/api/landing/<block>')
def landing(block):
    HITS.append(block)
    if not session.get('a'):
        return jsonify({'error': 'unauthorized'}), 401
    if block == 'files':
        return jsonify({'ok': False, 'error': 'לא זמין כרגע'}), 500
    extra = {'months': [{'key': '2026_10', 'label': 'אוקטובר 2026'}, {'key': '2026_09', 'label': 'ספטמבר 2026'}],
             'current': '2026_10'} if block == 'monthly' else {}
    return jsonify({'ok': True, 'dot': 'amber', 'kpi': '1,234₪', 'caption': 'כיתוב ארוך ' * 6,
                    'details': ['שורה 1', 'שורה 2'], 'extra': extra})

@app.route('/_hits')
def hits():
    return jsonify(HITS)

if __name__ == '__main__':
    app.run(port=5077)
```

Then write `<scratchpad>/landing_behave.py` (Playwright, same `check()`/results pattern as `photo_behave.py`) asserting:
1. Fresh context at `/` → `#gate` visible, `#dash` has `hidden`, and `/_hits` is empty after 1 s.
2. Wrong password → `#formErr` text is `סיסמה שגויה, נסו שוב`; `#dash` is still hidden.
3. Password `pw` → `#dash` visible, `#gate` hidden after 400 ms, 14 `.card` elements, the first 11 without the `tile` class.
4. `#blk-plants .kpi` text is `1,234₪`; `#blk-files .err` text is `לא זמין כרגע` and the other blocks are unaffected.
5. Monthly: the `select` has 2 options; changing to `2026_09` and clicking `פתח` navigates to `/general/2026_09` (the harness returns a 404 there, so check `page.url`).
6. Viewport 375×812 and 320×700: `document.documentElement.scrollWidth <= innerWidth`.
7. After a reload, the dashboard opens without the gate (session cookie).
8. התנתקות → gate visible, `#grid` empty.
9. `/?auth=required&next=/plants` without a session → gate; sign-in → `page.url` ends with `/plants`.
10. No page errors.

Run the harness through a temporary `.claude/launch.json` entry "LandingHarness" (`python <scratchpad>/landing_harness.py`, port 5077) with `preview_start`. Then run `python <scratchpad>/landing_behave.py`. Expected: every line `PASS`. Restore `.claude/launch.json` afterwards: `git checkout -- .claude/launch.json`.

- [ ] **Step 3: Real-page look** — restart BankDash (5050), open `/` in the preview, sign in, and screenshot at desktop and at 375 px. Check that the numbers match Task 5's smoke output.

- [ ] **Step 4: Commit** (VERSION → 1.25.11)

```bash
printf '1.25.11\r\n' > VERSION
git add index.html VERSION
git commit -m "feat(landing): sign-in gate + KPI dashboard landing page

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Spec sync, final version, push

**Files:**
- Modify: `docs/superpowers/specs/2026-10-04-landing-dashboard-design.md`
- Modify: `VERSION` → `1.26.0`

- [ ] **Step 1: Update the spec**
  - API section: block JSON is `{ok, dot, kpi, caption, details, extra}`. It replaces `facts`.
  - Blocks table, bills row: details = "all 5 types with their average".
  - Block anatomy: details hold ≤3 lines, except bills (5).

- [ ] **Step 2: Full test run**

Run: `python -m pytest tests/test_landing_service.py tests/test_landing_loaders.py tests/test_landing_routes.py tests/test_plant_logic.py tests/test_plant_suggestions.py tests/test_plant_service.py tests/test_plant_routes.py -q`
Expected: all pass.

- [ ] **Step 3: Commit + push** (VERSION → 1.26.0, minor bump for the feature)

```bash
printf '1.26.0\r\n' > VERSION
git add docs/superpowers/specs/2026-10-04-landing-dashboard-design.md VERSION
git commit -m "docs(landing): sync spec with implemented block shape; v1.26.0

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push origin Dev/GeneralFeatures
```

- [ ] **Step 4: Restart server and report the version (1.26.0)** to the user.
