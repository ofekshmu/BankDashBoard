"""Connection-pool accounting without a real database.

psycopg2's ThreadedConnectionPool raises "connection pool exhausted" as soon as every connection is
borrowed. DataBase must (1) make borrowers wait for a free connection instead, and (2) get back the
connection of a thread that ended without returning it (background workers, streamed responses).
"""
import gc
import threading
import time

import psycopg2
import psycopg2.extensions
import psycopg2.pool
import pytest

from database import DataBase
from db_pool import PoolGate


class FakeConn:
    def __init__(self):
        self.closed = 0
        self.autocommit = False

    def get_transaction_status(self):
        return psycopg2.extensions.TRANSACTION_STATUS_IDLE

    def cursor(self):
        conn = self

        class _Cur:
            def execute(self, *a):
                if conn.closed:
                    raise psycopg2.OperationalError('closed')

            def close(self):
                pass
        return _Cur()

    def rollback(self):
        pass


class FakePool:
    """Same contract as psycopg2's pool: fails immediately past maxconn."""
    def __init__(self, minconn, maxconn, *a, **kw):
        self.maxconn = maxconn
        self.idle, self.used = [], set()
        self.lock = threading.Lock()
        self.peak = 0

    def getconn(self):
        with self.lock:
            if len(self.used) >= self.maxconn:
                raise psycopg2.pool.PoolError('connection pool exhausted')
            conn = self.idle.pop() if self.idle else FakeConn()
            self.used.add(conn)
            self.peak = max(self.peak, len(self.used))
            return conn

    def putconn(self, conn, close=False):
        with self.lock:
            self.used.discard(conn)
            if not close:
                self.idle.append(conn)


@pytest.fixture
def pool(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://fake')
    monkeypatch.setattr(psycopg2.pool, 'ThreadedConnectionPool', FakePool)
    monkeypatch.setattr(psycopg2.extensions, 'register_type', lambda *a: None)
    monkeypatch.setattr(DataBase, '_DataBase__pool', None)
    monkeypatch.setattr(DataBase, '_DataBase__instance', None)
    monkeypatch.setattr(DataBase, '_DataBase__tables_bootstrapped', True)
    monkeypatch.setattr(DataBase, '_gate', PoolGate(DataBase.POOL_MAX, timeout=30))
    yield lambda: DataBase._get_pool()
    DataBase.release_thread_connection()


def _run_threads(n, fn):
    errors = []

    def wrap():
        try:
            fn()
        except Exception as e:  # noqa: BLE001 — collected for the assertion
            errors.append(f'{type(e).__name__}: {e}')
    threads = [threading.Thread(target=wrap) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return errors


def test_burst_larger_than_the_pool_waits_instead_of_failing(pool):
    def request():
        DataBase().cursor.execute('SELECT 1')
        time.sleep(0.05)                     # hold the connection like a real query
        DataBase.release_thread_connection()
    assert _run_threads(DataBase.POOL_MAX + 8, request) == []
    assert pool().peak == DataBase.POOL_MAX and not pool().used


def test_thread_that_never_returns_its_connection_gives_it_back_when_it_ends(pool):
    def leaky_worker():
        DataBase().cursor.execute('SELECT 1')   # no release_thread_connection()
    for _ in range(DataBase.POOL_MAX * 3):       # far more leaky threads than the pool holds
        assert _run_threads(1, leaky_worker) == []
        gc.collect()
    assert not pool().used
    assert _run_threads(DataBase.POOL_MAX, lambda: DataBase().cursor.execute('SELECT 1')) == []


def test_explicit_release_then_thread_end_returns_the_connection_once(pool):
    def worker():
        DataBase().cursor.execute('SELECT 1')
        DataBase.release_thread_connection()
        DataBase.release_thread_connection()     # second call is a no-op
    assert _run_threads(3, worker) == []
    gc.collect()
    # an over-release would raise ValueError from the BoundedSemaphore; all permits are free again
    slots = DataBase._gate._slots
    assert all(slots.acquire(blocking=False) for _ in range(DataBase.POOL_MAX))
    assert not slots.acquire(blocking=False)


def test_full_pool_times_out_with_a_clear_error(pool, monkeypatch):
    DataBase._gate.timeout = 0.2
    hold, done = threading.Event(), threading.Event()

    def holder():
        DataBase().cursor.execute('SELECT 1')
        hold.set()
        done.wait(5)
        DataBase.release_thread_connection()
    threads = [threading.Thread(target=holder) for _ in range(DataBase.POOL_MAX)]
    for t in threads:
        t.start()
    while len(pool().used) < DataBase.POOL_MAX:
        time.sleep(0.01)
    try:
        errors = _run_threads(1, DataBase)
        assert len(errors) == 1 and 'stayed busy' in errors[0]
    finally:
        done.set()
        for t in threads:
            t.join()
    assert not pool().used


def test_replacing_a_dead_connection_keeps_the_count(pool):
    def worker():
        db = DataBase()
        db.connection.closed = 1                 # server dropped it
        DataBase().cursor.execute('SELECT 1')    # __new__ replaces it
        DataBase.release_thread_connection()
    assert _run_threads(DataBase.POOL_MAX + 2, worker) == []
    gc.collect()
    assert not pool().used


# ── WebApp's _pg_conn() pool (raw SQL routes) ──────────────────────────────
@pytest.fixture
def pg(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://fake')
    import WebApp
    fake = FakePool(1, WebApp._PG_POOL_MAX)
    monkeypatch.setattr(WebApp, '_pg_pool', fake)
    monkeypatch.setattr(WebApp, '_pg_gate', PoolGate(WebApp._PG_POOL_MAX, timeout=30))
    return WebApp, fake


def test_pg_conn_burst_waits_instead_of_failing(pg):
    WebApp, fake = pg

    def route():
        conn = WebApp._pg_conn()
        try:
            time.sleep(0.05)
        finally:
            conn.close()
    assert _run_threads(WebApp._PG_POOL_MAX + 8, route) == []
    assert fake.peak == WebApp._PG_POOL_MAX and not fake.used


def test_pg_conn_not_closed_on_an_error_path_is_returned_anyway(pg):
    WebApp, fake = pg

    def buggy_route():
        conn = WebApp._pg_conn()
        raise RuntimeError('query failed before close()')
    for _ in range(WebApp._PG_POOL_MAX * 2):
        assert len(_run_threads(1, buggy_route)) == 1
        gc.collect()
    assert not fake.used


def test_pg_conn_close_is_idempotent(pg):
    WebApp, fake = pg
    conn = WebApp._pg_conn()
    conn.close()
    conn.close()                                 # would over-release the BoundedSemaphore
    del conn
    gc.collect()
    slots = WebApp._pg_gate._slots
    assert all(slots.acquire(blocking=False) for _ in range(WebApp._PG_POOL_MAX))


# ── PoolGate itself ────────────────────────────────────────────────────────
def test_pool_gate_releases_the_permit_when_getting_the_connection_fails():
    gate = PoolGate(1, timeout=0.1)

    def failing_connect():
        raise RuntimeError('connect failed')
    with pytest.raises(RuntimeError):
        gate.borrow(failing_connect)
    assert gate.borrow(lambda: 'conn') == 'conn'          # the permit came back
    with pytest.raises(psycopg2.OperationalError, match='all 1 database connections stayed busy'):
        gate.acquire()
    gate.release()
    with pytest.raises(ValueError):
        gate.release()                                     # more releases than acquires
