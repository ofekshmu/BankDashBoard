"""New-build apartment projects (e.g. Mona): the money model, with no database access.

Payments tagged to a project are split into four kinds:
  price   - goes into the apartment price (builds the value you own; comes back on a sale)
  cost    - an extra expense (consultant/lawyer fees, taxes, ...): spent, never an asset
  income  - money in, e.g. rent: not an asset
  refund  - money back out of a price payment

Equity - the asset shown on the accounts page - is what you own of the apartment:
  equity = price payments - refunds + appreciation of the whole price
         = (market value) - (what is still owed on the price)
Profit if sold = equity + income - everything spent, which simplifies to
  appreciation + income - extra costs   (the paid-in price comes back on a sale).

The page recomputes `derive` / `sums` in JavaScript while the growth slider moves; the two
copies are checked against each other in tests/test_housing_projects_js.py.
"""
import calendar
import re
from datetime import date, timedelta

DEFAULT_GROWTH_PCT = 3.0
MAX_GROWTH_PCT = 15.0
DEFAULT_DOWN_PCT = 10.0
DEFAULT_MORTGAGE_PCT = 75.0   # share of the price financed by the mortgage taken at delivery
MIN_ANNUALIZE_YEARS = 1.0    # a shorter history gives silly annualised figures (−25% in 3 months is not −58% a year)

KIND_PRICE, KIND_COST, KIND_INCOME, KIND_REFUND = 'price', 'cost', 'income', 'refund'
OUT_KINDS = (KIND_PRICE, KIND_COST)
IN_KINDS = (KIND_INCOME, KIND_REFUND)

# Outgoing payments whose name/description mention one of these are extra costs by default
# (fees and taxes around the purchase). Every payment can be flipped on the page.
_COST_WORDS = ('ליווי', 'עורך דין', 'שמאי', 'מס רכישה', 'יועץ', 'ייעוץ', 'תיווך', 'מתווך',
               'עמלה', 'ביטוח', 'דמי טיפול', 'אגרה')
_LAWYER = re.compile('עו["״]ד')   # עו"ד / עו״ד — not the word "עוד"


def classify_kind(name, description, out, income):
    """Automatic kind of one payment: incoming → income; outgoing → cost for fee-like names, else price."""
    if not (out and out > 0):
        return KIND_INCOME
    text = f'{name or ""} {description or ""}'
    if _LAWYER.search(text) or any(w in text for w in _COST_WORDS):
        return KIND_COST
    return KIND_PRICE


def apply_override(auto, override, is_out):
    """The user's choice when it fits the payment's direction, else the automatic kind."""
    allowed = OUT_KINDS if is_out else IN_KINDS
    return override if override in allowed else auto


# ── time and value ─────────────────────────────────────────────────────────
def years_between(start, end):
    """Years from `start` to `end` (365.25-day years), never negative."""
    return max((end - start).days, 0) / 365.25


def grown_value(price, rate_pct, years):
    """`price` grown at `rate_pct` a year for `years`; unchanged for zero/negative time."""
    if price is None:
        return None
    return price * (1 + rate_pct / 100) ** years if years > 0 else price


def expected_mortgage(price, own_pct, paid_price):
    """What the mortgage will cover at delivery: the price minus the larger of the own-funds share
    (`own_pct` % of the price, i.e. 100 − the mortgage share: the down payment plus the extra amount
    paid straight up before the loan) and what was already paid."""
    if price is None:
        return None
    return max(price - max(paid_price, price * own_pct / 100), 0)


# ── sums and the derived numbers ───────────────────────────────────────────
def sums(txs):
    """Totals by kind. `net_invested` is everything spent less refunds (what the sale must beat)."""
    paid = costs = income = refunds = 0.0
    for t in txs:
        k, out, inc = t['kind'], t['out'] or 0, t['income'] or 0
        if k == KIND_PRICE:
            paid += out
        elif k == KIND_COST:
            costs += out
        elif k == KIND_REFUND:
            refunds += inc
        elif k == KIND_INCOME:
            income += inc
    return {'paid_price': paid - refunds, 'extra_costs': costs, 'income_total': income, 'refunds': refunds,
            'net_invested': paid + costs - refunds, 'out_total': paid + costs}


