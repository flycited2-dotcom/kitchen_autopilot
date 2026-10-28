import json

import pytest

import check_package as cp
from kitchen_common import load_rules
from tests.kitchen_fixtures import (BRIEF, FOLDER, ID, RECIPE, SHOTS, TEXTS, VIDEO_BRIEF, VOICEOVER, make_root,
                                    package, write_package)

RULES = load_rules()


def _recipe(**over):
    return package(recipe=dict(RECIPE, **over))["recipe"]


# --- brief ---------------------------------------------------------------------------------------------------

def test_valid_brief():
    assert cp.check_brief(BRIEF, FOLDER, RULES, set()) == []


def test_brief_id_and_folder_mismatch():
    reasons = cp.check_brief(dict(BRIEF, id="x"), "02-other", RULES, set())
    assert f"brief: id x, ожидался {ID}" in reasons
    assert f"папка 02-other, ожидалась {FOLDER}" in reasons


def test_brief_repeat():
    reasons = cp.check_brief(BRIEF, FOLDER, RULES, {(BRIEF["slug"], "2026-10-15")})
    assert any("2026-10-15" in r for r in reasons)


# --- recipe --------------------------------------------------------------------------------------------------

def test_valid_recipe():
    assert cp.check_recipe(RECIPE, BRIEF, RULES) == []


def test_recipe_qty_and_units():
    recipe = package()["recipe"]
    recipe["ingredients"][0].update(qty=0)
    recipe["ingredients"][1].update(unit="горсть")
    recipe["ingredients"][8].update(qty=5)
    reasons = cp.check_recipe(recipe, BRIEF, RULES)
    assert "«рис»: qty — число больше 0" in reasons
    assert "«стейк тунца»: единица «горсть» не из rules/recipe.yaml" in reasons
    assert "«соль»: при «по вкусу» qty должно быть null" in reasons


def test_recipe_steps_use_only_listed_ingredients_and_all_are_used():
    recipe = package()["recipe"]
    recipe["steps"][2]["uses"] = ["огурец", "помидор"]
    reasons = cp.check_recipe(recipe, BRIEF, RULES)
    assert "шаг 3: «помидор» нет в списке ингредиентов" in reasons
    assert "ингредиент «авокадо» не используется ни в одном шаге" not in reasons  # используется в шаге 4
    recipe["steps"][3]["uses"].remove("кунжут")
    assert "ингредиент «кунжут» не используется ни в одном шаге" in cp.check_recipe(recipe, BRIEF, RULES)


def test_recipe_step_numbering():
    recipe = package()["recipe"]
    recipe["steps"][1]["n"] = 5
    assert "шаг 2: номер 5, ожидался 2" in cp.check_recipe(recipe, BRIEF, RULES)


def test_recipe_rubric_limits():
    brief = dict(BRIEF, rubric="iz_togo_chto_est")
    reasons = cp.check_recipe(_recipe(time_total_min=35), brief, RULES)
    assert "recipe: 35 мин — дольше рубрики (30 мин)" in reasons
    assert "recipe: 9 ингредиентов — больше рубрики (6)" in reasons


def test_recipe_raw_fish_requires_safety_phrase():
    recipe = package()["recipe"]
    recipe["steps"][1]["text"] = "Тунец нарезать ломтиками."
    recipe["safety_notes"] = []
    reasons = cp.check_recipe(recipe, BRIEF, RULES)
    assert any(r.startswith("безопасность (raw_fish): для «стейк тунца»") for r in reasons)


def test_canned_tuna_and_chicken_eggs_do_not_trigger_safety():
    recipe = package()["recipe"]
    recipe["ingredients"][1]["name"] = "тунец консервированный"
    recipe["ingredients"].append({"name": "яйцо куриное", "qty": 2, "unit": "шт"})
    recipe["steps"][1].update(text="Тунец размять вилкой.", uses=["тунец консервированный", "масло растительное",
                                                                  "соль", "яйцо куриное"])
    recipe["steps"][3]["uses"] = ["рис", "шпинат свежий", "огурец", "авокадо", "соевый соус", "кунжут"]
    recipe["safety_notes"] = []
    assert cp.check_recipe(recipe, BRIEF, RULES) == []


def test_chicken_requires_full_doneness():
    recipe = package()["recipe"]
    recipe["ingredients"][1]["name"] = "куриное филе"
    recipe["steps"][1].update(text="Филе обжарить по 5 минут.", uses=["куриное филе", "масло растительное", "соль"])
    recipe["steps"][3]["uses"] = ["рис", "шпинат свежий", "огурец", "авокадо", "куриное филе", "соевый соус",
                                  "кунжут"]
    reasons = cp.check_recipe(recipe, BRIEF, RULES)
    assert any(r.startswith("безопасность (poultry)") for r in reasons)
    recipe["steps"][1]["text"] = "Филе обжарить до полной готовности, по 5 минут с каждой стороны."
    assert cp.check_recipe(recipe, BRIEF, RULES) == []


