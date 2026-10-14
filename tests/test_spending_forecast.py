"""Tests for the spending forecast (no DB: the pure functions on plain data)."""
from datetime import date

from RecurringCharges import collapse_rent
from SpendingForecast import (
    build_salary_profile, build_card_profiles, build_card_events, build_rent_profile, build_rent_events,
    build_recurring_events, compute_free_amount, compute_forecast, compute_both, usual_day, _pivot_day,
    recurring_months, monthly_recurring_total,
)

AS_OF = date(2026, 10, 14)
HORIZON = date(2026, 11, 10)


def _salary(day=10, amount=15000, months=range(4, 10), name='חברת אלפא'):
    return [{'date': date(2026, m, day), 'amount': amount, 'name': name} for m in months]


def _two_salaries(last_a=10, last_b=11):
    """One salary on the 9th, another that lands at the end of the month / start of the next."""
    a = [{'date': date(2026, m, 9), 'amount': 15000, 'name': 'חברת אלפא'} for m in range(4, last_a)]
    b = [{'date': d, 'amount': 9000, 'name': 'בנק גמא'} for d in
         (date(2026, 4, 30), date(2026, 6, 1), date(2026, 6, 30), date(2026, 7, 31), date(2026, 9, 1))][: last_b]
    return a + b


def _card(card='4603', day=10, base=3000, months=range(4, 10)):
    """A card charged on `day` each month; the amount grows with the month so avg != max."""
    return [{'card': card, 'name': f'כרטיס {card}', 'date': date(2026, m, day), 'amount': base + m * 100} for m in months]


def _rent_rows(amount=5600, day=1, months=range(5, 11), fee=280, fee_day=5):
    """The rent (a different cheque each month) and the building fee, both in the rent category."""
    rows = [{'date': date(2026, m, day), 'amount': amount} for m in months]
    if fee:
        rows += [{'date': date(2026, m, fee_day), 'amount': fee} for m in months]
    return rows


def _bank_group(name='הראל ביטוח', day=18, amount=380, category='ביטוחים', table='BankTransactions'):
    occs = [{'month': f'2026-{m:02d}', 'date': date(2026, m, day), 'amount': amount, 'table': table} for m in range(6, 10)]
    return {'name': name, 'group_key': name, 'category': category, 'current_amount': amount,
            'max_amount': amount + 100, 'occurrences': occs, 'possibly_stopped': False}


def test_usual_day_is_never_an_average():
    assert usual_day([10, 10, 9, 11]) == 10
    assert usual_day([5, 6]) == 6      # nothing repeats: the latest day
    assert usual_day([5, 7, 7, 8]) == 7
    assert usual_day([]) == 1


def test_pivot_day_starts_the_cycle_after_the_widest_gap():
    assert _pivot_day([9, 10, 11]) == 9
    assert _pivot_day([30, 31, 1, 2]) == 30                    # the cycle starts on the 30th, 1st/2nd belong to it
    assert _pivot_day([29, 30, 31, 1, 2, 3]) == 29
    assert _pivot_day([6, 8, 12]) == 6
    assert _pivot_day([15]) == 15


def test_two_salaries_with_close_days_stay_two_streams_because_payers_differ():
    """Days jump ±3 days: the start-of-month salary (29..3) and the one around the 9th (6..12) overlap in
    day-of-month distance, so only the payer's name can tell them apart."""
    a = [{'date': date(2026, m, d), 'amount': 15000, 'name': 'חברת אלפא'} for m, d in
         ((4, 6), (5, 12), (6, 9), (7, 7), (8, 10), (9, 8))]
    b = [{'date': d, 'amount': 9000, 'name': 'בנק גמא'} for d in
         (date(2026, 4, 30), date(2026, 6, 2), date(2026, 6, 30), date(2026, 7, 29), date(2026, 9, 3), date(2026, 9, 30))]
    prof = build_salary_profile(a + b, AS_OF, AS_OF, 'avg')
    assert sorted(st['amount'] for st in prof['streams']) == [9000, 15000]
    assert len(prof['streams']) == 2


