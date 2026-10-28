import json

import plan_day
from tests.kitchen_fixtures import make_root, week_plan, write_json


def test_briefs_from_plan_and_write(tmp_path, capsys):
    root = make_root(tmp_path)
    write_json(root / "plans" / "2026-11-02.json", week_plan())
    assert plan_day.main(["2026-11-04", "--root", str(root), "--write"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["plan"] == "plans/2026-11-02.json"
    assert [s["id"] for s in out["slots"]] == ["2026-11-04-01-zavtrak-2", "2026-11-04-02-uzhin-2"]
    brief = json.loads((root / "runs" / "2026-11-04" / "01-zavtrak-2" / "brief.json").read_text(encoding="utf-8"))
    assert brief == out["slots"][0]
    assert brief["meal"] == "завтрак" and brief["slot"] == 1
    assert out["created"] == ["runs/2026-11-04/01-zavtrak-2", "runs/2026-11-04/02-uzhin-2"]


def test_existing_brief_is_kept(tmp_path, capsys):
    root = make_root(tmp_path)
    write_json(root / "plans" / "2026-11-02.json", week_plan())
    existing = write_json(root / "runs" / "2026-11-04" / "01-zavtrak-2" / "brief.json", {"edited": True})
    assert plan_day.main(["2026-11-04", "--root", str(root), "--write"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["kept"] == ["runs/2026-11-04/01-zavtrak-2"]
    assert json.loads(existing.read_text(encoding="utf-8")) == {"edited": True}


def test_without_write_nothing_created(tmp_path, capsys):
    root = make_root(tmp_path)
    write_json(root / "plans" / "2026-11-02.json", week_plan())
    assert plan_day.main(["2026-11-03", "--root", str(root)]) == 0
    assert not (root / "runs" / "2026-11-03").exists()


def test_latest_plan_wins(tmp_path, capsys):
    root = make_root(tmp_path)
    write_json(root / "plans" / "2026-11-02.json", week_plan())
    newer = week_plan("2026-11-04")
    write_json(root / "plans" / "2026-11-04.json", newer)
    assert plan_day.main(["2026-11-05", "--root", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["plan"] == "plans/2026-11-04.json"


def test_no_plan_for_date(tmp_path, capsys):
    root = make_root(tmp_path)
    assert plan_day.main(["2026-11-04", "--root", str(root)]) == 1
    assert json.loads(capsys.readouterr().out)["slots"] == []


def test_bad_date_and_broken_slot(tmp_path, capsys):
    root = make_root(tmp_path)
    assert plan_day.main(["04.11.2026", "--root", str(root)]) == 2
    plan = week_plan()
    del plan["days"][0]["slots"][0]["slug"]
    write_json(root / "plans" / "2026-11-02.json", plan)
    capsys.readouterr()
    assert plan_day.main(["2026-11-02", "--root", str(root)]) == 2
    assert "slug" in json.loads(capsys.readouterr().out)["error"]
