"""Housing projects (new-build apartments such as Mona): the money model.

Payments tagged to the project split into
  price   - goes into the apartment price (builds the value you own; comes back on a sale)
  cost    - an extra expense (fees, tax, advisers): spent, never an asset
  income  - money in, e.g. rent: not an asset
  refund  - money back from a price payment
Equity (the asset shown on the accounts page) = price payments - refunds + appreciation of the
whole price, the same idea as value - what is still owed.
"""
from datetime import date

import pytest

import src_utils.housing_projects as hp

T = date(2026, 10, 9)


def tx(day, name='העברה מהחשבון', out=0.0, income=0.0, desc='', kind=None, key=None):
    auto = hp.classify_kind(name, desc, out, income)
    return {'key': key or f'BankTransactions:{name}:{day}:{out}:{income}', 'table': 'BankTransactions', 'id': 1,
            'date': day, 'name': name, 'description': desc, 'out': out, 'income': income,
            'auto_kind': auto, 'kind': kind or auto}


# ── classification ─────────────────────────────────────────────────────────
def test_outgoing_defaults_to_price_and_fees_default_to_cost():
    assert hp.classify_kind('העברה מהחשבון', '', 15000, 0) == 'price'
    assert hp.classify_kind('קבוצת בר סרוסי השקעו', 'פעימה ראשונה - ליווי', 5000, 0) == 'cost'
    assert hp.classify_kind('עו"ד כהן', '', 3000, 0) == 'cost'
    assert hp.classify_kind('עו״ד כהן', '', 3000, 0) == 'cost'            # gershayim variant
    assert hp.classify_kind('מס רכישה', '', 9000, 0) == 'cost'
    assert hp.classify_kind('תשלום עוד אחד', '', 9000, 0) == 'price'     # the word "עוד" is not "עו"ד"


def test_incoming_defaults_to_income():
    assert hp.classify_kind('שכירות', '', 0, 4000) == 'income'


def test_override_must_fit_the_direction_otherwise_automatic_wins():
    assert hp.apply_override('price', 'cost', is_out=True) == 'cost'
    assert hp.apply_override('cost', 'price', is_out=True) == 'price'
    assert hp.apply_override('income', 'refund', is_out=False) == 'refund'
    assert hp.apply_override('price', 'refund', is_out=True) == 'price'    # refund is for incoming rows only
    assert hp.apply_override('income', 'cost', is_out=False) == 'income'
    assert hp.apply_override('price', None, is_out=True) == 'price'
    assert hp.apply_override('price', 'bogus', is_out=True) == 'price'


# ── appreciation ───────────────────────────────────────────────────────────
def test_years_between_clamps_at_zero():
    assert hp.years_between(date(2026, 1, 1), date(2027, 1, 1)) == pytest.approx(365 / 365.25)
    assert hp.years_between(date(2027, 1, 1), date(2026, 1, 1)) == 0


def test_grown_value_compounds_yearly_and_never_goes_below_price():
    assert hp.grown_value(1_000_000, 3, 1.0) == pytest.approx(1_030_000)
    assert hp.grown_value(1_000_000, 3, 2.0) == pytest.approx(1_060_900)
    assert hp.grown_value(1_000_000, 0, 5.0) == 1_000_000
    assert hp.grown_value(1_000_000, 3, 0) == 1_000_000
    assert hp.grown_value(None, 3, 1.0) is None


# ── derived numbers (one formula set; the page mirrors it in JS) ───────────
INP = {'price': 1_000_000, 'paid_price': 100_000, 'extra_costs': 5_000, 'income_total': 0,
       'net_invested': 105_000, 'years_now': 1.0, 'years_delivery': 3.0, 'years_invested': 1.0,
       'expected_mortgage': 900_000}


def test_derive_equity_is_paid_in_plus_appreciation():
    d = hp.derive(INP, 3)
    assert d['appreciation'] == pytest.approx(30_000)
    assert d['market_value'] == pytest.approx(1_030_000)
    assert d['equity'] == pytest.approx(130_000)
    assert d['remaining_to_pay'] == 900_000
    assert d['monthly_appreciation'] == pytest.approx(1_030_000 * ((1.03) ** (1 / 12) - 1))


