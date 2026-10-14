"""
Spending forecast — "how much can I spend until the next salary?"

Combines the bank balance, the recurring bank charges, the rent, every credit card's
own charge day and the salary date, and works out how much money is *free* so that no
point in time before the next salary goes below zero.

Two scenarios are computed together, so switching between them in the page is only a
change of view:
  - 'max' (harsh): the latest salary day / lowest salary seen, every card at its largest
    month of the history, the rent at its highest of the last three months
  - 'avg': the average salary day / amount, every card at its average month, the latest rent

Rules of thumb (from the last HISTORY_MONTHS months of data):
  - each card (CardTransactions, grouped by CardID and Charge_Date) is charged on its own usual
    day of the month; once the card already holds charges for a future Charge_Date that exact date
    is used, and the charge is never below what the card holds
  - the rent (BankTransactions tagged RENT_CATEGORY, read directly — it does not depend on the
    recurring-charge detection) is due on its usual day; what was already paid this month is deducted
  - recurring charges paid straight from the bank at their usual day-of-month (those paid by card
    are already inside that card's charge)
  - spending is assumed to happen right now, so the free amount is the lowest balance reached
    along the way — the worst moment before the salary

Pure functions work on plain dicts/dates; only fetch_forecast_inputs() and
get_forecast() touch the DB.
"""
import calendar as _cal
from datetime import date as _date

from RecurringCharges import month_key, _to_plain_date, RENT_CATEGORY

SALARY_CATEGORY = 'משכורת'

HISTORY_MONTHS = 6             # months of history behind every rule of thumb
MIN_SALARY_FRACTION = 0.5      # a deposit below this share of the usual salary is not "the salary"
RENT_PAID_FRACTION = 0.9       # this share of the rent paid this month counts as "paid in full"
STALE_BALANCE_DAYS = 3         # the balance is flagged old when it is older than this
MODES = ('avg', 'max')


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
    """
    The usual day-of-month of a charge, from days listed oldest first: the most common
    day (ties: the larger), or the latest day when none repeats — never an average.
    """
    if not days:
        return 1
    counts = {}
    for d in days:
        counts[d] = counts.get(d, 0) + 1
    best = max(counts.values())
    if best > 1:
        return max(d for d, c in counts.items() if c == best)
    return days[-1]


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


def _is_current_month(d: _date, as_of: _date) -> bool:
    return d.year == as_of.year and d.month == as_of.month


def _due_now(today: _date, as_of: _date, horizon: _date) -> _date:
    """The date given to a charge that is late (its usual day passed unpaid): right now."""
    return min(max(today, as_of), horizon)


# ── Salary ──────────────────────────────────────────────────────────────────────

def build_salary_profile(rows: list, as_of: _date, mode: str = 'max') -> dict:
    """
    rows: [{'date': date, 'amount': float}] salary deposits (Income > 0 tagged as salary).
    Returns the salary rule of thumb plus when the next salary is expected.

    A month's salary is the sum of its deposits; its day is the day of the largest deposit.
    The harsh mode takes the latest day and the lowest amount seen, the average mode the
    average of both. 'received_this_month' is true once the current month holds a deposit of
    at least MIN_SALARY_FRACTION of the usual amount.
    """
    first_key = _months_back(as_of, HISTORY_MONTHS)
    by_month = {}
    for r in rows:
        mk = month_key(r['date'])
        if mk >= first_key:
            by_month.setdefault(mk, []).append(r)

    months = []
    for mk in sorted(by_month):
        biggest = max(by_month[mk], key=lambda r: r['amount'])
        months.append({'month': mk, 'amount': round(sum(r['amount'] for r in by_month[mk]), 2),
                       'day': biggest['date'].day})

    cur_key = month_key(as_of)
    past = [m for m in months if m['month'] != cur_key] or months
    if not past:
        return {'known': False, 'months': [], 'received_this_month': False, 'next_date': None}

    avg_amount = round(sum(m['amount'] for m in past) / len(past), 2)
    min_amount = min(m['amount'] for m in past)
    day_avg = int(round(sum(m['day'] for m in past) / len(past)))
    day_max = max(m['day'] for m in past)
    day = day_max if mode == 'max' else day_avg
    cur = next((m for m in months if m['month'] == cur_key), None)
    received = bool(cur and cur['amount'] >= avg_amount * MIN_SALARY_FRACTION)

    base = _add_months(as_of, 1 if received else 0)
    return {
        'known': True,
        'day': day, 'day_avg': day_avg, 'day_max': day_max,
        'amount': min_amount if mode == 'max' else avg_amount,
        'avg_amount': avg_amount, 'min_amount': min_amount,
        'max_amount': max(m['amount'] for m in past),
        'months': months,
        'received_this_month': received,
        'next_date': _clamp_day(base.year, base.month, day),
    }


