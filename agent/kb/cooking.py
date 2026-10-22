"""The fixed list of cooking methods used by the recipe knowledge base (kb.methods, kb.build, kb.upload).

Each method has a code (stored in the index and used in filters such as cooking_method eq 'red_braise'),
English and Chinese names, a family for broad filters (cooking_family eq 'braise_stew'), and a one-line
definition that the labeling model reads. Change codes only together with re-labeling (kb.methods --redo).
"""

from typing import NamedTuple


class Method(NamedTuple):
    code: str
    en: str
    zh: str
    family: str
    definition: str


FAMILIES = {
    "fry": "cooked in oil on the stove",
    "braise_stew": "long, moist cooking in a little or a lot of liquid",
    "boil_poach": "cooked in water, broth or fat, quickly or gently",
    "steam": "cooked by steam",
    "dry_heat": "oven, grill, fire or hot air",
    "cure_preserve": "smoked, salted, pickled, fermented or steeped",
    "no_cook": "served raw, dressed, blended, chilled or frozen",
    "sugar": "candied, glazed or caramelized",
    "other": "anything else",
}

METHODS = (
    # fry
    Method("stir_fry", "Stir-fry", "炒", "fry", "small pieces tossed in a hot wok or pan with a little oil"),
    Method("quick_fry", "Explode-fry", "爆", "fry", "seconds-long toss over very high heat (爆炒, 葱爆, 酱爆)"),
    Method("dry_fry", "Dry-fry", "干煸", "fry", "fried slowly until the moisture is gone and edges crisp (干煸豆角)"),
    Method("slip_fry", "Fry then sauce", "熘", "fry", "fried or oil-blanched, then tossed in a thickened sauce (醋熘, 滑熘, 焦熘)"),
    Method("fry_splash", "Fry and splash", "烹", "fry", "fried, then a thin sauce splashed in and cooked off (炸烹)"),
    Method("aromatic_flash_fry", "Chili-oil flash-fry", "炝", "fry", "flash-cooked with chili or Sichuan-pepper oil (炝炒)"),
    Method("hot_oil_pour", "Hot-oil pour", "油泼", "fry", "smoking oil poured over seasonings on the food (油泼面)"),
    Method("dry_pot", "Dry pot", "干锅", "fry", "fried, then served sizzling in a small pot over a flame"),
    Method("saute", "Sauté", "嫩煎", "fry", "Western quick cooking in a little fat in a skillet"),
    Method("sear", "Sear", "煎封", "fry", "browned at high heat, usually before another method"),
    Method("pan_fry", "Pan-fry", "煎", "fry", "flat pieces in a little oil until golden on both sides"),
    Method("shallow_fry", "Shallow-fry", "半煎炸", "fry", "oil about halfway up the food (schnitzel, fritters)"),
    Method("potsticker_fry", "Fry-steam", "贴 / 锅贴", "fry", "bottom pan-fried, then steamed with water under a lid"),
    Method("deep_fry", "Deep-fry", "炸", "fry", "submerged in hot oil, plain, battered or crumbed (干炸, 软炸, 酥炸)"),
    Method("griddle", "Griddle", "铁板", "fry", "on a hot flat plate with little oil (pancakes, teppanyaki, 铁板烧)"),
    # braise / stew
    Method("braise", "Braise", "焖", "braise_stew", "browned, then cooked covered in a little liquid"),
    Method("red_braise", "Red-braise", "红烧", "braise_stew", "braised with soy sauce and sugar to a glossy reduced sauce"),
    Method("dry_braise", "Dry-braise", "干烧", "braise_stew", "braised until the sauce is absorbed and clings (干烧鱼)"),
    Method("soy_braise", "Soy-paste braise", "酱", "braise_stew", "long braise in soy sauce or bean paste, often served cold (酱牛肉)"),
    Method("master_stock", "Master-stock braise", "卤", "braise_stew", "simmered in a spiced master stock (卤味)"),
    Method("thick_braise", "Thickened braise", "烩", "braise_stew", "mixed ingredients in a starch-thickened sauce (烩菜)"),
    Method("plate_braise", "Braise and plate whole", "扒", "braise_stew", "large neat pieces braised, sauce poured over (扒白菜)"),
    Method("stew", "Stew", "炖", "braise_stew", "long gentle cooking submerged in liquid"),
    Method("slow_simmer", "Slow-simmer", "煨", "braise_stew", "very low heat for hours until tender (煨汤)"),
    Method("pot_simmer", "Clay-pot simmer", "煲", "braise_stew", "slow-cooked in a clay pot, often a soup (煲汤, 煲仔饭)"),
    Method("slow_cook", "Slow-cooker", "慢炖锅", "braise_stew", "hours in an electric slow cooker"),
    Method("pressure_cook", "Pressure-cook", "高压锅", "braise_stew", "in a pressure cooker or Instant Pot"),
    # boil / poach
    Method("boil", "Boil", "煮", "boil_poach", "in boiling water or broth (noodles, dumplings, eggs)"),
    Method("simmer", "Simmer", "小火煮", "boil_poach", "kept just below a boil (sauces, soups, curries)"),
    Method("poach", "Poach", "浸", "boil_poach", "gently cooked in hot liquid below boiling (白切鸡, poached eggs)"),
    Method("quick_boil", "Quick-boil", "汆", "boil_poach", "thin slices or balls briefly in boiling broth (汆丸子)"),
    Method("blanch", "Blanch", "焯", "boil_poach", "dipped briefly in boiling water, often then cooled"),
    Method("scald_dress", "Scald and dress", "白灼", "boil_poach", "briefly boiled, dressed with soy and hot oil (白灼虾)"),
    Method("spicy_poach", "Sichuan spicy poach", "水煮", "boil_poach", "poached in chili broth, topped with hot oil (水煮鱼)"),
    Method("hot_pot", "Hot pot", "涮", "boil_poach", "dipped into simmering broth at the table (涮羊肉, 火锅)"),
    Method("sous_vide", "Sous vide", "低温慢煮", "boil_poach", "sealed and held in a precisely heated water bath"),
    Method("confit", "Confit", "油封", "boil_poach", "slowly cooked submerged in fat"),
    # steam
    Method("steam", "Steam", "蒸", "steam", "cooked by steam"),
    Method("clear_steam", "Plain steam", "清蒸", "steam", "steamed plainly, finished with soy and hot oil (清蒸鱼)"),
    Method("powder_steam", "Rice-powder steam", "粉蒸", "steam", "coated in seasoned rice powder and steamed (粉蒸肉)"),
    Method("double_boil", "Double-boil", "隔水炖", "steam", "in a covered bowl set in boiling water for hours (炖盅)"),
    # dry heat
    Method("roast", "Roast", "烤", "dry_heat", "in an oven or over a fire, mainly meat and vegetables"),
    Method("bake", "Bake", "烘焙", "dry_heat", "in an oven, mainly doughs, batters and casseroles"),
    Method("gratin", "Gratin", "焗", "dry_heat", "baked under a cheese or crumb crust (芝士焗)"),
    Method("salt_bake", "Salt-bake", "盐焗", "dry_heat", "baked buried in hot salt (盐焗鸡)"),
    Method("grill", "Grill", "烧烤", "dry_heat", "over direct heat from below (charcoal, gas grill, 烤串)"),
    Method("broil", "Broil", "上火烤", "dry_heat", "under direct top heat in an oven"),
    Method("barbecue", "Barbecue", "低温烟熏烤", "dry_heat", "low and slow over indirect heat with smoke"),
    Method("air_fry", "Air-fry", "空气炸锅", "dry_heat", "hot circulating air in an air fryer"),
    Method("toast", "Toast", "烘烤", "dry_heat", "browned in a toaster or dry pan (bread, nuts, spices)"),
    # cure / preserve
    Method("smoke", "Smoke", "熏", "cure_preserve", "flavored, cooked or preserved by smoke (熏鱼)"),
    Method("cure", "Salt-cure", "腌腊", "cure_preserve", "salted and/or air-dried (腊肉, gravlax, bacon)"),
    Method("pickle", "Pickle", "泡 / 渍", "cure_preserve", "preserved in brine or vinegar (泡菜, pickles)"),
    Method("ferment", "Ferment", "发酵", "cure_preserve", "transformed by microbes over days (kimchi, sauerkraut, 酸菜)"),
    Method("wine_marinate", "Wine-marinate", "醉", "cure_preserve", "steeped in rice wine (醉鸡, 醉虾)"),
    Method("lees_marinate", "Lees-marinate", "糟", "cure_preserve", "steeped in fermented rice-wine lees (糟卤)"),
    Method("marinate", "Marinate", "腌制", "cure_preserve", "soaked in seasoning; main only if nothing else cooks the food"),
    Method("dehydrate", "Dehydrate", "风干 / 烘干", "cure_preserve", "dried by air or low heat (jerky, dried fruit)"),
    # no cook
    Method("cold_dress", "Cold-dress", "凉拌", "no_cook", "mixed with a seasoned dressing and served cold (拍黄瓜)"),
    Method("salad", "Salad", "沙拉", "no_cook", "Western salad tossed with dressing"),
    Method("raw", "Raw", "生食", "no_cook", "served raw: sashimi, tartare, carpaccio"),
    Method("acid_cure", "Acid-cure", "酸渍", "no_cook", "'cooked' by citrus or vinegar (ceviche)"),
    Method("blend", "Blend", "打碎 / 搅拌", "no_cook", "blended or puréed (smoothies, hummus, pesto)"),
    Method("whip", "Whip", "打发", "no_cook", "whipped into a foam (whipped cream, mousse)"),
    Method("chill_set", "Chill to set", "冷藏凝固", "no_cook", "set in the fridge (jelly, panna cotta, 凉粉)"),
    Method("freeze", "Freeze", "冷冻", "no_cook", "frozen (ice cream, sorbet, popsicles)"),
    Method("mix", "Mix or brew", "调制 / 冲泡", "no_cook", "drinks and sauces only mixed or steeped (tea, cocktails, dressings)"),
    # sugar
    Method("caramelize", "Caramelize", "熬焦糖", "sugar", "sugar cooked to caramel, or food browned in it"),
    Method("spun_sugar", "Spun-sugar coat", "拔丝", "sugar", "fried pieces coated in hot sugar that pulls into threads"),
    Method("sugar_frost", "Sugar-frost coat", "挂霜", "sugar", "coated in sugar syrup that dries to a white frost"),
    Method("honey_glaze", "Honey glaze", "蜜汁", "sugar", "glazed in honey or sugar syrup (蜜汁叉烧)"),
    Method("candy", "Candy-making", "熬糖", "sugar", "sugar syrup cooked to a set stage (fudge, toffee, 糖葫芦)"),
    # other
    Method("flambe", "Flambé", "火焰烹调", "other", "alcohol set alight in the pan"),
    Method("microwave", "Microwave", "微波", "other", "cooked in a microwave oven"),
    Method("other", "Other", "其他", "other", "nothing above fits"),
)

METHOD_CODES = tuple(method.code for method in METHODS)
BY_CODE = {method.code: method for method in METHODS}


def family_of(code: str) -> str:
    return BY_CODE[code].family


def prompt_table() -> str:
    """The list as the labeling model reads it, one line per method, grouped by family."""
    lines = []
    for family, meaning in FAMILIES.items():
        lines.append(f"[{family}: {meaning}]")
        lines += [f"{m.code} = {m.zh} / {m.en}: {m.definition}" for m in METHODS if m.family == family]
    return "\n".join(lines)
