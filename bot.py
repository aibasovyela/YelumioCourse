"""
bot.py — главный файл бота курса с системой доступа.

Команды куратора (только от CURATOR_ID):
  /add 123456789      — выдать доступ вручную
  /remove 123456789   — забрать доступ
  /students           — список всех студентов с доступом

Команды студентов:
  /start    — вход (попросит код, если настроен)
  /status   — прогресс и дедлайны
  /hw       — текущее задание
  /help     — помощь
"""

import logging
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import db
import schedule as sched
from config import (
    BOT_TOKEN, CURATOR_ID, TIMEZONE, MODULES,
    ACCESS_CODE, PAYMENT_URL,
    WELCOME_TEXT, HW_CONFIRM_TEXT, HW_CLOSED_TEXT, REMINDER_TEXT,
    NO_ACCESS_TEXT, ENTER_CODE_TEXT, WRONG_CODE_TEXT, CODE_OK_TEXT,
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# Состояния ConversationHandler для /start
WAITING_CODE = 1


# ══════════════════════════════════════════════════════════════════════════════
#  ПРОВЕРКА ДОСТУПА
# ══════════════════════════════════════════════════════════════════════════════

def curator_only(func):
    """Декоратор — только для куратора."""
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != CURATOR_ID:
            await update.message.reply_text("⛔ Эта команда только для куратора.")
            return
        return await func(update, ctx)
    return wrapper


# ══════════════════════════════════════════════════════════════════════════════
#  ОТПРАВКА МОДУЛЯ
# ══════════════════════════════════════════════════════════════════════════════

async def deliver_module(bot, student: dict, module: dict) -> None:
    uid = student["id"]

    await bot.send_message(chat_id=uid, text=module["text"], parse_mode="Markdown")

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("▶️  Смотреть видео", url=module["video"])
    ]])
    await bot.send_message(
        chat_id=uid,
        text="👆 Нажми, чтобы открыть видео",
        reply_markup=keyboard,
    )

    deadline     = sched.hw_deadline(student, module["number"])
    deadline_str = deadline.strftime("%d.%m.%Y") if deadline else "—"

    await bot.send_message(
        chat_id=uid,
        text=f"{module['hw_text']}\n\n📅 Дедлайн: *{deadline_str}*",
        parse_mode="Markdown",
    )

    db.mark_module_sent(uid, module["number"])
    log.info(f"Модуль {module['number']} → {student['name']} ({uid})")


# ══════════════════════════════════════════════════════════════════════════════
#  ВХОД / РЕГИСТРАЦИЯ (ConversationHandler)
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    uid  = user.id

    # Уже есть доступ → сразу в курс
    if db.has_access(uid):
        await _enter_course(update, ctx, user)
        return ConversationHandler.END

    # Код не настроен → только ручное добавление куратором
    if not ACCESS_CODE:
        await update.message.reply_text(
            NO_ACCESS_TEXT.format(payment_url=PAYMENT_URL),
            parse_mode="Markdown",
        )
        # Уведомляем куратора о попытке входа
        if CURATOR_ID:
            await ctx.bot.send_message(
                CURATOR_ID,
                f"🔔 Попытка входа без доступа:\n"
                f"👤 {user.full_name}"
                + (f" (@{user.username})" if user.username else "")
                + f"\n🆔 `{uid}`\n\n"
                f"Чтобы выдать доступ: /add {uid}",
                parse_mode="Markdown",
            )
        return ConversationHandler.END

    # Просим код
    await update.message.reply_text(ENTER_CODE_TEXT, parse_mode="Markdown")
    return WAITING_CODE


