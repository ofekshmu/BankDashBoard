"""Landing dashboard — one pure builder per KPI block.

Every builder turns raw data (loaded by landing_loaders.py or WebApp.py) into
{ok, dot, kpi, caption, details, attention, extra}. `attention` is a one-line
summary of what needs a look, set only on amber/red blocks; the landing page
lists those lines in its attention strip. Nothing here touches the DB, so each
block is unit-testable with plain dicts and lists.
"""
from datetime import date, datetime
from statistics import median

HEB_MONTHS = ('ינואר', 'פברואר', 'מרץ', 'אפריל', 'מאי', 'יוני',
              'יולי', 'אוגוסט', 'ספטמבר', 'אוקטובר', 'נובמבר', 'דצמבר')
STALE_DAYS = 30          # same threshold as the accounts page (_STALE_DAYS)
MAX_DETAILS = 3
TREND_MONTHS = 3         # accounts block sparkline window


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


def block(kpi, caption, details=(), dot=None, extra=None, attention=None):
    """One KPI block. `attention` is kept only when the dot is amber or red."""
    return {'ok': True, 'dot': dot, 'kpi': kpi, 'caption': caption,
            'details': [d for d in details if d],
            'attention': attention if dot in ('amber', 'red') else None,
            'extra': extra or {}}


def count_text(n, one, many):
    """Hebrew count phrase: `one` when n == 1, else f'{n} {many}'."""
    return one if n == 1 else f'{n} {many}'


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


def _shift_month(d, back):
    """'YYYY_MM' of the month `back` months before date `d`."""
    n = d.year * 12 + d.month - 1 - back
    return f'{n // 12:04d}_{n % 12 + 1:02d}'


def month_flow(payload, today):
    """Income, spending, net income and net investment of the previous and the current month, as
    the monthly page's general chart shows them: general_earnings / general_spendings (investments
    excluded), general_net / general_current_net (cash included) and investments out − in.
    general_* figures live under payload['charts'] and are relative to the real current month,
    whatever month the payload is for.
    Returns [previous, current] as {key, label, income, spend, net, invest}, or [] when the
    payload lacks them."""
    p = (payload or {}).get('charts') or {}
    try:
        prev = {'income': p['general_earnings'][0], 'spend': p['general_spendings'][0],
                'net': p['general_net'][0],
                'invest': p['general_investments_out'][0] - p['general_investments_in'][0]}
        cur = {'income': p['general_current_earnings'], 'spend': p['general_current_spendings'],
               'net': p['general_current_net'],
               'invest': p['general_current_investments_out'] - p['general_current_investments_in']}
    except (KeyError, IndexError, TypeError):
        return []
    out = []
    for back, vals in ((1, prev), (0, cur)):
        key = _shift_month(today, back)
        out.append({'key': key, 'label': month_label(key),
                    **{k: round(float(vals[k] or 0)) for k in ('income', 'spend', 'net', 'invest')}})
    return out


def card_misses_line(misses):
    """'חיוב כרטיס לא אומת: 4603, 1565 (ספטמבר) · 2922 (יולי)' — newest month first."""
    by_month = {}
    for key, card in misses:
        by_month.setdefault(key, []).append(str(card))
    return 'חיוב כרטיס לא אומת: ' + ' · '.join(
        f"{', '.join(cards)} ({HEB_MONTHS[int(key[5:7]) - 1]})" for key, cards in sorted(by_month.items(), reverse=True))


def build_monthly(months, key, payload, today=None, card_misses=None):
    """The analysis month's alert count, plus `card_misses` — [(spending month, card)] whose
    charge matched no bank debit in the last months (the organizer's red cells): those make
    the block at least amber and show as a detail line and in the attention strip."""
    keys = sorted({m['key'] for m in months or [] if m.get('key')}, reverse=True)
    extra = {'months': [{'key': k, 'label': month_label(k)} for k in keys], 'current': key,
             'flow': month_flow(payload, today) if today else []}
    if not key:
        return block('—', 'אין ניתוחים חודשיים', dot='grey', extra=extra)
    if payload is None:
        return block('—', f'אין ניתוח ל{month_label(key)}', dot='grey', extra=extra)
    n = len(payload.get('alerts') or []) + len(payload.get('organizer_alerts') or [])
    dot = 'green' if n == 0 else ('amber' if n <= 2 else 'red')
    misses = card_misses_line(card_misses) if card_misses else None
    if misses and dot == 'green':
        dot = 'amber'
    attention = ' · '.join(x for x in (
        f"{count_text(n, 'התראה אחת', 'התראות')} ב{month_label(key)}" if n else None, misses) if x)
    return block(str(n), f'התראות ב{month_label(key)}', [misses], dot=dot, extra=extra, attention=attention)


