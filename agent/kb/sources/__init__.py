"""Recipe sources for the knowledge base: download (fetch) and parse each one into KBRecipe records.

Only needed to rebuild data/recipes.jsonl from scratch, e.g. after losing it or to pick up new recipes:
  python -m kb.sources.fetch      download into data/raw/ (resumes), then run kb.build
"""
