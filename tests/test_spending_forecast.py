"""Tests for the spending forecast (no DB: the pure functions on plain data)."""
from datetime import date

from RecurringCharges import collapse_rent
from SpendingForecast import (
    build_salary_profile, build_card_profiles, build_card_events, build_rent_profile, build_rent_events,
    build_recurring_events, compute_free_amount, compute_forecast, compute_both, usual_day,
)

AS_OF = date(2026, 10, 14)
HORIZON = date(2026, 11, 10)


def _salary(day=10, amount=15000, months=range(4, 10)):
    return [{'date': date(2026, m, day), 'amount': amount} for m in months]


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


def test_salary_modes_pick_harsh_or_average_day_and_amount():
    rows = [{'date': date(2026, 4, 9), 'amount': 15000}, {'date': date(2026, 5, 10), 'amount': 16000},
            {'date': date(2026, 6, 14), 'amount': 14000}]
    harsh = build_salary_profile(rows, AS_OF, 'max')
    avg = build_salary_profile(rows, AS_OF, 'avg')
    assert harsh['day'] == 14 and harsh['amount'] == 14000          # latest day, lowest salary
    assert avg['day'] == 11 and avg['amount'] == 15000              # mean day, mean salary
    assert harsh['next_date'] == date(2026, 10, 14)


def test_salary_next_month_when_received_and_small_deposit_ignored():
    rows = _salary() + [{'date': date(2026, 10, 9), 'amount': 15000}]
    p = build_salary_profile(rows, AS_OF, 'avg')
    assert p['received_this_month'] and p['next_date'] == date(2026, 11, 10)
    rows = _salary() + [{'date': date(2026, 10, 9), 'amount': 2000}]
    assert not build_salary_profile(rows, AS_OF, 'avg')['received_this_month']


def test_every_card_has_its_own_day():
    rows = _card('4603', day=10) + _card('1111', day=2, base=5000)
    prof = build_card_profiles(rows, AS_OF)
    assert {p['card']: p['day'] for p in prof} == {'4603': 10, '1111': 2}
    assert [p['card'] for p in prof] == ['1111', '4603']               # ordered by day


def test_card_modes_and_late_card():
    prof = build_card_profiles(_card('4603', day=10), AS_OF)           # October's charge missing
    assert prof[0]['avg_month'] == 3000 + 650 and prof[0]['max_month'] == 3900
    avg = build_card_events(prof, [], AS_OF, HORIZON, 'avg', AS_OF)
    mx = build_card_events(prof, [], AS_OF, HORIZON, 'max', AS_OF)
    assert sorted((e['date'], e['late']) for e in avg) == [(AS_OF, True), (date(2026, 11, 10), False)]
    assert sorted(e['amount'] for e in avg) == [3650, 3650] and sorted(e['amount'] for e in mx) == [3900, 3900]


def test_card_charged_this_month_is_skipped_and_held_charge_sets_date_and_floor():
    rows = _card('4603', day=10) + [{'card': '4603', 'name': 'כרטיס 4603', 'date': date(2026, 10, 10), 'amount': 3300},
                                     {'card': '4603', 'name': 'כרטיס 4603', 'date': date(2026, 11, 9), 'amount': 8000}]
    prof = build_card_profiles(rows, AS_OF)
    assert prof[0]['charged_this_month']
    ev = build_card_events(prof, rows, AS_OF, HORIZON, 'avg', AS_OF)
    assert [(e['date'], e['amount']) for e in ev] == [(date(2026, 11, 9), 8000)]   # exact Charge_Date, above the average


def test_held_charge_of_a_card_without_history_is_its_own_event():
    rows = [{'card': '9999', 'name': 'כרטיס 9999', 'date': date(2026, 10, 20), 'amount': 700}]
    ev = build_card_events(build_card_profiles(rows, AS_OF), rows, AS_OF, HORIZON, 'avg', AS_OF)
    assert [(e['date'], e['amount']) for e in ev] == [(date(2026, 10, 20), 700)]


def test_rent_is_read_from_the_raw_rows_not_from_recurring_groups():
    p = build_rent_profile(_rent_rows(5880), AS_OF, 'avg')
    assert p['amount'] == 5880 and p['day'] == 1 and p['paid_this_month'] == 5880
    assert build_rent_events(p, AS_OF, AS_OF, HORIZON)[0]['date'] == date(2026, 11, 1)   # October is paid
    assert len(build_rent_events(p, AS_OF, AS_OF, HORIZON)) == 1


