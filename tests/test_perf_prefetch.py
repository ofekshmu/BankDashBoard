"""month_prefetch: a page that walks many months reads them with two range queries instead of one per month.

No database: a fake cursor records the statements the DataBase methods run."""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'source'))

from database import DataBase  # noqa: E402

BANK_COLS = ['ID', 'Name', 'Date', 'Ref', 'Out', 'Category']
CARD_COLS = ['TableName', 'CardID', 'Date/Executed_Date', 'Value_Date/Charge_Date', 'Income/Charge_Value',
             'Description/Charge_Currency', 'Reserved/Value_Currency', 'Out/Transaction_value', 'Category']


class FakeCursor:
    def __init__(self):
        self.sql = []
        self._rows, self.description = [], []

    def execute(self, sql, params=()):
        self.sql.append(' '.join(sql.split()))
        if 'FROM BankTransactions' in sql:
            self._rows = [(1, 'a', date(2026, 1, 5), 1, 10, 'x'), (2, 'b', date(2026, 1, 20), 2, 20, 'x'),
                          (3, 'c', date(2026, 3, 2), 3, 30, 'y')]
            self.description = [(c,) for c in BANK_COLS]
        else:
            self._rows = [('CardTransactions', '1111', date(2026, 1, 1), date(2026, 2, 10), 5, 'ILS', 'ILS', 5, 'x')]
            self.description = [(c,) for c in CARD_COLS]
        return self

    def fetchall(self):
        return self._rows


class FakeDb:
    def __init__(self):
        self.cursor = FakeCursor()


def test_months_in_the_span_are_answered_without_further_queries():
    db = FakeDb()
    with DataBase.month_prefetch(db, (2025, 12), (2026, 4)):
        assert len(db.cursor.sql) == 2                                  # one range query per table
        jan = DataBase.get_Bank_Transactions(db, 1, 2026)
        feb = DataBase.get_Bank_Transactions(db, 2, 2026)               # no rows that month: empty, same columns
        card = DataBase.get_cards_by_charge_date(db, 2, 2026)
        assert list(jan['ID']) == [1, 2] and list(jan.columns) == BANK_COLS
        assert feb.empty and list(feb.columns) == BANK_COLS
        assert len(card) == 1 and list(card.columns) == CARD_COLS
        assert len(db.cursor.sql) == 2                                  # still only the two range queries


def test_months_outside_the_span_and_after_the_block_query_normally():
    db = FakeDb()
    with DataBase.month_prefetch(db, (2026, 1), (2026, 2)):
        DataBase.get_Bank_Transactions(db, 8, 2025)                     # outside the window
        assert len(db.cursor.sql) == 3
    DataBase.get_Bank_Transactions(db, 1, 2026)                         # the block is over: the store is gone
    assert len(db.cursor.sql) == 4


def test_the_returned_frame_is_a_copy():
    db = FakeDb()
    with DataBase.month_prefetch(db, (2026, 1), (2026, 1)):
        first = DataBase.get_Bank_Transactions(db, 1, 2026)
        first.loc[:, 'Out'] = 0
        assert list(DataBase.get_Bank_Transactions(db, 1, 2026)['Out']) == [10, 20]


def test_timeline_schema_check_runs_once_per_process(monkeypatch):
    """Every timeline endpoint calls ensure_timeline_tables(); its 12 statements must not repeat per request."""
    class Cur:
        def __init__(self):
            self.n = 0

        def execute(self, *a, **k):
            self.n += 1

    class Conn:
        def commit(self):
            pass

    class Db:
        TIMELINE_SEED_CATEGORIES = DataBase.TIMELINE_SEED_CATEGORIES
        cursor, connection = Cur(), Conn()

    monkeypatch.setattr(DataBase, '_DataBase__timeline_ready', False)
    db = Db()
    DataBase.ensure_timeline_tables(db)
    first = db.cursor.n
    assert first >= 8
    DataBase.ensure_timeline_tables(db)
    assert db.cursor.n == first


def test_splits_are_not_read_again_when_the_caller_passes_them():
    import pandas as pd

    class Db:                                    # no get_all_splits: reading would raise
        pass

    df = pd.DataFrame([{'TableName': 'BankTransactions', 'ID': 1, 'Out': 100, 'Income': 0, 'Category': 'x', 'Description': ''},
                       {'TableName': 'BankTransactions', 'ID': 2, 'Out': 5, 'Income': 0, 'Category': 'x', 'Description': ''}])
    splits = [{'split_id': 10, 'orig_table': 'BankTransactions', 'orig_id': 1, 'amount': 60, 'description': 'a', 'category': 'p'},
              {'split_id': 11, 'orig_table': 'BankTransactions', 'orig_id': 1, 'amount': 40, 'description': 'b', 'category': 'q'}]
    out = DataBase.apply_splits_to_df(Db(), df, splits)
    assert sorted(out['ID']) == [2, 10, 11] and sorted(out['Out']) == [5, 40, 60]