def test_recipe_stop_words_and_price():
    recipe = package()["recipe"]
    recipe["safety_notes"].append("Этот боул лечит усталость, а стоит всего 300 руб.")
    reasons = cp.check_recipe(recipe, BRIEF, RULES)
    assert "recipe: стоп-слово: лечит" in reasons
    assert "recipe: цена в рецепте запрещена" in reasons


# --- shots ---------------------------------------------------------------------------------------------------

def test_valid_shots():
    assert cp.check_shots(SHOTS, RECIPE, RULES) == []


def test_shots_count_and_numbering():
    shots = package()["shots"]
    shots["shots"] = shots["shots"][:10]
    reasons = cp.check_shots(shots, RECIPE, RULES)
    assert "кадров 10, нужно от 16 до 24" in reasons


def test_shots_forbidden_word_in_prompt_and_style_block():
    shots = package()["shots"]
    shots["shots"][0]["prompt"] += " Add a caption with the dish name."
    shots["style_block"] = "Photorealistic food photography, soft light, light oak table, ceramic bowl."
    reasons = cp.check_shots(shots, RECIPE, RULES)
    assert "кадр 1: в prompt слово «caption» — запреты на текст пишутся только в style_block" in reasons
    assert "shots: в style_block нет «no text»" in reasons


def test_shots_every_step_covered_and_required_kinds():
    shots = package()["shots"]
    shots["shots"] = [s for s in shots["shots"] if s["step"] != 3 and s["kind"] != "cover"]
    for n, shot in enumerate(shots["shots"], 1):
        shot["n"] = n
    reasons = cp.check_shots(shots, RECIPE, RULES)
    assert "шаг 3 рецепта не показан ни одним process-кадром" in reasons
    assert "нет кадра вида cover" in reasons


def test_process_shot_must_reference_step():
    shots = package()["shots"]
    shots["shots"][4]["step"] = 9
    assert "кадр 5: process-кадр должен ссылаться на шаг рецепта (step)" in cp.check_shots(shots, RECIPE, RULES)


# --- video_brief ---------------------------------------------------------------------------------------------

def test_valid_video_brief():
    assert cp.check_video_brief(VIDEO_BRIEF, SHOTS, RECIPE, BRIEF, RULES) == []


def test_video_brief_hook_durations_and_titles():
    vb = package()["video_brief"]
    vb["scenes"][0]["shot"] = 5
    vb["scenes"][1]["seconds"] = 9
    vb["scenes"][2]["title"] = "Рис — 200 г, это очень длинный титр"
    vb["cover_shot"] = 99
    reasons = cp.check_video_brief(vb, SHOTS, RECIPE, BRIEF, RULES)
    assert "сцена 1 — хук: нужен кадр вида hero, serving" in reasons
    assert "сцена 2: seconds от 2 до 6" in reasons
    assert "сцена 3: число 200 в титре не из рецепта" in reasons
    assert any(r.startswith("сцена 3: титр длиннее 32") for r in reasons)
    assert "cover_shot должен ссылаться на кадр из shots.json" in reasons


def test_video_brief_total_duration():
    vb = package()["video_brief"]
    vb["scenes"] = vb["scenes"][:4]
    reasons = cp.check_video_brief(vb, SHOTS, RECIPE, BRIEF, RULES)
    assert "ролик 17 с — нужно от 15 до 59" not in reasons
    vb["scenes"] = vb["scenes"][:3]
    reasons = cp.check_video_brief(vb, SHOTS, RECIPE, BRIEF, RULES)
    assert "сцен 3, нужно от 4 до 12" in reasons
    assert "ролик 12 с — нужно от 15 до 59" in reasons


# --- texts ---------------------------------------------------------------------------------------------------

def test_valid_texts():
    assert cp.check_texts(TEXTS, RECIPE, BRIEF, RULES) == []


def test_texts_numbers_must_come_from_recipe():
    texts = package()["texts"]
    texts["platforms"]["tiktok"]["text"] = "Обед за 15 минут — боул с тунцом, всего 300 калорий!"
    reasons = cp.check_texts(texts, RECIPE, BRIEF, RULES)
    assert "tiktok: число 300 не из рецепта" in reasons
    assert "tiktok: число 15 не из рецепта" not in reasons  # 15 — время варки риса в шаге 1