def test_rent_unpaid_this_month_is_late_and_partial_payment_is_deducted():
    p = build_rent_profile(_rent_rows(5880, months=range(5, 10)), AS_OF, 'avg')      # October missing
    ev = build_rent_events(p, AS_OF, AS_OF, HORIZON)
    assert sorted((e['date'], e['late'], e['amount']) for e in ev) == [(AS_OF, True, 5880), (date(2026, 11, 1), False, 5880)]
    rows = _rent_rows(5880, months=range(5, 10)) + [{'date': date(2026, 10, 1), 'amount': 4500}]
    p = build_rent_profile(rows, AS_OF, 'avg', override=5880)                         # building fee still due
    ev = sorted(build_rent_events(p, AS_OF, AS_OF, HORIZON), key=lambda e: e['date'])
    assert (ev[0]['late'], ev[0]['amount']) == (True, 1380)


def test_rent_override_and_harsh_mode():
    rows = _rent_rows(4700, months=range(5, 8)) + _rent_rows(4900, months=range(8, 11))
    assert build_rent_profile(rows, AS_OF, 'avg')['amount'] == 4900
    rows[-1]['amount'] = 4800
    assert build_rent_profile(rows, AS_OF, 'max')['amount'] == 4900                   # highest of the last 3
    over = build_rent_profile(rows, AS_OF, 'avg', override=5880)
    assert over['amount'] == 5880 and over['overridden'] and over['detected'] == 4800
    assert build_rent_profile([], AS_OF, 'avg') is None
    assert build_rent_profile([], AS_OF, 'avg', override=5880)['day'] == 1


def test_bank_groups_card_paid_stopped_and_rent_are_filtered():
    card = _bank_group('Netflix', table='CardTransactions')
    stopped = dict(_bank_group('Old'), possibly_stopped=True)
    rent = _bank_group('שכירות', category='שכירות')
    ev, skipped = build_recurring_events([card, stopped, rent], AS_OF, AS_OF, HORIZON, 'avg')
    assert ev == [] and {s['reason'] for s in skipped} == {'card', 'stopped', 'rent'}
    ev, _ = build_recurring_events([_bank_group()], AS_OF, AS_OF, HORIZON, 'avg')
    assert [e['date'] for e in ev] == [date(2026, 10, 18)]
    ev, _ = build_recurring_events([_bank_group()], AS_OF, AS_OF, HORIZON, 'max')
    assert ev[0]['amount'] == 480


def test_free_amount_is_the_lowest_point():
    events = [{'date': date(2026, 10, 20), 'name': 'a', 'amount': 3000, 'kind': 'card'},
              {'date': date(2026, 11, 1), 'name': 'rent', 'amount': 4500, 'kind': 'rent'}]
    r = compute_free_amount(10000, events)
    assert r['free'] == 2500 and r['tight_name'] == 'rent' and events[0]['balance_after'] == 7000
    assert compute_free_amount(5000, events)['free'] == -2500


def _inputs(**kw):
    base = {'balance': 30000, 'balance_date': AS_OF,
            'salary_rows': _salary() + [{'date': date(2026, 10, 10), 'amount': 15000}],
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
    assert avg['totals'] == {'card': 3650, 'recurring': 380, 'rent': 5880, 'all': 9910}
    assert [e['name'] for e in avg['events']][-1] == 'כרטיס 4603'


def test_forecast_rent_override_changes_the_amount_in_both_scenarios():
    both = compute_both(_inputs(rent_rows=_rent_rows(4700, months=range(5, 10))), AS_OF, rent_override=5880)
    for sc in both['scenarios'].values():     # October unpaid (late) + November 1st
        assert sc['rent']['amount'] == 5880 and sc['totals']['rent'] == 2 * 5880


def test_overdue_salary_assumes_today():
    f = compute_forecast(_inputs(salary_rows=_salary()), AS_OF, 'avg')
    assert f['horizon'] == AS_OF and any('טרם' in n or 'עדיין לא נקלטה' in n for n in f['notes'])


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
