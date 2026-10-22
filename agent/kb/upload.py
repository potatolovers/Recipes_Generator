"""Uploads data/recipes.jsonl to the Azure AI Search index the agent searches (M2).

Run from agent/ with the agent's venv; needs AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_ADMIN_KEY and
AGENT_MODEL_EMBED in .env. The admin key stays on this laptop; the deployed agent gets a query key.
  python -m kb.upload --limit 50   only the first 50 recipes, as a quick test
  python -m kb.upload              create or update the index, then add or replace every recipe
  python -m kb.upload --recreate   delete the index first (after a schema change, or to drop old recipes)
Re-running is safe: recipes are replaced by id, so after kb.build changes recipes.jsonl run it again.
After a schema change use --recreate: replaced copies count toward the free tier's 50 MB until Azure
cleans them up.

Each recipe becomes one search document: its names are searchable by keyword (with a Chinese and an
English analyzer), and two 512-number vectors are searchable by meaning:
- name_vector: every name of the dish and its main cooking method, for dish-name queries;
- content_vector: all cooking methods, all ingredients and the steps, i.e. what the dish actually is.
The rest (ingredients, steps, notes, source link) is stored for the agent to read, not searched.
"""

import argparse
import base64
import json
import sys
import time

from kb.cooking import BY_CODE
from kb import RECIPES

BATCH = 50  # recipes per upload request
# Azure counts each embedding request against the deployment's tokens-per-minute limit by its size, so the
# 100 texts of a batch (~14K tokens, up to ~35K) go in calls of at most this many UTF-8 bytes (~5-9K tokens).
EMBED_CALL_BYTES = 20_000
RETRY_PAUSES = (10, 30, 60, 60, 60)  # seconds, after a failed embedding call; the token count resets each minute
FREE_TIER_MB = 50
EMBED_DIMENSIONS = 512  # same as app.llm.EMBED_DIMENSIONS (checked in tests)
STEPS_CHARS = 1200  # longer steps keep their start and end; ~88% of recipes fit whole
CONTENT_CHARS = 4000  # hard cap per content text, far below the embedding model's input limit


def field(name: str, type_: str = "Edm.String", searchable: bool = False, filterable: bool = False,
          analyzer: str | None = None, facetable: bool = False) -> dict:
    """Every attribute set explicitly: Azure turns most of them on by default, which costs storage."""
    spec = {"name": name, "type": type_, "searchable": searchable, "filterable": filterable,
            "sortable": False, "facetable": facetable, "retrievable": True}
    if analyzer:
        spec["analyzer"] = analyzer
    return spec


LIST = "Collection(Edm.String)"
INDEX = {
    "fields": [
        {**field("key", filterable=True), "key": True},  # URL-safe base64 of id: keys allow only A-Z a-z 0-9 - _ =
        field("id", filterable=True),
        field("source", filterable=True),
        field("language", filterable=True),
        field("title", searchable=True, analyzer="standard.lucene"),
        field("title_en", searchable=True, analyzer="en.microsoft"),
        field("title_zh", searchable=True, analyzer="zh-Hans.microsoft"),
        field("aliases", LIST, searchable=True, analyzer="standard.lucene"),
        field("cuisine", filterable=True),
        field("category", filterable=True),
        # Cooking-method codes from kb/cooking.py: filter (cooking_method eq 'stew') and count (facets).
        field("cooking_method", filterable=True, facetable=True),
        field("cooking_methods", LIST, filterable=True, facetable=True),
        field("cooking_family", filterable=True, facetable=True),
        field("servings"),
        field("description"),
        field("ingredients", LIST),
        field("steps", LIST),
        field("notes", LIST),
        field("url"),
        field("license"),
        field("video_url"),
        {"name": "name_vector", "type": "Collection(Edm.Single)", "searchable": True, "retrievable": False,
         "stored": False, "dimensions": EMBED_DIMENSIONS, "vectorSearchProfile": "names"},
        {"name": "content_vector", "type": "Collection(Edm.Single)", "searchable": True, "retrievable": False,
         "stored": False, "dimensions": EMBED_DIMENSIONS, "vectorSearchProfile": "names"},
    ],
    "vectorSearch": {
        "algorithms": [{"name": "hnsw", "kind": "hnsw",
                        "hnswParameters": {"m": 4, "efConstruction": 400, "efSearch": 500, "metric": "cosine"}}],
        "profiles": [{"name": "names", "algorithm": "hnsw"}],
    },
}
TEXT_FIELDS = ("id", "source", "language", "title", "title_en", "title_zh", "cuisine", "category", "servings",
               "description", "url", "license", "video_url", "cooking_method", "cooking_family")
LIST_FIELDS = ("aliases", "ingredients", "steps", "notes", "cooking_methods")


def doc_key(recipe_id: str) -> str:
    return base64.urlsafe_b64encode(recipe_id.encode("utf-8")).decode("ascii")


def method_words(codes: list[str]) -> str:
    """Methods in both languages, e.g. "红烧 Red-braise", so Chinese and English queries both match."""
    return ", ".join(f"{BY_CODE[code].zh} {BY_CODE[code].en}" for code in codes if code in BY_CODE)


