"""
database.py — Firebase Realtime Database bilan ishlash uchun qatlam.

MUHIM ARXITEKTURA IZOHI:
firebase-admin SDK sinxron (blocking) tarmoq chaqiruvlaridan foydalanadi.
Aiogram esa to'liq asinxron (asyncio) muhitda ishlaydi. Agar firebase-admin
chaqiruvlarini to'g'ridan-to'g'ri `await` qilinadigan funksiyalar ichida
sinxron chaqirsak, butun event loop bloklanib qoladi va bot boshqa
foydalanuvchilarga bir vaqtning o'zida javob bera olmay qoladi.
Shu sababli barcha DB operatsiyalari `asyncio.to_thread()` orqali alohida
thread'da bajariladi.
"""
import asyncio
import logging
from typing import Optional

import firebase_admin
from firebase_admin import credentials, db

import config

logger = logging.getLogger(__name__)

_app: Optional[firebase_admin.App] = None


def init_app() -> None:
    """Firebase Admin ilovasini bir marta ishga tushiradi. bot.py startida chaqiriladi."""
    global _app
    if _app is not None:
        logger.warning("Firebase ilovasi allaqachon ishga tushirilgan, qayta ishga tushirish o'tkazib yuborildi.")
        return

    cred_dict = config.load_firebase_credentials()
    cred = credentials.Certificate(cred_dict)
    _app = firebase_admin.initialize_app(
        cred, {"databaseURL": config.FIREBASE_DATABASE_URL}
    )
    logger.info("Firebase ilovasi muvaffaqiyatli ishga tushirildi.")


def _ensure_initialized() -> None:
    if _app is None:
        raise RuntimeError(
            "Firebase ilovasi ishga tushirilmagan. Avval database.init_app() ni chaqiring."
        )


# ==========================================================================
# Ichki sinxron funksiyalar (faqat asyncio.to_thread orqali chaqiriladi)
# ==========================================================================

def _sync_set_user(chat_id: int, region: str, name: str) -> None:
    db.reference(f"/users/{chat_id}").set(
        {"region": region, "type": "private", "name": name}
    )


def _sync_update_user_region(chat_id: int, region: str) -> None:
    db.reference(f"/users/{chat_id}").update({"region": region})


def _sync_get_user(chat_id: int) -> Optional[dict]:
    return db.reference(f"/users/{chat_id}").get()


def _sync_remove_user(chat_id: int) -> None:
    db.reference(f"/users/{chat_id}").delete()


def _sync_get_all_users() -> dict:
    return db.reference("/users").get() or {}


def _sync_set_chat(chat_id: int, region: Optional[str], chat_type: str, title: str) -> None:
    db.reference(f"/chats/{chat_id}").set(
        {"region": region, "type": chat_type, "title": title}
    )


def _sync_update_chat_region(chat_id: int, region: str) -> None:
    db.reference(f"/chats/{chat_id}").update({"region": region})


def _sync_get_chat(chat_id: int) -> Optional[dict]:
    return db.reference(f"/chats/{chat_id}").get()


def _sync_remove_chat(chat_id: int) -> None:
    db.reference(f"/chats/{chat_id}").delete()


def _sync_get_all_chats() -> dict:
    return db.reference("/chats").get() or {}


# ==========================================================================
# Tashqi asinxron API — handlers.py va scheduler.py shularni chaqiradi
# ==========================================================================

async def add_user(chat_id: int, region: str, name: str) -> None:
    _ensure_initialized()
    await asyncio.to_thread(_sync_set_user, chat_id, region, name)


async def update_user_region(chat_id: int, region: str) -> None:
    _ensure_initialized()
    await asyncio.to_thread(_sync_update_user_region, chat_id, region)


async def get_user(chat_id: int) -> Optional[dict]:
    _ensure_initialized()
    return await asyncio.to_thread(_sync_get_user, chat_id)


async def remove_user(chat_id: int) -> None:
    _ensure_initialized()
    await asyncio.to_thread(_sync_remove_user, chat_id)


async def get_all_users() -> dict:
    _ensure_initialized()
    return await asyncio.to_thread(_sync_get_all_users)


async def add_chat(chat_id: int, region: Optional[str], chat_type: str, title: str) -> None:
    _ensure_initialized()
    await asyncio.to_thread(_sync_set_chat, chat_id, region, chat_type, title)


async def update_chat_region(chat_id: int, region: str) -> None:
    _ensure_initialized()
    await asyncio.to_thread(_sync_update_chat_region, chat_id, region)


async def get_chat(chat_id: int) -> Optional[dict]:
    _ensure_initialized()
    return await asyncio.to_thread(_sync_get_chat, chat_id)


async def remove_chat(chat_id: int) -> None:
    _ensure_initialized()
    await asyncio.to_thread(_sync_remove_chat, chat_id)


async def get_all_chats() -> dict:
    _ensure_initialized()
    return await asyncio.to_thread(_sync_get_all_chats)
