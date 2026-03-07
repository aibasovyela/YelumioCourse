"""
bot.py — бот курса AI-Контент (aiogram 3)

Логика:
- При /start выходит приветствие + 8 кнопок модулей
- Нажимаешь кнопку → текст модуля + кнопка видео + кнопка материалов + ДЗ
- Доступ по белому списку username/ID
- Видео закрываются через 3 месяца
- /status, /calls, /help
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

BOT_TOKEN  = os.getenv("BOT_TOKEN", "7992712058:AAFBwAD25j1yh3PCL_ELcWiKL9XVspQW8oc")
CURATOR_ID = int(os.getenv("CURATOR_ID", "910046222"))
DB_FILE    = "students.json"
TIMEZONE   = "Asia/Almaty"

COURSE_START   = date(2026, 3, 10)
ACCESS_MONTHS  = 3
CALENDLY_URL   = "https://calendly.com/aibasovyela/30min"

# Белый список — username строчными без @ или числовой ID
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
    # Добавляй числовые ID сюда если нужно:
    # 123456789,
}

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
#  МОДУЛИ
# ══════════════════════════════════════════════════════════════════════════════

MODULES = [
    {
        "number":      0,
        "title":       "Модуль 0 — Введение",
        "emoji":       "🎯",
        "hw_deadline": date(2026, 3, 13),
        "video":       "https://youtu.be/ССЫЛКА_МОДУЛЬ_0",
        "materials":   None,  # нет материалов для модуля 0
        "text": (
            "🎯 *Модуль 0 — Введение*\n\n"
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
        "number":      1,
        "title":       "Модуль 1 — Идея и концепция",
        "emoji":       "💡",
        "hw_deadline": date(2026, 3, 17),
        "video":       "https://youtu.be/ССЫЛКА_МОДУЛЬ_1",
        "materials":   "https://www.canva.com/folder/FAHDR6SvHuM",
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
        "video":       "https://youtu.be/ССЫЛКА_МОДУЛЬ_2",
        "materials":   "https://www.canva.com/folder/FAHDR93073M",
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
        "number":      3,
        "title":       "Модуль 3 — ИИ-фото",
        "emoji":       "📸",
        "hw_deadline": date(2026, 3, 27),
        "video":       "https://youtu.be/ССЫЛКА_МОДУЛЬ_3",
        "materials":   "https://www.canva.com/folder/FAHDR9aQ0nE",
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
        "number":      4,
        "title":       "Модуль 4 — ИИ-видео",
        "emoji":       "🎥",
        "hw_deadline": date(2026, 3, 31),
        "video":       "https://youtu.be/ССЫЛКА_МОДУЛЬ_4",
        "materials":   "https://www.canva.com/folder/FAHDR0DkVZ0",
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
        "video":       "https://youtu.be/ССЫЛКА_МОДУЛЬ_5",
        "materials":   "https://www.canva.com/folder/FAHDR2Mlg3o",
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
        "video":       "https://youtu.be/ССЫЛКА_МОДУЛЬ_6",
        "materials":   "https://drive.google.com/drive/folders/1C5T1X91x-nnAVg0F2GnlEpHb1W52QHbq?usp=sharing",
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
        "number":      7,
        "title":       "Модуль 7 — Портфолио и заработок",
        "emoji":       "💼",
        "hw_deadline": date(2026, 4, 15),
        "video":       "https://youtu.be/ССЫЛКА_МОДУЛЬ_7",
        "materials":   "https://www.canva.com/folder/FAHDR2Mlg3o",
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

HW_DAYS = 5

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
            "hw_submitted": {},
            "last_module":  None,
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

def modules_menu_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с 8 кнопками модулей — по 2 в ряд."""
    buttons = []
    row = []
    for mod in MODULES:
        btn = InlineKeyboardButton(
            text=f"{mod['emoji']} М{mod['number']}",
            callback_data=f"module_{mod['number']}",
        )
        row.append(btn)
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def module_content_keyboard(mod: dict) -> InlineKeyboardMarkup:
    """Кнопки видео + материалы для конкретного модуля."""
    buttons = []
    if videos_open():
        buttons.append([InlineKeyboardButton(
            text="▶️ Смотреть видео",
            url=mod["video"],
        )])
    else:
        buttons.append([InlineKeyboardButton(
            text="🔒 Видео недоступно (истёк срок)",
            callback_data="video_expired",
        )])
    if mod.get("materials"):
        buttons.append([InlineKeyboardButton(
            text="📂 Материалы к модулю",
            url=mod["materials"],
        )])
    # Кнопка назад
    buttons.append([InlineKeyboardButton(
        text="◀️ Назад к модулям",
        callback_data="back_to_menu",
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

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

    if not is_allowed(uid, username):
        await message.answer(
            "🔒 *Доступ закрыт*\n\n"
            "Этот бот только для участников курса *AI-Контент*.\n\n"
            "Если ты купил курс — напиши куратору для получения доступа.",
            parse_mode="Markdown",
        )
        if CURATOR_ID:
            uname = f" (@{username})" if username else ""
            await bot.send_message(
                CURATOR_ID,
                f"🔔 Попытка входа без доступа:\n"
                f"👤 {user.full_name}{uname}\n"
                f"🆔 `{uid}`",
                parse_mode="Markdown",
            )
        return

    upsert_student(uid, user.full_name, username)

    await message.answer(
        f"👋 Привет, *{user.first_name}*!\n\n"
        "Добро пожаловать в курс *AI-Контент* 🎉\n\n"
        "Выбери модуль который хочешь открыть 👇",
        parse_mode="Markdown",
        reply_markup=modules_menu_keyboard(),
    )


@dp.message(Command("menu"))
async def cmd_menu(message: Message):
    user     = message.from_user
    uid      = user.id
    username = user.username or ""

    if not is_allowed(uid, username):
        await message.answer("🔒 У вас нет доступа к курсу.")
        return

    await message.answer(
        "📚 *Модули курса*\n\nВыбери модуль 👇",
        parse_mode="Markdown",
        reply_markup=modules_menu_keyboard(),
    )


# Нажатие на кнопку модуля
@dp.callback_query(F.data.startswith("module_"))
async def cb_module(call: CallbackQuery):
    uid      = call.from_user.id
    username = call.from_user.username or ""

    if not is_allowed(uid, username):
        await call.answer("🔒 Нет доступа", show_alert=True)
        return

    mod_num = int(call.data.split("_")[1])
    mod     = next((m for m in MODULES if m["number"] == mod_num), None)
    if not mod:
        await call.answer("Модуль не найден", show_alert=True)
        return

    set_last_module(uid, mod_num)

    today     = date.today()
    dl        = mod["hw_deadline"]
    dl_str    = dl.strftime("%d.%m.%Y")
    days_left = (dl - today).days
    student   = get_student(uid)
    hw_done   = str(mod_num) in (student or {}).get("hw_submitted", {})

    if days_left > 0:
        deadline_line = f"📅 Дедлайн ДЗ: *{dl_str}* (осталось {days_left} дн.)"
    elif days_left == 0:
        deadline_line = f"📅 Дедлайн ДЗ: *{dl_str}* — сегодня последний день! ⚠️"
    else:
        deadline_line = f"📅 Дедлайн ДЗ: *{dl_str}* — истёк"

    hw_status = "✅ ДЗ уже сдано!" if hw_done else mod["hw_text"]

    text = (
        f"{mod['text']}\n\n"
        f"{'─' * 20}\n"
        f"{hw_status}\n\n"
        f"{deadline_line}"
    )

    await call.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=module_content_keyboard(mod),
    )
    await call.answer()


# Назад к меню модулей
@dp.callback_query(F.data == "back_to_menu")
async def cb_back(call: CallbackQuery):
    await call.message.edit_text(
        "📚 *Модули курса*\n\nВыбери модуль 👇",
        parse_mode="Markdown",
        reply_markup=modules_menu_keyboard(),
    )
    await call.answer()


# Видео истекло
@dp.callback_query(F.data == "video_expired")
async def cb_expired(call: CallbackQuery):
    await call.answer(
        "🔒 Доступ к видео закрыт — истёк срок 3 месяца.",
        show_alert=True,
    )


# /status
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
    hw    = student.get("hw_submitted", {})
    lines = [f"📊 *Твой прогресс*\n"]

    # Последний открытый модуль
    last_mod_num = student.get("last_module")
    if last_mod_num is not None:
        last_mod = next((m for m in MODULES if m["number"] == last_mod_num), None)
        if last_mod:
            lines.append(f"📖 *Последний модуль:*\n    {last_mod['title']}\n")

    # Последнее сданное ДЗ
    if hw:
        last_hw_num = max(int(k) for k in hw.keys())
        last_hw_mod = next((m for m in MODULES if m["number"] == last_hw_num), None)
        if last_hw_mod:
            dt = datetime.fromisoformat(hw[str(last_hw_num)][-1]).strftime("%d.%m в %H:%M")
            lines.append(f"✅ *Последнее ДЗ:*\n    {last_hw_mod['title']}\n    Сдано: {dt}\n")
    else:
        lines.append("📝 *ДЗ:* ещё не сдавал\n")

    # Таблица дедлайнов
    lines.append("*Дедлайны ДЗ:*")
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

        lines.append(f"  {icon} {mod['emoji']} {mod['title']}\n      до {dl.strftime('%d.%m')}")

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📚 Открыть модули", callback_data="back_to_menu")
    ]])

    await message.answer("\n".join(lines), parse_mode="Markdown", reply_markup=kb)


