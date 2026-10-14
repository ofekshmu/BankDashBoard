"""The side menu's links live in one file, source/html/nav.js, served at /nav.js.

Every page with a sidebar leaves its link list empty (data-nav="<current page key>") and loads
/nav.js right after the sidebar, so adding or renaming a menu item happens in one place.
Generated copies (output.html) are rebuilt from Base_template.html and are not checked.
"""
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, 'source', 'html')
NAV_JS = os.path.join(HTML, 'nav.js')

# file → data-nav key of the page's own item ('' = page not in the menu, e.g. the landing page)
PAGES = {
    'index.html': '',
    'source/html/Base_template.html': 'monthly-page',
    'source/html/Bills.html': 'bills',
    'source/html/CardAnalysis.html': 'cards',
    'source/html/Files.html': 'files',
    'source/html/PlantTracker.html': 'plants',
    'source/html/RecurringCharges.html': 'recurring',
    'source/html/Search.html': 'search',
    'source/html/SpotifyTracker.html': 'spotify',
    'source/html/Tagger.html': 'tagger',
    'source/WebApp.py': None,          # categories + organizer pages are built here
    'source/src_utils/utils.py': None,  # category page
}


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


def _nav_keys():
    return re.findall(r"\['(\w+)',\s*'[^']+',\s*'(/[^']*)'\]", _read('source/html/nav.js'))


@pytest.mark.parametrize('rel', sorted(PAGES))
def test_every_sidebar_uses_the_shared_links(rel):
    s = _read(rel)
    boxes = re.findall(r'<div class="sidebar-scroll"([^>]*)>(.*?)</div>', s, re.S)
    assert boxes, 'no sidebar found'
    for attrs, body in boxes:
        assert 'data-nav=' in attrs and not body.strip(), 'link list must come from /nav.js'
    assert s.count('<script src="/nav.js"></script>') == len(boxes)
    assert 'class="nav-item' not in s, 'hard-coded menu item left behind'
    if PAGES[rel] is not None:
        assert [a for a, _ in boxes] == [f' data-nav="{PAGES[rel]}"']


def test_generated_pages_name_their_own_item():
    keys = {k for k, _ in _nav_keys()}
    found = re.findall(r'data-nav="([\w-]*)"', _read('source/WebApp.py') + _read('source/src_utils/utils.py'))
    assert sorted(found) == ['categories', 'categories', 'organizer'] and set(found) <= keys


def test_nav_js_lists_each_page_once_and_marks_page_keys_it_knows():
    keys = [k for k, _ in _nav_keys()]
    assert len(keys) == len(set(keys)) and len(keys) >= 14
    assert {v for v in PAGES.values() if v} - {'monthly-page'} <= set(keys)
    js = _read('source/html/nav.js')
    # the monthly page's script finds these by id
    for needed in ("'nav-overview'", "'nav-accounts'", "'nav-bills-link'", "'nav-bills-dot'"):
        assert needed in js


def _database_url_available():
    if os.environ.get('DATABASE_URL'):
        return True
    try:
        from dotenv import dotenv_values
    except ImportError:
        return False
    return bool(dotenv_values(os.path.join(ROOT, '.env')).get('DATABASE_URL'))


@pytest.mark.skipif(not _database_url_available(), reason='DATABASE_URL not configured')
def test_recurring_page_renders_the_current_template_with_the_cached_data(monkeypatch):
    """The cache keeps the data; the page shell always comes from today's template, so menu
    and layout changes show without a regeneration."""
    import WebApp
    import database

    class FakeDB:
        def ensure_recurring_tables(self):
            pass

        def get_recurring_cache(self):
            return {'html': '<html>old page with class="nav-item"</html>', 'data_json': '{"groups": []}'}

    monkeypatch.setattr(database, 'DataBase', FakeDB)
    c = WebApp.app.test_client()
    with c.session_transaction() as s:
        s['authenticated'] = True
    h = c.get('/recurring').get_data(as_text=True)
    assert 'old page' not in h and 'data-nav="recurring"' in h and '{"groups": []}' in h


@pytest.mark.skipif(not _database_url_available(), reason='DATABASE_URL not configured')
def test_nav_js_is_public_and_every_link_is_a_real_route():
    import WebApp
    c = WebApp.app.test_client()
    r = c.get('/nav.js')               # no session: the landing page loads it before sign-in
    assert r.status_code == 200 and 'javascript' in r.headers['Content-Type']
    rules = {rule.rule for rule in WebApp.app.url_map.iter_rules()}
    assert [href for _, href in _nav_keys() if href not in rules] == []
