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
MAX_AMOUNT_DEVIATION = 0.50   # an occurrence deviating more than this from the
                              # group's median likely belongs to a different
                              # bill entirely (or isn't a fixed bill at all) —
                              # dropped from the group rather than merely flagged
MAX_CHANGED_FRACTION = 0.40   # if more than this fraction of occurrences show
                              # "amount changed", it reads as general repeat
                              # spending at the same business, not a fixed bill
MAX_RUN_COUNT = 3             # more than this many separate appear/gap/reappear
                              # cycles is too fragmented to be a real recurring bill
MAX_MONTHS_SINCE_LAST_OCCURRENCE = 6   # a bill not seen in more than this many
                                        # months is no longer considered recurring


def _excluded_categories() -> set:
    """Categories excluded from recurring-charge candidacy: reserved
    withdrawal/excluded categories (Constants.ReservedNames), plus housing/
    mortgage (already tracked on the Housing page — the real housing
    category is the property's own address string, e.g. MORTGAGE_CATEGORY
    in src_utils/mortgage.py, not a generic "Rent" label)."""
    cats = set()
    try:
        from Constants import ReservedNames, CC_CHARGE_CATEGORY_NAME
        cats.add(ReservedNames.WHITDRAWAL_CATEGORY)
        cats.add(ReservedNames.EXCLUDED_CATEGORY)
        cats.add(CC_CHARGE_CATEGORY_NAME)  # "אשראי" — never a recurring-billing candidate
    except Exception:
        cats.update({'withdrawal', 'Excluded', 'אשראי'})
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


def find_all_runs(months_sorted: list) -> list:
    """months_sorted: sorted list of distinct 'YYYY-MM' strings.
    Returns every run of consecutive months, in order (each a list of month keys)."""
    if not months_sorted:
        return []
    runs = []
    cur_run = [months_sorted[0]]
    for i in range(1, len(months_sorted)):
        if _months_apart(months_sorted[i - 1], months_sorted[i]) == 1:
            cur_run.append(months_sorted[i])
        else:
            runs.append(cur_run)
            cur_run = [months_sorted[i]]
    runs.append(cur_run)
    return runs


def find_longest_run(months_sorted: list) -> list:
    """months_sorted: sorted list of distinct 'YYYY-MM' strings.
    Returns the longest run of consecutive months anywhere in the list."""
    runs = find_all_runs(months_sorted)
    if not runs:
        return []
    return max(runs, key=len)


# ── Group stats + alerts ────────────────────────────────────────────────────────

def build_group_from_cluster(cluster: dict, today: _date) -> dict:
    """
    Given a cluster (from cluster_transactions), compute whether it qualifies
    as a recurring group, and if so return its full stats/occurrence/alert
    payload. Returns None if it doesn't qualify.

    Qualification, beyond the basic 3-consecutive-month streak, also weeds out
    clusters that read as general repeat spending at the same business rather
    than a fixed recurring bill:
      - Rule 1 (amount ceiling): an occurrence deviating more than
        MAX_AMOUNT_DEVIATION from the group's median is dropped from the
        group entirely — it likely belongs to a different bill, or isn't a
        fixed bill at all (e.g. a one-off larger purchase at a business you
        also pay a smaller fixed amount to monthly).
      - Rule 2 (too many changed): if more than MAX_CHANGED_FRACTION of the
        remaining occurrences still show an "amount changed" deviation
        (AMOUNT_CHANGE_THRESHOLD), the amounts are too unstable to be a fixed
        bill (a single clean price rise stays well under this fraction).
      - Rule 3 (too fragmented): if the remaining occurrences break into more
        than MAX_RUN_COUNT separate appear/gap/reappear runs, the pattern is
        too sporadic to be a real recurring bill (e.g. a plant nursery you
        buy from now and then, not a fixed monthly charge).
      - Rule 4 (stale): if the last occurrence is more than
        MAX_MONTHS_SINCE_LAST_OCCURRENCE months before the most recently
        completed calendar month, it's no longer a *current* recurring bill
        even if it clearly was one in the past.
    """
    members = cluster['members']
    by_month = {}
    for m in members:
        mk = month_key(m['date'])
        # keep the largest-amount occurrence if more than one in the same month
        if mk not in by_month or m['amount'] > by_month[mk]['amount']:
            by_month[mk] = m

    distinct_months = sorted(by_month.keys())
    if len(distinct_months) < MIN_STREAK_MONTHS:
        return None

    # Rule 1: drop occurrences that deviate too wildly from the group's median.
    raw_amounts = [by_month[mk]['amount'] for mk in distinct_months]
    raw_median = statistics.median(raw_amounts)
    if raw_median > 0:
        distinct_months = [
            mk for mk in distinct_months
            if abs(by_month[mk]['amount'] - raw_median) / raw_median <= MAX_AMOUNT_DEVIATION
        ]
    if len(distinct_months) < MIN_STREAK_MONTHS:
        return None

    longest_run = find_longest_run(distinct_months)
    if len(longest_run) < MIN_STREAK_MONTHS:
        return None

    # Rule 3: too many separate appear/gap/reappear cycles.
    if len(find_all_runs(distinct_months)) > MAX_RUN_COUNT:
        return None

    amounts = [by_month[mk]['amount'] for mk in distinct_months]
    median_amount = statistics.median(amounts)

    occurrences = []
    changed_count = 0
    for mk in distinct_months:
        tx = by_month[mk]
        deviates = (
            median_amount > 0
            and abs(tx['amount'] - median_amount) / median_amount > AMOUNT_CHANGE_THRESHOLD
        )
        if deviates:
            changed_count += 1
        occurrences.append({
            'month': mk,
            'date': tx['date'],
            'amount': tx['amount'],
            'table': tx['table'],
            'id': tx['id'],
            'name': tx['name'],
            'status': 'changed' if deviates else 'paid',
        })

    # Rule 2: too many "amount changed" months relative to group size.
    if changed_count / len(occurrences) > MAX_CHANGED_FRACTION:
        return None

    last_month = distinct_months[-1]
    last_complete = _last_complete_month_key(today)
    months_since_last = _months_apart(last_month, last_complete)
    possibly_stopped = months_since_last > 0

    # Rule 4: hasn't been seen in too long — no longer a *current* recurring
    # bill, even if it clearly was one in the past.
    if months_since_last > MAX_MONTHS_SINCE_LAST_OCCURRENCE:
        return None

    # day-of-month mode, for next-expected estimate — only over the
    # (Rule-1-filtered) months that actually count toward this group
    days = [by_month[mk]['date'].day for mk in distinct_months]
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