def test_derive_profit_is_appreciation_plus_income_minus_extra_costs():
    d = hp.derive(INP, 3)
    assert d['profit'] == pytest.approx(25_000)                     # 30,000 + 0 - 5,000; the paid-in price comes back
    assert d['total_return_pct'] == pytest.approx(25_000 / 105_000 * 100)
    assert d['annual_return_pct'] == pytest.approx(25_000 / 105_000 * 100)   # exactly one year invested
    d2 = hp.derive(dict(INP, income_total=12_000, net_invested=105_000), 0)
    assert d2['profit'] == pytest.approx(7_000)                     # no growth: rent - fees


def test_derive_does_not_annualize_less_than_a_year():
    for years in (0.1, 0.3, 0.99):
        d = hp.derive(dict(INP, years_invested=years), 3)
        assert d['total_return_pct'] is not None and d['annual_return_pct'] is None
    assert hp.derive(dict(INP, years_invested=1.0), 3)['annual_return_pct'] is not None


def test_derive_without_price_or_investment():
    d = hp.derive(dict(INP, price=None, years_delivery=None, expected_mortgage=None), 3)
    assert d['market_value'] is None and d['appreciation'] == 0 and d['equity'] == 100_000
    assert d['remaining_to_pay'] is None and d['value_at_delivery'] is None and d['equity_at_delivery'] is None
    d = hp.derive(dict(INP, paid_price=0, extra_costs=0, net_invested=0, years_invested=None), 3)
    assert d['total_return_pct'] is None and d['annual_return_pct'] is None


def test_derive_delivery_projection_uses_the_expected_mortgage():
    d = hp.derive(INP, 3)
    assert d['value_at_delivery'] == pytest.approx(1_000_000 * 1.03 ** 3)
    assert d['equity_at_delivery'] == pytest.approx(1_000_000 * 1.03 ** 3 - 900_000)


def test_expected_mortgage_is_the_price_minus_the_larger_of_paid_and_own_funds_share():
    # own funds = 25% of the price (mortgage 75%): the 10% now plus another 15% at delivery
    assert hp.expected_mortgage(1_000_000, 25, 15_000) == 750_000
    assert hp.expected_mortgage(1_000_000, 25, 250_000) == 750_000
    assert hp.expected_mortgage(1_000_000, 25, 300_000) == 700_000     # paid more than planned: less to finance
    assert hp.expected_mortgage(1_000_000, 25, 2_000_000) == 0
    assert hp.expected_mortgage(None, 25, 15_000) is None


# ── sums by kind ───────────────────────────────────────────────────────────
def test_sums_split_price_cost_income_and_refunds():
    txs = [tx(date(2026, 7, 8), out=15_000),
           tx(date(2026, 6, 10), name='קבוצת בר סרוסי', desc='ליווי', out=5_000),
           tx(date(2026, 8, 1), name='שכירות', income=2_000),
           tx(date(2026, 8, 5), name='החזר פיקדון', income=1_000, kind='refund')]
    s = hp.sums(txs)
    assert s == {'paid_price': 14_000, 'extra_costs': 5_000, 'income_total': 2_000, 'refunds': 1_000,
                 'net_invested': 19_000, 'out_total': 20_000}


# ── growth start ───────────────────────────────────────────────────────────
def test_growth_start_prefers_contract_date_then_timeline_then_first_payment_then_today():
    pay = [date(2026, 7, 8)]
    ev = [date(2026, 10, 9), date(2026, 11, 1)]
    assert hp.growth_start(date(2026, 9, 1), ev, pay, T) == (date(2026, 9, 1), 'contract')
    assert hp.growth_start(None, ev, pay, T) == (date(2026, 10, 9), 'timeline')
    assert hp.growth_start(None, [], pay, T) == (date(2026, 7, 8), 'payment')
    assert hp.growth_start(None, [], [], T) == (T, 'today')


# ── the project summary, with Mona's real starting data ────────────────────
def settings(**kw):
    s = {'key': 'mona', 'name': 'מונה', 'tx_category': 'דירת קבלן', 'timeline_category': 'cat_x',
         'price': None, 'down_pct': 10.0, 'mortgage_pct': 75.0, 'contract_date': None, 'delivery_date': None,
         'growth_pct': 3.0}
    s.update(kw)
    return s


REAL = [tx(date(2026, 7, 8), out=15_000),
        tx(date(2026, 6, 10), name='קבוצת בר סרוסי השקעו', desc='פעימה ראשונה - ליווי', out=5_000)]
