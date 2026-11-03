import asyncio
import logging
import socket

import aiohttp
import discord
import pytest

import login_retry

LOGGER = logging.getLogger("test_login_retry")


class FakeLogin:
    """渡された例外を先頭から順に送出し、尽きたら成功する login の代用品。"""

    def __init__(self, errors: list[Exception]):
        self.errors = list(errors)
        self.calls = 0

    async def __call__(self, token: str) -> None:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)


def _recording_sleep(delays: list[float]):
    """待機時間を記録するだけの sleep の代用品（実際には待たない）。"""

    async def sleep(delay: float) -> None:
        delays.append(delay)

    return sleep


def test_retries_transient_errors_until_login_succeeds():
    # DNS 解決失敗（OSError の一種）と接続エラーを連続で起こしてから成功させる
    login = FakeLogin([socket.gaierror(-3, "Try again"), aiohttp.ClientError()])
    delays: list[float] = []

    asyncio.run(
        login_retry.login_with_retry(
            login, "token", logger=LOGGER, sleep=_recording_sleep(delays)
        )
    )

    assert login.calls == 3
    assert delays == [login_retry.INITIAL_RETRY_DELAY, login_retry.INITIAL_RETRY_DELAY * 2]


def test_retry_delay_is_capped_at_max_delay():
    login = FakeLogin([OSError() for _ in range(4)])
    delays: list[float] = []

    asyncio.run(
        login_retry.login_with_retry(
            login,
            "token",
            logger=LOGGER,
            initial_delay=1,
            max_delay=3,
            sleep=_recording_sleep(delays),
        )
    )

    assert delays == [1, 2, 3, 3]


def test_invalid_token_is_not_retried():
    # トークン不正は再試行しても回復しないため、そのまま送出されること
    login = FakeLogin([discord.LoginFailure("Improper token has been passed.")])

    with pytest.raises(discord.LoginFailure):
        asyncio.run(
            login_retry.login_with_retry(
                login, "token", logger=LOGGER, sleep=_recording_sleep([])
            )
        )
    assert login.calls == 1
