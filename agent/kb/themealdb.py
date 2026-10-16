"""TheMealDB (themealdb.com): international meals with measured ingredients, many with a YouTube video.

The free test key "1" is for development and education only; a supporter key is required before an
app-store release. Data is fetched by first letter (one request each) and cached as returned.
"""

import json
import re
import string
from collections.abc import Iterator
from pathlib import Path

from kb.net import get_json
from kb.record import KBRecipe

NAME = "themealdb"
API = "https://www.themealdb.com/api/json/v1/1"
LICENSE = "TheMealDB free API: development and education only; supporter key required before an app-store release"
KEYS = string.ascii_lowercase
FREE_LIST_CAP = 100  # the free key caps some listings at 100; exactly 100 results may mean a cut-off list

STEP_LABEL = re.compile(r"^(step\s*)?\d+\s*[.):-]?$", re.I)
STEP_PREFIX = re.compile(r"^(step\s*\d+\s*[.):-]?|\d+[.)](?!\d)|[-•*▢])\s*", re.I)


def fetch(raw_dir: Path, refresh: bool = False) -> str:
    total, capped = 0, []
    for key in KEYS:
        target = raw_dir / f"first_letter_{key}.json"
        if target.exists() and not refresh:
            data = json.loads(target.read_text("utf-8"))
        else:
            data = get_json(f"{API}/search.php", {"f": key})
            target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        count = len(data.get("meals") or [])
        total += count
        if count == FREE_LIST_CAP:
            capped.append(key)
    note = f"; letters {', '.join(capped)} returned exactly {FREE_LIST_CAP}, possibly a cut-off list" if capped else ""
    return f"{total} meals{note}"


def items(raw_dir: Path) -> Iterator[dict]:
    seen = set()
    for path in sorted(raw_dir.glob("first_letter_*.json")):
        for meal in json.loads(path.read_text("utf-8")).get("meals") or []:
            if meal["idMeal"] not in seen:
                seen.add(meal["idMeal"])
                yield meal


def to_recipe(meal: dict) -> KBRecipe:
    def field(key: str) -> str:
        return (meal.get(key) or "").strip()

    ingredients = [f"{field(f'strMeasure{i}')} {field(f'strIngredient{i}')}".strip()
                   for i in range(1, 21) if field(f"strIngredient{i}")]
    title = field("strMeal")
    return KBRecipe(
        id=f"{NAME}:{meal['idMeal']}", source=NAME, title=title, language="en", title_en=title,
        url=f"https://www.themealdb.com/meal/{meal['idMeal']}", license=LICENSE,
        ingredients=ingredients, steps=split_instructions(field("strInstructions")),
        cuisine=None if field("strArea") in ("", "Unknown") else field("strArea"),
        category=field("strCategory") or None,
        notes=[f"Original recipe: {field('strSource')}"] if field("strSource") else [],
        video_url=field("strYoutube") or None,
    )


def split_instructions(text: str) -> list[str]:
    """One step per line; drops "STEP 1" labels and "1." prefixes; a single paragraph splits into sentences."""
    steps = []
    for line in re.split(r"[\r\n]+", text):
        line = line.strip()
        if not line or STEP_LABEL.match(line):
            continue
        line = STEP_PREFIX.sub("", line).strip()
        if line:
            steps.append(line)
    if len(steps) == 1:
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", steps[0])
        if len(sentences) > 1:
            steps = sentences
    return steps
