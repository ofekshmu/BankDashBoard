"""
Spending forecast — "how much can I spend until the next salary?"

Combines the bank balance, the recurring bank charges, the rent, every credit card's
own charge day and every salary stream, and works out how much money is *free* so that no
point in time before the next salary goes below zero.

Two scenarios are computed together, so switching between them in the page is only a
change of view:
  - 'max' (harsh): the latest day / lowest amount of every salary, every card at its largest
    month of the history
  - 'avg': the average day / amount of every salary, every card at its average month

Only recurring things influence the result, by the recurring-charges page's own definition
(recurring_months: at least 3 consecutive months, a stable amount, not stale). A one-off deposit
tagged as salary or a one-off payment tagged as rent is ignored.

Rules of thumb (from the last HISTORY_MONTHS months of data):
  - salaries: the deposits tagged as salary are split into streams by their day of the month
    (e.g. one on the 9th, another at the end/start of the month); the forecast ends at the
    next salary of any stream
  - each card (CardTransactions, grouped by CardID and Charge_Date) is charged on its own usual
    day of the month; once the card already holds charges for a future Charge_Date that exact date
    is used, and the charge is never below what the card holds
  - the rent category (BankTransactions tagged RENT_CATEGORY) holds several operations that repeat every
    month with the same amount (the rent, the building fee…): told apart by amount, each must be recurring
    by the recurring-charges definition, each costs its latest amount on its usual day
  - recurring charges paid straight from the bank at their usual day-of-month (those paid by card
    are already inside that card's charge)
  - anything dated up to today that the files do not show yet is assumed to have happened on its
    planned date (the files are only updated now and then): a charge is deducted, a salary is added.
    If it did not happen, the next file update shows it and the recurring analysis absorbs the change
  - spending is assumed to happen right now, so the free amount is the lowest balance reached
    along the way — the worst moment before the salary

Pure functions work on plain dicts/dates; only fetch_forecast_inputs() and
get_forecast() touch the DB.
"""
import calendar as _cal
from datetime import date as _date, timedelta as _timedelta

import statistics

from RecurringCharges import (
    month_key, _to_plain_date, RENT_CATEGORY, MIN_STREAK_MONTHS, MAX_AMOUNT_DEVIATION, MAX_RUN_COUNT,
    MAX_MONTHS_SINCE_LAST_OCCURRENCE, find_all_runs, find_longest_run, _last_complete_month_key, _months_apart,
    cluster_transactions, recurring_operations, RENT_NAME, RENT_EXTRA_NAME, STEP_CHANGE_MAX,
)

SALARY_CATEGORY = 'משכורת'
AUTO_CARD_DESCRIPTION = 'Auto Insertion'   # Card.description of a card the importer created by itself

HISTORY_MONTHS = 6             # months of history behind every rule of thumb
SALARY_LOOKBACK_DAYS = 25      # an unreceived salary older than this is not assumed to have arrived
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


def _plus_month(d: _date) -> _date:
    """The same day of the next month (the month's last day when it has fewer days)."""
    nxt = _add_months(d, 1)
    return _clamp_day(nxt.year, nxt.month, d.day)


def _history_start(as_of: _date) -> str:
    """'YYYY-MM' key of the first month of the history window (HISTORY_MONTHS months before as_of's month)."""
    return _months_back(as_of, HISTORY_MONTHS)


def _group_by_month(rows: list, key_fn=None, since_key: str = None) -> dict:
    """
    {'YYYY-MM': [rows]} in date order. The month is that of the row's date unless key_fn(row) says
    otherwise (a salary's cycle); since_key keeps only months from that key on.
    """
    key_fn = key_fn or (lambda r: month_key(r['date']))
    out = {}
    for r in sorted(rows, key=lambda r: r['date']):
        mk = key_fn(r)
        if since_key is None or mk >= since_key:
            out.setdefault(mk, []).append(r)
    return out


