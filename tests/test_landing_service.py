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


def test_cash_ils_total_matches_the_cash_pie():
    # pie: positive balances only, each round(balance * rate)
    assert ls.cash_ils_total({'ILS': 4714, 'EUR': 150, 'JPY': 172000, 'USD': -5},
                             {'EUR': 3.4482758, 'JPY': 0.0194137, 'USD': 3.7}) == 4714 + 517 + 3339
    assert ls.cash_ils_total({'ILS': 100}, {}) == 100                     # ILS needs no rate


def test_cash_ils_total_is_unknown_without_a_rate_for_a_held_currency():
    assert ls.cash_ils_total({'ILS': 100, 'JPY': 172000}, {}) is None     # never count ¥ as ₪
    assert ls.cash_ils_total({'ILS': 100, 'JPY': 0}, {}) == 100           # nothing held, no rate needed
    assert ls.cash_ils_total(None, {}) is None
    # unknown total → no cash correction, the server Total stands
    assert ls.accounts_total(ACCTS['accounts'], {'JPY': 1000}, {}) == 24500


TREND_TOTAL = [['2026-06-01', 100.0], ['2026-07-03', 1000.0], ['2026-08-15', 1100.0], ['2026-10-02', 1200.0]]


def test_accounts_trend_last_three_months_from_the_value_at_the_window_start():
    t = ls.accounts_trend(TREND_TOTAL, 0, date(2026, 10, 4))
    # window starts 2026-07-04: the 07-03 point is the value then, June is dropped
    assert t['points'] == [['2026-07-03', 1000], ['2026-08-15', 1100], ['2026-10-02', 1200]]
    assert t['change'] == 200 and t['change_pct'] == 20.0


def test_accounts_trend_is_shifted_by_the_cash_delta_so_it_ends_at_the_kpi():
    t = ls.accounts_trend(TREND_TOTAL, 100, date(2026, 10, 4))
    assert t['points'][-1] == ['2026-10-02', 1300] and t['change'] == 200 and t['change_pct'] == 18.2


def test_accounts_trend_one_point_per_half_month_and_spikes_smoothed_away():
    total = [['2026-07-05', 1000.0], ['2026-07-20', 1010.0],
             ['2026-08-05', 5000.0],                                   # one-off spike
             ['2026-08-20', 1020.0],
             ['2026-09-01', 100.0], ['2026-09-02', 1030.0], ['2026-09-03', 1040.0],   # same half-month
             ['2026-10-03', 1050.0]]
    t = ls.accounts_trend(total, 0, date(2026, 10, 4))
    assert [p[1] for p in t['points']] == [1000, 1010, 1020, 1030, 1030, 1050]   # no 5000, no 100
    assert [p[0] for p in t['points']] == ['2026-07-05', '2026-07-20', '2026-08-05', '2026-08-20',
                                           '2026-09-03', '2026-10-03']
    assert t['change'] == 50                                            # line's start → current value


def test_accounts_trend_without_history_before_the_window_or_enough_points():
    t = ls.accounts_trend(TREND_TOTAL[2:], 0, date(2026, 10, 4))
    assert t['points'][0] == ['2026-08-15', 1100] and t['change_pct'] == 9.1
    assert ls.accounts_trend(TREND_TOTAL[-1:], 0, date(2026, 10, 4)) is None
    assert ls.accounts_trend([], 0, date(2026, 10, 4)) is None


def test_accounts_block_carries_the_trend():
    accts = {'accounts': dict(ACCTS['accounts'], Total=TREND_TOTAL)}
    b = ls.build_accounts(accts, {'ILS': 4100}, {}, date(2026, 10, 4))   # cash delta = 4100 - 4000
    assert b['kpi'] == '1,300₪' and b['extra']['trend']['points'][-1] == ['2026-10-02', 1300]
    assert ls.build_accounts(ACCTS, None, {}, TODAY)['extra']['trend']['change'] == 24499


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
def test_cards_counts_active_names_the_month_and_lists_them_all():
    cards = [{'card_id': '1111', 'network': 'Visa', 'current_charge': 100},
             {'card_id': '2222', 'network': 'Max', 'current_charge': 900},
             {'card_id': '3333', 'network': 'Isracard', 'current_charge': 0},
             {'card_id': '4444', 'network': '', 'current_charge': 50},
             {'card_id': '5555', 'network': 'Visa', 'current_charge': 10}]
    b = ls.build_cards(cards, '2026-10')
    assert b['kpi'] == '4' and b['caption'] == 'כרטיסים פעילים באוקטובר 2026' and b['dot'] is None
    assert b['details'] == ['Max ·2222 · 900₪', 'Visa ·1111 · 100₪', '·4444 · 50₪', 'Visa ·5555 · 10₪']
    assert ls.build_cards(cards)['caption'] == 'כרטיסים פעילים החודש'   # no month known


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
def test_spotify_net_balance_red_when_negative_and_lists_everyone():
    b = ls.build_spotify([{'name': 'דנה', 'balance': -30}, {'name': 'יוסי', 'balance': 20},
                          {'name': 'רון', 'balance': -60}])
    assert b['kpi'] == '-70₪' and b['caption'] == 'מאזן נטו של המשתתפים'
    assert b['dot'] == 'red' and b['extra']['tone'] == 'neg'
    assert b['details'] == ['רון · -60₪', 'דנה · -30₪', 'יוסי · +20₪']   # lowest balance first


