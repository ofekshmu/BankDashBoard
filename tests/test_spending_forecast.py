"""Tests for the spending forecast (no DB: the pure functions on plain data)."""
from datetime import date

from RecurringCharges import collapse_rent
from SpendingForecast import (
    build_salary_profile, build_card_profiles, build_card_events, build_recurring_events,
    compute_free_amount, compute_forecast, usual_day,
)

AS_OF = date(2026, 10, 14)


def _salary(day=10, amount=15000, months=((2026, 4), (2026, 5), (2026, 6), (2026, 7), (2026, 8), (2026, 9))):
    return [{'date': date(y, m, day), 'amount': amount} for y, m in months]


def _cards(day=2, amount=6000, name='ישראכרט', months=range(4, 10)):
    return [{'date': date(2026, m, day), 'name': name, 'amount': amount + m * 100} for m in months]


def _rent_group(paid_this_month=False):
    occs = [{'month': f'2026-{m:02d}', 'date': date(2026, m, 1), 'amount': 4500, 'table': 'BankTransactions'}
            for m in range(6, 11 if paid_this_month else 10)]
    return {'name': 'שכירות', 'group_key': 'שכירות', 'category': 'שכירות', 'current_amount': 4500,
            'max_amount': 4500, 'occurrences': occs, 'possibly_stopped': not paid_this_month and False}


def test_usual_day_prefers_most_common():
    assert usual_day([10, 10, 9, 11]) == 10
    assert usual_day([5, 6]) == 6      # no repeat: rounded average
    assert usual_day([]) == 1


def test_salary_next_date_this_month_when_not_received():
    p = build_salary_profile(_salary(), AS_OF)
    assert p['avg_amount'] == 15000 and p['day'] == 10
    assert not p['received_this_month']
    assert p['next_date'] == date(2026, 10, 10)    # already passed: handled by the forecast (late)


def test_salary_next_month_when_received():
    rows = _salary() + [{'date': date(2026, 10, 9), 'amount': 15000}]
    p = build_salary_profile(rows, AS_OF)
    assert p['received_this_month'] and p['next_date'] == date(2026, 11, 10)


def test_small_deposit_is_not_the_salary():
    rows = _salary() + [{'date': date(2026, 10, 9), 'amount': 2000}]
    assert not build_salary_profile(rows, AS_OF)['received_this_month']


def test_salary_day_override_and_clamping():
    p = build_salary_profile(_salary(), date(2026, 1, 20), salary_day=31)
    assert p['day'] == 31 and p['next_date'] == date(2026, 1, 31)
    p = build_salary_profile(_salary(), date(2026, 2, 3), salary_day=31)
    assert p['next_date'] == date(2026, 2, 28)


def test_card_profile_and_modes():
    prof = build_card_profiles(_cards(), AS_OF)
    assert len(prof) == 1 and prof[0]['day'] == 2
    assert prof[0]['avg_month'] == 6000 + 650 and prof[0]['max_month'] == 6900
    avg = build_card_events(prof, [], AS_OF, date(2026, 11, 10), 'avg')
    mx = build_card_events(prof, [], AS_OF, date(2026, 11, 10), 'max')
    assert sorted((e['date'], e['late']) for e in avg) == [(AS_OF, True), (date(2026, 11, 2), False)]   # October's 2nd was never charged
    assert avg[0]['amount'] == 6650 and mx[0]['amount'] == 6900


def test_card_charged_this_month_is_skipped_and_pending_is_a_floor():
    rows = _cards() + [{'date': date(2026, 10, 2), 'name': 'ישראכרט', 'amount': 5000}]
    prof = build_card_profiles(rows, date(2026, 10, 14))
    assert prof[0]['charged_this_month']
    ev = build_card_events(prof, [{'date': date(2026, 11, 2), 'amount': 8000}], date(2026, 10, 14),
                           date(2026, 11, 10), 'avg')
    assert len(ev) == 1 and ev[0]['amount'] == 8000     # the card already holds more than the average


def test_card_usual_day_passed_without_charge_is_late():
    prof = build_card_profiles(_cards(day=10), AS_OF)    # usual day 10, October's charge missing
    ev = build_card_events(prof, [], AS_OF, date(2026, 11, 10), 'avg', AS_OF)
    late = [e for e in ev if e['late']]
    assert len(late) == 1 and late[0]['date'] == AS_OF and late[0]['amount'] == 6650


