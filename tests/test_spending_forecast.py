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


def _rent_rows(amount=5880, day=1, months=range(5, 11)):
    return [{'date': date(2026, m, day), 'amount': amount} for m in months]


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


def test_a_one_off_deposit_on_the_20th_is_not_a_salary_stream():
    rows = _salary(day=9, months=range(4, 10)) + [{'date': date(2026, 7, 20), 'amount': 4000, 'name': 'בונוס חד פעמי'}]    # bonus, once
    for mode in ('max', 'avg'):
        prof = build_salary_profile(rows, AS_OF, AS_OF, mode)
        assert [s['day'] for s in prof['streams']] == [9]
        assert all(u['date'].day == 9 for u in prof['upcoming'])
    only_once = [{'date': date(2026, 9, 20), 'amount': 4000, 'name': 'בונוס'}]
    assert build_salary_profile(only_once, AS_OF, AS_OF, 'max')['known'] is False


def test_rent_must_be_recurring_to_be_assumed():
    assert build_rent_profile(_rent_rows(5880, months=range(8, 10)), AS_OF) is None            # two months only
    assert build_rent_profile([{'date': date(2026, 9, 1), 'amount': 20000}], AS_OF) is None   # a single payment (deposit?)
    assert build_rent_profile(_rent_rows(5880, months=range(7, 10)), AS_OF)['amount'] == 5880


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


def test_rent_is_the_monthly_average_read_from_the_raw_rows():
    rows = _rent_rows(5000, months=range(5, 8)) + _rent_rows(6000, months=range(8, 10)) + [{'date': date(2026, 10, 1), 'amount': 5880}]
    p = build_rent_profile(rows, AS_OF)
    assert p['amount'] == round((3 * 5000 + 2 * 6000) / 5, 2) and p['day'] == 1   # completed months only
    assert p['paid_this_month'] == 5880 and [m['month'] for m in p['monthly']][-1] == '2026-10'
    assert build_rent_profile([], AS_OF) is None


def test_rent_paid_this_month_waits_for_next_month_and_unpaid_is_taken_on_its_day():
    p = build_rent_profile(_rent_rows(5880), AS_OF)
    assert [e['date'] for e in build_rent_events(p, AS_OF, HORIZON)] == [date(2026, 11, 1)]
    p = build_rent_profile(_rent_rows(5880, months=range(5, 10)), AS_OF)                # October missing
    ev = sorted(build_rent_events(p, AS_OF, HORIZON), key=lambda e: e['date'])
    assert [(e['date'], e['amount']) for e in ev] == [(date(2026, 10, 1), 5880), (date(2026, 11, 1), 5880)]
    rows = _rent_rows(5880, months=range(5, 10)) + [{'date': date(2026, 10, 1), 'amount': 4500}]
    ev = sorted(build_rent_events(build_rent_profile(rows, AS_OF), AS_OF, HORIZON), key=lambda e: e['date'])
    assert (ev[0]['date'], ev[0]['amount']) == (date(2026, 10, 1), 1380)               # the part still unpaid


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
            'rent_rows': _rent_rows(5880), 'groups': [_bank_group()]}
    base.update(kw)
    return base


def test_forecast_scenarios_are_both_computed_and_harsh_is_not_looser():
    both = compute_both(_inputs(), AS_OF)
    avg, mx = both['scenarios']['avg'], both['scenarios']['max']
    assert both['ok'] and avg['mode'] == 'avg' and mx['mode'] == 'max'
    # horizon 11/10: Oct 18 insurance, Nov 1 rent 5880, card 4603 on Nov 10
    assert avg['free'] == 30000 - 380 - 5880 - 3650
    assert mx['free'] == 30000 - 480 - 5880 - 3900 and mx['free'] < avg['free']
    assert avg['totals'] == {'card': 3650, 'recurring': 380, 'rent': 5880, 'all': 9910, 'known': 0, 'estimated': 9910}
    assert [e['name'] for e in avg['events']][-1] == 'כרטיס 4603'
    assert not any(e['assumed'] for e in avg['events'])      # everything is still ahead of today


def test_monthly_recurring_total_leaves_out_card_paid_stopped_and_rent():
    groups = [_bank_group('הראל ביטוח', amount=380), _bank_group('Netflix', amount=50, table='CardTransactions'),
              dict(_bank_group('Old', amount=99), possibly_stopped=True), _bank_group('שכירות', amount=5880, category='שכירות')]
    assert monthly_recurring_total(groups, 'avg') == {'total': 380, 'count': 1}
    assert monthly_recurring_total(groups, 'max') == {'total': 480, 'count': 1}
    both = compute_both(_inputs(groups=groups), AS_OF)
    assert both['scenarios']['avg']['fixed_monthly'] == {'recurring': 380, 'count': 1, 'rent': 5880, 'total': 6260}


def test_totals_separate_what_is_known_from_what_is_estimated():
    held = [{'card': '4603', 'name': 'כרטיס 4603', 'date': date(2026, 11, 9), 'amount': 8000}]
    f = compute_forecast(_inputs(card_rows=_inputs()['card_rows'] + held), AS_OF, 'avg')
    assert f['totals']['known'] == 8000 and f['totals']['estimated'] == f['totals']['all'] - 8000


def test_unseen_things_up_to_today_are_assumed_done_and_overdue_salary_arrives():
    f = compute_forecast(_inputs(salary_rows=_salary(), rent_rows=_rent_rows(5880, months=range(5, 10))), AS_OF, 'avg')
    assumed = {e['name']: e for e in f['events'] if e['assumed']}
    assert assumed['שכירות + ועד בית']['date'] == date(2026, 10, 1)
    assert assumed['משכורת (יום 10)']['amount'] == -15000 and assumed['משכורת (יום 10)']['kind'] == 'income'
    assert f['totals']['rent'] == 2 * 5880 and f['horizon'] == date(2026, 11, 10)


def test_no_salary_is_reported():
    f = compute_both(_inputs(salary_rows=[]), AS_OF)
    assert f['scenarios']['avg']['ok'] is False and f['scenarios']['avg']['reason'] == 'no_salary'


def test_collapse_rent_merges_cheques_of_a_month():
    tx = [{'table': 'BankTransactions', 'id': i, 'date': date(2026, 9, d), 'name': f'שיק {i}', 'amount': a, 'category': 'שכירות'}
          for i, (d, a) in enumerate([(1, 3000), (3, 1500)])]
    tx.append({'table': 'BankTransactions', 'id': 9, 'date': date(2026, 9, 5), 'name': 'x', 'amount': 10, 'category': 'מצרכים'})
    out = collapse_rent(tx)
    rent = [t for t in out if t['category'] == 'שכירות']
    assert len(rent) == 1 and rent[0]['amount'] == 4500 and rent[0]['name'] == 'שכירות' and len(out) == 2
