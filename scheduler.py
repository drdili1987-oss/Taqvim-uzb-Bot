"""
scheduler.py — APScheduler yordamida har daqiqada namoz vaqtlarini tekshirib,
guruh/kanallarga (faqat Bomdodda, to'liq jadval) va shaxsiy foydalanuvchilarga
(har namoz vaqtida, alohida xabar) yuboruvchi modul.
"""
import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import config
import database
import prayers

logger = logging.getLogger(__name__)

TASHKENT_TZ = ZoneInfo(config.TIMEZONE)

# Bir vaqtning o'zida nechta xabar parallel yuborilishini cheklaydi
# (Telegram flood-limitiga tushib qolmaslik uchun).
_send_semaphore = asyncio.Semaphore(config.SEND_CONCURRENCY_LIMIT)


async def _safe_send(bot: Bot, chat_id: int, text: str, *, is_chat_entity: bool) -> None:
    """
    Xabarni xavfsiz yuboradi. Agar bot bloklangan yoki chatdan chiqarilgan
    bo'lsa — tegishli Firebase yozuvi avtomatik o'chiriladi (self-healing),
    aks holda bot keyingi safar ham shu "o'lik" chatga xabar yuborishga urinib,
    resurs sarflayveradi.
    """
    async with _send_semaphore:
        try:
            await bot.send_message(chat_id, text)
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 1)
            try:
                await bot.send_message(chat_id, text)
            except Exception as retry_exc:
                logger.error("Qayta urinishda ham xabar yuborilmadi chat_id=%s: %s", chat_id, retry_exc)
        except (TelegramForbiddenError, TelegramBadRequest) as exc:
            logger.warning(
                "chat_id=%s ga xabar yuborib bo'lmadi (%s). Yozuv Firebase'dan o'chirilmoqda.",
                chat_id, exc,
            )
            try:
                if is_chat_entity:
                    await database.remove_chat(chat_id)
                else:
                    await database.remove_user(chat_id)
            except Exception as db_exc:
                logger.error("DB yozuvini o'chirishda xatolik chat_id=%s: %s", chat_id, db_exc)
        except Exception as exc:  # noqa: BLE001 — kutilmagan xatoni jim yutib yubormaslik uchun log qilinadi
            logger.exception("Kutilmagan xato chat_id=%s uchun xabar yuborishda: %s", chat_id, exc)


def _group_by_region(entities: dict) -> dict:
    """{"123": {"region": "Toshkent", ...}, ...} -> {"Toshkent": [123, ...]}"""
    grouped: dict = {}
    for chat_id_str, info in entities.items():
        if not isinstance(info, dict):
            continue
        region = info.get("region")
        if not region:
            continue
        try:
            chat_id = int(chat_id_str)
        except (TypeError, ValueError):
            continue
        grouped.setdefault(region, []).append(chat_id)
    return grouped


async def _check_and_notify(bot: Bot) -> None:
    now = datetime.now(TASHKENT_TZ)
    current_hm = now.strftime("%H:%M")

    try:
        all_users = await database.get_all_users()
        all_chats = await database.get_all_chats()
    except Exception as exc:
        logger.error("Firebase'dan foydalanuvchi/chat ro'yxatini olishda xatolik: %s", exc)
        return

    users_by_region = _group_by_region(all_users)
    chats_by_region = _group_by_region(all_chats)

    all_regions = set(users_by_region) | set(chats_by_region)
    if not all_regions:
        return

    for region in all_regions:
        times = await prayers.get_today_times(region)
        if not times:
            continue

        # Ushbu daqiqada kirgan namoz vaqtini aniqlaymiz (bir daqiqada faqat
        # bittasi mos kelishi mumkin, chunki vaqtlar bir xil bo'lmaydi).
        matched_prayer = None
        for prayer_key in config.TRIGGER_PRAYERS:
            if times.get(prayer_key) == current_hm:
                matched_prayer = prayer_key
                break

        if matched_prayer is None:
            continue

        user_ids = users_by_region.get(region, [])
        chat_ids = chats_by_region.get(region, [])

        if matched_prayer == "bomdod":
            # Ertalab Bomdod vaqtida hammaga (shaxsiy va guruhlarga) to'liq jadval
            full_text = prayers.format_full_schedule(region, times, bomdod_notice=True)
            tasks = [_safe_send(bot, uid, full_text, is_chat_entity=False) for uid in user_ids]
            tasks += [_safe_send(bot, cid, full_text, is_chat_entity=True) for cid in chat_ids]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
        else:
            # Qolgan namoz vaqtlarida faqat aynan o'sha namozning qisqa eslatmasi
            reminder_text = prayers.format_reminder(region, matched_prayer, current_hm)
            tasks = [_safe_send(bot, uid, reminder_text, is_chat_entity=False) for uid in user_ids]
            tasks += [_safe_send(bot, cid, reminder_text, is_chat_entity=True) for cid in chat_ids]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=TASHKENT_TZ)
    scheduler.add_job(
        _check_and_notify,
        trigger=CronTrigger(second=0),  # har daqiqaning 0-soniyasida ishga tushadi
        args=(bot,),
        id="prayer_notifier",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=30,
    )
    return scheduler