# /calls
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
        "• Длительность — 45 минут\n\n"
        "Выбери удобные дату и время 👇",
        parse_mode="Markdown",
        reply_markup=kb,
    )


# /help
@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "🤖 *Команды бота*\n\n"
        "/start — главное меню с модулями\n"
        "/menu — открыть меню модулей\n"
        "/status — твой прогресс и дедлайны\n"
        "/calls — записаться на созвон\n"
        "/help — это сообщение\n\n"
        "📤 *Сдача ДЗ:*\n"
        "Просто отправь файл, фото, видео или текст — бот всё примет!",
        parse_mode="Markdown",
    )


# /students — только куратор
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
        last_s   = f"М{last_m}" if last_m is not None else "—"
        lines.append(
            f"• {s['name']} ({uname})\n"
            f"  🆔 `{s['id']}` · ДЗ: {hw_count} · Посл: {last_s}"
        )

    text = "\n\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n\n...список обрезан"
    await message.answer(text, parse_mode="Markdown")


# Приём ДЗ — любой контент не команда
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

    # Модуль с ближайшим открытым дедлайном куда ещё не сдавал
    open_modules = [
        m for m in MODULES
        if m["hw_deadline"] >= today
        and str(m["number"]) not in student["hw_submitted"]
    ]

    if not open_modules:
        all_done = all(str(m["number"]) in student["hw_submitted"] for m in MODULES)
        if all_done:
            await message.answer("🎉 Ты уже сдал все домашние задания! Молодец!")
        else:
            await message.answer(
                "⏰ Все текущие дедлайны истекли.\n"
                "Если хочешь сдать с опозданием — напиши куратору напрямую."
            )
        return

    target = min(open_modules, key=lambda m: m["hw_deadline"])
    dl_str = target["hw_deadline"].strftime("%d.%m.%Y")

    # Пересылаем куратору
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
        InlineKeyboardButton(text="📚 Открыть модули", callback_data="back_to_menu")
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
#  НАПОМИНАНИЯ
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
