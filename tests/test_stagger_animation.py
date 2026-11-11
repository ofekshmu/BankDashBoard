"""Menus and lists enter with one shared stagger: a 0.4s `rise`, each item 40ms x its index later.

The rules live in source/html/stagger.css (lists, grids, dropdowns; linked by nav.js) and source/html/nav.js (side menu,
which is on every page). These checks keep the numbers from drifting and make sure the side menu still
carries an index on every item.
"""
import os
import re

HTML = os.path.join(os.path.dirname(__file__), '..', 'source', 'html')


def _read(name):
    with open(os.path.join(HTML, name), encoding='utf-8') as f:
        return f.read()


def test_stagger_css_has_one_rise_animation_and_the_40ms_rule():
    css = _read('stagger.css')
    assert len(re.findall(r'@keyframes rise\b', css)) == 1
    assert 'animation: rise .4s backwards;' in css
    assert 'animation-delay: calc(var(--i, 0) * 40ms);' in css


def test_list_items_get_their_index_and_it_is_capped():
    css = _read('stagger.css')
    for n in range(1, 13):
        assert re.search(r':nth-child\(%d\) \{ --i: %d; \}' % (n, n - 1), css), n
    assert ':nth-child(n+13) { --i: 12; }' in css


def test_stagger_never_overrides_an_items_own_animation():
    # :where() keeps the specificity at zero, so a row's own animation (exit, entrance) still wins
    css = _read('stagger.css')
    assert re.search(r':where\(\.stagger[^)]*\) > \* \{\s*animation: rise', css)


def test_side_menu_items_carry_an_index_and_use_the_same_numbers():
    js = _read('nav.js')
    assert 'nav-rise .4s backwards' in js and 'calc(var(--i,0)*40ms)' in js
    assert "setProperty('--i'" in js
    assert 'STAGGER_MAX = 12' in js
    assert 'prefers-reduced-motion' in js


def test_nav_js_links_the_stagger_sheet_and_the_server_serves_it_publicly():
    assert "/stagger.css" in _read('nav.js')
    src = open(os.path.join(HTML, '..', 'WebApp.py'), encoding='utf-8').read()
    assert "'/stagger.css'" in src and "@app.route('/stagger.css')" in src
