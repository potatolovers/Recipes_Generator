"""Parses every downloaded source into data/recipes.jsonl and prints a summary. No network.

Run from agent/: python -m kb.build   (kb.fetch runs this after downloading)
"""

import json
import re
import sys
from collections import Counter

from kb import DATA, KB_ROOT, RAW, RECIPES, howtocook, themealdb, wikibooks
from kb.record import KBRecipe

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
    DATA.mkdir(parents=True, exist_ok=True)
    with RECIPES.open("w", encoding="utf-8", newline="\n") as out:
        for recipe in kept.values():
            out.write(recipe.to_json() + "\n")
    print(f"total {len(kept)} recipes -> {RECIPES.relative_to(KB_ROOT.parent).as_posix()}")
    report_coverage(list(kept.values()))
    return list(kept.values())


def report_coverage(recipes: list[KBRecipe]) -> None:
    """Which eval dishes have a recipe with the same title or alias, or only a similar one."""
    if not EVAL_CASES.exists():
        return
    cases = json.loads(EVAL_CASES.read_text("utf-8"))
    dishes = list(dict.fromkeys(case["dish"] for case in cases if case.get("expect", "succeeded") != "rejected"))
    names = [(recipe, {recipe.title.lower(), *(alias.lower() for alias in recipe.aliases)}) for recipe in recipes]
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
    print(f"\neval dishes: {len(dishes)} | same title {len(exact)} | similar title only {len(similar)} | none {len(missing)}")
    for dish, close in similar:
        print(f"  similar  {dish}: {', '.join(close[:3])}{' ...' if len(close) > 3 else ''}")
    for dish, _ in missing:
        print(f"  none     {dish}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    build()
