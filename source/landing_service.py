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
