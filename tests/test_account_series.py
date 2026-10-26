"""An account's balance history: one value per day, the entry made last wins."""
from datetime import date

import src_utils.account_series as acs

D1, D2, D3 = date(2026, 10, 1), date(2026, 10, 13), date(2026, 10, 26)


def test_a_same_day_correction_replaces_the_earlier_entry():
    entered = [(D1, 500.0), (D3, 7.0), (D3, 0.0)]            # set to 7 and then corrected to 0 on the same day
    assert acs.collapse_same_day(entered) == [(D1, 500.0), (D3, 0.0)]


def test_zero_is_a_balance_like_any_other():
    assert acs.collapse_same_day([(D1, 12.0), (D2, 0.0)]) == [(D1, 12.0), (D2, 0.0)]


def test_the_result_is_sorted_by_date_whatever_the_entry_order():
    assert [d for d, _ in acs.collapse_same_day([(D3, 1.0), (D1, 2.0), (D2, 3.0), (D1, 4.0)])] == [D1, D2, D3]
    assert acs.collapse_same_day([]) == []


def test_latest_value_is_the_last_entry_of_the_latest_day():
    assert acs.latest_value([[D1, 500.0], [D3, 7.0], [D3, 0.0]]) == 0.0          # not the larger of the day's values
    assert acs.latest_value([[D3, 0.0], [D1, 500.0]]) == 0.0                       # list order does not matter across days
    assert acs.latest_value([]) is None and acs.latest_value(None) is None
    assert acs.latest_value([[D1, None]]) == 0.0
