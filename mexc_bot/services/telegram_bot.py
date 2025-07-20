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
# Import database helpers from the package to avoid relying on ``PYTHONPATH``
from mexc_bot.core.db import stats as db_stats, Session, Trade, get_today_pnl
from datetime import datetime

load_dotenv()
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")
if TG_CHAT_ID is not None:
    try:
        TG_CHAT_ID = int(TG_CHAT_ID)
    except ValueError:
        TG_CHAT_ID = None

bot_start_time = datetime.now()
trader = None


class TgNotifier:
    def __init__(self):
        if TG_BOT_TOKEN:
            self.app = ApplicationBuilder().token(TG_BOT_TOKEN).build()
            self.app.add_handler(CommandHandler("stats", self.cmd_stats))
            self.app.add_handler(CommandHandler("last", self.cmd_last))
            self.app.add_handler(CommandHandler("pnl_today", self.cmd_pnl_today))
            self.app.add_handler(CommandHandler("health", self.cmd_health))
        else:
            self.app = None

    async def start(self):
        if self.app is None:
            logger.info("Telegram bot disabled")
            return
        await self.app.initialize()
        await self.app.start()
        logger.info("Telegram bot started")

    async def stop(self):
        if self.app:
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
            upd.effective_chat.id,
            text,
            parse_mode=ParseMode.MARKDOWN,
        )

    async def cmd_last(self, upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
        with Session() as sess:
            t: Trade | None = sess.query(Trade).order_by(Trade.id.desc()).first()
        if not t:
            await ctx.bot.send_message(upd.effective_chat.id, "Сделок пока нет.")
            return
        text = (
            f"{t.entry_date:%Y-%m-%d %H:%M}  →  {t.exit_date:%Y-%m-%d %H:%M}\n"
            f"{t.position} {t.qty:.4f}\n"
            f"EP: {t.entry_price:.2f}  |  XP: {t.exit_price:.2f}\n"
            f"PNL: {t.pnl:.2f} ({t.reason})"
        )
        await ctx.bot.send_message(upd.effective_chat.id, text)

    async def cmd_pnl_today(self, upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
        pnl = get_today_pnl()
        await ctx.bot.send_message(
            upd.effective_chat.id,
            f"\U0001f4ca \u041f\u0440\u0438\u0431\u044b\u043b\u044c \u0437\u0430 \u0441\u0435\u0433\u043e\u0434\u043d\u044f: {pnl:.2f} USDT",
        )

    async def cmd_health(self, upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
        uptime = datetime.now() - bot_start_time
        bal = trader.balance if trader is not None else 0.0
        await ctx.bot.send_message(
            upd.effective_chat.id,
            f"\U0001f916 \u0410\u043f\u0442\u0430\u0439\u043c: {uptime}\n\U0001f4b0 \u0411\u0430\u043b\u0430\u043d\u0441: {bal:.2f} USDT",
        )

    # -------------- notifications -------------- #
    async def notify(self, text: str):
        if not self.app or TG_CHAT_ID is None:
            return
        try:
            await self.app.bot.send_message(
                TG_CHAT_ID,
                text,
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            logger.error("TG notify failed: %s", e)
