"""Merging one category into another (WebApp._merge_categories), with a temporary categories.json,
fake auto-tag rules and a fake database — nothing real is read or written."""
import json
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


class FakeDB:
    calls = []

    def replace_category(self, frm, to):
        FakeDB.calls.append(('replace', frm, to))
        return {'BankTransactions': 1, 'CardTransactions': 2, 'HousingProjects': 1}

    def commit_changes(self):
        FakeDB.calls.append(('commit',))


@pytest.fixture
def env(monkeypatch, tmp_path):
    import WebApp
    import database
    cats = tmp_path / 'categories.json'
    cats.write_text(json.dumps(['מצרכים', 'דירת קבלן', 'Mona']), encoding='utf-8')
    rules = {'בר סרוסי': 'דירת קבלן', 'סופר': 'מצרכים'}
    (tmp_path / 'דירת_קבלן.html').write_text('x')
    monkeypatch.setattr(WebApp, '_CATEGORIES_JSON_PATH', str(cats))
    monkeypatch.setattr(WebApp, 'CATEGORY_ANALYSIS_DIR', str(tmp_path))
    monkeypatch.setattr(WebApp, '_read_at', lambda: dict(rules))
    monkeypatch.setattr(WebApp, '_write_at', lambda d: rules.update(d))
    monkeypatch.setattr(WebApp, '_build_slug_map', lambda c, kind: {'דירת קבלן': 'דירת_קבלן'})
    monkeypatch.setattr(database, 'DataBase', FakeDB)
    FakeDB.calls = []
    return WebApp, cats, rules, tmp_path


def test_merge_moves_everything_and_drops_the_old_category(env):
    webapp, cats, rules, tmp_path = env
    out = webapp._merge_categories('דירת קבלן', 'Mona')
    assert FakeDB.calls == [('replace', 'דירת קבלן', 'Mona'), ('commit',)]
    assert json.loads(cats.read_text(encoding='utf-8')) == ['מצרכים', 'Mona']
    assert rules == {'בר סרוסי': 'Mona', 'סופר': 'מצרכים'} and out['rules_remapped'] == 1
    assert out['counts']['HousingProjects'] == 1
    assert not (tmp_path / 'דירת_קבלן.html').exists()                      # its cached analysis page is gone


@pytest.mark.parametrize('frm, into, message', [
    ('Mona', 'Mona', 'עצמה'), ('', 'Mona', 'חסרים'), ('אין', 'Mona', 'לא נמצאה'), ('Mona', 'אין', 'לא נמצאה'),
    ('NotCategorized', 'Mona', 'שמורה'), ('Mona', 'Excluded', 'שמורה')])
def test_merge_refuses_bad_requests_and_changes_nothing(env, frm, into, message):
    webapp, cats, rules, _ = env
    before = cats.read_text(encoding='utf-8')
    with pytest.raises(ValueError, match=message):
        webapp._merge_categories(frm, into)
    assert FakeDB.calls == [] and cats.read_text(encoding='utf-8') == before


def test_merge_endpoint_is_registered_once(env):
    webapp = env[0]
    rules = [r for r in webapp.app.url_map.iter_rules() if r.rule == '/api/tagger/categories/merge']
    assert len(rules) == 1 and rules[0].methods >= {'POST'}
