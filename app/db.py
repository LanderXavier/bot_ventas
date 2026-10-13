from __future__ import annotations
from psycopg_pool import ConnectionPool

_pool: ConnectionPool | None = None

def pool(dsn: str) -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(dsn, open=True)
    return _pool
