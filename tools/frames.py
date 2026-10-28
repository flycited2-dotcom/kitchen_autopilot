"""Кадры ролика для осмотра редактором: каждые N секунд, 540 px по ширине.

Запуск: python tools/frames.py runs/2026-11-02/01-boul-s-tuncom/ready/video.mp4 [--every 2] [--out DIR]
По умолчанию кадры — в <папка блюда>/review/frames/ (ролик лежит в <папка блюда>/ready/).
Вывод: JSON {"ok", "frames": [пути]}. Код: 0 — готово, 2 — ошибка входа или ffmpeg.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import media
from kitchen_common import CheckError


def extract(video: Path, out_dir: Path, every: float) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.jpg"):
        old.unlink()
    media.run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-vf", f"fps=1/{every:g},scale=540:-2",
               str(out_dir / "%02d.jpg")])
    return sorted(out_dir.glob("*.jpg"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--every", type=float, default=2.0, help="шаг в секундах")
    parser.add_argument("--out", type=Path, help="папка для кадров")
    args = parser.parse_args(argv)
    out_dir = args.out or args.video.resolve().parent.parent / "review" / "frames"
    try:
        if not args.video.is_file():
            raise CheckError(f"нет файла {args.video}")
        if args.every <= 0:
            raise CheckError("--every должно быть больше 0")
        frames = extract(args.video, out_dir, args.every)
    except (CheckError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"ok": True, "frames": [path.as_posix() for path in frames]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
