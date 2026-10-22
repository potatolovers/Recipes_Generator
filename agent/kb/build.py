"""Parses every downloaded source into data/recipes.jsonl and prints a summary. No network.

Run from agent/: python -m kb.build   (kb.sources.fetch runs it after downloading)

Saved model answers are merged in, each used only while the recipe still has the title it was given for:
- data/names.jsonl: English/Chinese names and alternate names, from an earlier naming step (since removed),
  {"id", "title", "en", "zh", "aka"} per line.
- data/methods.jsonl: cooking methods from kb.methods, {"id", "title", "main", "all"} per line, codes from
  kb/cooking.py.
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

from kb.cooking import BY_CODE, family_of
from kb import DATA, KB_ROOT, METHODS, NAMES, RAW, RECIPES
from kb.sources import howtocook, themealdb, wikibooks
from kb.sources.record import KBRecipe

SOURCES = {module.NAME: module for module in (howtocook, themealdb, wikibooks)}
EVAL_CASES = KB_ROOT.parent / "evals" / "dishes.json"


def build() -> list[KBRecipe]:
    kept: dict[str, KBRecipe] = {}
    print(f"\n{'source':<10} {'parsed':>7} {'kept':>6} {'skipped':>8}  main skip reason")
    for name, module in SOURCES.items():
        raw = RAW / name
        if not raw.exists() or not any(raw.iterdir()):
            print(f"{name:<10} not downloaded yet")
            continue
        parsed, reasons = 0, Counter()
        for item in module.items(raw):
            parsed += 1
            try:
                recipe = module.to_recipe(item)
            except Exception as exc:  # one malformed page must not stop the build
                reasons[f"parse error ({type(exc).__name__})"] += 1
                continue
            problems = recipe.problems()
            if problems:
                reasons[problems[0]] += 1
            else:
                kept[recipe.id] = recipe
        skipped = sum(reasons.values())
        reason = reasons.most_common(1)[0][0] if reasons else ""
        print(f"{name:<10} {parsed:>7} {parsed - skipped:>6} {skipped:>8}  {reason}")
    names = load_names()
    generic = generic_aliases(names)
    named = sum(apply_names(recipe, names.get(recipe.id), generic) for recipe in kept.values())
    methods = load_names(METHODS)
    labeled = sum(apply_methods(recipe, methods.get(recipe.id)) for recipe in kept.values())
    DATA.mkdir(parents=True, exist_ok=True)
    with RECIPES.open("w", encoding="utf-8", newline="\n") as out:
        for recipe in kept.values():
            out.write(recipe.to_json() + "\n")
    print(f"total {len(kept)} recipes -> {RECIPES.relative_to(KB_ROOT.parent).as_posix()}"
          f" | {named} with saved English/Chinese names | {labeled} with cooking methods")
    report_coverage(list(kept.values()))
    return list(kept.values())


def load_names(path: Path = NAMES) -> dict[str, dict]:
    """Recipe id → latest saved answer in a JSON-lines file (names.jsonl or methods.jsonl)."""
    if not path.exists():
        return {}
    names = {}
    for line in path.read_text("utf-8").splitlines():
        if line.strip():
            entry = json.loads(line)
            names[entry["id"]] = entry
    return names


def generic_aliases(names: dict[str, dict], min_recipes: int = 3) -> set[str]:
    """Alternate names the model gave to several different recipes ("beef stew", 巧克力蛋糕): categories,
    not names, so a search for them would rank unrelated recipes as exact matches."""
    counts: dict[str, int] = {}
    for entry in names.values():
        for alias in {name.casefold() for name in entry["aka"]}:
            counts[alias] = counts.get(alias, 0) + 1
    return {alias for alias, count in counts.items() if count >= min_recipes}


def apply_names(recipe: KBRecipe, entry: dict | None, generic: set[str] = frozenset()) -> bool:
    """Fills title_en/title_zh where the source has none and sets aliases, leaving out `generic` ones;
    True if names were applied."""
    if not entry or entry["title"] != recipe.title:
        return False
    recipe.title_en = recipe.title_en or entry["en"]
    recipe.title_zh = recipe.title_zh or entry["zh"]
    taken = {recipe.title.casefold(), recipe.title_en.casefold(), recipe.title_zh.casefold()}
    aliases = []
    for name in [entry["en"], entry["zh"], *(alias for alias in entry["aka"] if alias.casefold() not in generic)]:
        if name.casefold() not in taken:
            taken.add(name.casefold())
            aliases.append(name)
    recipe.aliases = aliases
    return True


def apply_methods(recipe: KBRecipe, entry: dict | None) -> bool:
    """Sets the cooking-method fields from a saved answer; codes not in kb/cooking.py are dropped."""
    if not entry or entry["title"] != recipe.title or entry.get("main") not in BY_CODE:
        return False
    recipe.cooking_method = entry["main"]
    recipe.cooking_methods = [code for code in dict.fromkeys(entry.get("all", [])) if code in BY_CODE] or [entry["main"]]
    recipe.cooking_family = family_of(entry["main"])
    return True


def report_coverage(recipes: list[KBRecipe]) -> None:
    """Which eval dishes have a recipe with the same name (title, English/Chinese name or alias), or only a similar one."""
    if not EVAL_CASES.exists():
        return
    cases = json.loads(EVAL_CASES.read_text("utf-8"))
    dishes = list(dict.fromkeys(case["dish"] for case in cases if case.get("expect", "succeeded") != "rejected"))
    names = [(recipe, {name.lower() for name in (recipe.title, recipe.title_en, recipe.title_zh, *recipe.aliases) if name})
             for recipe in recipes]
    exact, similar, missing = [], [], []
    for dish in dishes:
        key = dish.lower()
        if any(key in recipe_names for _, recipe_names in names):
            exact.append(dish)
            continue
        if dish.isascii():
            words = set(re.findall(r"\w+", key))
            close = [recipe.title for recipe, _ in names if words <= set(re.findall(r"\w+", recipe.title.lower()))]
        else:
            close = [recipe.title for recipe, _ in names if key in recipe.title]
        (similar if close else missing).append((dish, close))
    print(f"\neval dishes: {len(dishes)} | same name {len(exact)} | similar title only {len(similar)} | none {len(missing)}")
    for dish, close in similar:
        print(f"  similar  {dish}: {', '.join(close[:3])}{' ...' if len(close) > 3 else ''}")
    for dish, _ in missing:
        print(f"  none     {dish}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    build()
