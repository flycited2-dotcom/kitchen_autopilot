from datetime import date

import pytest

import kitchen_common as kc
from tests.kitchen_fixtures import BRIEF, make_root, week_plan, write_json


def test_numbers_ignore_list_markers_keycaps_hashtags_and_urls():
    text = "1. Рис 150 г\n2️⃣ Тунец 1,5 кг #рецепт30 https://x.ru/7"
    assert kc.numbers(text) == {"150", "1.5"}


def test_numbers_grouped_thousands_and_trailing_zeros():
    assert kc.numbers("1 000 г и 2,50 л") == {"1000", "2.5"}


def test_canon_number():
    assert kc.canon_number(150.0) == "150"
    assert kc.canon_number(0.5) == "0.5"
    assert kc.canon_number("1,50") == "1.5"


def test_stop_word_matches_from_word_start_only():
    assert kc.stop_words_in("Этот салат ЛЕЧИТ всё", ["лечит"]) == ["лечит"]
    assert kc.stop_words_in("излечиться", ["лечит"]) == []


def test_price_regex_does_not_catch_chopping():
    assert kc.PRICE.search("Мелко порубить, рубленые котлеты, рублю зелень") is None
    assert kc.PRICE.search("Всего 300 руб.") is not None
    assert kc.PRICE.search("от 199 ₽") is not None
    assert kc.PRICE.search("50 рублей") is not None


def test_forbidden_words_whole_words_only():
    assert kc.forbidden_words("Textured table, no Logo here", ["text", "logo"]) == ["logo"]


def test_history_and_repeat(tmp_path):
    root = make_root(tmp_path)
    write_json(root / "plans" / "2026-11-02.json", week_plan())
    write_json(root / "runs" / "2026-10-20" / "01-boul" / "brief.json", dict(BRIEF, slug="boul", date="2026-10-20"))
    history = kc.dish_history(root)
    assert ("zavtrak-0", "2026-11-02") in history
    assert ("boul", "2026-10-20") in history
    assert kc.recent_repeat("boul", date(2026, 11, 2), history, 30) == "2026-10-20"
    assert kc.recent_repeat("boul", date(2026, 12, 1), history, 30) is None
    # само блюдо в свою же дату — не повтор
    assert kc.recent_repeat("zavtrak-0", date(2026, 11, 2), history, 30) is None


def test_history_skips_given_file(tmp_path):
    root = make_root(tmp_path)
    plan = write_json(root / "plans" / "2026-11-02.json", week_plan())
    assert kc.dish_history(root, skip=plan) == set()


def test_read_json_errors(tmp_path):
    with pytest.raises(kc.CheckError, match="нет файла"):
        kc.read_json(tmp_path / "nope.json", "рецепт")
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(kc.CheckError, match="не JSON"):
        kc.read_json(bad, "рецепт")


def test_load_rules_reads_all_files():
    rules = kc.load_rules()
    assert set(rules) == set(kc.RULE_FILES)
    assert rules["shots"]["target_shots"] == 20