def derive(inp, growth_pct):
    """Everything the page shows that depends on the growth rate.

    `inp`: price (or None), paid_price, extra_costs, income_total, net_invested, years_now (since
    growth started), years_delivery (None without a delivery date), years_invested (since the
    first payment, None without one), expected_mortgage (None without a price).
    """
    price, paid = inp.get('price'), inp['paid_price']
    r = growth_pct / 100
    market = grown_value(price, growth_pct, inp['years_now']) if price is not None else None
    appreciation = (market - price) if market is not None else 0.0
    equity = paid + appreciation
    profit = equity + inp['income_total'] - inp['net_invested']
    invested = inp['net_invested']
    total_ret = profit / invested * 100 if invested > 0 else None
    years = inp.get('years_invested')
    annual = None
    if total_ret is not None and years is not None and years >= MIN_ANNUALIZE_YEARS and total_ret > -100:
        annual = ((1 + total_ret / 100) ** (1 / years) - 1) * 100
    at_delivery = None
    if price is not None and inp.get('years_delivery') is not None:
        at_delivery = grown_value(price, growth_pct, inp['years_delivery'])
    mortgage = inp.get('expected_mortgage')
    return {
        'market_value': market,
        'appreciation': appreciation,
        'monthly_appreciation': market * ((1 + r) ** (1 / 12) - 1) if market is not None else 0.0,
        'equity': equity,
        'remaining_to_pay': max(price - paid, 0) if price is not None else None,
        'profit': profit,
        'total_return_pct': total_ret,
        'annual_return_pct': annual,
        'value_at_delivery': at_delivery,
        'equity_at_delivery': at_delivery - mortgage if at_delivery is not None and mortgage is not None else None,
    }


def growth_start(contract_date, event_dates, price_dates, today):
    """When the price started growing, and where that date came from: the signing date if set, else
    the project's earliest timeline event, else the first price payment, else today."""
    if contract_date:
        return contract_date, 'contract'
    if event_dates:
        return min(event_dates), 'timeline'
    if price_dates:
        return min(price_dates), 'payment'
    return today, 'today'


# ── building the project summary ───────────────────────────────────────────
def _iso(d):
    return d.isoformat() if d else None


def _month(d):
    return f'{d.year:04d}-{d.month:02d}'


def _event_date(e):
    try:
        return date.fromisoformat(str(e['event_date'])[:10])
    except (KeyError, ValueError):
        return None


def _month_range(first, last):
    y, m = first.year, first.month
    out = []
    while (y, m) <= (last.year, last.month):
        out.append(f'{y:04d}-{m:02d}')
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _upto(txs, today):
    return sorted((t for t in txs if t['date'] <= today), key=lambda t: t['date'])


def _inputs(settings, txs, events, today):
    """The numbers `derive` needs, from the settings and the payments up to today."""
    s = sums(txs)
    price = settings.get('price')
    price_dates = [t['date'] for t in txs if t['kind'] == KIND_PRICE]
    start, source = growth_start(settings.get('contract_date'),
                                 [d for d in map(_event_date, events) if d], price_dates, today)
    outs = [t['date'] for t in txs if t['out']]
    delivery = settings.get('delivery_date')
    inp = {
        'price': price, **{k: s[k] for k in ('paid_price', 'extra_costs', 'income_total', 'net_invested')},
        'years_now': years_between(start, today),
        'years_delivery': years_between(start, delivery) if delivery else None,
        'years_invested': years_between(min(outs), today) if outs else None,
        'expected_mortgage': expected_mortgage(
            price, 100 - settings.get('mortgage_pct', DEFAULT_MORTGAGE_PCT), s['paid_price']),
    }
    return inp, start, source, s


