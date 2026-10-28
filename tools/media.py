"""Обёртки над ffmpeg/ffprobe: запуск команды и свойства медиафайла."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from kitchen_common import CheckError


def require(tool: str) -> None:
    if shutil.which(tool) is None:
        raise CheckError(f"не найден {tool}: установите FFmpeg (winget install Gyan.FFmpeg) и откройте новое окно")


def run(cmd: list[str]) -> str:
    require(cmd[0])
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise CheckError(f"{cmd[0]} завершился с кодом {result.returncode}: {result.stderr.strip()[-800:]}")
    return result.stdout


def probe(path: Path) -> dict:
    return json.loads(run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format",
                           str(path)]))


def duration(info: dict) -> float:
    return float((info.get("format") or {}).get("duration") or 0)


def has_audio(info: dict) -> bool:
    return any(stream.get("codec_type") == "audio" for stream in info.get("streams") or [])


def frame_rate(value: str | None) -> float | None:
    """«30/1» → 30.0; «0/0» и пусто → None."""
    try:
        numerator, denominator = (float(part) for part in str(value).split("/"))
        return numerator / denominator if denominator else None
    except ValueError:
        return None
