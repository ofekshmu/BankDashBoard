from datetime import date, datetime

import landing_service as ls

TODAY = date(2026, 10, 4)


# ── helpers ────────────────────────────────────────────────────────────────
def test_money_and_pct():
    assert ls.money(12345.6) == '12,346₪'
    assert ls.money(-50.4) == '-50₪'
    assert ls.money(None) == '0₪'
    assert ls.pct(4.21) == '+4.2%'
    assert ls.pct(-1.26) == '-1.3%'
    assert ls.pct(0) == '+0.0%'


def test_dates():
    assert ls.as_date('2026-09-10') == date(2026, 9, 10)
    assert ls.as_date('2026-09-10T08:00:00') == date(2026, 9, 10)
    assert ls.as_date(datetime(2026, 9, 10, 8)) == date(2026, 9, 10)
    assert ls.as_date('') is None and ls.as_date('junk') is None
    assert ls.short_date('2026-09-10') == '10.09.26'
    assert ls.month_label('2026_10') == 'אוקטובר 2026'


def test_cap():
    assert ls.cap(['a', 'b']) == ['a', 'b']
    assert ls.cap(['a', 'b', 'c', 'd', 'e']) == ['a', 'b', '+3 נוספים']


def test_block_shape():
    b = ls.block('3', 'cap', ['x', None, ''], dot='red')
    assert b == {'ok': True, 'dot': 'red', 'kpi': '3', 'caption': 'cap', 'details': ['x'],
                 'attention': None, 'extra': {}}


def test_attention_kept_only_on_amber_and_red():
    assert ls.block('1', 'c', dot='red', attention='x')['attention'] == 'x'
    assert ls.block('1', 'c', dot='amber', attention='x')['attention'] == 'x'
    for dot in ('green', 'grey', None):
        assert ls.block('1', 'c', dot=dot, attention='x')['attention'] is None


def test_count_text():
    assert ls.count_text(1, 'אחד', 'רבים') == 'אחד'
    assert ls.count_text(3, 'אחד', 'רבים') == '3 רבים'


# ── monthly ────────────────────────────────────────────────────────────────
MONTHS = [{'key': '2026_08'}, {'key': '2026_09'}, {'key': '2026_10'}]


def test_pick_month_prefers_today_else_latest():
    assert ls.pick_month(MONTHS, TODAY) == '2026_10'
    assert ls.pick_month(MONTHS[:2], TODAY) == '2026_09'
    assert ls.pick_month([], TODAY) is None


def test_monthly_counts_both_alert_lists_and_dots():
    b = ls.build_monthly(MONTHS, '2026_10', {'alerts': [1, 2], 'organizer_alerts': [3]})
    assert b['kpi'] == '3' and b['dot'] == 'red' and b['caption'] == 'התראות באוקטובר 2026'
    assert ls.build_monthly(MONTHS, '2026_10', {'alerts': [], 'organizer_alerts': None})['dot'] == 'green'
    assert ls.build_monthly(MONTHS, '2026_10', {'alerts': [1, 2]})['dot'] == 'amber'


def test_monthly_extra_lists_months_newest_first():
    b = ls.build_monthly(MONTHS, '2026_10', {'alerts': []})
    assert b['extra']['current'] == '2026_10'
    assert [m['key'] for m in b['extra']['months']] == ['2026_10', '2026_09', '2026_08']
    assert b['extra']['months'][0]['label'] == 'אוקטובר 2026'


def test_monthly_no_data():
    b = ls.build_monthly(MONTHS, '2026_10', None)
    assert b['dot'] == 'grey' and b['kpi'] == '—' and 'אוקטובר' in b['caption']
    assert ls.build_monthly([], None, None)['dot'] == 'grey'


# ── accounts ───────────────────────────────────────────────────────────────
ACCTS = {'accounts': {
    'Main Bank': [['2026-09-10', 20000.0]],
    'Cash': [['2026-09-26', 4000.0]],
    'Old': [['2026-07-01', 500.0]],
    'Closed': [['2026-01-01', 0]],
    'Total': [['2026-09-01', 1.0], ['2026-09-26', 24500.0]],
}}


def test_accounts_total_matches_page_cash_adjustment():
    # page: Total + (sum(round(balance * rate)) - Cash last value)
    total = ls.accounts_total(ACCTS['accounts'], {'ILS': 3000, 'USD': 1000}, {'USD': 3.7})
    assert total == 24500 + (3000 + 3700 - 4000)
    assert ls.accounts_total(ACCTS['accounts'], None, {}) == 24500
    assert ls.accounts_total({}, {}, {}) is None


