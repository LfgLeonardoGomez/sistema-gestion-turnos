from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def get_connection(request: Request) -> Iterator[Connection]:
    pool: ConnectionPool = request.app.state.pool
    with pool.connection() as conn:
        yield conn


ConnDep = Annotated[Connection, Depends(get_connection)]


def create_pool(database_url: str, password: str) -> ConnectionPool:
    return ConnectionPool(
        conninfo=database_url,
        min_size=1,
        max_size=10,
        open=False,
        kwargs={"row_factory": dict_row, "password": password},
    )