def test_one_salary_modes_pick_harsh_or_average_day_and_amount():
    rows = [{'date': date(2026, 4, 9), 'amount': 15000}, {'date': date(2026, 5, 10), 'amount': 16000},
            {'date': date(2026, 6, 14), 'amount': 14000}]
    harsh = build_salary_profile(rows, AS_OF, AS_OF, 'max')['streams'][0]
    avg = build_salary_profile(rows, AS_OF, AS_OF, 'avg')['streams'][0]
    assert harsh['day'] == 14 and harsh['amount'] == 14000          # latest day, lowest salary
    assert avg['day'] == 11 and avg['amount'] == 15000              # mean day, mean salary


def test_two_salaries_are_two_streams_and_horizon_is_the_nearest():
    prof = build_salary_profile(_two_salaries(), AS_OF, AS_OF, 'avg')
    assert [(st['day'], st['amount']) for st in prof['streams']] == [(9, 15000), (31, 9000)]
    # neither the 9th of October nor the end-of-September salary is in the data yet: both assumed arrived
    assert [a['date'] for a in prof['assumed']] == [date(2026, 9, 30), date(2026, 10, 9)]
    assert [u['date'] for u in prof['upcoming']][:2] == [date(2026, 10, 31), date(2026, 11, 9)]
    assert prof['next_date'] == date(2026, 10, 31)         # the end-of-month salary comes first


def test_received_salary_waits_for_next_cycle_and_overdue_one_is_assumed():
    received = _salary() + _salary(months=[10])
    prof = build_salary_profile(received, AS_OF, AS_OF, 'avg')
    assert prof['assumed'] == [] and prof['next_date'] == date(2026, 11, 10)
    overdue = build_salary_profile(_salary(), AS_OF, AS_OF, 'avg')
    assert [a['date'] for a in overdue['assumed']] == [date(2026, 10, 10)]     # taken as arrived on its date
    assert overdue['next_date'] == date(2026, 11, 10)


def test_recurring_definition_matches_the_recurring_page():
    ms = lambda keys, a=100: [{'month': k, 'amount': a} for k in keys]
    assert recurring_months(ms(['2026-07', '2026-08', '2026-09']), AS_OF)                    # 3 consecutive months
    assert recurring_months(ms(['2026-08', '2026-09']), AS_OF) == []                          # only 2
    assert recurring_months(ms(['2026-05', '2026-07', '2026-09']), AS_OF) == []               # no 3 in a row
    assert recurring_months(ms(['2025-12', '2026-01', '2026-02']), AS_OF) == []               # stale (last > 6 months before last complete month)
    wild = ms(['2026-07', '2026-08', '2026-09']) + [{'month': '2026-06', 'amount': 900}]
    assert [m['month'] for m in recurring_months(wild, AS_OF)] == ['2026-07', '2026-08', '2026-09']   # outlier dropped


def test_a_salary_that_shifted_from_the_31st_to_the_2nd_is_one_salary_whatever_it_is_called():
    """Usual days 31 and 2 are two days apart across the month's edge: one operation that moved a few days —
    even when the bank names the deposits differently, the amounts differ, and each family has its own run of months."""
    deposits = [(date(2026, 4, 2), 'משכורת אלפא', 13329), (date(2026, 5, 3), 'משכורת אלפא', 13400), (date(2026, 6, 2), 'משכורת אלפא', 13250),
                (date(2026, 7, 31), 'העברה אלפא בעמ', 8437), (date(2026, 8, 31), 'העברה אלפא בעמ', 8500), (date(2026, 9, 30), 'העברה אלפא בעמ', 8400)]
    rows = [{'date': d, 'amount': a, 'name': n} for d, n, a in deposits]
    for mode in ('avg', 'max'):
        prof = build_salary_profile(rows, AS_OF, AS_OF, mode)
        assert len(prof['streams']) == 1
        assert len([u for u in prof['upcoming'] if u['date'] <= date(2026, 11, 14)]) == 1      # one date in the month ahead


def test_merging_never_makes_a_salary_vanish_and_varying_pay_is_still_recurring():
    """Family X pays every month, family Y only in some months, so the merged cycles are 13k or 21k: the amounts are not
    judged (only the months), the salary stays — and so does the one at the 9th. The diagnostics say what was done."""
    x = [{'date': date(2026, m, 2), 'amount': 13329, 'name': 'חברת אלפא'} for m in range(4, 10)]
    y = [{'date': date(2026, m, 30), 'amount': 8437, 'name': 'בנק גמא'} for m in (4, 6, 8)]
    z = [{'date': date(2026, m, 9), 'amount': 22093, 'name': 'מוסד דלתא'} for m in range(4, 10)]
    prof = build_salary_profile(x + y + z, AS_OF, AS_OF, 'avg')
    assert sorted(st['day'] for st in prof['streams'])[-1] == 9 and len(prof['streams']) == 2
    assert {d['name'] for d in prof['diagnostics']} == {'חברת אלפא', 'בנק גמא', 'מוסד דלתא'}
    assert any('מוזגו' in d['status'] for d in prof['diagnostics'])


