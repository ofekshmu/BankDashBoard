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
    assert 'animation: rise var(--rise-dur, .4s) backwards;' in css
    assert 'animation-delay: calc(var(--i, 0) * 40ms * var(--rise-on, 1));' in css


def test_list_items_get_their_index_and_it_is_capped():
    css = _read('stagger.css')
    for n in range(1, 13):
        assert re.search(r':nth-child\(%d\)\) \{ --i: %d; \}' % (n, n - 1), css), n
    assert ':nth-child(n+13)) { --i: 12; }' in css


def test_stagger_never_overrides_an_items_own_animation():
    # :where() keeps the specificity at zero, so a row's own animation (exit, entrance) still wins
    css = _read('stagger.css')
    assert re.search(r':where\(\.stagger[^{]*\) \{\s*animation: rise', css)
    assert not re.search(r'\) > \* \{', css)


def test_side_menu_items_carry_an_index_and_use_the_same_numbers():
    js = _read('nav.js')
    assert 'nav-rise .4s backwards' in js and 'calc(var(--i,0)*40ms)' in js
    assert "setProperty('--i'" in js
    assert 'STAGGER_MAX = 12' in js
    assert 'prefers-reduced-motion' in js


def test_nav_js_links_the_stagger_sheet_and_the_server_serves_it_publicly():
    assert "['stagger', 'motion']" in _read('nav.js')
    src = open(os.path.join(HTML, '..', 'WebApp.py'), encoding='utf-8').read()
    for name in ('stagger', 'motion'):
        assert "'/%s.css'" % name in src and "@app.route('/%s.css')" % name in src


def test_expand_uses_the_shared_ease_out_350ms():
    css = _read('motion.css')
    assert '--ease-expand: cubic-bezier(0.16, 1, 0.3, 1);' in css and '--dur-expand: 0.35s;' in css
    assert 'details::details-content' in css
    assert 'cubic-bezier(.16,1,.3,1)' in _read('Search.html')


def test_button_press_sinks_to_95_and_springs_back():
    js = _read('nav.js')
    assert 'initPress()' in js and '0.95' in js and "scale: '1.04'" in js
    assert "classList.contains('nav-item')" in js    # side-menu rows are not pressed


def test_loading_placeholders_do_not_animate_so_a_list_never_rises_twice():
    css = _read('stagger.css')
    assert '.tx-list > :not(.sq-loading, .skel-card)' in css


def test_a_redrawn_list_does_not_rise_again():
    css = _read('stagger.css')
    assert '.stg-still { --rise-dur: 0s; --rise-on: 0; }' in css
    js = _read('nav.js')
    assert "classList.add('stg-still')" in js and "classList.remove('stg-still')" in js
    # the rows that own their entrance (tagging, files) follow the same switch
    for page in ('Tagger.html', 'Files.html'):
        assert 'var(--rise-dur, .4s)' in _read(page), page


def test_only_real_stagger_lists_are_marked_still():
    js = _read('nav.js')
    assert "getComputedStyle(n).animationName === 'rise'" in js      # not any container that happens to be redrawn


def test_served_pages_and_assets_are_revalidated():
    src = open(os.path.join(HTML, '..', 'WebApp.py'), encoding='utf-8').read()
    assert '@app.after_request' in src and '_revalidate_pages_and_assets' in src


def test_tag_all_leaves_the_screen_before_the_server_answers():
    js = _read('Tagger.html')
    body = js[js.index('async function _doTagAll'):js.index('function _restoreRow')]
    assert body.index('rows.forEach(_collapseRow)') < body.index("fetch('/api/tagger/tag-all-by-name'")
    assert 'rows.forEach(_restoreRow)' in body       # rolled back when the server refuses
    no = js[js.index('async function confirmTagAll'):js.index('const _kindByName')]
    assert no.index('exitRow(key)') < no.index("fetch('/api/tagger/save-rule'")


def test_success_mark_draws_the_circle_then_the_tick():
    css = _read('motion.css')
    assert '.ok-draw circle' in css and 'ok-draw-line .3s ease-out forwards' in css
    assert '.ok-draw path' in css and 'ok-draw-line .17s ease-out .3s forwards' in css    # 300ms + 170ms = the 470ms of the brief
    assert 'window.okDraw' in _read('nav.js')
    for page, kind in (('Tagger.html', "type === 'success'"), ('Files.html', "type === 'ok'"), ('PlantTracker.html', "kind === 'ok'")):
        assert 'okDraw()' in _read(page) and kind in _read(page), page
