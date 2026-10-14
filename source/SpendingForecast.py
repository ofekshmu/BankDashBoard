"""
Spending forecast — "how much can I spend until the next salary?"

Combines the bank balance, the recurring bank charges (rent included), the
credit-card charge dates/amounts and the salary date, and works out how much
money is *free* so that no point in time before the next salary goes below zero.

Rules of thumb (all derived from the last HISTORY_MONTHS months of data):
  - salary: average amount, average day of the month (the day can be overridden)
  - each card (one bank "credit-card charge" source): usual charge day, average
    monthly charge; in the harsh mode ("max") the largest month of the history
  - a card charge is never lower than what the card already holds for that date
    (CardTransactions whose Charge_Date is still ahead)
  - recurring charges paid straight from the bank at their usual day-of-month
    (recurring charges paid by card are already inside the card charge)
  - spending is assumed to happen right now, so the free amount is the lowest
    balance reached along the way — the worst moment before the salary

Pure functions work on plain dicts/dates; only fetch_forecast_inputs() and
get_forecast() touch the DB.
"""
import calendar as _cal
import statistics
from datetime import date as _date

from RecurringCharges import normalize_name, month_key, _parse_month_key, _to_plain_date

SALARY_CATEGORY = 'משכורת'
RENT_CATEGORY = 'שכירות'
CC_CHARGE_CATEGORY = 'אשראי'

HISTORY_MONTHS = 6             # months of history behind every rule of thumb
MIN_SALARY_FRACTION = 0.5      # a deposit below this share of the usual salary is not "the salary"
PENDING_MATCH_DAYS = 5         # a card's pending charge belongs to a usual charge day within this many days
STALE_BALANCE_DAYS = 3         # the balance is flagged old when it is older than this
CARD_MODES = ('avg', 'max')


# ── Date helpers ────────────────────────────────────────────────────────────────

def _clamp_day(year: int, month: int, day: int) -> _date:
    """The given day of a month, moved back to the month's last day when it has fewer days."""
    return _date(year, month, min(day, _cal.monthrange(year, month)[1]))