def build_project(settings, txs, events, today):
    """Everything about one project as JSON-safe data (dates as ISO strings).

    `txs`: dicts with key, table, id, date, name, description, out, income, auto_kind, kind.
    `events`: the project's timeline events (id, name, event_date, description, color).
    """
    txs = _upto(txs, today)
    g = settings.get('growth_pct', DEFAULT_GROWTH_PCT)
    price = settings.get('price')
    inp, start, source, s = _inputs(settings, txs, events, today)
    d = derive(inp, g)

    down = None
    mortgage_pct = settings.get('mortgage_pct', DEFAULT_MORTGAGE_PCT)
    mortgage = inp['expected_mortgage']
    financing = {'mortgage_pct': mortgage_pct, 'expected_mortgage': mortgage,
                 'mortgage_pct_of_price': None, 'own_total_target': None, 'own_total_left': None,
                 'delivery_payment': None}
    if price is not None:
        target = price * settings.get('down_pct', DEFAULT_DOWN_PCT) / 100
        down = {'target': round(target, 2), 'paid': round(s['paid_price'], 2),
                'left': round(max(target - s['paid_price'], 0), 2),
                'progress_pct': round(min(s['paid_price'] / target * 100, 100), 1) if target else None}
        # own money before the loan = the down payment plus the extra amount paid straight up at delivery
        own_total = price * (100 - mortgage_pct) / 100
        financing.update({'mortgage_pct_of_price': round(mortgage / price * 100, 1),
                          'own_total_target': round(own_total, 2),
                          'own_total_left': round(max(own_total - s['paid_price'], 0), 2),
                          'delivery_payment': round(max(own_total - target, 0), 2)})
    delivery = settings.get('delivery_date')

    outs = [t for t in txs if t['out']]
    required = max(s['extra_costs'] - s['income_total'], 0)
    required_growth = None
    if price and required > 0 and inp['years_now'] >= MIN_ANNUALIZE_YEARS:
        required_growth = (((price + required) / price) ** (1 / inp['years_now']) - 1) * 100

    months = {m: {'month': m, 'out': 0.0, 'income': 0.0, 'paid': 0.0} for m in
              (_month_range(txs[0]['date'], today) if txs else [])}
    for t in txs:
        row = months[_month(t['date'])]
        row['out'] += t['out'] or 0
        row['income'] += t['income'] or 0
        row['paid'] += (t['out'] or 0) if t['kind'] == KIND_PRICE else -(t['income'] or 0) if t['kind'] == KIND_REFUND else 0
    monthly, cum = [], 0.0
    for m in sorted(months):
        row = months[m]
        cum += row['paid']
        monthly.append({'month': m, 'out': round(row['out'], 2), 'income': round(row['income'], 2),
                        'net': round(row['income'] - row['out'], 2), 'cum_paid': round(cum, 2)})

    largest = max(outs, key=lambda t: t['out'], default=None)
    last_out = max(outs, key=lambda t: t['date'], default=None)
    n_months = len(monthly) or 1
    ev = sorted((e for e in events if _event_date(e)), key=_event_date)
    upcoming = [e for e in ev if _event_date(e) > today]
    past = [e for e in ev if _event_date(e) <= today]

    return {
        'key': settings['key'], 'name': settings['name'], 'tx_category': settings['tx_category'],
        'timeline_category': settings.get('timeline_category'), 'today': _iso(today),
        'has_price': price is not None,
        'settings': {'price': price, 'down_pct': settings.get('down_pct', DEFAULT_DOWN_PCT),
                     'mortgage_pct': mortgage_pct, 'growth_pct': g,
                     'contract_date': _iso(settings.get('contract_date')), 'delivery_date': _iso(delivery)},
        'growth_start': _iso(start), 'growth_start_source': source,
        'years': {k: inp[k] for k in ('years_now', 'years_delivery', 'years_invested')},
        'money': {k: round(v, 2) for k, v in s.items()},
        'derived': d,
        'down': down,
        'financing': financing,
        'delivery': {'date': _iso(delivery),
                     'days_left': (delivery - today).days if delivery else None,
                     'value_at_delivery': d['value_at_delivery'], 'equity_at_delivery': d['equity_at_delivery']},
        'returns': {'profit_if_sold': d['profit'], 'total_return_pct': d['total_return_pct'],
                    'annual_return_pct': d['annual_return_pct'],
                    'break_even': {'required_appreciation': round(required, 2),
                                   'required_pct_of_price': round(required / price * 100, 2) if price else None,
                                   'required_growth_pct': required_growth}},
        'stats': {
            'n_out': len(outs), 'n_in': sum(1 for t in txs if t['income']),
            'largest': {'amount': largest['out'], 'date': _iso(largest['date']), 'name': largest['name']} if largest else None,
            'last_out': {'date': _iso(last_out['date']), 'amount': last_out['out'],
                         'days_ago': (today - last_out['date']).days} if last_out else None,
            'first_date': _iso(txs[0]['date']) if txs else None,
            'avg_monthly_out': round(s['out_total'] / n_months, 2) if txs else 0.0,
            'overhead_pct_of_price': round(s['extra_costs'] / price * 100, 2) if price else None,
        },
        'monthly': monthly,
        'transactions': [{**{k: t[k] for k in ('key', 'table', 'id', 'name', 'description', 'out', 'income', 'auto_kind', 'kind')},
                          'date': _iso(t['date'])} for t in reversed(txs)],
        'events': ev,
        'event_stats': {'count': len(ev), 'next': upcoming[0] if upcoming else None,
                        'last': past[-1] if past else None},
    }


