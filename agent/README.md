# Agent service (M0–M2)

Dish name → recipe JSON, built to [docs/AGENT_SERVICE_PLAN.md](../docs/AGENT_SERVICE_PLAN.md), which is the
source of truth for this service. Separate from `backend/`; nothing calls it yet.

**Status:** M1 (dish name → web search → recipe) is deployed to Azure Container Apps. M2's recipe knowledge
base is built and uploaded, and the graph now searches it before the web (`kb_retrieve` → `grade`); that route
is tested with scripted replies and a fake search service only, not yet against the real services.
Not started: OpenTelemetry tracing, `traceparent`, cost per run, profile memory.

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
| `python -m app.cli "Tomato and egg stir-fry" "Caesar salad"` | Run dish names, save `01_request` → `07_response` under `outputs/` (`03_kb_retrieve` / `04_grade` show the knowledge-base step) |
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

`kb/` holds the recipe knowledge base: `kb/data/recipes.jsonl` (4,958 recipes, one per line, same shape for
every source, see `kb/sources/record.py`) goes into an Azure AI Search index. `kb/data/` is git-ignored.

```powershell
.\.venv\Scripts\python.exe -m kb.methods            # label cooking methods with the model; --limit N, --redo
.\.venv\Scripts\python.exe -m kb.build              # raw downloads → recipes.jsonl, merging saved names + methods
.\.venv\Scripts\python.exe -m kb.upload             # recipes → Azure AI Search index (recipes-v1); --recreate, --limit
.\.venv\Scripts\python.exe -m kb.query "Kung pao chicken"   # top 3 hybrid matches, with the read-only query key
.\.venv\Scripts\python.exe -m kb.query beef --method stew   # filter by main cooking method (or --family)
.\.venv\Scripts\python.exe -m evals.run_retrieval_eval      # score keyword / vector combinations: hit@1, hit@3, MRR
.\.venv\Scripts\python.exe -m kb.sources.fetch      # only to rebuild from scratch: download all sources again
```

`kb.upload` needs `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_ADMIN_KEY` and `AGENT_MODEL_EMBED` in `.env` (see
`.env.example`); the admin key never goes to the Container App. Each recipe is one search document: its names
are searchable by keyword (`title`, `title_en` with an English analyzer, `title_zh` with a Chinese one,
`aliases`), and two 512-number vectors (text-embedding-3-small) are searchable by meaning:

| Vector | Text it is made from | Good for |
| --- | --- | --- |
| `name_vector` | every name and alias, then the main cooking method in Chinese and English | dish-name queries |
| `content_vector` | all cooking methods, every ingredient line as written, steps (first and last 600 characters when longer than 1,200) | what the dish is: ingredients, technique, described dishes |

Embedding both costs under $0.05 for all recipes (about 1.2M tokens). Ingredients, steps and notes are also stored for the agent to
read. Each vector adds about 11 MB; the index is about 32 MB of the free tier's 50 MB. Re-running replaces
recipes by id, but replaced copies count toward the 50 MB until Azure cleans them up, so after a schema change
use `--recreate` (the index is empty for the few minutes the upload takes).

`evals/retrieval_cases.json` lists 68 English queries, written as English-speaking users would type them: dish
names (Western, international and Chinese dishes by their English names), the same food cooked another way
(grilled vs poached salmon, fried vs scrambled eggs), dishes described instead of named, and 5 dishes the index
doesn't have (Cobb salad, Crab rangoon…), with the recipe ids that count as right. `evals.run_retrieval_eval`
asks the index each query seven ways (keyword only, each vector, and combinations) with the read-only query
key and prints hit@1, hit@3 and MRR per combination, then the misses of the best one. One embedding call; search
queries on the free tier are free.

English/Chinese names and alternate names come from `kb/data/names.jsonl`: model answers for 3,630 recipes from
an earlier naming step, since removed. `kb.build` merges them and leaves out alternate names that were given to
3+ different recipes (categories such as "beef stew", not names). The other 1,328 recipes keep only their own
title. Back up `names.jsonl`: it can't be regenerated without that step.

