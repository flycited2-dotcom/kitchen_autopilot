"""Общее для проверок кухни: чтение JSON и правил, нормализация текста, числа, стоп-слова, история блюд.

Логика стоп-слов и «каждое число подтверждено» перенесена из all_content_autopilot/tools/check_draft.py.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RULE_FILES = ("plan", "rubrics", "recipe", "food_safety", "stopwords", "shots", "video", "platforms")

_GROUPED = re.compile(r"(?<=\d)[   ](?=\d{3}(?!\d))")
_NUMBER = re.compile(r"[0-9]+(?:[.,][0-9]+)?")
_KEYCAP = re.compile(r"[0-9]️?⃣")
_URL = re.compile(r"https?://\S+")
_HASHTAG_IN_TEXT = re.compile(r"#\S+")
_LIST_MARKER = re.compile(r"(?m)^\s*\d+[.)]\s")
_SPACED_PERCENT = re.compile(r"(?<=\d)\s+%")
_WORD = re.compile(r"[0-9A-Za-zА-Яа-яЁё]+(?:[-'][0-9A-Za-zА-Яа-яЁё]+)*")
# «руб» — только как валюта: «рубленый», «порубить», «рублю» не цена.
PRICE = re.compile(r"₽|\bруб(?:\.|лей|ля|ль)?(?![а-яё])|\d\s*р\.|\bRUB\b", re.IGNORECASE)
HASHTAG = re.compile(r"^#[0-9a-zа-яё_]+$", re.IGNORECASE)
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class CheckError(ValueError):
    """Вход нельзя проверить: нет файла, не JSON, не та структура."""


def read_json(path: Path, what: str):
    path = Path(path)
    if not path.is_file():
        raise CheckError(f"нет файла {path.name}")
    try:
        return json.loads(path.read_bytes().decode("utf-8-sig"))
    except UnicodeDecodeError as exc:
        raise CheckError(f"{what} не в кодировке UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise CheckError(f"{what} не JSON: {exc}") from exc


def load_yaml(path: Path):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def load_rules(rules_dir: Path = ROOT / "rules") -> dict:
    rules = {}
    for name in RULE_FILES:
        path = Path(rules_dir) / f"{name}.yaml"
        if not path.is_file():
            raise CheckError(f"нет правил {path.name}")
        rules[name] = load_yaml(path)
    return rules


def parse_date(value, what: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CheckError(f"{what}: дата не в формате ГГГГ-ММ-ДД ({value!r})") from exc


def is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def has_text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def as_dict(value) -> dict:
    """Зависимость другого раздела с битой структурой — как пустой объект: ошибку покажет её собственный раздел."""
    return value if isinstance(value, dict) else {}


def normalize(text: str) -> str:
    text = text.casefold().replace("ё", "е").replace(" ", " ").replace(" ", " ")
    return _SPACED_PERCENT.sub("%", text)


def has_stem(normalized_text: str, stem: str) -> bool:
    """Основа ищется с начала слова: «лечит» ловит «ЛЕЧИТ», но не «излечиться»."""
    return re.search(rf"(?<![0-9a-zа-я]){re.escape(normalize(stem))}", normalized_text) is not None


def stop_words_in(text: str, words: list[str]) -> list[str]:
    lowered = normalize(text)
    return [word for word in words if has_stem(lowered, word)]


def forbidden_words(text: str, words: list[str]) -> list[str]:
    """Целые слова (английские запреты в промптах): «text» ловится, «textured» — нет."""
    lowered = text.casefold()
    return [word for word in words
            if re.search(rf"(?<![0-9a-zа-я]){re.escape(word.casefold())}(?![0-9a-zа-я])", lowered)]


def count_words(text: str) -> int:
    return len(_WORD.findall(text))


def canon_number(value) -> str:
    number = float(str(value).replace(",", "."))
    return str(int(number)) if number.is_integer() else f"{number:g}"


def numbers(text: str) -> set[str]:
    """Числа текста без URL, хештегов, эмодзи-цифр (1️⃣) и маркеров нумерованного списка («1. …»)."""
    text = _KEYCAP.sub(" ", text)
    text = _LIST_MARKER.sub(" ", _URL.sub(" ", _HASHTAG_IN_TEXT.sub(" ", text)))
    return {canon_number(value) for value in _NUMBER.findall(_GROUPED.sub("", text))}


def _try_json(path: Path):
    try:
        return read_json(path, path.name)
    except CheckError:
        return None


def dish_history(root: Path, skip: Path | None = None) -> set[tuple[str, str]]:
    """(slug, дата) запланированных и сделанных блюд: plans/*.json и runs/*/*/brief.json."""
    root = Path(root)
    skip = Path(skip).resolve() if skip else None
    items = set()
    for path in sorted(root.glob("plans/*.json")):
        if skip and path.resolve() == skip:
            continue
        plan = _try_json(path)
        days = plan.get("days") if isinstance(plan, dict) else None
        for day in days if isinstance(days, list) else []:
            slots = day.get("slots") if isinstance(day, dict) else None
            for slot in slots if isinstance(slots, list) else []:
                if isinstance(slot, dict) and has_text(slot.get("slug")) and has_text(day.get("date")):
                    items.add((slot["slug"], day["date"]))
    for path in sorted(root.glob("runs/*/*/brief.json")):
        if skip and path.resolve() == skip:
            continue
        brief = _try_json(path)
        if isinstance(brief, dict) and has_text(brief.get("slug")) and has_text(brief.get("date")):
            items.add((brief["slug"], brief["date"]))
    return items


def recent_repeat(slug: str, day: date, history: set, repeat_days: int) -> str | None:
    """Дата, когда это блюдо уже было или будет ближе repeat_days дней. Само блюдо в свою дату — не повтор."""
    for other_slug, other_date in sorted(history):
        if other_slug != slug or other_date == day.isoformat():
            continue
        try:
            other = date.fromisoformat(other_date)
        except ValueError:
            continue
        if abs((other - day).days) < repeat_days:
            return other_date
    return None