def _sum_amounts(rows: list) -> float:
    return round(sum(r['amount'] for r in rows), 2)


def _mean(values) -> float:
    values = list(values)
    return round(sum(values) / len(values), 2)


def _by_mode(mode: str, harsh, average):
    """The harsh scenario's figure for 'max', the average scenario's otherwise."""
    return harsh if mode == 'max' else average


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


def _is_late(day: int, as_of: _date, paid: bool) -> bool:
    """True when this month's usual day (`day`) is already behind as_of and the charge was not paid."""
    return not paid and _clamp_day(as_of.year, as_of.month, day) <= as_of


def _usual_date_this_month(day: int, as_of: _date) -> _date:
    """This month's usual date of a charge — where a late (unseen) charge is assumed to have happened."""
    return _clamp_day(as_of.year, as_of.month, day)


# ── What counts as recurring ────────────────────────────────────────────────────

def recurring_months(months: list, as_of: _date) -> list:
    """
    The recurring-charges page's own definition of "recurring" (RecurringCharges.build_group_from_cluster),
    applied to a series of months: months = [{'month': 'YYYY-MM', 'amount': float}, ...].
    Returns the months that belong to the recurring series, or [] when it is not recurring:
      - an amount deviating more than MAX_AMOUNT_DEVIATION from the median is dropped (not part of the series)
      - at least MIN_STREAK_MONTHS consecutive months remain
      - no more than MAX_RUN_COUNT separate appear/gap/reappear runs
      - the last one is at most MAX_MONTHS_SINCE_LAST_OCCURRENCE months before the last completed month
    So a one-off deposit or payment never becomes a salary, a rent or a charge of the forecast.
    """
    by_month = {}
    for m in months:
        by_month[m['month']] = max(by_month.get(m['month'], 0), m['amount'])
    if len(by_month) < MIN_STREAK_MONTHS:
        return []
    median = statistics.median(by_month.values())
    keep = sorted(mk for mk, a in by_month.items() if median <= 0 or abs(a - median) / median <= MAX_AMOUNT_DEVIATION)
    if len(keep) < MIN_STREAK_MONTHS or len(find_longest_run(keep)) < MIN_STREAK_MONTHS:
        return []
    if len(find_all_runs(keep)) > MAX_RUN_COUNT:
        return []
    if _months_apart(keep[-1], _last_complete_month_key(as_of)) > MAX_MONTHS_SINCE_LAST_OCCURRENCE:
        return []
    return [m for m in months if m['month'] in keep]


# ── Salary (one or more streams) ────────────────────────────────────────────────

def _pivot_day(days: list) -> int:
    """
    The day of the month a salary's cycle starts on, from the days its deposits arrived: the day right
    after the widest empty stretch of the (circular) month. A salary that lands between the 29th and the
    3rd gets 29, one that lands between the 6th and the 12th gets 6 — the jitter of a few days either
    way stays inside one cycle.
    """
    ds = sorted(set(days))
    n = len(ds)
    if n == 1:
        return ds[0]
    gaps = [(ds[i + 1] - ds[i]) if i < n - 1 else (ds[0] + 31 - ds[-1]) for i in range(n)]
    widest = max(range(n), key=lambda i: gaps[i])
    return ds[(widest + 1) % n]


def _position(day: int, pivot: int) -> int:
    """A day's place along a salary's cycle: days before the pivot belong to the next month (+31)."""
    return day if day >= pivot else day + 31


def _cycle_key(d: _date, pivot: int) -> str:
    """The month a deposit's cycle starts in: a deposit before the pivot day belongs to the previous month."""
    return month_key(d) if d.day >= pivot else month_key(_add_months(d, -1))


def _cycle_date(position: int, cycle_start: _date) -> _date:
    """The date of a stream's usual position in the cycle that starts in cycle_start's month."""
    if position <= 31:
        return _clamp_day(cycle_start.year, cycle_start.month, position)
    nxt = _add_months(cycle_start, 1)
    return _clamp_day(nxt.year, nxt.month, position - 31)


