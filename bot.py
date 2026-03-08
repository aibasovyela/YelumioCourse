"""
bot.py — бот курса Yelumio AI-Креатив (aiogram 3)
"""

import asyncio
import json
import logging
import os
from datetime import datetime, date
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ══════════════════════════════════════════════════════════════════════════════
#  НАСТРОЙКИ
# ══════════════════════════════════════════════════════════════════════════════

BOT_TOKEN  = os.getenv("BOT_TOKEN", "ВСТАВЬ_ТОКЕН")
CURATOR_ID = int(os.getenv("CURATOR_ID", "0"))
DB_FILE    = "students.json"
TIMEZONE   = "Asia/Almaty"

COURSE_START  = date(2026, 3, 10)
ACCESS_MONTHS = 3
CALENDLY_URL  = "https://calendly.com/aibasovyela/30min"

# Белый список — username строчными без @ или числовой Telegram ID
ALLOWED_USERS = {
    "zhukentay",
    "danaaltaibaeva",
    "a1tayir",
    "best_shakyru",
    "agzamasseka",
    "anastassiyay",
    "chqrnell4",
    "abzaluly_ali",
    "valikhan_t",
    # Числовые ID добавляй сюда:
    # 123456789,
}

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
#  МОДУЛИ
#  Каждый модуль может иметь несколько блоков видео (список)
# ══════════════════════════════════════════════════════════════════════════════

