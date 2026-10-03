from datetime import date

import pytest
from flask import Flask

from routes import landing_routes as lr


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(lr, 'LOADERS', {})
    monkeypatch.setattr(lr, '_server_today', lambda: date(2026, 10, 4))
    lr.clear_cache()
    app = Flask(__name__)
    app.register_blueprint(lr.landing_bp)
    return app.test_client()


def test_blocks_are_the_eleven_live_blocks():
    assert lr.BLOCKS == ('monthly', 'accounts', 'cards', 'housing', 'timeline', 'bills',
                         'spotify', 'plants', 'recurring', 'tagger', 'files')


def test_ok_block_passes_today_and_returns_json(client):
    seen = []
    lr.register_loader('plants', lambda today: seen.append(today) or {'ok': True, 'kpi': '2'})
    r = client.get('/api/landing/plants')
    assert r.status_code == 200 and r.get_json()['kpi'] == '2' and seen == [date(2026, 10, 4)]


def test_unknown_block_404(client):
    assert client.get('/api/landing/nope').status_code == 404


def test_block_without_loader_is_an_isolated_failure(client):
    r = client.get('/api/landing/files')
    assert r.status_code == 500 and r.get_json() == {'ok': False, 'error': 'לא זמין כרגע'}


def test_failing_block_does_not_affect_another(client):
    lr.register_loader('cards', lambda today: 1 / 0)
    lr.register_loader('bills', lambda today: {'ok': True, 'kpi': '5'})
    assert client.get('/api/landing/cards').status_code == 500
    assert client.get('/api/landing/bills').get_json()['kpi'] == '5'


def test_cache_for_ttl_and_failures_not_cached(client, monkeypatch):
    calls = []
    lr.register_loader('timeline', lambda today: calls.append(1) or {'ok': True, 'kpi': str(len(calls))})
    now = [1000.0]
    monkeypatch.setattr(lr, '_now', lambda: now[0])
    assert client.get('/api/landing/timeline').get_json()['kpi'] == '1'
    now[0] += lr.CACHE_TTL - 1
    assert client.get('/api/landing/timeline').get_json()['kpi'] == '1'
    now[0] += 2
    assert client.get('/api/landing/timeline').get_json()['kpi'] == '2'

    boom = {'fail': True}
    def flaky(today):
        if boom['fail']:
            raise RuntimeError('db down')
        return {'ok': True, 'kpi': 'x'}
    lr.register_loader('tagger', flaky)
    assert client.get('/api/landing/tagger').status_code == 500
    boom['fail'] = False
    assert client.get('/api/landing/tagger').get_json()['kpi'] == 'x'


def test_responses_are_not_browser_cached(client):
    lr.register_loader('plants', lambda today: {'ok': True})
    assert client.get('/api/landing/plants').headers['Cache-Control'] == 'no-store'
