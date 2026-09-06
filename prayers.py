"""
prayers.py — islomapi.uz orqali kunlik namoz vaqtlarini olish, kunlik keshlash
va foydalanuvchiga chiroyli formatda taqdim etish.

MUHIM ARXITEKTOR IZOHI (e'tiborsiz qoldirmaslik kerak):
islomapi.uz uchun rasmiy, barqaror JSON-sxema hujjati ochiq manbada topilmadi —
faqat endpoint va so'rov parametrlari (region, month, day) hujjatlashtirilgan.
Shu sababli `_extract_time()` javobdagi kalitlarni bir nechta mumkin bo'lgan
variant bo'yicha moslashuvchan qidiradi (CANDIDATE_KEYS lug'ati).
PRODUCTIONga chiqarishdan oldin bitta real so'rovni (masalan brauzerda yoki
`curl "https://islomapi.uz/api/present/day?region=Toshkent"`) qo'lda tekshirib,
agar kalit nomlari mos kelmasa — CANDIDATE_KEYS lug'atiga haqiqiy nomlarni
qo'shib qo'yish kerak. Bu joyni sinovdan o'tkazmasdan production'ga chiqarish
— bu kodning yagona "noaniq" qismi ekanligini alohida ta'kidlayman.
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import aiohttp

import config

logger = logging.getLogger(__name__)

TASHKENT_TZ = ZoneInfo(config.TIMEZONE)

# Har bir kanonik namoz vaqti uchun API javobida uchrashi mumkin bo'lgan
# kalit nomi variantlari (solishtirishda hammasi lowercase qilinadi).
CANDIDATE_KEYS: dict = {
    "tong": ["tong", "saharlik", "tong_saharlik", "imsak", "fajr_start"],
    "bomdod": ["bomdod", "fajr", "bomdod_vaqti"],
    "quyosh": ["quyosh", "quyosh_chiqishi", "sunrise"],
    "peshin": ["peshin", "dhuhr", "zuhr"],
    "asr": ["asr"],
    "shom": ["shom", "iftorlik", "sunset", "magrib", "maghrib", "shom_iftorlik"],
    "xufton": ["xufton", "isha"],
}

# Kesh: {(region, "YYYY-MM-DD"): {"tong": "05:32", "bomdod": "06:15", ...}}
_cache: dict = {}
_cache_lock = asyncio.Lock()
# Har bir region uchun alohida lock — bir xil regionga bir vaqtda ko'p
# coroutine murojaat qilganda API'ga takroriy so'rov ketmasligi uchun
# (thundering herd muammosining oldini olish).
_region_locks: dict = {}


def _today_str() -> str:
    return datetime.now(TASHKENT_TZ).strftime("%Y-%m-%d")


def _get_region_lock(region: str) -> asyncio.Lock:
    if region not in _region_locks:
        _region_locks[region] = asyncio.Lock()
    return _region_locks[region]


def _unwrap_payload(raw: dict) -> dict:
    """Ba'zi API'lar natijani {"data": {...}} kabi wrapper ichida qaytarishi mumkin."""
    for wrapper_key in ("data", "result", "response"):
        value = raw.get(wrapper_key)
        if isinstance(value, dict):
            # Aladhan API'si namoz vaqtlarini "timings" ichida beradi
            if "timings" in value and isinstance(value["timings"], dict):
                return value["timings"]
            return value
    return raw


def _extract_time(payload_lower: dict, canonical_key: str) -> Optional[str]:
    for candidate in CANDIDATE_KEYS[canonical_key]:
        value = payload_lower.get(candidate)
        if value:
            return str(value).strip()
    return None


def _parse_response(raw: dict) -> dict:
    payload = _unwrap_payload(raw)
    payload_lower = {str(k).strip().lower(): v for k, v in payload.items()}
    result = {}
    for canonical_key in CANDIDATE_KEYS:
        value = _extract_time(payload_lower, canonical_key)
        if value:
            result[canonical_key] = value
    return result


import re

def _adjust_time(time_str: str, minutes_offset: int) -> str:
    """Vaqtga (HH:MM) ma'lum daqiqalarni qo'shadi yoki ayiradi."""
    if not time_str: return time_str
    try:
        h, m = map(int, time_str.strip().split(':'))
        total_minutes = h * 60 + m + minutes_offset
        # Kun doirasida ushlab turish
        total_minutes = total_minutes % (24 * 60)
        return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"
    except ValueError:
        return time_str

async def _fetch_from_api(region: str) -> dict:
    """namozvaqti.uz saytidan HTML orqali namoz vaqtlarini olamiz (islom.uz bilan bir xil)"""
    slug = config.slug_by_city_name(region)
    if not slug:
        slug = "toshkent"
        
    url = f"https://namozvaqti.uz/shahar/{slug}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    timeout = aiohttp.ClientTimeout(total=config.API_REQUEST_TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, headers=headers) as resp:
            resp.raise_for_status()
            html = await resp.text()

    parsed = {}
    
    # HTML dan id orqali vaqtlarni ajratib olamiz
    patterns = {
        "bomdod": r'id="bomdod">(\d{2}:\d{2})</p>',
        "quyosh": r'id="quyosh">(\d{2}:\d{2})</p>',
        "peshin": r'id="peshin">(\d{2}:\d{2})</p>',
        "asr": r'id="asr">(\d{2}:\d{2})</p>',
        "shom": r'id="shom">(\d{2}:\d{2})</p>',
        "xufton": r'id="hufton">(\d{2}:\d{2})</p>',
    }
    
    for k, pattern in patterns.items():
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            parsed[k] = match.group(1)
            
    # Tong va bomdod bir xil vaqtni bildiradi
    if "bomdod" in parsed:
        parsed["tong"] = parsed["bomdod"]

    missing = [k for k in config.TRIGGER_PRAYERS if k not in parsed]
    if missing:
        logger.warning("region=%s uchun quyidagi vaqtlar API javobida topilmadi: %s", region, missing)

    return parsed


async def get_today_times(region: str) -> Optional[dict]:
    """
    Berilgan region uchun bugungi namoz vaqtlarini qaytaradi.
    Natija kunlik keshlanadi — bitta kun ichida bir regionga faqat bitta
    tashqi HTTP so'rov yuboriladi, qolgan barcha chaqiruvlar keshdan o'qiydi.
    """
    cache_key = (region, _today_str())

    async with _cache_lock:
        cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    lock = _get_region_lock(region)
    async with lock:
        # Lock ichida qayta tekshiramiz: navbatda kutayotgan boshqa coroutine
        # allaqachon fetch qilib, keshni to'ldirgan bo'lishi mumkin.
        async with _cache_lock:
            cached = _cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            parsed = await _fetch_from_api(region)
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.error("islomapi.uz'dan ma'lumot olishda tarmoq xatoligi (region=%s): %s", region, exc)
            return None

        if not parsed:
            return None

        async with _cache_lock:
            # Eski kunlarga oid keshni tozalaymiz (xotira sizib ketmasligi uchun).
            stale_keys = [k for k in _cache if k[1] != _today_str()]
            for k in stale_keys:
                del _cache[k]
            _cache[cache_key] = parsed

        return parsed


WEEKDAYS_UZ = {
    0: "Dushanba",
    1: "Seshanba",
    2: "Chorshanba",
    3: "Payshanba",
    4: "Juma",
    5: "Shanba",
    6: "Yakshanba"
}

def format_full_schedule(region: str, times: dict, *, bomdod_notice: bool = False) -> str:
    """Kanal/guruh va shaxsiy chatlar uchun to'liq kunlik jadval matni (HTML)."""
    now = datetime.now(TASHKENT_TZ)
    date_str = now.strftime("%d.%m.%Y")
    weekday_str = WEEKDAYS_UZ[now.weekday()]
    
    lines = [
        f"🕌 <b>{region}</b> — bugungi namoz vaqtlari", 
        f"📅 Sana: <b>{date_str}</b>, <i>{weekday_str}</i>",
        ""
    ]
    
    for key in config.FULL_SCHEDULE_ORDER:
        value = times.get(key)
        if not value:
            continue
        display = config.PRAYER_DISPLAY_NAMES[key]
        lines.append(f"🕐 {display}: <b>{value}</b>")
        
    if bomdod_notice:
        lines.append("")
        lines.append("🔔 <i>Bomdod namozi vaqti kirdi.</i>")
        
    # Toshkent vaqtiga nisbatan farqlar
    lines.append("")
    lines.append("➖" * 12)
    lines.append("🌍 <i>Toshkent vaqtiga nisbatan farqlar (daqiqa):</i>")
    lines.append("Andijon: -13 | Namangan: -10 | Farg'ona: -10")
    lines.append("Guliston: +2 | Jizzax: +6 | Samarqand: +9")
    lines.append("Termiz: +12 | Navoiy: +15 | Buxoro: +18")
    lines.append("Qarshi: +18 | Urganch: +36 | Xiva: +37")
    lines.append("Nukus: +40")
    
    return "\n".join(lines)


def format_reminder(region: str, prayer_key: str, time_str: str) -> str:
    """Shaxsiy chatga kun davomidagi bitta namoz vaqti uchun qisqa eslatma (HTML)."""
    display = config.PRAYER_DISPLAY_NAMES.get(prayer_key, prayer_key.title())
    
    if prayer_key == "quyosh":
        return f"🌅 Quyosh chiqdi — <b>{time_str}</b>\n⚠️ <i>Bomdod namozi vaqti chiqdi!</i>\n📍 {region}"
        
    return f"🔔 <b>{display}</b> namozi vaqti kirdi — <b>{time_str}</b>\n📍 {region}"
