"""Валидный пакет блюда для тестов: боул с тунцом (тот же пример, что в .claude/agents/recipe-developer.md)."""
from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATE = "2026-11-02"
SLUG = "boul-s-tuncom"
ID = f"{DATE}-01-{SLUG}"
FOLDER = f"01-{SLUG}"

STYLE = ("Photorealistic food photography for a vertical 9:16 cooking short. The same set in every shot: "
         "light oak wooden table, matte off-white ceramic bowl. Soft natural daylight from the left. "
         "No text, no logos, no watermarks, no brand packaging.")

BRIEF = {
    "id": ID, "date": DATE, "slot": 1, "dish": "Боул с тунцом и шпинатом", "slug": SLUG,
    "rubric": "recept_30s", "meal": "обед", "why": "Быстрый сытный обед из продуктов обычного магазина.",
}

RECIPE = {
    "id": ID,
    "dish": "Боул с тунцом и шпинатом",
    "servings": 2,
    "time_total_min": 25,
    "ingredients": [
        {"name": "рис", "qty": 150, "unit": "г"},
        {"name": "стейк тунца", "qty": 250, "unit": "г"},
        {"name": "шпинат свежий", "qty": 60, "unit": "г"},
        {"name": "огурец", "qty": 1, "unit": "шт"},
        {"name": "авокадо", "qty": 1, "unit": "шт"},
        {"name": "соевый соус", "qty": 2, "unit": "ст. л."},
        {"name": "кунжут", "qty": 1, "unit": "ч. л."},
        {"name": "масло растительное", "qty": 1, "unit": "ст. л."},
        {"name": "соль", "qty": None, "unit": "по вкусу"},
    ],
    "steps": [
        {"n": 1, "text": "Промыть рис и отварить до готовности по инструкции на упаковке.",
         "uses": ["рис"], "time_min": 15},
        {"n": 2, "text": "Тунец посолить и обжарить на разогретом масле по 1–2 минуты с каждой стороны, "
                         "нарезать ломтиками.",
         "uses": ["стейк тунца", "масло растительное", "соль"], "time_min": 5},
        {"n": 3, "text": "Огурец нарезать тонкими кружками, авокадо — кубиками.",
         "uses": ["огурец", "авокадо"], "time_min": 5},
        {"n": 4, "text": "Выложить в миски рис, шпинат, огурец, авокадо и тунец, полить соевым соусом "
                         "и посыпать кунжутом.",
         "uses": ["рис", "шпинат свежий", "огурец", "авокадо", "стейк тунца", "соевый соус", "кунжут"]},
    ],
    "safety_notes": ["Тунец с сырой серединой — только рыба глубокой заморозки для сырого употребления."],
}

# (kind, step, angle, описание) — 20 кадров, все шаги рецепта покрыты process-кадрами.
_SHOT_PLAN = [
    ("hero", None, "top-down 90°", "finished tuna bowl"),
    ("hero", None, "45°", "finished tuna bowl with chopsticks"),
    ("ingredients", None, "top-down 90°", "all raw ingredients laid out"),
    ("ingredients", None, "eye level", "tuna steak, avocado and cucumber"),
    ("process", 1, "45°", "rinsing rice in a sieve"),
    ("process", 1, "close-up macro", "cooked rice in a pot"),
    ("process", 2, "45°", "tuna steak searing in a pan"),
    ("process", 2, "close-up macro", "seared tuna edge"),
    ("process", 2, "eye level", "slicing seared tuna"),
    ("process", 3, "top-down 90°", "slicing cucumber into thin rounds"),
    ("process", 3, "hands close-up", "dicing avocado"),
    ("process", 4, "top-down 90°", "arranging rice and spinach in the bowl"),
    ("process", 4, "45°", "drizzling soy sauce over the bowl"),
    ("detail", None, "close-up macro", "sesame seeds on tuna slices"),
    ("detail", None, "close-up macro", "fresh spinach leaves"),
    ("serving", None, "45°", "bowl served with a napkin"),
    ("serving", None, "eye level", "two bowls ready to eat"),
    ("serving", None, "top-down 90°", "bowl with chopsticks on the side"),
    ("detail", None, "low angle", "glossy avocado cubes"),
    ("cover", None, "eye level", "bowl in the lower two thirds, calm empty background above"),
]

