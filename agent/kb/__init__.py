"""Recipe knowledge base (M2). Standard library only, so the scripts run without the agent's packages.

`python -m kb.fetch` downloads the sources into data/raw/ and then runs kb.build, which parses them
into data/recipes.jsonl. data/ is git-ignored; rebuild it with the same command.
"""

from pathlib import Path

KB_ROOT = Path(__file__).resolve().parent
DATA = KB_ROOT / "data"
RAW = DATA / "raw"
RECIPES = DATA / "recipes.jsonl"
