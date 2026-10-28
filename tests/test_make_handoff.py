import json

import make_handoff
from tests.kitchen_fixtures import DATE, make_root, package, write_json, write_package


def _ready(tmp_path, data=None, verdict=True):
    root = make_root(tmp_path)
    folder = write_package(root, data)
    if verdict is not None:
        write_json(folder / "verdicts" / "package.json", {"stage": "package", "ok": verdict})
    return root, folder


def _read(path):
    return path.read_text(encoding="utf-8-sig")


def test_handoff_files_and_folders(tmp_path, capsys):
    root, folder = _ready(tmp_path)
    assert make_handoff.main([str(folder), "--root", str(root)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    ready = folder / "ready"
    for name in ("0_ЧТО_ДЕЛАТЬ.txt", "1_фото_ChatGPT.txt", "2_видео_Grok.txt", "3_озвучка.txt", "5_рецепт.txt"):
        assert (ready / name).is_file(), name
    for name in ("YouTube", "TikTok", "Instagram", "Facebook", "Telegram", "VK"):
        assert (ready / "4_тексты" / f"{name}.txt").is_file(), name
    for name in ("images", "clips", "voice"):
        assert (folder / name).is_dir()


def test_photo_file_has_style_and_all_20_prompts(tmp_path, capsys):
    root, folder = _ready(tmp_path)
    make_handoff.main([str(folder), "--root", str(root)])
    text = _read(folder / "ready" / "1_фото_ChatGPT.txt")
    assert "No text, no logos, no watermarks" in text
    assert "Кадр 01" in text and "Кадр 20" in text and "Кадр 21" not in text
    assert "→ images/01.png" in text
    assert "процесс, шаг 2" in text


def test_grok_file_has_scenes_photos_and_titles(tmp_path, capsys):
    root, folder = _ready(tmp_path)
    make_handoff.main([str(folder), "--root", str(root)])
    text = _read(folder / "ready" / "2_видео_Grok.txt")
    assert "7 сцен, всего 30 с" in text
    assert "Сцена 01 · 4 с · фото 16 из папки images → clips/01.mp4" in text
    assert "Титр (наложит сборка): Рис — 150 г" in text
    assert "Vertical 9:16 cooking short" in text


def test_voice_and_texts(tmp_path, capsys):
    root, folder = _ready(tmp_path)
    make_handoff.main([str(folder), "--root", str(root)])
    voice = _read(folder / "ready" / "3_озвучка.txt")
    assert "Сцена 01 (4 с): Обед за 25 минут — боул с тунцом!" in voice
    assert voice.rstrip().endswith("Сохрани рецепт и подпишись!")
    youtube = _read(folder / "ready" / "4_тексты" / "YouTube.txt")
    assert youtube.startswith("ЗАГОЛОВОК:\nБоул с тунцом за 25 минут")
    assert "#кухнянараздва #рецепт #shorts" in youtube
    telegram = _read(folder / "ready" / "4_тексты" / "Telegram.txt")
    assert "ВТОРОЕ СООБЩЕНИЕ" in telegram and "Стейк тунца — 250 г" in telegram


def test_recipe_text_formats_quantities(tmp_path, capsys):
    data = package()
    data["recipe"]["ingredients"][6]["qty"] = 0.5
    root, folder = _ready(tmp_path, data)
    make_handoff.main([str(folder), "--root", str(root)])
    recipe = _read(folder / "ready" / "5_рецепт.txt")
    assert "— кунжут — 0,5 ч. л." in recipe
    assert "— соль — по вкусу" in recipe
    assert "Порций: 2 · Время: 25 мин" in recipe
    assert "4. Выложить в миски" in recipe
    todo = _read(folder / "ready" / "0_ЧТО_ДЕЛАТЬ.txt")
    assert "Кухня на раз-два — Боул с тунцом и шпинатом" in todo
    assert f"scripts\\kitchen-finish.ps1 {DATE}" in todo


def test_refuses_without_positive_verdict(tmp_path, capsys):
    root, folder = _ready(tmp_path, verdict=False)
    assert make_handoff.main([str(folder), "--root", str(root)]) == 1
    assert not (folder / "ready").exists()
    root, folder = _ready(tmp_path / "second", verdict=None)
    assert make_handoff.main([str(folder), "--root", str(root)]) == 1


def test_missing_file_is_input_error(tmp_path, capsys):
    root = make_root(tmp_path)
    folder = write_package(root, skip=("voiceover",))
    write_json(folder / "verdicts" / "package.json", {"stage": "package", "ok": True})
    assert make_handoff.main([str(folder), "--root", str(root)]) == 2
    assert "voiceover.json" in json.loads(capsys.readouterr().out)["error"]
