import datetime

import formatting
from repository import BalanceEntry, Transaction

USER = 1
BOB = 2
CAROL = 3


def test_format_summary_with_no_entries():
    assert formatting.format_summary([]) == "貸し借りはありません"


def test_format_summary_lending():
    entries = [BalanceEntry(counterparty_id=BOB, net_amount=3000)]
    result = formatting.format_summary(entries)
    assert f"<@{BOB}>" in result
    assert "3,000円" in result
    assert "貸しています" in result


def test_format_summary_borrowing():
    entries = [BalanceEntry(counterparty_id=BOB, net_amount=-1500)]
    result = formatting.format_summary(entries)
    assert "1,500円" in result
    assert "借りています" in result


def test_format_summary_lists_multiple_counterparties():
    entries = [
        BalanceEntry(counterparty_id=BOB, net_amount=1000),
        BalanceEntry(counterparty_id=CAROL, net_amount=-500),
    ]
    result = formatting.format_summary(entries)
    lines = result.splitlines()
    assert len(lines) == 3  # ヘッダー + 2件


def test_format_lend_confirmation_contains_key_facts():
    text = formatting.format_lend_confirmation(borrower_id=BOB, amount=1000, memo="ラーメン代")
    assert f"<@{BOB}>" in text
    assert "1,000円" in text
    assert "ラーメン代" in text


def test_format_borrow_confirmation_contains_key_facts():
    text = formatting.format_borrow_confirmation(lender_id=BOB, amount=1000, memo="ラーメン代")
    assert f"<@{BOB}>" in text
    assert "1,000円" in text
    assert "ラーメン代" in text


def _tx(**overrides):
    base = {
        "id": 1,
        "guild_id": 100,
        "creditor_id": USER,
        "debtor_id": BOB,
        "amount": 1000,
        "memo": "ラーメン代",
        "created_by": USER,
        "created_at": "2026-09-06T12:00:00+00:00",
    }
    base.update(overrides)
    return Transaction(**base)


def test_format_history_line_when_user_is_creditor():
    line = formatting.format_history_line(_tx(), user_id=USER)
    assert f"<@{BOB}>" in line
    assert "貸した" in line
    assert "1,000円" in line
    assert "ラーメン代" in line


def test_format_history_line_when_user_is_debtor():
    tx = _tx(creditor_id=BOB, debtor_id=USER)
    line = formatting.format_history_line(tx, user_id=USER)
    assert f"<@{BOB}>" in line
    assert "借りた" in line


def test_format_history_line_converts_timestamp_to_jst():
    tx = _tx(created_at="2026-09-06T03:00:00+00:00")
    line = formatting.format_history_line(tx, user_id=USER)
    assert "2026-09-06 12:00" in line


def test_format_history_file_joins_multiple_lines():
    transactions = [_tx(id=1, memo="1回目"), _tx(id=2, memo="2回目")]
    content = formatting.format_history_file(transactions, user_id=USER)
    lines = content.splitlines()
    assert len(lines) == 2
    assert "1回目" in lines[0]
    assert "2回目" in lines[1]


def test_build_month_choices_lists_recent_months_descending_then_all():
    now = datetime.datetime(2026, 1, 15, 3, 0, tzinfo=datetime.timezone.utc)  # JST 2026-01-15 12:00
    choices = formatting.build_month_choices(now=now, count=3)
    assert choices == ["2026-01", "2025-12", "2025-11", "all"]


def test_build_month_choices_all_is_last():
    choices = formatting.build_month_choices()
    assert choices[-1] == formatting.MONTH_ALL
