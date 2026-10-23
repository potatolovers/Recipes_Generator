"""Run from agent/: python -m app.cli "Tomato and egg stir-fry" "Caesar salad" --allergy peanut"""

import argparse
import sys
from datetime import datetime
from uuid import uuid4

from app import AGENT_ROOT
from app.graph import generate
from app.llm import AzureModelClient, ModelFailure
from app.schemas import GenerateRequest, Profile, RecipeInput
from app.search import optional_search


def main():
    parser = argparse.ArgumentParser(description="Dish names → knowledge base or web search → recipe JSON (contract v0)")
    parser.add_argument("dishes", nargs="+")
    parser.add_argument("--servings", type=int, default=2)
    parser.add_argument("--allergy", action="append", default=[], help="repeatable, e.g. --allergy peanut")
    parser.add_argument("--dislike", action="append", default=[])
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        llm = AzureModelClient()
    except ModelFailure as exc:
        print(f"{exc.code}: {exc.message}", file=sys.stderr)
        raise SystemExit(1)

    kb = optional_search()  # None without AZURE_SEARCH_ENDPOINT / AZURE_SEARCH_QUERY_KEY: web search only
    failed = 0
    for dish in args.dishes:
        request = GenerateRequest(
            request_id=str(uuid4()), user_id="cli", input=RecipeInput(type="dish_name", value=dish),
            servings=args.servings, profile=Profile(allergies=args.allergy, dislikes=args.dislike),
        )
        output = AGENT_ROOT / "outputs" / f"{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:8]}"
        output.mkdir(parents=True)
        response = generate(request, llm, lambda name, value: (output / name).write_text(value, encoding="utf-8"), kb)
        failed += response.status != "succeeded"
        print(response.model_dump_json(indent=2))
        print(f"Stage records saved to: {output}\n", file=sys.stderr)
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
