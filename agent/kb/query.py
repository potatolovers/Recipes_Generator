"""Tries dish names against the recipe index, the way the agent's kb_retrieve step will.

Run from agent/ with the agent's venv: python -m kb.query "Kung pao chicken" "Beef stew"
                                       python -m kb.query beef --method stew     only stews (filter)
Uses the read-only query key (AZURE_SEARCH_QUERY_KEY), the same one the deployed agent gets.
Each query is hybrid: keyword search on the names plus vector search on name_vector and content_vector,
merged by rank. evals/run_retrieval_eval.py compares these parts one by one.
"""

import argparse
import sys


def main(argv: list[str] | None = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="python -m kb.query", description=__doc__.splitlines()[0])
    parser.add_argument("dishes", nargs="+", help="dish names to look up")
    parser.add_argument("--top", type=int, default=3, help="results per dish (default 3, as the agent uses)")
    parser.add_argument("--method", help="only recipes whose main cooking method is this code (kb/cooking.py)")
    parser.add_argument("--family", help="only recipes in this cooking family, e.g. braise_stew")
    args = parser.parse_args(argv)

    from kb.cooking import BY_CODE, FAMILIES

    if args.method and args.method not in BY_CODE:
        parser.error(f"unknown method {args.method!r}; codes are listed in kb/cooking.py")
    if args.family and args.family not in FAMILIES:
        parser.error(f"unknown family {args.family!r}; choose from {', '.join(FAMILIES)}")
    conditions = [f"cooking_method eq '{args.method}'" if args.method else "",
                  f"cooking_family eq '{args.family}'" if args.family else ""]
    filter_ = " and ".join(condition for condition in conditions if condition) or None

    from app.llm import AzureModelClient, ModelFailure
    from app.search import AzureSearch, SearchFailure

    try:
        search, llm = AzureSearch(), AzureModelClient()
        vectors = llm.embed(args.dishes)
        for dish, vector in zip(args.dishes, vectors):
            print(dish)
            hits = search.hybrid(dish, vector, args.top, "title,title_en,title_zh,source,cooking_method", filter_)
            for rank, hit in enumerate(hits, 1):
                names = " / ".join(dict.fromkeys(n for n in (hit["title"], hit.get("title_en"), hit.get("title_zh")) if n))
                print(f"  {rank}. {hit['@search.score']:.4f}  {names}  [{hit['source']} · {hit.get('cooking_method') or 'no method yet'}]")
    except (ModelFailure, SearchFailure) as exc:
        print(f"FAILED: {exc.message}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
