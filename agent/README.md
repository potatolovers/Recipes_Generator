# Agent service (M0–M1 starter)

Dish name → recipe JSON, built to [docs/AGENT_SERVICE_PLAN.md](../docs/AGENT_SERVICE_PLAN.md), which is the
source of truth for this service. Separate from `backend/`; nothing calls it yet.

**Status:** the API, graph, validation and allergen post-check are tested with scripted replies only (16 tests).
The Azure client, the smoke script and the eval runner have never been run against a real deployment.
Not started: Azure resources, Dockerfile/deploy, OpenTelemetry tracing, `traceparent`, cost per run.

## Run

```powershell
cd agent
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn app.api.main:app --port 8100
```

`.env.example` starts with `MOCK=1`: `POST /v1/recipes:generate` returns `examples/response_succeeded.json`
with a "Mock response" warning, so the backend can integrate before any model exists.

```powershell
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8100/v1/recipes:generate' -Headers @{'X-Api-Key'='dev-local-key'} -ContentType 'application/json' -InFile examples\request.json | ConvertTo-Json -Depth 10
```

For real runs, fill in the Foundry endpoint, key and two deployment names in `.env`, set `MOCK=0`, then:

| Command | Plan item |
| --- | --- |
| `python -m app.smoke` | M0: one `web_search` call prints a cited answer |
| `python -m app.cli "番茄炒蛋" "Caesar salad"` | Day 2: run dish names, save `01_request` → `05_response` under `outputs/` |
| `python -m evals.run_eval` | Day 5: 20 dishes, 8 profile cases (allergies, dislikes), 2 non-food inputs; pass/fail, p50/p95 latency, tokens, searches |

## Visualize the graph (LangGraph Studio)

`app/graph/studio.py` is the same graph plus a first node, `prepare_request`, that turns Studio's input
form (dish, servings, allergies, dislikes) into a `GenerateRequest`. It reads the model settings from `.env`.

```powershell
.\.venv\Scripts\python.exe -m pip install -U "langgraph-cli[inmem]" "langgraph-api>=0.15"
$env:PYTHONUTF8 = 1
.\.venv\Scripts\langgraph.exe dev
```

`PYTHONUTF8` is required on Windows with a non-UTF-8 system locale (e.g. Chinese/GBK); without it the
server fails at startup with `UnicodeDecodeError: 'gbk' codec can't decode`. Install with `requirements.txt`
already applied: its FastAPI upper bound keeps the two installs compatible.

The browser opens https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024 (free LangSmith sign-in).
Every Studio run calls the real model and web search; `MOCK` does not apply. With `LANGSMITH_TRACING=false`
in `.env`, runs stay on this machine. "Deserializing unregistered type app.schemas..." warnings in the
terminal are expected.

## Knowledge base data (M2)

`kb/` downloads recipes and builds `kb/data/recipes.jsonl`, one recipe per line in the same shape for every
source (`kb/record.py`). Standard library only. `kb/data/` is git-ignored: anyone can rebuild it.

```powershell
.\.venv\Scripts\python.exe -m kb.fetch               # all sources, then build; re-run to resume
.\.venv\Scripts\python.exe -m kb.fetch themealdb     # only the named sources
.\.venv\Scripts\python.exe -m kb.build               # re-parse what's downloaded, no network
```

| Source | What | License / terms |
| --- | --- | --- |
| `howtocook` | Chinese home recipes from GitHub, pinned to one commit | Unlicense (public domain) |
| `themealdb` | International meals with measures; many link a YouTube video | Free key "1" for development and education only; supporter key before an app-store release |
| `wikibooks` | English recipes from the Wikibooks Cookbook | CC BY-SA 4.0: credit the page; adaptations share alike |

Raw downloads stay in `kb/data/raw/<source>/`, so a parser fix needs only `kb.build`. The build prints counts per
source and which eval dishes have a recipe with the same title. Records with no ingredients or no steps are
skipped. English titles for Chinese recipes (and the reverse) come in the next step.

## Layout (plan module → code)

```text
app/schemas.py            schemas/      contract v0 models; examples/ holds request + 3 responses
app/api/main.py           api/          /v1/recipes:generate (?stream=true SSE), /healthz, X-Api-Key, MOCK=1
app/graph/__init__.py     graph/        StateGraph wiring, retry cap, response assembly
app/graph/classify.py     classify      reject non-dishes, normalize name, aliases
app/graph/web_research.py web_research  Responses API web_search → cited notes
app/graph/synthesize.py   synthesize    structured output into Recipe
app/graph/validate.py     validate      unit/citation/reference checks, allergen synonym list
app/llm.py                —             ModelClient protocol + Azure client (vendor formats stay here)
evals/                    evals/        dishes.json, run_eval.py
kb/                       ingest/       recipe sources → kb/data/recipes.jsonl (M2)
```

## Behaviour to know

- Every response is HTTP 200 with `status` `succeeded` / `rejected` / `failed`; only auth (401/503) and
  malformed requests (422) use other codes. The plan does not specify this; change it if the backend prefers.
- `validate` sends a failed draft back to `synthesize` once; a second failure returns `VALIDATION_FAILED`
  with `recipe: null` rather than an unchecked recipe.
- Non-food input returns `NOT_A_RECIPE` after `classify`, before any search.
- `usage.step_latency_ms` maps each node to the milliseconds it took (summed if it ran twice, and including a
  node that failed). It is an addition to the plan's v0 `usage` example.
- The allergen check matches ingredient names against a short synonym list; it is a safety net, not a guarantee.