STREAM_NEAR_DAYS = 7           # two salary groups this close (circular day of month) may be one salary
SALARY_DAY_JITTER = 3          # a salary lands up to this many days either side of its usual date


def _circular_gap(days_a: list, days_b: list) -> int:
    """The smallest distance between a day of one list and a day of the other, on the circle of the month."""
    return min(min(abs(a - b), 31 - abs(a - b)) for a in days_a for b in days_b)


SAME_SALARY_ONE_PER_CYCLE = 0.8   # share of cycles that must hold exactly one deposit for two groups to be one salary


def _is_one_salary(a: list, b: list) -> bool:
    """
    Two groups of deposits (clustered apart by name) that are really one salary whose landing day,
    description or amount varies: close in day of month and — put together — one deposit per cycle
    (SAME_SALARY_ONE_PER_CYCLE of the cycles; one odd month is tolerated). The amount is deliberately
    not compared: pay that varies is still one salary. Two real salaries both pay in every cycle, so
    together they hold two deposits per cycle and never pass.
    """
    union = a + b
    if _circular_gap([r['date'].day for r in a], [r['date'].day for r in b]) > STREAM_NEAR_DAYS:
        return False
    pivot = _pivot_day([r['date'].day for r in union])
    per_cycle = {}
    for r in union:
        per_cycle[_cycle_key(r['date'], pivot)] = per_cycle.get(_cycle_key(r['date'], pivot), 0) + 1
    if len(per_cycle) < MIN_STREAK_MONTHS:
        return False
    singles = sum(1 for n in per_cycle.values() if n == 1)
    return singles / len(per_cycle) >= SAME_SALARY_ONE_PER_CYCLE


def _merge_same_salary(groups: list) -> list:
    """Joins the payer groups that are one salary under different names (see _is_one_salary)."""
    groups = [list(g) for g in groups]
    merged = True
    while merged:
        merged = False
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                if _is_one_salary(groups[i], groups[j]):
                    groups[i] += groups[j]
                    del groups[j]
                    merged = True
                    break
            if merged:
                break
    return groups


def _deposit_near(rows: list, d: _date, amount: float) -> bool:
    """
    True when some salary deposit (of any payer name) of about `amount` (within STEP_CHANGE_MAX — a different
    salary of another size nearby does not count) landed within SALARY_DAY_JITTER days of d.
    """
    return any(abs((r['date'] - d).days) <= SALARY_DAY_JITTER and r['amount'] >= amount * (1 - STEP_CHANGE_MAX)
               for r in rows)