def test_texts_platform_rules():
    texts = package()["texts"]
    del texts["platforms"]["vk"]
    texts["platforms"]["youtube"]["title"] = ""
    texts["platforms"]["instagram"]["hashtags"] = ["#рецепт", "без решётки", "#обед", "#обед"]
    texts["platforms"]["telegram"].pop("recipe_post")
    texts["platforms"]["facebook"]["hashtags"] = ["#рецепт"]
    reasons = cp.check_texts(texts, RECIPE, BRIEF, RULES)
    assert "vk: нужны text и hashtags" in reasons
    assert "youtube: нет title" in reasons
    assert "instagram: неверные хештеги: без решётки" in reasons
    assert "instagram: хештеги повторяются" in reasons
    assert "instagram: нет фирменного хештега #кухнянараздва" in reasons
    assert "facebook: нет фирменного хештега #кухнянараздва" in reasons
    assert "telegram: нет recipe_post" in reasons


def test_texts_length_includes_hashtags():
    texts = package()["texts"]
    texts["platforms"]["telegram"]["text"] = "а" * 990
    texts["platforms"]["telegram"]["hashtags"] = ["#рецепт", "#обед"]
    reasons = cp.check_texts(texts, RECIPE, BRIEF, RULES)
    assert "telegram: текст с хештегами 1005 символов — больше 1000" in reasons


def test_texts_stop_words_and_price():
    texts = package()["texts"]
    texts["platforms"]["vk"]["text"] += " Детокс для всей семьи всего за 199 ₽."
    reasons = cp.check_texts(texts, RECIPE, BRIEF, RULES)
    assert "vk: стоп-слово: детокс" in reasons
    assert "vk: цена запрещена" in reasons


# --- voiceover -----------------------------------------------------------------------------------------------

def test_valid_voiceover():
    assert cp.check_voiceover(VOICEOVER, VIDEO_BRIEF, RECIPE, BRIEF, RULES) == []


def test_voiceover_too_many_words_unknown_scene_and_numbers():
    vo = package()["voiceover"]
    vo["lines"][0]["text"] = "Сегодня мы с тобой приготовим очень вкусный и быстрый боул с тунцом и шпинатом"
    vo["lines"][1]["scene"] = 42
    vo["lines"][2]["text"] = "Рис варим 40 минут."
    reasons = cp.check_voiceover(vo, VIDEO_BRIEF, RECIPE, BRIEF, RULES)
    assert "сцена 1: 14 слов на 4 с — максимум 10" in reasons
    assert "реплика 2: сцены 42 нет в video_brief.json" in reasons
    assert "сцена 3: число 40 не из рецепта" in reasons


def test_voiceover_duplicate_scene():
    vo = package()["voiceover"]
    vo["lines"][1]["scene"] = 1
    assert "сцена 1: больше одной реплики" in cp.check_voiceover(vo, VIDEO_BRIEF, RECIPE, BRIEF, RULES)


# --- папка целиком и CLI -------------------------------------------------------------------------------------

def test_folder_all_sections_ok(tmp_path):
    root = make_root(tmp_path)
    folder = write_package(root)
    result = cp.check_folder(folder, RULES, root)
    assert result["ok"] is True
    assert set(result["sections"]) == set(cp.SECTIONS)


def test_folder_missing_file_reported_in_dependent_sections(tmp_path):
    root = make_root(tmp_path)
    folder = write_package(root, skip=("recipe",))
    result = cp.check_folder(folder, RULES, root, only=("brief", "recipe", "shots"))
    assert result["ok"] is False
    assert result["sections"]["brief"] == []
    assert result["sections"]["recipe"] == ["нет файла recipe.json"]
    assert result["sections"]["shots"] == ["нет файла recipe.json"]


def test_folder_broken_structure_is_a_reason_not_a_crash(tmp_path):
    root = make_root(tmp_path)
    folder = write_package(root, data=package(shots=["не объект"]))
    result = cp.check_folder(folder, RULES, root, only=("shots", "video_brief"))
    assert result["sections"]["shots"] == ["shots.json: нужен объект со списком shots"]
    assert result["sections"]["video_brief"]  # ссылки на кадры не находятся


def test_cli(tmp_path, capsys):
    root = make_root(tmp_path)
    folder = write_package(root)
    assert cp.main([str(folder), "--root", str(root), "--only", "brief,recipe"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True and set(out["sections"]) == {"brief", "recipe"}
    assert cp.main([str(folder), "--root", str(root), "--only", "nope"]) == 2
    assert cp.main([str(tmp_path / "missing"), "--root", str(root)]) == 2


@pytest.mark.parametrize("name", ["brief", "recipe", "shots", "texts", "video_brief", "voiceover"])
def test_each_section_rejects_non_object(name):
    data = package(**{name: []})
    files = {key: data[key] for key in cp.NEEDS[name]}
    with pytest.raises(cp.CheckError):
        cp.RUNNERS[name](files, FOLDER, RULES, set())
