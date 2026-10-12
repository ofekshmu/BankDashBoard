"""Comparing an uploaded credit-card file with the rows stored for the same file."""
from datetime import date, datetime

import src_utils.file_diff as fd


def rec(name='בית קפה', executed=date(2026, 10, 1), charge=date(2026, 10, 10), value=50.0, serial='1001', **over):
    r = {'name': name, 'executed_date': executed, 'charge_date': charge, 'charge_value': value,
         'charge_currency': '₪', 'transaction_value': value, 'value_currency': '₪',
         'extra_info': f'Serial: {serial} | Info: (None)'}
    r.update(over)
    return r


A, B, C, D = rec('א', serial='1'), rec('ב', serial='2', value=20), rec('ג', serial='3', value=7), rec('ד', serial='4')


# ── normalising ────────────────────────────────────────────────────────────
def test_amounts_are_rounded_the_way_the_database_stores_them():
    assert fd.norm_amount(272.82) == 273 and fd.norm_amount('95.0') == 95 and fd.norm_amount(2.5) == 3
    assert fd.norm_amount(-2.5) == -3 and fd.norm_amount(None) is None and fd.norm_amount('') is None


def test_dates_and_text_are_normalised():
    assert fd.norm_date(datetime(2026, 10, 3, 14, 5)) == '2026-10-03' == fd.norm_date(date(2026, 10, 3))
    assert fd.norm_date('End of month ') == 'End of month' and fd.norm_date(None) == ''
    assert fd.norm_text('  a \n  b ') == 'a b' and fd.norm_text(None) == ''


def test_serial_is_read_from_extra_info():
    assert fd.serial_of(A) == '1'
    assert fd.serial_of({'extra_info': 'Trans type: x | Method: y'}) is None
    assert fd.serial_of({'extra_info': 'Serial: None | Info: (None)'}) is None


# ── comparing ──────────────────────────────────────────────────────────────
def test_identical_files():
    d = fd.compare([A, B, C], [A, B, C])
    assert d.counts() == {'same': 3, 'changed': 0, 'added': 0, 'removed': 0, 'moved': 0}
    assert fd.classify(d) == fd.STATUS_IDENTICAL


def test_rounding_differences_do_not_count_as_changes():
    stored = [dict(A, charge_value=273, transaction_value=273)]       # as read back from the integer columns
    new = [dict(A, charge_value=272.82, transaction_value=272.82)]
    assert fd.classify(fd.compare(stored, new)) == fd.STATUS_IDENTICAL


def test_new_file_with_extra_rows():
    d = fd.compare([A, B], [D, A, B, C])                                # new rows come first (newest first)
    assert d.counts()['added'] == 2 and not d.removed and not d.changed and d.moved == 0
    assert sorted(d.added) == [0, 3]
    assert fd.classify(d) == fd.STATUS_NEW


def test_a_stored_row_missing_from_the_new_file_is_its_own_status():
    d = fd.compare([A, B, C], [A, C])
    assert d.removed == [1] and not d.added
    assert fd.classify(d) == fd.STATUS_MISSING == 'missing_rows'


def test_missing_rows_win_over_added_and_changed_rows():
    d = fd.compare([A, B], [A, D])
    assert d.added == [1] and d.removed == [1]
    assert fd.classify(d) == fd.STATUS_MISSING
    corrected = dict(B, charge_value=25.0, transaction_value=25.0)
    assert fd.classify(fd.compare([A, B, C], [A, corrected])) == fd.STATUS_MISSING


def test_same_voucher_with_other_values_is_a_change_not_an_add_and_a_remove():
    corrected = dict(B, charge_value=25.0, transaction_value=25.0)
    d = fd.compare([A, B], [A, corrected])
    assert not d.added and not d.removed
    assert d.changed == [(1, 1, ['charge_value', 'transaction_value'])]
    assert fd.classify(d) == fd.STATUS_OTHER


def test_repeated_identical_purchases_are_matched_one_to_one():
    x = rec('משקט', serial=None, value=10, extra_info='Serial: None | Info: (None)')
    assert fd.compare([x, x], [x, x]).counts()['same'] == 2
    d = fd.compare([x, x], [x, x, x])
    assert len(d.matched) == 2 and len(d.added) == 1
    d = fd.compare([x, x, x], [x, x])
    assert len(d.matched) == 2 and len(d.removed) == 1


def test_a_different_order_is_reported_as_moved_rows():
    d = fd.compare([A, B, C, D], [A, C, B, D])
    assert d.moved == 1 and fd.classify(d) == fd.STATUS_IDENTICAL
    assert fd.compare([A, B, C, D], [D, C, B, A]).moved == 3


def test_a_file_of_another_card_is_never_identical():
    d = fd.compare([A], [A])
    assert fd.classify(d, identity_ok=False) == fd.STATUS_OTHER


def test_empty_sides():
    assert fd.classify(fd.compare([], [])) == fd.STATUS_IDENTICAL
    assert fd.classify(fd.compare([], [A])) == fd.STATUS_NEW
    assert fd.classify(fd.compare([A], [])) == fd.STATUS_MISSING


# ── structure ──────────────────────────────────────────────────────────────
def test_structure_diff_lists_only_fields_both_sides_know():
    old = {'format': 'Isra-Card-2026', 'header_row': 12, 'columns': 8, 'rows': 25}
    new = {'format': 'Isra-Card-2026', 'header_row': 12, 'columns': 8, 'rows': 40, 'headers': ['x']}
    out = {s['field']: s for s in fd.structure_diff(old, new)}
    assert set(out) == {'format', 'header_row', 'columns', 'rows'}
    assert out['rows'] == {'field': 'rows', 'label': 'שורות בטבלה', 'old': 25, 'new': 40, 'changed': True}
    assert not out['header_row']['changed']


# ── investigating missing rows ─────────────────────────────────────────────
def test_date_range_and_total():
    rows = [rec(executed=date(2026, 10, 3), value=10.4), rec(executed=date(2026, 9, 28), value=20.6), rec(executed='n/a')]
    assert fd.date_range(rows) == ('2026-09-28', '2026-10-03') and fd.date_range([]) is None
    assert fd.total(rows) == 10 + 21 + 50


def test_position_shape():
    assert fd.position_shape([], 5) == 'none' and fd.position_shape([0, 1, 2], 3) == 'all'
    assert fd.position_shape([3, 4], 5) == 'tail' and fd.position_shape([0, 1], 5) == 'head'
    assert fd.position_shape([2, 3], 6) == 'block' and fd.position_shape([1, 4], 6) == 'scattered'


def test_similar_candidates_need_two_of_name_date_amount():
    gone = rec('קפה', serial='9', value=30.0)
    pool = [(0, rec('קפה', serial='1', value=45.0)),                      # same name + date, amount differs
            (1, rec('מסעדה', serial='2', value=30.0)),                    # same date + amount, name differs
            (2, rec('קפה', serial='3', value=30.0, executed=date(2026, 10, 5))),   # same name + amount, date differs
            (3, rec('אחר', serial='4', value=99.0, executed=date(2026, 9, 1)))]    # nothing in common
    out = fd.similar_candidates(gone, pool)
    assert [(c['index'], c['differs']) for c in out] == [(0, ['amount']), (1, ['name']), (2, ['date'])]
    assert fd.similar_candidates(gone, pool, limit=1)[0]['index'] == 0