def _to_plain_date(value):
    """Normalize a DB date value (date, datetime, pandas Timestamp, or string) to datetime.date."""
    import datetime as _dt_mod
    if isinstance(value, _dt_mod.datetime):
        return value.date()
    if isinstance(value, _dt_mod.date):
        return value
    import pandas as pd
    return pd.to_datetime(value).date()


def fetch_candidate_transactions(db, months_back: int = 13) -> list:
    """
    Pull expense transactions from the last `months_back` months, excluding
    withdrawal/excluded/housing categories and anything in
    RecurringExcludedTransactions.

    Uses the same Final_Value pipeline as the rest of the app (splits applied,
    then SimpleMath.process_prices) rather than reading the raw Out/Charge_Value
    columns directly — process_prices converts foreign-currency card charges to
    their ILS value (Charge_Value is the original foreign-currency amount;
    Transaction_Value/Final_Value is the ILS-converted one) and drops card-side
    aggregate "אשראי" rows so bank-side and card-side amounts are never
    double-counted. Reading Charge_Value directly (as an earlier version of
    this function did) produced wildly inflated amounts for foreign-currency
    transactions, e.g. a JPY hotel charge showing as if it were that many ILS.

    Also excludes rows classified as Trans_Type.payment (an installment
    payment on a single larger purchase, e.g. "תשלום 2 מתוך 6") — these are
    one purchase spread over several charges, already shown as their own
    payment series in the monthly analysis, not a recurring bill.

    Returns list of dicts: table, id, date, name, amount, category.
    """
    import pandas as pd
    from src_utils.calculations import SimpleMath
    from Constants import Trans_Type

    cutoff = _date.today().replace(day=1) - _timedelta(days=months_back * 31)
    excluded_tx = db.get_recurring_excluded_tx()

    bank_df = db.get_transactions('BankTransactions', category_filter=None, name_filter=None)
    bank_df = db.apply_splits_to_df(bank_df)
    bank_df = SimpleMath.process_prices(bank_df, general_analysis=False)

    card_df = db.get_transactions('CardTransactions', category_filter=None, name_filter=None)
    card_df = db.apply_splits_to_df(card_df)
    card_df = SimpleMath.process_prices(card_df, general_analysis=False)
    if not card_df.empty:
        card_df = card_df.rename(columns={'Executed_Date': 'Date'})

    results = []
    for df, table_name in ((bank_df, 'BankTransactions'), (card_df, 'CardTransactions')):
        if df.empty or 'Final_Value' not in df.columns:
            continue
        for _, row in df.iterrows():
            final_value = row.get('Final_Value')
            if final_value is None or pd.isna(final_value) or final_value >= 0:
                continue  # only expenses — Final_Value is signed, negative = spending
            if row.get('Transaction_Type') == Trans_Type.payment:
                continue  # installment payment on one purchase, not a recurring bill
            tx_date = _to_plain_date(row['Date'])
            if tx_date < cutoff:
                continue
            tx_id = int(row['ID'])
            if (table_name, tx_id) in excluded_tx:
                continue
            category = row.get('Category') or ''
            if category in EXCLUDED_CATEGORIES:
                continue
            results.append({
                'table': table_name, 'id': tx_id, 'date': tx_date,
                'name': row['Name'], 'amount': abs(float(final_value)), 'category': category,
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

    # Apply manual merges: fold secondary cluster's members into primary's,
    # remembering each secondary's own display name so the merged group can
    # show "merged with X" and, per-occurrence, which original name a given
    # transaction actually came from.
    merges = db.get_recurring_merges()  # {secondary_key: primary_key}
    by_key = {c['norm_key']: c for c in clusters}
    merged_from_names = {}  # primary_key -> [secondary display names]
    for secondary_key, primary_key in merges.items():
        sec = by_key.get(secondary_key)
        prim = by_key.get(primary_key)
        if sec and prim and sec is not prim:
            sec_name = max(sec['members'], key=lambda m: m['date'])['name']
            merged_from_names.setdefault(primary_key, []).append(sec_name)
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
        group['merged_from'] = merged_from_names.get(cluster['norm_key'], [])
        groups.append(group)

    groups.sort(key=lambda g: g['current_amount'], reverse=True)
    return groups


ALERT_WINDOW_MONTHS = 12   # "in the last year" for introduced/removed alerts


def apply_history_tracking(db, groups: list, today: _date = None) -> dict:
    """
    Compares the currently-qualifying groups against RecurringHistory (every
    group_key ever seen recurring across past regens) to find bills that were
    genuinely newly introduced or that silently stopped qualifying, both
    within the last ALERT_WINDOW_MONTHS months. Updates RecurringHistory to
    reflect the current state as a side effect.

    Returns {'introduced': [{group_key, name, month}], 'removed': [{group_key, name, month}]}.

    A group's own first_payment_date can't be used directly to detect
    "newly introduced", since fetch_candidate_transactions only looks back
    ~13 months from today — a bill that's been recurring for years would
    still show a first_payment_date near the edge of that window, and would
    incorrectly look "new" every single regen. RecurringHistory instead
    records the first regen that ever saw each group qualify, which stays
    fixed once written.

    A manually-merged group (RecurringMerges) is a single continuing bill
    under a new name, not two bills — one stopping and another starting. So:
      - a merge's secondary_key is never flagged "removed" (its bill didn't
        stop, its identity now lives under primary_key), and
      - if the secondary had its own history but the primary doesn't yet (or
        started later), the primary's First_Seen_Month is pulled back to the
        secondary's, so the rename itself doesn't look "introduced" either.
    """
    if today is None:
        today = _date.today()

    history = db.get_recurring_history()
    was_cold_start = len(history) == 0   # first-ever regen: seed silently, no alerts

    merges = db.get_recurring_merges()   # {secondary_key: primary_key}
    merged_away_keys = set(merges.keys())
    for secondary_key, primary_key in merges.items():
        sec_hist = history.get(secondary_key)
        if not sec_hist:
            continue
        prim_hist = history.get(primary_key)
        if prim_hist:
            if sec_hist['first_seen_month'] < prim_hist['first_seen_month']:
                prim_hist['first_seen_month'] = sec_hist['first_seen_month']
        else:
            history[primary_key] = dict(sec_hist)

    current_keys = set()
    introduced = []
    for g in groups:
        key = g['group_key']
        current_keys.add(key)
        last_seen_month = month_key(g['last_payment_date'])
        if key not in history:
            first_seen_month = month_key(g['first_payment_date'])
            db.upsert_recurring_history(key, g['name'], first_seen_month, last_seen_month)
            if not was_cold_start:
                introduced.append({'group_key': key, 'name': g['name'], 'month': first_seen_month})
        else:
            db.upsert_recurring_history(key, g['name'], history[key]['first_seen_month'], last_seen_month)
    db.connection.commit()

    removed = []
    for key, rec in history.items():
        if key in current_keys:
            continue
        if key in merged_away_keys:
            continue   # folded into another group's identity, not actually stopped
        if _months_apart(rec['last_seen_month'], month_key(today)) <= ALERT_WINDOW_MONTHS:
            removed.append({'group_key': key, 'name': rec['name'], 'month': rec['last_seen_month']})

    return {'introduced': introduced, 'removed': removed}
