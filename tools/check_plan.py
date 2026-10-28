"""Проверка недельного плана правилами rules/plan.yaml и rules/rubrics.yaml.

Запуск: python tools/check_plan.py plans/2026-11-02.json [--root .]
Вывод: JSON-вердикт в stdout. Код: 0 — прошёл, 1 — отклонён, 2 — ошибка входа.
Повторы блюд ищутся в plans/*.json (кроме проверяемого) и runs/*/*/brief.json под --root.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import timedelta
from pathlib import Path

import yaml

from kitchen_common import (ROOT, SLUG, CheckError, dish_history, has_text, load_rules, parse_date, read_json,
                            recent_repeat, stop_words_in)

DISH_KEYS = ("dish", "slug", "rubric", "meal", "why")


def has_dish_fields(item: dict) -> bool:
    return all(has_text(item.get(key)) for key in DISH_KEYS)


def check_dish(item: dict, where: str, rules: dict) -> list[str]:
    """Поля блюда — общие для слота плана и brief.json."""
    reasons = [f"{where}: нет поля {key}" for key in DISH_KEYS if not has_text(item.get(key))]
    if reasons:
        return reasons
    if not SLUG.match(item["slug"]):
        reasons.append(f"{where}: slug «{item['slug']}» — только латиница, цифры и дефисы")
    rubric = rules["rubrics"].get(item["rubric"])
    if rubric is None:
        reasons.append(f"{where}: неизвестная рубрика {item['rubric']}")
    elif rubric.get("meals") and item["meal"] not in rubric["meals"]:
        reasons.append(f"{where}: рубрика {item['rubric']} — только для: {', '.join(rubric['meals'])}")
    if item["meal"] not in rules["plan"]["meals"]:
        reasons.append(f"{where}: неизвестный приём пищи {item['meal']}")
    for word in stop_words_in(f"{item['dish']} {item['why']}", rules["stopwords"]["stop_words"]):
        reasons.append(f"{where}: стоп-слово: {word}")
    return reasons


def check_plan(plan, rules: dict, history: set) -> list[str]:
    if not isinstance(plan, dict) or not isinstance(plan.get("days"), list):
        raise CheckError("в плане нет списка days")
    limits = rules["plan"]
    start = parse_date(plan.get("week_start"), "week_start")
    reasons = []
    if len(plan["days"]) != limits["days"]:
        reasons.append(f"дней в плане {len(plan['days'])}, нужно {limits['days']}")
    slugs, rubrics = Counter(), Counter()
    for i, day in enumerate(plan["days"]):
        if not isinstance(day, dict) or not isinstance(day.get("slots"), list):
            raise CheckError(f"день {i + 1}: нет списка slots")
        current = parse_date(day.get("date"), f"день {i + 1}")
        expected = start + timedelta(days=i)
        if current != expected:
            reasons.append(f"день {i + 1}: дата {current}, ожидалась {expected}")
        if len(day["slots"]) != limits["slots_per_day"]:
            reasons.append(f"{current}: блюд {len(day['slots'])}, нужно {limits['slots_per_day']}")
        meals = Counter()
        for j, slot in enumerate(day["slots"], 1):
            where = f"{current} слот {j}"
            if not isinstance(slot, dict):
                raise CheckError(f"{where}: слот должен быть объектом")
            if slot.get("slot") != j:
                reasons.append(f"{where}: номер слота {slot.get('slot')}, ожидался {j}")
            reasons += check_dish(slot, where, rules)
            if not has_dish_fields(slot):
                continue
            slugs[slot["slug"]] += 1
            rubrics[slot["rubric"]] += 1
            meals[slot["meal"]] += 1
            seen = recent_repeat(slot["slug"], current, history, limits["repeat_days"])
            if seen:
                reasons.append(f"{where}: «{slot['dish']}» ({slot['slug']}) уже есть на {seen} — повтор ближе "
                               f"{limits['repeat_days']} дней")
        for meal, count in meals.items():
            if count > 1:
                reasons.append(f"{current}: «{meal}» два раза — приёмы пищи в день разные")
    for slug, count in slugs.items():
        if count > 1:
            reasons.append(f"блюдо {slug} в плане {count} раза")
    total = sum(rubrics.values())
    for rubric, count in rubrics.items():
        if count / total > limits["max_rubric_share"]:
            reasons.append(f"рубрика {rubric}: {count} из {total} — больше доли {limits['max_rubric_share']}")
    return reasons


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--rules-dir", type=Path, default=ROOT / "rules")
    parser.add_argument("--root", type=Path, default=ROOT, help="корень с plans/ и runs/ — для поиска повторов")
    args = parser.parse_args(argv)
    try:
        rules = load_rules(args.rules_dir)
        plan = read_json(args.plan, "план")
        reasons = check_plan(plan, rules, dish_history(args.root, skip=args.plan))
    except (CheckError, OSError, yaml.YAMLError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"ok": not reasons, "reasons": reasons}, ensure_ascii=False))
    return 0 if not reasons else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