def test_accounts_block_lists_stale_accounts():
    b = ls.build_accounts(ACCTS, None, {}, TODAY)
    assert b['kpi'] == '24,500₪' and b['caption'] == 'שווי כל החשבונות'
    assert b['dot'] == 'amber' and b['details'] == ['Old · עודכן 01.07.26']   # zero-balance 'Closed' skipped


def test_accounts_block_all_fresh_and_empty():
    fresh = {'accounts': {'A': [['2026-10-01', 5]], 'Total': [['2026-10-01', 5]]}}
    b = ls.build_accounts(fresh, None, {}, TODAY)
    assert b['dot'] == 'green' and b['details'] == ['כל החשבונות מעודכנים']
    assert ls.build_accounts(None, None, {}, TODAY)['dot'] == 'grey'


# ── cards ──────────────────────────────────────────────────────────────────
def test_cards_counts_active_and_lists_top3():
    cards = [{'card_id': '1111', 'network': 'Visa', 'current_charge': 100},
             {'card_id': '2222', 'network': 'Max', 'current_charge': 900},
             {'card_id': '3333', 'network': 'Isracard', 'current_charge': 0},
             {'card_id': '4444', 'network': '', 'current_charge': 50},
             {'card_id': '5555', 'network': 'Visa', 'current_charge': 10}]
    b = ls.build_cards(cards)
    assert b['kpi'] == '4' and b['caption'] == 'כרטיסים פעילים החודש' and b['dot'] is None
    assert b['details'] == ['Max ·2222 · 900₪', 'Visa ·1111 · 100₪', '·4444 · 50₪']


def test_cards_none_active():
    b = ls.build_cards([{'card_id': '1', 'current_charge': 0}])
    assert b['kpi'] == '0' and b['dot'] == 'grey'


# ── housing ────────────────────────────────────────────────────────────────
def test_housing_block():
    m = {'annual_return_pct': 4.21, 'total_return_pct': 31.0, 'default_rate': 5,
         'equity_appreciated': 500000, 'alltime_income': 120000, 'net_invested': 400000}
    b = ls.build_housing(m)
    assert b['kpi'] == '+4.2%' and b['caption'] == 'תשואה שנתית (5% עליית ערך)' and b['dot'] == 'green'
    assert b['details'] == ['תשואה כוללת במכירה +31.0%', 'רווח נקי 220,000₪']
    assert ls.build_housing(dict(m, annual_return_pct=-2))['dot'] == 'red'
    assert ls.build_housing({})['dot'] == 'grey'


def test_housing_missing_default_rate_uses_page_default():
    m = {'annual_return_pct': 4.21, 'default_rate': None}
    assert ls.build_housing(m)['caption'] == 'תשואה שנתית (5% עליית ערך)'
    assert ls.build_housing(dict(m, default_rate=0))['caption'] == 'תשואה שנתית (5% עליית ערך)'   # page: || 5
    assert ls.build_housing(dict(m, default_rate=3.5))['caption'] == 'תשואה שנתית (3.5% עליית ערך)'


# ── timeline ───────────────────────────────────────────────────────────────
def test_timeline():
    b = ls.build_timeline({'name': 'חתונה', 'event_date': '2026-11-02', 'created_at': datetime(2026, 10, 1)})
    assert b['kpi'] == 'חתונה' and b['caption'] == 'האירוע האחרון שנוצר' and b['details'] == ['02.11.26']
    assert ls.build_timeline(None)['dot'] == 'grey'


# ── bills ──────────────────────────────────────────────────────────────────
# Same rules as the bills page's per-type "ממוצע חודשי" (Bills.html kpiCard):
# only entries with a transaction_id, abs(amount ?? tx_amount), entries with
# neither are skipped, total ÷ merged half-month span (calcSpanMonths).
BILL_TYPES = [{'id': i, 'name': n} for i, n in
              ((1, 'חשמל'), (2, 'מים'), (3, 'ארנונה'), (4, 'גז'), (5, 'אינטרנט'), (6, 'ועד'), (7, 'סלולר'))]


def E(type_id, start, end, amount=None, tx_amount=None, tx=1):
    return {'bill_type_id': type_id, 'start_month': start, 'end_month': end,
            'transaction_id': tx, 'amount': amount, 'tx_amount': tx_amount}


BILL_ENTRIES = [
    E(1, '2026-01', '2026-02', 600),
    E(1, '2026-03', '2026-04', 400),
    E(1, '2026-05', '2026-05', 250),      # contiguous → 5 months, 1250 / 5 = 250
    E(2, '2026-01', '2026-02', 200),
    E(2, '2026-03', '2026-04', 100),      # 300 / 4 = 75
    E(3, '2026-01', '2026-01', 500),
    E(4, '2026-01', '2026-01', 50),
    E(5, '2026-01', '2026-01', 100),
    E(6, '2026-01', '2026-01', 30),
    E(7, '2026-01', '2026-01', 60),
]


