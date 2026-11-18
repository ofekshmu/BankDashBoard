"""The landing page follows the flat "de-AI" design: no gradients, hairline cards, no shadows except floating layers,
one primary metric, neutral sub-boxes, accessible sparkline/status dots."""
import re
from pathlib import Path

HTML = (Path(__file__).resolve().parent.parent / 'index.html').read_text(encoding='utf-8')


def test_no_gradients_anywhere():
    assert 'gradient' not in re.sub(r'/\*.*?\*/', '', HTML, flags=re.S)


def test_shadows_only_on_floating_layers_and_focus_rings():
    lines = [l for l in HTML.splitlines() if 'box-shadow' in l and 'none' not in l]
    for l in lines:
        assert any(k in l for k in ('shadow-overlay', 'focus-visible', '-4px 0 24px')), l


def test_cards_are_hairline_with_no_lift_on_hover():
    card = re.search(r'\.card \{ position:relative[^}]*\}', HTML).group(0)
    assert 'var(--border)' in card and 'shadow' not in card
    assert 'translateY' not in HTML


def test_primary_card_is_bigger_than_secondary():
    assert re.search(r'\.card\.primary \.kpi \{[^}]*font-size:40px', HTML)
    assert re.search(r'\n\s*\.kpi \{[^}]*font-size:22px', HTML)


def test_mini_kpis_are_neutral_and_sparkline_has_no_area():
    assert '--mk' not in HTML
    assert 'class="ta"' not in HTML and 'class=\\"ta\\"' not in HTML


def test_accessibility_hooks():
    assert 'role="img" aria-label="' in HTML          # sparkline + status dot
    assert 'prefers-reduced-motion' in HTML
    assert 'data-retry' in HTML
