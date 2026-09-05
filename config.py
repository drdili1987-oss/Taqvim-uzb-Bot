"""
config.py — Loyihaning barcha konfiguratsiya va environment o'zgaruvchilari.
Barcha maxfiy qiymatlar (token, credential) faqat environment o'zgaruvchilaridan
o'qiladi — Render platformasida xavfsiz deploy qilish uchun shart.
"""
import os
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Bot sozlamalari
# --------------------------------------------------------------------------
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN environment o'zgaruvchisi topilmadi. "
        "Uni Render dashboard > Environment bo'limida o'rnating."
    )
    
BOT_USERNAME = "taqvim_uzb_bot"

# --------------------------------------------------------------------------
# Admin foydalanuvchilar (Telegram user_id lar vergul bilan ajratilgan)
# Misol: ADMIN_IDS=156664,123456
# --------------------------------------------------------------------------
_admin_ids_raw: str = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: list[int] = [
    int(uid.strip()) for uid in _admin_ids_raw.split(",") if uid.strip().isdigit()
]
if not ADMIN_IDS:
    logger.warning("ADMIN_IDS environment o'zgaruvchisi topilmadi yoki bo'sh. Admin funksiyalari ishlamaydi.")

# --------------------------------------------------------------------------
# Firebase sozlamalari
# --------------------------------------------------------------------------
FIREBASE_DATABASE_URL: str = os.getenv("FIREBASE_DATABASE_URL", "")
if not FIREBASE_DATABASE_URL:
    raise RuntimeError("FIREBASE_DATABASE_URL environment o'zgaruvchisi topilmadi.")

# Render'da qulay bo'lishi uchun butun JSON kalitni bitta env o'zgaruvchiga solamiz.
FIREBASE_CREDENTIALS_JSON: Optional[str] = os.getenv("FIREBASE_CREDENTIALS_JSON")
# Lokal ishlash uchun fallback fayl nomi.
FIREBASE_CREDENTIALS_FILE: str = os.getenv("FIREBASE_CREDENTIALS_FILE", "firebase_key.json")


def load_firebase_credentials() -> dict:
    """
    Firebase service-account credential'larni yuklaydi.
    Ustuvorlik: 1) FIREBASE_CREDENTIALS_JSON env (Render uchun),
                2) lokal firebase_key.json fayl.
    """
    if FIREBASE_CREDENTIALS_JSON:
        try:
            return json.loads(FIREBASE_CREDENTIALS_JSON)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "FIREBASE_CREDENTIALS_JSON noto'g'ri JSON formatida. "
                "Butun service-account JSON faylining kontentini bitta qatorga "
                "(escape qilingan holda) joylashtirganingizga ishonch hosil qiling."
            ) from exc

    if os.path.isfile(FIREBASE_CREDENTIALS_FILE):
        with open(FIREBASE_CREDENTIALS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    raise RuntimeError(
        "Firebase credential topilmadi. FIREBASE_CREDENTIALS_JSON environment "
        f"o'zgaruvchisini o'rnating yoki '{FIREBASE_CREDENTIALS_FILE}' faylini "
        "loyiha papkasiga joylashtiring."
    )


# --------------------------------------------------------------------------
# Vaqt mintaqasi
# --------------------------------------------------------------------------
TIMEZONE = "Asia/Tashkent"

# --------------------------------------------------------------------------
# Namoz vaqtlari API
# --------------------------------------------------------------------------
PRAYER_API_BASE_URL = "https://api.aladhan.com/v1/timingsByCity"
API_REQUEST_TIMEOUT = 15  # soniya

# --------------------------------------------------------------------------
# Qo'llab-quvvatlanadigan shaharlar
# key   -> ichki "slug" (callback_data va lookup uchun xavfsiz, faqat lotin harflar)
# value -> API'ga yuboriladigan va foydalanuvchiga ko'rsatiladigan haqiqiy nom
# --------------------------------------------------------------------------
CITIES: dict = {
    "toshkent": "Toshkent",
    "samarqand": "Samarqand",
    "buxoro": "Buxoro",
    "andijon": "Andijon",
    "namangan": "Namangan",
    "fargona": "Farg'ona",
    "qarshi": "Qarshi",
    "termiz": "Termiz",
    "navoiy": "Navoiy",
    "urganch": "Urganch",
    "nukus": "Nukus",
    "jizzax": "Jizzax",
    "guliston": "Guliston",
    "xiva": "Xiva",
}


def city_name_by_slug(slug: str) -> Optional[str]:
    return CITIES.get(slug)


def slug_by_city_name(name: str) -> Optional[str]:
    for slug, city in CITIES.items():
        if city == name:
            return slug
    return None


# --------------------------------------------------------------------------
# Namoz vaqtlari — kanonik kalitlar va ko'rinadigan nomlar
# --------------------------------------------------------------------------
# "bomdod" — asosiy trigger: shu vaqt kirganda guruh/kanallarga TO'LIQ jadval,
# shaxsiy foydalanuvchilarga esa TO'LIQ jadval + eslatma yuboriladi.
# Qolgan 5 tasi (quyosh, peshin, asr, shom, xufton) kun davomida FAQAT
# shaxsiy chatlarga qisqa eslatma sifatida yuboriladi.
PRAYER_DISPLAY_NAMES: dict = {
    "tong": "Tong (saharlik)",
    "bomdod": "Bomdod",
    "quyosh": "Quyosh",
    "peshin": "Peshin",
    "asr": "Asr",
    "shom": "Shom (iftorlik)",
    "xufton": "Xufton",
}

# Scheduler shu ro'yxat bo'yicha "vaqt keldimi?" deb tekshiradi.
TRIGGER_PRAYERS = ["bomdod", "quyosh", "peshin", "asr", "shom", "xufton"]

# To'liq jadval chiqarilganda ko'rsatiladigan tartib (agar API "tong"ni ham
# qaytarsa, u ham jadvalga qo'shiladi).
FULL_SCHEDULE_ORDER = ["tong", "bomdod", "quyosh", "peshin", "asr", "shom", "xufton"]

# Bir vaqtning o'zida nechta chatga parallel xabar yuborilishi mumkinligi
# (Telegram flood-limitlariga tushib qolmaslik uchun cheklov).
SEND_CONCURRENCY_LIMIT = 20

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
