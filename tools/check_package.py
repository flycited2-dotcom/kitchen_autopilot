"""Проверка пакета блюда: brief, recipe, shots, texts, video_brief, voiceover.

Запуск: python tools/check_package.py runs/2026-11-02/01-boul-s-tuncom [--only brief,recipe] [--root .]
Вывод: JSON {"ok", "folder", "sections": {раздел: [причины]}}. Код: 0 — прошёл, 1 — отклонён, 2 — ошибка входа.
Числа в текстах, титрах и озвучке должны встречаться в recipe.json (логика check_draft.py из Agents_MY).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

import yaml

from check_plan import check_dish, has_dish_fields
from kitchen_common import (HASHTAG, PRICE, ROOT, CheckError, as_dict, canon_number, count_words, dish_history,
                            forbidden_words, has_stem, has_text, is_int, is_number, load_rules, normalize, numbers,
                            parse_date, read_json, recent_repeat, stop_words_in)

SECTIONS = ("brief", "recipe", "shots", "texts", "video_brief", "voiceover")
# Файлы, которые нужны разделу (свой — последним).
NEEDS = {
    "brief": ("brief",),
    "recipe": ("brief", "recipe"),
    "shots": ("recipe", "shots"),
    "texts": ("brief", "recipe", "texts"),
    "video_brief": ("brief", "recipe", "shots", "video_brief"),
    "voiceover": ("brief", "recipe", "video_brief", "voiceover"),
}


def _id_reason(data: dict, expected, what: str) -> list[str]:
    if data.get("id") != expected:
        return [f"{what}: id {data.get('id')} не совпадает с brief ({expected})"]
    return []


def _text_reasons(text: str, where: str, supported: set[str], rules: dict) -> list[str]:
    """Стоп-слова, цены и числа не из рецепта — общая проверка любого текста для зрителя."""
    reasons = [f"{where}: стоп-слово: {word}" for word in stop_words_in(text, rules["stopwords"]["stop_words"])]
    if PRICE.search(text):
        reasons.append(f"{where}: цена запрещена")
    reasons += [f"{where}: число {number} не из рецепта" for number in sorted(numbers(text) - supported)]
    return reasons


def supported_numbers(recipe, brief, rules: dict) -> set[str]:
    """Все числа рецепта (кроме id) + число ингредиентов, номера шагов и числа из названия рубрики."""
    found: set[str] = set()

    def walk(value, key=None):
        if key == "id" or isinstance(value, bool):
            return
        if is_number(value):
            found.add(canon_number(value))
        elif isinstance(value, str):
            found.update(numbers(value))
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            for item_key, item in value.items():
                walk(item, item_key)

    recipe = as_dict(recipe)
    walk(recipe)
    if isinstance(recipe.get("ingredients"), list):
        found.add(str(len(recipe["ingredients"])))
    if isinstance(recipe.get("steps"), list):
        found.update(str(n) for n in range(1, len(recipe["steps"]) + 1))
    rubric = rules["rubrics"].get(as_dict(brief).get("rubric"), {})
    found.update(numbers(rubric.get("title", "")))
    return found


# --- brief ---------------------------------------------------------------------------------------------------

def check_brief(brief, folder_name: str, rules: dict, history: set) -> list[str]:
    if not isinstance(brief, dict):
        raise CheckError("brief.json должен быть объектом")
    day = parse_date(brief.get("date"), "brief.date")
    reasons = check_dish(brief, "brief", rules)
    if not is_int(brief.get("slot")) or brief["slot"] < 1:
        reasons.append("brief: slot — целое число от 1")
    if reasons or not has_dish_fields(brief):
        return reasons
    expected_id = f"{day.isoformat()}-{brief['slot']:02d}-{brief['slug']}"
    if brief.get("id") != expected_id:
        reasons.append(f"brief: id {brief.get('id')}, ожидался {expected_id}")
    expected_folder = f"{brief['slot']:02d}-{brief['slug']}"
    if folder_name != expected_folder:
        reasons.append(f"папка {folder_name}, ожидалась {expected_folder}")
    seen = recent_repeat(brief["slug"], day, history, rules["plan"]["repeat_days"])
    if seen:
        reasons.append(f"brief: «{brief['dish']}» ({brief['slug']}) уже есть на {seen} — повтор ближе "
                       f"{rules['plan']['repeat_days']} дней")
    return reasons


# --- recipe --------------------------------------------------------------------------------------------------

def _qty_reasons(item: dict, limits: dict) -> list[str]:
    unit = item["unit"].strip()
    qty = item.get("qty")
    if unit in limits["no_qty_units"]:
        return [] if qty is None else [f"«{item['name']}»: при «{unit}» qty должно быть null"]
    if unit not in limits["units"]:
        return [f"«{item['name']}»: единица «{unit}» не из rules/recipe.yaml"]
    if not is_number(qty) or qty <= 0:
        return [f"«{item['name']}»: qty — число больше 0"]
    return []


def _safety_matches(name: str, rule: dict) -> bool:
    lowered = normalize(name)
    if any(normalize(part) in lowered for part in rule.get("except") or []):
        return False
    return any(has_stem(lowered, stem) for stem in rule["match"])


def _safety_reasons(names: list[str], steps: list, notes: list[str], safety: dict) -> list[str]:
    """Фраза безопасности засчитывается в шаге, где продукт используется, или в safety_notes —
    «до готовности» из шага про рис не прикрывает сырой тунец."""
    reasons = []
    for rule in safety["rules"]:
        for name in (name for name in names if _safety_matches(name, rule)):
            key = normalize(name.strip())
            texts = [str(step.get("text", "")) for step in steps if isinstance(step, dict)
                     and isinstance(step.get("uses"), list)
                     and key in {normalize(str(used).strip()) for used in step["uses"]}]
            text = normalize(" ".join(texts + notes))
            if not any(normalize(phrase) in text for phrase in rule["require_any"]):
                reasons.append(f"безопасность ({rule['id']}): для «{name}» в его шаге или safety_notes нужна "
                               f"одна из фраз: {'; '.join(rule['require_any'])}")
                break
    return reasons


def check_recipe(recipe, brief, rules: dict) -> list[str]:
    if not isinstance(recipe, dict):
        raise CheckError("recipe.json должен быть объектом")
    if not isinstance(recipe.get("ingredients"), list) or not isinstance(recipe.get("steps"), list):
        raise CheckError("recipe.json: ingredients и steps должны быть списками")
    brief, limits = as_dict(brief), rules["recipe"]
    rubric = rules["rubrics"].get(brief.get("rubric"), {})
    reasons = _id_reason(recipe, brief.get("id"), "recipe")
    if not has_text(recipe.get("dish")):
        reasons.append("recipe: нет названия блюда")
    for key in ("servings", "time_total_min"):
        if not is_int(recipe.get(key)) or recipe[key] <= 0:
            reasons.append(f"recipe: {key} — целое число больше 0")
    if is_int(recipe.get("time_total_min")) and rubric.get("max_time_min") \
            and recipe["time_total_min"] > rubric["max_time_min"]:
        reasons.append(f"recipe: {recipe['time_total_min']} мин — дольше рубрики ({rubric['max_time_min']} мин)")

    ingredients, steps = recipe["ingredients"], recipe["steps"]
    names: dict[str, str] = {}
    for i, item in enumerate(ingredients, 1):
        if not isinstance(item, dict) or not has_text(item.get("name")) or not isinstance(item.get("unit"), str):
            reasons.append(f"ингредиент {i}: нужны name и unit")
            continue
        key = normalize(item["name"].strip())
        if key in names:
            reasons.append(f"ингредиент «{item['name']}» указан дважды")
        names[key] = item["name"]
        reasons += _qty_reasons(item, limits)
    if not limits["min_ingredients"] <= len(ingredients) <= limits["max_ingredients"]:
        reasons.append(f"ингредиентов {len(ingredients)}, нужно от {limits['min_ingredients']} "
                       f"до {limits['max_ingredients']}")
    if rubric.get("max_ingredients") and len(ingredients) > rubric["max_ingredients"]:
        reasons.append(f"recipe: {len(ingredients)} ингредиентов — больше рубрики ({rubric['max_ingredients']})")
    if not 1 <= len(steps) <= limits["max_steps"]:
        reasons.append(f"шагов {len(steps)}, нужно от 1 до {limits['max_steps']}")

    used = set()
    for i, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            reasons.append(f"шаг {i}: должен быть объектом")
            continue
        if step.get("n") != i:
            reasons.append(f"шаг {i}: номер {step.get('n')}, ожидался {i}")
        if not has_text(step.get("text")):
            reasons.append(f"шаг {i}: нет текста")
        if step.get("time_min") is not None and (not is_int(step["time_min"]) or step["time_min"] <= 0):
            reasons.append(f"шаг {i}: time_min — целое число больше 0")
        uses = step.get("uses")
        if not isinstance(uses, list) or not uses or not all(isinstance(name, str) for name in uses):
            reasons.append(f"шаг {i}: uses — непустой список ингредиентов")
            continue
        for name in uses:
            key = normalize(name.strip())
            if key not in names:
                reasons.append(f"шаг {i}: «{name}» нет в списке ингредиентов")
            used.add(key)
    for key, name in names.items():
        if key not in used:
            reasons.append(f"ингредиент «{name}» не используется ни в одном шаге")

    notes = recipe.get("safety_notes", [])
    if not isinstance(notes, list) or not all(isinstance(note, str) for note in notes):
        reasons.append("recipe: safety_notes — список строк")
        notes = []
    body = " ".join([str(step.get("text", "")) for step in steps if isinstance(step, dict)] + notes)
    reasons += _safety_reasons(list(names.values()), steps, notes, rules["food_safety"])
    everything = " ".join([str(recipe.get("dish", "")), body, *names.values()])
    reasons += [f"recipe: стоп-слово: {word}" for word in stop_words_in(everything, rules["stopwords"]["stop_words"])]
    if PRICE.search(everything):
        reasons.append("recipe: цена в рецепте запрещена")
    return reasons


# --- shots ---------------------------------------------------------------------------------------------------

def _step_numbers(recipe) -> set[int]:
    steps = as_dict(recipe).get("steps")
    return {step["n"] for step in steps if isinstance(step, dict) and is_int(step.get("n"))} \
        if isinstance(steps, list) else set()


def _shot_kinds(shots) -> dict[int, str]:
    items = as_dict(shots).get("shots")
    return {shot["n"]: shot.get("kind") for shot in items if isinstance(shot, dict) and is_int(shot.get("n"))} \
        if isinstance(items, list) else {}


def check_shots(shots, recipe, rules: dict) -> list[str]:
    if not isinstance(shots, dict) or not isinstance(shots.get("shots"), list):
        raise CheckError("shots.json: нужен объект со списком shots")
    limits = rules["shots"]
    reasons = _id_reason(shots, as_dict(recipe).get("id"), "shots")
    style = shots.get("style_block")
    if not has_text(style):
        reasons.append("shots: нет style_block")
    else:
        reasons += [f"shots: в style_block нет «{phrase}»" for phrase in limits["style_block_must_contain"]
                    if normalize(phrase) not in normalize(style)]
    items = shots["shots"]
    if not limits["min_shots"] <= len(items) <= limits["max_shots"]:
        reasons.append(f"кадров {len(items)}, нужно от {limits['min_shots']} до {limits['max_shots']}")
    steps = _step_numbers(recipe)
    kinds, angles, covered = Counter(), set(), set()
    for i, shot in enumerate(items, 1):
        if not isinstance(shot, dict):
            reasons.append(f"кадр {i}: должен быть объектом")
            continue
        if shot.get("n") != i:
            reasons.append(f"кадр {i}: номер {shot.get('n')}, ожидался {i}")
        kind = shot.get("kind")
        if kind in limits["kinds"]:
            kinds[kind] += 1
        else:
            reasons.append(f"кадр {i}: kind {kind} не из {', '.join(limits['kinds'])}")
        if has_text(shot.get("angle")):
            angles.add(normalize(shot["angle"].strip()))
        else:
            reasons.append(f"кадр {i}: нет angle")
        if not has_text(shot.get("title_ru")):
            reasons.append(f"кадр {i}: нет title_ru")
        prompt = shot.get("prompt")
        if not has_text(prompt) or len(prompt) < limits["min_prompt_length"]:
            reasons.append(f"кадр {i}: prompt короче {limits['min_prompt_length']} символов")
        else:
            reasons += [f"кадр {i}: в prompt слово «{word}» — запреты на текст пишутся только в style_block"
                        for word in forbidden_words(prompt, limits["prompt_forbidden_words"])]
        if kind == "process":
            if is_int(shot.get("step")) and shot["step"] in steps:
                covered.add(shot["step"])
            else:
                reasons.append(f"кадр {i}: process-кадр должен ссылаться на шаг рецепта (step)")
    reasons += [f"нет кадра вида {kind}" for kind in limits["required_kinds"] if not kinds[kind]]
    if len(angles) < limits["min_distinct_angles"]:
        reasons.append(f"разных ракурсов {len(angles)}, нужно не меньше {limits['min_distinct_angles']}")
    reasons += [f"шаг {n} рецепта не показан ни одним process-кадром" for n in sorted(steps - covered)]
    return reasons


# --- video_brief ---------------------------------------------------------------------------------------------

def check_video_brief(video_brief, shots, recipe, brief, rules: dict) -> list[str]:
    if not isinstance(video_brief, dict) or not isinstance(video_brief.get("scenes"), list):
        raise CheckError("video_brief.json: нужен объект со списком scenes")
    limits = rules["video"]
    reasons = _id_reason(video_brief, as_dict(brief).get("id"), "video_brief")
    description = video_brief.get("technical_description")
    if not has_text(description) or len(description) < limits["min_description_length"]:
        reasons.append(f"video_brief: technical_description короче {limits['min_description_length']} символов")
    kinds = _shot_kinds(shots)
    if video_brief.get("cover_shot") not in kinds:
        reasons.append("cover_shot должен ссылаться на кадр из shots.json")
    scenes = video_brief["scenes"]
    if not limits["min_scenes"] <= len(scenes) <= limits["max_scenes"]:
        reasons.append(f"сцен {len(scenes)}, нужно от {limits['min_scenes']} до {limits['max_scenes']}")
    supported = supported_numbers(recipe, brief, rules)
    total = 0.0
    for i, scene in enumerate(scenes, 1):
        where = f"сцена {i}"
        if not isinstance(scene, dict):
            reasons.append(f"{where}: должна быть объектом")
            continue
        if scene.get("n") != i:
            reasons.append(f"{where}: номер {scene.get('n')}, ожидался {i}")
        if scene.get("shot") not in kinds:
            reasons.append(f"{where}: кадра {scene.get('shot')} нет в shots.json")
        elif i == 1 and kinds[scene["shot"]] not in limits["hook_first_kinds"]:
            reasons.append(f"сцена 1 — хук: нужен кадр вида {', '.join(limits['hook_first_kinds'])}")
        seconds = scene.get("seconds")
        if is_number(seconds) and limits["min_scene_seconds"] <= seconds <= limits["max_scene_seconds"]:
            total += seconds
        else:
            reasons.append(f"{where}: seconds от {limits['min_scene_seconds']} до {limits['max_scene_seconds']}")
        for key in ("motion_prompt", "camera"):
            if not has_text(scene.get(key)):
                reasons.append(f"{where}: нет {key}")
        if has_text(scene.get("motion_prompt")):
            reasons += [f"{where}: в motion_prompt слово «{word}» — титры накладывает сборка, не Grok"
                        for word in forbidden_words(scene["motion_prompt"], rules["shots"]["prompt_forbidden_words"])]
        title = scene.get("title", "")
        if not isinstance(title, str):
            reasons.append(f"{where}: title — строка (можно пустую)")
            continue
        if len(title) > limits["title_max_length"]:
            reasons.append(f"{where}: титр длиннее {limits['title_max_length']} символов ({len(title)})")
        for reason in _text_reasons(title, where, supported, rules):
            reasons.append(reason.replace("не из рецепта", "в титре не из рецепта"))
    if not limits["min_total_seconds"] <= total <= limits["max_total_seconds"]:
        reasons.append(f"ролик {total:g} с — нужно от {limits['min_total_seconds']} до {limits['max_total_seconds']}")
    return reasons


# --- texts ---------------------------------------------------------------------------------------------------

def check_texts(texts, recipe, brief, rules: dict) -> list[str]:
    if not isinstance(texts, dict) or not isinstance(texts.get("platforms"), dict):
        raise CheckError("texts.json: нужен объект с platforms")
    config = rules["platforms"]
    brand = normalize(config["brand_hashtag"])
    supported = supported_numbers(recipe, brief, rules)
    reasons = _id_reason(texts, as_dict(brief).get("id"), "texts")
    if has_text(texts.get("hook")):
        reasons += _text_reasons(texts["hook"], "hook", supported, rules)
    else:
        reasons.append("texts: нет hook")
    for name, limits in config["platforms"].items():
        item = texts["platforms"].get(name)
        if not isinstance(item, dict) or not isinstance(item.get("text"), str) \
                or not isinstance(item.get("hashtags"), list):
            reasons.append(f"{name}: нужны text и hashtags")
            continue
        tags = item["hashtags"]
        bad = [str(tag) for tag in tags if not isinstance(tag, str) or not HASHTAG.match(tag)]
        if bad:
            reasons.append(f"{name}: неверные хештеги: {', '.join(bad)}")
        normalized_tags = [normalize(tag) for tag in tags if isinstance(tag, str)]
        if len(set(normalized_tags)) != len(tags):
            reasons.append(f"{name}: хештеги повторяются")
        if len(tags) > limits["hashtags_max"]:
            reasons.append(f"{name}: хештегов {len(tags)}, максимум {limits['hashtags_max']}")
        if limits.get("require_brand_hashtag") and brand not in normalized_tags:
            reasons.append(f"{name}: нет фирменного хештега {config['brand_hashtag']}")
        full = item["text"].strip() + ("\n\n" + " ".join(str(tag) for tag in tags) if tags else "")
        if len(full) < limits["text_min"]:
            reasons.append(f"{name}: текст с хештегами {len(full)} символов — меньше {limits['text_min']}")
        if len(full) > limits["text_max"]:
            reasons.append(f"{name}: текст с хештегами {len(full)} символов — больше {limits['text_max']}")
        parts = [item["text"]]
        if limits.get("require_title"):
            title = item.get("title")
            if not has_text(title):
                reasons.append(f"{name}: нет title")
            else:
                if len(title) > limits["title_max"]:
                    reasons.append(f"{name}: title {len(title)} символов — больше {limits['title_max']}")
                parts.append(title)
        if limits.get("require_recipe_post"):
            post = item.get("recipe_post")
            if not has_text(post):
                reasons.append(f"{name}: нет recipe_post")
            else:
                if len(post) > limits["recipe_post_max"]:
                    reasons.append(f"{name}: recipe_post {len(post)} символов — больше {limits['recipe_post_max']}")
                parts.append(post)
        reasons += _text_reasons("\n".join(parts), name, supported, rules)
    return reasons


# --- voiceover -----------------------------------------------------------------------------------------------

def check_voiceover(voiceover, video_brief, recipe, brief, rules: dict) -> list[str]:
    if not isinstance(voiceover, dict) or not isinstance(voiceover.get("lines"), list):
        raise CheckError("voiceover.json: нужен объект со списком lines")
    rate = rules["video"]["voice_words_per_second_max"]
    reasons = _id_reason(voiceover, as_dict(brief).get("id"), "voiceover")
    if not has_text(voiceover.get("voice")):
        reasons.append("voiceover: нет описания голоса voice")
    scenes = as_dict(video_brief).get("scenes")
    seconds = {scene["n"]: scene["seconds"] for scene in scenes
               if isinstance(scene, dict) and is_int(scene.get("n")) and is_number(scene.get("seconds"))} \
        if isinstance(scenes, list) else {}
    if not voiceover["lines"]:
        reasons.append("voiceover: нет ни одной реплики")
    supported = supported_numbers(recipe, brief, rules)
    seen: list[int] = []
    for i, line in enumerate(voiceover["lines"], 1):
        if not isinstance(line, dict) or not has_text(line.get("text")):
            reasons.append(f"реплика {i}: нужен text")
            continue
        scene = line.get("scene")
        if scene not in seconds:
            reasons.append(f"реплика {i}: сцены {scene} нет в video_brief.json")
            continue
        if scene in seen:
            reasons.append(f"сцена {scene}: больше одной реплики")
        elif seen and scene < seen[-1]:
            reasons.append(f"реплика {i}: сцены идут не по порядку")
        seen.append(scene)
        words, limit = count_words(line["text"]), math.floor(seconds[scene] * rate)
        if words > limit:
            reasons.append(f"сцена {scene}: {words} слов на {seconds[scene]:g} с — максимум {limit}")
        reasons += _text_reasons(line["text"], f"сцена {scene}", supported, rules)
    return reasons


# --- папка целиком -------------------------------------------------------------------------------------------

RUNNERS = {
    "brief": lambda f, folder, rules, history: check_brief(f["brief"], folder, rules, history),
    "recipe": lambda f, folder, rules, history: check_recipe(f["recipe"], f["brief"], rules),
    "shots": lambda f, folder, rules, history: check_shots(f["shots"], f["recipe"], rules),
    "texts": lambda f, folder, rules, history: check_texts(f["texts"], f["recipe"], f["brief"], rules),
    "video_brief": lambda f, folder, rules, history: check_video_brief(
        f["video_brief"], f["shots"], f["recipe"], f["brief"], rules),
    "voiceover": lambda f, folder, rules, history: check_voiceover(
        f["voiceover"], f["video_brief"], f["recipe"], f["brief"], rules),
}


def check_folder(folder: Path, rules: dict, root: Path, only: tuple[str, ...] = SECTIONS) -> dict:
    folder = Path(folder)
    if not folder.is_dir():
        raise CheckError(f"нет папки {folder}")
    cache: dict = {}

    def load(name: str):
        if name not in cache:
            try:
                cache[name] = read_json(folder / f"{name}.json", f"{name}.json")
            except CheckError as exc:
                cache[name] = exc
        if isinstance(cache[name], CheckError):
            raise cache[name]
        return cache[name]

    history = dish_history(root)
    sections = {}
    for name in only:
        try:
            files = {need: load(need) for need in NEEDS[name]}
            sections[name] = RUNNERS[name](files, folder.name, rules, history)
        except CheckError as exc:
            sections[name] = [str(exc)]
    return {"ok": not any(sections.values()), "folder": folder.name, "sections": sections}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--only", default=",".join(SECTIONS), help="разделы через запятую: " + ",".join(SECTIONS))
    parser.add_argument("--rules-dir", type=Path, default=ROOT / "rules")
    parser.add_argument("--root", type=Path, default=ROOT, help="корень с plans/ и runs/ — для поиска повторов")
    args = parser.parse_args(argv)
    only = tuple(part.strip() for part in args.only.split(",") if part.strip())
    try:
        unknown = [name for name in only if name not in SECTIONS]
        if unknown or not only:
            raise CheckError(f"неизвестные разделы: {', '.join(unknown) or '(пусто)'}")
        result = check_folder(args.folder, load_rules(args.rules_dir), args.root, only)
    except (CheckError, OSError, yaml.YAMLError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