async def handle_code(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает введённый код доступа."""
    user      = update.effective_user
    entered   = update.message.text.strip()

    if entered == ACCESS_CODE:
        db.grant_access(user.id, user, method="code")
        await update.message.reply_text(CODE_OK_TEXT, parse_mode="Markdown")
        await _enter_course(update, ctx, user)

        # Уведомляем куратора
        if CURATOR_ID:
            await ctx.bot.send_message(
                CURATOR_ID,
                f"✅ Новый студент вошёл по коду:\n"
                f"👤 {user.full_name}"
                + (f" (@{user.username})" if user.username else "")
                + f"\n🆔 `{user.id}`",
                parse_mode="Markdown",
            )
        return ConversationHandler.END

    # Неверный код
    await update.message.reply_text(
        WRONG_CODE_TEXT.format(payment_url=PAYMENT_URL),
        parse_mode="Markdown",
    )
    return WAITING_CODE   # даём ещё попытку


async def _enter_course(update: Update, ctx: ContextTypes.DEFAULT_TYPE, user) -> None:
    """Финальный вход в курс: приветствие + Модуль 1."""
    student = db.register(user)

    await update.message.reply_text(
        WELCOME_TEXT.format(name=user.first_name),
        parse_mode="Markdown",
    )

    first = MODULES[0]
    if first["number"] not in student["modules_sent"]:
        await deliver_module(ctx.bot, student, first)


# ══════════════════════════════════════════════════════════════════════════════
#  КОМАНДЫ КУРАТОРА
# ══════════════════════════════════════════════════════════════════════════════

@curator_only
async def cmd_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /add 123456789  — выдать доступ по Telegram ID.
    Студенту сразу придёт уведомление.
    """
    if not ctx.args:
        await update.message.reply_text(
            "Использование: /add <telegram_id>\n"
            "Пример: /add 123456789\n\n"
            "Узнать ID студента: попроси его написать @userinfobot"
        )
        return

    try:
        target_id = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")
        return

    db.grant_access(target_id, method="manual")

    # Уведомляем куратора
    await update.message.reply_text(
        f"✅ Доступ выдан пользователю `{target_id}`.\n\n"
        f"Попроси его написать боту /start — курс откроется.",
        parse_mode="Markdown",
    )

    # Уведомляем студента
    try:
        await ctx.bot.send_message(
            target_id,
            "🎉 *Вам открыт доступ к курсу AI-Контент!*\n\n"
            "Напиши /start чтобы начать.",
            parse_mode="Markdown",
        )
    except Exception:
        await update.message.reply_text(
            "⚠️ Не удалось написать студенту — возможно, он ещё не запускал бота.\n"
            "Попроси его написать /start боту."
        )


@curator_only
async def cmd_remove(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/remove 123456789 — забрать доступ."""
    if not ctx.args:
        await update.message.reply_text("Использование: /remove <telegram_id>")
        return

    try:
        target_id = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")
        return

    ok = db.revoke_access(target_id)
    if ok:
        await update.message.reply_text(f"🚫 Доступ отозван у `{target_id}`.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"Пользователь `{target_id}` не найден в базе.", parse_mode="Markdown")


@curator_only
async def cmd_students(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/students — список всех студентов с доступом."""
    all_students = db.get_all_students()
    active = [s for s in all_students.values() if s.get("access")]

    if not active:
        await update.message.reply_text("Пока нет студентов с доступом.")
        return

    lines = [f"👥 *Студентов с доступом: {len(active)}*\n"]
    for s in active:
        day     = sched.days_since_start(s) if s.get("start_date") else "—"
        sent    = len(s.get("modules_sent", []))
        method  = "🔑 код" if s.get("access_method") == "code" else "👤 вручную"
        uname   = f"@{s['username']}" if s.get("username") else "нет юзернейма"
        lines.append(
            f"• {s['name']} ({uname})\n"
            f"  🆔 `{s['id']}` · {method}\n"
            f"  📦 Модулей: {sent}/8 · День: {day}"
        )

    # Telegram ограничивает длину — шлём частями если много студентов
    text = "\n\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n\n...и ещё (список обрезан)"

    await update.message.reply_text(text, parse_mode="Markdown")


# ══════════════════════════════════════════════════════════════════════════════
#  КОМАНДЫ СТУДЕНТОВ
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid     = update.effective_user.id
    if not db.has_access(uid):
        await update.message.reply_text(
            NO_ACCESS_TEXT.format(payment_url=PAYMENT_URL), parse_mode="Markdown"
        )
        return

    student = db.get_student(uid)
    if not student or not student.get("start_date"):
        await update.message.reply_text("Напиши /start чтобы начать курс 👋")
        return

    day  = sched.days_since_start(student)
    sent = student["modules_sent"]
    lines = [f"📊 *Твой прогресс* — день {day} из 45\n"]

    for mod in MODULES:
        n = mod["number"]
        if n in sent:
            deadline = sched.hw_deadline(student, n)
            count    = db.hw_count(student, n)
            hw_open  = sched.is_hw_open(student, n)
            icon     = "✅"
            status   = "Получен"
            if hw_open and deadline:
                status += f" · ДЗ до {deadline.strftime('%d.%m')}"
            if count:
                status += f" · {count} раб. сдано"
        elif day >= mod["day"]:
            icon, status = "🔓", "Скоро придёт"
        else:
            icon   = "🔒"
            status = f"Откроется через {mod['day'] - day} дн."

        lines.append(f"{icon} *{mod['title']}*\n    {status}")

    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown")


async def cmd_hw(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not db.has_access(uid):
        await update.message.reply_text(
            NO_ACCESS_TEXT.format(payment_url=PAYMENT_URL), parse_mode="Markdown"
        )
        return

    student = db.get_student(uid)
    if not student or not student.get("start_date"):
        await update.message.reply_text("Напиши /start чтобы начать курс 👋")
        return

    active = sched.active_hw_module(student)
    if not active:
        await update.message.reply_text(
            "Сейчас нет открытых заданий.\nОжидай следующий модуль — пришлю уведомление! 🔔"
        )
        return

    deadline = sched.hw_deadline(student, active["number"])
    await update.message.reply_text(
        f"📝 Открыто ДЗ к *{active['title']}*\n\n"
        f"{active['hw_text']}\n\n"
        f"📅 Дедлайн: *{deadline.strftime('%d.%m.%Y')}*\n\n"
        f"Просто отправь мне файл, фото, видео или текст!",
        parse_mode="Markdown",
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🤖 *Команды бота*\n\n"
        "/start — начать курс\n"
        "/status — прогресс и дедлайны\n"
        "/hw — текущее задание\n"
        "/help — это сообщение\n\n"
        "Для сдачи ДЗ просто отправь файл, фото или текст — бот всё поймёт 📤",
        parse_mode="Markdown",
    )


# ══════════════════════════════════════════════════════════════════════════════
#  ПРИЁМ ДОМАШНИХ ЗАДАНИЙ
# ══════════════════════════════════════════════════════════════════════════════

async def handle_submission(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user    = update.effective_user
    uid     = user.id

    # Проверка доступа
    if not db.has_access(uid):
        await update.message.reply_text(
            NO_ACCESS_TEXT.format(payment_url=PAYMENT_URL),
            parse_mode="Markdown",
        )
        return

    student = db.get_student(uid)
    if not student or not student.get("start_date"):
        await update.message.reply_text("Напиши /start чтобы начать курс 👋")
        return

    active = sched.active_hw_module(student)

    if not active:
        await update.message.reply_text(HW_CLOSED_TEXT, parse_mode="Markdown")
        return

    deadline = sched.hw_deadline(student, active["number"])

    # Пересылаем куратору
    if CURATOR_ID:
        header = (
            f"📥 *ДЗ · {active['title']}*\n"
            f"👤 {user.full_name}"
            + (f" (@{user.username})" if user.username else "")
            + f"\n🆔 `{uid}`"
            + f"\n📅 День {sched.days_since_start(student)}"
        )
        try:
            await ctx.bot.send_message(CURATOR_ID, header, parse_mode="Markdown")
            await update.message.forward(CURATOR_ID)
        except Exception as e:
            log.error(f"Ошибка пересылки куратору: {e}")

    db.record_hw(uid, active["number"])

    await update.message.reply_text(
        HW_CONFIRM_TEXT.format(
            module_title=active["title"],
            deadline=deadline.strftime("%d.%m.%Y"),
        ),
        parse_mode="Markdown",
    )


# ══════════════════════════════════════════════════════════════════════════════
#  ПЛАНИРОВЩИК
# ══════════════════════════════════════════════════════════════════════════════

async def job_send_modules(app: Application) -> None:
    students = db.get_all_students()
    for student in students.values():
        if not student.get("access") or not student.get("start_date"):
            continue
        for module in sched.modules_due(student):
            try:
                await deliver_module(app.bot, student, module)
            except Exception as e:
                log.error(f"Ошибка отправки М{module['number']} → {student['id']}: {e}")


async def job_reminders(app: Application) -> None:
    from datetime import timedelta
    now      = datetime.now()
    students = db.get_all_students()

    for student in students.values():
        if not student.get("access") or not student.get("start_date"):
            continue
        for mod_num in student["modules_sent"]:
            deadline = sched.hw_deadline(student, mod_num)
            if not deadline:
                continue
            hours_left = (deadline - now).total_seconds() / 3600
            if not (20 < hours_left <= 28):
                continue
            if db.hw_count(student, mod_num) > 0:
                continue
            mod = next((m for m in MODULES if m["number"] == mod_num), None)
            if not mod:
                continue
            try:
                await app.bot.send_message(
                    chat_id=student["id"],
                    text=REMINDER_TEXT.format(
                        module_title=mod["title"],
                        deadline=deadline.strftime("%d.%m.%Y"),
                    ),
                    parse_mode="Markdown",
                )
            except Exception as e:
                log.error(f"Ошибка напоминания {student['id']}: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  ЗАПУСК
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    if BOT_TOKEN == "ВСТАВЬ_ТОКЕН_СЮДА":
        raise RuntimeError("Установи BOT_TOKEN в config.py или переменную окружения!")

    app = Application.builder().token(BOT_TOKEN).build()

    # ConversationHandler для /start с вводом кода
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            WAITING_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_code)
            ],
        },
        fallbacks=[CommandHandler("start", cmd_start)],
    )
    app.add_handler(conv)

    # Команды куратора
    app.add_handler(CommandHandler("add",      cmd_add))
    app.add_handler(CommandHandler("remove",   cmd_remove))
    app.add_handler(CommandHandler("students", cmd_students))

    # Команды студентов
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("hw",     cmd_hw))
    app.add_handler(CommandHandler("help",   cmd_help))

    # Приём ДЗ — всё кроме команд
    app.add_handler(MessageHandler(
        filters.ALL & ~filters.COMMAND,
        handle_submission,
    ))

    # Планировщик
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    scheduler.add_job(job_send_modules, "interval", hours=1, args=[app])
    scheduler.add_job(job_reminders,   "interval", hours=1, args=[app])
    scheduler.start()

    log.info("✅ Бот запущен!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