def build_salary_profile(rows: list, as_of: _date, today: _date, mode: str = 'max') -> dict:
    """
    rows: [{'date': date, 'amount': float, 'name': str}] salary deposits (Income > 0 tagged as salary).

    The deposits are split into streams by who pays them (the deposit's name, clustered like the recurring
    page does — two earners → two streams, however close their days of the month are). A stream's
    month is the sum of its deposits; its day is that of the largest deposit. The harsh mode takes the
    latest position in the month and the lowest amount seen, the average mode the average of both.

    For every stream the cycles around now are checked: a cycle whose usual date is up to `today` and
    that the data does not show yet is assumed to have arrived on its date ('assumed'); the first
    usual date after `today` is an upcoming salary. next_date is the earliest upcoming one.
    """
    first_key = _history_start(as_of)
    rows = [r for r in rows if month_key(r['date']) >= first_key]
    if not rows:
        return {'known': False, 'streams': [], 'assumed': [], 'upcoming': [], 'next_date': None}

    payers = _merge_same_salary([c['members'] for c in cluster_transactions(
        [dict(r, name=r.get('name', '')) for r in rows])])
    cur_key = month_key(as_of)
    streams = []
    for mine in payers:
        pivot = _pivot_day([r['date'].day for r in mine])
        cycles = _group_by_month(mine, key_fn=lambda r: _cycle_key(r['date'], pivot))
        months = []
        for ck in sorted(cycles):
            biggest = max(cycles[ck], key=lambda r: r['amount'])
            months.append({'month': ck, 'amount': _sum_amounts(cycles[ck]),
                           'day': biggest['date'].day, 'position': _position(biggest['date'].day, pivot)})
        months = recurring_months(months, as_of)
        if not months:
            continue   # a one-off deposit tagged as salary is not a salary stream
        past = [m for m in months if m['month'] < cur_key] or months
        avg_amount = _mean(m['amount'] for m in past)
        min_amount = min(m['amount'] for m in past)
        pos_avg = int(round(_mean(m['position'] for m in past)))
        pos_max = max(m['position'] for m in past)
        position = _by_mode(mode, pos_max, pos_avg)
        names = [r.get('name', '') for r in mine]
        streams.append({
            'name': max(set(names), key=names.count),
            'day': ((position - 1) % 31) + 1, 'position': position,
            'day_avg': ((pos_avg - 1) % 31) + 1, 'day_max': ((pos_max - 1) % 31) + 1,
            'amount': _by_mode(mode, min_amount, avg_amount),
            'avg_amount': avg_amount, 'min_amount': min_amount,
            'max_amount': max(m['amount'] for m in past),
            'months': months, 'received_cycles': set(cycles),
        })
    if not streams:
        return {'known': False, 'streams': [], 'assumed': [], 'upcoming': [], 'next_date': None}
    streams.sort(key=lambda s: s['position'])

    assumed, upcoming = [], []
    for s in streams:
        for k in (-1, 0, 1, 2):
            start = _add_months(as_of, k)
            d = _cycle_date(s['position'], start)
            if month_key(start) in s['received_cycles'] or d <= as_of - _timedelta(days=SALARY_LOOKBACK_DAYS):
                continue
            if _deposit_near(rows, d, s['amount']):
                continue   # a deposit of about that size landed around that date — under another name, but it is this salary
            item = {'date': d, 'amount': s['amount'], 'day': s['day'], 'payer': s['name']}
            if d <= today:
                assumed.append(item)
            else:
                upcoming.append(item)
    upcoming.sort(key=lambda u: u['date'])
    assumed.sort(key=lambda u: u['date'])
    for s in streams:
        s.pop('received_cycles')
    return {
        'known': True, 'streams': streams, 'assumed': assumed, 'upcoming': upcoming,
        'next_date': upcoming[0]['date'] if upcoming else today + _timedelta(days=30),
        'next_amount': upcoming[0]['amount'] if upcoming else 0,
    }


# ── Credit cards (each on its own charge day) ───────────────────────────────────

def build_card_profiles(rows: list, as_of: _date) -> list:
    """
    rows: [{'card': id, 'name': str, 'date': Charge_Date, 'amount': float, 'auto': bool}] — what every
    card is charged on each Charge_Date (dates after as_of are what the card already holds).
    One profile per card with at least two completed charge months: its usual charge day, average
    and largest month over the last HISTORY_MONTHS months, whether it was charged this month, and
    the future charges it already holds.
    """
    cur_key = month_key(as_of)
    first_key = _history_start(as_of)
    cards = {}
    for r in sorted(rows, key=lambda r: r['date']):
        c = cards.setdefault(r['card'], {'name': r['name'], 'auto': bool(r.get('auto')), 'past': [], 'held': []})
        if r['date'] > as_of:
            c['held'].append(r)
        elif month_key(r['date']) >= first_key:
            c['past'].append(r)

    profiles = []
    for card, c in cards.items():
        per_month = _group_by_month(c['past'])
        done = {mk: v for mk, v in per_month.items() if mk != cur_key}
        if len(done) < 2:
            continue   # not enough history to call it a monthly charge
        totals = [_sum_amounts(v) for v in done.values()]
        profiles.append({
            'card': card,
            'name': c['name'],
            'auto': c['auto'],
            'day': usual_day([r['date'].day for r in c['past'] if month_key(r['date']) != cur_key]),
            'avg_month': _mean(totals),
            'max_month': max(totals),
            'months': len(done),
            'charged_this_month': cur_key in per_month,
            'held': c['held'],
        })
    profiles.sort(key=lambda p: p['day'])
    return profiles