def test_a_group_that_is_not_recurring_is_named_in_the_diagnostics():
    prof = build_salary_profile(_salary(day=9) + [{'date': date(2026, 7, 20), 'amount': 4000, 'name': 'בונוס'}], AS_OF, AS_OF, 'avg')
    odd = [d for d in prof['diagnostics'] if d['name'] == 'בונוס'][0]
    assert 'לא חוזרת' in odd['status'] and len(prof['streams']) == 1


def test_two_salaries_further_apart_than_the_jitter_stay_two():
    a = [{'date': date(2026, m, 2), 'amount': 13329, 'name': 'חברת אלפא'} for m in range(4, 10)]
    z = [{'date': date(2026, m, 9), 'amount': 22093, 'name': 'בנק גמא'} for m in range(4, 10)]
    prof = build_salary_profile(a + z, AS_OF, AS_OF, 'avg')
    assert sorted(st['day'] for st in prof['streams']) == [2, 9]            # 7 days apart: different salaries


def test_a_salary_that_already_landed_under_another_name_is_not_assumed_again():
    """Stream A (the 2nd, named 'חברת אלפא') has no October deposit under its own name, but a deposit of about
    that size landed on Oct 1 under a different name: that is the October salary, not one to assume."""
    a = [{'date': date(2026, m, 2), 'amount': 13329, 'name': 'חברת אלפא'} for m in range(4, 10)]
    b = [{'date': date(2026, m, 20), 'amount': 8437, 'name': 'בנק גמא'} for m in range(4, 10)]
    oct1 = [{'date': date(2026, 10, 1), 'amount': 13329, 'name': 'העברה מחברת אלפא'}]
    with_deposit = build_salary_profile(a + b + oct1, AS_OF, AS_OF, 'avg')
    assert [x['date'] for x in with_deposit['assumed']] == []
    without = build_salary_profile(a + b, AS_OF, AS_OF, 'avg')
    assert [x['date'] for x in without['assumed']] == [date(2026, 10, 2)]      # truly missing: still assumed


def test_two_deposits_within_the_jitter_every_month_are_one_salary_paid_in_instalments():
    first = [{'date': date(2026, m, 2), 'amount': 13329, 'name': 'חברת אלפא'} for m in range(4, 10)]
    second = [{'date': date(2026, m, 31 if m in (5, 7, 8) else 30), 'amount': 8437, 'name': 'העברה אלפא'} for m in range(4, 10)]
    prof = build_salary_profile(first + second, AS_OF, AS_OF, 'avg')
    assert len(prof['streams']) == 1 and prof['streams'][0]['max_amount'] == 13329 + 8437       # a full cycle's deposits add up


def test_a_one_off_deposit_on_the_20th_is_not_a_salary_stream():
    rows = _salary(day=9, months=range(4, 10)) + [{'date': date(2026, 7, 20), 'amount': 4000, 'name': 'בונוס חד פעמי'}]    # bonus, once
    for mode in ('max', 'avg'):
        prof = build_salary_profile(rows, AS_OF, AS_OF, mode)
        assert [s['day'] for s in prof['streams']] == [9]
        assert all(u['date'].day == 9 for u in prof['upcoming'])
    only_once = [{'date': date(2026, 9, 20), 'amount': 4000, 'name': 'בונוס'}]
    assert build_salary_profile(only_once, AS_OF, AS_OF, 'max')['known'] is False


def test_every_card_has_its_own_day():
    rows = _card('4603', day=10) + _card('1111', day=2, base=5000)
    prof = build_card_profiles(rows, AS_OF)
    assert {p['card']: p['day'] for p in prof} == {'4603': 10, '1111': 2}
    assert [p['card'] for p in prof] == ['1111', '4603']               # ordered by day


