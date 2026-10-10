"""Housing project service: loading a project, validating edits, per-payment kinds and the
accounts overlay — against an in-memory fake database."""
from datetime import date

import pytest

import housing_project_service as svc

T = date(2026, 10, 9)


class FakeDB:
    def __init__(self, **settings):
        self.project = {'key': 'mona', 'name': 'מונה', 'tx_category': 'דירת קבלן', 'timeline_category': None,
                        'price': None, 'down_pct': 10.0, 'mortgage_pct': 75.0, 'contract_date': None,
                        'delivery_date': None, 'growth_pct': 3.0}
        self.project.update(settings)
        self.kinds = {}
        self.txs = [
            {'table': 'BankTransactions', 'id': 737, 'key': 'BankTransactions:737', 'date': date(2026, 7, 8),
             'name': 'העברה מהחשבון', 'description': '', 'out': 15000.0, 'income': 0.0},
            {'table': 'CardTransactions', 'id': 2340, 'key': 'CardTransactions:2340', 'date': date(2026, 6, 10),
             'name': 'קבוצת בר סרוסי השקעו', 'description': 'פעימה ראשונה - ליווי', 'out': 5000.0, 'income': 0.0},
        ]
        self.categories = [{'key': 'mortgage', 'label': 'שבזי'}, {'key': 'cat_mona', 'label': 'MONA'}]
        self.events = [{'id': 79, 'name': 'חתימה על בקשת רכישה', 'event_date': '2026-10-09',
                        'description': '', 'color': '#ec4899', 'category': 'cat_mona', 'transactions': []}]
        self.fail = False

    def ensure_housing_project_tables(self): pass
    def ensure_timeline_tables(self): pass

    def get_housing_project(self, key):
        if self.fail:
            raise RuntimeError('db down')
        return dict(self.project) if key == 'mona' else None

    def list_housing_projects(self):
        if self.fail:
            raise RuntimeError('db down')
        return [dict(self.project)]

    def update_housing_project(self, key, **fields): self.project.update(fields)
    def get_housing_tx_kinds(self, key): return dict(self.kinds)

    def set_housing_tx_kind(self, key, tx_key, kind):
        if kind is None:
            self.kinds.pop(tx_key, None)
        else:
            self.kinds[tx_key] = kind

    def get_project_transactions(self, category): return [dict(t) for t in self.txs] if category == 'דירת קבלן' else []
    def get_timeline_categories(self, include_deleted=False): return list(self.categories)
    def timeline_category_exists(self, key, active_only=True): return any(c['key'] == key for c in self.categories)
    def get_timeline_events(self, category=None): return [e for e in self.events if category in (None, e['category'])]


# ── loading ────────────────────────────────────────────────────────────────
def test_payload_for_mona_reads_the_existing_tag_and_finds_the_timeline_by_label():
    db = FakeDB()
    p = svc.project_payload(db, 'mona', T)
    assert p['tx_category'] == 'דירת קבלן' and p['account_name'] == 'נכס מונה'
    assert p['timeline_category'] == 'cat_mona' and db.project['timeline_category'] == 'cat_mona'   # remembered
    assert [e['name'] for e in p['events']] == ['חתימה על בקשת רכישה']
    kinds = {t['key']: (t['auto_kind'], t['kind']) for t in p['transactions']}
    assert kinds == {'BankTransactions:737': ('price', 'price'), 'CardTransactions:2340': ('cost', 'cost')}
    assert p['money']['paid_price'] == 15000 and p['money']['extra_costs'] == 5000
    assert p['growth_start'] == '2026-10-09' and p['growth_start_source'] == 'timeline'


def test_payload_without_a_matching_timeline_category_has_no_events():
    db = FakeDB()
    db.categories = [{'key': 'mortgage', 'label': 'שבזי'}]
    p = svc.project_payload(db, 'mona', T)
    assert p['timeline_category'] is None and p['events'] == []


def test_unknown_project():
    with pytest.raises(svc.UnknownProject):
        svc.project_payload(FakeDB(), 'nope', T)


def test_user_kind_overrides_the_automatic_one():
    db = FakeDB()
    db.kinds = {'CardTransactions:2340': 'price', 'BankTransactions:737': 'refund'}   # refund doesn't fit an outgoing row
    p = svc.project_payload(db, 'mona', T)
    kinds = {t['key']: (t['auto_kind'], t['kind']) for t in p['transactions']}
    assert kinds == {'BankTransactions:737': ('price', 'price'), 'CardTransactions:2340': ('cost', 'price')}
    assert p['money']['paid_price'] == 20000 and p['money']['extra_costs'] == 0


# ── editing the settings ───────────────────────────────────────────────────
def test_update_saves_valid_settings_and_returns_the_new_payload():
    db = FakeDB()
    p = svc.update_project(db, 'mona', {'price': '1450000', 'down_pct': 10, 'growth_pct': 4.5,
                                        'contract_date': '2026-10-01', 'delivery_date': '2029-03-01',
                                        'tx_category': ' דירת קבלן '}, T)
    assert db.project['price'] == 1_450_000 and db.project['growth_pct'] == 4.5
    assert db.project['contract_date'] == date(2026, 10, 1) and db.project['delivery_date'] == date(2029, 3, 1)
    assert db.project['tx_category'] == 'דירת קבלן'
    assert p['settings']['price'] == 1_450_000 and p['growth_start'] == '2026-10-01'


def test_growth_rate_is_limited_to_zero_through_fifteen():
    db = FakeDB()
    assert svc.update_project(db, 'mona', {'growth_pct': 15}, T)['settings']['growth_pct'] == 15
    assert svc.update_project(db, 'mona', {'growth_pct': 0}, T)['settings']['growth_pct'] == 0
    for bad in (15.1, -0.5, 'abc', None, float('nan'), True):
        with pytest.raises(svc.ProjectError):
            svc.update_project(db, 'mona', {'growth_pct': bad}, T)
    assert db.project['growth_pct'] == 0