def build_card_events(profiles: list, all_rows: list, as_of: _date, horizon: _date, mode: str) -> list:
    """
    Upcoming card charges until `horizon`, each card on its own day.
    For a month in which the card already holds charges, the event sits on that exact Charge_Date and
    is the card's usual amount (average / largest month) but never less than what it holds. Otherwise
    it sits on the card's usual day. A card whose usual day this month passed with no charge in the data
    is assumed charged on that day. Held charges of a card without enough history stay as events of their own.
    """
    events, profiled = [], {p['card'] for p in profiles}
    for p in profiles:
        base = _by_mode(mode, p['max_month'], p['avg_month'])
        held_by_month = _group_by_month([r for r in p['held'] if r['date'] <= horizon])
        cursor = _date(as_of.year, as_of.month, 1)
        while cursor <= horizon:
            mk = month_key(cursor)
            usual = _clamp_day(cursor.year, cursor.month, p['day'])
            is_cur = _is_current_month(cursor, as_of)
            if mk in held_by_month:
                rows = held_by_month[mk]
                held = _sum_amounts(rows)
                events.append(_card_event(p, min(r['date'] for r in rows), max(base, held), held, base))
            elif is_cur and _is_late(p['day'], as_of, p['charged_this_month']):
                events.append(_card_event(p, _usual_date_this_month(p['day'], as_of), base, 0, base))
            elif as_of < usual <= horizon and not (is_cur and p['charged_this_month']):
                events.append(_card_event(p, usual, base, 0, base))
            cursor = _add_months(cursor, 1)
    for r in all_rows:
        if r['card'] not in profiled and as_of < r['date'] <= horizon and r['amount'] > 0:
            events.append({'date': r['date'], 'name': r['name'], 'amount': round(r['amount'], 2), 'kind': 'card',
                           'detail': {'held': round(r['amount'], 2), 'base': 0, 'auto': bool(r.get('auto'))}})
    return events


def _card_event(p: dict, date: _date, amount: float, held: float, base: float) -> dict:
    """One upcoming card charge, with how much of it the card already holds."""
    return {'date': date, 'name': p['name'], 'amount': round(amount, 2), 'kind': 'card',
            'detail': {'held': round(held, 2), 'base': round(base, 2), 'day': p['day'], 'auto': p['auto']}}


# ── Rent ────────────────────────────────────────────────────────────────────────

def build_rent_profile(rows: list, as_of: _date) -> dict:
    """
    rows: [{'date': date, 'amount': float}] bank payments tagged RENT_CATEGORY.
    The category holds separate operations that repeat every month with the same amount (the rent, the
    building fee…). They are told apart by amount (RecurringCharges.recurring_operations) and each one must
    be recurring by the recurring-charges definition (recurring_months) — a one-off payment is ignored.
    Every operation costs its latest amount, due on its usual day. None when nothing recurs.

    {'amount': total per month, 'items': [{'name', 'amount', 'day', 'paid_this_month', 'monthly'}], ...}
    """
    since = _history_start(as_of)
    recent = [r for r in rows if month_key(r['date']) >= since]
    cur_key = month_key(as_of)
    items = []
    for op in recurring_operations(recent):
        series = [{'month': mk, 'amount': r['amount']} for mk, r in sorted(op['months'].items())]
        if not recurring_months(series, as_of):
            continue
        latest = op['months'][max(op['months'])]
        items.append({
            'amount': round(latest['amount'], 2),
            'day': usual_day([r['date'].day for r in sorted(op['rows'], key=lambda r: r['date'])]),
            'paid_this_month': cur_key in op['months'],
            'months': len(series),
            'monthly': series,
        })
    if not items:
        return None
    items.sort(key=lambda i: (-i['months'], -i['amount']))
    for k, it in enumerate(items):
        it['name'] = RENT_NAME if k == 0 else RENT_EXTRA_NAME if k == 1 else f"{RENT_NAME} {round(it['amount'])}"
    return {'amount': round(sum(i['amount'] for i in items), 2), 'items': items}


