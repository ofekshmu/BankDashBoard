"""Neon drops idle connections (pooler idle timeout / compute auto-suspend). The next query on such a
connection fails with "SSL connection has been closed unexpectedly". These tests drop sockets the
same way and check that requests still succeed.

Opt-in (talks to DATABASE_URL, read-only queries only): set DB_TESTS=1.
"""
import os
import socket
import threading

import pytest

pytestmark = pytest.mark.skipif(os.getenv('DB_TESTS') != '1', reason='set DB_TESTS=1 to run against DATABASE_URL')


@pytest.fixture(scope='module')
def DataBase():
    from dotenv import load_dotenv
    load_dotenv()
    from database import DataBase
    return DataBase


def _drop(conn):
    """Simulate the server dropping the connection: shut down its TCP socket."""
    sk = socket.socket(fileno=conn.fileno())
    try:
        sk.shutdown(socket.SHUT_RDWR)
    finally:
        sk.detach()


def _in_thread(fn):
    out = {}

    def run():
        try:
            out['value'] = fn()
        except Exception as e:  # noqa: BLE001 — reported by the assertion
            out['error'] = f'{type(e).__name__}: {e}'
    t = threading.Thread(target=run)
    t.start()
    t.join()
    return out


def _fill_pool(DataBase, n=6):
    def borrow():
        db = DataBase()
        db.cursor.execute('SELECT 1').fetchone()
        db.connection.rollback()
        DataBase.release_thread_connection()
    threads = [threading.Thread(target=borrow) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def _request(DataBase):
    def fn():
        try:
            return DataBase().cursor.execute('SELECT 42').fetchone()[0]
        finally:
            DataBase.release_thread_connection()
    return _in_thread(fn)


def test_request_survives_all_idle_pooled_connections_dropped(DataBase):
    _fill_pool(DataBase)
    pool = DataBase._get_pool()
    for c in list(pool._pool):
        DataBase._mark_idle_since(c, 0)          # pretend they've been idle for a long time
        _drop(c)
    assert _request(DataBase) == {'value': 42}


def test_dead_connections_are_discarded_not_leaked(DataBase):
    _fill_pool(DataBase)
    pool = DataBase._get_pool()
    for c in list(pool._pool):
        DataBase._mark_idle_since(c, 0)
        _drop(c)
    assert _request(DataBase) == {'value': 42}
    assert len(pool._used) == 0                    # every borrowed connection went back
    assert all(not c.closed for c in pool._pool)   # dead ones were closed and dropped, not re-pooled


def test_connection_dropped_mid_request_is_replaced_on_next_statement(DataBase):
    def fn():
        try:
            db = DataBase()
            db.cursor.execute('SELECT 1').fetchone()
            db.connection.commit()                 # idle, between transactions
            _drop(db.connection)                   # server drops it while this thread holds it
            return db.cursor.execute('SELECT 7').fetchone()[0]
        finally:
            DataBase.release_thread_connection()
    assert _in_thread(fn) == {'value': 7}


def test_no_silent_retry_inside_an_open_transaction(DataBase):
    def fn():
        try:
            db = DataBase()
            db.cursor.execute('SELECT 1').fetchone()   # transaction now open (not committed)
            _drop(db.connection)
            db.cursor.execute('SELECT 2').fetchone()
            return 'retried'
        finally:
            DataBase.release_thread_connection()
    out = _in_thread(fn)
    assert 'error' in out                              # surfaced, not replayed on a new connection
    assert _request(DataBase) == {'value': 42}         # and the next request is fine


def test_recently_used_pool_dropped_all_at_once(DataBase):
    """Connections used seconds ago (not 'stale') all dropped together: the retry must not take another dead one."""
    _fill_pool(DataBase)
    for c in list(DataBase._get_pool()._pool):
        _drop(c)
    assert _request(DataBase) == {'value': 42}
