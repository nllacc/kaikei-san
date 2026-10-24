"""Discordのインタラクション（スラッシュコマンド）応答に関する補助関数。"""

import logging

import discord


async def acquire_interaction(
    ctx: discord.ApplicationContext, *, command: str, logger: logging.Logger
) -> bool:
    """コマンド処理の前にインタラクションの応答権を確保する（defer）。

    同じTOKENのbotが複数稼働していると、Discordは同じインタラクションを全インスタンスへ配送する。
    応答できるのは最初に確保した1インスタンスのみのため、確保に失敗した場合は
    別インスタンスが処理済みとみなし、DBへの書き込み等を行わずに処理を中断させる。
    確保できた場合は True、できなかった場合は False を返す。
    """
    try:
        await ctx.defer()
    except discord.HTTPException as error:
        logger.error(
            "command=%s guild_id=%s user_id=%s 応答の確保に失敗したため処理を中断しました。"
            "同じTOKENで別のインスタンスが稼働している可能性があります (status=%s code=%s)",
            command,
            ctx.guild_id,
            ctx.author.id,
            error.status,
            error.code,
        )
        return False
    return True