SHOTS = {
    "id": ID,
    "style_block": STYLE,
    "shots": [
        {"n": n, "kind": kind, "step": step, "angle": angle, "title_ru": f"Кадр {n}",
         "prompt": f"{desc.capitalize()}, the same matte off-white ceramic bowl on the light oak table, "
                   f"soft window light from the left."}
        for n, (kind, step, angle, desc) in enumerate(_SHOT_PLAN, 1)
    ],
}

TECHNICAL = ("Vertical 9:16 cooking short, about 30 seconds, photorealistic home kitchen look. Each clip starts "
             "from the attached photo and keeps the same bowl, table and window light. Smooth slow camera moves, "
             "natural steam and sizzling sounds, no people faces, hands only when needed.")

VIDEO_BRIEF = {
    "id": ID,
    "technical_description": TECHNICAL,
    "cover_shot": 20,
    "scenes": [
        {"n": 1, "shot": 16, "seconds": 4, "camera": "slow push-in",
         "motion_prompt": "Steam gently rising, sesame seeds glistening.", "title": "Боул с тунцом"},
        {"n": 2, "shot": 3, "seconds": 4, "camera": "slow top-down pan",
         "motion_prompt": "Ingredients slightly shifting as light moves.", "title": "Всего 9 продуктов"},
        {"n": 3, "shot": 5, "seconds": 4, "camera": "static",
         "motion_prompt": "Water running over rice in the sieve.", "title": "Рис — 150 г"},
        {"n": 4, "shot": 7, "seconds": 5, "camera": "slow push-in",
         "motion_prompt": "Tuna sizzling, oil bubbling around the edges.", "title": "Тунец — по 1–2 минуты"},
        {"n": 5, "shot": 10, "seconds": 4, "camera": "static top-down",
         "motion_prompt": "Knife slicing cucumber into thin rounds.", "title": "Огурец и авокадо"},
        {"n": 6, "shot": 12, "seconds": 5, "camera": "slow tilt down",
         "motion_prompt": "Hands placing rice and spinach into the bowl.", "title": "Собираем боул"},
        {"n": 7, "shot": 18, "seconds": 4, "camera": "slow pull-out",
         "motion_prompt": "Soft steam, chopsticks resting beside the bowl.", "title": "Сохрани рецепт"},
    ],
}

TEXTS = {
    "id": ID,
    "hook": "Обед за 25 минут — боул с тунцом и шпинатом",
    "platforms": {
        "youtube": {"title": "Боул с тунцом за 25 минут 🥗",
                    "text": "Сытный обед из 9 продуктов: рис, тунец, шпинат, огурец и авокадо. Сохрани рецепт!",
                    "hashtags": ["#кухнянараздва", "#рецепт", "#shorts"]},
        "tiktok": {"text": "Обед за 25 минут — боул с тунцом и шпинатом 🥗",
                   "hashtags": ["#кухнянараздва", "#рецепт", "#обед"]},
        "instagram": {"text": "Боул с тунцом и шпинатом — обед за 25 минут.\n\n"
                              "На 2 порции: рис 150 г, стейк тунца 250 г, шпинат 60 г, огурец, авокадо, "
                              "соевый соус и кунжут.\n\nСохрани, чтобы не потерять 📌",
                      "hashtags": ["#кухнянараздва", "#рецепт", "#обед"]},
        "facebook": {"text": "Боул с тунцом и шпинатом — сытный обед за 25 минут. Рецепт на 2 порции в ролике.",
                     "hashtags": ["#кухнянараздва", "#рецепт"]},
        "telegram": {"text": "🥗 Боул с тунцом и шпинатом — обед за 25 минут. Рецепт — следующим сообщением.",
                     "hashtags": ["#рецепт"],
                     "recipe_post": "Боул с тунцом и шпинатом (2 порции, 25 минут)\n\n"
                                    "Рис — 150 г\nСтейк тунца — 250 г\nШпинат — 60 г\nОгурец — 1 шт\n"
                                    "Авокадо — 1 шт\nСоевый соус — 2 ст. л.\nКунжут — 1 ч. л.\n\n"
                                    "1. Отварить рис.\n2. Обжарить тунец по 1–2 минуты с каждой стороны.\n"
                                    "3. Нарезать огурец и авокадо.\n4. Собрать боул и полить соусом."},
        "vk": {"text": "Боул с тунцом и шпинатом — обед за 25 минут 🥗\n\n"
                       "На 2 порции нужно: рис 150 г, стейк тунца 250 г, шпинат 60 г, огурец, авокадо, "
                       "2 ст. л. соевого соуса и 1 ч. л. кунжута.\n\n"
                       "Рис отвари, тунец обжарь по 1–2 минуты с каждой стороны и нарежь. Огурец — кружками, "
                       "авокадо — кубиками. Собери всё в миске, полей соусом и посыпь кунжутом.",
               "hashtags": ["#кухнянараздва", "#рецепт", "#обед"]},
    },
}

