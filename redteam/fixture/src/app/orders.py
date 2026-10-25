"""Order lookups for the red-team fixture repository."""

import sqlite3


def find_order(
    connection: sqlite3.Connection, order_id: int
) -> tuple[object, ...] | None:
    """Return one order row using a parameterised query."""
    return connection.execute(
        "SELECT id, total FROM orders WHERE id = ?", (order_id,)
    ).fetchone()