EVENTS = [{'id': 79, 'name': 'חתימה על בקשת רכישה', 'event_date': '2026-10-09', 'description': '', 'color': '#ec4899'}]


def test_summary_without_a_price_still_counts_the_money():
    p = hp.build_project(settings(), REAL, EVENTS, T)
    assert p['has_price'] is False
    assert p['money']['paid_price'] == 15_000 and p['money']['extra_costs'] == 5_000
    assert p['derived']['equity'] == 15_000 and p['derived']['appreciation'] == 0
    assert p['derived']['profit'] == -5_000 and p['derived']['total_return_pct'] == pytest.approx(-25.0)
    assert p['growth_start'] == '2026-10-09' and p['growth_start_source'] == 'timeline'
    assert p['today'] == '2026-10-09'


def test_summary_with_price_tracks_down_payment_and_financing():
    p = hp.build_project(settings(price=1_000_000, delivery_date=date(2028, 10, 9)), REAL, EVENTS, T)
    assert p['has_price'] and p['derived']['remaining_to_pay'] == 985_000
    assert p['down'] == {'target': 100_000, 'paid': 15_000, 'left': 85_000, 'progress_pct': 15.0}
    # 10% now + another 15% at delivery = 25% own money; the mortgage covers the other 75%
    assert p['financing'] == {'mortgage_pct': 75.0, 'expected_mortgage': 750_000, 'mortgage_pct_of_price': 75.0,
                              'own_total_target': 250_000, 'own_total_left': 235_000, 'delivery_payment': 150_000}
    assert p['delivery']['days_left'] == 731
    assert p['derived']['value_at_delivery'] == pytest.approx(1_000_000 * 1.03 ** (731 / 365.25))
    assert p['derived']['equity_at_delivery'] == pytest.approx(1_000_000 * 1.03 ** (731 / 365.25) - 750_000)
    assert p['derived']['appreciation'] == 0                           # growth starts on the signing day


def test_financing_follows_the_chosen_mortgage_share_and_never_goes_negative():
    p = hp.build_project(settings(price=1_000_000, mortgage_pct=60.0), REAL, EVENTS, T)
    f = p['financing']
    assert f['expected_mortgage'] == 600_000 and f['own_total_target'] == 400_000 and f['delivery_payment'] == 300_000
    # a down payment bigger than the own-funds share leaves nothing extra to pay at delivery
    p = hp.build_project(settings(price=1_000_000, mortgage_pct=95.0, down_pct=10.0), REAL, EVENTS, T)
    assert p['financing']['delivery_payment'] == 0 and p['financing']['expected_mortgage'] == 950_000
    assert hp.build_project(settings(), REAL, EVENTS, T)['financing']['expected_mortgage'] is None


def test_summary_statistics():
    txs = REAL + [tx(date(2026, 8, 20), name='שכירות', income=2_000)]
    p = hp.build_project(settings(price=1_000_000), txs, EVENTS, T)
    st = p['stats']
    assert st['n_out'] == 2 and st['n_in'] == 1
    assert st['largest']['amount'] == 15_000 and st['largest']['date'] == '2026-07-08'
    assert st['last_out'] == {'date': '2026-07-08', 'amount': 15_000, 'days_ago': 93}
    assert st['first_date'] == '2026-06-10'
    assert st['avg_monthly_out'] == pytest.approx(20_000 / 5)          # June..October
    assert st['overhead_pct_of_price'] == pytest.approx(0.5)
    assert [m['month'] for m in p['monthly']] == ['2026-06', '2026-07', '2026-08', '2026-09', '2026-10']
    assert p['monthly'][1]['out'] == 15_000 and p['monthly'][2]['income'] == 2_000
    assert p['monthly'][-1]['cum_paid'] == 15_000


def test_break_even_growth_needs_enough_history():
    young = hp.build_project(settings(price=1_000_000), REAL, EVENTS, T)
    be = young['returns']['break_even']
    assert be['required_appreciation'] == 5_000 and be['required_growth_pct'] is None   # signing was today
    mid = hp.build_project(settings(price=1_000_000, contract_date=date(2026, 3, 1)), REAL, EVENTS, T)
    assert mid['returns']['break_even']['required_growth_pct'] is None                  # 7 months: too short to call a yearly rate
    old = hp.build_project(settings(price=1_000_000, contract_date=date(2025, 1, 1)), REAL, EVENTS, T)
    years = (T - date(2025, 1, 1)).days / 365.25
    assert old['returns']['break_even']['required_growth_pct'] == pytest.approx(((1_005_000 / 1_000_000) ** (1 / years) - 1) * 100, rel=1e-3)


