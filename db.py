"""db.py — JSON-база студентов с системой доступа."""

import json
import logging
from datetime import datetime
from pathlib import Path

from config import DB_FILE

log = logging.getLogger(__name__)


def _load() -> dict:
    if Path(DB_FILE).exists():
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save(db: dict) -> None:
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


# ── Доступ ────────────────────────────────────────────────────────────────────

def has_access(user_id: int) -> bool:
    """Проверяет, есть ли у пользователя доступ к курсу."""
    db  = _load()
    uid = str(user_id)
    return uid in db and db[uid].get("access", False)


def grant_access(user_id: int, user=None, method: str = "code") -> dict:
    """
    Выдаёт доступ пользователю.
    method: "code" — ввёл код, "manual" — добавлен куратором вручную.
    """
    db  = _load()
    uid = str(user_id)

    if uid not in db:
        db[uid] = {
            "id":           user_id,
            "name":         user.full_name if user else str(user_id),
            "username":     (user.username or "") if user else "",
            "start_date":   None,      # заполнится при финальной регистрации
            "access":       False,
            "access_granted": None,
            "access_method":  None,
            "modules_sent": [],
            "hw_submitted": {},
        }

    db[uid]["access"]         = True
    db[uid]["access_granted"] = datetime.now().isoformat()
    db[uid]["access_method"]  = method
    if user:
        db[uid]["name"]     = user.full_name
        db[uid]["username"] = user.username or ""

    _save(db)
    log.info(f"Доступ выдан: {db[uid]['name']} ({user_id}) [{method}]")
    return db[uid]


def revoke_access(user_id: int) -> bool:
    """Отзывает доступ у пользователя."""
    db  = _load()
    uid = str(user_id)
    if uid not in db:
        return False
    db[uid]["access"] = False
    _save(db)
    log.info(f"Доступ отозван: {uid}")
    return True


# ── Студенты ──────────────────────────────────────────────────────────────────

def get_all_students() -> dict:
    return _load()


def get_student(user_id: int) -> dict | None:
    return _load().get(str(user_id))


def register(user) -> dict:
    """Финальная регистрация после получения доступа — фиксируем start_date."""
    db  = _load()
    uid = str(user.id)

    # Запись уже есть (создана при grant_access) — просто обновляем
    if uid not in db:
        db[uid] = {
            "id":             user.id,
            "name":           user.full_name,
            "username":       user.username or "",
            "access":         True,
            "access_granted": datetime.now().isoformat(),
            "access_method":  "direct",
            "modules_sent":   [],
            "hw_submitted":   {},
        }

    # Фиксируем дату старта только один раз
    if not db[uid].get("start_date"):
        db[uid]["start_date"] = datetime.now().isoformat()
        db[uid]["name"]       = user.full_name
        db[uid]["username"]   = user.username or ""
        _save(db)
        log.info(f"Старт курса: {user.full_name} ({user.id})")

    return db[uid]


def mark_module_sent(user_id: int, module_number: int) -> None:
    db  = _load()
    uid = str(user_id)
    if uid in db and module_number not in db[uid]["modules_sent"]:
        db[uid]["modules_sent"].append(module_number)
        _save(db)


def record_hw(user_id: int, module_number: int) -> None:
    db  = _load()
    uid = str(user_id)
    key = str(module_number)
    if uid in db:
        db[uid]["hw_submitted"].setdefault(key, [])
        db[uid]["hw_submitted"][key].append(datetime.now().isoformat())
        _save(db)


def hw_count(student: dict, module_number: int) -> int:
    return len(student["hw_submitted"].get(str(module_number), []))


def count_with_access() -> int:
    db = _load()
    return sum(1 for s in db.values() if s.get("access"))