def test_price_can_be_cleared_but_not_negative_or_zero():
    db = FakeDB(price=1_000_000.0)
    assert svc.update_project(db, 'mona', {'price': None}, T)['has_price'] is False
    assert svc.update_project(db, 'mona', {'price': ''}, T)['has_price'] is False
    for bad in (-5, 0, 'x', 1e12):
        with pytest.raises(svc.ProjectError):
            svc.update_project(db, 'mona', {'price': bad}, T)


def test_other_field_validation():
    db = FakeDB()
    for body in ({'down_pct': 101}, {'down_pct': -1}, {'contract_date': 'yesterday'}, {'tx_category': '  '},
                 {'tx_category': 'x' * 81}, {'delivery_date': '2025-01-01', 'contract_date': '2026-01-01'}, {}):
        with pytest.raises(svc.ProjectError):
            svc.update_project(db, 'mona', body, T)
    assert svc.update_project(db, 'mona', {'contract_date': '', 'delivery_date': None}, T)['settings']['contract_date'] is None


def test_mortgage_share_drives_the_financing_and_is_checked_against_the_down_payment():
    db = FakeDB()
    p = svc.update_project(db, 'mona', {'price': 1_000_000, 'mortgage_pct': 70}, T)
    assert db.project['mortgage_pct'] == 70 and p['settings']['mortgage_pct'] == 70
    assert p['financing']['expected_mortgage'] == 700_000 and p['financing']['own_total_target'] == 300_000
    for bad in (-1, 101, 'x', None, True):
        with pytest.raises(svc.ProjectError):
            svc.update_project(db, 'mona', {'mortgage_pct': bad}, T)
    with pytest.raises(svc.ProjectError, match='המקדמה'):
        svc.update_project(db, 'mona', {'down_pct': 40}, T)               # own funds are only 30%
    with pytest.raises(svc.ProjectError, match='המקדמה'):
        svc.update_project(db, 'mona', {'mortgage_pct': 95}, T)           # 10% down but only 5% own funds
    assert db.project['mortgage_pct'] == 70 and db.project['down_pct'] == 10
    assert svc.update_project(db, 'mona', {'down_pct': 30, 'mortgage_pct': 70}, T)['settings']['down_pct'] == 30


def test_default_plan_is_ten_percent_now_fifteen_at_delivery_and_a_seventy_five_percent_mortgage():
    p = svc.update_project(FakeDB(), 'mona', {'price': 2_000_000}, T)
    f = p['financing']
    assert f['expected_mortgage'] == 1_500_000 and f['own_total_target'] == 500_000
    assert p['down']['target'] == 200_000 and f['delivery_payment'] == 300_000


def test_delivery_is_checked_against_the_saved_contract_date_too():
    db = FakeDB(contract_date=date(2026, 6, 1))
    with pytest.raises(svc.ProjectError):
        svc.update_project(db, 'mona', {'delivery_date': '2026-01-01'}, T)


# ── per-payment kinds ──────────────────────────────────────────────────────
def test_set_tx_kind_saves_clears_and_validates():
    db = FakeDB()
    p = svc.set_tx_kind(db, 'mona', 'CardTransactions:2340', 'price', T)
    assert db.kinds == {'CardTransactions:2340': 'price'} and p['money']['paid_price'] == 20000
    p = svc.set_tx_kind(db, 'mona', 'CardTransactions:2340', None, T)
    assert db.kinds == {} and p['money']['paid_price'] == 15000
    with pytest.raises(svc.ProjectError):
        svc.set_tx_kind(db, 'mona', 'BankTransactions:737', 'refund', T)      # outgoing row
    with pytest.raises(svc.ProjectError):
        svc.set_tx_kind(db, 'mona', 'BankTransactions:999', 'price', T)       # not one of the project's payments
    with pytest.raises(svc.ProjectError):
        svc.set_tx_kind(db, 'mona', 'BankTransactions:737', 'bogus', T)
    assert db.kinds == {}


# ── the asset on the accounts page ─────────────────────────────────────────
def test_account_assets_use_price_payments_only():
    db = FakeDB(price=1_000_000.0, contract_date=date(2026, 7, 1))
    assets = svc.account_assets(db, T)
    series = assets['נכס מונה']
    assert series[0][0] == '2026-07-08' and series[-1][0] == '2026-10-09'
    assert series[-1][1] == pytest.approx(15000 + 1_000_000 * (1.03 ** (100 / 365.25) - 1), abs=0.01)


def test_account_assets_are_empty_before_any_price_payment():
    db = FakeDB()
    db.txs = db.txs[1:]                                    # only the "ליווי" fee
    assert svc.account_assets(db, T) == {}


def test_overlay_adds_the_asset_to_the_accounts_payload():
    db = FakeDB()
    payload = {'accounts': {'Main Bank': [['2026-09-01', 100.0]], 'Total': [['2026-09-01', 100.0]]}}
    out = svc.overlay_accounts(payload, db, T)
    assert out['accounts']['נכס מונה'][-1] == ['2026-10-09', 15000.0]
    assert out['accounts']['Total'][-1] == ['2026-10-09', 15100.0]
    assert 'נכס מונה' not in payload['accounts']


def test_overlay_never_breaks_the_accounts_page():
    db = FakeDB()
    db.fail = True
    payload = {'accounts': {'Total': [['2026-09-01', 100.0]]}}
    assert svc.overlay_accounts(payload, db, T) is payload
