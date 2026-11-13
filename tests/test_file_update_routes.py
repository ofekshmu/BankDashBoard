"""The file-update endpoints on a bare Flask app (fake database, fake Excel reader, temp folders)."""
import os
import threading
from datetime import datetime

import pytest
from flask import Flask

import file_update_service as svc
import routes.file_update_routes as fr
from tests.test_file_update_service import FMT, FakeDB, put, reader_for


@pytest.fixture
def env(monkeypatch, tmp_path):
    folders = svc.Folders(str(tmp_path / 'in'), str(tmp_path / 'ver'), str(tmp_path / 'trash'))
    os.makedirs(folders.input)
    os.makedirs(os.path.join(folders.verified, FMT))
    db = FakeDB(tagged=('a',))
    finished = []
    lock = threading.Lock()
    fr.init(folders, lock, lambda: finished.append(1))
    monkeypatch.setattr(fr, 'get_db', lambda: db)
    monkeypatch.setattr(fr, 'get_reader', lambda: reader_for('a', 'b', 'c', 'd'))
    monkeypatch.setattr(fr, 'get_header_reader', lambda: None)       # no Excel in tests
    monkeypatch.setattr(fr, '_format_of', lambda name: FMT if name.endswith('.xlsx') else None)
    app = Flask(__name__)
    app.register_blueprint(fr.file_update_bp)
    put(folders.input, '4603_10_2026.xlsx', b'new')
    put(folders.verified, '4603_10_2026.xlsx', b'old', FMT)
    return app.test_client(), db, folders, finished, lock


def test_analyze_returns_the_report(env):
    client, *_ = env
    r = client.post('/api/files/analyze', json={'filename': '4603_10_2026.xlsx'})
    d = r.get_json()
    assert r.status_code == 200 and d['ok']
    assert d['report']['status'] == 'new_transactions' and d['report']['counts']['added'] == 1


def test_apply_update_changes_things_and_finishes(env):
    client, db, folders, finished, _ = env
    r = client.post('/api/files/apply-update', json={'filename': '4603_10_2026.xlsx', 'mode': 'update'})
    d = r.get_json()
    assert r.status_code == 200 and d['ok'] and d['counts']['added'] == 1
    assert db.plan['kind'] == 'update' and finished == [1]
    assert os.listdir(folders.input) == []


def test_apply_replace(env):
    client, db, *_ = env
    r = client.post('/api/files/apply-update', json={'filename': '4603_10_2026.xlsx', 'mode': 'replace'})
    assert r.status_code == 200 and db.plan['kind'] == 'replace' and db.plan['keep'] == []


def test_bad_requests(env):
    client, db, *_ = env
    assert client.post('/api/files/analyze', json={}).status_code == 400
    assert client.post('/api/files/analyze', json={'filename': '../x.xlsx'}).status_code == 400
    assert client.post('/api/files/apply-update', json={'filename': 'a.xlsx', 'mode': 'drop'}).status_code == 400
    assert client.post('/api/files/apply-update', data='nope', content_type='text/plain').status_code == 400
    r = client.post('/api/files/analyze', json={'filename': 'a.txt'})
    assert r.status_code == 400 and 'לא מזוהה' in r.get_json()['error']
    assert db.plan is None


def test_nothing_to_compare_is_404(env, monkeypatch):
    client, *_ = env
    monkeypatch.setattr(fr, 'get_reader', lambda: reader_for('a', month=datetime(2026, 11, 1)))
    r = client.post('/api/files/analyze', json={'filename': '4603_11_2026.xlsx'})
    assert r.status_code == 404 and r.get_json()['nothing_to_compare'] is True


def test_busy_while_an_insert_runs(env):
    client, _, _, _, lock = env
    with lock:
        r = client.post('/api/files/analyze', json={'filename': '4603_10_2026.xlsx'})
    assert r.status_code == 409 and 'כבר מתבצע' in r.get_json()['error']


def test_a_failing_finish_step_does_not_hide_the_update(env, monkeypatch):
    client, db, folders, _, lock = env
    fr.init(folders, lock, lambda: 1 / 0)
    r = client.post('/api/files/apply-update', json={'filename': '4603_10_2026.xlsx', 'mode': 'update'})
    d = r.get_json()
    assert r.status_code == 200 and d['ok'] and any('תיוג' in w for w in d['warnings'])
    assert db.plan is not None


def test_unexpected_errors_are_500_and_release_the_lock(env, monkeypatch):
    client, _, _, _, lock = env

    def boom(*a, **k):
        raise RuntimeError('excel crashed')
    monkeypatch.setattr(fr, 'get_reader', lambda: boom)
    r = client.post('/api/files/analyze', json={'filename': '4603_10_2026.xlsx'})
    assert r.status_code == 500 and r.get_json()['ok'] is False
    assert not lock.locked()


def test_format_of_identifies_a_file_the_parser_skipped(monkeypatch):
    import sys
    import types

    class FakeParser:
        name_to_type = {'known.xlsx': 'Isra-Card-2026'}

        @classmethod
        def getInstance(cls, newInstance=False):
            return cls()

        def _Parser__identify(self, name):
            return ('Isra-Card-2026', {}) if name.startswith('x') else (None, None)

    monkeypatch.setitem(sys.modules, 'Parser', types.SimpleNamespace(Parser=FakeParser))
    assert fr._format_of('known.xlsx') == 'Isra-Card-2026'
    assert fr._format_of('x.xlsx') == 'Isra-Card-2026'              # skipped by the folder scan, identified alone
    assert fr._format_of('other.xlsx') is None
    import builtins
    assert builtins.input.__name__ == 'input'                        # the terminal prompt patch is undone
