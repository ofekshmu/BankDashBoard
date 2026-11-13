"""Payments that went into an apartment's value count as investments in the monthly analysis.

A transaction tagged with an apartment's category (שלום שבאזי 7 / Mona) is an expense by default. When the user
says on the housing page that it went into the apartment's value (kind `price`, or a `refund` of such money) it
is shown like any other investment (category "השקעה/חיסכון"): out of the spending / earning charts and in the
investments section. The original category stays in `Property_Category` so the page can say where it came from.

`mark()` is pure (a DataFrame and a set of keys); `mark_from_db()` finds the keys in the database and never raises,
so a failure leaves the analysis exactly as it was.
"""
import logging

import pandas as pd

logger = logging.getLogger(__name__)

ORIGINAL_COLUMN = 'Property_Category'


def row_keys(df):
    """The housing-page key of every row: 'BankTransactions:12' / 'CardTransactions:7', or 'split:3' for a
    split part (whose ID is the split's own)."""
    split = df['_split_orig_id'].notna() if '_split_orig_id' in df.columns else pd.Series(False, index=df.index)
    keys = []
    for is_split, table, tx_id in zip(split, df['TableName'], df['ID']):
        try:
            tx_id = int(tx_id)
        except (TypeError, ValueError):
            keys.append('')
            continue
        keys.append(f'split:{tx_id}' if is_split else f'{table}:{tx_id}')
    return pd.Series(keys, index=df.index)


def mark(df, keys, investment_category):
    """`df` with the rows whose key is in `keys` moved to `investment_category` (the original category is kept
    in the Property_Category column). Returns `df` itself when there is nothing to mark."""
    if not keys or df is None or df.empty or not {'TableName', 'ID', 'Category'} <= set(df.columns):
        return df
    hit = row_keys(df).isin(keys)
    if not hit.any():
        return df
    df = df.copy()
    if ORIGINAL_COLUMN not in df.columns:
        df[ORIGINAL_COLUMN] = None
    df.loc[hit, ORIGINAL_COLUMN] = df.loc[hit, 'Category']
    df.loc[hit, 'Category'] = investment_category
    return df


def mark_from_db(df, db=None, keys=None):
    """mark() with the keys read from the database (or passed in, to compute them once for many months).
    Any failure is logged and `df` is returned unchanged."""
    from Constants import INVESTMENT_CATEGORY
    try:
        if keys is None:
            keys = load_keys(db)
        return mark(df, keys, INVESTMENT_CATEGORY)
    except Exception:
        logger.exception('property investments could not be applied; the analysis is shown without them')
        return df


def load_keys(db=None):
    """The keys of every payment that went into an apartment's value (see housing_project_service)."""
    import housing_project_service as svc
    if db is None:
        from database import DataBase
        db = DataBase()
    return svc.investment_keys(db)
