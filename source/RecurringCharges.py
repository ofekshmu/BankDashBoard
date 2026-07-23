"""
Recurring Charges — detection algorithm and stats.

Pure functions operate on plain dicts with keys:
  table, id, date (datetime.date), name, amount (positive float), category
No DB access except in get_recurring_groups() and fetch_candidate_transactions()
at the bottom.
"""
import re
import statistics
import calendar as _cal
from datetime import date as _date, timedelta as _timedelta
from difflib import SequenceMatcher

SIMILARITY_THRESHOLD = 0.82
AMOUNT_CHANGE_THRESHOLD = 0.15
MIN_STREAK_MONTHS = 3


def _excluded_categories() -> set:
    """Categories excluded from recurring-charge candidacy: reserved
    withdrawal/excluded categories (Constants.ReservedNames), plus housing/
    mortgage (already tracked on the Housing page — the real housing
    category is the property's own address string, e.g. MORTGAGE_CATEGORY
    in src_utils/mortgage.py, not a generic "Rent" label)."""
    cats = set()
    try:
        from Constants import ReservedNames
        cats.add(ReservedNames.WHITDRAWAL_CATEGORY)
        cats.add(ReservedNames.EXCLUDED_CATEGORY)
    except Exception:
        cats.update({'withdrawal', 'Excluded'})
    try:
        from src_utils.mortgage import MORTGAGE_CATEGORY
        cats.add(MORTGAGE_CATEGORY)
    except Exception:
        pass
    # "דירת קבלן" (contractor's apartment — a new-build property paid off in
    # installments) and "שכירות" (rent) are additional housing categories also
    # tracked on the Housing page, separate from MORTGAGE_CATEGORY.
    cats.add('דירת קבלן')
    cats.add('שכירות')
    return cats


EXCLUDED_CATEGORIES = _excluded_categories()


# ── Name normalization + clustering ────────────────────────────────────────────

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


# ── Month arithmetic ────────────────────────────────────────────────────────────

def month_key(d: _date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _parse_month_key(mk: str) -> _date:
    y, m = mk.split('-')
    return _date(int(y), int(m), 1)


def _months_apart(a: str, b: str) -> int:
    da, db = _parse_month_key(a), _parse_month_key(b)
    return (db.year - da.year) * 12 + (db.month - da.month)


def _last_complete_month_key(today: _date) -> str:
    """The most recently fully-completed calendar month relative to today."""
    first_of_this_month = today.replace(day=1)
    prev_month_last_day = first_of_this_month - _timedelta(days=1)
    return month_key(prev_month_last_day)


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


# ── Group stats + alerts ────────────────────────────────────────────────────────

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


# ── Candidate pool + DB orchestration ───────────────────────────────────────────

def fetch_candidate_transactions(db, months_back: int = 13) -> list:
    """
    Pull expense transactions (bank Out>0, card Charge_Value>0) from the last
    `months_back` months, excluding withdrawal/excluded/housing categories and
    anything in RecurringExcludedTransactions.
    Returns list of dicts: table, id, date, name, amount, category.
    """
    cutoff = _date.today().replace(day=1) - _timedelta(days=months_back * 31)
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
