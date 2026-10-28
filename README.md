# kitchen_autopilot — «Кухня на раз-два»

Команда ИИ-агентов, которая каждый день готовит кулинарный контент для YouTube Shorts, TikTok, Instagram Reels,
Facebook Reels, Telegram и ВК: план на неделю → рецепт → 20 кадров → раскадровка ролика → подписи и озвучка →
проверка → сборка готового ролика 9:16. Ниша — повседневная быстрая домашняя еда.

**Этап 1 (сейчас):** всё делается локально на ПК в папке `runs/`. Фото генерирует ChatGPT (веб), видео — Grok
(подписка), озвучку — ElevenLabs; агенты готовят для них точные задания, а сборка и проверки — автоматические.
Публикует владелец вручную. Как пользоваться — [ИНСТРУКЦИЯ.md](ИНСТРУКЦИЯ.md).

## Команда агентов

```
Оркестратор (Claude Code, /kitchen-week, /kitchen-day, /kitchen-finish)
  ├─ content-manager   — что готовим: план на 7 дней × 2 блюда, сезон, разнообразие, без повторов 30 дней
  ├─ recipe-developer  — рецепт: граммы, шаги, время, порции, безопасность
  ├─ photo-director    — 20 кадров с разных ракурсов, промпты для ChatGPT в едином стиле
  ├─ video-producer    — раскадровка 9:16: сцены, движение камеры, титры, ТЗ для Grok
  ├─ copywriter        — подписи под 6 площадок + реплики озвучки по сценам
  ├─ editor            — проверяет план, рецепт, пакет и готовый ролик (скрипты + по существу)
  └─ reporter          — короткий итог владельцу
```

Субагент в Claude Code не может вызвать другого субагента, поэтому задания раздаёт оркестратор,
а контент-менеджер решает, что именно готовим.

## Конвейер блюда

```
brief.json ─► recipe.json ─► editor «рецепт» ─► shots.json + texts.json ─► video_brief.json ─► voiceover.json
                                                                  │
                                                  editor «пакет» ─► make_handoff.py ─► ready/*.txt
владелец: ChatGPT → images/, Grok → clips/, ElevenLabs → voice/
                                                  assemble.py ─► ready/video.mp4 + cover.jpg ─► editor «финал»
```

## Инструменты (tools/)

| Скрипт | Что делает |
|---|---|
| `plan_day.py` | берёт блюда дня из недельного плана, создаёт папки и `brief.json` |
| `check_plan.py` | правила недельного плана: даты, слоты, рубрики, повторы, доля рубрики |
| `check_package.py` | правила пакета: brief, рецепт (единицы, шаги, безопасность), 20 кадров, раскадровка, подписи 6 площадок, озвучка; каждое число — из рецепта |
| `make_handoff.py` | задания для ChatGPT/Grok/ElevenLabs, подписи площадок, рецепт — в `ready/` |
| `assemble.py` | ffmpeg: клипы → 1080×1920, титры (Pillow), озвучка, музыка, громкость; обложка |
| `check_video.py` | размер, частота кадров, длительность, звук, вес файла |
| `frames.py` | кадры ролика для осмотра редактором |

Правила — `rules/*.yaml` и `rules/brand.md`, `rules/style.md`; параметры сборки — `config/kitchen.yaml`.

## Разработка

```bash
pip install -r requirements.txt
python -m pytest
```
Тесты сборки нуждаются в `ffmpeg`/`ffprobe` в PATH (без них пропускаются).

## Дальше

- Этап 2: автоматизация генерации. Фото в ChatGPT — через фото-агента RitualB2B (Chrome + CDP, новый режим
  `kitchen`), видео в Grok — браузерный агент по тому же образцу, озвучка — API ElevenLabs.
- Этап 3: публикация по API (Telegram, ВК, YouTube, TikTok, Instagram, Facebook) по кнопке владельца,
  расписание слотов и аналитика. План — [docs/superpowers/specs/2026-10-28-kitchen-autopilot-design.md](docs/superpowers/specs/2026-10-28-kitchen-autopilot-design.md).
