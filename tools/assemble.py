"""Сборка мастер-ролика 9:16 из клипов Grok: титры, озвучка, музыка, обложка.

Запуск: python tools/assemble.py runs/2026-11-02/01-boul-s-tuncom [--root .] [--allow-trim]
Вход (папка блюда): video_brief.json, recipe.json, clips/NN.mp4 по сценам, images/NN.(png|jpg|jpeg|webp) —
кадр обложки (cover_shot), voice/voiceover.(mp3|wav|m4a) — по желанию. Музыка — media/music/ проекта, по желанию.
Выход: ready/video.mp4 и ready/cover.jpg; промежуточные файлы — work/ (можно удалить).
Код: 0 — собрано, 1 — не хватает файлов или озвучка длиннее ролика, 2 — ошибка входа или ffmpeg.
Текст на кадр кладёт эта сборка (Pillow → PNG → overlay), а не генератор: генераторы искажают буквы.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont, ImageOps

import media
from kitchen_common import ROOT, CheckError, load_yaml, read_json

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
CLIP_EXTS = (".mp4", ".mov", ".webm")
AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".aac", ".ogg")
AUDIO_FORMAT = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"


def find_media(directory: Path, stem: str, exts: tuple[str, ...]) -> Path | None:
    for ext in exts:
        for candidate in (directory / f"{stem}{ext}", directory / f"{stem}{ext.upper()}"):
            if candidate.is_file():
                return candidate
    return None


def scene_plan(video_brief: dict) -> list[dict]:
    """Сцены на общей шкале времени: начало, конец, титр."""
    start, plan = 0.0, []
    for scene in video_brief["scenes"]:
        seconds = float(scene["seconds"])
        plan.append({"n": scene["n"], "seconds": seconds, "start": start, "end": start + seconds,
                     "title": (scene.get("title") or "").strip()})
        start += seconds
    return plan


def missing_inputs(folder: Path, video_brief: dict) -> list[str]:
    missing = [f"clips/{scene['n']:02d}.mp4" for scene in video_brief["scenes"]
               if not find_media(folder / "clips", f"{scene['n']:02d}", CLIP_EXTS)]
    cover = video_brief["cover_shot"]
    if not find_media(folder / "images", f"{cover:02d}", IMAGE_EXTS):
        missing.append(f"images/{cover:02d}.png (обложка)")
    return missing


def pick_music(music_dir: Path, key: str) -> Path | None:
    """Трек выбирается детерминированно по id блюда: пересборка даёт тот же звук."""
    tracks = sorted(path for path in Path(music_dir).glob("*") if path.suffix.lower() in AUDIO_EXTS) \
        if Path(music_dir).is_dir() else []
    if not tracks:
        return None
    return tracks[int(hashlib.sha1(key.encode("utf-8")).hexdigest(), 16) % len(tracks)]


def scene_command(clip: Path, out: Path, seconds: float, clip_has_audio: bool, size: tuple[int, int],
                  fps: int) -> list[str]:
    """Клип → ровно seconds секунд 9:16: обрезка по центру, дотягивание последним кадром, звук или тишина."""
    width, height = size
    video = (f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},"
             f"fps={fps},setsar=1,tpad=stop_mode=clone:stop_duration={seconds:.3f},"
             f"trim=duration={seconds:.3f},setpts=PTS-STARTPTS,format=yuv420p[v]")
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(clip)]
    if clip_has_audio:
        audio_input = "[0:a]"
    else:
        cmd += ["-f", "lavfi", "-t", f"{seconds:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
        audio_input = "[1:a]"
    audio = f"{audio_input}{AUDIO_FORMAT},apad,atrim=duration={seconds:.3f},asetpts=PTS-STARTPTS[a]"
    return cmd + ["-filter_complex", f"{video};{audio}", "-map", "[v]", "-map", "[a]",
                  "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(fps),
                  "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", str(out)]


def concat_command(list_file: Path, out: Path) -> list[str]:
    return ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy",
            str(out)]


def final_command(base: Path, titles: list[tuple[Path, float, float]], voice: Path | None, music: Path | None,
                  total: float, out: Path, fps: int, config: dict) -> list[str]:
    """Титры поверх видео по времени сцен; звук сцен + озвучка + музыка → громкость под соцсети."""
    audio, encode = config["audio"], config["encode"]
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(base)]
    for png, _, _ in titles:
        cmd += ["-loop", "1", "-t", f"{total:.3f}", "-i", str(png)]
    index = 1 + len(titles)
    voice_index = music_index = None
    if voice:
        cmd += ["-i", str(voice)]
        voice_index, index = index, index + 1
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(music)]
        music_index = index
    graph, label = [], "[0:v]"
    for k, (_, start, end) in enumerate(titles, 1):
        graph.append(f"{label}[{k}:v]overlay=0:0:enable='between(t,{start:.3f},{end:.3f})'[v{k}]")
        label = f"[v{k}]"
    graph.append(f"{label}format=yuv420p[vout]")
    graph.append(f"[0:a]{AUDIO_FORMAT},volume={audio['clip_volume']}[a0]")
    mix = ["[a0]"]
    if voice_index is not None:
        delay = int(audio["voice_delay_ms"])
        graph.append(f"[{voice_index}:a]{AUDIO_FORMAT},adelay={delay}|{delay},volume={audio['voice_volume']}[a1]")
        mix.append("[a1]")
    if music_index is not None:
        fade = float(audio["fade_out_seconds"])
        graph.append(f"[{music_index}:a]{AUDIO_FORMAT},atrim=duration={total:.3f},volume={audio['music_volume']},"
                     f"afade=t=out:st={max(total - fade, 0):.3f}:d={fade:.3f}[a2]")
        mix.append("[a2]")
    loudness = f"loudnorm=I={audio['loudness_lufs']}:TP=-1.5:LRA=11,aresample=48000"
    if len(mix) > 1:
        graph.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=first:normalize=0,{loudness}[aout]")
    else:
        graph.append(f"[a0]{loudness}[aout]")
    return cmd + ["-filter_complex", ";".join(graph), "-map", "[vout]", "-map", "[aout]",
                  "-c:v", "libx264", "-preset", str(encode["preset"]), "-crf", str(encode["crf"]),
                  "-pix_fmt", "yuv420p", "-r", str(fps), "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                  "-movflags", "+faststart", "-t", f"{total:.3f}", str(out)]


def find_font(config: dict) -> str:
    for path in config["fonts"]:
        if Path(path).is_file():
            return path
    raise CheckError("не найден шрифт с кириллицей: впишите путь к .ttf в config/kitchen.yaml → fonts")


def _units(text: str) -> list[str]:
    """Слова для переноса: предлог или союз из 1–2 букв «приклеен» к следующему слову, а короткий хвост
    («150 г») — к предыдущему, чтобы ничего не висело в одиночку."""
    units, pending = [], ""
    for word in text.split():
        word = f"{pending} {word}".strip()
        pending = word if len(word) <= 2 else ""
        if not pending:
            units.append(word)
    if pending and units:
        units[-1] = f"{units[-1]} {pending}"
    elif pending:
        units.append(pending)
    return units


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: float) -> list[str]:
    lines, current = [], ""
    for word in _units(text):
        trial = f"{current} {word}".strip()
        if current and draw.textlength(trial, font=font) > max_width:
            lines.append(current)
            current = word
        else:
            current = trial
    return lines + [current] if current else lines


def draw_plate(image: Image.Image, text: str, font_path: str, font_size: int, y_ratio: float,
               style: dict) -> Image.Image:
    """Белый текст на полупрозрачной тёмной плашке: по центру по горизонтали, центр плашки — на y_ratio высоты."""
    width, height = image.size
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = ImageFont.truetype(font_path, font_size)
    padding = style["padding"]
    lines = _wrap(draw, text, font, width * style["max_width_ratio"] - 2 * padding)
    line_height = int(font_size * 1.25)
    block_width = max(draw.textlength(line, font=font) for line in lines)
    block_height = line_height * len(lines)
    cx, cy = width / 2, height * y_ratio
    draw.rounded_rectangle((cx - block_width / 2 - padding, cy - block_height / 2 - padding,
                            cx + block_width / 2 + padding, cy + block_height / 2 + padding),
                           radius=style["radius"], fill=(0, 0, 0, style["plate_opacity"]))
    for i, line in enumerate(lines):
        draw.text((cx, cy - block_height / 2 + line_height * (i + 0.5)), line, font=font,
                  fill=(255, 255, 255, 255), anchor="mm")
    return Image.alpha_composite(image.convert("RGBA"), overlay)


def render_title(text: str, size: tuple[int, int], font_path: str, config: dict) -> Image.Image:
    style = config["title"]
    return draw_plate(Image.new("RGBA", size, (0, 0, 0, 0)), text, font_path, style["font_size"], style["y_ratio"],
                      style)


def render_cover(image_path: Path, title: str, size: tuple[int, int], font_path: str, config: dict,
                 out: Path) -> None:
    with Image.open(image_path) as source:
        picture = ImageOps.fit(source.convert("RGB"), size, Image.Resampling.LANCZOS)
    cover = draw_plate(picture, title, font_path, config["cover"]["font_size"], config["cover"]["y_ratio"],
                       config["title"])
    cover.convert("RGB").save(out, "JPEG", quality=92)


def assemble(folder: Path, root: Path, allow_trim: bool = False) -> dict:
    video_brief = read_json(folder / "video_brief.json", "video_brief.json")
    recipe = read_json(folder / "recipe.json", "recipe.json")
    missing = missing_inputs(folder, video_brief)
    if missing:
        return {"ok": False, "error": "не хватает файлов", "missing": missing}
    config = load_yaml(root / "config" / "kitchen.yaml")
    rules = load_yaml(root / "rules" / "video.yaml")
    size, fps = (rules["width"], rules["height"]), rules["fps"]
    plan = scene_plan(video_brief)
    total = plan[-1]["end"]
    voice = find_media(folder / "voice", "voiceover", AUDIO_EXTS)
    if voice:
        voice_seconds = media.duration(media.probe(voice)) + config["audio"]["voice_delay_ms"] / 1000
        if voice_seconds > total + 0.05 and not allow_trim:
            return {"ok": False, "error": f"озвучка {voice_seconds:.1f} с длиннее ролика {total:g} с — сократите "
                                          f"текст или перегенерируйте (или --allow-trim)"}
    font = find_font(config)
    work, ready = folder / "work", folder / "ready"
    work.mkdir(exist_ok=True)
    ready.mkdir(exist_ok=True)

    names = []
    for scene in plan:
        clip = find_media(folder / "clips", f"{scene['n']:02d}", CLIP_EXTS)
        out = work / f"scene_{scene['n']:02d}.mp4"
        media.run(scene_command(clip, out, scene["seconds"], media.has_audio(media.probe(clip)), size, fps))
        names.append(out.name)
    list_file = work / "list.txt"
    list_file.write_text("".join(f"file '{name}'\n" for name in names), encoding="utf-8")
    base = work / "concat.mp4"
    media.run(concat_command(list_file, base))

    titles = []
    for scene in plan:
        if scene["title"]:
            png = work / f"title_{scene['n']:02d}.png"
            render_title(scene["title"], size, font, config).save(png)
            titles.append((png, scene["start"], scene["end"]))
    music = pick_music(root / config["music_dir"], video_brief["id"])
    video = ready / "video.mp4"
    media.run(final_command(base, titles, voice, music, total, video, fps, config))
    cover = ready / "cover.jpg"
    cover_image = find_media(folder / "images", f"{video_brief['cover_shot']:02d}", IMAGE_EXTS)
    render_cover(cover_image, recipe["dish"], size, font, config, cover)
    return {"ok": True, "video": video.as_posix(), "cover": cover.as_posix(), "seconds": total,
            "voice": voice.name if voice else None, "music": music.name if music else None}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT, help="корень проекта с config/, rules/, media/")
    parser.add_argument("--allow-trim", action="store_true", help="обрезать озвучку, если она длиннее ролика")
    args = parser.parse_args(argv)
    try:
        result = assemble(args.folder, args.root, args.allow_trim)
    except (CheckError, OSError, KeyError, TypeError, ValueError, yaml.YAMLError) as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