def test_spotify_debtors_are_red_even_when_the_net_is_positive():
    b = ls.build_spotify([{'name': 'דנה', 'balance': -30}, {'name': 'יוסי', 'balance': 80},
                          {'name': 'רון', 'balance': 0}])
    assert b['dot'] == 'green' and b['extra']['detail_tones'] == ['neg', None, None]


def test_spotify_green_when_net_positive_or_zero_and_lists_all_without_cap():
    many = [{'name': f'm{i}', 'balance': 10 + i} for i in range(5)] + [{'name': 'x', 'balance': -1}]
    b = ls.build_spotify(many)
    assert b['kpi'] == '+59₪' and b['dot'] == 'green' and b['extra']['tone'] == 'pos'
    assert len(b['details']) == 6 and b['attention'] is None
    b = ls.build_spotify([{'name': 'יוסי', 'balance': 0}])
    assert b['kpi'] == '0₪' and b['dot'] == 'green' and b['details'] == ['יוסי · 0₪']
    assert ls.build_spotify([])['dot'] == 'grey'


# ── plants ─────────────────────────────────────────────────────────────────
def test_plants():
    b = ls.build_plants({'due_today': 2, 'overdue': 1, 'auto_today': 3})
    assert b['kpi'] == '3' and b['caption'] == 'עציצים להשקיה' and b['dot'] == 'red'
    assert b['details'] == ['1 באיחור', '3 עציצים הושקו אוטומטית היום']
    assert ls.build_plants({'due_today': 1, 'overdue': 0, 'auto_today': 0})['dot'] == 'amber'
    # automatic waterings need no action: info only, never amber
    b = ls.build_plants({'due_today': 0, 'overdue': 0, 'auto_today': 1})
    assert b['dot'] == 'green' and b['details'] == ['עציץ אחד הושקה אוטומטית היום']


# ── recurring ──────────────────────────────────────────────────────────────
def test_recurring_next_upcoming_non_stopped():
    groups = [{'name': 'נטפליקס', 'current_amount': 55, 'next_expected': '2026-10-09', 'possibly_stopped': False},
              {'name': 'חדר כושר', 'current_amount': 199, 'next_expected': '2026-10-05', 'possibly_stopped': True},
              {'name': 'ביטוח', 'current_amount': 310.4, 'next_expected': date(2026, 10, 6), 'possibly_stopped': False},
              {'name': 'ישן', 'current_amount': 10, 'next_expected': '2026-09-01', 'possibly_stopped': False}]
    b = ls.build_recurring(groups, TODAY)
    assert b['kpi'] == '310₪' and b['caption'] == 'ביטוח · ב-06.10.26'
    assert b['details'] == ['עוד חיוב אחד החודש · 55₪']
    assert ls.build_recurring([], TODAY)['dot'] == 'grey'


def test_recurring_uses_this_month_even_when_the_snapshot_dates_are_old():
    # the page's snapshot was built in August, so every next_expected is in September
    groups = [{'name': 'ספוטיפיי', 'current_amount': 44, 'next_expected': '2026-09-22', 'possibly_stopped': False},
              {'name': 'גוגל', 'current_amount': 8, 'next_expected': '2026-09-01', 'possibly_stopped': False},
              {'name': 'ביטוח', 'current_amount': 66, 'next_expected': '2026-09-28', 'possibly_stopped': False}]
    b = ls.build_recurring(groups, TODAY)
    assert b['kpi'] == '44₪' and b['caption'] == 'ספוטיפיי · ב-22.10.26'      # Google's 01.10 already passed
    assert b['details'] == ['עוד חיוב אחד החודש · 66₪']


