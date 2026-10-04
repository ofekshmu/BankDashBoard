"""Landing-dashboard glue that lives in WebApp.py: the auth gate on /api/landing/*,
and the monthly / accounts loaders registered there.

Importing WebApp is cheap (~0.3s, no DB connection at import — DataBase/pg pools
are created lazily on first query; the only side effect is the daemon FX-refresh
thread), so these tests exercise the real app object and the real loader
functions, with their DB-touching collaborators monkeypatched. WebApp loads
.env itself; when no DATABASE_URL is configured at all the module-level tests
are skipped, and the static _PUBLIC_PATHS check below still runs.
"""
import ast
import os
from datetime import date

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEBAPP_PY = os.path.join(ROOT, 'source', 'WebApp.py')
TODAY = date(2026, 10, 4)


def _database_url_available():
    if os.environ.get('DATABASE_URL'):
        return True
    try:
        from dotenv import dotenv_values
    except ImportError:
        return False
    return bool(dotenv_values(os.path.join(ROOT, '.env')).get('DATABASE_URL'))


needs_webapp = pytest.mark.skipif(not _database_url_available(), reason='DATABASE_URL not configured')


@pytest.fixture(scope='module')
def webapp():
    import WebApp
    return WebApp


# ── Auth gate ──────────────────────────────────────────────────────────────
def test_no_public_path_is_a_landing_api_path_static():
    """Runs without a DB: parse the _PUBLIC_PATHS literal straight out of WebApp.py."""
    tree = ast.parse(open(WEBAPP_PY, encoding='utf-8-sig').read())
    public = next(ast.literal_eval(node.value) for node in tree.body
                  if isinstance(node, ast.Assign) and any(getattr(t, 'id', None) == '_PUBLIC_PATHS' for t in node.targets))
    assert public and not [p for p in public if p.startswith('/api/landing')]


@needs_webapp
def test_landing_api_requires_a_session(webapp):
    assert not [p for p in webapp._PUBLIC_PATHS if p.startswith('/api/landing')]
    client = webapp.app.test_client()
    for block in ('plants', 'accounts', 'monthly', 'nope'):
        r = client.get('/api/landing/' + block)
        assert r.status_code == 401 and r.get_json() == {'ok': False, 'error': 'unauthorized'}


# ── Accounts: one retry on a dropped pooled connection ─────────────────────
ACCOUNTS = {'accounts': {'Total': [['2026-10-01', 1000.0]]}}


def _accounts_env(monkeypatch, webapp, cash_map):
    monkeypatch.setattr(webapp, '_accounts_cached_payload', lambda: ACCOUNTS)
    monkeypatch.setattr(webapp, '_get_fx_rates', lambda: {})
    monkeypatch.setattr(webapp, '_cash_balance_map', cash_map)


@needs_webapp
@pytest.mark.parametrize('exc_name', ['OperationalError', 'InterfaceError'])
def test_accounts_retries_cash_map_once_on_dropped_connection(monkeypatch, webapp, exc_name):
    import psycopg2
    calls = []

    def cash_map(strict=False):
        calls.append(strict)
        if len(calls) == 1:
            raise getattr(psycopg2, exc_name)('SSL connection has been closed unexpectedly')
        return {}

    _accounts_env(monkeypatch, webapp, cash_map)
    b = webapp._landing_accounts(TODAY)
    assert calls == [True, True] and b['ok'] and b['kpi'] == '1,000₪'


@needs_webapp
def test_accounts_second_connection_failure_propagates(monkeypatch, webapp):
    import psycopg2
    calls = []

    def cash_map(strict=False):
        calls.append(strict)
        raise psycopg2.OperationalError('still down')

    _accounts_env(monkeypatch, webapp, cash_map)
    with pytest.raises(psycopg2.OperationalError):
        webapp._landing_accounts(TODAY)
    assert calls == [True, True]


@needs_webapp
def test_accounts_other_errors_are_not_retried(monkeypatch, webapp):
    calls = []

    def cash_map(strict=False):
        calls.append(strict)
        raise ValueError('bad data')

    _accounts_env(monkeypatch, webapp, cash_map)
    with pytest.raises(ValueError):
        webapp._landing_accounts(TODAY)
    assert calls == [True]


