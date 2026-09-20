import datetime

import pytest

import repository

GUILD = 100
ALICE = 1
BOB = 2
CAROL = 3


def test_add_lend_records_alice_as_creditor(conn):
    tx = repository.add_lend(
        conn, guild_id=GUILD, lender_id=ALICE, borrower_id=BOB, amount=1000, memo="ラーメン代"
    )
    assert tx.creditor_id == ALICE
    assert tx.debtor_id == BOB
    assert tx.amount == 1000
    assert tx.created_by == ALICE


def test_add_borrow_records_alice_as_debtor(conn):
    tx = repository.add_borrow(
        conn, guild_id=GUILD, borrower_id=ALICE, lender_id=BOB, amount=1000, memo="ラーメン代"
    )
    assert tx.creditor_id == BOB
    assert tx.debtor_id == ALICE
    assert tx.created_by == ALICE


def test_add_transaction_rejects_self_transaction(conn):
    with pytest.raises(repository.InvalidTransactionError):
        repository.add_transaction(
            conn,
            guild_id=GUILD,
            creditor_id=ALICE,
            debtor_id=ALICE,
            amount=1000,
            memo="不正",
            created_by=ALICE,
        )


@pytest.mark.parametrize("amount", [0, -100])
def test_add_transaction_rejects_non_positive_amount(conn, amount):
    with pytest.raises(repository.InvalidTransactionError):
        repository.add_transaction(
            conn,
            guild_id=GUILD,
            creditor_id=ALICE,
            debtor_id=BOB,
            amount=amount,
            memo="不正",
            created_by=ALICE,
        )


def test_get_summary_nets_multiple_transactions_with_same_counterparty(conn):
    repository.add_lend(conn, guild_id=GUILD, lender_id=ALICE, borrower_id=BOB, amount=3000, memo="a")
    repository.add_borrow(conn, guild_id=GUILD, borrower_id=ALICE, lender_id=BOB, amount=1000, memo="b")

    entries = repository.get_summary(conn, guild_id=GUILD, user_id=ALICE)

    assert entries == [repository.BalanceEntry(counterparty_id=BOB, net_amount=2000)]


def test_get_summary_reports_negative_when_user_is_net_borrower(conn):
    repository.add_borrow(conn, guild_id=GUILD, borrower_id=ALICE, lender_id=BOB, amount=1500, memo="a")

    entries = repository.get_summary(conn, guild_id=GUILD, user_id=ALICE)

    assert entries == [repository.BalanceEntry(counterparty_id=BOB, net_amount=-1500)]


def test_get_summary_omits_counterparties_with_zero_net_balance(conn):
    repository.add_lend(conn, guild_id=GUILD, lender_id=ALICE, borrower_id=BOB, amount=1000, memo="a")
    repository.add_borrow(conn, guild_id=GUILD, borrower_id=ALICE, lender_id=BOB, amount=1000, memo="b")

    entries = repository.get_summary(conn, guild_id=GUILD, user_id=ALICE)

    assert entries == []


def test_get_summary_separates_multiple_counterparties(conn):
    repository.add_lend(conn, guild_id=GUILD, lender_id=ALICE, borrower_id=BOB, amount=1000, memo="a")
    repository.add_borrow(conn, guild_id=GUILD, borrower_id=ALICE, lender_id=CAROL, amount=500, memo="b")

    entries = repository.get_summary(conn, guild_id=GUILD, user_id=ALICE)

    assert entries == [
        repository.BalanceEntry(counterparty_id=BOB, net_amount=1000),
        repository.BalanceEntry(counterparty_id=CAROL, net_amount=-500),
    ]


def test_get_summary_is_scoped_to_guild(conn):
    other_guild = 999
    repository.add_lend(conn, guild_id=other_guild, lender_id=ALICE, borrower_id=BOB, amount=1000, memo="a")

    entries = repository.get_summary(conn, guild_id=GUILD, user_id=ALICE)

    assert entries == []


def test_get_user_history_returns_only_involved_transactions_in_order(conn):
    repository.add_lend(
        conn, guild_id=GUILD, lender_id=ALICE, borrower_id=BOB, amount=1000, memo="1回目", now="2026-01-01T00:00:00+00:00"
    )
    repository.add_borrow(
        conn, guild_id=GUILD, borrower_id=ALICE, lender_id=CAROL, amount=500, memo="2回目", now="2026-01-02T00:00:00+00:00"
    )
    # ALICEが関与しない記録は含まれない
    repository.add_lend(
        conn, guild_id=GUILD, lender_id=BOB, borrower_id=CAROL, amount=200, memo="無関係", now="2026-01-03T00:00:00+00:00"
    )

    history = repository.get_user_history(conn, guild_id=GUILD, user_id=ALICE)

    assert [t.memo for t in history] == ["1回目", "2回目"]


def test_get_user_history_filters_by_start_and_end_at(conn):
    repository.add_lend(
        conn, guild_id=GUILD, lender_id=ALICE, borrower_id=BOB, amount=1000, memo="範囲外(前)",
        now="2025-12-31T23:00:00+00:00",
    )
    repository.add_lend(
        conn, guild_id=GUILD, lender_id=ALICE, borrower_id=BOB, amount=1000, memo="範囲内",
        now="2026-01-15T00:00:00+00:00",
    )
    repository.add_lend(
        conn, guild_id=GUILD, lender_id=ALICE, borrower_id=BOB, amount=1000, memo="範囲外(後)",
        now="2026-02-01T00:00:00+00:00",
    )

    history = repository.get_user_history(
        conn,
        guild_id=GUILD,
        user_id=ALICE,
        start_at="2026-01-01T00:00:00+00:00",
        end_at="2026-02-01T00:00:00+00:00",
    )

    assert [t.memo for t in history] == ["範囲内"]


def test_recent_range_utc_returns_now_minus_days():
    now = datetime.datetime(2026, 1, 31, tzinfo=datetime.timezone.utc)
    start_at, end_at = repository.recent_range_utc(days=30, now=now)
    assert start_at == "2026-01-01T00:00:00+00:00"
    assert end_at is None


def test_month_range_utc_within_year():
    start_at, end_at = repository.month_range_utc(2026, 6)
    assert start_at == "2026-05-31T15:00:00+00:00"  # 2026-06-01 00:00 JST
    assert end_at == "2026-06-30T15:00:00+00:00"  # 2026-07-01 00:00 JST


def test_month_range_utc_crosses_year_boundary():
    start_at, end_at = repository.month_range_utc(2025, 12)
    assert start_at == "2025-11-30T15:00:00+00:00"  # 2025-12-01 00:00 JST
    assert end_at == "2025-12-31T15:00:00+00:00"  # 2026-01-01 00:00 JST