def test_unmatched_pending_stays_its_own_event():
    prof = build_card_profiles(_cards(day=2), AS_OF)
    ev = build_card_events(prof, [{'date': date(2026, 10, 20), 'amount': 700}], AS_OF, date(2026, 11, 10), 'avg')
    assert any(e['amount'] == 700 and e['date'] == date(2026, 10, 20) for e in ev)


def test_rent_unpaid_with_passed_day_is_late_and_due_now():
    ev, skipped = build_recurring_events([_rent_group()], AS_OF, AS_OF, date(2026, 11, 10), 'avg')
    assert [(e['date'], e['late'], e['kind']) for e in ev if e['late']] == [(AS_OF, True, 'rent')]
    assert any(e['date'] == date(2026, 11, 1) for e in ev)


def test_rent_paid_this_month_waits_for_next_month():
    ev, _ = build_recurring_events([_rent_group(paid_this_month=True)], AS_OF, AS_OF, date(2026, 11, 10), 'avg')
    assert [e['date'] for e in ev] == [date(2026, 11, 1)]


def test_card_paid_and_stopped_groups_are_not_events():
    card_group = {'name': 'Netflix', 'occurrences': [{'month': '2026-09', 'date': date(2026, 9, 5), 'table': 'CardTransactions'}],
                  'current_amount': 50, 'max_amount': 50}
    stopped = dict(_rent_group(), possibly_stopped=True)
    ev, skipped = build_recurring_events([card_group, stopped], AS_OF, AS_OF, date(2026, 11, 10), 'avg')
    assert ev == [] and {s['reason'] for s in skipped} == {'card', 'stopped'}


def test_free_amount_is_the_lowest_point():
    events = [{'date': date(2026, 10, 20), 'name': 'a', 'amount': 3000, 'kind': 'card'},
              {'date': date(2026, 11, 1), 'name': 'rent', 'amount': 4500, 'kind': 'rent'}]
    r = compute_free_amount(10000, events, buffer=500)
    assert r['free'] == 10000 - 7500 - 500 and r['tight_name'] == 'rent' and not r['shortfall']
    assert events[0]['balance_after'] == 7000
    short = compute_free_amount(5000, events)
    assert short['shortfall'] and short['free'] == -2500


def test_full_forecast():
    cards = _cards() + [{'date': date(2026, 10, 2), 'name': 'ישראכרט', 'amount': 5000}]   # October already charged
    inputs = {'balance': 20000, 'balance_date': AS_OF, 'salary_rows': _salary(), 'card_rows': cards,
              'pending': [], 'groups': [_rent_group()]}
    f = compute_forecast(inputs, AS_OF, {'card_mode': 'avg'})
    assert f['ok'] and f['horizon'] == AS_OF            # salary overdue: expected today
    assert f['free'] == 20000 - 4500                    # only the late rent stands before it
    f = compute_forecast(inputs, AS_OF, {'card_mode': 'avg', 'salary_day': 25})
    assert f['horizon'] == date(2026, 10, 25) and f['free'] == 15500
    inputs['salary_rows'].append({'date': date(2026, 10, 9), 'amount': 15000})
    f = compute_forecast(inputs, AS_OF, {'card_mode': 'avg', 'buffer': 1000})
    # horizon 10/11: the late rent, 11/1 rent, 11/2 card (6650) -> 20000 - 4500 - 4500 - 6650 - 1000 buffer
    assert f['horizon'] == date(2026, 11, 10) and f['free'] == 20000 - 4500 - 4500 - 6650 - 1000
    assert f['totals']['rent'] == 9000 and f['totals']['card'] == 6650


def test_no_salary_is_reported():
    f = compute_forecast({'balance': 1, 'balance_date': AS_OF, 'salary_rows': [], 'card_rows': [], 'pending': [], 'groups': []}, AS_OF)
    assert not f['ok'] and f['reason'] == 'no_salary'


def test_collapse_rent_merges_cheques_of_a_month():
    tx = [{'table': 'BankTransactions', 'id': i, 'date': date(2026, 9, d), 'name': f'שיק {i}', 'amount': a, 'category': 'שכירות'}
          for i, (d, a) in enumerate([(1, 3000), (3, 1500)])]
    tx.append({'table': 'BankTransactions', 'id': 9, 'date': date(2026, 9, 5), 'name': 'x', 'amount': 10, 'category': 'מצרכים'})
    out = collapse_rent(tx)
    rent = [t for t in out if t['category'] == 'שכירות']
    assert len(rent) == 1 and rent[0]['amount'] == 4500 and rent[0]['name'] == 'שכירות' and len(out) == 2
