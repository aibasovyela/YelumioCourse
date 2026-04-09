"""
bot.py — бот курса Yelumio AI-Креатив (aiogram 3)
+ Интеграция Google Drive & Google Sheets для автосбора ДЗ
"""

import asyncio
import io
import json
import logging
import os
from datetime import datetime, date
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
    ContentType, ReplyKeyboardMarkup, KeyboardButton,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ── Google API ────────────────────────────────────────────────────────────────
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# ══════════════════════════════════════════════════════════════════════════════
#  НАСТРОЙКИ
# ══════════════════════════════════════════════════════════════════════════════

BOT_TOKEN  = os.getenv("BOT_TOKEN", "7992712058:AAFBwAD25j1yh3PCL_ELcWiKL9XVspQW8oc")
CURATOR_ID = int(os.getenv("CURATOR_ID", "910046222"))
DB_FILE    = "students.json"
TIMEZONE   = "Asia/Almaty"

COURSE_START  = date(2026, 3, 10)
ACCESS_MONTHS = 3
CALENDLY_URL  = "https://calendly.com/aibasovyela/30min"

# ── Google API настройки ──────────────────────────────────────────────────────
# Путь к JSON-ключу сервисного аккаунта
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "service_account.json")

# ID Google Sheets таблицы (из URL: https://docs.google.com/spreadsheets/d/ЭТОТ_ID/edit)
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "ВСТАВЬ_ID_ТАБЛИЦЫ")

# ID папки Google Drive (из URL: https://drive.google.com/drive/folders/ЭТОТ_ID)
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "ВСТАВЬ_ID_ПАПКИ")

# Имя листа в таблице
SHEET_NAME = "Домашки"

# Твой Gmail — чтобы файлы на Drive принадлежали тебе, а не сервисному аккаунту
GOOGLE_DRIVE_OWNER_EMAIL = os.getenv("GOOGLE_DRIVE_OWNER_EMAIL", "aibasovyela@gmail.com")

# ══════════════════════════════════════════════════════════════════════════════
#  GOOGLE API — ИНИЦИАЛИЗАЦИЯ
# ══════════════════════════════════════════════════════════════════════════════

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]

google_creds   = None
drive_service  = None
sheets_service = None

def init_google():
    """Инициализация Google API. Вызывается при старте бота."""
    global google_creds, drive_service, sheets_service

    # Способ 1 (рекомендуется): OAuth2 refresh token — работает с обычным Gmail
    refresh_token  = os.getenv("GOOGLE_OAUTH_REFRESH_TOKEN")
    client_id      = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
    client_secret  = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")

    if refresh_token and client_id and client_secret:
        from google.oauth2.credentials import Credentials as OAuthCredentials
        google_creds = OAuthCredentials(
            token=None,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri="https://oauth2.googleapis.com/token",
            scopes=SCOPES,
        )
        drive_service  = build("drive",  "v3", credentials=google_creds)
        sheets_service = build("sheets", "v4", credentials=google_creds)
        log.info("✅ Google Drive + Sheets подключены (OAuth2)")
        return

    # Способ 2: Service Account через переменную окружения
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        import json as _json
        info = _json.loads(creds_json)
        google_creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        drive_service  = build("drive",  "v3", credentials=google_creds)
        sheets_service = build("sheets", "v4", credentials=google_creds)
        log.info("✅ Google Drive + Sheets подключены (Service Account)")
        return

    # Способ 3: Service Account из файла (локальный запуск)
    creds_path = Path(GOOGLE_CREDENTIALS_FILE)
    if creds_path.exists():
        google_creds   = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
        drive_service  = build("drive",  "v3", credentials=google_creds)
        sheets_service = build("sheets", "v4", credentials=google_creds)
        log.info("✅ Google Drive + Sheets подключены (из файла)")
        return

    log.warning(
        "⚠️  Google не настроен — интеграция отключена.\n"
        "   Задай GOOGLE_OAUTH_* переменные в Railway (см. get_token.py).",
    )


def google_enabled() -> bool:
    return drive_service is not None and sheets_service is not None

# ══════════════════════════════════════════════════════════════════════════════
#  GOOGLE DRIVE — загрузка файлов
# ══════════════════════════════════════════════════════════════════════════════

# Кеш: {student_name: folder_id}
_folder_cache: dict[str, str] = {}

def get_or_create_student_folder(student_name: str) -> str:
    """Находит или создаёт подпапку по имени ученика внутри основной папки."""
    if student_name in _folder_cache:
        return _folder_cache[student_name]

    # Ищем существующую папку
    query = (
        f"'{GOOGLE_DRIVE_FOLDER_ID}' in parents "
        f"and name = '{student_name}' "
        f"and mimeType = 'application/vnd.google-apps.folder' "
        f"and trashed = false"
    )
    results = drive_service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])

    if files:
        folder_id = files[0]["id"]
    else:
        # Создаём новую папку
        meta = {
            "name": student_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [GOOGLE_DRIVE_FOLDER_ID],
        }
        folder = drive_service.files().create(body=meta, fields="id").execute()
        folder_id = folder["id"]
        log.info("📁 Создана папка на Drive: %s", student_name)

    _folder_cache[student_name] = folder_id
    return folder_id


def upload_to_drive(student_name: str, filename: str, data: bytes, mime_type: str, module_num: int):
    """Загружает файл в папку ученика на Google Drive."""
    if not google_enabled():
        log.warning("Google не подключен — пропускаю загрузку %s", filename)
        return

    try:
        folder_id = get_or_create_student_folder(student_name)

        # Добавляем номер модуля к имени файла
        name_parts = filename.rsplit(".", 1)
        if len(name_parts) == 2:
            drive_filename = f"M{module_num}_{name_parts[0]}.{name_parts[1]}"
        else:
            drive_filename = f"M{module_num}_{filename}"

        log.info("📤 Загружаю в Drive: %s (%d байт, %s)", drive_filename, len(data), mime_type)

        media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime_type, resumable=False)
        meta  = {"name": drive_filename, "parents": [folder_id]}

        result = drive_service.files().create(body=meta, media_body=media, fields="id").execute()
        file_id = result.get("id")

        log.info("✅ Загружен в Drive: %s → %s (id: %s)", drive_filename, student_name, file_id)

    except Exception as e:
        log.error("❌ Ошибка загрузки в Drive: %s — %s", filename, e)


