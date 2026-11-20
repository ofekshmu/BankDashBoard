"""The "מידע חיוני" box of each apartment (שבזי / מונה): validation, saving and the endpoints,
against an in-memory fake database."""
import pytest
from flask import Flask

import housing_info_service as svc
import routes.housing_project_routes as hr


class FakeDB:
    def __init__(self):
        self.rows = {'shabazi': [('כתובת הנכס', 'שבזי שלום 7/18')], 'mona': []}
        self.fail = False

    def ensure_housing_info_table(self): pass

    def get_housing_info(self, prop):
        if self.fail:
            raise RuntimeError('db down')
        return [{'label': l, 'value': v} for l, v in self.rows[prop]]

    def replace_housing_info(self, prop, items):
        self.rows[prop] = [(i['label'], i['value']) for i in items]


# ── service ────────────────────────────────────────────────────────────────
def test_load_returns_the_saved_rows_in_order():
    assert svc.load_info(FakeDB(), 'shabazi') == [{'label': 'כתובת הנכס', 'value': 'שבזי שלום 7/18'}]


def test_unknown_apartment_is_rejected():
    with pytest.raises(svc.InfoError):
        svc.load_info(FakeDB(), 'nope')
    with pytest.raises(svc.InfoError):
        svc.save_info(FakeDB(), 'nope', [])


def test_save_trims_keeps_order_and_drops_blank_rows():
    db = FakeDB()
    out = svc.save_info(db, 'mona', [{'label': ' כתובת ', 'value': ' הרצל 5 '}, {'label': '', 'value': ''},
                                      {'label': 'חשמלאי', 'value': '050-1234567'}, {'label': '  ', 'value': ' '}])
    assert out == [{'label': 'כתובת', 'value': 'הרצל 5'}, {'label': 'חשמלאי', 'value': '050-1234567'}]
    assert db.rows['mona'] == [('כתובת', 'הרצל 5'), ('חשמלאי', '050-1234567')]


def test_a_value_may_be_empty_but_a_row_needs_a_name():
    db = FakeDB()
    assert svc.save_info(db, 'mona', [{'label': 'מונה מים', 'value': ''}]) == [{'label': 'מונה מים', 'value': ''}]
    with pytest.raises(svc.InfoError, match='שם'):
        svc.save_info(db, 'mona', [{'label': '', 'value': '123'}])


@pytest.mark.parametrize('items', [
    'x', None, {'label': 'a'}, [1], [{'label': 5, 'value': 'x'}], [{'label': 'a', 'value': None}],
    [{'label': 'a' * 61, 'value': ''}], [{'label': 'a', 'value': 'b' * 501}],
    [{'label': str(i), 'value': ''} for i in range(svc.MAX_ITEMS + 1)],
])
def test_invalid_lists_are_rejected_and_nothing_is_saved(items):
    db = FakeDB()
    with pytest.raises(svc.InfoError):
        svc.save_info(db, 'mona', items)
    assert db.rows['mona'] == []


def test_saving_an_empty_list_clears_the_box():
    db = FakeDB()
    assert svc.save_info(db, 'shabazi', []) == [] and db.rows['shabazi'] == []


# ── endpoints ──────────────────────────────────────────────────────────────
@pytest.fixture
def env(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(hr, 'get_db', lambda: db)
    app = Flask(__name__)
    app.register_blueprint(hr.housing_projects_bp)
    return app.test_client(), db


def test_get_and_put(env):
    client, db = env
    assert client.get('/api/housing/info/shabazi').get_json() == {
        'ok': True, 'items': [{'label': 'כתובת הנכס', 'value': 'שבזי שלום 7/18'}]}
    r = client.put('/api/housing/info/mona', json={'items': [{'label': 'חשמלאי', 'value': '050'}]})
    assert r.status_code == 200 and r.get_json()['items'] == [{'label': 'חשמלאי', 'value': '050'}]
    assert db.rows['mona'] == [('חשמלאי', '050')]


def test_bad_requests_are_400_and_unknown_apartments_404(env):
    client, db = env
    assert client.put('/api/housing/info/mona', json={'items': [{'label': '', 'value': 'x'}]}).status_code == 400
    assert client.put('/api/housing/info/mona', data='nope', content_type='text/plain').status_code == 400
    assert client.put('/api/housing/info/nope', json={'items': []}).status_code == 404
    assert client.get('/api/housing/info/nope').status_code == 404
    assert db.rows['mona'] == []


def test_a_database_failure_is_a_500_with_a_message(env):
    client, db = env
    db.fail = True
    r = client.get('/api/housing/info/mona')
    assert r.status_code == 500 and r.get_json()['ok'] is False