def test_card_modes_and_unseen_charge_is_taken_on_its_usual_day():
    prof = build_card_profiles(_card('4603', day=10), AS_OF)           # October's charge missing in the data
    assert prof[0]['avg_month'] == 3000 + 650 and prof[0]['max_month'] == 3900
    avg = build_card_events(prof, [], AS_OF, HORIZON, 'avg')
    mx = build_card_events(prof, [], AS_OF, HORIZON, 'max')
    assert sorted(e['date'] for e in avg) == [date(2026, 10, 10), date(2026, 11, 10)]
    assert sorted(e['amount'] for e in avg) == [3650, 3650] and sorted(e['amount'] for e in mx) == [3900, 3900]


def test_card_charged_this_month_is_skipped_and_held_charge_sets_date_and_floor():
    rows = _card('4603', day=10) + [{'card': '4603', 'name': 'כרטיס 4603', 'date': date(2026, 10, 10), 'amount': 3300},
                                     {'card': '4603', 'name': 'כרטיס 4603', 'date': date(2026, 11, 9), 'amount': 8000}]
    prof = build_card_profiles(rows, AS_OF)
    assert prof[0]['charged_this_month']
    ev = build_card_events(prof, rows, AS_OF, HORIZON, 'avg')
    assert [(e['date'], e['amount']) for e in ev] == [(date(2026, 11, 9), 8000)]   # exact Charge_Date, above the average


def test_held_charge_of_a_card_without_history_is_its_own_event():
    rows = [{'card': '9999', 'name': 'כרטיס 9999', 'date': date(2026, 10, 20), 'amount': 700, 'auto': True}]
    ev = build_card_events(build_card_profiles(rows, AS_OF), rows, AS_OF, HORIZON, 'avg')
    assert [(e['date'], e['amount']) for e in ev] == [(date(2026, 10, 20), 700)]
    assert ev[0]['detail']['auto'] is True


def test_rent_and_building_fee_are_two_recurring_operations_told_apart_by_amount():
    p = build_rent_profile(_rent_rows(), AS_OF)
    assert [(i['name'], i['amount'], i['day']) for i in p['items']] == [('שכירות', 5600, 1), ('ועד בית', 280, 5)]
    assert p['amount'] == 5880 and all(i['paid_this_month'] for i in p['items'])
    assert build_rent_profile([], AS_OF) is None


def test_a_rent_update_is_one_operation_and_a_one_off_payment_is_ignored():
    rows = _rent_rows(5600, months=range(5, 8), fee=0) + _rent_rows(5880, months=range(8, 11), fee=0)
    p = build_rent_profile(rows, AS_OF)
    assert [(i['name'], i['amount']) for i in p['items']] == [('שכירות', 5880)]               # the latest amount
    assert build_rent_profile(_rent_rows(5880, months=range(5, 8), fee=0) + [{'date': date(2026, 9, 12), 'amount': 20000}], AS_OF)['amount'] == 5880
    assert build_rent_profile([{'date': date(2026, 9, 1), 'amount': 20000}], AS_OF) is None       # a single payment (deposit?)
    assert build_rent_profile(_rent_rows(5600, months=range(8, 10), fee=0), AS_OF) is None       # two months only


def test_a_doubled_payment_is_not_a_rent_update():
    """Two months of building fee paid at once (560 after six months of 280) is a one-off, not a new amount."""
    rows = _rent_rows(fee=280, months=range(5, 10)) + [{'date': date(2026, 10, 1), 'amount': 5600}, {'date': date(2026, 10, 5), 'amount': 560}]
    p = build_rent_profile(rows, AS_OF)
    assert [(i['name'], i['amount']) for i in p['items']] == [('שכירות', 5600), ('ועד בית', 280)] and p['amount'] == 5880


def test_rent_events_each_operation_on_its_own_day_and_unpaid_ones_are_assumed_paid_on_their_day():
    p = build_rent_profile(_rent_rows(), AS_OF)                                                # October is paid
    ev = sorted(build_rent_events(p, AS_OF, HORIZON), key=lambda e: e['date'])
    assert [(e['date'], e['name'], e['amount']) for e in ev] == [(date(2026, 11, 1), 'שכירות', 5600), (date(2026, 11, 5), 'ועד בית', 280)]
    assert [e['name'] for e in build_rent_events(p, AS_OF, date(2026, 11, 3))] == ['שכירות']       # the fee is past the horizon
    rows = _rent_rows(months=range(5, 10)) + [{'date': date(2026, 10, 1), 'amount': 5600}]   # fee missing in October
    ev = sorted(build_rent_events(build_rent_profile(rows, AS_OF), AS_OF, HORIZON), key=lambda e: e['date'])
    assert [(e['date'], e['name'], e['amount']) for e in ev] == [(date(2026, 10, 5), 'ועד בית', 280), (date(2026, 11, 1), 'שכירות', 5600), (date(2026, 11, 5), 'ועד בית', 280)]


