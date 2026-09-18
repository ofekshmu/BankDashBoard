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
from datetime import datetime, date as _date
from dateutil.relativedelta import relativedelta

from Constants import Local, CC_CHARGE_CATEGORY_NAME
from src_utils.utils import utils

TREND_MONTHS_DEFAULT = 6

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
    """{'charges': {CardID: {'amount', 'verified'}}, 'bank_total': float} for
    one billing month — memoized per call to get_card_analysis_data since the
    requested month and the trend window commonly overlap."""
    key = f'{month_start.year:04d}-{month_start.month:02d}'
    if key in cache:
        return cache[key]

    query_date = month_start - relativedelta(months=1)

    raw_df = utils.get_card_charge_df(query_date)
    charges = {}
    if not raw_df.empty:
        # interactive=False: read-only — never let a page view silently
        # auto-tag a BankTransactions row as an "אשראי" charge as a side effect.
        validation_df = utils.card_charge_validation(raw_df, query_date, tolerance=20, interactive=False)
        if not validation_df.empty:
            charges = {
                str(row['CardID']): {'amount': abs(float(row['Final_Value'])), 'verified': bool(row['Status'])}
                for _, row in validation_df.iterrows()
                if row['CardID'] != 'Bank'
            }

    next_dt = utils.next_month(query_date)
    bank_tx = db.get_Bank_Transactions(next_dt.month, next_dt.year)
    bank_total = 0.0
    if not bank_tx.empty and 'Category' in bank_tx.columns:
        cc_rows = bank_tx[bank_tx['Category'] == CC_CHARGE_CATEGORY_NAME]
        if not cc_rows.empty:
            bank_total = abs(float(cc_rows['Out'].sum()))

    result = {'charges': charges, 'bank_total': bank_total}
    cache[key] = result
    return result


def _month_overview(db, month_start: datetime, cards_meta: list, cache: dict) -> dict:
    is_open = _is_month_open(month_start)
    totals = _month_totals(db, month_start, cache)
    charges = totals['charges']

    billing_date = _billing_date_for(month_start)
    today = _date.today()

    cards = []
    for meta in cards_meta:
        cid = meta['card_id']
        info = charges.get(cid)
        amount = info['amount'] if info else 0.0

        if is_open:
            status = 'open'
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
        })

    total_charge = totals['bank_total'] if totals['bank_total'] > 0 else round(sum(c['current_charge'] for c in cards), 2)

    return {
        'month': f'{month_start.year:04d}-{month_start.month:02d}',
        'is_open': is_open,
        'next_charge_date': billing_date.isoformat() if is_open else None,
        'days_until_charge': (billing_date - today).days if is_open else None,
        'cards': cards,
        'total_charge': round(total_charge, 2),
    }


def _trend(db, end_month: datetime, months_back: int, cache: dict) -> list:
    """Total (all-cards) charge per billing month for the last `months_back`
    months ending at end_month, for the multi-month bar chart."""
    trend = []
    for i in range(months_back - 1, -1, -1):
        m = end_month - relativedelta(months=i)
        totals = _month_totals(db, m, cache)
        total = totals['bank_total'] if totals['bank_total'] > 0 else sum(v['amount'] for v in totals['charges'].values())
        trend.append({
            'month': f'{m.year:04d}-{m.month:02d}',
            'total': round(total, 2),
            'is_open': _is_month_open(m),
        })
    return trend


def get_card_analysis_data(db, month_key: str = None) -> dict:
    """Full payload for the Card Analysis page: available cards, the
    requested billing month's per-card breakdown, and a trailing trend.

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
    overview['trend'] = _trend(db, month_start, TREND_MONTHS_DEFAULT, cache)
    overview['cards_meta'] = cards_meta
    return overview
