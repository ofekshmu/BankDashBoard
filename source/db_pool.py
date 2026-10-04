"""Shared guard for the app's psycopg2 connection pools (DataBase and WebApp's _pg_conn).

psycopg2's ThreadedConnectionPool raises "connection pool exhausted" the moment every connection is
borrowed. A PoolGate sits in front of a pool and holds one permit per borrowed connection, so a
burst larger than the pool (the landing page fires 11 requests at once) waits for a free connection
instead of failing.
"""
import threading

import psycopg2


class PoolGate:
    """Caps borrowed connections at `size`; a borrower waits up to `timeout` seconds for a permit."""

    def __init__(self, size, timeout=30):
        self.size = size
        self.timeout = timeout
        self._slots = threading.BoundedSemaphore(size)

    def acquire(self):
        """Take a permit, or raise OperationalError when none frees up within the timeout."""
        if not self._slots.acquire(timeout=self.timeout):
            raise psycopg2.OperationalError(
                f'all {self.size} database connections stayed busy for {self.timeout}s')

    def release(self):
        """Give a permit back (exactly once per acquire — a BoundedSemaphore raises on extras)."""
        self._slots.release()

    def borrow(self, get_connection):
        """acquire(), then get_connection(); the permit is released again if that raises."""
        self.acquire()
        try:
            return get_connection()
        except BaseException:
            self.release()
            raise
