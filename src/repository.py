"""貸し借り記録（transactions）に対するDBアクセスをカプセル化するモジュール。"""

import datetime
import sqlite3
from dataclasses import dataclass


class InvalidTransactionError(ValueError):
    """貸し借り記録として不正な入力を表す例外。"""


@dataclass(frozen=True)
class Transaction:
    id: int
    guild_id: int
    creditor_id: int
    debtor_id: int
    amount: int
    memo: str
    created_by: int
    created_at: str


@dataclass(frozen=True)
class BalanceEntry:
    """あるユーザーから見た、特定の相手との差引残高。

    net_amount が正なら相手に貸している、負なら相手から借りている。
    """

    counterparty_id: int
    net_amount: int


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def add_transaction(
    conn: sqlite3.Connection,
    *,
    guild_id: int,
    creditor_id: int,
    debtor_id: int,
    amount: int,
    memo: str,
    created_by: int,
    now: str | None = None,
) -> Transaction:
    """貸し借り記録を1件追加する。

    creditor_id: 貸した人（お金を受け取る権利がある人）
    debtor_id: 借りた人（お金を返す義務がある人）
    """
    if creditor_id == debtor_id:
        raise InvalidTransactionError("creditor_id と debtor_id は異なるユーザーである必要があります")
    if amount <= 0:
        raise InvalidTransactionError("amount は正の整数である必要があります")

    created_at = now if now is not None else _now_iso()
    cursor = conn.execute(
        """
        INSERT INTO transactions
            (guild_id, creditor_id, debtor_id, amount, memo, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (guild_id, creditor_id, debtor_id, amount, memo, created_by, created_at),
    )
    conn.commit()
    return Transaction(
        id=cursor.lastrowid,
        guild_id=guild_id,
        creditor_id=creditor_id,
        debtor_id=debtor_id,
        amount=amount,
        memo=memo,
        created_by=created_by,
        created_at=created_at,
    )


def add_lend(
    conn: sqlite3.Connection,
    *,
    guild_id: int,
    lender_id: int,
    borrower_id: int,
    amount: int,
    memo: str,
    now: str | None = None,
) -> Transaction:
    """「貸した」記録を追加する（/lend コマンド用）。"""
    return add_transaction(
        conn,
        guild_id=guild_id,
        creditor_id=lender_id,
        debtor_id=borrower_id,
        amount=amount,
        memo=memo,
        created_by=lender_id,
        now=now,
    )


def add_borrow(
    conn: sqlite3.Connection,
    *,
    guild_id: int,
    borrower_id: int,
    lender_id: int,
    amount: int,
    memo: str,
    now: str | None = None,
) -> Transaction:
    """「借りた」記録を追加する（/borrow コマンド用）。"""
    return add_transaction(
        conn,
        guild_id=guild_id,
        creditor_id=lender_id,
        debtor_id=borrower_id,
        amount=amount,
        memo=memo,
        created_by=borrower_id,
        now=now,
    )


def get_summary(conn: sqlite3.Connection, *, guild_id: int, user_id: int) -> list[BalanceEntry]:
    """指定ユーザー視点の、相手ごとの差引残高一覧を返す（残高0の相手は含まない）。"""
    rows = conn.execute(
        """
        SELECT counterparty_id, SUM(signed_amount) AS net_amount FROM (
            SELECT debtor_id AS counterparty_id, amount AS signed_amount
            FROM transactions
            WHERE guild_id = :guild_id AND creditor_id = :user_id
            UNION ALL
            SELECT creditor_id AS counterparty_id, -amount AS signed_amount
            FROM transactions
            WHERE guild_id = :guild_id AND debtor_id = :user_id
        )
        GROUP BY counterparty_id
        HAVING net_amount != 0
        ORDER BY counterparty_id
        """,
        {"guild_id": guild_id, "user_id": user_id},
    ).fetchall()
    return [
        BalanceEntry(counterparty_id=row["counterparty_id"], net_amount=row["net_amount"])
        for row in rows
    ]


def get_user_history(
    conn: sqlite3.Connection,
    *,
    guild_id: int,
    user_id: int,
    start_at: str | None = None,
    end_at: str | None = None,
) -> list[Transaction]:
    """指定ユーザーが関与した記録を日時昇順で返す（/history コマンド用）。

    start_at/end_at はUTC ISO文字列。start_at は以上、end_at は未満で絞り込む。
    どちらも省略した場合は全件を返す。
    """
    conditions = ["guild_id = :guild_id", "(creditor_id = :user_id OR debtor_id = :user_id)"]
    params: dict[str, int | str] = {"guild_id": guild_id, "user_id": user_id}
    if start_at is not None:
        conditions.append("created_at >= :start_at")
        params["start_at"] = start_at
    if end_at is not None:
        conditions.append("created_at < :end_at")
        params["end_at"] = end_at

    rows = conn.execute(
        f"""
        SELECT * FROM transactions
        WHERE {' AND '.join(conditions)}
        ORDER BY created_at ASC, id ASC
        """,
        params,
    ).fetchall()
    return [Transaction(**dict(row)) for row in rows]


def recent_range_utc(
    *, days: int = 30, now: datetime.datetime | None = None
) -> tuple[str, None]:
    """直近days日分の範囲（UTC ISO文字列, 上限なし）を返す（/history コマンド用）。"""
    reference = now if now is not None else datetime.datetime.now(datetime.timezone.utc)
    start = reference - datetime.timedelta(days=days)
    return start.isoformat(), None


def month_range_utc(year: int, month: int) -> tuple[str, str]:
    """指定年月（JST基準のカレンダー月）をUTC ISO文字列の範囲[start, end)で返す（/history コマンド用）。"""
    jst = datetime.timezone(datetime.timedelta(hours=9))
    start_jst = datetime.datetime(year, month, 1, tzinfo=jst)
    if month == 12:
        end_jst = datetime.datetime(year + 1, 1, 1, tzinfo=jst)
    else:
        end_jst = datetime.datetime(year, month + 1, 1, tzinfo=jst)
    return (
        start_jst.astimezone(datetime.timezone.utc).isoformat(),
        end_jst.astimezone(datetime.timezone.utc).isoformat(),
    )