# ── Accounts ───────────────────────────────────────────────────────────────
def cash_ils_total(cash_map, rates):
    """Cash on hand in ILS exactly as the accounts page's cash pie ("סה"כ מזומן") sums it:
    positive balances only, each round(balance × rate). None when the map is missing or a
    held foreign currency has no rate yet — never count ¥/€ at 1:1."""
    if cash_map is None:
        return None
    total = 0
    for cur, bal in cash_map.items():
        bal = float(bal or 0)
        if bal <= 0:
            continue
        rate = 1.0 if cur == 'ILS' else (rates or {}).get(cur)
        if not rate:
            return None
        total += round(bal * float(rate))
    return total


def cash_delta(accounts, cash_map, rates):
    """What the accounts page adds to the Total series: the cash-by-currency total in ILS
    minus the Cash account's last (ILS-only) point. 0 when either side is missing."""
    cash = (accounts or {}).get('Cash') or []
    ils = cash_ils_total(cash_map, rates)
    if ils is None or not cash:
        return 0.0
    return ils - float(cash[-1][1] or 0)


def accounts_total(accounts, cash_map, rates):
    """Same figure as the accounts page grand total: the Total series' last point,
    with the Cash account replaced by the cash-by-currency total in ILS."""
    total = (accounts or {}).get('Total') or []
    if not total:
        return None
    return float(total[-1][1] or 0) + cash_delta(accounts, cash_map, rates)


def _months_back(d, n):
    """Date `n` calendar months before `d`, the day clamped to the target month's length."""
    m = d.year * 12 + d.month - 1 - n
    y, mo = m // 12, m % 12 + 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(y, mo, day)
        except ValueError:
            continue


def _smooth_half_months(window):
    """[(date, value)] → one point per half-month (1–15, 16–end): the bucket's median at its
    last date, then a 3-point running median so a one-off spike (e.g. a month-end transfer)
    doesn't show. The last point stays the real current value."""
    buckets = {}
    for d, v in window:
        buckets.setdefault((d.year, d.month, d.day > 15), []).append((d, v))
    pts = [(b[-1][0], median(v for _, v in b)) for _, b in sorted(buckets.items())]
    pts[-1] = window[-1]
    vals = [v for _, v in pts]
    smooth = vals[:1] + [median(vals[i - 1:i + 2]) for i in range(1, len(vals) - 1)] + vals[-1:]
    return [(d, s) for (d, _), s in zip(pts, smooth[:len(pts)])]


def accounts_trend(total, delta, today, months=TREND_MONTHS):
    """The Total series over the last `months` months, smoothed to ~2 points a month and
    shifted by `delta` (the cash correction) so it ends at the KPI. Starts at the value on
    the window's first day — the last point on or before it, else the first point inside it.
    `change` is from the line's first point to the current value.
    Returns {points: [[date, value]...], change, change_pct} or None with < 2 points."""
    pts = [(as_date(d), float(v or 0) + delta) for d, v in total or [] if as_date(d)]
    start = _months_back(today, months)
    window = [p for p in pts if p[0] <= start][-1:] + [p for p in pts if p[0] > start]
    line = _smooth_half_months(window) if len(window) >= 2 else []
    if len(line) < 2:
        return None
    first, last = line[0][1], line[-1][1]
    return {'points': [[d.isoformat(), round(v)] for d, v in line], 'change': round(last - first),
            'change_pct': round((last - first) / abs(first) * 100, 1) if first else None}


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
    """Grand total as on the accounts page, stale accounts, and a 3-month trend (extra.trend)."""
    accounts = (payload or {}).get('accounts') or {}
    total = accounts_total(accounts, cash_map, rates)
    if total is None:
        return block('—', 'שווי כל החשבונות', dot='grey')
    stale = _stale_accounts(accounts, today)
    details = cap(f'{name} · עודכן {short_date(d)}' for d, name in stale) or ['כל החשבונות מעודכנים']
    trend = accounts_trend(accounts['Total'], cash_delta(accounts, cash_map, rates), today)
    return block(money(total), 'שווי כל החשבונות', details, dot='amber' if stale else 'green',
                 extra={'trend': trend},
                 attention=count_text(len(stale), 'חשבון אחד לא עודכן', 'חשבונות לא עודכנו') + f' מעל {STALE_DAYS} יום')


# ── Cards ──────────────────────────────────────────────────────────────────
def build_cards(cards, month=None):
    """Every card with a charge in the card page's month ('YYYY-MM'), largest charge first."""
    active = sorted((c for c in cards or [] if float(c.get('current_charge') or 0) > 0),
                    key=lambda c: -float(c['current_charge']))
    details = [f"{(c.get('network') or '').strip()} ·{c.get('card_id')} · {money(c['current_charge'])}".strip()
               for c in active]
    when = f'ב{month_label(month.replace("-", "_"))}' if month else 'החודש'
    return block(str(len(active)), f'כרטיסים פעילים {when}', details, dot=None if active else 'grey')


# ── Housing ────────────────────────────────────────────────────────────────
def build_housing(m):
    m = m or {}
    if m.get('annual_return_pct') is None:
        return block('—', 'תשואה שנתית', dot='grey')
    rate = m.get('default_rate') or 5      # housing page: default_rate || 5
    rate = int(rate) if float(rate).is_integer() else rate
    profit = (m.get('equity_appreciated') or 0) + (m.get('alltime_income') or 0) - (m.get('net_invested') or 0)
    details = [f"תשואה כוללת במכירה {pct(m['total_return_pct'])}" if m.get('total_return_pct') is not None else None,
               f'רווח נקי {money(profit)}']
    # No attention line: housing never feeds the alert strip (the dot still shows the status)
    return block(pct(m['annual_return_pct']), f'תשואה שנתית ({rate}% עליית ערך)', details,
                 dot='green' if m['annual_return_pct'] >= 0 else 'red')


# ── Mona (new-build apartment) ─────────────────────────────────────────────
def build_mona(p):
    """The Mona project block: equity in the apartment (price payments + appreciation) as the KPI, then
    market value, own money paid vs. the plan, net profit and the delivery countdown / last event.
    `p` is housing_project_service.project_payload(); no attention line (never feeds the alert strip)."""
    if not p:
        return block('—', 'אין פרויקט', dot='grey')
    m, d, f = p.get('money') or {}, p.get('derived') or {}, p.get('financing') or {}
    name = p.get('name') or 'מונה'
    if not p.get('has_price'):
        return block(money(m.get('net_invested')), f'{name} · הושקע עד כה',
                     ['הזינו מחיר דירה בעמוד דיור כדי לראות שווי והון עצמי'], dot='grey')
    delivery = (p.get('delivery') or {}).get('days_left')
    last = (p.get('event_stats') or {}).get('last')
    if delivery is not None and delivery >= 0:
        tail = 'מסירה היום' if delivery == 0 else f'מסירה בעוד {count_text(delivery, "יום", "ימים")}'
    elif last:
        tail = f"אירוע אחרון: {last['name']} · {short_date(last.get('event_date'))}"
    else:
        tail = None
    profit = d.get('profit') or 0
    details = [f"שווי הדירה {money(d.get('market_value'))}",
               f"שולם {money(m.get('paid_price'))} מתוך הון עצמי {money(f.get('own_total_target'))}",
               f"רווח נקי {signed_money(profit)}"]
    if tail:
        details.append(tail)
    return block(money(d.get('equity')), f'{name} · הון עצמי בנכס', cap(details, 4),
                 dot='green' if profit >= 0 else None, extra={'prop': 'mona'})


