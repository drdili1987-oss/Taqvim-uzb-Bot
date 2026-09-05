"""
handlers.py — /start, /setcity, /bugun buyruqlari, inline callback'lar va
botning guruh/kanalga qo'shilishi yoki chiqarilishini kuzatuvchi router.
"""
import logging
from typing import Optional

from aiogram import Router, F, Bot
from aiogram.enums import ChatType, ChatMemberStatus
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    CallbackQuery,
    ChatMemberUpdated,
    InlineKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
import database
import prayers

logger = logging.getLogger(__name__)
router = Router(name="main")

ADMIN_STATUSES = {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}


def build_city_keyboard(scope: str) -> InlineKeyboardMarkup:
    """scope: 'user' yoki 'chat' — callback_data ichiga qo'shib yuboriladi."""
    builder = InlineKeyboardBuilder()
    for slug, name in config.CITIES.items():
        builder.button(text=name, callback_data=f"city:{scope}:{slug}")
    builder.adjust(2)
    return builder.as_markup()


async def _is_chat_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except Exception as exc:
        logger.warning("Admin tekshiruvida xatolik chat_id=%s user_id=%s: %s", chat_id, user_id, exc)
        return False
    return member.status in ADMIN_STATUSES


# ============================================================================
# /start — faqat shaxsiy chatda
# ============================================================================

@router.message(CommandStart(), F.chat.type == ChatType.PRIVATE)
async def cmd_start(message: Message) -> None:
    text = (
        "Assalomu alaykum! 🕌\n\n"
        "Men O'zbekiston shaharlari bo'yicha namoz vaqtlarini avtomatik yuboruvchi "
        "botman.\n\n"
        "Iltimos, quyidan o'z shahringizni tanlang:"
    )
    await message.answer(text, reply_markup=build_city_keyboard("user"))


# ============================================================================
# /setcity — shaxsiy chat, guruh (faqat admin), kanal
# ============================================================================

@router.message(Command("setcity"), F.chat.type == ChatType.PRIVATE)
async def cmd_setcity_private(message: Message) -> None:
    await message.answer("Shahringizni tanlang:", reply_markup=build_city_keyboard("user"))


