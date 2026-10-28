import json
import shutil
import subprocess

import pytest
from PIL import Image

import assemble
import check_video
import frames
import media
from kitchen_common import load_yaml
from tests.kitchen_fixtures import ID, ROOT, make_root, write_json

CONFIG = load_yaml(ROOT / "config" / "kitchen.yaml")
VIDEO_RULES = load_yaml(ROOT / "rules" / "video.yaml")
HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="нет ffmpeg/ffprobe")

BRIEF = {"id": ID, "cover_shot": 1, "scenes": [
    {"n": 1, "shot": 1, "seconds": 4, "title": "Рис — 150 г"},
    {"n": 2, "shot": 2, "seconds": 2, "title": ""},
]}


def _ffmpeg(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def _dish(tmp_path, voice_seconds=None, music=True):
    root = make_root(tmp_path)
    folder = root / "runs" / "2026-11-02" / "01-boul-s-tuncom"
    write_json(folder / "video_brief.json", BRIEF)
    write_json(folder / "recipe.json", {"id": ID, "dish": "Боул с тунцом и шпинатом"})
    (folder / "clips").mkdir()
    (folder / "images").mkdir()
    (folder / "voice").mkdir()
    # клип 1: вертикальный, 3 с со звуком (короче сцены — дотянется последним кадром)
    _ffmpeg("-f", "lavfi", "-i", "testsrc=size=720x1280:rate=24", "-f", "lavfi", "-i", "sine=frequency=440",
            "-t", "3", "-shortest", "-pix_fmt", "yuv420p", str(folder / "clips" / "01.mp4"))
    # клип 2: горизонтальный, без звука (обрежется по центру, получит тишину)
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30", "-t", "3", "-pix_fmt", "yuv420p",
            str(folder / "clips" / "02.mp4"))
    Image.new("RGB", (1024, 1536), (180, 140, 90)).save(folder / "images" / "01.png")
    if voice_seconds:
        _ffmpeg("-f", "lavfi", "-i", f"sine=frequency=220:duration={voice_seconds}", str(folder / "voice" / "voiceover.wav"))
    if music:
        (root / "media" / "music").mkdir(parents=True)
        _ffmpeg("-f", "lavfi", "-i", "sine=frequency=660:duration=2", str(root / "media" / "music" / "track.wav"))
    return root, folder


# --- без ffmpeg ----------------------------------------------------------------------------------------------

def test_scene_plan_timeline():
    plan = assemble.scene_plan(BRIEF)
    assert [(s["start"], s["end"]) for s in plan] == [(0.0, 4.0), (4.0, 6.0)]
    assert plan[1]["title"] == ""


def test_missing_inputs(tmp_path):
    folder = tmp_path / "dish"
    (folder / "clips").mkdir(parents=True)
    (folder / "clips" / "02.MP4").write_bytes(b"x")
    assert assemble.missing_inputs(folder, BRIEF) == ["clips/01.mp4", "images/01.png (обложка)"]


def test_pick_music_is_deterministic(tmp_path):
    for name in ("a.mp3", "b.wav", "c.m4a", "readme.md"):
        (tmp_path / name).write_bytes(b"x")
    first = assemble.pick_music(tmp_path, "dish-1")
    assert first == assemble.pick_music(tmp_path, "dish-1")
    assert first.suffix in (".mp3", ".wav", ".m4a")
    assert assemble.pick_music(tmp_path / "none", "dish-1") is None


def test_final_command_mixes_only_present_audio(tmp_path):
    base, out = tmp_path / "base.mp4", tmp_path / "out.mp4"
    only_clip = " ".join(assemble.final_command(base, [], None, None, 6.0, out, 30, CONFIG))
    assert "amix" not in only_clip and "[a0]loudnorm=I=-14" in only_clip
    titles = [(tmp_path / "t1.png", 0.0, 4.0)]
    full = assemble.final_command(base, titles, tmp_path / "v.wav", tmp_path / "m.mp3", 6.0, out, 30, CONFIG)
    graph = full[full.index("-filter_complex") + 1]
    assert "overlay=0:0:enable='between(t,0.000,4.000)'" in graph
    assert "[2:a]" in graph and "adelay=300|300" in graph  # озвучка — вход 2 (после титра)
    assert "[3:a]" in graph and "afade=t=out:st=4.500" in graph  # музыка — вход 3
    assert "amix=inputs=3:duration=first:normalize=0" in graph
    assert full[full.index("-stream_loop") + 1] == "-1"


def test_scene_command_uses_silence_when_clip_has_no_audio(tmp_path):
    cmd = assemble.scene_command(tmp_path / "c.mp4", tmp_path / "o.mp4", 4.0, False, (1080, 1920), 30)
    assert "anullsrc=r=48000:cl=stereo" in cmd
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert graph.startswith("[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920")
    assert "[1:a]" in graph and "tpad=stop_mode=clone:stop_duration=4.000" in graph


