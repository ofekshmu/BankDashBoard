"""Apartment-value payments shown as investments in the monthly analysis (src_utils/property_investments.py)."""
import pandas as pd

import src_utils.property_investments as pi

INV = 'השקעה/חיסכון'


def frame():
    return pd.DataFrame({
        'ID': [1117, 737, 2340, 5, 77],
        'TableName': ['BankTransactions', 'BankTransactions', 'CardTransactions', 'BankTransactions', 'CardTransactions'],
        'Name': ['רכישת נכס', 'העברה', 'ליווי', 'משכנתא', 'חלק מפוצל'],
        'Final_Value': [-10000.0, -15000.0, -5000.0, -2500.0, -300.0],
        'Category': ['Mona', 'Mona', 'Mona', 'שלום שבאזי 7', 'Mona'],
        '_split_orig_id': [None, None, None, None, 9],
    })


def test_row_keys_follow_the_housing_page_convention():
    assert list(pi.row_keys(frame())) == ['BankTransactions:1117', 'BankTransactions:737', 'CardTransactions:2340',
                                          'BankTransactions:5', 'split:77']


def test_marked_rows_become_investments_and_remember_where_they_came_from():
    df = frame()
    out = pi.mark(df, {'BankTransactions:1117', 'BankTransactions:5', 'split:77'}, INV)
    assert list(out['Category']) == [INV, 'Mona', 'Mona', INV, INV]
    assert list(out[pi.ORIGINAL_COLUMN].fillna('-')) == ['Mona', '-', '-', 'שלום שבאזי 7', 'Mona']
    assert list(df['Category']) == ['Mona', 'Mona', 'Mona', 'שלום שבאזי 7', 'Mona']          # the input is untouched


def test_nothing_to_mark_returns_the_same_frame():
    df = frame()
    assert pi.mark(df, set(), INV) is df
    assert pi.mark(df, {'BankTransactions:999'}, INV) is df
    empty = pd.DataFrame()
    assert pi.mark(empty, {'x'}, INV) is empty
    no_ids = pd.DataFrame({'Category': ['Mona']})
    assert pi.mark(no_ids, {'x'}, INV) is no_ids


def test_a_failure_leaves_the_analysis_as_it_was(monkeypatch):
    df = frame()

    def boom(db=None):
        raise RuntimeError('db down')
    monkeypatch.setattr(pi, 'load_keys', boom)
    assert pi.mark_from_db(df) is df


def test_keys_given_to_mark_from_db_are_used_without_a_database():
    out = pi.mark_from_db(frame(), keys={'BankTransactions:737'})
    assert out.loc[1, 'Category'] == INV
