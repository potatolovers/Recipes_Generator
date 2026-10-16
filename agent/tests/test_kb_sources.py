"""Knowledge-base source parsers on small fixtures shaped like the real data. No network."""

from kb import howtocook, themealdb, wikibooks

TOMATO_EGG = """# 西红柿炒鸡蛋的做法

一道酸甜开胃的家常菜肴。

预估烹饪难度：★★

## 必备原料和工具

* 西红柿
* 鸡蛋

## 计算

每次制作前需要确定计划做几份。一份正好够 1 个人食用

* 西红柿 = 1 个（约 180g） * 份数
* 鸡蛋 = 1.5 个 * 份数，向上取整

## 操作

1. 西红柿洗净
2. 可选：去掉西红柿的外表皮

  - 开水烫表皮，然后将西红柿放入冷水，剥去外皮

3. 将鸡蛋打入碗中，加入 `1g * 份数` 的盐，搅匀，即为 `鸡蛋液`

## 附加内容

* 加入盐 改为 “加入两滴生抽”

如果您遵循本指南的制作流程而发现有问题或可以改进的流程，请提出 Issue 或 Pull request 。
"""

CAESAR = """{{Recipe summary
| category = Salad recipes
| servings = 4
| time = 20 minutes
| image = [[File:Caesar salad (1).jpg|300px|A [[Cookbook:Salad|salad]]]]
}}
{{recipe}} | [[Cookbook:Salad|Salads]]

'''Caesar salad''' is a [[Cookbook:Salad|salad]] of [[Cookbook:Romaine Lettuce|romaine lettuce]].<ref>A cookbook.</ref>

== Ingredients ==
=== Dressing ===
* 2 [[Cookbook:Egg|egg]] yolks <!-- or pasteurized -->
* {{convert|60|ml|tbsp}} [[Cookbook:Lemon Juice|lemon juice]]
* {{frac|1|2}} [[Cookbook:Cup|cup]] (120&nbsp;ml) [[Cookbook:Olive Oil|olive oil]]
=== Salad ===
{| class="wikitable"
! Ingredient !! Amount
|-
| [[Cookbook:Parmesan Cheese|Parmesan]] || {{convert|1|-|2|oz|g}}
|-
| colspan="2" style="background: #f5f5f5;" | Croutons
|}

== Procedure ==
# Whisk the yolks and [[Cookbook:Lemon Juice|lemon juice]].
#* Use a [[w:Whisk|balloon whisk]].
# Toss the lettuce with the dressing.

== Notes, tips, and variations ==
* Add [[Cookbook:Anchovy|anchovies]] for a traditional version.

[[Category:Salad recipes]]
"""


def test_howtocook_markdown():
    recipe = howtocook.parse_markdown(TOMATO_EGG, "dishes/vegetable_dish/西红柿炒鸡蛋.md", "abc123")
    assert (recipe.id, recipe.title, recipe.category) == (
        "howtocook:vegetable_dish/西红柿炒鸡蛋", "西红柿炒鸡蛋", "vegetable_dish")
    assert recipe.servings == "每次制作前需要确定计划做几份。一份正好够 1 个人食用"
    assert recipe.ingredients == ["西红柿 = 1 个（约 180g） * 份数", "鸡蛋 = 1.5 个 * 份数，向上取整"]
    assert recipe.steps[1] == "可选：去掉西红柿的外表皮\n  - 开水烫表皮，然后将西红柿放入冷水，剥去外皮"
    assert recipe.steps[2] == "将鸡蛋打入碗中，加入 1g * 份数 的盐，搅匀，即为 鸡蛋液"
    assert recipe.notes == ["加入盐 改为 “加入两滴生抽”"]  # contribution boilerplate dropped
    assert recipe.problems() == []


def test_howtocook_ingredient_groups_and_fallback():
    groups = "- 必须配料\n  - 熟花生 = 150g\n- 可选配料\n  - 莴笋 = 约 250g\n"
    assert howtocook.leaf_bullets(groups) == ["必须配料：熟花生 = 150g", "可选配料：莴笋 = 约 250g"]
    shopping = "### 主食材\n\n- 鸡蛋\n\n### 必备工具\n\n- 温度计\n\n### 副食材\n\n- 香葱\n"
    assert howtocook.ingredients("+ 鸡蛋 1 个", shopping) == ["鸡蛋 1 个", "副食材：香葱"]


def test_themealdb_meal():
    meal = {"idMeal": "52772", "strMeal": "Teriyaki Chicken Casserole", "strCategory": "Chicken",
            "strArea": "Japanese", "strYoutube": "https://www.youtube.com/watch?v=4aZr5hZXP_s",
            "strInstructions": "STEP 1\r\nPreheat oven to 350° F.\r\n\r\nSTEP 2\r\n1.5 cups of sauce are reserved.",
            "strIngredient1": "soy sauce", "strMeasure1": "3/4 cup", "strIngredient2": "water",
            "strMeasure2": "1/2 cup", "strIngredient3": "", "strMeasure3": " ", "strIngredient4": None}
    recipe = themealdb.to_recipe(meal)
    assert recipe.ingredients == ["3/4 cup soy sauce", "1/2 cup water"]
    assert recipe.steps == ["Preheat oven to 350° F.", "1.5 cups of sauce are reserved."]
    assert (recipe.cuisine, recipe.video_url) == ("Japanese", "https://www.youtube.com/watch?v=4aZr5hZXP_s")
    assert themealdb.split_instructions("Heat the oil. Add the onions. Serve.") == [
        "Heat the oil.", "Add the onions.", "Serve."]


def test_wikibooks_wikitext():
    recipe = wikibooks.from_wikitext("Cookbook:Caesar Salad", CAESAR)
    assert recipe.ingredients == ["Dressing: 2 egg yolks", "Dressing: 60 ml lemon juice",
                                  "Dressing: 1/2 cup (120 ml) olive oil", "Salad: Parmesan 1–2 oz",
                                  "Salad: Croutons"]
    assert recipe.steps == ["Whisk the yolks and lemon juice.\n  - Use a balloon whisk.",
                            "Toss the lettuce with the dressing."]
    assert recipe.description == "Caesar salad is a salad of romaine lettuce."
    assert (recipe.servings, recipe.category) == ("4", "Salad")
    assert recipe.notes == ["Time: 20 minutes", "Add anchovies for a traditional version."]
    assert recipe.url == "https://en.wikibooks.org/wiki/Cookbook:Caesar_Salad"


def test_wikibooks_misnested_procedure_and_gallery():
    page = """== Ingredients ==
* 1 small eggplant
* Salt
<gallery>
File:Eggplant.jpg|Sliced eggplant
</gallery>
=== Procedure ===
# Slice the eggplant.
# Salt both sides.

== External links ==
* [http://example.com Site]
"""
    recipe = wikibooks.from_wikitext("Cookbook:Eggplant", page)
    assert recipe.ingredients == ["1 small eggplant", "Salt"]
    assert recipe.steps == ["Slice the eggplant.", "Salt both sides."]
    assert recipe.notes == []  # External links is not a notes section