def test_render_title_draws_plate_at_lower_third():
    font = assemble.find_font(CONFIG)
    image = assemble.render_title("Тунец — по 1–2 минуты", (1080, 1920), font, CONFIG)
    assert image.size == (1080, 1920) and image.mode == "RGBA"
    alpha = image.getchannel("A")
    assert alpha.getpixel((540, int(1920 * 0.74))) > 0
    assert alpha.getpixel((540, 200)) == 0


def test_short_words_stick_to_next_word():
    assert assemble._units("Боул с тунцом и шпинатом") == ["Боул", "с тунцом", "и шпинатом"]
    assert assemble._units("Суп и") == ["Суп и"]
    assert assemble._units("— 150 г") == ["— 150 г"]
    assert assemble._units("ок") == ["ок"]


def test_find_font_error():
    with pytest.raises(assemble.CheckError, match="шрифт"):
        assemble.find_font({"fonts": ["/nope/font.ttf"]})


def test_check_video_rules():
    info = {"streams": [{"codec_type": "video", "width": 1080, "height": 1920, "avg_frame_rate": "30/1"},
                        {"codec_type": "audio"}], "format": {"duration": "30.02"}}
    assert check_video.check(info, 10 * 1024 * 1024, VIDEO_RULES) == []
    bad = {"streams": [{"codec_type": "video", "width": 720, "height": 1280, "avg_frame_rate": "24/1"}],
           "format": {"duration": "70"}}
    reasons = check_video.check(bad, 60 * 1024 * 1024, VIDEO_RULES)
    assert "размер 720×1280, нужно 1080×1920" in reasons
    assert "частота кадров 24.0, нужно 30" in reasons
    assert "длительность 70.0 с, нужно от 15 до 59" in reasons
    assert "нет звуковой дорожки" in reasons
    assert "файл 60.0 МБ — больше 50 МБ" in reasons
    assert check_video.check({"streams": []}, 0, VIDEO_RULES) == ["нет видеодорожки"]


# --- с ffmpeg ------------------------------------------------------------------------------------------------

@needs_ffmpeg
def test_assemble_end_to_end(tmp_path, capsys):
    root, folder = _dish(tmp_path, voice_seconds=3)
    assert assemble.main([str(folder), "--root", str(root)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is True and result["voice"] == "voiceover.wav" and result["music"] == "track.wav"
    info = media.probe(folder / "ready" / "video.mp4")
    rules = dict(VIDEO_RULES, min_total_seconds=5)
    assert check_video.check(info, (folder / "ready" / "video.mp4").stat().st_size, rules) == []
    assert abs(media.duration(info) - 6.0) < 0.3
    with Image.open(folder / "ready" / "cover.jpg") as cover:
        assert cover.size == (1080, 1920)
    shots = frames.extract(folder / "ready" / "video.mp4", folder / "review" / "frames", 2)
    assert len(shots) >= 3
    with Image.open(shots[0]) as frame:
        assert frame.size[0] == 540


@needs_ffmpeg
def test_assemble_without_voice_and_music(tmp_path, capsys):
    root, folder = _dish(tmp_path, voice_seconds=None, music=False)
    assert assemble.main([str(folder), "--root", str(root)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["voice"] is None and result["music"] is None
    assert media.has_audio(media.probe(folder / "ready" / "video.mp4"))


@needs_ffmpeg
def test_voice_longer_than_video_is_refused(tmp_path, capsys):
    root, folder = _dish(tmp_path, voice_seconds=9, music=False)
    assert assemble.main([str(folder), "--root", str(root)]) == 1
    assert "длиннее ролика" in json.loads(capsys.readouterr().out)["error"]
    assert not (folder / "ready" / "video.mp4").exists()
    assert assemble.main([str(folder), "--root", str(root), "--allow-trim"]) == 0


def test_missing_clips_reported(tmp_path, capsys):
    root = make_root(tmp_path)
    folder = root / "runs" / "2026-11-02" / "01-boul-s-tuncom"
    write_json(folder / "video_brief.json", BRIEF)
    write_json(folder / "recipe.json", {"id": ID, "dish": "Боул"})
    assert assemble.main([str(folder), "--root", str(root)]) == 1
    assert json.loads(capsys.readouterr().out)["missing"] == ["clips/01.mp4", "clips/02.mp4", "images/01.png (обложка)"]


@needs_ffmpeg
def test_check_video_cli(tmp_path, capsys):
    root, folder = _dish(tmp_path, voice_seconds=None, music=False)
    assemble.main([str(folder), "--root", str(root)])
    capsys.readouterr()
    assert check_video.main([str(folder / "ready" / "video.mp4")]) == 1  # 6 с < 15 с по боевым правилам
    out = json.loads(capsys.readouterr().out)
    assert out["reasons"] == ["длительность 6.0 с, нужно от 15 до 59"]
    assert check_video.main([str(folder / "nope.mp4")]) == 2
