"""The housing project endpoints, on a bare Flask app with an in-memory fake database."""
from datetime import date

import pytest
from flask import Flask

import routes.housing_project_routes as hr
from tests.test_housing_project_service import FakeDB

T = date(2026, 10, 9)


@pytest.fixture
def env(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(hr, 'get_db', lambda: db)
    monkeypatch.setattr(hr, '_today', lambda: T)
    app = Flask(__name__)
    app.register_blueprint(hr.housing_projects_bp)
    return app.test_client(), db


def test_get_returns_the_project(env):
    client, _ = env
    r = client.get('/api/housing/projects/mona')
    d = r.get_json()
    assert r.status_code == 200 and d['ok'] and d['project']['account_name'] == 'נכס מונה'
    assert d['project']['money']['paid_price'] == 15000


def test_unknown_project_is_404(env):
    client, _ = env
    r = client.get('/api/housing/projects/nope')
    assert r.status_code == 404 and r.get_json()['ok'] is False


def test_post_saves_settings_and_returns_the_project(env):
    client, db = env
    r = client.post('/api/housing/projects/mona', json={'price': 1_450_000, 'growth_pct': 6.5})
    assert r.status_code == 200 and r.get_json()['project']['settings']['growth_pct'] == 6.5
    assert db.project['price'] == 1_450_000


def test_invalid_settings_are_400_with_a_message_and_nothing_is_saved(env):
    client, db = env
    r = client.post('/api/housing/projects/mona', json={'price': 900_000, 'growth_pct': 20})
    assert r.status_code == 400 and 'שיעור עליית הערך' in r.get_json()['error']
    assert db.project['price'] is None and db.project['growth_pct'] == 3.0
    assert client.post('/api/housing/projects/mona', data='not json', content_type='text/plain').status_code == 400


def test_tx_kind_endpoint(env):
    client, db = env
    r = client.post('/api/housing/projects/mona/tx-kind', json={'key': 'CardTransactions:2340', 'kind': 'price'})
    assert r.status_code == 200 and r.get_json()['project']['money']['paid_price'] == 20000
    assert db.kinds == {'CardTransactions:2340': 'price'}
    r = client.post('/api/housing/projects/mona/tx-kind', json={'key': 'CardTransactions:2340', 'kind': None})
    assert r.status_code == 200 and db.kinds == {}
    assert client.post('/api/housing/projects/mona/tx-kind', json={'key': 'x:1', 'kind': 'price'}).status_code == 400
    assert client.post('/api/housing/projects/mona/tx-kind', json={'kind': 'price'}).status_code == 400
    assert client.post('/api/housing/projects/mona/tx-kind', json={'key': 'a', 'kind': 5}).status_code == 400


def test_unexpected_errors_are_500_without_leaking_details(env):
    client, db = env
    db.fail = True
    r = client.get('/api/housing/projects/mona')
    assert r.status_code == 500 and 'db down' not in r.get_data(as_text=True)
