"""
bot.py — бот курса AI-Контент (aiogram 3, Python 3.14+)

Логика:
- Доступ только по белому списку Telegram username/ID
- Все модули открываются СРАЗУ при /start
- Фиксированные даты дедлайнов ДЗ (старт 10 марта)
- Доступ к видео закрывается через 3 месяца после старта курса
- /status — последний модуль + последнее сданное ДЗ
- /calls — информация о созвонах + ссылка Calendly
- ДЗ пересылаются куратору в личку
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
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ══════════════════════════════════════════════════════════════════════════════
#  НАСТРОЙКИ
# ══════════════════════════════════════════════════════════════════════════════

BOT_TOKEN  = os.getenv("BOT_TOKEN", 7992712058:AAGAiEJq5AN_UktKFgztlJoeEi5flhM8M1E)
CURATOR_ID = int(os.getenv("CURATOR_ID", "910046222"))
DB_FILE    = "students.json"
TIMEZONE   = "Asia/Almaty"

# Дата старта курса
COURSE_START = date(2026, 3, 10)

# Через сколько месяцев закрываются ссылки на видео
ACCESS_MONTHS = 3

# Ссылка на Calendly для созвонов
CALENDLY_URL = "https://calendly.com/aibasovyela/30min"

# ── Белый список — кто может войти ───────────────────────────────────────────
# Добавляй username БЕЗ @ или числовой Telegram ID
# Бот проверяет и то и другое
ALLOWED_USERS = {
    # username (строчными буквами, без @)
    "zhukentay",
    "danaaltaibaeva",
    "a1tayir",
    "best_shakyru",
    "agzamasseka",
    "anastassiyay",
    "chqrnell4",
    "abzaluly_ali",
    "valikhan_t",
    # Числовые ID — добавляй сюда после того как узнаешь
    # 123456789,
}

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
#  МОДУЛИ И ДЕДЛАЙНЫ
# ══════════════════════════════════════════════════════════════════════════════
# Все модули открываются сразу при /start
# Дедлайны ДЗ — фиксированные даты

MODULES = [
    {
        "number": 0,
        "title":  "Модуль 0 — Введение",
        "hw_deadline": date(2026, 3, 13),
        "video":  "https://youtu.be/ССЫЛКА_МОДУЛЬ_0",
        "text": (
            "👋 *Модуль 0 — Введение*\n\n"
            "Знакомство с курсом, инструментами и планом на 45 дней.\n"
            "Смотри видео и готовься к старту! 🚀"
        ),
        "hw_text": (
            "📝 *ДЗ к Модулю 0*\n\n"
            "Познакомься с инструментами из видео:\n"
            "• Зарегистрируйся в 2–3 AI-сервисах\n"
            "• Сделай первый тест-запрос\n\n"
            "Пришли скриншоты — дедлайн *13 марта* 🗓"
        ),
    },
    {
        "number": 1,
        "title":  "Модуль 1 — Идея и концепция",
        "hw_deadline": date(2026, 3, 17),
        "video":  "https://youtu.be/ССЫЛКА_МОДУЛЬ_1",
        "text": (
            "🎬 *Модуль 1 — Идея и концепция*\n\n"
            "Как рождается сильная идея для AI-контента.\n"
            "Смотри видео и дерзай! 💪"
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
        "number": 2,
        "title":  "Модуль 2 — Текст и промпты",
        "hw_deadline": date(2026, 3, 23),
        "video":  "https://youtu.be/ССЫЛКА_МОДУЛЬ_2",
        "text": (
            "✍️ *Модуль 2 — Текст и промпты*\n\n"
            "Управляем ИИ через точные запросы.\n"
            "После этого модуля получаешь именно то, что хочешь!"
        ),
        "hw_text": (
            "📝 *ДЗ к Модулю 2*\n\n"
            "Напиши 3 промпта для своей ниши + пришли результаты генерации.\n\n"
            "Текст + скриншоты — дедлайн *23 марта* 🗓"
        ),
    },
    {
        "number": 3,
        "title":  "Модуль 3 — ИИ-фото",
        "hw_deadline": date(2026, 3, 27),
        "video":  "https://youtu.be/ССЫЛКА_МОДУЛЬ_3",
        "text": (
            "📸 *Модуль 3 — ИИ-фото*\n\n"
            "Фото профессионального уровня без фотографа.\n"
            "Только промпт — и результат! 🎯"
        ),
        "hw_text": (
            "📝 *ДЗ к Модулю 3*\n\n"
            "Создай 3 AI-фото:\n"
            "• Продуктовый кадр\n"
            "• Lifestyle\n"
            "• Атмосферная сцена\n\n"
            "Пришли картинки — дедлайн *27 марта* 🗓"
        ),
    },
    {
        "number": 4,
        "title":  "Модуль 4 — ИИ-видео",
        "hw_deadline": date(2026, 3, 31),
        "video":  "https://youtu.be/ССЫЛКА_МОДУЛЬ_4",
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
        "number": 5,
        "title":  "Модуль 5 — Звук",
        "hw_deadline": date(2026, 4, 3),
        "video":  "https://youtu.be/ССЫЛКА_МОДУЛЬ_5",
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
        "number": 6,
        "title":  "Модуль 6 — Монтаж",
        "hw_deadline": date(2026, 4, 9),
        "video":  "https://youtu.be/ССЫЛКА_МОДУЛЬ_6",
        "text": (
            "✂️ *Модуль 6 — Монтаж*\n\n"
            "Собираем готовый упакованный результат.\n"
            "Практика — ключ к мастерству! ✂️"
        ),
        "hw_text": (
            "📝 *ДЗ к Модулю 6*\n\n"
            "Смонтируй ролик 15–30 сек:\n"
            "Фото → Видео → Звук → Монтаж\n\n"
            "Пришли — дедлайн *9 апреля* 🗓"
        ),
    },
    {
        "number": 7,
        "title":  "Модуль 7 — Портфолио и заработок",
        "hw_deadline": date(2026, 4, 15),
        "video":  "https://youtu.be/ССЫЛКА_МОДУЛЬ_7",
        "text": (
            "💼 *Модуль 7 — Портфолио и заработок*\n\n"
            "Финальный модуль! Превращаем навыки в профессию и доход.\n"
            "Ты прошёл огромный путь! 🏆"
        ),
        "hw_text": (
            "📝 *Финальное ДЗ — Модуль 7*\n\n"
            "1️⃣ Оформи кейс из любой работы курса\n"
            "2️⃣ Подготовь PDF-презентацию своих навыков (2–5 стр)\n\n"
            "Пришли оба файла — дедлайн *15 апреля* 🗓\n\n"
            "Горжусь тобой! 🙌"
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
            "id":           user_id,
            "name":         name,
            "username":     username,
            "joined":       datetime.now().isoformat(),
            "hw_submitted": {},   # {"0": ["2026-03-11T10:00"], ...}
            "last_module":  None, # последний просмотренный модуль
        }
        db_save(d)
        log.info(f"Новый студент: {name} ({user_id})")
    return d[uid]

def record_hw(user_id: int, module_number: int):
    d   = db_load()
    uid = str(user_id)
    key = str(module_number)
    if uid in d:
        d[uid]["hw_submitted"].setdefault(key, [])
        d[uid]["hw_submitted"][key].append(datetime.now().isoformat())
        db_save(d)

def set_last_module(user_id: int, module_number: int):
    d   = db_load()
    uid = str(user_id)
    if uid in d:
        d[uid]["last_module"] = module_number
        db_save(d)

# ══════════════════════════════════════════════════════════════════════════════
#  ПРОВЕРКА ДОСТУПА
# ══════════════════════════════════════════════════════════════════════════════

def is_allowed(user_id: int, username: str) -> bool:
    """Проверяет белый список по ID или username."""
    if user_id in ALLOWED_USERS:
        return True
    if user_id == CURATOR_ID:
        return True
    if username and username.lower() in ALLOWED_USERS:
        return True
    return False

def video_access_active() -> bool:
    """Проверяет, не истёк ли 3-месячный доступ к видео."""
    delta = date.today() - COURSE_START
    return delta.days < ACCESS_MONTHS * 30

# ══════════════════════════════════════════════════════════════════════════════
#  ОТПРАВКА ВСЕХ МОДУЛЕЙ
# ══════════════════════════════════════════════════════════════════════════════

async def send_all_modules(bot: Bot, user_id: int):
    """Отправляет все 8 модулей сразу."""
    student = get_student(user_id)
    videos_open = video_access_active()

    for mod in MODULES:
        # Текст модуля
        await bot.send_message(user_id, mod["text"], parse_mode="Markdown")

        # Кнопка с видео
        if videos_open:
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="▶️ Смотреть видео", url=mod["video"])
            ]])
            await bot.send_message(user_id, "👆 Нажми, чтобы открыть видео", reply_markup=kb)
        else:
            await bot.send_message(
                user_id,
                "🔒 Доступ к видео этого модуля закрыт (истёк срок 3 месяца).",
            )

        # ДЗ с дедлайном
        dl_str = mod["hw_deadline"].strftime("%d.%m.%Y")
        today  = date.today()
        days_left = (mod["hw_deadline"] - today).days

        if days_left > 0:
            deadline_note = f"📅 Дедлайн: *{dl_str}* (осталось {days_left} дн.)"
        elif days_left == 0:
            deadline_note = f"📅 Дедлайн: *{dl_str}* — сегодня последний день! ⚠️"
        else:
            deadline_note = f"📅 Дедлайн: *{dl_str}* — истёк"

        # Статус сдачи
        hw_done = str(mod["number"]) in (student or {}).get("hw_submitted", {})
        if hw_done:
            deadline_note += "\n✅ ДЗ уже сдано!"

        await bot.send_message(
            user_id,
            f"{mod['hw_text']}\n\n{deadline_note}",
            parse_mode="Markdown",
        )

        set_last_module(user_id, mod["number"])

        # Небольшая пауза чтобы не спамить
        await asyncio.sleep(0.3)

# ══════════════════════════════════════════════════════════════════════════════
#  ХЭНДЛЕРЫ
# ══════════════════════════════════════════════════════════════════════════════

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())


@dp.message(Command("start"))
async def cmd_start(message: Message):
    user     = message.from_user
    uid      = user.id
    username = user.username or ""

    # Проверка белого списка
    if not is_allowed(uid, username):
        await message.answer(
            "🔒 *Доступ закрыт*\n\n"
            "Этот бот только для участников курса *AI-Контент*.\n\n"
            "Если ты купил курс — напиши куратору для получения доступа.",
            parse_mode="Markdown",
        )
        # Уведомляем куратора
        if CURATOR_ID:
            uname = f" (@{username})" if username else ""
            await bot.send_message(
                CURATOR_ID,
                f"🔔 Попытка входа без доступа:\n"
                f"👤 {user.full_name}{uname}\n"
                f"🆔 `{uid}`\n\n"
                f"Добавить в ALLOWED\\_USERS в config если нужно.",
                parse_mode="Markdown",
            )
        return

    # Регистрируем
    upsert_student(uid, user.full_name, username)

    # Приветствие
    await message.answer(
        f"👋 Привет, *{user.first_name}*!\n\n"
        "Добро пожаловать в курс *AI-Контент* 🎉\n\n"
        "Все модули открыты сразу — смотри в удобное время.\n"
        "После каждого модуля сдай домашнее задание в указанный срок.\n\n"
        "📦 *8 модулей* — все доступны прямо сейчас\n"
        "📅 *Дедлайны ДЗ* — фиксированные даты\n"
        "🎥 *Доступ к видео* — 3 месяца с 10 марта\n"
        "📞 *Созвоны* — /calls\n\n"
        "Команды:\n"
        "/status — твой прогресс\n"
        "/calls — записаться на созвон\n"
        "/help — помощь\n\n"
        "Загружаю все модули... 👇",
        parse_mode="Markdown",
    )

    await send_all_modules(bot, uid)


@dp.message(Command("status"))
async def cmd_status(message: Message):
    user     = message.from_user
    uid      = user.id
    username = user.username or ""

    if not is_allowed(uid, username):
        await message.answer("🔒 У вас нет доступа к курсу.")
        return

    student = get_student(uid)
    if not student:
        await message.answer("Сначала напиши /start 👋")
        return

    today = date.today()
    lines = [f"📊 *Твой прогресс*\n👤 {user.first_name}\n"]

    # Последний просмотренный модуль
    last_mod_num = student.get("last_module")
    if last_mod_num is not None:
        last_mod = next((m for m in MODULES if m["number"] == last_mod_num), None)
        if last_mod:
            lines.append(f"📖 *Последний модуль:*\n    {last_mod['title']}\n")

    # Последнее сданное ДЗ
    hw = student.get("hw_submitted", {})
    if hw:
        last_hw_num = max(int(k) for k in hw.keys())
        last_hw_mod = next((m for m in MODULES if m["number"] == last_hw_num), None)
        if last_hw_mod:
            last_hw_time = hw[str(last_hw_num)][-1]
            dt = datetime.fromisoformat(last_hw_time).strftime("%d.%m в %H:%M")
            lines.append(f"✅ *Последнее ДЗ:*\n    {last_hw_mod['title']}\n    Сдано: {dt}\n")
    else:
        lines.append("📝 *ДЗ:* ещё не сдавал\n")

    # Таблица дедлайнов
    lines.append("*Дедлайны ДЗ:*")
    for mod in MODULES:
        dl        = mod["hw_deadline"]
        dl_str    = dl.strftime("%d.%m")
        hw_done   = str(mod["number"]) in hw
        days_left = (dl - today).days

        if hw_done:
            status = "✅"
        elif days_left < 0:
            status = "❌ просрочен"
        elif days_left == 0:
            status = "⚠️ сегодня!"
        else:
            status = f"🕐 {days_left} дн."

        lines.append(f"  {status} М{mod['number']} — до {dl_str}")

    await message.answer("\n".join(lines), parse_mode="Markdown")


@dp.message(Command("calls"))
async def cmd_calls(message: Message):
    user     = message.from_user
    uid      = user.id
    username = user.username or ""

    if not is_allowed(uid, username):
        await message.answer("🔒 У вас нет доступа к курсу.")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📅 Записаться на созвон", url=CALENDLY_URL)
    ]])

    await message.answer(
        "📞 *Созвоны с куратором*\n\n"
        "Каждый участник может записаться на *2 созвона в неделю* по 45 минут.\n\n"
        "📌 *Важно:*\n"
        "• Максимум 2 созвона в неделю\n"
        "• Созвоны доступны до *20 апреля*\n"
        "• Длительность каждого — 45 минут\n\n"
        "Выбери удобные дату и время по кнопке ниже 👇",
        parse_mode="Markdown",
        reply_markup=kb,
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "🤖 *Команды бота*\n\n"
        "/start — открыть все модули курса\n"
        "/status — твой прогресс и дедлайны ДЗ\n"
        "/calls — записаться на созвон с куратором\n"
        "/help — это сообщение\n\n"
        "📤 *Сдача ДЗ:*\n"
        "Просто отправь файл, фото, видео или текст — бот всё поймёт!",
        parse_mode="Markdown",
    )


# ── Команды куратора ──────────────────────────────────────────────────────────

@dp.message(Command("students"))
async def cmd_students(message: Message):
    if message.from_user.id != CURATOR_ID:
        return

    all_s = get_all()
    if not all_s:
        await message.answer("Студентов пока нет.")
        return

    today = date.today()
    lines = [f"👥 *Студентов: {len(all_s)}*\n"]

    for s in all_s.values():
        uname    = f"@{s['username']}" if s.get("username") else "—"
        hw_count = sum(len(v) for v in s.get("hw_submitted", {}).values())
        last_m   = s.get("last_module")
        last_m_s = f"М{last_m}" if last_m is not None else "—"
        lines.append(
            f"• {s['name']} ({uname})\n"
            f"  🆔 `{s['id']}` · ДЗ сдано: {hw_count} · Посл. модуль: {last_m_s}"
        )

    text = "\n\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n\n...список обрезан"
    await message.answer(text, parse_mode="Markdown")


# ── Приём домашних заданий ────────────────────────────────────────────────────

@dp.message(~F.text.startswith("/"))
async def handle_submission(message: Message):
    user     = message.from_user
    uid      = user.id
    username = user.username or ""

    if not is_allowed(uid, username):
        await message.answer("🔒 У вас нет доступа к курсу.")
        return

    student = get_student(uid)
    if not student:
        await message.answer("Сначала напиши /start 👋")
        return

    today = date.today()

    # Найти модуль с открытым дедлайном (сортируем — берём ближайший)
    open_modules = [
        m for m in MODULES
        if m["hw_deadline"] >= today
        and str(m["number"]) not in student["hw_submitted"]
    ]

    if not open_modules:
        # Все сданы или все просрочены
        all_done = all(
            str(m["number"]) in student["hw_submitted"] for m in MODULES
        )
        if all_done:
            await message.answer("🎉 Ты уже сдал все домашние задания! Молодец!")
        else:
            await message.answer(
                "⏰ Все текущие дедлайны истекли.\n"
                "Если хочешь сдать с опозданием — напиши куратору напрямую."
            )
        return

    # Берём модуль с ближайшим дедлайном
    target_mod = min(open_modules, key=lambda m: m["hw_deadline"])
    dl_str     = target_mod["hw_deadline"].strftime("%d.%m.%Y")
    days_left  = (target_mod["hw_deadline"] - today).days

    # Пересылаем куратору
    if CURATOR_ID:
        uname = f" (@{username})" if username else ""
        try:
            await bot.send_message(
                CURATOR_ID,
                f"📥 *ДЗ · {target_mod['title']}*\n"
                f"👤 {user.full_name}{uname}\n"
                f"🆔 `{uid}`\n"
                f"📅 Дедлайн: {dl_str} (осталось {days_left} дн.)",
                parse_mode="Markdown",
            )
            await message.forward(CURATOR_ID)
        except Exception as e:
            log.error(f"Ошибка пересылки куратору: {e}")

    record_hw(uid, target_mod["number"])

    await message.answer(
        f"✅ *ДЗ принято!*\n\n"
        f"Модуль: *{target_mod['title']}*\n"
        f"Дедлайн: {dl_str}\n\n"
        f"Куратор проверит и даст обратную связь 🙌",
        parse_mode="Markdown",
    )


# ══════════════════════════════════════════════════════════════════════════════
#  НАПОМИНАНИЯ О ДЕДЛАЙНАХ
# ══════════════════════════════════════════════════════════════════════════════

async def job_reminders():
    """Каждое утро в 10:00 напоминает о дедлайне завтра."""
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
                    log.info(f"Напоминание → {student['name']} (М{mod['number']})")
                except Exception as e:
                    log.error(f"Ошибка напоминания {uid}: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  ЗАПУСК
# ══════════════════════════════════════════════════════════════════════════════

async def main():
    if BOT_TOKEN == "ВСТАВЬ_ТОКЕН":
        raise RuntimeError("Установи BOT_TOKEN в переменные окружения Render!")

    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    # Напоминания каждый день в 10:00
    scheduler.add_job(job_reminders, "cron", hour=10, minute=0)
    scheduler.start()

    log.info("✅ Бот запущен!")
    await dp.start_polling(bot, drop_pending_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
