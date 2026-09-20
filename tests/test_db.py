import sqlite3

import db


def test_connect_creates_transactions_table(tmp_path):
    db_path = tmp_path / "nested" / "kaikei.db"
    connection = db.connect(str(db_path))
    try:
        assert db_path.exists()
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='transactions'"
        ).fetchall()
        assert len(rows) == 1
    finally:
        connection.close()


def test_init_db_is_idempotent():
    connection = sqlite3.connect(":memory:")
    db.init_db(connection)
    db.init_db(connection)  # 2回目もエラーにならないこと
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='transactions'"
    ).fetchall()
    assert len(rows) == 1
    connection.close()