# ── Credit cards (each on its own charge day) ───────────────────────────────────

def build_card_profiles(rows: list, as_of: _date) -> list:
    """
    rows: [{'card': id, 'name': str, 'date': Charge_Date, 'amount': float}] — what every card is
    charged on each Charge_Date (dates after as_of are what the card already holds).
    One profile per card with at least two completed charge months: its usual charge day, average
    and largest month over the last HISTORY_MONTHS months, whether it was charged this month, and
    the future charges it already holds.
    """
    cur_key = month_key(as_of)
    first_key = _months_back(as_of, HISTORY_MONTHS)
    cards = {}
    for r in sorted(rows, key=lambda r: r['date']):
        c = cards.setdefault(r['card'], {'name': r['name'], 'past': [], 'held': []})
        if r['date'] > as_of:
            c['held'].append(r)
        elif month_key(r['date']) >= first_key:
            c['past'].append(r)

    profiles = []
    for card, c in cards.items():
        per_month = {}
        for r in c['past']:
            per_month.setdefault(month_key(r['date']), []).append(r)
        done = {mk: v for mk, v in per_month.items() if mk != cur_key}
        if len(done) < 2:
            continue   # not enough history to call it a monthly charge
        totals = [round(sum(r['amount'] for r in v), 2) for v in done.values()]
        profiles.append({
            'card': card,
            'name': c['name'],
            'day': usual_day([r['date'].day for r in c['past'] if month_key(r['date']) != cur_key]),
            'avg_month': round(sum(totals) / len(totals), 2),
            'max_month': max(totals),
            'months': len(done),
            'charged_this_month': cur_key in per_month,
            'held': c['held'],
        })
    profiles.sort(key=lambda p: p['day'])
    return profiles


def build_card_events(profiles: list, all_rows: list, as_of: _date, horizon: _date, mode: str,
                      today: _date = None) -> list:
    """
    Upcoming card charges until `horizon`, each card on its own day.
    For a month in which the card already holds charges, the event sits on that exact Charge_Date and
    is the card's usual amount (average / largest month) but never less than what it holds. Otherwise
    it sits on the card's usual day. A card whose usual day this month passed with no charge is *late*
    (due now). Held charges of a card without enough history stay as events of their own.
    """
    today = today or as_of
    events, profiled = [], {p['card'] for p in profiles}
    for p in profiles:
        base = p['max_month'] if mode == 'max' else p['avg_month']
        held_by_month = {}
        for r in p['held']:
            if r['date'] <= horizon:
                held_by_month.setdefault(month_key(r['date']), []).append(r)
        cursor = _date(as_of.year, as_of.month, 1)
        while cursor <= horizon:
            mk = month_key(cursor)
            usual = _clamp_day(cursor.year, cursor.month, p['day'])
            is_cur = _is_current_month(cursor, as_of)
            if mk in held_by_month:
                rows = held_by_month[mk]
                held = round(sum(r['amount'] for r in rows), 2)
                events.append(_card_event(p, min(r['date'] for r in rows), max(base, held), held, base, False))
            elif is_cur and not p['charged_this_month'] and usual <= as_of:
                events.append(_card_event(p, _due_now(today, as_of, horizon), base, 0, base, True))
            elif as_of < usual <= horizon and not (is_cur and p['charged_this_month']):
                events.append(_card_event(p, usual, base, 0, base, False))
            cursor = _add_months(cursor, 1)
    for r in all_rows:
        if r['card'] not in profiled and as_of < r['date'] <= horizon and r['amount'] > 0:
            events.append({'date': r['date'], 'name': r['name'], 'amount': round(r['amount'], 2), 'kind': 'card',
                           'late': False, 'detail': {'held': round(r['amount'], 2), 'base': 0}})
    return events