def test_bank_groups_card_paid_stopped_and_rent_are_filtered():
    card = _bank_group('Netflix', table='CardTransactions')
    stopped = dict(_bank_group('Old'), possibly_stopped=True)
    rent = _bank_group('שכירות', category='שכירות')
    ev, skipped = build_recurring_events([card, stopped, rent], AS_OF, HORIZON, 'avg')
    assert ev == [] and {s['reason'] for s in skipped} == {'card', 'stopped', 'rent'}
    ev, _ = build_recurring_events([_bank_group()], AS_OF, HORIZON, 'avg')
    assert [e['date'] for e in ev] == [date(2026, 10, 18)]
    ev, _ = build_recurring_events([_bank_group()], AS_OF, HORIZON, 'max')
    assert ev[0]['amount'] == 480
    ev, _ = build_recurring_events([_bank_group(day=5)], AS_OF, HORIZON, 'avg')
    assert sorted(e['date'] for e in ev) == [date(2026, 10, 5), date(2026, 11, 5)]   # unseen this month: taken on its day


def test_free_amount_is_the_lowest_point_and_a_salary_lifts_the_balance():
    events = [{'date': date(2026, 10, 20), 'name': 'a', 'amount': 3000, 'kind': 'card'},
              {'date': date(2026, 11, 1), 'name': 'rent', 'amount': 4500, 'kind': 'rent'}]
    r = compute_free_amount(10000, events)
    assert r['free'] == 2500 and r['tight_name'] == 'rent' and events[0]['balance_after'] == 7000
    assert compute_free_amount(5000, events)['free'] == -2500
    with_income = events + [{'date': date(2026, 10, 25), 'name': 'sal', 'amount': -9000, 'kind': 'income'}]
    assert compute_free_amount(5000, with_income)['lowest_balance'] == 5000 - 3000   # dip before the salary


def _inputs(**kw):
    base = {'balance': 30000, 'balance_date': AS_OF,
            'salary_rows': _salary() + _salary(months=[10]),
            'card_rows': _card('4603', day=10) + [{'card': '4603', 'name': 'כרטיס 4603', 'date': date(2026, 10, 10), 'amount': 3300}],
            'rent_rows': _rent_rows(), 'groups': [_bank_group()]}
    base.update(kw)
    return base


def test_month_left_counts_only_charges_after_today_until_the_month_end():
    """Of the charges ahead (Oct 18 insurance, Nov 1 rent, Nov 5 fee, Nov 10 card) only the Oct 18 one falls in AS_OF's month."""
    f = compute_both(_inputs(), AS_OF)['scenarios']['avg']
    left = f['month_left']
    assert left['end'] == AS_OF.replace(day=31) and left['count'] == 1 and left['total'] == 380


def test_forecast_scenarios_are_both_computed_and_harsh_is_not_looser():
    both = compute_both(_inputs(), AS_OF)
    avg, mx = both['scenarios']['avg'], both['scenarios']['max']
    assert both['ok'] and avg['mode'] == 'avg' and mx['mode'] == 'max'
    # horizon 11/10: Oct 18 insurance, Nov 1 rent 5600, Nov 5 building fee 280, card 4603 on Nov 10
    assert avg['free'] == 30000 - 380 - 5600 - 280 - 3650
    assert mx['free'] == 30000 - 480 - 5600 - 280 - 3900 and mx['free'] < avg['free']
    assert avg['totals'] == {'card': 3650, 'recurring': 380, 'rent': 5880, 'all': 9910, 'known': 0, 'estimated': 9910}
    charges = [e['name'] for e in avg['events'] if e['kind'] != 'income']
    assert charges[:4] == ['הראל ביטוח', 'שכירות', 'ועד בית', 'כרטיס 4603']
    assert not any(e['assumed'] for e in avg['events'])      # everything is still ahead of today