def name_text(recipe: dict) -> str:
    """name_vector: every name of the dish, then its main cooking method."""
    parts = list(dict.fromkeys(name for name in (recipe["title"], recipe.get("title_en"), recipe.get("title_zh"),
                                                  *recipe.get("aliases", [])) if name))
    method = method_words([recipe["cooking_method"]]) if recipe.get("cooking_method") else ""
    return " | ".join([*parts, method] if method else parts)


def content_text(recipe: dict) -> str:
    """content_vector: all cooking methods, all ingredient lines as written, and the steps."""
    steps = " ".join(" ".join(step.split()) for step in recipe["steps"])
    if len(steps) > STEPS_CHARS:
        half = STEPS_CHARS // 2
        steps = f"{steps[:half]} … {steps[-half:]}"
    parts = [method_words(recipe.get("cooking_methods") or []), "; ".join(recipe["ingredients"]), steps]
    return " | ".join(part for part in parts if part)[:CONTENT_CHARS]


def document(recipe: dict, name_vector: list[float], content_vector: list[float]) -> dict:
    doc = {name: recipe.get(name) for name in TEXT_FIELDS}
    doc.update({name: recipe.get(name) or [] for name in LIST_FIELDS})
    doc.update(key=doc_key(recipe["id"]), name_vector=name_vector, content_vector=content_vector)
    return doc


def call_groups(texts: list[str], limit: int = EMBED_CALL_BYTES) -> list[list[str]]:
    """Consecutive groups of texts, each at most `limit` UTF-8 bytes (a longer single text goes alone)."""
    groups, size = [[]], 0
    for text in texts:
        length = len(text.encode("utf-8"))
        if groups[-1] and size + length > limit:
            groups.append([])
            size = 0
        groups[-1].append(text)
        size += length
    return groups if groups[0] else []


def with_retry(call, texts: list[str], failure: type[Exception]):
    for pause in (*RETRY_PAUSES, None):
        try:
            return call(texts)
        except failure as exc:
            if pause is None:
                raise
            print(f"  embedding call failed ({exc}); retrying in {pause} s")
            time.sleep(pause)


def embed_all(embed, texts: list[str], failure: type[Exception]) -> list[list[float]]:
    return [vector for group in call_groups(texts) for vector in with_retry(embed, group, failure)]


def upload(search, embed, recipes: list[dict], recreate: bool = False, failure: type[Exception] = Exception) -> dict:
    if recreate:
        search.delete_index()
        print(f"deleted index {search.index}")
    search.create_or_update_index(INDEX)
    print(f"index {search.index} is ready; uploading {len(recipes)} recipes in batches of {BATCH}")
    failed, sent = [], 0
    for start in range(0, len(recipes), BATCH):
        batch = recipes[start:start + BATCH]
        vectors = embed_all(embed, [name_text(r) for r in batch] + [content_text(r) for r in batch], failure)
        names, contents = vectors[:len(batch)], vectors[len(batch):]
        failed += search.upload([document(r, n, c) for r, n, c in zip(batch, names, contents)])
        sent += len(batch)
        if (start // BATCH + 1) % 10 == 0 or sent == len(recipes):
            print(f"  {sent}/{len(recipes)} sent")
    for message in failed[:10]:
        print(f"  not stored: {message}")
    return {"sent": sent, "failed": failed}


def report(search) -> None:
    stats = search.stats()
    storage, vectors = stats.get("storageSize", 0) / 1e6, stats.get("vectorIndexSize", 0) / 1e6
    print(f"index now holds {stats.get('documentCount', 0)} recipes, {storage:.1f} MB "
          f"(vectors {vectors:.1f} MB) of the free tier's {FREE_TIER_MB} MB. "
          "These counts can lag a minute behind an upload.")


def main(argv: list[str] | None = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="python -m kb.upload", description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, help="upload only the first N recipes")
    parser.add_argument("--recreate", action="store_true", help="delete and recreate the index first")
    args = parser.parse_args(argv)
    if not RECIPES.exists():
        parser.error("no recipes yet; run python -m kb.build (or python -m kb.sources.fetch) first")

    from app.llm import AzureModelClient, ModelFailure  # needs the agent's venv and .env
    from app.search import AzureSearch, SearchFailure

    try:
        search = AzureSearch("AZURE_SEARCH_ADMIN_KEY")
        llm = AzureModelClient()
    except (ModelFailure, SearchFailure) as exc:
        parser.error(exc.message)
    recipes = [json.loads(line) for line in RECIPES.read_text("utf-8").splitlines() if line.strip()][:args.limit]
    try:
        result = upload(search, llm.embed, recipes, args.recreate, ModelFailure)
        time.sleep(3)
        report(search)
    except (ModelFailure, SearchFailure) as exc:
        print(f"FAILED: {exc.message}")
        raise SystemExit(1)
    if result["failed"]:
        print(f"{len(result['failed'])} recipes were not stored; run again to retry them.")


if __name__ == "__main__":
    main()