def _card_event(p: dict, date: _date, amount: float, held: float, base: float, late: bool) -> dict:
    """One upcoming card charge, with how much of it the card already holds."""
    return {'date': date, 'name': p['name'], 'amount': round(amount, 2), 'kind': 'card', 'late': late,
            'detail': {'held': round(held, 2), 'base': round(base, 2), 'day': p['day']}}


# ── Rent ────────────────────────────────────────────────────────────────────────

def build_rent_profile(rows: list, as_of: _date, mode: str, override: float = None) -> dict:
    """
    rows: [{'date': date, 'amount': float}] bank payments tagged RENT_CATEGORY.
    The rent is the latest month's total (harsh mode: the highest of the last three months with
    payments); `override` (rent + building fee as the user knows it) replaces the amount. Returns
    None when there is neither history nor an override.
    """
    first_key = _months_back(as_of, HISTORY_MONTHS)
    per_month = {}
    for r in sorted(rows, key=lambda r: r['date']):
        if month_key(r['date']) >= first_key:
            per_month.setdefault(month_key(r['date']), []).append(r)
    if not per_month and not override:
        return None

    totals = {mk: round(sum(r['amount'] for r in v), 2) for mk, v in per_month.items()}
    keys = sorted(totals)
    detected = (max(totals[k] for k in keys[-3:]) if mode == 'max' else totals[keys[-1]]) if keys else 0
    amount = float(override) if override else detected
    days = [r['date'].day for mk in keys for r in per_month[mk]]
    return {
        'amount': round(amount, 2),
        'detected': round(detected, 2),
        'overridden': bool(override),
        'day': usual_day(days) if days else 1,
        'paid_this_month': totals.get(month_key(as_of), 0.0),
        'months': len(keys),
    }


def build_rent_events(profile: dict, as_of: _date, today: _date, horizon: _date) -> list:
    """
    Rent payments until `horizon`. This month only what is still unpaid counts (the part already
    paid is deducted; a rent paid to RENT_PAID_FRACTION is paid in full); an unpaid rent whose day
    passed is late — due now.
    """
    if not profile:
        return []
    amount, paid = profile['amount'], profile['paid_this_month']
    events = []

    def _ev(d, value, late):
        events.append({'date': d, 'name': 'שכירות + ועד בית', 'amount': round(value, 2), 'kind': 'rent',
                       'late': late, 'detail': {'paid': paid, 'source': 'override' if profile['overridden'] else 'data'}})

    for d in _dates_in_window(profile['day'], as_of, horizon):
        if not _is_current_month(d, as_of):
            _ev(d, amount, False)
    remaining = amount - paid
    if remaining > 0 and paid < amount * RENT_PAID_FRACTION:
        usual = _clamp_day(as_of.year, as_of.month, profile['day'])
        if usual > as_of:
            if usual <= horizon:
                _ev(usual, remaining, False)
        elif as_of <= horizon:
            _ev(_due_now(today, as_of, horizon), remaining, True)
    return events


# ── Recurring charges paid from the bank ────────────────────────────────────────