def _add_months(d: _date, n: int) -> _date:
    """First day of the month n months after d's month."""
    idx = d.year * 12 + (d.month - 1) + n
    return _date(idx // 12, idx % 12 + 1, 1)


def _months_back(d: _date, n: int) -> str:
    """'YYYY-MM' key of the month n months before d's month."""
    return month_key(_add_months(d, -n))


def usual_day(days: list) -> int:
    """The usual day-of-month of a charge: the most common day (ties: the latest), else the rounded average."""
    if not days:
        return 1
    counts = {}
    for d in days:
        counts[d] = counts.get(d, 0) + 1
    best = max(counts.values())
    if best > 1:
        return max(d for d, c in counts.items() if c == best)
    return int(round(sum(days) / len(days)))


# ── Salary ──────────────────────────────────────────────────────────────────────

def build_salary_profile(rows: list, as_of: _date, salary_day: int = None) -> dict:
    """
    rows: [{'date': date, 'amount': float}] salary deposits (Income > 0 tagged as salary).
    Returns the salary rule of thumb plus when the next salary is expected.

    A month's salary is the sum of its deposits; its day is the day of the largest
    deposit. 'received_this_month' is true once the current month holds a deposit of
    at least MIN_SALARY_FRACTION of the usual amount.
    """
    first_key = _months_back(as_of, HISTORY_MONTHS)
    by_month = {}
    for r in rows:
        mk = month_key(r['date'])
        if mk < first_key:
            continue
        by_month.setdefault(mk, []).append(r)

    months = []
    for mk in sorted(by_month):
        deposits = by_month[mk]
        biggest = max(deposits, key=lambda r: r['amount'])
        months.append({'month': mk, 'amount': round(sum(r['amount'] for r in deposits), 2),
                       'day': biggest['date'].day})

    cur_key = month_key(as_of)
    past = [m for m in months if m['month'] != cur_key] or months
    if not past:
        return {'known': False, 'months': [], 'received_this_month': False, 'next_date': None}

    avg_amount = round(sum(m['amount'] for m in past) / len(past), 2)
    day = int(salary_day) if salary_day else int(round(sum(m['day'] for m in past) / len(past)))
    cur = next((m for m in months if m['month'] == cur_key), None)
    received = bool(cur and cur['amount'] >= avg_amount * MIN_SALARY_FRACTION)

    base = _add_months(as_of, 1 if received else 0)
    return {
        'known': True,
        'day': day,
        'day_overridden': bool(salary_day),
        'avg_amount': avg_amount,
        'min_amount': min(m['amount'] for m in past),
        'max_amount': max(m['amount'] for m in past),
        'months': months,
        'received_this_month': received,
        'next_date': _clamp_day(base.year, base.month, day),
    }


# ── Credit cards ────────────────────────────────────────────────────────────────

def build_card_profiles(rows: list, as_of: _date) -> list:
    """
    rows: [{'date': date, 'name': str, 'amount': float}] bank-side credit-card charges.
    One profile per charging source (the normalized bank row name), over the last
    HISTORY_MONTHS completed months (the current month only tells whether it was charged).
    """
    cur_key = month_key(as_of)
    first_key = _months_back(as_of, HISTORY_MONTHS)
    sources = {}
    for r in rows:
        mk = month_key(r['date'])
        if mk < first_key:
            continue
        key = normalize_name(r['name']) or r['name']
        src = sources.setdefault(key, {'name': r['name'], 'rows': []})
        src['rows'].append(r)

    profiles = []
    for key, src in sources.items():
        per_month = {}
        for r in src['rows']:
            per_month.setdefault(month_key(r['date']), []).append(r)
        done = {mk: v for mk, v in per_month.items() if mk != cur_key}
        if len(done) < 2:
            continue   # not enough history to call it a monthly charge
        totals = [round(sum(r['amount'] for r in v), 2) for v in done.values()]
        days = [r['date'].day for v in done.values() for r in v]
        cur_rows = per_month.get(cur_key, [])
        profiles.append({
            'key': key,
            'name': src['name'],
            'day': usual_day(days),
            'avg_month': round(sum(totals) / len(totals), 2),
            'max_month': max(totals),
            'months': len(done),
            'charged_this_month': bool(cur_rows),
            'charged_this_month_amount': round(sum(r['amount'] for r in cur_rows), 2),
        })
    profiles.sort(key=lambda p: p['day'])
    return profiles


# ── Events (everything that moves the balance before the salary) ────────────────

def _dates_in_window(day: int, start_exclusive: _date, end_inclusive: _date) -> list:
    """Every date of `day` (clamped per month) with start_exclusive < date <= end_inclusive."""
    out = []
    cursor = _date(start_exclusive.year, start_exclusive.month, 1)
    while cursor <= end_inclusive:
        d = _clamp_day(cursor.year, cursor.month, day)
        if start_exclusive < d <= end_inclusive:
            out.append(d)
        cursor = _add_months(cursor, 1)
    return out


def build_card_events(profiles: list, pending: list, as_of: _date, horizon: _date, mode: str, today: _date = None) -> list:
    """
    Upcoming card charges until `horizon`.
    pending: [{'date': Charge_Date, 'amount': float}] what the cards already hold for future charge dates.
    A charge is the card's average month (or its largest month in 'max' mode), but never less
    than the pending amount belonging to it. Pending amounts that match no usual day stay as
    their own event. A card whose usual day this month passed with no charge is *late* (due now).
    """
    today = today or as_of
    events = []
    claimed = set()
    for p in profiles:
        base = p['max_month'] if mode == 'max' else p['avg_month']
        for d in _dates_in_window(p['day'], as_of, horizon):
            if d.year == as_of.year and d.month == as_of.month and p['charged_this_month']:
                continue   # this month's charge already left the account
            held = 0.0
            for i, pend in enumerate(pending):
                if i in claimed:
                    continue
                if abs((pend['date'] - d).days) <= PENDING_MATCH_DAYS:
                    held += pend['amount']
                    claimed.add(i)
            amount = max(base, held)
            events.append({'date': d, 'name': p['name'], 'amount': round(amount, 2), 'kind': 'card', 'late': False,
                           'detail': {'held': round(held, 2), 'base': round(base, 2)}})
        # the usual day passed this month with no charge: it may still come, so it is due now
        usual_this_month = _clamp_day(as_of.year, as_of.month, p['day'])
        if usual_this_month <= as_of and not p['charged_this_month']:
            events.append({'date': min(max(today, as_of), horizon), 'name': p['name'], 'amount': round(base, 2),
                           'kind': 'card', 'late': True, 'detail': {'held': 0, 'base': round(base, 2)}})
    for i, pend in enumerate(pending):
        if i in claimed or not (as_of < pend['date'] <= horizon):
            continue
        events.append({'date': pend['date'], 'name': 'חיוב כרטיס', 'amount': round(pend['amount'], 2),
                       'kind': 'card', 'late': False, 'detail': {'held': round(pend['amount'], 2), 'base': 0}})
    return events


def build_recurring_events(groups: list, as_of: _date, today: _date, horizon: _date, mode: str) -> tuple:
    """
    Upcoming charges of recurring groups that are paid straight from the bank, until `horizon`.
    groups: dicts from RecurringCharges (occurrences with 'table', 'date', 'month').
    Returns (events, skipped) — skipped lists groups left out (card-paid or stopped).

    A group whose usual day this month already passed without a payment is *late*:
    it is counted as due today, the careful choice for a bill that may still arrive.
    """
    events, skipped = [], []
    cur_key = month_key(as_of)
    for g in groups:
        occs = g.get('occurrences') or []
        if not occs:
            continue
        if g.get('possibly_stopped'):
            skipped.append({'name': g.get('name'), 'reason': 'stopped'})
            continue
        if occs[-1].get('table') != 'BankTransactions':
            skipped.append({'name': g.get('name'), 'reason': 'card'})   # inside the card charge already
            continue
        day = usual_day([_to_plain_date(o['date']).day for o in occs])
        amount = float(g.get('max_amount') if mode == 'max' else g.get('current_amount'))
        paid_this_month = any(o['month'] == cur_key for o in occs)
        is_rent = (g.get('category') == RENT_CATEGORY)
        kind = 'rent' if is_rent else 'recurring'

        for d in _dates_in_window(day, as_of, horizon):
            if d.year == as_of.year and d.month == as_of.month and paid_this_month:
                continue
            events.append({'date': d, 'name': g.get('name'), 'amount': round(amount, 2), 'kind': kind,
                           'late': False, 'group_key': g.get('group_key')})
        # usual day already passed this month with no payment: due now
        usual_this_month = _clamp_day(as_of.year, as_of.month, day)
        if usual_this_month <= as_of and not paid_this_month and as_of <= horizon:
            events.append({'date': min(max(today, as_of), horizon),
                           'name': g.get('name'), 'amount': round(amount, 2), 'kind': kind,
                           'late': True, 'group_key': g.get('group_key')})
    return events, skipped


# ── The forecast ────────────────────────────────────────────────────────────────

def compute_free_amount(balance: float, events: list, buffer: float = 0.0) -> dict:
    """
    Walks the charges in date order and returns the lowest balance reached
    (spending is assumed to happen right now) — that is the free amount, before the buffer.
    Each event gets 'balance_after' (the balance with nothing else spent).
    """
    running = balance
    lowest, lowest_at = balance, None
    for ev in sorted(events, key=lambda e: (e['date'], -e['amount'])):
        running -= ev['amount']
        ev['balance_after'] = round(running, 2)
        if running < lowest:
            lowest, lowest_at = running, ev
    free = round(lowest - buffer, 2)
    return {
        'free': free,
        'lowest_balance': round(lowest, 2),
        'tight_date': lowest_at['date'] if lowest_at else None,
        'tight_name': lowest_at['name'] if lowest_at else None,
        'shortfall': free < 0,
    }


def compute_forecast(inputs: dict, today: _date, params: dict = None) -> dict:
    """
    inputs: {'balance', 'balance_date', 'salary_rows', 'card_rows', 'pending', 'groups'}
    params: {'salary_day': int|None, 'buffer': float, 'card_mode': 'avg'|'max', 'balance': float|None}
    """
    params = params or {}
    mode = params.get('card_mode') if params.get('card_mode') in CARD_MODES else 'max'
    buffer = max(0.0, float(params.get('buffer') or 0))
    salary_day = params.get('salary_day')
    if salary_day is not None and not 1 <= int(salary_day) <= 31:
        salary_day = None

    as_of = inputs.get('balance_date') or today
    balance = params.get('balance')
    balance = float(balance) if balance not in (None, '') else float(inputs.get('balance') or 0)
    notes = []

    salary = build_salary_profile(inputs.get('salary_rows') or [], as_of, salary_day)
    if not salary['known']:
        return {'ok': False, 'reason': 'no_salary', 'today': today, 'as_of': as_of, 'balance': balance,
                'notes': ['לא נמצאו הפקדות משכורת (קטגוריית "משכורת") — תייג את המשכורת כדי לחשב.']}

    horizon = max(salary['next_date'], today)
    if salary['next_date'] < today:
        late = (today - salary['next_date']).days
        notes.append(f'המשכורת אמורה הייתה להיכנס ב-{salary["next_date"].strftime("%d/%m")} (לפני {late} ימים) ועדיין לא נקלטה — '
                     'מניחים שתיכנס היום. אם היא מאחרת, קבע יום כניסה ידני.')

    profiles = build_card_profiles(inputs.get('card_rows') or [], as_of)
    card_events = build_card_events(profiles, inputs.get('pending') or [], as_of, horizon, mode, today)
    rec_events, skipped = build_recurring_events(inputs.get('groups') or [], as_of, today, horizon, mode)
    events = card_events + rec_events
    result = compute_free_amount(balance, events, buffer)

    days_left = max(1, (horizon - today).days)
    stale_days = (today - as_of).days
    if stale_days > STALE_BALANCE_DAYS:
        notes.append(f'היתרה מעודכנת ל-{as_of.strftime("%d/%m")} (לפני {stale_days} ימים) — הורד קובץ בנק עדכני לדיוק.')
    if not profiles:
        notes.append('לא זוהו חיובי כרטיס אשראי בחשבון הבנק — חיובי כרטיס אינם נכללים בחישוב.')

    totals = {k: round(sum(e['amount'] for e in events if e['kind'] == k), 2) for k in ('card', 'recurring', 'rent')}
    totals['all'] = round(sum(totals.values()), 2)
    return {
        'ok': True,
        'today': today, 'as_of': as_of, 'balance': round(balance, 2),
        'stale_days': stale_days,
        'salary': salary,
        'horizon': horizon, 'days_left': days_left,
        'cards': profiles,
        'events': sorted(events, key=lambda e: (e['date'], -e['amount'])),
        'skipped': skipped,
        'totals': totals,
        'free': result['free'],
        'free_daily': round(result['free'] / days_left, 2) if result['free'] > 0 else 0,
        'lowest_balance': result['lowest_balance'],
        'tight_date': result['tight_date'], 'tight_name': result['tight_name'],
        'shortfall': result['shortfall'],
        'params': {'salary_day': salary['day'], 'salary_day_overridden': salary['day_overridden'],
                   'buffer': buffer, 'card_mode': mode},
        'notes': notes,
    }


# ── DB access ───────────────────────────────────────────────────────────────────

def _to_float(v):
    """Balance/amount cells may be text with thousands separators; None when unreadable."""
    try:
        return float(str(v).replace(',', '').strip())
    except (TypeError, ValueError):
        return None


def fetch_forecast_inputs(db, groups: list) -> dict:
    """Reads what the forecast needs from the DB (read-only)."""
    cutoff = _add_months(_date.today(), -(HISTORY_MONTHS + 1))
    bal_date = db.get_latest_balance_date()
    balance = _to_float(db.get_latest_Balance())

    sal = db.cursor.execute(
        "SELECT Date, Income FROM BankTransactions WHERE Category = %s AND Income > 0 AND Date >= %s",
        (SALARY_CATEGORY, cutoff)).fetchall()
    cards = db.cursor.execute(
        "SELECT Date, Name, Out FROM BankTransactions WHERE Category = %s AND Out > 0 AND Date >= %s",
        (CC_CHARGE_CATEGORY, cutoff)).fetchall()
    pend = db.cursor.execute(
        """SELECT Charge_Date, SUM(Transaction_Value) FROM CardTransactions
           WHERE Charge_Date > %s AND Transaction_Value > 0 GROUP BY Charge_Date""",
        (bal_date or _date.today(),)).fetchall()
    db.connection.commit()   # read-only, but don't leave the shared connection idle in a transaction

    return {
        'balance': balance,
        'balance_date': _to_plain_date(bal_date) if bal_date else None,
        'salary_rows': [{'date': _to_plain_date(r[0]), 'amount': float(r[1])} for r in sal],
        'card_rows': [{'date': _to_plain_date(r[0]), 'name': r[1], 'amount': float(r[2])} for r in cards],
        'pending': [{'date': _to_plain_date(r[0]), 'amount': float(r[1])} for r in pend if r[1]],
        'groups': groups,
    }


def get_forecast(db, groups: list, params: dict = None, today: _date = None) -> dict:
    """Full pipeline for the endpoint: DB inputs -> forecast."""
    return compute_forecast(fetch_forecast_inputs(db, groups), today or _date.today(), params)
