"""The landing page follows the flat "de-AI" design: no gradients, hairline cards, no shadows except floating layers,
one primary metric, neutral sub-boxes, accessible sparkline/status dots."""
import re
from pathlib import Path

HTML = (Path(__file__).resolve().parent.parent / 'index.html').read_text(encoding='utf-8')


def test_only_the_page_canvas_is_a_gradient():
    body = re.sub(r'/\*.*?\*/', '', HTML, flags=re.S)
    assert body.count('linear-gradient') == 1 and '--canvas:linear-gradient' in body


def test_shadows_only_on_floating_layers_and_focus_rings():
    lines = [l for l in HTML.splitlines() if 'box-shadow:' in l and 'none' not in l]
    for l in lines:
        assert any(k in l for k in ('shadow-overlay', 'shadow-card', 'focus-visible', '-4px 0 24px')), l


def test_cards_are_glass_with_no_lift_on_hover():
    card = re.search(r'\.card \{ position:relative[^}]*\}', HTML).group(0)
    assert 'var(--glass)' in card and 'var(--shadow-card)' in card
    assert 'translateY' not in HTML


def test_primary_card_is_bigger_than_secondary():
    assert re.search(r'\.card\.primary \.kpi \{[^}]*font-size:40px', HTML)
    assert re.search(r'\n\s*\.kpi \{[^}]*font-size:22px', HTML)


def test_mini_kpis_are_neutral_and_sparkline_has_no_area():
    assert 'mini-kpi coloured' in HTML or "' coloured'" in HTML   # only tiles that carry a colour (bills) are filled
    assert 'class="ta"' not in HTML and 'class=\\"ta\\"' not in HTML


def test_accessibility_hooks():
    assert 'role="img" aria-label="' in HTML          # sparkline + status dot
    assert 'prefers-reduced-motion' in HTML
    assert 'data-retry' in HTML


def test_accounts_is_primary_and_monthly_second():
    assert "['accounts', 'monthly']" in HTML
    assert re.search(r'\.card\.lead2 \.kpi \{[^}]*font-size:30px', HTML)


def test_eye_button_sits_above_the_card_link_overlay():
    assert re.search(r'\.mask-btn \{ position:relative; z-index:2', HTML)