# ── Accounts page: the cash total ships with the data (no 723k → 727k jump) ──
def _accounts_api_json(webapp, path='/api/accounts/data'):
    with webapp.app.test_request_context(path):
        resp, status = webapp.accounts_data_api()[:2]
        return resp.get_json(), status


@needs_webapp
def test_accounts_data_carries_the_cash_ils_total(monkeypatch, webapp):
    monkeypatch.setattr(webapp, '_accounts_cached_payload', lambda: ACCOUNTS)
    monkeypatch.setattr(webapp, '_compute_accounts', lambda: ACCOUNTS)
    monkeypatch.setattr(webapp, '_get_fx_rates', lambda: {'JPY': 0.02})
    monkeypatch.setattr(webapp, '_cash_balance_map', lambda strict=False: {'ILS': 100, 'JPY': 1000})
    d, status = _accounts_api_json(webapp)
    assert status == 200 and d['cash_ils_total'] == 120 and d['accounts'] == ACCOUNTS['accounts']
    d, status = _accounts_api_json(webapp, '/api/accounts/data?fresh=1')
    assert status == 200 and d['cash_ils_total'] == 120


@needs_webapp
def test_accounts_data_cash_total_is_null_when_unknown(monkeypatch, webapp):
    monkeypatch.setattr(webapp, '_accounts_cached_payload', lambda: ACCOUNTS)
    monkeypatch.setattr(webapp, '_get_fx_rates', lambda: {})                     # rates not loaded yet
    monkeypatch.setattr(webapp, '_cash_balance_map', lambda strict=False: {'JPY': 1000})
    assert _accounts_api_json(webapp)[0]['cash_ils_total'] is None

    def down(strict=False):
        raise RuntimeError('db down')
    monkeypatch.setattr(webapp, '_cash_balance_map', down)
    d, status = _accounts_api_json(webapp)
    assert status == 200 and d['cash_ils_total'] is None                        # the page still loads


# ── Monthly: a non-200 analysis is a failure, not "no analysis" ─────────────
class _Resp:
    def __init__(self, data, status):
        self._data, self.status_code = data, status

    def get_json(self):
        return self._data


MONTHS = [{'key': '2026_09'}, {'key': '2026_10'}]


@needs_webapp
def test_monthly_non_200_raises_instead_of_grey_no_analysis(monkeypatch, webapp):
    monkeypatch.setattr(webapp, '_landing_month_keys', lambda: MONTHS)
    monkeypatch.setattr(webapp, 'monthly_data_api', lambda key: (_Resp({'error': 'boom'}, 500), 500))
    with pytest.raises(RuntimeError, match='boom'):
        webapp._landing_monthly(TODAY)
    monkeypatch.setattr(webapp, 'monthly_data_api', lambda key: _Resp(None, 404))
    with pytest.raises(RuntimeError):
        webapp._landing_monthly(TODAY)


@needs_webapp
def test_monthly_ok_and_no_months(monkeypatch, webapp):
    seen = []
    monkeypatch.setattr(webapp, '_landing_month_keys', lambda: MONTHS)
    monkeypatch.setattr(webapp, 'monthly_data_api',
                        lambda key: seen.append(key) or _Resp({'alerts': [1], 'organizer_alerts': []}, 200))
    b = webapp._landing_monthly(TODAY)
    assert seen == ['2026_10'] and b['kpi'] == '1' and b['dot'] == 'amber'
    monkeypatch.setattr(webapp, '_landing_month_keys', lambda: [])
    b = webapp._landing_monthly(TODAY)
    assert b['dot'] == 'grey' and b['caption'] == 'אין ניתוחים חודשיים'


@needs_webapp
def test_landing_page_and_version_are_never_browser_cached(webapp, monkeypatch):
    c = webapp.app.test_client()
    r = c.get('/api/version')
    assert r.status_code == 200 and r.headers['Cache-Control'] == 'no-store'
    assert r.get_json()['version'] == open(os.path.join(ROOT, 'VERSION')).read().strip()
    r = c.get('/')
    assert r.status_code == 200 and r.headers['Cache-Control'] == 'no-store'
