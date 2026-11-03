"""ログイン時の一時的なネットワーク障害を再試行で吸収する補助モジュール。

discord.py / py-cord の Client.login() は再試行を行わないため、起動時にDNS解決などが
失敗すると例外がプロセス外へ抜けて bot が終了する。ここでは一時的な障害に限り、
待機時間を指数的に伸ばしながら成功するまで再試行する。
トークン不正（LoginFailure）は再試行しても回復しないため、そのまま送出する。
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

import aiohttp
import discord

INITIAL_RETRY_DELAY = 5.0
MAX_RETRY_DELAY = 300.0

# 再試行対象とする一時的な障害（DNS解決失敗・接続失敗・Discord側の一時的なHTTPエラー）
TRANSIENT_ERRORS = (OSError, aiohttp.ClientError, discord.HTTPException)


async def login_with_retry(
    login: Callable[[str], Awaitable[None]],
    token: str,
    *,
    logger: logging.Logger,
    initial_delay: float = INITIAL_RETRY_DELAY,
    max_delay: float = MAX_RETRY_DELAY,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """login が成功するまで再試行する。待機時間は倍々に伸ばし、max_delay で頭打ちにする。"""
    delay = initial_delay
    while True:
        try:
            await login(token)
            return
        except TRANSIENT_ERRORS as error:
            logger.warning("ログインに失敗しました。%.0f秒後に再試行します: %s", delay, error)
            await sleep(delay)
            delay = min(delay * 2, max_delay)