@router.message(Command("setcity"), F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def cmd_setcity_group(message: Message, bot: Bot) -> None:
    if not await _is_chat_admin(bot, message.chat.id, message.from_user.id):
        await message.reply("⛔️ Ushbu buyruqni faqat guruh administratorlari ishlata oladi.")
        return
    await message.answer("Guruh uchun shaharni tanlang:", reply_markup=build_city_keyboard("chat"))


@router.channel_post(Command("setcity"))
async def channel_post_setcity(message: Message) -> None:
    # Kanal postlari bot uchun alohida update turi (channel_post) bo'lgani sababli,
    # oddiy .message() handleri bu yerga tushmaydi — shuning uchun alohida ro'yxatdan
    # o'tkazilgan. Kanalda amaliy jihatdan har qanday post yuboruvchi allaqachon
    # kanal administratori hisoblanadi (aks holda post joylay olmaydi).
    await message.answer("Kanal uchun shaharni tanlang:", reply_markup=build_city_keyboard("chat"))


# ============================================================================
# /bugun — joriy kun namoz vaqtlarini darhol ko'rsatish
# ============================================================================

@router.message(Command("bugun"))
async def cmd_bugun(message: Message) -> None:
    await _send_today_schedule(message)


@router.channel_post(Command("bugun"))
async def channel_post_bugun(message: Message) -> None:
    await _send_today_schedule(message)


async def _send_today_schedule(message: Message) -> None:
    chat = message.chat
    region: Optional[str] = None

    if chat.type == ChatType.PRIVATE:
        user_data = await database.get_user(chat.id)
        region = user_data.get("region") if user_data else None
    else:
        chat_data = await database.get_chat(chat.id)
        region = chat_data.get("region") if chat_data else None

    if not region:
        scope = "user" if chat.type == ChatType.PRIVATE else "chat"
        await message.answer(
            "Avval shahar tanlanishi kerak:",
            reply_markup=build_city_keyboard(scope),
        )
        return

    times = await prayers.get_today_times(region)
    if not times:
        await message.answer(
            "⚠️ Namoz vaqtlarini olishda xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring."
        )
        return

    await message.answer(prayers.format_full_schedule(region, times))


# ============================================================================
# Callback: shahar tanlash (/start va /setcity tugmalaridan keladi)
# ============================================================================

@router.callback_query(F.data.startswith("city:"))
async def callback_city_selected(callback: CallbackQuery) -> None:
    try:
        _, scope, slug = callback.data.split(":", 2)
    except ValueError:
        await callback.answer("Noto'g'ri so'rov.", show_alert=True)
        return

    city_name = config.city_name_by_slug(slug)
    if not city_name:
        await callback.answer("Bunday shahar topilmadi.", show_alert=True)
        return

    chat = callback.message.chat

    if scope == "user":
        user = callback.from_user
        existing = await database.get_user(chat.id)
        if existing:
            await database.update_user_region(chat.id, city_name)
        else:
            await database.add_user(chat.id, city_name, user.full_name)
        await callback.message.edit_text(
            f"✅ Shahringiz <b>{city_name}</b> etib belgilandi.\n"
            f"Endi har namoz vaqti kirganda sizga eslatma yuboraman."
        )

    elif scope == "chat":
        if chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            if not await _is_chat_admin(callback.bot, chat.id, callback.from_user.id):
                await callback.answer("⛔️ Faqat administrator shahar tanlay oladi.", show_alert=True)
                return
        chat_type = "channel" if chat.type == ChatType.CHANNEL else "group"
        existing = await database.get_chat(chat.id)
        if existing:
            await database.update_chat_region(chat.id, city_name)
        else:
            await database.add_chat(chat.id, city_name, chat_type, chat.title or str(chat.id))
        await callback.message.edit_text(
            f"✅ Ushbu chat uchun shahar <b>{city_name}</b> etib belgilandi.\n"
            f"Har kuni Bomdod namozi vaqtida to'liq jadval avtomatik yuboriladi."
        )
    else:
        await callback.answer("Noma'lum so'rov turi.", show_alert=True)
        return

    # Shahar tanlangach, darhol bugungi to'liq jadvalni yuborish
    times = await prayers.get_today_times(city_name)
    if times:
        await callback.message.answer(prayers.format_full_schedule(city_name, times))

    await callback.answer("Saqlandi ✅")


# ============================================================================
# Bot guruh/kanalga qo'shilishi yoki undan chiqarilishi
# ============================================================================

@router.my_chat_member(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL}))
async def on_bot_membership_changed(event: ChatMemberUpdated) -> None:
    old_status = event.old_chat_member.status
    new_status = event.new_chat_member.status

    joined_statuses = {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR}
    left_statuses = {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}

    chat = event.chat

    if old_status in left_statuses and new_status in joined_statuses:
        chat_type = "channel" if chat.type == ChatType.CHANNEL else "group"
        existing = await database.get_chat(chat.id)
        if not existing:
            await database.add_chat(chat.id, None, chat_type, chat.title or str(chat.id))
        try:
            await event.bot.send_message(
                chat.id,
                "Salom! Bu chat uchun namoz vaqtlarini yoqish uchun administrator "
                "/setcity buyrug'ini yuborishi kerak.",
            )
        except Exception as exc:
            logger.info("Xush kelibsiz xabarini yuborib bo'lmadi chat_id=%s: %s", chat.id, exc)

    elif new_status in left_statuses:
        await database.remove_chat(chat.id)
        logger.info("Bot chat_id=%s dan chiqarildi, yozuv Firebase'dan o'chirildi.", chat.id)