def avg_of(entries, types=BILL_TYPES):
    return dict(ls.bill_averages(types, entries))


def test_bill_averages_top5_by_entry_count():
    avgs = ls.bill_averages(BILL_TYPES, BILL_ENTRIES)
    assert avgs[0] == ('חשמל', 250) and avgs[1] == ('מים', 75)
    assert len(avgs) == 5                     # top 5 types by counted entries (ties → name)


def test_bill_amount_falls_back_to_linked_transaction_amount():
    # Amount NULL → tx_amount (page: e.amount ?? e.tx_amount); a stored 0 is kept
    assert avg_of([E(1, '2026-01', '2026-01', None, -300), E(1, '2026-02', '2026-02', 100, -900)]) == {'חשמל': 200}
    assert avg_of([E(1, '2026-01', '2026-02', 0, -900)]) == {'חשמל': 0}


def test_bill_negative_amounts_are_absolute():
    assert avg_of([E(1, '2026-01', '2026-01', -200), E(1, '2026-02', '2026-02', 100)]) == {'חשמל': 150}


def test_bill_entries_without_any_amount_add_no_months():
    # 600 over Jan–Feb; the amount-less March entry must not stretch the span
    assert avg_of([E(1, '2026-01', '2026-02', 600), E(1, '2026-03', '2026-03')]) == {'חשמל': 300}


def test_bill_entries_without_transaction_are_excluded():
    assert avg_of([E(1, '2026-01', '2026-01', 100), E(1, '2026-02', '2026-02', 900, tx=None)]) == {'חשמל': 100}
    assert ls.bill_averages(BILL_TYPES, [E(1, '2026-01', '2026-01', 900, tx=None)]) == []


def test_bill_overlapping_entries_merge_their_months():
    # Jan–Mar ∪ Feb–Apr = 4 months, not 6
    assert avg_of([E(1, '2026-01', '2026-03', 300), E(1, '2026-02', '2026-04', 100)]) == {'חשמל': 100}


def test_bill_gaps_between_entries_are_not_counted():
    assert avg_of([E(1, '2026-01', '2026-01', 100), E(1, '2026-06', '2026-06', 300)]) == {'חשמל': 200}


def test_bill_half_month_boundaries():
    # mid-Jan → end of Feb = 3 half-months = 1.5 months
    assert avg_of([E(1, '2026-01-15', '2026-02', 150)]) == {'חשמל': 100}
    # start of Jan → mid-Jan = 1 half-month = 0.5 months
    assert avg_of([E(1, '2026-01', '2026-01-15', 50)]) == {'חשמל': 100}
    # mid-Jan → mid-Mar = 4 half-months = 2 months
    assert avg_of([E(1, '2026-01-15', '2026-03-15', 400)]) == {'חשמל': 200}


def test_bill_span_months_matches_page_helper():
    assert ls.bill_span_months([]) == 1
    assert ls.bill_span_months([E(1, '2026-01', '2026-01')]) == 1
    assert ls.bill_span_months([E(1, '2025-12', '2026-01'), E(1, '2026-01', '2026-03')]) == 4
    assert ls.bill_span_months([E(1, '2026-01-15', '2026-01-15')]) == 1      # empty interval → 1


def test_bills_block_shows_all_five():
    b = ls.build_bills(BILL_TYPES, BILL_ENTRIES)
    assert b['caption'] == 'ממוצע חודשי — 5 החשבונות הנפוצים'
    assert len(b['details']) == 5 and b['details'][0] == 'חשמל · 250₪'
    assert b['kpi'] == ls.money(sum(a for _, a in ls.bill_averages(BILL_TYPES, BILL_ENTRIES)))
    assert ls.build_bills(BILL_TYPES, [])['dot'] == 'grey'


# ── spotify ────────────────────────────────────────────────────────────────
def test_spotify_only_debtors():
    b = ls.build_spotify([{'name': 'דנה', 'balance': -30}, {'name': 'יוסי', 'balance': 20},
                          {'name': 'רון', 'balance': -60}])
    assert b['kpi'] == '90₪' and b['caption'] == 'חובות פתוחים' and b['dot'] == 'amber'
    assert b['details'] == ['רון · 60₪', 'דנה · 30₪']


def test_spotify_caps_and_no_debt():
    many = [{'name': f'm{i}', 'balance': -10 - i} for i in range(5)]
    assert ls.build_spotify(many)['details'][-1] == '+3 נוספים'
    b = ls.build_spotify([{'name': 'יוסי', 'balance': 0}])
    assert b['kpi'] == '0₪' and b['dot'] == 'green' and b['details'] == ['אין חובות']


