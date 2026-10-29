---
description: Пакеты на день — рецепт, 20 кадров для ChatGPT, раскадровка для Grok, озвучка, подписи 6 площадок
argument-hint: <дата ГГГГ-ММ-ДД>
---
Дата: $ARGUMENTS. Папка runs/$ARGUMENTS/ уже создана запускающим скриптом.

Режим запуска — безголовый (`claude -p`): сессия заканчивается, как только ты завершаешь ход.
- Субагентов вызывай только синхронно: `run_in_background: false`. Параллельность — несколько вызовов Agent
  в одном сообщении (разные блюда и независимые шаги одного блюда).
- Не завершай ход и не пиши «жду», пока не выполнен шаг 5.
- Каждому субагенту передавай точный путь папки блюда: runs/$ARGUMENTS/<NN>-<slug>/.

1. Запусти `python tools/plan_day.py $ARGUMENTS --write`. Он печатает блюда дня из недельного плана и создаёт
   папки runs/$ARGUMENTS/<NN>-<slug>/ с brief.json. Код 1 (плана на дату нет) — вызови content-manager в режиме
   «день» на дату $ARGUMENTS: он сам создаст brief.json.
2. Перед КАЖДЫМ вызовом editor сам запусти скрипт этого этапа: «рецепт» —
   `python tools/check_package.py runs/$ARGUMENTS/<NN>-<slug> --only brief,recipe`, «пакет» — без --only.
   Код 1 — верни авторам разделов (recipe → recipe-developer, shots → photo-director, video_brief →
   video-producer, texts/voiceover → copywriter) причины из вывода и запусти скрипт снова; так до 2 раз.
   Эти возвраты не считаются кругами редактора: редактор получает только то, что прошло скрипт, и судит
   по существу. Скрипт так и не прошёл — блюдо закрыто с выводом скрипта.
   Возвращая правку, говори агенту, что номера кадров и шагов, на которые ссылаются другие файлы, менять нельзя.
   Для каждого блюда — по шагам (разные блюда ведёшь параллельно):
   a. recipe-developer → recipe.json.
   b. editor, этап «рецепт» → verdicts/recipe.json. Отказ — один раз верни recipe-developer с notes и причинами,
      затем снова editor. Второй отказ — блюдо закрыто, дальше не идёт.
   c. Параллельно: photo-director → shots.json и copywriter (задание «тексты») → texts.json.
   d. video-producer → video_brief.json.
   e. copywriter (задание «озвучка») → voiceover.json.
   f. editor, этап «пакет» → verdicts/package.json. Отказ — один раз верни КАЖДОМУ агенту из return_to его
      замечания (copywriter — с указанием, какое задание переделать), затем снова editor «пакет».
      Второй отказ — окончательный.
   g. Если пакет принят — `python tools/make_handoff.py runs/$ARGUMENTS/<NN>-<slug>`.
3. Если make_handoff вернул код ≠ 0 — отметь блюдо как «пакет не собран» с выводом команды.
4. Вызови reporter: режим «день», дата $ARGUMENTS → runs/$ARGUMENTS/summary.txt.
5. Последним сообщением выведи содержимое runs/$ARGUMENTS/summary.txt.

Ничего не публикуй и не загружай на площадки. Фото, видео и звук не генерируй — только задания для них.
