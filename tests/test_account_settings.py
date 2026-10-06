"""Accounts page: per-account settings — inactive flag (only at balance 0), owner and info.

Runs the real WebApp routes with the DataBase class and the accounts payload replaced, so no
real database is touched. Skipped when no DATABASE_URL is configured (WebApp import needs it).
"""
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _database_url_available():
    if os.environ.get('DATABASE_URL'):
        return True
    try:
        from dotenv import dotenv_values
    except ImportError:
        return False
    return bool(dotenv_values(os.path.join(ROOT, '.env')).get('DATABASE_URL'))


pytestmark = pytest.mark.skipif(not _database_url_available(), reason='DATABASE_URL not configured')

ACCOUNTS = {'accounts': {
    'Old Savings': [['2026-01-01', 500.0], ['2026-09-01', 0.0]],      # closed: last balance 0
    'Main Bank': [['2026-10-01', 20000.0]],
    'BTB': [['2026-09-11', 131222.0]],
    'Total': [['2026-10-01', 20000.0]],
}, 'accounts_meta': {}}


class FakeSettingsDB:
    rows = {}

    def ensure_account_settings_table(self):
        pass

    def get_account_settings(self):
        return {k: dict(v) for k, v in FakeSettingsDB.rows.items()}

    def update_account_settings(self, name, **fields):
        row = FakeSettingsDB.rows.setdefault(name, {'inactive': False, 'owner': '', 'info': ''})
        row.update(fields)


@pytest.fixture
def client(monkeypatch):
    import WebApp
    import database
    FakeSettingsDB.rows = {}
    monkeypatch.setattr(database, 'DataBase', FakeSettingsDB)
    monkeypatch.setattr(WebApp, '_accounts_cached_payload', lambda: ACCOUNTS)
    monkeypatch.setattr(WebApp, '_compute_accounts', lambda *a, **k: ACCOUNTS)
    monkeypatch.setattr(WebApp, '_accounts_cash_ils_total', lambda: None)
    c = WebApp.app.test_client()
    with c.session_transaction() as s:
        s['authenticated'] = True
    return c


def post(client, **body):
    r = client.post('/api/accounts/settings', json=body)
    return r.status_code, r.get_json()


def test_owner_and_info_are_saved_and_served_with_the_accounts_data(client):
    status, d = post(client, name='BTB', owner='  אופק ', info='חשבון עו"ש\nסניף 902')
    assert status == 200 and d['ok'] and d['settings'] == {'inactive': False, 'owner': 'אופק', 'info': 'חשבון עו"ש\nסניף 902'}
    data = client.get('/api/accounts/data').get_json()
    assert data['account_settings']['BTB']['owner'] == 'אופק'


def test_an_account_can_go_inactive_only_at_zero_balance(client):
    status, d = post(client, name='BTB', inactive=True)
    assert status == 400 and not d['ok'] and FakeSettingsDB.rows == {}
    status, d = post(client, name='Old Savings', inactive=True)
    assert status == 200 and d['settings']['inactive'] is True
    status, d = post(client, name='Old Savings', inactive=False)        # reactivating is always allowed
    assert status == 200 and d['settings']['inactive'] is False


def test_unknown_account_and_bad_fields_are_rejected(client):
    assert post(client, name='Nope', owner='x')[0] == 400
    assert post(client, name='', owner='x')[0] == 400
    assert post(client, name='BTB', owner='x' * 61)[0] == 400
    assert post(client, name='BTB', info=5)[0] == 400
    assert post(client, name='BTB')[0] == 400                           # nothing to change
    assert FakeSettingsDB.rows == {}


def test_cash_and_main_bank_take_no_settings(client):
    assert post(client, name='Main Bank', owner='אופק')[0] == 400
    assert post(client, name='Cash', info='ארנק')[0] == 400
    assert FakeSettingsDB.rows == {}


def test_a_new_non_zero_balance_reactivates_an_inactive_account(client, monkeypatch):
    import WebApp

    class Conn:
        def execute(self, *a):
            return self

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(WebApp, '_acct_db', lambda: Conn())
    FakeSettingsDB.rows = {'Old Savings': {'inactive': True, 'owner': 'אופק', 'info': ''}}
    r = client.post('/api/accounts/status', json={'name': 'Old Savings', 'date': '2026-10-06', 'value': 0})
    assert r.get_json()['ok'] and FakeSettingsDB.rows['Old Savings']['inactive'] is True    # still 0
    r = client.post('/api/accounts/status', json={'name': 'Old Savings', 'date': '2026-10-06', 'value': 1200})
    assert r.get_json()['ok'] and FakeSettingsDB.rows['Old Savings'] == {'inactive': False, 'owner': 'אופק', 'info': ''}


def test_accounts_data_still_loads_when_settings_cannot_be_read(client, monkeypatch):
    def boom(self):
        raise RuntimeError('db down')
    monkeypatch.setattr(FakeSettingsDB, 'get_account_settings', boom)
    r = client.get('/api/accounts/data')
    assert r.status_code == 200 and r.get_json()['account_settings'] == {}