def build_recurring_events(groups: list, as_of: _date, today: _date, horizon: _date, mode: str) -> tuple:
    """
    Upcoming charges of recurring groups that are paid straight from the bank, until `horizon`.
    groups: dicts from RecurringCharges (occurrences with 'table', 'date', 'month').
    Returns (events, skipped) — skipped lists groups left out (card-paid, stopped, or rent, which has
    its own profile).

    A group whose usual day this month already passed without a payment is *late*:
    it is counted as due now, the careful choice for a bill that may still arrive.
    """
    events, skipped = [], []
    cur_key = month_key(as_of)
    for g in groups:
        occs = g.get('occurrences') or []
        if not occs:
            continue
        if g.get('category') == RENT_CATEGORY:
            skipped.append({'name': g.get('name'), 'reason': 'rent'})
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

        for d in _dates_in_window(day, as_of, horizon):
            if _is_current_month(d, as_of) and paid_this_month:
                continue
            events.append({'date': d, 'name': g.get('name'), 'amount': round(amount, 2), 'kind': 'recurring',
                           'late': False, 'group_key': g.get('group_key')})
        usual_this_month = _clamp_day(as_of.year, as_of.month, day)
        if usual_this_month <= as_of and not paid_this_month and as_of <= horizon:
            events.append({'date': _due_now(today, as_of, horizon), 'name': g.get('name'),
                           'amount': round(amount, 2), 'kind': 'recurring', 'late': True,
                           'group_key': g.get('group_key')})
    return events, skipped


# ── The forecast ────────────────────────────────────────────────────────────────

def compute_free_amount(balance: float, events: list) -> dict:
    """
    Walks the charges in date order and returns the lowest balance reached
    (spending is assumed to happen right now) — that is the free amount.
    Each event gets 'balance_after' (the balance with nothing else spent).
    """
    running = balance
    lowest, lowest_at = balance, None
    for ev in sorted(events, key=lambda e: (e['date'], -e['amount'])):
        running -= ev['amount']
        ev['balance_after'] = round(running, 2)
        if running < lowest:
            lowest, lowest_at = running, ev
    return {
        'free': round(lowest, 2),
        'lowest_balance': round(lowest, 2),
        'tight_date': lowest_at['date'] if lowest_at else None,
        'tight_name': lowest_at['name'] if lowest_at else None,
    }


def compute_forecast(inputs: dict, today: _date, mode: str = 'max', rent_override: float = None) -> dict:
    """
    One scenario. inputs: {'balance', 'balance_date', 'salary_rows', 'card_rows', 'rent_rows', 'groups'}.
    The free amount here ignores any buffer / manual balance — the page applies both on top
    (free = lowest_balance + (manual balance − balance) − buffer).
    """
    mode = mode if mode in MODES else 'max'
    as_of = inputs.get('balance_date') or today
    balance = float(inputs.get('balance') or 0)
    notes = []

    salary = build_salary_profile(inputs.get('salary_rows') or [], as_of, mode)
    if not salary['known']:
        return {'ok': False, 'reason': 'no_salary',
                'notes': ['לא נמצאו הפקדות משכורת (קטגוריית "משכורת") — תייג את המשכורת כדי לחשב.']}

    horizon = max(salary['next_date'], today)
    if salary['next_date'] < today:
        late = (today - salary['next_date']).days
        notes.append(f'המשכורת אמורה הייתה להיכנס ב-{salary["next_date"].strftime("%d/%m")} (לפני {late} ימים) ועדיין לא נקלטה — '
                     'מניחים שתיכנס היום.')

    card_rows = inputs.get('card_rows') or []
    profiles = build_card_profiles(card_rows, as_of)
    card_events = build_card_events(profiles, card_rows, as_of, horizon, mode, today)
    rent = build_rent_profile(inputs.get('rent_rows') or [], as_of, mode, rent_override)
    rent_events = build_rent_events(rent, as_of, today, horizon)
    rec_events, skipped = build_recurring_events(inputs.get('groups') or [], as_of, today, horizon, mode)
    events = card_events + rent_events + rec_events
    result = compute_free_amount(balance, events)

    stale_days = (today - as_of).days
    if stale_days > STALE_BALANCE_DAYS:
        notes.append(f'היתרה מעודכנת ל-{as_of.strftime("%d/%m")} (לפני {stale_days} ימים) — הורד קובץ בנק עדכני לדיוק.')
    if not profiles:
        notes.append('לא זוהו חיובי כרטיס אשראי — חיובי כרטיס אינם נכללים בחישוב.')
    if not rent:
        notes.append('לא נמצאה שכירות (קטגוריית "שכירות") — הזן שכירות + ועד בית ידנית.')

    totals = {k: round(sum(e['amount'] for e in events if e['kind'] == k), 2) for k in ('card', 'recurring', 'rent')}
    totals['all'] = round(sum(totals.values()), 2)
    return {
        'ok': True,
        'mode': mode,
        'salary': salary,
        'horizon': horizon, 'days_left': max(1, (horizon - today).days),
        'cards': [{k: v for k, v in p.items() if k != 'held'} for p in profiles],
        'rent': rent,
        'events': sorted(events, key=lambda e: (e['date'], -e['amount'])),
        'skipped': skipped,
        'totals': totals,
        'free': result['free'], 'lowest_balance': result['lowest_balance'],
        'tight_date': result['tight_date'], 'tight_name': result['tight_name'],
        'notes': notes,
    }


