"""The monthly page's full-page loader ("Block Build" bar + analysis stage timeline).

Static checks: the controller is wired to the page's single progress controller, the analysis stage
thresholds match the points the analysis reports, and the other progress indicators step aside."""
import os
import re

HTML = os.path.join(os.path.dirname(__file__), '..', 'source', 'html')


def _page():
    with open(os.path.join(HTML, 'Base_template.html'), encoding='utf-8') as f:
        return f.read()


def test_the_bar_has_one_block_per_stage_and_no_extra_line_above_the_timeline():
    page = _page()
    assert 'id="bb-loader"' in page and 'id="bb-stages"' in page
    assert "track.innerHTML = new Array(n + 1).join(" in page                    # n blocks, n = number of stages
    assert 'for (var i = 0; i < st.length; i++) {' in page                      # the blocks follow the stages, not a fixed five
    assert 'bb-seg' not in page                                                  # the thin per-stage line is gone


def test_every_percentage_the_page_already_reports_reaches_the_loader():
    page = _page()
    assert '_bb.set(v);' in page and '_bb.show(_bbMode());' in page
    assert 'done: function(failed) {' in page and '_bb.finish(failed);' in page
    assert '_loadBar.done(!success);' in page          # a failed analysis must not show a fake 100%


def test_analysis_stage_thresholds_match_the_points_the_analysis_reports():
    """monthly_analysis() reports 15, 8, 10, 12, 6, 10, 5 points (cumulative 15, 23, 33, 45, 51, 61, 66 of 100)."""
    page = _page()
    block = page[page.index('analysis: [['):page.index("fetch:    [[")]
    bounds = [int(x) for x in re.findall(r"', (\d+)\]", block)]
    assert bounds == [15, 33, 51, 66, 100]
    cumulative = {15, 23, 33, 45, 51, 61, 66}
    assert {15, 33, 51, 66} <= cumulative


def test_the_other_progress_indicators_step_aside_while_it_is_up():
    page = _page()
    assert 'body.bb-on #page-load-bar-wrap, body.bb-on #regen-progress-panel, body.bb-on .log-float { display: none !important; }' in page
    assert 'z-index: 390' in page      # below the hamburger (400), so the menu stays reachable


def test_a_month_that_renders_from_the_cache_never_flashes_the_loader():
    page = _page()
    assert 'showTimer = setTimeout(reveal, 120)' in page     # appears only after a beat
    assert 'clearTimeout(showTimer); showTimer = null;' in page   # finish() before that cancels it
