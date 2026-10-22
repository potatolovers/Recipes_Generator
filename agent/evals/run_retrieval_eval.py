"""M2 retrieval eval, run from agent/: python -m evals.run_retrieval_eval [--top 10] [--misses 3]

Asks the recipe index every query in evals/retrieval_cases.json in seven ways (keyword search on the
names, each vector field, and their combinations) and scores whether a right recipe comes back on top:
  hit@1  share of queries whose first result is a right recipe
  hit@3  share with a right recipe in the first 3 (the agent will read the top 3)
  MRR    mean of 1/rank of the first right recipe (1, 1/2, 1/3, ...; 0 when none is in the top N)
Query groups: name (a dish name, Chinese or English), method (names where the cooking method is what
tells dishes apart, e.g. 清蒸鱼 vs 红烧鱼), description (the dish described, not named).

Uses the read-only query key, like the deployed agent, and one embedding call for all queries
(a fraction of a cent). Searches on the free tier cost nothing.
"""

import argparse
import json
import sys
from datetime import datetime

from app import AGENT_ROOT

CASES = AGENT_ROOT / "evals" / "retrieval_cases.json"
GROUPS = ("name", "method", "description")
# combination -> (keyword search on the names?, vector fields searched)
COMBINATIONS = {
    "keyword": (True, ()),
    "name vector": (False, ("name_vector",)),
    "content vector": (False, ("content_vector",)),
    "name + content vectors": (False, ("name_vector", "content_vector")),
    "keyword + name vector": (True, ("name_vector",)),
    "keyword + content vector": (True, ("content_vector",)),
    "keyword + both vectors": (True, ("name_vector", "content_vector")),  # what kb.query and the agent use
}


def load_queries(cases: list[dict]) -> list[dict]:
    """One row per query text: {"dish", "group", "text", "expect"}."""
    return [{"dish": case["dish"], "group": group, "text": text, "expect": case["expect"]}
            for case in cases for group, texts in case["queries"].items() for text in texts]


def first_right(ids: list[str], expect: list[str]) -> int | None:
    """Rank (1-based) of the first right recipe, or None when no result is right."""
    return next((rank for rank, recipe_id in enumerate(ids, 1) if recipe_id in expect), None)


def summarize(ranks: list[int | None]) -> dict:
    count = len(ranks) or 1
    return {"queries": len(ranks),
            "hit@1": sum(rank == 1 for rank in ranks) / count,
            "hit@3": sum(rank is not None and rank <= 3 for rank in ranks) / count,
            "mrr": sum(1 / rank for rank in ranks if rank) / count}


def run(search, rows: list[dict], vectors: list[list[float]], top: int,
        combinations: dict = COMBINATIONS) -> dict[str, list[dict]]:
    """Every query in every combination; each row gains the first right rank and the top 3 titles."""
    results = {}
    for name, (keyword, fields) in combinations.items():
        scored = []
        for row, vector in zip(rows, vectors):
            hits = search.hybrid(row["text"] if keyword else None, vector, top, "id,title,title_zh",
                                 vector_fields=fields)
            scored.append({**row, "rank": first_right([hit["id"] for hit in hits], row["expect"]),
                           "top3": [hit.get("title_zh") or hit["title"] for hit in hits[:3]]})
        results[name] = scored
    return results


def table(results: dict[str, list[dict]]) -> list[str]:
    width = max(map(len, results)) + 2
    lines = [f"{'combination':<{width}}  hit@1  hit@3   MRR  |  hit@3 by group: "
             + "  ".join(f"{group}" for group in GROUPS)]
    for name, rows in results.items():
        total = summarize([row["rank"] for row in rows])
        by_group = [summarize([row["rank"] for row in rows if row["group"] == group])["hit@3"] for group in GROUPS]
        lines.append(f"{name:<{width}}  {total['hit@1']:5.2f}  {total['hit@3']:5.2f}  {total['mrr']:5.2f}  |  "
                     + "  ".join(f"{value:>{len(group)}.2f}" for value, group in zip(by_group, GROUPS)))
    return lines


def misses(rows: list[dict], worse_than: int) -> list[str]:
    return [f"  {row['text']}  [{row['group']}]  first right at "
            f"{row['rank'] or 'none'}; got {' / '.join(row['top3']) or 'nothing'}"
            for row in rows if row["rank"] is None or row["rank"] > worse_than]


def main(argv: list[str] | None = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="python -m evals.run_retrieval_eval", description=__doc__.splitlines()[0])
    parser.add_argument("--top", type=int, default=10, help="results fetched per query; MRR counts these (default 10)")
    parser.add_argument("--misses", type=int, default=3,
                        help="list queries of the best combination with no right recipe in this many (default 3)")
    args = parser.parse_args(argv)

    from app.llm import AzureModelClient, ModelFailure
    from app.search import AzureSearch, SearchFailure

    rows = load_queries(json.loads(CASES.read_text(encoding="utf-8")))
    try:
        search, llm = AzureSearch(), AzureModelClient()
        vectors = llm.embed([row["text"] for row in rows])
        results = run(search, rows, vectors, args.top)
    except (ModelFailure, SearchFailure) as exc:
        print(f"FAILED: {exc.message}")
        if "content_vector" in exc.message:
            print("The index has no content_vector yet: run python -m kb.upload --recreate first.")
        raise SystemExit(1)

    print(f"{len(rows)} queries; " + ", ".join(f"{sum(row['group'] == group for row in rows)} {group}" for group in GROUPS))
    print("\n".join(table(results)))
    best = max(results, key=lambda name: (summarize([r["rank"] for r in results[name]])["mrr"], name))
    found = misses(results[best], args.misses)
    print(f"\nBest by MRR: {best}. Queries without a right recipe in its top {args.misses} ({len(found)}):")
    print("\n".join(found) or "  none")

    output = AGENT_ROOT / "outputs" / f"retrieval-{datetime.now():%Y%m%d-%H%M%S}.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps({"summary": {name: summarize([r["rank"] for r in rows_]) for name, rows_ in results.items()},
                                  "rows": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved to: {output}", file=sys.stderr)


if __name__ == "__main__":
    main()
