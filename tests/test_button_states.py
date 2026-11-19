"""One button, eight states (source/html/buttons.css + nav.js): hover 8 %, pressed 97 %, focus ring 2px/2px,
loading keeps the width, success 2 s, error with retry, selected never colour alone, disabled 50 % with the reason."""
import re
from pathlib import Path

HTML = Path(__file__).resolve().parent.parent / 'source' / 'html'
CSS = (HTML / 'buttons.css').read_text(encoding='utf-8')
NAV = (HTML / 'nav.js').read_text(encoding='utf-8')
PAGES = [p for p in HTML.glob('*.html') if '<button' in p.read_text(encoding='utf-8')]


def test_hover_is_8_percent_lighter_and_only_where_hover_exists():
    assert 'brightness(1.08)' in CSS and '@media (hover: hover)' in CSS


def test_pressed_scales_to_97_percent():
    assert 'from = b.getBoundingClientRect().width > 240 ? 0.985 : 0.97' in NAV


def test_focus_ring_is_2px_with_2px_offset_for_the_keyboard_only():
    assert ':focus-visible' in CSS and 'outline: 2px solid' in CSS and 'outline-offset: 2px' in CSS


def test_loading_ignores_a_second_click_and_keeps_the_width():
    assert "data-state=\"loading\"" in CSS and 'pointer-events: none' in CSS
    assert "stopImmediatePropagation" in NAV and "style.minWidth" in NAV


def test_success_lasts_two_seconds_and_error_offers_retry():
    assert '}, 2000)' in NAV and 'נסו שוב' in NAV


def test_selected_has_a_tick_not_only_a_colour():
    assert re.search(r'aria-pressed="true"\]::before[^}]*content: "✓"', CSS, re.S)


def test_disabled_is_half_opacity_with_a_reason():
    assert 'opacity: .5' in CSS and 'data-reason' in NAV and '.btn-reason' in CSS


def test_no_page_dims_a_disabled_button_to_another_value():
    for p in PAGES + [HTML.parent.parent / 'index.html']:
        for line in p.read_text(encoding='utf-8').splitlines():
            m = re.search(r':disabled *\{[^}]*opacity *: *([0-9.]+)', line)
            assert not m or float(m.group(1)) == 0.5, (p.name, line.strip())


def test_stylesheet_is_served_publicly_and_linked_everywhere():
    web = (HTML.parent / 'WebApp.py').read_text(encoding='utf-8')
    assert "@app.route('/buttons.css')" in web and "'/buttons.css'" in web.split('_PUBLIC_PATHS')[1][:400]
    assert "['stagger', 'motion', 'buttons']" in NAV and '/buttons.css' in (HTML / 'login.html').read_text(encoding='utf-8')


def test_no_button_lifts_on_hover():
    for p in PAGES:
        assert not re.search(r'\.btn:hover *\{ *transform: *translateY', p.read_text(encoding='utf-8')), p.name


def test_a_click_paints_no_browser_highlight_over_the_button():
    assert '-webkit-tap-highlight-color: transparent' in CSS and 'user-select: none' in CSS