VOICEOVER = {
    "id": ID,
    "voice": "Тёплый женский голос, дружелюбный, живой темп",
    "lines": [
        {"scene": 1, "text": "Обед за 25 минут — боул с тунцом!"},
        {"scene": 2, "text": "Нужно всего 9 продуктов из обычного магазина."},
        {"scene": 3, "text": "Рис промываем и варим до готовности."},
        {"scene": 4, "text": "Тунец обжариваем по 1–2 минуты с каждой стороны."},
        {"scene": 5, "text": "Огурец кружками, авокадо кубиками."},
        {"scene": 6, "text": "Собираем всё в миску, соевый соус и кунжут."},
        {"scene": 7, "text": "Сохрани рецепт, чтобы не потерять!"},
    ],
}

PACKAGE = {"brief": BRIEF, "recipe": RECIPE, "shots": SHOTS, "texts": TEXTS,
           "video_brief": VIDEO_BRIEF, "voiceover": VOICEOVER}


def package(**over) -> dict:
    """Глубокая копия пакета с заменой отдельных файлов."""
    data = copy.deepcopy(PACKAGE)
    data.update(copy.deepcopy(over))
    return data


def write_json(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def make_root(tmp_path: Path) -> Path:
    """Корень проекта во временной папке: настоящие rules/ и config/, пустые plans/ и runs/."""
    root = tmp_path / "root"
    shutil.copytree(ROOT / "rules", root / "rules")
    shutil.copytree(ROOT / "config", root / "config")
    (root / "plans").mkdir()
    (root / "runs").mkdir()
    return root


def write_package(root: Path, data: dict | None = None, skip: tuple[str, ...] = ()) -> Path:
    folder = root / "runs" / DATE / FOLDER
    for name, content in (data or package()).items():
        if name not in skip:
            write_json(folder / f"{name}.json", content)
    return folder


def week_plan(start: str = DATE) -> dict:
    """Валидный план на 7 дней: 14 разных блюд, рубрики вперемешку, завтрак/обед/ужин."""
    from datetime import date, timedelta

    first = date.fromisoformat(start)
    rubrics = ["recept_30s", "iz_togo_chto_est", "sezonnoe", "byudzhetno"]
    days = []
    for i in range(7):
        day = (first + timedelta(days=i)).isoformat()
        slots = [
            {"slot": 1, "dish": f"Завтрак номер {i}", "slug": f"zavtrak-{i}", "rubric": "zavtrak_10",
             "meal": "завтрак", "why": "Быстрый завтрак перед работой."},
            {"slot": 2, "dish": f"Ужин номер {i}", "slug": f"uzhin-{i}", "rubric": rubrics[i % len(rubrics)],
             "meal": "ужин", "why": "Сытный ужин из обычных продуктов."},
        ]
        days.append({"date": day, "slots": slots})
    return {"week_start": start, "days": days}
