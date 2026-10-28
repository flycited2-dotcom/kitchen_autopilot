"""Блюда дня из недельного плана; с --write создаёт runs/<дата>/<NN>-<slug>/brief.json.

Запуск: python tools/plan_day.py 2026-11-04 [--write] [--root .]
Вывод: JSON {"date", "plan", "slots": [brief…], "created", "kept"}.
Код: 0 — блюда есть, 1 — плана на эту дату нет, 2 — ошибка входа.
Существующий brief.json не перезаписывается (владелец мог его поправить).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from kitchen_common import ROOT, CheckError, has_text, is_int, parse_date, read_json

BRIEF_KEYS = ("dish", "slug", "rubric", "meal", "why")


def find_plan(root: Path, iso: str) -> tuple[Path, dict] | tuple[None, None]:
    """Последний по имени план, в котором есть эта дата."""
    found = (None, None)
    for path in sorted(Path(root).glob("plans/*.json")):
        try:
            plan = read_json(path, "план")
        except CheckError:
            continue
        days = plan.get("days") if isinstance(plan, dict) else None
        if isinstance(days, list) and any(isinstance(day, dict) and day.get("date") == iso for day in days):
            found = (path, plan)
    return found


def briefs_for(plan: dict, iso: str) -> list[dict]:
    day = next(day for day in plan["days"] if isinstance(day, dict) and day.get("date") == iso)
    slots = day.get("slots")
    if not isinstance(slots, list):
        raise CheckError(f"{iso}: в плане нет списка slots")
    briefs = []
    for i, slot in enumerate(slots, 1):
        if not isinstance(slot, dict) or not is_int(slot.get("slot")):
            raise CheckError(f"{iso} слот {i}: нет номера slot")
        missing = [key for key in BRIEF_KEYS if not has_text(slot.get(key))]
        if missing:
            raise CheckError(f"{iso} слот {i}: нет полей {', '.join(missing)} — сначала check_plan.py")
        briefs.append({"id": f"{iso}-{slot['slot']:02d}-{slot['slug']}", "date": iso, "slot": slot["slot"],
                       **{key: slot[key] for key in BRIEF_KEYS}})
    return briefs


def write_briefs(root: Path, briefs: list[dict]) -> tuple[list[str], list[str]]:
    created, kept = [], []
    for brief in briefs:
        relative = f"runs/{brief['date']}/{brief['slot']:02d}-{brief['slug']}"
        path = Path(root) / relative / "brief.json"
        if path.exists():
            kept.append(relative)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")
        created.append(relative)
    return created, kept


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("date")
    parser.add_argument("--write", action="store_true", help="создать папки дня и brief.json")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        iso = parse_date(args.date, "дата").isoformat()
        path, plan = find_plan(args.root, iso)
        briefs = briefs_for(plan, iso) if plan else []
        created, kept = write_briefs(args.root, briefs) if args.write else ([], [])
    except (CheckError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    plan_name = path.relative_to(args.root).as_posix() if path else None
    print(json.dumps({"date": iso, "plan": plan_name, "slots": briefs, "created": created, "kept": kept},
                     ensure_ascii=False))
    return 0 if briefs else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