MODULES = [
    {
        "number":      0,
        "title":       "Модуль 0 — Введение",
        "emoji":       "🎯",
        "hw_deadline": date(2026, 3, 13),
        "videos": [
            {"label": "Блок 1", "url": "https://youtu.be/KpRemQAmxxU"},
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
        "number":      1,
        "title":       "Модуль 1 — Идея и концепция",
        "emoji":       "💡",
        "hw_deadline": date(2026, 3, 17),
        "videos": [
            {"label": "Видеоурок", "url": "https://youtu.be/oeH0VmIzLcQ"},
        ],
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
        "number":      2,
        "title":       "Модуль 2 — Текст и промпты",
        "emoji":       "✍️",
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
        "number":      3,
        "title":       "Модуль 3 — ИИ-фото",
        "emoji":       "📸",
        "hw_deadline": date(2026, 3, 27),
        "videos": [
            {"label": "Блоки 1–3", "url": "https://youtu.be/pbG_ssLSIig"},
            {"label": "Блоки 4–7", "url": "https://youtu.be/MR0tdZxgCzo"},
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
        "number":      4,
        "title":       "Модуль 4 — ИИ-видео",
        "emoji":       "🎥",
        "hw_deadline": date(2026, 3, 31),
        "videos": [
            {"label": "Видеоурок",  "url": "https://youtu.be/eHOWCPcxlMc"},
            {"label": "Практика",   "url": "https://youtu.be/4dfD1ZQO0pY"},
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
        "number":      5,
        "title":       "Модуль 5 — Звук",
        "emoji":       "🎵",
        "hw_deadline": date(2026, 4, 3),
        "videos": [
            {"label": "Блок 1", "url": "https://youtu.be/W2_Kgz4zvjo"},
            {"label": "Блок 2", "url": "https://youtu.be/IrWEePy2eLo"},
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
        "number":      6,
        "title":       "Модуль 6 — Монтаж",
        "emoji":       "✂️",
        "hw_deadline": date(2026, 4, 9),
        "videos": [
            {"label": "Видеоурок", "url": "https://youtu.be/vF_vcYxOisY"},
            {"label": "Практика",  "url": "https://youtu.be/3piejCnnhqA"},
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
        "number":      7,
        "title":       "Модуль 7 — Портфолио и заработок",
        "emoji":       "💼",
        "hw_deadline": date(2026, 4, 15),
        "videos": [
            {"label": "Видеоурок", "url": "https://youtu.be/vcPycJvVVHI"},
        ],
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
#  БАЗА ДАННЫХ
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
        log.info(f"Новый студент: {name} ({user_id})")
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

def course_menu_keyboard() -> InlineKeyboardMarkup:
    """8 кнопок модулей по 2 в ряд."""
    rows = []
    row  = []
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
    """Кнопки видео (один или несколько блоков) + материалы + назад."""
    rows = []
    if videos_open():
        for v in mod["videos"]:
            rows.append([InlineKeyboardButton(
                text=f"▶️ {v['label']}",
                url=v["url"],
            )])
    else:
        rows.append([InlineKeyboardButton(
            text="🔒 Видео недоступно (истёк срок 3 мес.)",
            callback_data="noop",
        )])
    if mod.get("materials"):
        rows.append([InlineKeyboardButton(
            text="📂 Материалы к модулю",
            url=mod["materials"],
        )])
    rows.append([InlineKeyboardButton(text="◀️ Все модули", callback_data="back_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def deadline_line(mod: dict, hw_done: bool) -> str:
    today     = date.today()
    dl        = mod["hw_deadline"]
    days_left = (dl - today).days
    dl_str    = dl.strftime("%d.%m.%Y")
    if hw_done:
        return f"✅ ДЗ уже сдано!"
    if days_left > 0:
        return f"📅 Дедлайн ДЗ: *{dl_str}* (осталось {days_left} дн.)"
    if days_left == 0:
        return f"📅 Дедлайн ДЗ: *{dl_str}* — сегодня последний день! ⚠️"
    return f"📅 Дедлайн ДЗ: *{dl_str}* — истёк ❌"

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
        "📦 8 модулей — все доступны прямо сейчас — /course\n"
        "📅 Дедлайны ДЗ — фиксированные даты — /dom\n"
        "🎥 Доступ к видео — 3 месяца с 10 марта\n"
        "📞 Созвоны — /calls\n\n"
        "Команды:\n"
        "/course — видеоуроки с материалами\n"
        "/status — твой прогресс\n"
        "/calls — записаться на созвон\n"
        "/dom — сроки домашних заданий\n"
        "/help — помощь",
        parse_mode="Markdown",
        reply_markup=course_menu_keyboard(),
    )

# ── /course — меню модулей ────────────────────────────────────────────────────
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

# ── /dom — дедлайны ДЗ ───────────────────────────────────────────────────────
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
    lines = [f"📊 *Твой прогресс*\n"]

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
        "🤖 *Команды бота*\n\n"
        "/course — видеоуроки с материалами\n"
        "/status — твой прогресс и дедлайны\n"
        "/dom — сроки домашних заданий\n"
        "/calls — записаться на созвон\n"
        "/help — это сообщение\n\n"
        "📤 *Сдача ДЗ:*\n"
        "Просто отправь файл, фото, видео или текст — бот всё примет!",
        parse_mode="Markdown",
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

# ── Callback: нажатие на модуль ───────────────────────────────────────────────
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

# ── Приём ДЗ ─────────────────────────────────────────────────────────────────
@dp.message(~F.text.startswith("/"))
async def handle_submission(message: Message):
    user     = message.from_user
    uid      = user.id
    username = user.username or ""

    if not is_allowed(uid, username):
        await message.answer(
            "⛔️ У вас нет доступа к этому боту.\n"
            "Если вы оплатили курс — напишите менеджеру."
        )
        return

    student = get_student(uid)
    if not student:
        await message.answer("Сначала напиши /start 👋")
        return

    today = date.today()
    open_mods = [
        m for m in MODULES
        if m["hw_deadline"] >= today and str(m["number"]) not in student["hw_submitted"]
    ]

    if not open_mods:
        all_done = all(str(m["number"]) in student["hw_submitted"] for m in MODULES)
        if all_done:
            await message.answer("🎉 Ты уже сдал все домашние задания! Молодец!")
        else:
            await message.answer(
                "⏰ Все текущие дедлайны истекли.\n"
                "Если хочешь сдать с опозданием — напиши куратору напрямую."
            )
        return

    target = min(open_mods, key=lambda m: m["hw_deadline"])
    dl_str = target["hw_deadline"].strftime("%d.%m.%Y")

    if CURATOR_ID:
        uname = f" (@{username})" if username else ""
        try:
            await bot.send_message(
                CURATOR_ID,
                f"📥 *ДЗ · {target['title']}*\n"
                f"👤 {user.full_name}{uname}\n"
                f"🆔 `{uid}`\n"
                f"📅 Дедлайн: {dl_str}",
                parse_mode="Markdown",
            )
            await message.forward(CURATOR_ID)
        except Exception as e:
            log.error(f"Ошибка пересылки: {e}")

    record_hw(uid, target["number"])

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📚 Открыть модули", callback_data="back_menu")
    ]])
    await message.answer(
        f"✅ *ДЗ принято!*\n\n"
        f"Модуль: *{target['title']}*\n"
        f"Дедлайн: {dl_str}\n\n"
        f"Куратор проверит и даст обратную связь 🙌",
        parse_mode="Markdown",
        reply_markup=kb,
    )

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
                        f"Успей сдать — просто отправь файл или текст боту! 💪",
                        parse_mode="Markdown",
                    )
                except Exception as e:
                    log.error(f"Напоминание {uid}: {e}")

# ══════════════════════════════════════════════════════════════════════════════
#  ЗАПУСК
# ══════════════════════════════════════════════════════════════════════════════

async def main():
    if BOT_TOKEN == "ВСТАВЬ_ТОКЕН":
        raise RuntimeError("Установи BOT_TOKEN в переменные окружения!")
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    scheduler.add_job(job_reminders, "cron", hour=10, minute=0)
    scheduler.start()
    log.info("✅ Бот запущен!")
    await dp.start_polling(bot, drop_pending_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