Cooking methods use the fixed list in `kb/cooking.py`: 75 Chinese and Western techniques (炒, 爆, 熘, 红烧, 卤,
白灼, 拔丝, sous vide, confit, gratin…) in 9 families. `kb.methods` asks the lightweight model (`AGENT_MODEL_LIGHTWEIGHT`, e.g.
gpt-4.1-mini; default `AGENT_MODEL_CLASSIFY`) for each recipe's main method and every method its steps use, 40 recipes per call;
answers outside the list are rejected. About $0.63 on gpt-4.1-mini for all recipes; answers
are saved in `kb/data/methods.jsonl`, so it resumes and later runs only label new recipes. The index gets
`cooking_method`, `cooking_methods` and `cooking_family`, all filterable and facetable, not searched.

| Source (`kb/sources/`) | What | License / terms |
| --- | --- | --- |
| `howtocook` | Chinese home recipes from GitHub, pinned to one commit | Unlicense (public domain) |
| `themealdb` | International meals with measures; many link a YouTube video | Free key "1" for development and education only; supporter key before an app-store release; don't republish the data (this repo is public) |
| `wikibooks` | English recipes from the Wikibooks Cookbook | CC BY-SA 4.0: credit the page; adaptations share alike |

Raw downloads stay in `kb/data/raw/<source>/`, so a parser fix needs only `kb.build`. The build prints counts per
source and which eval dishes have a recipe with the same name. Records with no ingredients or no steps are
skipped.

## Layout (plan module → code)

```text
app/schemas.py            schemas/      contract v0 models; examples/ holds request + 3 responses
app/api/main.py           api/          /v1/recipes:generate (?stream=true SSE), /healthz, X-Api-Key, MOCK=1
app/graph/__init__.py     graph/        StateGraph wiring, retry cap, response assembly
app/graph/classify.py     classify      reject non-dishes, normalize name, aliases
app/graph/kb_retrieve.py  kb_retrieve   English dish name → name_vector search, top 3 (M2)
app/graph/grade.py        grade         lightweight model: each candidate same / variant / different (M2)
app/graph/web_research.py web_research  Responses API web_search → cited notes (when the knowledge base has no match)
app/graph/synthesize.py   synthesize    structured output into Recipe
app/graph/validate.py     validate      unit/citation/reference checks, allergen synonym list
app/llm.py                —             ModelClient protocol + Azure client (vendor formats stay here)
app/search.py             —             Azure AI Search REST client; optional_search() for the agent (query key)
evals/                    evals/        dishes.json, run_eval.py; retrieval_cases.json, run_retrieval_eval.py
kb/                       ingest/       recipes.jsonl → search index (M2); kb/sources/ downloads + parsers
```

## Behaviour to know

- Every response is HTTP 200 with `status` `succeeded` / `rejected` / `failed`; only auth (401/503) and
  malformed requests (422) use other codes. The plan does not specify this; change it if the backend prefers.
- `validate` sends a failed draft back to `synthesize` once; a second failure returns `VALIDATION_FAILED`
  with `recipe: null` rather than an unchecked recipe.
- Non-food input returns `NOT_A_RECIPE` after `classify`, before any search.
- Knowledge base first: `kb_retrieve` embeds the English dish name and searches `name_vector` (top 3);
  `grade` asks the lightweight model whether each candidate is the same dish, a variant or a different dish.
  The first "same" becomes the only source (`sources[].kind` = `kb`, `url` = its original page, the title
  credits the site, as Wikibooks' CC BY-SA requires) and web search is skipped. Otherwise `web_research` runs
  as in M1. When search isn't configured, fails or times out (10 s), or the grader call fails, the request
  continues with web search: the knowledge base never fails a request.
- Container App settings for the knowledge base: `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_QUERY_KEY` (read-only;
  never the admin key), `AZURE_SEARCH_INDEX`, `AGENT_MODEL_EMBED`, `AGENT_MODEL_LIGHTWEIGHT`. Without the first
  two the service runs web-only, as before.
- `usage.step_latency_ms` maps each node to the milliseconds it took (summed if it ran twice, and including a
  node that failed). It is an addition to the plan's v0 `usage` example.
- The allergen check matches ingredient names against a short synonym list; it is a safety net, not a guarantee.