def test_recurring_clamps_the_day_and_handles_nothing_left_this_month():
    g = [{'name': 'ארנונה', 'current_amount': 900, 'next_expected': '2026-08-31', 'possibly_stopped': False}]
    assert ls.build_recurring(g, date(2026, 11, 2))['caption'] == 'ארנונה · ב-30.11.26'
    b = ls.build_recurring(g, date(2026, 11, 30))
    assert b['kpi'] == '900₪'                                                  # due today still counts
    b = ls.build_recurring([dict(g[0], next_expected='2026-09-01')], date(2026, 11, 2))
    assert b['dot'] == 'grey' and b['caption'] == 'אין חיובים צפויים עוד החודש'


# ── tagger ─────────────────────────────────────────────────────────────────
UNTAGGED = [{'name': 'פז דלק', 'exec_date': '2026-10-04'}, {'name': 'העברה בBIT', 'exec_date': '2026-10-01'},
            {'name': 'שופרסל', 'exec_date': '2026-09-28'}, {'name': 'ישן', 'exec_date': '2026-09-01'}]


def test_tagger_shows_only_untagged_count_and_newest_name_and_date():
    b = ls.build_tagger(UNTAGGED, 57)
    assert b['kpi'] == '57' and b['caption'] == 'עסקאות ממתינות לתיוג'
    assert b['details'] == ['פז דלק · 04.10.26', 'העברה בBIT · 01.10.26', 'שופרסל · 28.09.26']


def test_tagger_nothing_left_to_tag():
    b = ls.build_tagger([], 0)
    assert b['kpi'] == '0' and b['caption'] == 'אין עסקאות לתיוג' and b['dot'] == 'green' and b['details'] == []


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
    assert ls.build_spotify(debt)['attention'] == 'מאזן שלילי -50₪ · 2 חברים בחוב'
    assert ls.build_spotify([{'name': 'א', 'balance': 5}])['attention'] is None


def test_plants_attention_lists_each_nonzero_count():
    b = ls.build_plants({'due_today': 2, 'overdue': 1, 'auto_today': 4})
    assert b['attention'] == 'עציץ אחד באיחור · 2 עציצים להשקות היום'
    assert ls.build_plants({'due_today': 0, 'overdue': 0, 'auto_today': 3})['attention'] is None


# ── monthly: net income + investments of last and current month ────────────
FLOW_CHARTS = {'general_net': [5200.4, 3000], 'general_current_net': -812.6,
               'general_investments_out': [2000, 500], 'general_investments_in': [300, 0],
               'general_current_investments_out': 1500, 'general_current_investments_in': 0,
               'general_earnings': [9000.6, 8000], 'general_spendings': [4100.2, 5000],
               'general_current_earnings': 1200.2, 'general_current_spendings': 2300.7}
FLOW_PAYLOAD = {'alerts': [], 'charts': FLOW_CHARTS}   # same shape as /api/monthly/<key>/data


def test_month_flow_previous_then_current():
    flow = ls.month_flow(FLOW_PAYLOAD, TODAY)
    assert flow == [{'key': '2026_09', 'label': 'ספטמבר 2026', 'income': 9001, 'spend': 4100,
                     'net': 5200, 'invest': 1700},
                    {'key': '2026_10', 'label': 'אוקטובר 2026', 'income': 1200, 'spend': 2301,
                     'net': -813, 'invest': 1500}]


def test_month_flow_crosses_the_year_and_handles_missing_data():
    flow = ls.month_flow(FLOW_PAYLOAD, date(2026, 1, 15))
    assert [f['key'] for f in flow] == ['2025_12', '2026_01']
    assert ls.month_flow({'alerts': []}, TODAY) == []
    assert ls.month_flow({'charts': dict(FLOW_CHARTS, general_net=[])}, TODAY) == []
    assert ls.month_flow(FLOW_CHARTS, TODAY) == []   # figures at the top level are not read
    assert ls.month_flow(None, TODAY) == []


def test_monthly_block_carries_the_flow():
    b = ls.build_monthly(MONTHS, '2026_10', FLOW_PAYLOAD, TODAY)
    assert [f['net'] for f in b['extra']['flow']] == [5200, -813]
    assert ls.build_monthly(MONTHS, '2026_10', FLOW_PAYLOAD)['extra']['flow'] == []   # no date → no flow