def build_rent_events(profile: dict, as_of: _date, horizon: _date) -> list:
    """
    Payments of every rent operation until `horizon`: the rent, the building fee… each on its usual day.
    An operation not yet paid this month whose day already passed is assumed paid on that day.
    """
    if not profile:
        return []
    events = []
    for it in profile['items']:
        def _ev(d, it=it):
            events.append({'date': d, 'name': it['name'], 'amount': it['amount'], 'kind': 'rent',
                           'detail': {'paid': it['paid_this_month']}})
        for d in _dates_in_window(it['day'], as_of, horizon):
            if not _is_current_month(d, as_of):
                _ev(d)
        usual = _usual_date_this_month(it['day'], as_of)
        if not it['paid_this_month'] and usual <= horizon:
            _ev(usual)   # before as_of: assumed paid on its day; after: still ahead
    return events


# ── Recurring charges paid from the bank ────────────────────────────────────────

def build_recurring_events(groups: list, as_of: _date, horizon: _date, mode: str) -> tuple:
    """
    Upcoming charges of recurring groups that are paid straight from the bank, until `horizon`.
    groups: dicts from RecurringCharges (occurrences with 'table', 'date', 'month').
    Returns (events, skipped) — skipped lists groups left out (card-paid, stopped, or rent, which has
    its own profile).

    A group whose usual day this month already passed without a payment in the data is assumed
    to have been paid on that day.
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
        amount = _recurring_amount(g, mode)
        paid_this_month = any(o['month'] == cur_key for o in occs)

        for d in _dates_in_window(day, as_of, horizon):
            if _is_current_month(d, as_of) and paid_this_month:
                continue
            events.append({'date': d, 'name': g.get('name'), 'amount': round(amount, 2), 'kind': 'recurring',
                           'group_key': g.get('group_key')})
        if _is_late(day, as_of, paid_this_month) and _usual_date_this_month(day, as_of) <= horizon:
            events.append({'date': _usual_date_this_month(day, as_of), 'name': g.get('name'),
                           'amount': round(amount, 2), 'kind': 'recurring', 'group_key': g.get('group_key')})
    return events, skipped


def _recurring_amount(group: dict, mode: str) -> float:
    """What a recurring group is expected to cost: its highest amount (harsh) or its latest (average)."""
    return float(_by_mode(mode, group.get('max_amount'), group.get('current_amount')))


def monthly_recurring_total(groups: list, mode: str) -> dict:
    """
    What the recurring charges paid straight from the bank cost per month (the same groups the
    forecast uses, rent aside): {'total', 'count'}. Charges paid by card are left out — they arrive
    inside the card's charge, which is only an estimate.
    """
    total, count = 0.0, 0
    for g in groups:
        occs = g.get('occurrences') or []
        if (not occs or g.get('category') == RENT_CATEGORY or g.get('possibly_stopped')
                or occs[-1].get('table') != 'BankTransactions'):
            continue
        total += _recurring_amount(g, mode)
        count += 1
    return {'total': round(total, 2), 'count': count}


# ── The forecast ────────────────────────────────────────────────────────────────

def compute_free_amount(balance: float, events: list, horizon: _date = None, today: _date = None) -> dict:
    """
    Walks the events in date order (money out are positive amounts, salaries negative) and returns the
    lowest balance reached (spending is assumed to happen right now) — that is the free amount.
    Each event gets 'balance_after' (the balance with nothing else spent), also after the salary.
    With `today`, events dated up to it have already happened (the data just doesn't show them): they
    move the starting balance ('balance_now') and are not part of the stretch measured, which only
    covers what is still ahead. With `horizon` (the next salary's date) that stretch ends there: events
    after it, and the salary arriving on it, lie beyond the money being measured.
    """
    ordered = sorted(events, key=lambda e: (e['date'], -e['amount']))
    running = balance
    for ev in ordered:
        if today is not None and ev['date'] <= today:
            running -= ev['amount']
            ev['balance_after'] = round(running, 2)
    balance_now = running
    lowest, lowest_at = balance_now, None
    for ev in ordered:
        if today is not None and ev['date'] <= today:
            continue
        running -= ev['amount']
        ev['balance_after'] = round(running, 2)
        counts = horizon is None or (ev['date'] <= horizon and not (ev['kind'] == 'income' and not ev.get('assumed')))
        if counts and running < lowest:
            lowest, lowest_at = running, ev
    return {
        'free': round(lowest, 2),
        'lowest_balance': round(lowest, 2),
        'balance_now': round(balance_now, 2),
        'tight_date': lowest_at['date'] if lowest_at else None,
        'tight_name': lowest_at['name'] if lowest_at else None,
    }


def compute_forecast(inputs: dict, today: _date, mode: str = 'max') -> dict:
    """
    One scenario. inputs: {'balance', 'balance_date', 'salary_rows', 'card_rows', 'rent_rows', 'groups'}.
    The free amount here ignores any buffer — the page subtracts it (free = lowest_balance − buffer).
    Every event dated up to `today` carries assumed=True (taken as done on its date though the files
    do not show it yet).
    """
    mode = mode if mode in MODES else 'max'
    as_of = inputs.get('balance_date') or today
    balance = float(inputs.get('balance') or 0)
    notes = []

    salary = build_salary_profile(inputs.get('salary_rows') or [], as_of, today, mode)
    if not salary['known']:
        return {'ok': False, 'reason': 'no_salary',
                'notes': ['לא זוהתה משכורת חוזרת (קטגוריית "משכורת", לפחות 3 חודשים ברצף) — תייג את המשכורת כדי לחשב.']}

    horizon = salary['next_date']
    chart_end = _plus_month(today)           # the chart always looks a month ahead of today
    window_end = max(horizon, chart_end)
    card_rows = inputs.get('card_rows') or []
    profiles = build_card_profiles(card_rows, as_of)
    card_events = build_card_events(profiles, card_rows, as_of, window_end, mode)
    rent = build_rent_profile(inputs.get('rent_rows') or [], as_of)
    rent_events = build_rent_events(rent, as_of, window_end)
    rec_events, skipped = build_recurring_events(inputs.get('groups') or [], as_of, window_end, mode)
    income_events = [{'date': a['date'], 'name': f'משכורת (יום {a["day"]})', 'amount': -a['amount'], 'kind': 'income',
                      'detail': {'payer': a['payer']}}
                     for a in salary['assumed'] + [u for u in salary['upcoming'] if u['date'] <= window_end]]
    events = card_events + rent_events + rec_events + income_events
    for e in events:
        e['assumed'] = e['date'] <= today
        e['after_salary'] = e['date'] > horizon
    result = compute_free_amount(balance, events, horizon, today)
    to_salary = [e for e in events if not e['after_salary']]   # what the free amount is measured against

    stale_days = (today - as_of).days
    if stale_days > STALE_BALANCE_DAYS:
        notes.append(f'היתרה מעודכנת ל-{as_of.strftime("%d/%m")} (לפני {stale_days} ימים). פעולות עד היום שטרם נקלטו בקבצים '
                     'מחושבות כאילו בוצעו במועדן.')
    if not profiles:
        notes.append('לא זוהו חיובי כרטיס אשראי — חיובי כרטיס אינם נכללים בחישוב.')
    if not rent:
        notes.append('לא זוהתה שכירות חוזרת (קטגוריית "שכירות", לפחות 3 חודשים ברצף) — השכירות אינה נכללת בחישוב.')

    totals = {k: round(sum(e['amount'] for e in to_salary if e['kind'] == k), 2) for k in ('card', 'recurring', 'rent')}
    totals['all'] = round(sum(totals.values()), 2)
    # what is known for sure (charges a card already holds) versus what is an estimate (everything projected)
    totals['known'] = round(sum(e['detail']['held'] for e in to_salary if e['kind'] == 'card'), 2)
    totals['estimated'] = round(totals['all'] - totals['known'], 2)
    recurring = monthly_recurring_total(inputs.get('groups') or [], mode)
    fixed_monthly = {'recurring': recurring['total'], 'count': recurring['count'],
                     'rent': rent['amount'] if rent else 0, 'total': round(recurring['total'] + (rent['amount'] if rent else 0), 2)}
    return {
        'ok': True,
        'mode': mode,
        'salary': salary,
        'horizon': horizon, 'chart_end': chart_end, 'days_left': max(1, (horizon - today).days),
        'cards': [{k: v for k, v in p.items() if k != 'held'} for p in profiles],
        'rent': rent,
        'events': sorted(events, key=lambda e: (e['date'], -e['amount'])),
        'skipped': skipped,
        'totals': totals, 'fixed_monthly': fixed_monthly,
        'free': result['free'], 'lowest_balance': result['lowest_balance'], 'balance_now': result['balance_now'],
        'tight_date': result['tight_date'], 'tight_name': result['tight_name'],
        'notes': notes,
    }


def compute_both(inputs: dict, today: _date) -> dict:
    """Both scenarios at once, so the page switches between them without asking again."""
    as_of = inputs.get('balance_date') or today
    return {
        'ok': True,
        'today': today, 'as_of': as_of,
        'balance': round(float(inputs.get('balance') or 0), 2),
        'stale_days': (today - as_of).days,
        'scenarios': {m: compute_forecast(inputs, today, m) for m in MODES},
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
        "SELECT Date, Income, Name FROM BankTransactions WHERE Category = %s AND Income > 0 AND Date >= %s",
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
    descriptions = {r[0]: (r[1] or '').strip()
                    for r in db.cursor.execute("SELECT CardID, description FROM Card").fetchall()}
    db.connection.commit()   # read-only, but don't leave the shared connection idle in a transaction

    def _card_label(card_id):
        """(display name, created-by-the-importer flag). The importer's own placeholder text is not shown."""
        desc = descriptions.get(card_id, '')
        auto = desc == AUTO_CARD_DESCRIPTION
        return f'כרטיס {str(card_id).strip()}' + (f' · {desc}' if desc and not auto else ''), auto

    card_rows = []
    for r in cards:
        name, auto = _card_label(r[0])
        card_rows.append({'card': str(r[0]).strip(), 'name': name, 'auto': auto,
                          'date': _to_plain_date(r[1]), 'amount': float(r[2] or 0)})
    return {
        'balance': balance,
        'balance_date': _to_plain_date(bal_date) if bal_date else None,
        'salary_rows': [{'date': _to_plain_date(r[0]), 'amount': float(r[1]), 'name': r[2] or ''} for r in sal],
        'rent_rows': [{'date': _to_plain_date(r[0]), 'amount': float(r[1])} for r in rent],
        'card_rows': card_rows,
        'groups': groups,
    }


def get_forecast(db, groups: list, today: _date = None) -> dict:
    """Full pipeline for the endpoint: DB inputs -> both scenarios."""
    return compute_both(fetch_forecast_inputs(db, groups), today or _date.today())
