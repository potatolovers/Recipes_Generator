"""Merging saved English/Chinese names (data/names.jsonl) into recipes in kb.build. No network."""

from kb.build import apply_names, generic_aliases, load_names
from kb.sources.record import KBRecipe


def recipe(title: str, **names) -> KBRecipe:
    return KBRecipe(id="howtocook:x", source="howtocook", title=title, language="zh", url="", license="",
                    ingredients=["a"], steps=["s"], **names)


def test_apply_names_keeps_source_titles_and_skips_renamed_recipes():
    dish = recipe("西红柿炒鸡蛋", title_zh="西红柿炒鸡蛋")
    entry = {"id": "howtocook:x", "title": "西红柿炒鸡蛋", "en": "Tomato and egg stir-fry", "zh": "西红柿炒鸡蛋",
             "aka": ["番茄炒蛋", "Xihongshi chao jidan"]}
    assert apply_names(dish, entry)
    assert (dish.title_en, dish.title_zh) == ("Tomato and egg stir-fry", "西红柿炒鸡蛋")
    assert dish.aliases == ["番茄炒蛋", "Xihongshi chao jidan"]
    assert not apply_names(recipe("renamed upstream"), entry)  # answer was for a different title


def test_generic_aliases_are_left_out():
    cakes = {f"c{i}": {"id": f"c{i}", "title": f"Cake {i}", "en": f"Cake {i}", "zh": "蛋糕", "aka": ["巧克力蛋糕", f"cake {i}x"]}
             for i in range(3)}
    generic = generic_aliases(cakes)
    assert generic == {"巧克力蛋糕"}
    cake = recipe("Cake 0", title_en="Cake 0")
    apply_names(cake, cakes["c0"], generic)
    assert (cake.title_zh, cake.aliases) == ("蛋糕", ["cake 0x"])


def test_load_names_latest_wins(tmp_path):
    path = tmp_path / "names.jsonl"
    path.write_text('{"id": "a", "title": "T", "en": "Old", "zh": "旧", "aka": []}\n'
                    '{"id": "a", "title": "T", "en": "New", "zh": "新", "aka": []}\n', encoding="utf-8")
    assert load_names(path)["a"]["en"] == "New"
