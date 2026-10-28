"""Проверка готового ролика по rules/video.yaml: размер, частота кадров, длительность, звук, вес файла.

Запуск: python tools/check_video.py runs/2026-11-02/01-boul-s-tuncom/ready/video.mp4
Вывод: JSON-вердикт в stdout. Код: 0 — прошёл, 1 — отклонён, 2 — ошибка входа или ffprobe.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

import media
from kitchen_common import ROOT, CheckError, load_yaml


def check(info: dict, size_bytes: int, rules: dict) -> list[str]:
    streams = info.get("streams") or []
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    if video is None:
        return ["нет видеодорожки"]
    reasons = []
    if (video.get("width"), video.get("height")) != (rules["width"], rules["height"]):
        reasons.append(f"размер {video.get('width')}×{video.get('height')}, нужно {rules['width']}×{rules['height']}")
    fps = media.frame_rate(video.get("avg_frame_rate") or video.get("r_frame_rate"))
    if fps is None or abs(fps - rules["fps"]) > rules["fps_tolerance"]:
        reasons.append(f"частота кадров {fps if fps is None else round(fps, 2)}, нужно {rules['fps']}")
    seconds, tolerance = media.duration(info), rules["duration_tolerance"]
    if not rules["min_total_seconds"] - tolerance <= seconds <= rules["max_total_seconds"] + tolerance:
        reasons.append(f"длительность {seconds:.1f} с, нужно от {rules['min_total_seconds']} "
                       f"до {rules['max_total_seconds']}")
    if not media.has_audio(info):
        reasons.append("нет звуковой дорожки")
    if size_bytes > rules["max_file_mb"] * 1024 * 1024:
        reasons.append(f"файл {size_bytes / 1024 / 1024:.1f} МБ — больше {rules['max_file_mb']} МБ")
    return reasons


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--rules-dir", type=Path, default=ROOT / "rules")
    args = parser.parse_args(argv)
    try:
        if not args.video.is_file():
            raise CheckError(f"нет файла {args.video}")
        rules = load_yaml(args.rules_dir / "video.yaml")
        info = media.probe(args.video)
        size = args.video.stat().st_size
        reasons = check(info, size, rules)
    except (CheckError, OSError, ValueError, yaml.YAMLError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"ok": not reasons, "seconds": round(media.duration(info), 2),
                      "size_mb": round(size / 1024 / 1024, 1), "reasons": reasons}, ensure_ascii=False))
    return 0 if not reasons else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
