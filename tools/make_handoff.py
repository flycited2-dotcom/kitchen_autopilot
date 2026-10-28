"""Пакет для владельца: задания ChatGPT (фото), Grok (видео), ElevenLabs (озвучка), подписи площадок, рецепт.

Запуск: python tools/make_handoff.py runs/2026-11-02/01-boul-s-tuncom [--root .]
Пишет в папку блюда ready/*.txt и создаёт пустые images/, clips/, voice/ — туда владелец кладёт результаты.
Работает только после принятого редактором пакета (verdicts/package.json, ok=true).
Код: 0 — готово, 1 — нет принятого вердикта, 2 — ошибка входа.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from kitchen_common import ROOT, CheckError, canon_number, load_yaml, read_json

FILES = ("brief", "recipe", "shots", "texts", "video_brief", "voiceover")
PLATFORMS = (("youtube", "YouTube"), ("tiktok", "TikTok"), ("instagram", "Instagram"), ("facebook", "Facebook"),
             ("telegram", "Telegram"), ("vk", "VK"))
KINDS = {"hero": "главный кадр", "ingredients": "ингредиенты", "process": "процесс", "detail": "деталь",
         "serving": "подача", "cover": "обложка"}
LINE = "────────"


def display_number(value) -> str:
    return canon_number(value).replace(".", ",")


def qty_text(item: dict) -> str:
    if item.get("qty") is None:
        return item["unit"]
    return f"{display_number(item['qty'])} {item['unit']}"


def todo_text(pkg: dict, brand: str, rubrics: dict) -> str:
    brief, shots, video = pkg["brief"], pkg["shots"]["shots"], pkg["video_brief"]["scenes"]
    rubric = rubrics.get(brief["rubric"], {}).get("title", brief["rubric"])
    return "\n".join([
        f"{brand} — {pkg['recipe']['dish']}",
        f"{brief['date']}, блюдо {brief['slot']} · {rubric} · {brief['meal']}",
        "",
        "Что сделать, чтобы получился ролик:",
        f"1. Фото — 1_фото_ChatGPT.txt: {len(shots)} кадров → папка images.",
        f"2. Видео — 2_видео_Grok.txt: {len(video)} клипов → папка clips.",
        "3. Озвучка — 3_озвучка.txt → ElevenLabs → файл voice/voiceover.mp3.",
        "4. Сборка и проверка — в папке проекта запустите:",
        f"   powershell -ExecutionPolicy Bypass -File scripts\\kitchen-finish.ps1 {brief['date']}",
        "   Получится ready\\video.mp4 и ready\\cover.jpg.",
        "5. Публикация — вручную: подписи для площадок в папке 4_тексты, рецепт — 5_рецепт.txt.",
        "",
    ])


def photo_text(pkg: dict) -> str:
    shots = pkg["shots"]
    lines = [
        f"«{pkg['recipe']['dish']}» — фото для ChatGPT: {len(shots['shots'])} кадров, вертикаль.",
        "",
        "Как делать:",
        "1. Откройте НОВЫЙ чат ChatGPT и первым сообщением отправьте блок СТИЛЬ.",
        "2. Дальше по одному отправляйте промпты кадров. Если стиль «поплыл» — допишите:",
        "   «в том же стиле, та же посуда и тот же стол».",
        "3. Каждую картинку сохраняйте в папку images этого блюда под указанным именем.",
        "   Подойдут .png, .jpg и .webp — главное, номер в имени (01, 02 …).",
        "",
        "СТИЛЬ:",
        shots["style_block"],
    ]
    for shot in shots["shots"]:
        kind = KINDS.get(shot["kind"], shot["kind"])
        if shot["kind"] == "process" and shot.get("step"):
            kind = f"{kind}, шаг {shot['step']}"
        lines += ["", LINE,
                  f"Кадр {shot['n']:02d} · {shot['title_ru']} · {kind} · {shot['angle']} → images/{shot['n']:02d}.png",
                  shot["prompt"]]
    return "\n".join(lines) + "\n"


def grok_text(pkg: dict) -> str:
    video = pkg["video_brief"]
    total = sum(scene["seconds"] for scene in video["scenes"])
    lines = [
        f"«{pkg['recipe']['dish']}» — видео для Grok: {len(video['scenes'])} сцен, всего {total:g} с, вертикаль 9:16.",
        "",
        "Как делать:",
        "1. Для каждой сцены прикрепите в Grok указанное фото из папки images и вставьте промпт сцены.",
        "2. Готовый клип сохраните в папку clips под номером сцены: 01.mp4, 02.mp4 …",
        "3. Титры и озвучку в Grok НЕ добавляйте — их наложит сборка (scripts\\kitchen-finish.ps1).",
        "   Клип длиннее сцены сборка обрежет сама, короче — дотянет последним кадром.",
        "",
        "ТЕХНИЧЕСКОЕ ОПИСАНИЕ РОЛИКА (можно отправить Grok первым сообщением):",
        video["technical_description"],
    ]
    for scene in video["scenes"]:
        lines += ["", LINE,
                  f"Сцена {scene['n']:02d} · {scene['seconds']:g} с · фото {scene['shot']:02d} из папки images "
                  f"→ clips/{scene['n']:02d}.mp4",
                  f"Камера: {scene['camera']}",
                  f"Промпт: {scene['motion_prompt']}",
                  f"Титр (наложит сборка): {scene.get('title') or '—'}"]
    return "\n".join(lines) + "\n"


def voice_text(pkg: dict) -> str:
    voiceover = pkg["voiceover"]
    seconds = {scene["n"]: scene["seconds"] for scene in pkg["video_brief"]["scenes"]}
    lines = [
        f"«{pkg['recipe']['dish']}» — озвучка для ElevenLabs.",
        f"Голос: {voiceover['voice']}",
        "Готовый файл сохраните как voice/voiceover.mp3 (подойдут .wav и .m4a).",
        "",
        "По сценам (сколько секунд на реплику):",
    ]
    lines += [f"Сцена {line['scene']:02d} ({seconds[line['scene']]:g} с): {line['text']}" for line in voiceover["lines"]]
    lines += ["", "Весь текст одним куском:"] + [line["text"] for line in voiceover["lines"]]
    return "\n".join(lines) + "\n"


def platform_text(key: str, item: dict) -> str:
    tags = " ".join(item["hashtags"])
    body = item["text"].strip() + (f"\n\n{tags}" if tags else "")
    if key == "youtube":
        return f"ЗАГОЛОВОК:\n{item['title']}\n\nОПИСАНИЕ:\n{body}\n"
    if key == "telegram":
        return (f"ПОДПИСЬ К ВИДЕО:\n{body}\n\n{LINE} ВТОРОЕ СООБЩЕНИЕ (рецепт) {LINE}\n"
                f"{item['recipe_post'].strip()}\n")
    return body + "\n"


def recipe_text(recipe: dict) -> str:
    lines = [recipe["dish"], f"Порций: {recipe['servings']} · Время: {recipe['time_total_min']} мин", "",
             "Ингредиенты:"]
    lines += [f"— {item['name']} — {qty_text(item)}" for item in recipe["ingredients"]]
    lines += ["", "Приготовление:"] + [f"{step['n']}. {step['text']}" for step in recipe["steps"]]
    notes = recipe.get("safety_notes") or []
    if notes:
        lines += ["", "Важно:"] + [f"— {note}" for note in notes]
    return "\n".join(lines) + "\n"


def build(folder: Path, pkg: dict, brand: str, rubrics: dict) -> list[Path]:
    ready = folder / "ready"
    texts = {
        ready / "0_ЧТО_ДЕЛАТЬ.txt": todo_text(pkg, brand, rubrics),
        ready / "1_фото_ChatGPT.txt": photo_text(pkg),
        ready / "2_видео_Grok.txt": grok_text(pkg),
        ready / "3_озвучка.txt": voice_text(pkg),
        ready / "5_рецепт.txt": recipe_text(pkg["recipe"]),
    }
    for key, title in PLATFORMS:
        texts[ready / "4_тексты" / f"{title}.txt"] = platform_text(key, pkg["texts"]["platforms"][key])
    for path, text in texts.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        # utf-8-sig: Блокнот на любой Windows открывает кириллицу без «кракозябр».
        path.write_text(text, encoding="utf-8-sig")
    for name in ("images", "clips", "voice"):
        (folder / name).mkdir(exist_ok=True)
    return list(texts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT, help="корень проекта с config/ и rules/")
    args = parser.parse_args(argv)
    try:
        verdict_path = args.folder / "verdicts" / "package.json"
        verdict = read_json(verdict_path, "вердикт") if verdict_path.is_file() else None
        if not (isinstance(verdict, dict) and verdict.get("ok") is True):
            print(json.dumps({"ok": False, "error": "пакет не принят редактором (verdicts/package.json)"},
                             ensure_ascii=False))
            return 1
        pkg = {name: read_json(args.folder / f"{name}.json", f"{name}.json") for name in FILES}
        config = load_yaml(args.root / "config" / "kitchen.yaml")
        rubrics = load_yaml(args.root / "rules" / "rubrics.yaml")
        written = build(args.folder, pkg, config["brand"], rubrics)
    except (CheckError, OSError, KeyError, TypeError, yaml.YAMLError) as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 2
    print(json.dumps({"ok": True, "ready": (args.folder / "ready").as_posix(),
                      "files": [path.relative_to(args.folder).as_posix() for path in written]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
