import asyncio
import logging
from types import SimpleNamespace

import discord

import interaction

LOGGER = logging.getLogger("test_interaction")


class FakeContext:
    """defer の成否を差し替えられる ApplicationContext の代用品。"""

    def __init__(self, error: Exception | None = None):
        self.guild_id = 100
        self.author = SimpleNamespace(id=1)
        self.error = error
        self.deferred = False

    async def defer(self):
        if self.error is not None:
            raise self.error
        self.deferred = True


def _already_acknowledged() -> discord.HTTPException:
    # 別インスタンスが先に応答した場合に Discord が返すエラー（40060）を模す
    response = SimpleNamespace(status=400, reason="Bad Request")
    return discord.HTTPException(
        response, {"code": 40060, "message": "Interaction has already been acknowledged."}
    )


def test_acquire_interaction_succeeds_when_defer_succeeds():
    ctx = FakeContext()
    assert asyncio.run(interaction.acquire_interaction(ctx, command="lend", logger=LOGGER))
    assert ctx.deferred


def test_acquire_interaction_fails_when_already_acknowledged(caplog):
    ctx = FakeContext(error=_already_acknowledged())
    with caplog.at_level(logging.ERROR, logger="test_interaction"):
        result = asyncio.run(interaction.acquire_interaction(ctx, command="lend", logger=LOGGER))
    assert result is False
    assert "別のインスタンス" in caplog.text
    assert "code=40060" in caplog.text
