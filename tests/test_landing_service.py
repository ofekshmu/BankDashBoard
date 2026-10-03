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
    assert b == {'ok': True, 'dot': 'red', 'kpi': '3', 'caption': 'cap', 'details': ['x'], 'extra': {}}


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
