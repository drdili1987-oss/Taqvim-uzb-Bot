"""
bot.py — Loyihaning kirish nuqtasi (entry point).
Bot, Dispatcher, Firebase va APScheduler'ni birlashtirib ishga tushiradi.
Render'da "Background Worker" sifatida `python bot.py` orqali ishga tushadi
(qarang: Procfile).
"""
import asyncio
import logging

# .env fayldan environment o'zgaruvchilarini yuklaydi (lokal ishlatish uchun).
# Render platformasida bu qator ahamiyatsiz — u yerda env vars dashboard orqali beriladi.
from dotenv import load_dotenv
load_dotenv()

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

import config
import database
from handlers import router
from scheduler import setup_scheduler

logger = logging.getLogger(__name__)


async def main() -> None:
    # 1) Firebase Realtime Database ulanishini ishga tushiramiz.
    database.init_app()

    # 2) Botni yaratamiz — barcha xabarlar standart HTML parse_mode bilan yuboriladi.
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)

    # 3) APScheduler'ni ishga tushiramiz — har daqiqada namoz vaqtlarini tekshiradi.
    scheduler = setup_scheduler(bot)
    scheduler.start()
    logger.info("Scheduler ishga tushdi (Asia/Tashkent, har daqiqada tekshiradi).")

    try:
        # Eski webhook (agar bo'lsa) va navbatdagi update'larni tozalab, polling'ni
        # boshlaymiz. Render Background Worker uchun long-polling eng qulay usul —
        # tashqi HTTP portga ehtiyoj qolmaydi.
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Bot polling rejimida ishga tushmoqda...")
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