# ── the asset on the accounts page ─────────────────────────────────────────
def _month_end(y, m):
    return date(y, m, calendar.monthrange(y, m)[1])


def equity_history(settings, txs, events, today):
    """[(date, equity)] from the first price payment to today: a point on that day, at each month
    end, and today. Empty when no money has gone into the price."""
    txs = _upto(txs, today)
    price = settings.get('price')
    g = settings.get('growth_pct', DEFAULT_GROWTH_PCT)
    price_pay = [t for t in txs if t['kind'] == KIND_PRICE and t['out']]
    if not price_pay:
        return []
    start, _ = growth_start(settings.get('contract_date'),
                            [d for d in map(_event_date, events) if d], [t['date'] for t in price_pay], today)

    def equity_on(day):
        paid = sum(t['out'] for t in price_pay if t['date'] <= day) - \
            sum(t['income'] for t in txs if t['kind'] == KIND_REFUND and t['date'] <= day)
        apprec = grown_value(price, g, years_between(start, day)) - price if price is not None else 0.0
        return paid + apprec

    first = price_pay[0]['date']
    days = [first]
    y, m = first.year, first.month
    while _month_end(y, m) < today:
        if _month_end(y, m) > first:
            days.append(_month_end(y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    if today > first:
        days.append(today)
    return [(d, equity_on(d)) for d in days]


def apply_overlay(payload, extra):
    """The accounts payload with the projects' assets added and the Total series shifted by them.

    `extra`: {account name: [[iso date, value], ...]}. The input is not changed; the same object is
    returned when there is nothing to add. A name that already exists is left alone.
    """
    if not payload or not payload.get('accounts'):
        return payload
    extra = {n: pts for n, pts in extra.items() if pts and n not in payload['accounts']}
    if not extra:
        return payload

    def at(points, day):
        last = None
        for d, v in points:
            if d <= day:
                last = v
            else:
                break
        return last or 0.0

    accounts = dict(payload['accounts'])
    total = accounts.get('Total') or []
    sorted_extra = {n: sorted(pts) for n, pts in extra.items()}
    days = sorted({d for d, _ in total} | {d for pts in sorted_extra.values() for d, _ in pts})
    base = sorted(total)
    accounts.update({n: [list(p) for p in pts] for n, pts in sorted_extra.items()})
    accounts['Total'] = [[d, round(at(base, d) + sum(at(pts, d) for pts in sorted_extra.values()), 2)] for d in days]
    return {**payload, 'accounts': accounts}