def test_monthly_recurring_total_counts_bank_and_card_paid_but_not_stopped_or_rent():
    groups = [_bank_group('הראל ביטוח', amount=380), _bank_group('Netflix', amount=50, table='CardTransactions'),
              dict(_bank_group('Old', amount=99), possibly_stopped=True), _bank_group('שכירות', amount=5880, category='שכירות')]
    assert monthly_recurring_total(groups, 'avg') == {'total': 430, 'count': 2, 'by_card_count': 1, 'by_card_total': 50}
    assert monthly_recurring_total(groups, 'max')['total'] == 480 + 150           # the highest amount of each
    both = compute_both(_inputs(groups=groups), AS_OF)
    fixed = both['scenarios']['avg']['fixed_monthly']
    assert (fixed['recurring'], fixed['count'], fixed['by_card_count'], fixed['rent'], fixed['total']) == (430, 2, 1, 5880, 6310)


def test_the_chart_looks_a_month_ahead_and_the_free_amount_stops_at_the_salary():
    f = compute_forecast(_inputs(), AS_OF, 'avg')
    assert f['chart_end'] == date(2026, 11, 14) and f['horizon'] == date(2026, 11, 10)
    names = [(e['date'], e['kind'], e['after_salary']) for e in f['events']]
    assert (date(2026, 11, 10), 'income', False) in names                 # the salary itself is on the chart
    assert any(e['after_salary'] for e in f['events']) or f['events'][-1]['date'] <= f['horizon']
    # nothing after the salary is part of the totals or the lowest point
    assert f['totals']['all'] == sum(e['amount'] for e in f['events'] if not e['after_salary'] and e['kind'] != 'income')
    # a late-month horizon still shows a full month: salary far away, chart_end earlier than horizon
    far = compute_forecast(_inputs(salary_rows=_salary(day=28) + _salary(day=28, months=[10])), AS_OF, 'avg')
    assert far['horizon'] == date(2026, 11, 28) and far['chart_end'] == date(2026, 11, 14)


def test_card_charges_right_after_the_salary_limit_what_can_be_spent_before_it():
    """Spending 37,000 before the salary would be fine until the salary — but the card bills what was spent
    just after it, and 20,000 of it comes off right away: the free amount is the lowest point of the whole stretch."""
    events = [{'date': date(2026, 10, 20), 'name': 'rent', 'amount': 3000, 'kind': 'rent'},
              {'date': date(2026, 11, 1), 'name': 'משכורת', 'amount': -13000, 'kind': 'income'},
              {'date': date(2026, 11, 2), 'name': 'כרטיס', 'amount': 20000, 'kind': 'card'}]
    r = compute_free_amount(40000, events)
    assert r['free'] == 40000 - 3000 + 13000 - 20000 and r['tight_name'] == 'כרטיס' and r['tight_date'] == date(2026, 11, 2)


def test_the_forecast_counts_the_card_that_bills_right_after_the_next_salary():
    cards = _card('4603', day=2, base=15000) + [{'card': '4603', 'name': 'כרטיס 4603', 'date': date(2026, 10, 2), 'amount': 15000}]
    f = compute_forecast(_inputs(salary_rows=_salary(day=1) + _salary(day=1, months=[10]), card_rows=cards, groups=[], rent_rows=[]), AS_OF, 'avg')
    nov2 = [e for e in f['events'] if e['name'] == 'כרטיס 4603'][0]
    assert nov2['after_salary'] and f['free'] < 30000                     # the Nov 2 charge (after the Nov 1 salary) is in the minimum
    assert f['tight_name'] == 'כרטיס 4603' or f['free'] == f['lowest_balance']


def test_an_assumed_salary_does_not_make_the_free_amount_equal_to_the_balance():
    """The balance 30,000 plus a salary that already arrived (not in the data yet) is what is in the account now;
    the charges still ahead come off that, so the free amount is below it (it used to be the bare balance)."""
    f = compute_forecast(_inputs(salary_rows=_salary(), card_rows=_card('4603', day=10) + [
        {'card': '4603', 'name': 'כרטיס 4603', 'date': date(2026, 10, 10), 'amount': 3300}]), AS_OF, 'avg')
    assert [e['name'] for e in f['events'] if e['assumed']] == ['משכורת (יום 10)']
    assert f['balance_now'] == 30000 + 15000                                  # the assumed salary is part of "now"
    ahead = sum(e['amount'] for e in f['events'] if not e['assumed'] and not e['after_salary'] and e['kind'] != 'income')
    assert ahead > 0 and f['free'] == 30000 + 15000 - ahead and f['free'] < f['balance_now']


