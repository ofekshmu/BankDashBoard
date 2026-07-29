"""Tests for the Category Analysis page's regen path (WebApp.py + calculations.py)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime

import pandas as pd

import WebApp
from src_utils.calculations import SimpleMath


def test_build_slug_map_resolves_collisions():
    """Two distinct names that punctuation-strip to the same base slug (e.g.
    differing only by an asterisk vs. a double space) must not share a slug —
    sharing one means they'd share one generated HTML file, silently
    clobbering each other."""
    names = ['PAYPAL *NETFLIX COM', 'PAYPAL  NETFLIX COM', 'a totally unrelated business']
    slug_map = WebApp._build_slug_map(names, 'biz')

    assert len(set(slug_map.values())) == len(names), "every distinct name must get its own slug"
    assert slug_map['a totally unrelated business'] == 'biz_a_totally_unrelated_business', \
        "a name with no collision should keep the plain, unhashed slug"

    # Same input always produces the same slugs (stable across regens).
    slug_map2 = WebApp._build_slug_map(names, 'biz')
    assert slug_map == slug_map2
    print("PASS: _build_slug_map resolves collisions")


def test_build_slug_map_no_collision_passthrough():
    names = ['מצרכים', 'רכב', 'ביטוחים']
    slug_map = WebApp._build_slug_map(names, 'cat')
    assert slug_map['מצרכים'] == 'cat_מצרכים'
    assert slug_map['רכב'] == 'cat_רכב'
    assert slug_map['ביטוחים'] == 'cat_ביטוחים'
    print("PASS: _build_slug_map passes through non-colliding names unchanged")


def test_process_prices_handles_single_row_dataframe():
    """Regression test: df.apply(func, axis=1) where func returns a 4-element
    pd.Series used to raise "Columns must be same length as key" specifically
    when df had exactly one row (a very common case — many businesses in a
    real dataset only ever appear once or twice). Fixed via result_type='expand'."""
    df = pd.DataFrame([{
        'TableName': 'BankTransactions',
        'Category': 'מצרכים',
        'Date': datetime(2026, 1, 5),
        'Income': 0,
        'Out': 150.0,
    }])
    result = SimpleMath.process_prices(df.copy(), general_analysis=False)
    assert len(result) == 1
    assert result.iloc[0]['Final_Value'] == -150.0
    assert result.iloc[0]['Transaction_Type'] is not None
    print("PASS: process_prices handles a single-row DataFrame")


def test_process_prices_handles_multi_row_dataframe():
    """Same as above but with multiple rows — must keep working exactly as
    before (result_type='expand' should be a no-op for the already-working
    multi-row case)."""
    df = pd.DataFrame([
        {'TableName': 'BankTransactions', 'Category': 'מצרכים', 'Date': datetime(2026, 1, 5), 'Income': 0, 'Out': 150.0},
        {'TableName': 'BankTransactions', 'Category': 'רכב', 'Date': datetime(2026, 1, 10), 'Income': 500.0, 'Out': 0},
    ])
    result = SimpleMath.process_prices(df.copy(), general_analysis=False)
    assert len(result) == 2
    assert result.iloc[0]['Final_Value'] == -150.0
    assert result.iloc[1]['Final_Value'] == 500.0
    print("PASS: process_prices handles a multi-row DataFrame")


if __name__ == '__main__':
    test_build_slug_map_resolves_collisions()
    test_build_slug_map_no_collision_passthrough()
    test_process_prices_handles_single_row_dataframe()
    test_process_prices_handles_multi_row_dataframe()
    print("\nAll tests passed")