def test_events_summary_lists_next_and_last():
    evs = [{'id': 1, 'name': 'a', 'event_date': '2026-09-01', 'description': '', 'color': '#111'},
           {'id': 2, 'name': 'b', 'event_date': '2026-10-09', 'description': '', 'color': '#111'},
           {'id': 3, 'name': 'c', 'event_date': '2026-12-01', 'description': '', 'color': '#111'}]
    p = hp.build_project(settings(), [], evs, T)
    assert p['event_stats'] == {'count': 3, 'next': evs[2], 'last': evs[1]}
    assert hp.build_project(settings(), [], [], T)['event_stats'] == {'count': 0, 'next': None, 'last': None}


# ── the asset history for the accounts page ────────────────────────────────
def test_equity_history_starts_with_the_first_price_payment_and_ends_today():
    s = settings(price=1_000_000, contract_date=date(2026, 7, 1))
    h = hp.equity_history(s, REAL, [], T)
    assert h[0] == (date(2026, 7, 8), pytest.approx(15_000 + 1_000_000 * (1.03 ** (7 / 365.25) - 1)))
    assert [d for d, _ in h][-1] == T
    assert [d for d, _ in h] == sorted(d for d, _ in h)
    assert date(2026, 7, 31) in [d for d, _ in h] and date(2026, 9, 30) in [d for d, _ in h]
    assert h[-1][1] == pytest.approx(hp.build_project(s, REAL, [], T)['derived']['equity'])


def test_equity_history_excludes_costs_and_future_dates():
    s = settings(price=None)
    h = hp.equity_history(s, REAL, [], T)
    assert all(v == 15_000 for d, v in h if d >= date(2026, 7, 8))
    assert hp.equity_history(s, [tx(date(2026, 6, 10), out=5_000, kind='cost')], [], T) == []
    assert hp.equity_history(s, [tx(date(2026, 12, 1), out=5_000)], [], T) == []      # not paid yet


def test_equity_history_applies_refunds_and_stays_empty_when_nothing_is_owned():
    s = settings(price=None)
    txs = [tx(date(2026, 7, 8), out=15_000), tx(date(2026, 8, 5), name='החזר', income=15_000, kind='refund')]
    h = hp.equity_history(s, txs, [], T)
    assert h[0][1] == 15_000 and h[-1][1] == 0


# ── adding the asset to the accounts payload ───────────────────────────────
def test_apply_overlay_adds_the_asset_and_shifts_the_total():
    payload = {'accounts': {'Main Bank': [['2026-09-01', 100.0], ['2026-10-01', 150.0]],
                            'Total': [['2026-09-01', 100.0], ['2026-10-01', 150.0]]},
               'accounts_meta': {}}
    extra = {'נכס מונה': [['2026-09-15', 20.0], ['2026-10-05', 25.0]]}
    out = hp.apply_overlay(payload, extra)
    assert out['accounts']['נכס מונה'] == [['2026-09-15', 20.0], ['2026-10-05', 25.0]]
    assert out['accounts']['Total'] == [['2026-09-01', 100.0], ['2026-09-15', 120.0],
                                        ['2026-10-01', 170.0], ['2026-10-05', 175.0]]
    assert payload['accounts']['Total'][0] == ['2026-09-01', 100.0]      # the input is not mutated
    assert 'נכס מונה' not in payload['accounts']


def test_apply_overlay_without_assets_returns_the_payload_unchanged():
    payload = {'accounts': {'Total': [['2026-09-01', 100.0]]}}
    assert hp.apply_overlay(payload, {}) is payload
    assert hp.apply_overlay(payload, {'נכס מונה': []}) is payload
    assert hp.apply_overlay({}, {'נכס מונה': [['2026-09-01', 1.0]]}) == {}   # no accounts at all: nothing to add to


def test_apply_overlay_value_before_the_first_total_point():
    payload = {'accounts': {'Total': [['2026-10-01', 100.0]]}}
    out = hp.apply_overlay(payload, {'נכס מונה': [['2026-07-08', 15_000.0]]})
    assert out['accounts']['Total'] == [['2026-07-08', 15_000.0], ['2026-10-01', 15_100.0]]
