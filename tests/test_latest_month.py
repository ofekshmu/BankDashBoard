"""_get_latest_yyyy_mm — the month /accounts, /housing, /timeline and /monthly open.

The database is the source of truth: leftover generated pages in Outputs/general_analysis
(the newest was 2026_06 while the bank data reached October) must not win over it.
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


class FakeConn:
    def __init__(self, max_date):
        self.max_date = max_date

    def execute(self, sql, *a):
        assert 'BankTransactions' in sql
        return self

    def fetchone(self):
        if isinstance(self.max_date, Exception):
            raise self.max_date
        return (self.max_date,)

    def close(self):
        pass


@pytest.fixture
def webapp(monkeypatch, tmp_path):
    import WebApp
    (tmp_path / '2026_06.html').write_text('old page')          # leftover generated page
    monkeypatch.setattr(WebApp, 'GENERAL_ANALYSIS_DIR', str(tmp_path))
    monkeypatch.setattr(WebApp, '_monthly_data_cache', {})
    return WebApp


def test_the_database_month_wins_over_leftover_files(webapp, monkeypatch):
    monkeypatch.setattr(webapp, '_pg_conn', lambda: FakeConn('2026-10-04'))
    assert webapp._get_latest_yyyy_mm() == '2026_10'


def test_files_and_cache_are_only_a_fallback_when_the_database_fails(webapp, monkeypatch):
    monkeypatch.setattr(webapp, '_pg_conn', lambda: FakeConn(RuntimeError('db down')))
    assert webapp._get_latest_yyyy_mm() == '2026_06'
    monkeypatch.setattr(webapp, '_monthly_data_cache', {'2026_09': {}, '2026_08': {}})
    assert webapp._get_latest_yyyy_mm() == '2026_09'                # the newer of cache and files


def test_accounts_redirects_to_the_latest_bank_month(webapp, monkeypatch):
    monkeypatch.setattr(webapp, '_pg_conn', lambda: FakeConn('2026-10-04'))
    c = webapp.app.test_client()
    with c.session_transaction() as s:
        s['authenticated'] = True
    r = c.get('/accounts')
    assert r.status_code == 302 and r.headers['Location'].endswith('/general/2026_10?panel=accounts')
