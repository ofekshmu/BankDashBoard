"""
Card Analysis — per-card, per-month CHARGE tracking (not raw spend).

"Charge" here means the amount that actually posts to the bank account for a
card's billing cycle (Charge_Date-based) — reusing the exact
utils.get_card_charge_df / utils.card_charge_validation pipeline the
Organizer page already uses to validate a card's summed total against the
bank-side CC debit, rather than re-deriving a sum from raw transactions.

Month labelling: a billing month here is the month the charge actually posts
(matching a real card/bank statement, and the reference bank-app screenshot
this page is modeled on) — NOT the Organizer's own row labelling, which
shows the spending month instead. get_card_charge_df/card_charge_validation
internally shift by next_month(), so to query billing month M we pass
date = M - 1 month.
"""
import calendar
from datetime import datetime, date as _date
from dateutil.relativedelta import relativedelta
import pandas as pd

from Constants import Local, CC_CHARGE_CATEGORY_NAME
from src_utils.utils import utils

TREND_MONTHS_DEFAULT = 6
EXPECTED_DATE_LOOKBACK_MONTHS = 12
CHARGE_TOLERANCE = 20

# Mirrors AppManager.py's own inline dict (no shared constant exists for
# this) — issuer/format -> the network name shown to the user.
_FMT_DISPLAY = {
    'American-Express': 'American Express', 'Isra-Card': 'Mastercard',
    'Isra-Card-2026': 'Mastercard', 'Cal': 'Cal', 'Leumi-Max': 'Max',
}


def _month_start(d: _date) -> datetime:
    return datetime(d.year, d.month, 1)


def _billing_date_for(month_start: datetime) -> _date:
    """The calendar date a card's charge for this billing month actually posts."""
    return _date(month_start.year, month_start.month, Local.CHARGE_DAY)


def _is_month_open(month_start: datetime, today: _date = None) -> bool:
    """True while this billing month's charge hasn't posted yet — bank-side
    validation is meaningless before that date, so the month is shown as a
    live, still-accumulating total instead of verified/not-verified."""
    today = today or _date.today()
    return today < _billing_date_for(month_start)


def get_available_cards(db) -> list:
    """Every card the app has ever seen, with display metadata. Neither a
    nickname nor a credit limit is tracked anywhere else in the app — limit
    is the one piece of user-set config this page adds (CardLimits table)."""
    card_ids = db.get_card_ids()
    formats = db.get_card_formats()
    limits = db.get_card_limits()
    palette = Local.Colors
    return [
        {
            'card_id': cid,
            'network': _FMT_DISPLAY.get(formats.get(cid, ''), formats.get(cid, '')),
            'color': palette[i % len(palette)],
            'credit_limit': limits.get(cid),
        }
        for i, cid in enumerate(card_ids)
    ]


def _month_totals(db, month_start: datetime, cache: dict) -> dict:
    """{'charges': {CardID: {'amount', 'verified', 'charge_date'?}}, 'bank_total': float}
    for one billing month — memoized per call to get_card_analysis_data since
    the requested month, the trend window, and each card's expected-charge-date
    lookback all commonly revisit the same months."""
    key = f'{month_start.year:04d}-{month_start.month:02d}'
    if key in cache:
        return cache[key]

    query_date = month_start - relativedelta(months=1)

    raw_df = utils.get_card_charge_df(query_date)
    charges = {}
    if not raw_df.empty:
        # interactive=False: read-only — never let a page view silently
        # auto-tag a BankTransactions row as an "אשראי" charge as a side effect.
        validation_df = utils.card_charge_validation(raw_df, query_date, tolerance=CHARGE_TOLERANCE, interactive=False)
        if not validation_df.empty:
            charges = {
                str(row['CardID']): {'amount': abs(float(row['Final_Value'])), 'verified': bool(row['Status'])}
                for _, row in validation_df.iterrows()
                if row['CardID'] != 'Bank'
            }

    next_dt = utils.next_month(query_date)
    bank_tx = db.get_Bank_Transactions(next_dt.month, next_dt.year)
    bank_total = 0.0
    cc_rows = pd.DataFrame()
    if not bank_tx.empty and 'Category' in bank_tx.columns:
        cc_rows = bank_tx[bank_tx['Category'] == CC_CHARGE_CATEGORY_NAME]
        if not cc_rows.empty:
            bank_total = abs(float(cc_rows['Out'].sum()))

    # For a verified card, recover the actual bank-side transaction date —
    # card_charge_validation already matched it by amount/tolerance but only
    # returns the boolean Status, not which row it matched. Re-applying the
    # same amount/tolerance match against the same cc_rows here is cheap
    # (already fetched) and avoids touching the shared utils.py function.
    if not cc_rows.empty:
        for info in charges.values():
            if not info['verified']:
                continue
            match = cc_rows[(cc_rows['Out'].abs() - info['amount']).abs() <= CHARGE_TOLERANCE]
            if not match.empty:
                info['charge_date'] = pd.to_datetime(match.iloc[0]['Date']).date()

    result = {'charges': charges, 'bank_total': bank_total}
    cache[key] = result
    return result