# ── Timeline ───────────────────────────────────────────────────────────────
def build_timeline(event):
    if not event:
        return block('—', 'אין אירועים', dot='grey')
    return block(event['name'], 'האירוע האחרון שנוצר', [short_date(event.get('event_date'))])


# ── Bills ──────────────────────────────────────────────────────────────────
TOP_BILLS = 5
BILLS_GROUP = 'סיטרמן'   # the bills page's group whose average the landing block shows


def _half_day(ym):
    """JS parseInt(ym.slice(8)) || 1 — the day part of 'YYYY-MM' / 'YYYY-MM-15'."""
    digits = ''
    for ch in str(ym)[8:]:
        if not ch.isdigit():
            break
        digits += ch
    return int(digits or 0) or 1


def _half_coords(start, end):
    """[start, end) in half-month units, exactly like Bills.html calcSpanMonths."""
    start, end = str(start), str(end or start)
    s = int(start[:4]) * 24 + (int(start[5:7]) - 1) * 2 + (1 if _half_day(start) >= 15 else 0)
    e = int(end[:4]) * 24 + (int(end[5:7]) - 1) * 2 + (1 if _half_day(end) >= 15 else 2)
    return s, e


def bill_span_months(entries):
    """Port of the bills page's calcSpanMonths: merged half-month span, in months."""
    intervals = sorted(iv for iv in (_half_coords(e['start_month'], e['end_month']) for e in entries or [])
                       if iv[1] > iv[0])
    if not intervals:
        return 1
    merged = [list(intervals[0])]
    for s, e in intervals[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return max(sum(e - s for s, e in merged) / 2, 0.5)


def _bill_amount(e):
    """Page rule: e.amount ?? e.tx_amount (a stored 0 is kept)."""
    return e.get('amount') if e.get('amount') is not None else e.get('tx_amount')


def bill_averages(types, entries, group=None):
    """[(name, average per month)] per bill type.

    Without `group`: the TOP_BILLS types with the most counted entries. With `group`: every
    type of that bill group, largest average first.
    Mirrors the bills page's per-type monthly average (Bills.html kpiCard, all-time
    view): entries with a transaction_id only, abs(amount ?? tx_amount), entries
    with neither skipped, total ÷ bill_span_months of the counted entries."""
    names = {t['id']: t['name'] for t in types or [] if group is None or t.get('group') == group}
    by_type = {}
    for e in entries or []:
        if not e.get('transaction_id') or _bill_amount(e) is None or e.get('bill_type_id') not in names:
            continue
        by_type.setdefault(e['bill_type_id'], []).append(e)
    stats = [(names[tid], len(es), sum(abs(float(_bill_amount(e))) for e in es) / bill_span_months(es))
             for tid, es in by_type.items()]
    if group is not None:
        return [(name, avg) for name, _, avg in sorted(stats, key=lambda t: (-t[2], t[0]))]
    top = sorted(stats, key=lambda t: (-t[1], t[0]))[:TOP_BILLS]
    return [(name, avg) for name, _, avg in top]


def build_bills(types, entries):
    """Monthly bill average of the BILLS_GROUP home: the group total, then a small tile per bill
    (extra.tiles: name, average, the bill type's colour)."""
    avgs = bill_averages(types, entries, group=BILLS_GROUP)
    if not avgs:
        return block('—', f'אין חשבונות ל{BILLS_GROUP}', dot='grey')
    colors = {t['name']: t.get('color') for t in types or [] if t.get('group') == BILLS_GROUP}
    tiles = [{'name': name, 'value': money(a), 'color': colors.get(name)} for name, a in avgs]
    return block(money(sum(a for _, a in avgs)), f'ממוצע חודשי — {BILLS_GROUP}', extra={'tiles': tiles})


# ── Spotify ────────────────────────────────────────────────────────────────
def signed_money(v):
    """money() with an explicit '+' on positive amounts; zero stays unsigned."""
    return ('+' if round(float(v or 0)) > 0 else '') + money(v)


def build_spotify(members):
    """Net balance of all participants (green when ≥ 0, red when negative), then every
    participant's balance, lowest first."""
    members = sorted(members or [], key=lambda m: float(m.get('balance') or 0))
    if not members:
        return block('—', 'אין משתתפים', dot='grey')
    net = sum(float(m.get('balance') or 0) for m in members)
    debtors = [m for m in members if round(float(m.get('balance') or 0)) < 0]
    neg = round(net) < 0
    details = [f"{m['name']} · {signed_money(m.get('balance'))}" for m in members]
    # each debtor's line is red, whatever the net (details stay in member order)
    tones = ['neg' if round(float(m.get('balance') or 0)) < 0 else None for m in members]
    # alert on every member in debt, even when the net is positive (amber then; red when the net is negative)
    dot = 'red' if neg else ('amber' if debtors else 'green')
    return block(signed_money(net), 'מאזן נטו של המשתתפים', details, dot=dot,
                 extra={'tone': 'neg' if neg else 'pos', 'detail_tones': tones},
                 attention='בחוב: ' + ' · '.join(f"{m['name']} {money(-float(m['balance']))}" for m in debtors))


# ── Plants ─────────────────────────────────────────────────────────────────
def build_plants(summary):
    """Plants to water today (due + overdue); automatic waterings need no action, so they are info only."""
    s = summary or {}
    due, overdue, auto = s.get('due_today', 0), s.get('overdue', 0), s.get('auto_today', 0)
    dot = 'red' if overdue else ('amber' if due else 'green')
    details = [f'{overdue} באיחור' if overdue else None,
               count_text(auto, 'עציץ אחד הושקה אוטומטית היום', 'עציצים הושקו אוטומטית היום') if auto else None]
    attention = ' · '.join(x for x in (
        count_text(overdue, 'עציץ אחד באיחור', 'עציצים באיחור') if overdue else None,
        count_text(due, 'עציץ אחד להשקות היום', 'עציצים להשקות היום') if due else None,
    ) if x)
    return block(str(due + overdue), 'עציצים להשקיה', details, dot=dot, attention=attention)


# ── Recurring charges ──────────────────────────────────────────────────────
def _this_month_on(day, today):
    """`day` of today's month, clamped to the month's length."""
    last = (date(today.year + today.month // 12, today.month % 12 + 1, 1) - date.resolution).day
    return today.replace(day=min(day, last))


def build_recurring(groups, today):
    """Next expected recurring charge this month. The page's cached next_expected is only as
    fresh as its last regeneration, so only its day of month is used, placed in today's month.
    Charges whose day already passed are skipped; the rest of the month is summed below."""
    upcoming = []
    for g in groups or []:
        d = as_date(g.get('next_expected'))
        if d and not g.get('possibly_stopped'):
            due = _this_month_on(d.day, today)
            if due >= today:
                upcoming.append((due, g))
    upcoming.sort(key=lambda x: x[0])
    if not upcoming:
        return block('—', 'אין חיובים צפויים עוד החודש', dot='grey')
    (d, g), rest = upcoming[0], upcoming[1:]
    details = [count_text(len(rest), 'עוד חיוב אחד החודש', 'חיובים נוספים החודש') + ' · ' +
               money(sum(float(r.get('current_amount') or 0) for _, r in rest))] if rest else []
    return block(money(g.get('current_amount')), f"{g['name']} · ב-{short_date(d)}", details)


# ── Tagger ─────────────────────────────────────────────────────────────────
def build_tagger(untagged, total):
    """Only what still needs tagging: the untagged count, then the newest untagged
    transactions as 'name · date' (newest first)."""
    if not total:
        return block('0', 'אין עסקאות לתיוג', dot='green')
    details = [' · '.join(x for x in (tx.get('name'), short_date(tx.get('exec_date'))) if x)
               for tx in (untagged or [])[:MAX_DETAILS]]
    return block(str(total), 'עסקאות ממתינות לתיוג', details)


# ── Files ──────────────────────────────────────────────────────────────────
def build_files(f):
    if not f:
        return block('—', 'אין קבצים', dot='grey')
    return block(short_date(f.get('last_update') or f.get('date')), 'קובץ אחרון',
                 [f.get('file_name'), f.get('format')])