def save_text_to_drive(student_name: str, text: str, module_num: int):
    """Сохраняет текстовое ДЗ как .txt файл на Google Drive."""
    if not google_enabled():
        return

    filename = f"M{module_num}_текст_{datetime.now().strftime('%H%M%S')}.txt"
    data = text.encode("utf-8")
    upload_to_drive(student_name, filename, data, "text/plain", module_num)

# ══════════════════════════════════════════════════════════════════════════════
#  GOOGLE SHEETS — галочки
# ══════════════════════════════════════════════════════════════════════════════

def mark_hw_in_sheet(student_name: str, module_num: int):
    """
    Ставит галочку в Google Sheets.

    Ожидаемая структура таблицы (лист "Домашки"):
    ┌──────────────┬────────┬────────┬────────┬─── ... ──┬────────┐
    │  Имя ученика │  ДЗ 0  │  ДЗ 1  │  ДЗ 2  │   ...    │  ДЗ 7  │
    ├──────────────┼────────┼────────┼────────┼──────────┼────────┤
    │  Иван Иванов │   ✅   │        │        │          │        │
    │  Анна Петрова│        │   ✅   │        │          │        │
    └──────────────┴────────┴────────┴────────┴──────────┴────────┘

    Колонка A — имя, колонки B-I — модули 0-7.
    """
    if not google_enabled():
        return

    try:
        # Читаем колонку A (имена)
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=GOOGLE_SHEET_ID,
            range=f"{SHEET_NAME}!A:A",
        ).execute()
        names = result.get("values", [])

        # Ищем строку ученика
        row_index = None
        for i, row in enumerate(names):
            if row and row[0].strip().lower() == student_name.strip().lower():
                row_index = i + 1  # 1-based
                break

        if row_index is None:
            # Ученика нет в таблице — добавляем новую строку
            row_index = len(names) + 1
            sheets_service.spreadsheets().values().append(
                spreadsheetId=GOOGLE_SHEET_ID,
                range=f"{SHEET_NAME}!A:A",
                valueInputOption="RAW",
                body={"values": [[student_name]]},
            ).execute()
            log.info("➕ Добавлен в таблицу: %s (строка %d)", student_name, row_index)

        # Колонка для модуля: B=0, C=1, D=2, ... I=7
        col_letter = chr(ord("B") + module_num)
        cell = f"{SHEET_NAME}!{col_letter}{row_index}"

        timestamp = datetime.now().strftime("%d.%m %H:%M")

        sheets_service.spreadsheets().values().update(
            spreadsheetId=GOOGLE_SHEET_ID,
            range=cell,
            valueInputOption="RAW",
            body={"values": [[f"✅ {timestamp}"]]},
        ).execute()
        log.info("✅ Галочка в таблице: %s — М%d (%s)", student_name, module_num, cell)

    except Exception as e:
        log.error("Ошибка записи в Google Sheets: %s", e)

# ══════════════════════════════════════════════════════════════════════════════
#  БЕЛЫЙ СПИСОК
# ══════════════════════════════════════════════════════════════════════════════

ALLOWED_USERS = {
    "zhukentay", "danaaltaibaeva", "a1tayir", "best_shakyru",
    "agzamasseka", "anastassiyay", "chqrnell4", "valikhan_t", "zhanelline",
    6445420184, 345113758, 488026765, 892359261, 68050510,
    1416291091, 8438804950, 426784991, 813765273, 1289369020,
    240975601, 986286963, 945443674, 5695976461, 1934209258, 729840478, 5146480857,
}

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
#  МОДУЛИ
# ══════════════════════════════════════════════════════════════════════════════

