"""Landing page boot: splash with progress, whole-dashboard reveal, per-tab cache."""
import os

with open(os.path.join(os.path.dirname(__file__), '..', 'index.html'), encoding='utf-8') as f:
    HTML = f.read()


def test_splash_is_in_the_markup_with_progress_bar_and_percent():
    assert 'id="boot"' in HTML and 'id="bootFill"' in HTML and 'id="bootPct"' in HTML


def test_dashboard_is_revealed_only_after_all_blocks_load():
    assert 'revealDashboard(true)' in HTML
    assert 'Promise.all(missing.map' in HTML
    assert 'id="bootWhat"' in HTML


def test_tiles_slide_in_and_blocks_are_cached_per_tab():
    assert '@keyframes tile-in' in HTML
    assert 'sessionStorage.setItem(CACHE_KEY' in HTML
    assert 'clearLandingCache();' in HTML   # sign-out drops the cache
