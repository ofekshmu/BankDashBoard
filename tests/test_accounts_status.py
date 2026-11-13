"""Adding a balance to an account (POST /api/accounts/status): a balance of 0 is accepted, and an owner
turns a same-named entry into a separate account. Runs the real route against an in-memory SQLite table
(a stand-in for the connection `_acct_db()` hands out); the real database is never touched.
"""
import os
import sqlite3

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


class Conn:
    """The wrapper's execute/commit/close over one shared in-memory SQLite database."""

    def __init__(self, raw):
        self.raw = raw

    def execute(self, sql, params=()):
        return self.raw.execute(sql, params)

    def commit(self):
        self.raw.commit()

    def close(self):
        pass


class FakeDB:
    settings = {}

    def ensure_account_settings_table(self):
        pass

    def update_account_settings(self, name, **fields):
        FakeDB.settings.setdefault(name, {}).update(fields)


@pytest.fixture
def env(monkeypatch):
    import WebApp
    import database
    raw = sqlite3.connect(':memory:', check_same_thread=False)
    raw.execute("CREATE TABLE OtherAccountStatus (ID INTEGER PRIMARY KEY, AccountName TEXT, StatusDate TEXT, "
                "Value REAL, TransactionID TEXT, Currency TEXT)")
    raw.execute("INSERT INTO OtherAccountStatus (AccountName, StatusDate, Value, Currency) "
                "VALUES ('Savings', '2026-09-01', 500, 'ILS')")
    reactivated = []
    FakeDB.settings = {}
    monkeypatch.setattr(WebApp, '_acct_db', lambda: Conn(raw))
    monkeypatch.setattr(WebApp, '_compute_accounts', lambda *a, **k: {})
    monkeypatch.setattr(WebApp, '_reactivate_if_inactive', reactivated.append)
    monkeypatch.setattr(database, 'DataBase', FakeDB)
    client = WebApp.app.test_client()
    with client.session_transaction() as s:
        s['authenticated'] = True
    return client, raw, reactivated


def post(client, **body):
    r = client.post('/api/accounts/status', json=dict({'date': '2026-10-26', 'value': 10, 'currency': 'ILS'}, **body))
    return r.get_json()


def rows(raw, name):
    return raw.execute("SELECT StatusDate, Value FROM OtherAccountStatus WHERE AccountName = ? ORDER BY ID", (name,)).fetchall()


def test_zero_is_saved_and_does_not_reactivate(env):
    client, raw, reactivated = env
    d = post(client, name='Savings', value=0)
    assert d['ok'] and d['account'] == 'Savings' and d['created'] is False
    assert rows(raw, 'Savings') == [('2026-09-01', 500.0), ('2026-10-26', 0.0)]
    assert reactivated == []                                   # money in reactivates, a zero balance does not
    assert post(client, name='Savings', value=3)['ok'] and reactivated == ['Savings']


def test_without_an_owner_the_same_name_is_the_same_account(env):
    client, raw, _ = env
    d = post(client, name='Savings', value=40)
    assert d['account'] == 'Savings' and d['created'] is False
    assert len(rows(raw, 'Savings')) == 2


def test_an_owner_makes_a_separate_account_of_the_same_name(env):
    client, raw, _ = env
    d = post(client, name='Savings', owner='  דנה ', value=40)
    assert d['ok'] and d['account'] == 'Savings (דנה)' and d['created'] is True
    assert rows(raw, 'Savings') == [('2026-09-01', 500.0)]                      # the existing account is untouched
    assert rows(raw, 'Savings (דנה)') == [('2026-10-26', 40.0)]
    assert FakeDB.settings == {'Savings (דנה)': {'owner': 'דנה'}}


def test_the_same_name_and_owner_again_adds_to_that_account(env):
    client, raw, _ = env
    post(client, name='Savings', owner='דנה', value=40)
    d = post(client, name='Savings', owner='דנה', value=45)
    assert d['account'] == 'Savings (דנה)' and d['created'] is False
    assert len(rows(raw, 'Savings (דנה)')) == 2


def test_invalid_requests(env):
    client, raw, _ = env
    assert post(client, name='', value=1)['ok'] is False
    assert post(client, name='Total', value=1)['ok'] is False
    assert post(client, name='X', owner='o' * 61, value=1)['ok'] is False
    assert post(client, name='X', owner=5, value=1)['ok'] is False
    assert raw.execute("SELECT COUNT(*) FROM OtherAccountStatus").fetchone()[0] == 1


def test_account_key_helper():
    import WebApp
    assert WebApp.account_key(' חיסכון ', ' דנה ') == 'חיסכון (דנה)'
    assert WebApp.account_key('חיסכון', '') == 'חיסכון' == WebApp.account_key('חיסכון')