MODULES = [
    {
        "number": 0, "title": "Модуль 0 — Введение", "emoji": "🎯",
        "hw_deadline": date(2026, 3, 13),
        "videos": [
            {"label": "Блок 1", "url": "https://youtu.be/2PN6raFuNWI"},
            {"label": "Блок 2", "url": "https://youtu.be/lJfx6dbi4So"},
            {"label": "Блок 3", "url": "https://youtu.be/UyR5XMGRBMI"},
        ],
        "materials": None,
        "text": (
            "🎯 *Модуль 0 — Введение*\n\n"
            "Знакомство с курсом, инструментами и планом.\n"
            "Смотри все блоки и готовься к старту! 🚀"
        ),
        "hw_text": (
            "📝 *ДЗ к Модулю 0*\n\n"
            "Зарегистрируйся в 2–3 AI-сервисах и сделай первый тест-запрос.\n"
            "Пришли скриншоты — дедлайн *13 марта* 🗓"
        ),
    },
    {
        "number": 1, "title": "Модуль 1 — Идея и концепция", "emoji": "💡",
        "hw_deadline": date(2026, 3, 17),
        "videos": [{"label": "Видеоурок", "url": "https://youtu.be/oeH0VmIzLcQ"}],
        "materials": "https://www.canva.com/folder/FAHDR6SvHuM",
        "text": (
            "💡 *Модуль 1 — Идея и концепция*\n\n"
            "Как рождается сильная идея для AI-контента.\n"
            "Смотри видео и изучай материалы! 💪"
        ),
        "hw_text": (
            "📝 *ДЗ к Модулю 1*\n\n"
            "Придумай концепцию для контент-проекта:\n"
            "• Тема и целевая аудитория\n"
            "• 3 идеи для первых постов\n\n"
            "Пришли текстом или файлом — дедлайн *17 марта* 🗓"
        ),
    },
    {
        "number": 2, "title": "Модуль 2 — Текст и промпты", "emoji": "✍️",
        "hw_deadline": date(2026, 3, 23),
        "videos": [
            {"label": "Блоки 1–2", "url": "https://youtu.be/c0oJAYCfjVc"},
            {"label": "Блоки 3–5", "url": "https://youtu.be/vz52r6QZ104"},
            {"label": "Блок 6",    "url": "https://youtu.be/k3eWjuYm7GI"},
        ],
        "materials": "https://www.canva.com/folder/FAHDR93073M",
        "text": (
            "✍️ *Модуль 2 — Текст и промпты*\n\n"
            "Управляем ИИ через точные запросы.\n"
            "После этого модуля получаешь именно то, что хочешь!"
        ),
        "hw_text": (
            "📝 *ДЗ к Модулю 2*\n\n"
            "Напиши 3 промпта для своей ниши + пришли результаты генерации.\n"
            "Текст + скриншоты — дедлайн *23 марта* 🗓"
        ),
    },
    {
        "number": 3, "title": "Модуль 3 — ИИ-фото", "emoji": "📸",
        "hw_deadline": date(2026, 3, 27),
        "videos": [
            {"label": "Блоки 1–3", "url": "https://youtu.be/pbG_ssLSIig"},
            {"label": "Блоки 4–7", "url": "https://youtu.be/j1wJ881YYIA"},
            {"label": "Практика 1", "url": "https://youtu.be/DHYOvwSuDTE"},
            {"label": "Практика 2", "url": "https://youtu.be/W_v9Y_oTaik"},
        ],
        "materials": "https://www.canva.com/folder/FAHDR9aQ0nE",
        "text": (
            "📸 *Модуль 3 — ИИ-фото*\n\n"
            "Фото профессионального уровня без фотографа.\n"
            "Только промпт — и результат! 🎯"
        ),
        "hw_text": (
            "📝 *ДЗ к Модулю 3*\n\n"
            "Создай 3 AI-фото: продуктовый кадр, lifestyle, атмосферная сцена.\n"
            "Пришли картинки — дедлайн *27 марта* 🗓"
        ),
    },
    {
        "number": 4, "title": "Модуль 4 — ИИ-видео", "emoji": "🎥",
        "hw_deadline": date(2026, 3, 31),
        "videos": [
            {"label": "Видеоурок", "url": "https://youtu.be/KNpSHwEQ19o"},
            {"label": "Практика",  "url": "https://youtu.be/3_14I_0hfhU"},
        ],
        "materials": "https://www.canva.com/folder/FAHDR0DkVZ0",
        "text": (
            "🎥 *Модуль 4 — ИИ-видео*\n\n"
            "Оживляем визуал и работаем с движением.\n"
            "Поехали! 🚀"
        ),
        "hw_text": (
            "📝 *ДЗ к Модулю 4*\n\n"
            "Возьми фото из М3 и оживи через I2V.\n"
            "Пришли видео — дедлайн *31 марта* 🗓"
        ),
    },
    {
        "number": 5, "title": "Модуль 5 — Звук", "emoji": "🎵",
        "hw_deadline": date(2026, 4, 3),
        "videos": [
            {"label": "Блок 1", "url": "https://youtu.be/vtwJTv0zLI0"},
            {"label": "Блок 2", "url": "https://youtu.be/JtIALmqyGBE"},
        ],
        "materials": "https://www.canva.com/folder/FAHDR2Mlg3o",
        "text": (
            "🎵 *Модуль 5 — Звук*\n\n"
            "Музыка, голос, субтитры — то, что делает креатив дорогим.\n"
            "Слушай внимательно! 🎧"
        ),
        "hw_text": (
            "📝 *ДЗ к Модулю 5*\n\n"
            "Добавь к видео из М4 музыку + субтитры.\n"
            "Пришли ролик — дедлайн *3 апреля* 🗓"
        ),
    },
    {
        "number": 6, "title": "Модуль 6 — Монтаж", "emoji": "✂️",
        "hw_deadline": date(2026, 4, 9),
        "videos": [
            {"label": "Видеоурок", "url": "https://youtu.be/pyz-lsxzu5Y?si=Kydywc3LwmPDCqPc"},
            {"label": "Практика",  "url": "https://youtu.be/qumSB2xWCRg?si=8BN6cEyEgnzR0P_4"},
        ],
        "materials": "https://drive.google.com/drive/folders/1C5T1X91x-nnAVg0F2GnlEpHb1W52QHbq?usp=sharing",
        "text": (
            "✂️ *Модуль 6 — Монтаж*\n\n"
            "Собираем готовый упакованный результат.\n"
            "Практика — ключ к мастерству! ✂️"
        ),
        "hw_text": (
            "📝 *ДЗ к Модулю 6*\n\n"
            "Смонтируй ролик 15–30 сек: Фото → Видео → Звук → Монтаж.\n"
            "Пришли — дедлайн *9 апреля* 🗓"
        ),
    },
    {
        "number": 7, "title": "Модуль 7 — Портфолио и заработок", "emoji": "💼",
        "hw_deadline": date(2026, 4, 15),
        "videos": [{"label": "Видеоурок", "url": "https://youtu.be/tUFCVG1qjB8"}],
        "materials": "https://www.canva.com/folder/FAHDR2Mlg3o",
        "text": (
            "💼 *Модуль 7 — Портфолио и заработок*\n\n"
            "Финальный модуль! Превращаем навыки в профессию и доход.\n"
            "Ты прошёл огромный путь! 🏆"
        ),
        "hw_text": (
            "📝 *Финальное ДЗ — Модуль 7*\n\n"
            "1️⃣ Оформи кейс из любой работы курса\n"
            "2️⃣ Подготовь PDF-презентацию своих навыков (2–5 стр)\n\n"
            "Пришли оба файла — дедлайн *15 апреля* 🗓\n\nГоржусь тобой! 🙌"
        ),
    },
]

