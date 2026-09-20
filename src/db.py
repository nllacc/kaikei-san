"""SQLiteデータベースの接続・初期化を担うモジュール。"""

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    creditor_id INTEGER NOT NULL,
    debtor_id INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    memo TEXT NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
"""


def init_db(conn: sqlite3.Connection) -> None:
    """接続済みのDBにtransactionsテーブルを作成する（既存なら何もしない）。"""
    conn.execute(SCHEMA)
    conn.commit()


def connect(db_path: str) -> sqlite3.Connection:
    """SQLiteファイルへ接続し、スキーマを初期化して返す。"""
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn
