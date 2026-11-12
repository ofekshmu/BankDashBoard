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


def test_a_recently_used_connection_is_not_probed_on_every_construction():
    """DataBase() is built many times per request; probing each time cost a round trip per construction
    (the card analysis page built it 13 times: ~700 ms of its 1.2 s). The probe now only runs on a connection
    that has been idle, and every successful statement marks the connection verified."""
    import inspect
    assert 0 < DataBase._PROBE_AFTER_IDLE_SECONDS <= 10          # short: an idle-in-transaction connection cannot be replayed
    src = inspect.getsource(DataBase.__new__)
    assert 'verified_at' in src and '_PROBE_AFTER_IDLE_SECONDS' in src
    from database import _ChainableCursor
    assert 'verified_at' in inspect.getsource(_ChainableCursor.execute)


def test_bootstrap_skips_the_thirteen_ddl_statements_when_every_base_table_exists():
    import inspect
    import re

    class Cur:
        def __init__(self, found):
            self.found, self.sql = found, []

        def execute(self, sql, params=()):
            self.sql.append(' '.join(sql.split()))
            return self

        def fetchone(self):
            return (self.found,)

    class Conn:
        def commit(self):
            pass

    class Db:
        def __init__(self, found):
            self.cursor, self.connection = Cur(found), Conn()

    full, partial = Db(len(DataBase._BASE_TABLES)), Db(3)
    DataBase._bootstrap_tables(full)
    assert len(full.cursor.sql) == 1                                  # just the catalogue check
    DataBase._bootstrap_tables(partial)
    assert len(partial.cursor.sql) == 1 + len(DataBase._BASE_TABLES)  # a missing table: everything is (re)created

    # the list of tables to look for is exactly the list the method creates
    created = re.findall(r'CREATE TABLE IF NOT EXISTS (\w+)\s*\(', inspect.getsource(DataBase._bootstrap_tables))
    assert sorted(t.lower() for t in created) == sorted(DataBase._BASE_TABLES)