# ══════════════════════════════════════════════════════════════════════════════
#  БАЗА ДАННЫХ (JSON)
# ══════════════════════════════════════════════════════════════════════════════

def db_load() -> dict:
    if Path(DB_FILE).exists():
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def db_save(data: dict):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_student(user_id: int) -> dict | None:
    return db_load().get(str(user_id))

def get_all() -> dict:
    return db_load()

def upsert_student(user_id: int, name: str, username: str) -> dict:
    d   = db_load()
    uid = str(user_id)
    if uid not in d:
        d[uid] = {
            "id": user_id, "name": name, "username": username,
            "joined": datetime.now().isoformat(),
            "hw_submitted": {}, "last_module": None,
        }
        db_save(d)
        log.info("Новый студент: %s (%s)", name, user_id)
    return d[uid]

def record_hw(user_id: int, module_number: int):
    d, uid, key = db_load(), str(user_id), str(module_number)
    if uid in d:
        d[uid]["hw_submitted"].setdefault(key, [])
        d[uid]["hw_submitted"][key].append(datetime.now().isoformat())
        db_save(d)

def set_last_module(user_id: int, module_number: int):
    d, uid = db_load(), str(user_id)
    if uid in d:
        d[uid]["last_module"] = module_number
        db_save(d)

# ══════════════════════════════════════════════════════════════════════════════
#  ХЕЛПЕРЫ
# ══════════════════════════════════════════════════════════════════════════════

def is_allowed(user_id: int, username: str) -> bool:
    if user_id == CURATOR_ID:
        return True
    if user_id in ALLOWED_USERS:
        return True
    if username and username.lower() in ALLOWED_USERS:
        return True
    return False

def videos_open() -> bool:
    return (date.today() - COURSE_START).days < ACCESS_MONTHS * 30

