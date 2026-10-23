"""M1 eval, run from agent/: python -m evals.run_eval

Calls the real model, the recipe knowledge base when configured, and web search for cases the knowledge
base doesn't answer, so it costs money. Each row records its route: "kb" (written from a knowledge-base
recipe) or "web". It checks status,
must-have ingredients, profile cases (allergens and dislikes absent from the ingredient list) and
"no search on rejection"; step order and cost are not scored yet.
"""

import json
import sys
from datetime import datetime
from uuid import uuid4

from app import AGENT_ROOT
from app.graph import generate
from app.schemas import GenerateRequest, GenerateResponse, Profile, RecipeInput

CASES = AGENT_ROOT / "evals" / "dishes.json"


def score(case: dict, response: GenerateResponse) -> list[str]:
    """Empty list = pass. must_have is a list of groups; any term in a group satisfies it.

    must_not_have is a flat list; a term found in any ingredient name, step instruction or tip fails
    the case, so an ingredient a step uses without listing it is caught too. Warnings are not checked,
    because that is where substitutions are explained. Both match substrings, lowercased.
    """
    expected = case.get("expect", "succeeded")
    if response.status != expected:
        code = response.error.code if response.error else None
        return [f"status {response.status} (error {code}), expected {expected}"]
    if expected == "rejected":
        return ["rejected input still ran a web search"] if response.usage.search_requests else []
    names = " | ".join(item.name.lower() for item in response.recipe.ingredients)
    missing = [f"missing ingredient: {' / '.join(group)}" for group in case.get("must_have", [])
               if not any(term in names for term in group)]
    steps = " | ".join(f"{step.instruction} {step.tip or ''}".lower() for step in response.recipe.steps)
    unwanted = [f"unwanted ingredient: {term}" for term in case.get("must_not_have", []) if term in names]
    unwanted += [f"unwanted in steps: {term}" for term in case.get("must_not_have", [])
                 if term in steps and term not in names]
    return missing + unwanted


def label(case: dict) -> str:
    profile = case.get("profile", {})
    tags = [f"{key}={','.join(values)}" for key, values in profile.items() if values]
    return f"{case['dish']} [{'; '.join(tags)}]" if tags else case["dish"]


def percentile(values: list[int], fraction: float) -> int:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(fraction * (len(ordered) - 1)))]


def main():
    from app.llm import AzureModelClient

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    from app.search import optional_search

    llm = AzureModelClient()
    kb = optional_search()
    print("knowledge base: " + ("on" if kb else "off (AZURE_SEARCH_ENDPOINT / AZURE_SEARCH_QUERY_KEY not set)"))
    rows = []
    for case in json.loads(CASES.read_text(encoding="utf-8")):
        request = GenerateRequest(request_id=str(uuid4()), user_id="eval",
                                  input=RecipeInput(type="dish_name", value=case["dish"]),
                                  profile=Profile(**case.get("profile", {})))
        response = generate(request, llm, kb=kb)
        problems = score(case, response)
        route = "kb" if any(source.kind == "kb" for source in response.sources) else "web"
        rows.append({"case": label(case), "passed": not problems, "problems": problems, "route": route,
                     "usage": response.usage.model_dump(), "response": response.model_dump()})
        print(f"{'PASS' if not problems else 'FAIL'}  [{route}]  {label(case)}  {'; '.join(problems)}")

    latencies = [row["usage"]["latency_ms"] for row in rows]
    step_times: dict[str, list[int]] = {}
    for row in rows:
        for step, ms in row["usage"]["step_latency_ms"].items():
            step_times.setdefault(step, []).append(ms)
    summary = {
        "cases": len(rows), "passed": sum(row["passed"] for row in rows),
        "answered_from_kb": sum(row["route"] == "kb" for row in rows),
        "latency_ms_p50": percentile(latencies, 0.5), "latency_ms_p95": percentile(latencies, 0.95),
        "latency_ms_p50_by_route": {route: percentile([row["usage"]["latency_ms"] for row in rows if row["route"] == route], 0.5)
                                    for route in sorted({row["route"] for row in rows})},
        **{f"total_{key}": sum(row["usage"][key] for row in rows)
           for key in ("input_tokens", "output_tokens", "search_requests")},
        "step_latency_ms_p50": {step: percentile(times, 0.5) for step, times in step_times.items()},
    }
    output = AGENT_ROOT / "outputs" / f"eval-{datetime.now():%Y%m%d-%H%M%S}.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Saved to: {output}", file=sys.stderr)


if __name__ == "__main__":
    main()
