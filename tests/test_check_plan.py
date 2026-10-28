import json

import check_plan
from kitchen_common import load_rules
from tests.kitchen_fixtures import BRIEF, make_root, week_plan, write_json

RULES = load_rules()


def test_valid_plan_passes():
    assert check_plan.check_plan(week_plan(), RULES, set()) == []


def test_wrong_dates_and_slot_count():
    plan = week_plan()
    plan["days"][2]["date"] = "2026-11-09"
    plan["days"][3]["slots"].pop()
    reasons = check_plan.check_plan(plan, RULES, set())
    assert "день 3: дата 2026-11-09, ожидалась 2026-11-04" in reasons
    assert "2026-11-05: блюд 1, нужно 2" in reasons


def test_unknown_rubric_meal_and_bad_slug():
    plan = week_plan()
    plan["days"][0]["slots"][1].update(rubric="nope", meal="полдник", slug="Боул")
    reasons = check_plan.check_plan(plan, RULES, set())
    assert "2026-11-02 слот 2: неизвестная рубрика nope" in reasons
    assert "2026-11-02 слот 2: неизвестный приём пищи полдник" in reasons
    assert any("slug «Боул»" in r for r in reasons)


def test_breakfast_rubric_only_for_breakfast():
    plan = week_plan()
    plan["days"][0]["slots"][1]["rubric"] = "zavtrak_10"
    reasons = check_plan.check_plan(plan, RULES, set())
    assert "2026-11-02 слот 2: рубрика zavtrak_10 — только для: завтрак" in reasons


def test_duplicates_inside_plan_and_same_meal_twice():
    plan = week_plan()
    plan["days"][1]["slots"][1]["slug"] = "uzhin-0"
    plan["days"][2]["slots"][1]["meal"] = "завтрак"
    reasons = check_plan.check_plan(plan, RULES, set())
    assert "блюдо uzhin-0 в плане 2 раза" in reasons
    assert "2026-11-04: «завтрак» два раза — приёмы пищи в день разные" in reasons


def test_repeat_from_history():
    reasons = check_plan.check_plan(week_plan(), RULES, {("uzhin-3", "2026-10-20")})
    assert any("uzhin-3" in r and "2026-10-20" in r for r in reasons)


def test_rubric_share():
    plan = week_plan()
    for day in plan["days"]:
        day["slots"][1]["rubric"] = "recept_30s"
    plan["days"][0]["slots"][0].update(rubric="recept_30s")
    reasons = check_plan.check_plan(plan, RULES, set())
    assert any(r.startswith("рубрика recept_30s: 8 из 14") for r in reasons)


def test_stop_word_in_dish():
    plan = week_plan()
    plan["days"][0]["slots"][1]["dish"] = "Детокс-смузи"
    assert "2026-11-02 слот 2: стоп-слово: детокс" in check_plan.check_plan(plan, RULES, set())


def test_cli_ok_and_history_from_runs(tmp_path, capsys):
    root = make_root(tmp_path)
    path = write_json(root / "plans" / "2026-11-02.json", week_plan())
    assert check_plan.main([str(path), "--root", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    write_json(root / "runs" / "2026-10-25" / "02-uzhin-1" / "brief.json",
               dict(BRIEF, slug="uzhin-1", date="2026-10-25"))
    assert check_plan.main([str(path), "--root", str(root)]) == 1
    assert "uzhin-1" in capsys.readouterr().out


def test_cli_bad_input(tmp_path, capsys):
    path = write_json(tmp_path / "plan.json", {"days": "x"})
    assert check_plan.main([str(path), "--root", str(tmp_path)]) == 2
    assert json.loads(capsys.readouterr().out)["ok"] is False
