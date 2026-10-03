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
