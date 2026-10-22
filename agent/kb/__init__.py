"""Recipe knowledge base (M2): recipes.jsonl → Azure AI Search.

  python -m kb.methods   label each recipe's cooking methods with the model (saved in data/methods.jsonl)
  python -m kb.build     parse data/raw/ into data/recipes.jsonl, merging saved names and methods (no network)
  python -m kb.upload    send data/recipes.jsonl to the search index (agent venv + .env)
  python -m kb.query     try dish names against the index
kb/sources/ downloads and parses the recipe sources; only needed to rebuild from scratch.
data/ is git-ignored.
"""

from pathlib import Path

KB_ROOT = Path(__file__).resolve().parent
DATA = KB_ROOT / "data"
RAW = DATA / "raw"
RECIPES = DATA / "recipes.jsonl"
NAMES = DATA / "names.jsonl"
METHODS = DATA / "methods.jsonl"