# ── plants ─────────────────────────────────────────────────────────────────
def test_plants():
    b = ls.build_plants({'due_today': 2, 'overdue': 1, 'auto_pending_confirm': 3})
    assert b['kpi'] == '3' and b['caption'] == 'עציצים להשקיה' and b['dot'] == 'red'
    assert b['details'] == ['1 באיחור', '3 השקיות אוטומטיות ממתינות לאישור']
    assert ls.build_plants({'due_today': 0, 'overdue': 0, 'auto_pending_confirm': 1})['dot'] == 'amber'
    assert ls.build_plants({'due_today': 0, 'overdue': 0, 'auto_pending_confirm': 0})['dot'] == 'green'


# ── recurring ──────────────────────────────────────────────────────────────
def test_recurring_next_upcoming_non_stopped():
    groups = [{'name': 'נטפליקס', 'current_amount': 55, 'next_expected': '2026-10-09', 'possibly_stopped': False},
              {'name': 'חדר כושר', 'current_amount': 199, 'next_expected': '2026-10-05', 'possibly_stopped': True},
              {'name': 'ביטוח', 'current_amount': 310.4, 'next_expected': date(2026, 10, 6), 'possibly_stopped': False},
              {'name': 'ישן', 'current_amount': 10, 'next_expected': '2026-09-01', 'possibly_stopped': False}]
    b = ls.build_recurring(groups, TODAY)
    assert b['kpi'] == '310₪' and b['caption'] == 'ביטוח · ב-06.10.26'
    assert ls.build_recurring([], TODAY)['dot'] == 'grey'


# ── tagger ─────────────────────────────────────────────────────────────────
def test_tagger():
    tx = {'name': 'שופרסל', 'exec_date': '2026-10-02', 'charge_value': 212.5,
          'transaction_value': 300, 'category': 'סופר'}
    b = ls.build_tagger(tx)
    assert b['kpi'] == '212₪' and b['caption'] == 'שופרסל' and b['details'] == ['סופר · 02.10.26']
    assert ls.build_tagger(dict(tx, charge_value=None))['kpi'] == '300₪'
    assert ls.build_tagger(None)['dot'] == 'grey'


# ── files ──────────────────────────────────────────────────────────────────
def test_files():
    b = ls.build_files({'file_name': 'leumi_10.xlsx', 'format': 'Leumi Bank',
                        'date': '2026-10-01', 'last_update': datetime(2026, 10, 3, 9)})
    assert b['kpi'] == '03.10.26' and b['caption'] == 'קובץ אחרון'
    assert b['details'] == ['leumi_10.xlsx', 'Leumi Bank']
    assert ls.build_files(None)['dot'] == 'grey'


# ── attention lines ────────────────────────────────────────────────────────
def test_attention_lines_per_block():
    assert ls.build_monthly(MONTHS, '2026_10', {'alerts': [1, 2, 3]})['attention'] == '3 התראות באוקטובר 2026'
    assert ls.build_monthly(MONTHS, '2026_10', {'alerts': [1]})['attention'] == 'התראה אחת באוקטובר 2026'
    assert ls.build_monthly(MONTHS, '2026_10', {'alerts': []})['attention'] is None
    assert ls.build_accounts(ACCTS, None, {}, TODAY)['attention'] == 'חשבון אחד לא עודכן מעל 30 יום'
    m = {'annual_return_pct': -2.04, 'default_rate': 5}
    assert ls.build_housing(m)['attention'] == 'תשואה שנתית שלילית -2.0%'
    assert ls.build_housing(dict(m, annual_return_pct=3))['attention'] is None
    debt = [{'name': 'א', 'balance': -30}, {'name': 'ב', 'balance': -20.4}]
    assert ls.build_spotify(debt)['attention'] == '2 חברים בחוב · 50₪'
    assert ls.build_spotify([{'name': 'א', 'balance': 5}])['attention'] is None


def test_plants_attention_lists_each_nonzero_count():
    b = ls.build_plants({'due_today': 2, 'overdue': 1, 'auto_pending_confirm': 0})
    assert b['attention'] == 'עציץ אחד באיחור · 2 עציצים להשקות היום'
    b = ls.build_plants({'due_today': 0, 'overdue': 0, 'auto_pending_confirm': 3})
    assert b['attention'] == '3 השקיות אוטומטיות ממתינות לאישור'
    assert ls.build_plants({'due_today': 0, 'overdue': 0, 'auto_pending_confirm': 0})['attention'] is None