def _expected_charge_date(db, card_id: str, open_month_start: datetime, cache: dict) -> _date:
    """The date this card's charge is expected to post in open_month_start,
    inferred from the day-of-month of the most recent billing month in which
    this specific card was actually verified against the bank statement.
    None ("unknown") if it was never verified within the lookback window."""
    for i in range(1, EXPECTED_DATE_LOOKBACK_MONTHS + 1):
        m = open_month_start - relativedelta(months=i)
        totals = _month_totals(db, m, cache)
        info = totals['charges'].get(card_id)
        if info and info.get('verified') and info.get('charge_date'):
            day = info['charge_date'].day
            last_day_of_month = calendar.monthrange(open_month_start.year, open_month_start.month)[1]
            return _date(open_month_start.year, open_month_start.month, min(day, last_day_of_month))
    return None


def _month_overview(db, month_start: datetime, cards_meta: list, cache: dict) -> dict:
    is_open = _is_month_open(month_start)
    totals = _month_totals(db, month_start, cache)
    charges = totals['charges']
    today = _date.today()

    cards = []
    for meta in cards_meta:
        cid = meta['card_id']
        info = charges.get(cid)
        amount = info['amount'] if info else 0.0

        expected_charge_date = None
        if is_open:
            status = 'open'
            expected_charge_date = _expected_charge_date(db, cid, month_start, cache)
        elif info is None:
            status = 'not_found'
        elif info['verified']:
            status = 'verified'
        else:
            status = 'not_verified'

        available_balance = None
        if is_open and meta['credit_limit']:
            available_balance = round(meta['credit_limit'] - amount, 2)

        cards.append({
            'card_id': cid,
            'network': meta['network'],
            'color': meta['color'],
            'credit_limit': meta['credit_limit'],
            'current_charge': round(amount, 2),
            'status': status,
            'available_balance': available_balance,
            'expected_charge_date': expected_charge_date.isoformat() if expected_charge_date else None,
            'days_until_charge': (expected_charge_date - today).days if expected_charge_date else None,
        })

    total_charge = totals['bank_total'] if totals['bank_total'] > 0 else round(sum(c['current_charge'] for c in cards), 2)

    return {
        'month': f'{month_start.year:04d}-{month_start.month:02d}',
        'is_open': is_open,
        'cards': cards,
        'total_charge': round(total_charge, 2),
    }


def _trend(db, end_month: datetime, months_back: int, cache: dict):
    """Total (all-cards) charge per billing month for the last `months_back`
    months ending at end_month (for the summary bar chart), plus the same
    per-card breakdown (for each card's own mini trend) — built from the same
    _month_totals calls, so this costs nothing beyond the total trend already
    being computed."""
    trend = []
    per_card = {}
    month_keys = []
    for i in range(months_back - 1, -1, -1):
        m = end_month - relativedelta(months=i)
        totals = _month_totals(db, m, cache)
        total = totals['bank_total'] if totals['bank_total'] > 0 else sum(v['amount'] for v in totals['charges'].values())
        key = f'{m.year:04d}-{m.month:02d}'
        month_keys.append(key)
        trend.append({'month': key, 'total': round(total, 2), 'is_open': _is_month_open(m)})
        for cid, info in totals['charges'].items():
            per_card.setdefault(cid, {})[key] = round(info['amount'], 2)
    return trend, per_card, month_keys


def get_card_analysis_data(db, month_key: str = None) -> dict:
    """Full payload for the Card Analysis page: available cards, the
    requested billing month's per-card breakdown (each with its own trend),
    and the all-cards trend.

    @param db: DataBase instance (caller ensures ensure_card_limits_table() first)
    @param month_key: 'YYYY-MM' billing month to view; defaults to the
           current billing month (today's date)
    """
    if month_key:
        year, month = (int(x) for x in month_key.split('-'))
        month_start = datetime(year, month, 1)
    else:
        month_start = _month_start(_date.today())

    cards_meta = get_available_cards(db)
    cache = {}
    overview = _month_overview(db, month_start, cards_meta, cache)
    trend, per_card_trend, trend_month_keys = _trend(db, month_start, TREND_MONTHS_DEFAULT, cache)
    overview['trend'] = trend
    for c in overview['cards']:
        series = per_card_trend.get(c['card_id'], {})
        c['trend'] = [{'month': mk, 'amount': series.get(mk, 0.0)} for mk in trend_month_keys]
    return overview