def compute_both(inputs: dict, today: _date, rent_override: float = None) -> dict:
    """Both scenarios at once, so the page switches between them without asking again."""
    as_of = inputs.get('balance_date') or today
    return {
        'ok': True,
        'today': today, 'as_of': as_of,
        'balance': round(float(inputs.get('balance') or 0), 2),
        'stale_days': (today - as_of).days,
        'scenarios': {m: compute_forecast(inputs, today, m, rent_override) for m in MODES},
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
    from Constants import ReservedNames
    cutoff = _add_months(_date.today(), -(HISTORY_MONTHS + 1))
    bal_date = db.get_latest_balance_date()
    balance = _to_float(db.get_latest_Balance())

    sal = db.cursor.execute(
        "SELECT Date, Income FROM BankTransactions WHERE Category = %s AND Income > 0 AND Date >= %s",
        (SALARY_CATEGORY, cutoff)).fetchall()
    rent = db.cursor.execute(
        "SELECT Date, Out FROM BankTransactions WHERE Category = %s AND Out > 0 AND Date >= %s",
        (RENT_CATEGORY, cutoff)).fetchall()
    # What each card is charged per Charge_Date, withdrawals left out (the bank debit of those is separate).
    # A refund (negative value) lowers the charge, like SimpleMath.process_prices does.
    cards = db.cursor.execute(
        """SELECT CardID, Charge_Date,
                  SUM(CASE WHEN Charge_Value < 0 OR Transaction_Value < 0 THEN -ABS(Transaction_Value)
                           ELSE Transaction_Value END)
           FROM CardTransactions
           WHERE Charge_Date IS NOT NULL AND Charge_Date >= %s
             AND (Category IS NULL OR Category <> %s)
           GROUP BY CardID, Charge_Date""",
        (cutoff, ReservedNames.WHITDRAWAL_CATEGORY)).fetchall()
    names = {r[0]: r[1] for r in db.cursor.execute("SELECT CardID, description FROM Card").fetchall()}
    db.connection.commit()   # read-only, but don't leave the shared connection idle in a transaction

    def _card_name(card_id):
        desc = (names.get(card_id) or '').strip()
        return f'כרטיס {str(card_id).strip()}' + (f' · {desc}' if desc else '')

    return {
        'balance': balance,
        'balance_date': _to_plain_date(bal_date) if bal_date else None,
        'salary_rows': [{'date': _to_plain_date(r[0]), 'amount': float(r[1])} for r in sal],
        'rent_rows': [{'date': _to_plain_date(r[0]), 'amount': float(r[1])} for r in rent],
        'card_rows': [{'card': str(r[0]).strip(), 'name': _card_name(r[0]), 'date': _to_plain_date(r[1]),
                       'amount': float(r[2] or 0)} for r in cards],
        'groups': groups,
    }


def get_forecast(db, groups: list, rent_override: float = None, today: _date = None) -> dict:
    """Full pipeline for the endpoint: DB inputs -> both scenarios."""
    return compute_both(fetch_forecast_inputs(db, groups), today or _date.today(), rent_override)