def test_an_assumed_charge_lowers_the_balance_now_and_future_ones_come_off_it():
    events = [{'date': date(2026, 10, 12), 'name': 'rent', 'amount': 5000, 'kind': 'rent', 'assumed': True},
              {'date': date(2026, 10, 20), 'name': 'card', 'amount': 3000, 'kind': 'card', 'assumed': False}]
    r = compute_free_amount(20000, events, today=AS_OF)
    assert r['balance_now'] == 15000 and r['free'] == 12000 and r['tight_name'] == 'card'


def test_the_monthly_recurring_figure_is_the_whole_month_whatever_day_it_is_or_what_was_paid():
    """All the recurring operations of the month (1st to the end) — bank charges and the rent with its fee — paid or not yet."""
    groups = [_bank_group('הראל ביטוח', day=18, amount=380), _bank_group('חברת חשמל', day=25, amount=220, category='חשבונות'),
              _bank_group('Netflix', amount=50, table='CardTransactions')]
    early = compute_forecast(_inputs(groups=groups, balance_date=date(2026, 10, 3), rent_rows=_rent_rows(months=range(5, 10))), date(2026, 10, 3), 'avg')
    late = compute_forecast(_inputs(groups=groups, balance_date=date(2026, 10, 28)), date(2026, 10, 28), 'avg')
    expected = 380 + 220 + 50 + 5600 + 280              # the card-paid Netflix is a recurring charge too
    assert early['fixed_monthly']['total'] == late['fixed_monthly']['total'] == expected
    assert (early['fixed_monthly']['recurring'], early['fixed_monthly']['count'], early['fixed_monthly']['by_card_count']) == (650, 3, 1)


def test_totals_separate_what_is_known_from_what_is_estimated():
    held = [{'card': '4603', 'name': 'כרטיס 4603', 'date': date(2026, 11, 9), 'amount': 8000}]
    f = compute_forecast(_inputs(card_rows=_inputs()['card_rows'] + held), AS_OF, 'avg')
    assert f['totals']['known'] == 8000 and f['totals']['estimated'] == f['totals']['all'] - 8000


def test_unseen_things_up_to_today_are_assumed_done_and_overdue_salary_arrives():
    f = compute_forecast(_inputs(salary_rows=_salary(), rent_rows=_rent_rows(months=range(5, 10))), AS_OF, 'avg')
    assumed = {e['name']: e for e in f['events'] if e['assumed']}
    assert assumed['שכירות']['date'] == date(2026, 10, 1) and assumed['ועד בית']['date'] == date(2026, 10, 5)
    assert assumed['משכורת (יום 10)']['amount'] == -15000 and assumed['משכורת (יום 10)']['kind'] == 'income'
    assert f['totals']['rent'] == 2 * 5880 and f['horizon'] == date(2026, 11, 10)   # October's and November's, fee included


def test_no_salary_is_reported():
    f = compute_both(_inputs(salary_rows=[]), AS_OF)
    assert f['scenarios']['avg']['ok'] is False and f['scenarios']['avg']['reason'] == 'no_salary'


def test_collapse_rent_names_each_recurring_amount_as_its_own_charge():
    tx = [{'table': 'BankTransactions', 'id': m * 10 + k, 'date': date(2026, m, d), 'name': f'שיק {m}{k}', 'amount': a, 'category': 'שכירות'}
          for m in range(6, 10) for k, (d, a) in enumerate([(1, 5600), (5, 280)])]
    tx.append({'table': 'BankTransactions', 'id': 99, 'date': date(2026, 9, 12), 'name': 'x', 'amount': 15000, 'category': 'שכירות'})   # one-off
    tx.append({'table': 'BankTransactions', 'id': 98, 'date': date(2026, 9, 5), 'name': 'מכולת', 'amount': 10, 'category': 'מצרכים'})
    out = collapse_rent(tx)
    names = sorted(t['name'] for t in out if t['category'] == 'שכירות')
    assert names.count('שכירות') == 4 and names.count('ועד בית') == 4 and names.count('שכירות 15000') == 1   # the one-off stays apart
    assert len([t for t in out if t['category'] != 'שכירות']) == 1
