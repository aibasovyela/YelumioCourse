"""schedule.py — логика расписания модулей и дедлайнов ДЗ."""

from datetime import datetime, timedelta

from config import MODULES, HW_DAYS


def days_since_start(student: dict) -> int:
    start = datetime.fromisoformat(student["start_date"])
    return (datetime.now() - start).days


def module_unlock_date(student: dict, module: dict) -> datetime:
    start = datetime.fromisoformat(student["start_date"])
    return start + timedelta(days=module["day"])


def hw_deadline(student: dict, module_number: int) -> datetime | None:
    mod = _find_module(module_number)
    if not mod:
        return None
    return module_unlock_date(student, mod) + timedelta(days=HW_DAYS)


def is_hw_open(student: dict, module_number: int) -> bool:
    """ДЗ принимается если модуль отправлен и дедлайн не истёк."""
    if module_number not in student["modules_sent"]:
        return False
    deadline = hw_deadline(student, module_number)
    return deadline is not None and datetime.now() < deadline


def active_hw_module(student: dict) -> dict | None:
    """Последний модуль с открытым окном ДЗ."""
    for mod_num in reversed(student["modules_sent"]):
        if is_hw_open(student, mod_num):
            return _find_module(mod_num)
    return None


def modules_due(student: dict) -> list[dict]:
    """Модули, которые уже пора отправить, но ещё не отправлены."""
    day  = days_since_start(student)
    sent = student["modules_sent"]
    return [m for m in MODULES if m["number"] not in sent and day >= m["day"]]


def _find_module(number: int) -> dict | None:
    return next((m for m in MODULES if m["number"] == number), None)