def main_keyboard() -> ReplyKeyboardMarkup:
    """Постоянная клавиатура внизу чата — всегда видна."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📚 Модули"), KeyboardButton(text="📤 Сдать ДЗ")],
            [KeyboardButton(text="📊 Прогресс"), KeyboardButton(text="📅 Дедлайны")],
            [KeyboardButton(text="📞 Созвоны"), KeyboardButton(text="❓ Помощь")],
        ],
        resize_keyboard=True,
    )

def course_menu_keyboard() -> InlineKeyboardMarkup:
    rows, row = [], []
    for mod in MODULES:
        row.append(InlineKeyboardButton(
            text=f"{mod['emoji']} М{mod['number']} — {mod['title'].split('—')[1].strip()}",
            callback_data=f"mod_{mod['number']}",
        ))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)

def module_keyboard(mod: dict) -> InlineKeyboardMarkup:
    rows = []
    if videos_open():
        for v in mod["videos"]:
            rows.append([InlineKeyboardButton(text=f"▶️ {v['label']}", url=v["url"])])
    else:
        rows.append([InlineKeyboardButton(
            text="🔒 Видео недоступно (истёк срок 3 мес.)", callback_data="noop",
        )])
    if mod.get("materials"):
        rows.append([InlineKeyboardButton(text="📂 Материалы к модулю", url=mod["materials"])])
    rows.append([InlineKeyboardButton(text="◀️ Все модули", callback_data="back_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def deadline_line(mod: dict, hw_done: bool) -> str:
    today     = date.today()
    dl        = mod["hw_deadline"]
    days_left = (dl - today).days
    dl_str    = dl.strftime("%d.%m.%Y")
    if hw_done:
        return "✅ ДЗ уже сдано!"
    if days_left > 0:
        return f"📅 Дедлайн ДЗ: *{dl_str}* (осталось {days_left} дн.)"
    if days_left == 0:
        return f"📅 Дедлайн ДЗ: *{dl_str}* — сегодня последний день! ⚠️"
    return f"📅 Дедлайн ДЗ: *{dl_str}* — истёк ❌"


def hw_choice_keyboard(student: dict) -> InlineKeyboardMarkup:
    """Кнопки выбора модуля для сдачи ДЗ (только несданные с активным дедлайном)."""
    today = date.today()
    rows  = []
    for mod in MODULES:
        hw_done   = str(mod["number"]) in student.get("hw_submitted", {})
        days_left = (mod["hw_deadline"] - today).days

        if hw_done:
            continue  # Уже сдано — не показываем

        if days_left < 0:
            label = f"❌ М{mod['number']} — просрочено"
            # Всё равно даём кнопку — вдруг куратор разрешил
        else:
            label = f"{mod['emoji']} ДЗ {mod['number']} — {mod['title'].split('—')[1].strip()}"

        rows.append([InlineKeyboardButton(
            text=label,
            callback_data=f"hw_{mod['number']}",
        )])

    if not rows:
        rows.append([InlineKeyboardButton(text="🎉 Все ДЗ сданы!", callback_data="back_menu")])

    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="hw_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ══════════════════════════════════════════════════════════════════════════════
#  FSM — состояние ожидания файла после выбора модуля
# ══════════════════════════════════════════════════════════════════════════════

class HWSubmission(StatesGroup):
    waiting_for_content = State()

# ══════════════════════════════════════════════════════════════════════════════
#  БОТ
# ══════════════════════════════════════════════════════════════════════════════

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())

# ── /start ────────────────────────────────────────────────────────────────────
@dp.message(Command("start"))
async def cmd_start(message: Message):
    user     = message.from_user
    uid      = user.id
    username = user.username or ""

    if not is_allowed(uid, username):
        await message.answer(
            "⛔️ У вас нет доступа к этому боту.\n"
            "Если вы оплатили курс — напишите менеджеру."
        )
        if CURATOR_ID:
            uname = f" (@{username})" if username else ""
            await bot.send_message(
                CURATOR_ID,
                f"🔔 Попытка входа без доступа:\n"
                f"👤 {user.full_name}{uname}\n"
                f"🆔 `{uid}`\n\n"
                f"Добавить в ALLOWED\\_USERS если нужно.",
                parse_mode="Markdown",
            )
        return

    upsert_student(uid, user.full_name, username)

    await message.answer(
        f"👋 Привет, *{user.first_name}*!\n\n"
        "Добро пожаловать на курс от *Yelumio* по созданию ИИ креатива! 🎉\n\n"
        "Все модули открыты сразу — можешь смотреть в удобное время.\n"
        "После каждого модуля сдай домашнее задание в указанный срок.\n\n"
        "📦 8 модулей — все доступны прямо сейчас\n"
        "📅 Дедлайны ДЗ — фиксированные даты\n"
        "🎥 Доступ к видео — 3 месяца с 10 марта\n"
        "📞 Созвоны с куратором\n\n"
        "Используй кнопки внизу 👇",
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )

# ── /course ───────────────────────────────────────────────────────────────────
@dp.message(Command("course"))
async def cmd_course(message: Message):
    uid      = message.from_user.id
    username = message.from_user.username or ""
    if not is_allowed(uid, username):
        await message.answer("⛔️ У вас нет доступа к этому боту.\nЕсли вы оплатили курс — напишите менеджеру.")
        return
    await message.answer(
        "📚 *Видеоуроки курса*\n\nВыбери модуль 👇",
        parse_mode="Markdown",
        reply_markup=course_menu_keyboard(),
    )

# ── /dom ──────────────────────────────────────────────────────────────────────
@dp.message(Command("dom"))
async def cmd_dom(message: Message):
    uid      = message.from_user.id
    username = message.from_user.username or ""
    if not is_allowed(uid, username):
        await message.answer("⛔️ У вас нет доступа к этому боту.\nЕсли вы оплатили курс — напишите менеджеру.")
        return

    student = get_student(uid)
    hw      = (student or {}).get("hw_submitted", {})
    today   = date.today()

    lines = ["📅 *Сроки домашних заданий*\n"]
    for mod in MODULES:
        dl        = mod["hw_deadline"]
        days_left = (dl - today).days
        hw_done   = str(mod["number"]) in hw
        if hw_done:
            icon = "✅"
        elif days_left < 0:
            icon = "❌"
        elif days_left == 0:
            icon = "⚠️"
        else:
            icon = "🕐"
        lines.append(f"{icon} *{mod['title']}*\n    до {dl.strftime('%d.%m.%Y')}")

    await message.answer("\n\n".join(lines), parse_mode="Markdown")

# ── /status ───────────────────────────────────────────────────────────────────
@dp.message(Command("status"))
async def cmd_status(message: Message):
    uid      = message.from_user.id
    username = message.from_user.username or ""
    if not is_allowed(uid, username):
        await message.answer("⛔️ У вас нет доступа к этому боту.\nЕсли вы оплатили курс — напишите менеджеру.")
        return

    student = get_student(uid)
    if not student:
        await message.answer("Сначала напиши /start 👋")
        return

    hw    = student.get("hw_submitted", {})
    today = date.today()
    lines = ["📊 *Твой прогресс*\n"]

    last_mod_num = student.get("last_module")
    if last_mod_num is not None:
        last_mod = next((m for m in MODULES if m["number"] == last_mod_num), None)
        if last_mod:
            lines.append(f"📖 *Последний открытый модуль:*\n    {last_mod['title']}\n")

    if hw:
        last_num = max(int(k) for k in hw.keys())
        last_mod = next((m for m in MODULES if m["number"] == last_num), None)
        if last_mod:
            dt = datetime.fromisoformat(hw[str(last_num)][-1]).strftime("%d.%m в %H:%M")
            lines.append(f"✅ *Последнее сданное ДЗ:*\n    {last_mod['title']}\n    Сдано: {dt}\n")
    else:
        lines.append("📝 *ДЗ:* ещё не сдавал\n")

    lines.append("*Все дедлайны:*")
    for mod in MODULES:
        dl        = mod["hw_deadline"]
        days_left = (dl - today).days
        hw_done   = str(mod["number"]) in hw
        if hw_done:
            icon = "✅"
        elif days_left < 0:
            icon = "❌"
        elif days_left == 0:
            icon = "⚠️"
        else:
            icon = "🕐"
        lines.append(f"  {icon} {mod['emoji']} М{mod['number']} — до {dl.strftime('%d.%m')}")

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📚 Открыть модули", callback_data="back_menu")
    ]])
    await message.answer("\n".join(lines), parse_mode="Markdown", reply_markup=kb)

# ── /calls ────────────────────────────────────────────────────────────────────
@dp.message(Command("calls"))
async def cmd_calls(message: Message):
    uid      = message.from_user.id
    username = message.from_user.username or ""
    if not is_allowed(uid, username):
        await message.answer("⛔️ У вас нет доступа к этому боту.\nЕсли вы оплатили курс — напишите менеджеру.")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📅 Записаться на созвон", url=CALENDLY_URL)
    ]])
    await message.answer(
        "📞 *Созвоны с куратором*\n\n"
        "Каждый участник может записаться на *2 созвона в неделю* по 45 минут.\n\n"
        "📌 *Условия:*\n"
        "• Максимум 2 созвона в неделю\n"
        "• Доступны до *20 апреля*\n"
        "• Длительность — 45 минут\n\n"
        "Выбери удобные дату и время 👇",
        parse_mode="Markdown",
        reply_markup=kb,
    )

# ── /help ─────────────────────────────────────────────────────────────────────
@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "🤖 *Как пользоваться ботом*\n\n"
        "Используй кнопки внизу экрана:\n\n"
        "📚 *Модули* — видеоуроки с материалами\n"
        "📤 *Сдать ДЗ* — выбрать модуль и отправить работу\n"
        "📊 *Прогресс* — твой статус и дедлайны\n"
        "📅 *Дедлайны* — сроки домашних заданий\n"
        "📞 *Созвоны* — записаться на созвон с куратором\n\n"
        "Если кнопки пропали — нажми /start",
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )

# ── /students — только куратор ────────────────────────────────────────────────
@dp.message(Command("students"))
async def cmd_students(message: Message):
    if message.from_user.id != CURATOR_ID:
        return
    all_s = get_all()
    if not all_s:
        await message.answer("Студентов пока нет.")
        return
    lines = [f"👥 *Студентов: {len(all_s)}*\n"]
    for s in all_s.values():
        uname    = f"@{s['username']}" if s.get("username") else "—"
        hw_count = sum(len(v) for v in s.get("hw_submitted", {}).values())
        last_m   = s.get("last_module")
        lines.append(
            f"• {s['name']} ({uname})\n"
            f"  🆔 `{s['id']}` · ДЗ: {hw_count} · Посл.модуль: {'М'+str(last_m) if last_m is not None else '—'}"
        )
    text = "\n\n".join(lines)
    await message.answer(text[:4000], parse_mode="Markdown")

# ══════════════════════════════════════════════════════════════════════════════
#  НОВАЯ КОМАНДА /hw — СДАЧА ДЗ С ВЫБОРОМ МОДУЛЯ
# ══════════════════════════════════════════════════════════════════════════════

@dp.message(Command("hw"))
async def cmd_hw(message: Message, state: FSMContext):
    uid      = message.from_user.id
    username = message.from_user.username or ""
    if not is_allowed(uid, username):
        await message.answer("⛔️ У вас нет доступа к этому боту.\nЕсли вы оплатили курс — напишите менеджеру.")
        return

    student = get_student(uid)
    if not student:
        await message.answer("Сначала напиши /start 👋")
        return

    await state.clear()
    await message.answer(
        "📤 *Сдача домашнего задания*\n\n"
        "Выбери, к какому модулю сдаёшь ДЗ 👇",
        parse_mode="Markdown",
        reply_markup=hw_choice_keyboard(student),
    )

# ── Callback: выбор модуля для ДЗ ────────────────────────────────────────────
@dp.callback_query(F.data.startswith("hw_") & ~F.data.in_({"hw_cancel", "hw_done"}))
async def cb_hw_select(call: CallbackQuery, state: FSMContext):
    uid      = call.from_user.id
    username = call.from_user.username or ""
    if not is_allowed(uid, username):
        await call.answer("⛔️ Нет доступа", show_alert=True)
        return

    mod_num = int(call.data.split("_")[1])
    mod     = next((m for m in MODULES if m["number"] == mod_num), None)
    if not mod:
        await call.answer("Модуль не найден", show_alert=True)
        return

    # Сохраняем выбранный модуль в FSM
    await state.set_state(HWSubmission.waiting_for_content)
    await state.update_data(module_num=mod_num)

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Отмена", callback_data="hw_cancel")
    ]])

    await call.message.edit_text(
        f"📝 *Сдача ДЗ к {mod['title']}*\n\n"
        f"Отправь файл, фото, видео или текст — я приму всё!\n"
        f"Можешь отправить несколько сообщений подряд.\n\n"
        f"Когда закончишь — нажми кнопку ниже 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Готово, я всё отправил", callback_data="hw_done"),
        ], [
            InlineKeyboardButton(text="❌ Отмена", callback_data="hw_cancel"),
        ]]),
    )
    await call.answer()

# ── Callback: отмена сдачи ────────────────────────────────────────────────────
@dp.callback_query(F.data == "hw_cancel")
async def cb_hw_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Сдача ДЗ отменена.\n\nНажми /hw когда будешь готов 😊")
    await call.answer()

# ── Callback: завершение сдачи ────────────────────────────────────────────────
@dp.callback_query(F.data == "hw_done")
async def cb_hw_done(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    mod_num    = data.get("module_num")
    file_count = data.get("file_count", 0)

    if mod_num is None:
        await call.answer("Сначала выбери модуль через /hw", show_alert=True)
        return

    if file_count == 0:
        await call.answer("Ты ещё ничего не отправил! Пришли файл или текст.", show_alert=True)
        return

    uid     = call.from_user.id
    student = get_student(uid)
    mod     = next((m for m in MODULES if m["number"] == mod_num), None)

    # Записываем в локальную БД
    record_hw(uid, mod_num)

    # Записываем в Google Sheets
    mark_hw_in_sheet(student["name"], mod_num)

    await state.clear()

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📚 Открыть модули", callback_data="back_menu")
    ]])

    # Убираем кнопки из старого сообщения
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await call.message.answer(
        f"✅ *ДЗ принято!*\n\n"
        f"Модуль: *{mod['title']}*\n"
        f"Файлов: {file_count}\n\n"
        f"Куратор проверит и даст обратную связь 🙌",
        parse_mode="Markdown",
        reply_markup=kb,
    )
    await call.answer()

# ══════════════════════════════════════════════════════════════════════════════
#  ПРИЁМ КОНТЕНТА (в состоянии ожидания ДЗ)
# ══════════════════════════════════════════════════════════════════════════════

@dp.message(HWSubmission.waiting_for_content)
async def handle_hw_content(message: Message, state: FSMContext):
    """Принимает файлы/фото/видео/текст пока ученик в режиме сдачи ДЗ."""
    user    = message.from_user
    uid     = user.id
    student = get_student(uid)
    if not student:
        return

    data    = await state.get_data()
    mod_num = data.get("module_num")
    if mod_num is None:
        return

    mod         = next((m for m in MODULES if m["number"] == mod_num), None)
    file_count  = data.get("file_count", 0)
    student_name = student["name"]

    # ── Определяем тип контента и обрабатываем ────────────────────────────────

    file_obj  = None
    filename  = "file"
    mime_type = "application/octet-stream"

    if message.document:
        file_obj  = message.document
        filename  = message.document.file_name or "document"
        mime_type = message.document.mime_type or "application/octet-stream"

    elif message.photo:
        file_obj  = message.photo[-1]  # Максимальное качество
        filename  = f"photo_{datetime.now().strftime('%H%M%S')}.jpg"
        mime_type = "image/jpeg"

    elif message.video:
        file_obj  = message.video
        filename  = message.video.file_name or f"video_{datetime.now().strftime('%H%M%S')}.mp4"
        mime_type = message.video.mime_type or "video/mp4"

    elif message.audio:
        file_obj  = message.audio
        filename  = message.audio.file_name or f"audio_{datetime.now().strftime('%H%M%S')}.mp3"
        mime_type = message.audio.mime_type or "audio/mpeg"

    elif message.voice:
        file_obj  = message.voice
        filename  = f"voice_{datetime.now().strftime('%H%M%S')}.ogg"
        mime_type = "audio/ogg"

    elif message.video_note:
        file_obj  = message.video_note
        filename  = f"videonote_{datetime.now().strftime('%H%M%S')}.mp4"
        mime_type = "video/mp4"

    elif message.text:
        # Текстовое сообщение — сохраняем как .txt
        save_text_to_drive(student_name, message.text, mod_num)
        file_count += 1
        await state.update_data(file_count=file_count)

        # Пересылаем куратору
        if CURATOR_ID:
            uname = f" (@{user.username})" if user.username else ""
            try:
                await bot.send_message(
                    CURATOR_ID,
                    f"📥 *ДЗ · {mod['title']}*\n"
                    f"👤 {user.full_name}{uname}\n"
                    f"📝 Текст",
                    parse_mode="Markdown",
                )
                await message.forward(CURATOR_ID)
            except Exception as e:
                log.error("Ошибка пересылки: %s", e)

        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Готово, я всё отправил", callback_data="hw_done"),
        ], [
            InlineKeyboardButton(text="❌ Отмена", callback_data="hw_cancel"),
        ]])
        await message.answer(
            f"📝 Текст принят ({file_count} файл(ов)).\nМожешь отправить ещё или нажми *Готово* 👇",
            parse_mode="Markdown",
            reply_markup=kb,
        )
        return

    else:
        await message.answer("Этот тип контента не поддерживается. Отправь файл, фото, видео или текст.")
        return

    # ── Скачиваем и загружаем файл ────────────────────────────────────────────
    if file_obj:
        try:
            log.info("⬇️ Скачиваю из Telegram: %s (file_id: %s)", filename, file_obj.file_id)
            tg_file = await bot.get_file(file_obj.file_id)
            file_data = io.BytesIO()
            await bot.download_file(tg_file.file_path, file_data)
            file_bytes = file_data.getvalue()
            log.info("⬇️ Скачано: %s (%d байт)", filename, len(file_bytes))

            # Загружаем в Google Drive
            upload_to_drive(student_name, filename, file_bytes, mime_type, mod_num)

        except Exception as e:
            log.error("❌ Ошибка скачивания/загрузки файла: %s — %s", filename, e)

        file_count += 1
        await state.update_data(file_count=file_count)

        # Пересылаем куратору
        if CURATOR_ID:
            uname = f" (@{user.username})" if user.username else ""
            try:
                await bot.send_message(
                    CURATOR_ID,
                    f"📥 *ДЗ · {mod['title']}*\n"
                    f"👤 {user.full_name}{uname}\n"
                    f"📎 {filename}",
                    parse_mode="Markdown",
                )
                await message.forward(CURATOR_ID)
            except Exception as e:
                log.error("Ошибка пересылки: %s", e)

        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Готово, я всё отправил", callback_data="hw_done"),
        ], [
            InlineKeyboardButton(text="❌ Отмена", callback_data="hw_cancel"),
        ]])
        await message.answer(
            f"📎 Файл принят ({file_count} файл(ов)).\nМожешь отправить ещё или нажми *Готово* 👇",
            parse_mode="Markdown",
            reply_markup=kb,
        )

# ══════════════════════════════════════════════════════════════════════════════
#  ОБРАБОТЧИКИ КНОПОК ГЛАВНОГО МЕНЮ (ReplyKeyboard)
# ══════════════════════════════════════════════════════════════════════════════

MENU_BUTTONS = {"📚 Модули", "📤 Сдать ДЗ", "📊 Прогресс", "📅 Дедлайны", "📞 Созвоны", "❓ Помощь"}

@dp.message(F.text == "📚 Модули")
async def btn_course(message: Message):
    uid      = message.from_user.id
    username = message.from_user.username or ""
    if not is_allowed(uid, username):
        await message.answer("⛔️ У вас нет доступа к этому боту.")
        return
    await message.answer(
        "📚 *Видеоуроки курса*\n\nВыбери модуль 👇",
        parse_mode="Markdown",
        reply_markup=course_menu_keyboard(),
    )

@dp.message(F.text == "📤 Сдать ДЗ")
async def btn_hw(message: Message, state: FSMContext):
    uid      = message.from_user.id
    username = message.from_user.username or ""
    if not is_allowed(uid, username):
        await message.answer("⛔️ У вас нет доступа к этому боту.")
        return
    student = get_student(uid)
    if not student:
        await message.answer("Сначала напиши /start 👋")
        return
    await state.clear()
    await message.answer(
        "📤 *Сдача домашнего задания*\n\nВыбери, к какому модулю сдаёшь ДЗ 👇",
        parse_mode="Markdown",
        reply_markup=hw_choice_keyboard(student),
    )

@dp.message(F.text == "📊 Прогресс")
async def btn_status(message: Message):
    # Вызываем тот же код что и /status
    await cmd_status(message)

@dp.message(F.text == "📅 Дедлайны")
async def btn_dom(message: Message):
    await cmd_dom(message)

@dp.message(F.text == "📞 Созвоны")
async def btn_calls(message: Message):
    await cmd_calls(message)

@dp.message(F.text == "❓ Помощь")
async def btn_help(message: Message):
    await cmd_help(message)

# ══════════════════════════════════════════════════════════════════════════════
#  ОБРАБОТКА СООБЩЕНИЙ БЕЗ СОСТОЯНИЯ (напоминание использовать /hw)
# ══════════════════════════════════════════════════════════════════════════════

@dp.message(~F.text.startswith("/"))
async def handle_no_state(message: Message):
    """Если ученик отправил файл без выбора модуля — подсказываем."""
    uid      = message.from_user.id
    username = message.from_user.username or ""

    if not is_allowed(uid, username):
        await message.answer(
            "⛔️ У вас нет доступа к этому боту.\n"
            "Если вы оплатили курс — напишите менеджеру."
        )
        return

    # Игнорируем нажатия на кнопки меню (они уже обработаны выше)
    if message.text and message.text in MENU_BUTTONS:
        return

    has_content = (
        message.document or message.photo or message.video
        or message.audio or message.voice or message.video_note
    )

    if has_content or message.text:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📤 Сдать ДЗ", callback_data="start_hw")
        ]])
        await message.answer(
            "👆 Чтобы сдать домашнее задание, сначала выбери модуль!\n\n"
            "Нажми *📤 Сдать ДЗ* внизу или кнопку ниже 👇",
            parse_mode="Markdown",
            reply_markup=kb,
        )

# ── Callback: быстрый старт сдачи ────────────────────────────────────────────
@dp.callback_query(F.data == "start_hw")
async def cb_start_hw(call: CallbackQuery, state: FSMContext):
    uid      = call.from_user.id
    username = call.from_user.username or ""
    if not is_allowed(uid, username):
        await call.answer("⛔️ Нет доступа", show_alert=True)
        return

    student = get_student(uid)
    if not student:
        await call.answer("Сначала напиши /start", show_alert=True)
        return

    await state.clear()
    await call.message.edit_text(
        "📤 *Сдача домашнего задания*\n\n"
        "Выбери, к какому модулю сдаёшь ДЗ 👇",
        parse_mode="Markdown",
        reply_markup=hw_choice_keyboard(student),
    )
    await call.answer()

# ── Callback: нажатие на модуль (просмотр) ───────────────────────────────────
@dp.callback_query(F.data.startswith("mod_"))
async def cb_module(call: CallbackQuery):
    uid      = call.from_user.id
    username = call.from_user.username or ""
    if not is_allowed(uid, username):
        await call.answer("⛔️ Нет доступа", show_alert=True)
        return

    mod_num = int(call.data.split("_")[1])
    mod     = next((m for m in MODULES if m["number"] == mod_num), None)
    if not mod:
        await call.answer("Модуль не найден", show_alert=True)
        return

    set_last_module(uid, mod_num)
    student = get_student(uid)
    hw_done = str(mod_num) in (student or {}).get("hw_submitted", {})

    text = (
        f"{mod['text']}\n\n"
        f"{'─' * 22}\n"
        f"{mod['hw_text']}\n\n"
        f"{deadline_line(mod, hw_done)}"
    )

    await call.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=module_keyboard(mod),
    )
    await call.answer()

# ── Callback: назад к меню ────────────────────────────────────────────────────
@dp.callback_query(F.data == "back_menu")
async def cb_back(call: CallbackQuery):
    await call.message.edit_text(
        "📚 *Видеоуроки курса*\n\nВыбери модуль 👇",
        parse_mode="Markdown",
        reply_markup=course_menu_keyboard(),
    )
    await call.answer()

@dp.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery):
    await call.answer("🔒 Видео недоступно — истёк срок 3 месяца.", show_alert=True)

# ══════════════════════════════════════════════════════════════════════════════
#  НАПОМИНАНИЯ — каждый день в 10:00
# ══════════════════════════════════════════════════════════════════════════════

async def job_reminders():
    today    = date.today()
    students = get_all()
    for student in students.values():
        uid = student["id"]
        if not is_allowed(uid, student.get("username", "")):
            continue
        for mod in MODULES:
            days_left = (mod["hw_deadline"] - today).days
            hw_done   = str(mod["number"]) in student["hw_submitted"]
            if days_left == 1 and not hw_done:
                try:
                    await bot.send_message(
                        uid,
                        f"⏰ *Напоминание!*\n\n"
                        f"Завтра дедлайн ДЗ к *{mod['title']}*\n"
                        f"Срок: *{mod['hw_deadline'].strftime('%d.%m.%Y')}*\n\n"
                        f"Успей сдать — нажми /hw 💪",
                        parse_mode="Markdown",
                    )
                except Exception as e:
                    log.error("Напоминание %s: %s", uid, e)

# ══════════════════════════════════════════════════════════════════════════════
#  ЗАПУСК
# ══════════════════════════════════════════════════════════════════════════════

async def main():
    if BOT_TOKEN == "ВСТАВЬ_ТОКЕН":
        raise RuntimeError("Установи BOT_TOKEN в переменные окружения!")

    init_google()

    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    scheduler.add_job(job_reminders, "cron", hour=10, minute=0)
    scheduler.start()
    log.info("✅ Бот запущен!")
    await dp.start_polling(bot, drop_pending_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
