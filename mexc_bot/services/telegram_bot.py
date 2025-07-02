"""
Простой Telegram‑бот: уведомления о сделке + два slash‑command:
    /stats – общая статистика
    /last  – последняя сделка
"""

import os
from dotenv import load_dotenv
from loguru import logger
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from core.db import stats as db_stats, Session, Trade

load_dotenv()
TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_ID = int(os.getenv("TG_CHAT_ID"))


class TgNotifier:
    def __init__(self):
        self.app = ApplicationBuilder().token(TG_TOKEN).build()
        self.app.add_handler(CommandHandler("stats", self.cmd_stats))
        self.app.add_handler(CommandHandler("last", self.cmd_last))

    async def start(self):
        await self.app.initialize()
        await self.app.start()
        logger.info("Telegram bot started")

    async def stop(self):
        await self.app.stop()

    # -------------- commands -------------- #
    async def cmd_stats(self, upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
        s = db_stats()
        text = (
            f"📊 *Общая статистика*\n"
            f"Трейдов: {s['trades']}\n"
            f"Win‑rate: {s['win_rate']:.1f}%\n"
            f"PNL: {s['pnl']:.2f}"
        )
        await ctx.bot.send_message(
            upd.effective_chat.id, text, parse_mode=ParseMode.MARKDOWN
        )

    async def cmd_last(self, upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
        with Session() as sess:
            t: Trade | None = (
                sess.query(Trade).order_by(Trade.id.desc()).first()
            )
        if not t:
            await ctx.bot.send_message(
                upd.effective_chat.id, "Сделок пока нет."
            )
            return
        text = (
            f"{t.entry_date:%Y-%m-%d %H:%M}  →  {t.exit_date:%Y-%m-%d %H:%M}\n"
            f"{t.position} {t.qty:.4f}\n"
            f"EP: {t.entry_price:.2f}  |  XP: {t.exit_price:.2f}\n"
            f"PNL: {t.pnl:.2f} ({t.reason})"
        )
        await ctx.bot.send_message(upd.effective_chat.id, text)

    # -------------- notifications -------------- #
    async def notify(self, text: str):
        try:
            await self.app.bot.send_message(
                TG_CHAT_ID, text, parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error("TG notify failed: %s", e)
