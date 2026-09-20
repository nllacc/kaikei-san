"""Discordへ返信するテキストを組み立てる純粋関数群。DBにもdiscord.pyにも依存しない。"""

import datetime

from repository import BalanceEntry, Transaction

JST = datetime.timezone(datetime.timedelta(hours=9))

MONTH_ALL = "all"


def format_amount(amount: int) -> str:
    return format(amount, ",")


def format_lend_confirmation(*, borrower_id: int, amount: int, memo: str) -> str:
    return f"記録しました。<@{borrower_id}> に {format_amount(amount)}円 貸しました（名目: {memo}）"


def format_borrow_confirmation(*, lender_id: int, amount: int, memo: str) -> str:
    return f"記録しました。<@{lender_id}> から {format_amount(amount)}円 借りました（名目: {memo}）"


def format_summary(entries: list[BalanceEntry]) -> str:
    """/kaikei の応答テキストを組み立てる。"""
    if not entries:
        return "貸し借りはありません"

    lines = ["あなたの貸し借り状況:"]
    for entry in entries:
        mention = f"<@{entry.counterparty_id}>"
        amount = format_amount(abs(entry.net_amount))
        if entry.net_amount > 0:
            lines.append(f"- {mention} に {amount}円 貸しています")
        else:
            lines.append(f"- {mention} から {amount}円 借りています")
    return "\n".join(lines)


def format_history_line(transaction: Transaction, *, user_id: int) -> str:
    """/history のファイル出力の1行分を組み立てる。"""
    if transaction.creditor_id == user_id:
        counterparty_id = transaction.debtor_id
        direction = "貸した"
    else:
        counterparty_id = transaction.creditor_id
        direction = "借りた"

    created_at = datetime.datetime.fromisoformat(transaction.created_at)
    timestamp = created_at.astimezone(JST).strftime("%Y-%m-%d %H:%M")
    amount = format_amount(transaction.amount)
    return f"{timestamp} | <@{counterparty_id}> | {direction} | {amount}円 | {transaction.memo}"


def format_history_file(transactions: list[Transaction], *, user_id: int) -> str:
    """/history で添付するテキストファイルの中身を組み立てる。"""
    return "\n".join(format_history_line(t, user_id=user_id) for t in transactions)


def build_month_choices(*, now: datetime.datetime | None = None, count: int = 12) -> list[str]:
    """/history の month オプション用の選択肢（新しい月順） + 末尾に MONTH_ALL を返す。"""
    reference = (now.astimezone(JST) if now is not None else datetime.datetime.now(JST)).replace(day=1)
    choices = []
    for _ in range(count):
        choices.append(f"{reference.year:04d}-{reference.month:02d}")
        reference = (reference - datetime.timedelta(days=1)).replace(day=1)
    choices.append(MONTH_ALL)
    return choices
