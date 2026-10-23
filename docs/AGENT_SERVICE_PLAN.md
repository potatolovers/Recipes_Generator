# 拾味 Agent Service — Architecture Review & Milestone Plan (Azure)

Oct 5, 2026 · @Xingyu

## TL;DR

Your plan is sound: a separate LangGraph agent service on Azure, called by the backend over HTTP, built in four milestones with YouTube last. Change four things before you write code:

1. **Allergies are not memory.** Store them as explicit profile data in the backend, send them on every request, and check the output in code.
2. **Freeze a v0 JSON contract first**, so your teammate can build against mocks the same day.
3. **Host on Azure Container Apps; use Foundry for models, web search and tracing.** Foundry hosted agents are a good later step, not the first one.
4. **Plan YouTube as a tiered pipeline.** Transcripts cannot be pulled reliably from Azure, so read the description and linked recipe page first.

**Start now:** write the v0 schemas, deploy one mini model in a Foundry project, and run an M1 graph locally on 10 dish names. The day-by-day list is in *Start here* below.

## Verdict: what works and what to change

Keep the overall shape; fix six weak points now, while each fix is still a schema field or a design note rather than a rewrite.

| Area | Your plan | Verdict | What to do |
| --- | --- | --- | --- |
| Service boundary | Agent is its own service; backend calls it over HTTP | Keep | Two owners, two deploys, model keys stay server-side. Make the agent's ingress internal so only the backend can reach it. |
| Framework | LangGraph | Keep | Each milestone becomes new nodes on one graph. Its checkpointer and store cover run state (M1) and memory (M2). |
| Milestone order | Search → memory → RAG → YouTube | Keep, with one split | Move the explicit profile (allergies, diet, default servings) into M1 as request fields. M2 then covers learned preferences only. |
| Allergies | Remembered by agent memory | Change | Allergies are safety data: user-confirmed, stored by the backend, sent on every call, and checked by code after generation. LLM memory can miss, merge or be poisoned. |
| Output | "Ingredients, amounts for 2, steps" | Tighten | Agree a versioned JSON schema first, a slim subset of the repo's W1.1 contract: per-field origin (extracted / estimated), US units and °F, per-step ingredients, sources. |
| YouTube | Extract the recipe from the video | Redesign | The captions API only serves videos you can edit, and unofficial transcript tools get blocked from cloud IPs. Use a tiered pipeline, cheapest first, cached per video. |
| Latency | Not specified | Add | Dish name: synchronous with streamed progress, target p50 under 20 s. YouTube: async job (202 + job id + polling), since it can take a minute or more. |
| Security | Mentioned | Add | Web pages and video descriptions are untrusted text that can carry prompt injection. Treat tool output as data, never write web text into memory, validate every output. |

**Alternative order:** if accuracy turns out to be the bigger pain after M1, swap M2 and M3. RAG needs no user identity; learned memory does, and the app has no accounts yet.

**Repo mismatch to resolve first:** the repo's PROJECT.md and ARCHITECTURE.md still plan the OpenAI Agents API, text / image / video plus TikTok and Bilibili inputs, a Python server on a dev laptop, and personalization only in V3. Pick one plan and update PROJECT.md, or you and your teammate will build against different assumptions.

## Overall architecture

&#91;embedded content: system architecture · app, two services you deploy, managed Azure resources\]

The backend owns users, allergies, jobs and rate limits; your agent owns reasoning, retrieval and memory. Everything stays inside Azure except the optional M4 video model.

In restaurant terms: the backend is the front desk that takes the order, checks the allergy card and says how long the wait is. Your agent is the kitchen, and LangGraph is its station-by-station ticket flow. The knowledge base is the house recipe binder, web search is phoning another restaurant, and memory is the notes kept on regulars.

The split pays off because two people own two parts. A solo prototype could run everything inside one FastAPI app, at the cost of that clean handoff.

## Key decisions, with pros and cons

Five choices shape everything else. The recommended option is listed first in each table.

### 1. Where the agent runs (M1)

| Option | Pros | Cons | Pick it when |
| --- | --- | --- | --- |
| **Azure Container Apps + FastAPI** (recommended) | You design the API (`/v1/recipes`, jobs, streaming). Any auth scheme. The same container runs on your laptop. Free grant of 180,000 vCPU-seconds and 2 million requests per month; scales to zero. | You wire up tracing, auth and scaling settings yourself. | You want to learn agent serving and own the contract. |
| Foundry hosted agent (LangGraph adapter) | Generally available. Managed sessions, scale to zero, tracing to App Insights built in. `/invocations` accepts custom JSON. | Callers need Microsoft Entra ID tokens. Endpoint shapes are fixed (`/responses` expects a messages-style state). Less control over jobs, streaming and errors. | Later: redeploy the same graph to learn Foundry once the contract is stable. |

Sources: [Container Apps billing](https://learn.microsoft.com/en-us/azure/container-apps/billing), [LangGraph hosted agents](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/langchain-hosted-agents), [hosting options compared](https://devblogs.microsoft.com/all-things-azure/hostedagent/).

### 2. Web search (M1)

| Option | Pros | Cons |
| --- | --- | --- |
| **Azure OpenAI Responses API `web_search` tool** (recommended) | GA; no separate Bing resource; one call searches, reads and cites. | Billed as Grounding with Bing at $14 per 1,000 requests. Data leaves the Azure compliance boundary. Apps must show citations to users. You don't pick the pages. |
| Grounding with Bing Search tool | Same index, more knobs (count, freshness, market). | Needs its own Bing resource; built for Foundry agents, awkward from LangGraph. |
| Third-party search API as a LangGraph tool | You see raw results and choose which pages to read. | Outside Azure; another vendor and key. |

Sources: [web search in Responses API](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/web-search), [web grounding overview](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/web-overview), [Grounding with Bing pricing](https://www.microsoft.com/en-us/bing/apis/grounding-pricing).

### 3. Memory (M2)

| Option | Pros | Cons |
| --- | --- | --- |
| **Explicit profile in the backend DB + LangGraph Store on Postgres for learned preferences** (recommended) | Allergies stay deterministic and auditable. The store is namespaced per user and supports semantic search with pgvector. Same Postgres as the checkpointer; portable. | You write the extraction step yourself (or use the LangMem library). |
| Foundry Memory (Memory Store API) | Extracts user-profile and chat-summary memories automatically; CRUD API callable from custom code. | Preview. The concept page lists 100 scopes per store, roughly 100 users. No VNet support. Fine as an M2 experiment, never for allergies. |

Sources: [Foundry memory concepts](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/what-is-memory), [memory how-to](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/memory-usage).

### 4. Knowledge base store (M3)

| Option | Pros | Cons |
| --- | --- | --- |
| **Azure AI Search** (recommended) | Hybrid keyword + vector search out of the box, which matters because exact dish names should match. Semantic ranker. Free tier: 1 per subscription, 50 MB, 3 indexes. A pay-per-use Serverless tier is in preview. | Free tier holds only a few thousand recipes with vectors (estimate) and may be deleted after long inactivity. Basic tier is a fixed monthly cost. |
| pgvector in the same Postgres | One database for everything; cheapest. | You build keyword + vector fusion and ranking yourself. |

Sources: [AI Search tiers](https://learn.microsoft.com/en-us/azure/search/search-sku-tier), [AI Search limits](https://learn.microsoft.com/en-us/azure/search/search-limits-quotas-capacity).

### 5. YouTube evidence (M4)

Read cheap text before watching expensive video, the way you read a menu before tasting the dish. Token counts are for a 10-minute video and are estimates.

| Tier | Evidence | Cost | Notes |
| --- | --- | --- | --- |
| 1 | Title, description, chapters via YouTube Data API `videos.list` | 1 quota unit; under 2k tokens | Official. Many cooking channels put the full recipe or a link here. |
| 2 | Recipe page linked in the description | 3k–5k tokens | Parse schema.org `Recipe` JSON-LD first; respect the site's terms. |
| 3 | Transcript | about 2k tokens | `captions.download` needs edit rights on the video (200 units). Unofficial fetchers get blocked from cloud IPs. Treat as optional. |
| 4 | Video model | about 60k tokens (about 100 tokens per second at low resolution) | Gemini accepts public YouTube URLs directly (preview, outside Azure). An Azure-only path needs the video file, e.g. a user upload. |

Don't download YouTube videos server-side: it breaks YouTube's terms and the repo's own rule against bypassing platform limits. If most shared links turn out to be Shorts with empty descriptions, tier 4 becomes the default; budget for it.

Sources: [videos.list](https://developers.google.com/youtube/v3/docs/videos/list), [captions.download](https://developers.google.com/youtube/v3/docs/captions/download), [transcript tools blocked in production](https://transcriptfetch.com/blog/youtube-transcript-api-not-working-in-production), [Gemini video understanding](https://ai.google.dev/gemini-api/docs/video-understanding).

## Backend ↔ agent contract v0

Freeze this before M1 code. It is a slim subset of the repo's W1.1 contract, versioned by `schema_version` so fields can be added without breaking the app.

| Endpoint | Purpose | Milestone |
| --- | --- | --- |
| `POST /v1/recipes:generate` | Dish name → recipe, synchronous. `?stream=true` sends progress events over SSE. | M1 |
| `GET /healthz` | Liveness check for Container Apps | M1 |
| `POST /v1/feedback` | User edits and ratings → memory writer | M2 |
| `POST /v1/jobs` | YouTube URL → `202 Accepted` + `job_id` | M4 |
| `GET /v1/jobs/{job_id}` | `queued` / `running` / `succeeded` / `failed`, plus the result | M4 |

**Auth:** M1 uses an `X-Api-Key` header whose value lives in Key Vault, on internal-only ingress. From M2, switch to managed identity (Entra ID tokens). The backend forwards a `traceparent` header so one trace spans both services.

**Example input** (backend → agent):

```json
{
  "schema_version": "0.1",
  "request_id": "7c1e9a52-3f0b-4d61-9a77-2b8c0e4f5d10",
  "user_id": "anon-5f2c81",
  "input": { "type": "dish_name", "value": "Tomato and egg stir-fry" },
  "servings": 2,
  "profile": { "allergies": ["peanut"], "diet": [], "dislikes": ["cilantro"] },
  "locale": "en-US"
}
```

**Example output** (agent → backend, trimmed to two ingredients and one step):

```json
{
  "schema_version": "0.1",
  "run_id": "run_01JB7Q",
  "status": "succeeded",
  "classification": { "type": "dish", "normalized_name": "Tomato and egg stir-fry" },
  "recipe": {
    "title": "Tomato and Egg Stir-Fry",
    "servings": 2,
    "times": { "prep_min": 10, "cook_min": 8, "total_min": 18, "origin": "estimated" },
    "ingredients": [
      { "id": "egg", "name": "Large eggs", "quantity": 4, "unit": "count", "origin": "extracted", "source_ids": ["s1", "s2"] },
      { "id": "tomato", "name": "Ripe tomatoes", "quantity": 2, "unit": "count", "prep": "cut into wedges", "origin": "extracted", "source_ids": ["s1"] }
    ],
    "steps": [
      { "order": 1, "instruction": "Beat the eggs with a pinch of salt.", "ingredients_used": [{ "ingredient_id": "egg", "quantity": 4, "unit": "count" }], "duration_min": 1, "tip": "Beat until no streaks of white remain." }
    ],
    "warnings": ["Checked against your allergies: no peanut ingredients."]
  },
  "sources": [
    { "id": "s1", "kind": "web", "title": "…", "url": "https://…" },
    { "id": "s2", "kind": "web", "title": "…", "url": "https://…" }
  ],
  "usage": { "latency_ms": 14200, "input_tokens": 18400, "output_tokens": 2100, "search_requests": 3 },
  "error": null
}
```

`sources[].kind` is `web` (a page found by web search) or `kb` (a recipe from the agent's knowledge base, M2; `url` is its original page and `title` names the site). Progress events over SSE name the graph nodes: `classify`, `kb_retrieve`, `grade`, `web_research`, `synthesize`, `validate`; `grade` and `web_research` run only when needed.

A non-food input such as "how do I fix my car" returns `"status": "rejected"`, `"recipe": null` and `"error": { "code": "NOT_A_RECIPE" }`, without any web search. The `usage` numbers above are placeholders until M1 measures real ones.

## Milestones and their modules

Each milestone adds nodes to one graph and at most one or two Azure resources. Deploy each to Azure and pass its test before starting the next.

&#91;embedded content: agent graph · end state, nodes tagged by milestone\]

The M1 path is the accented column; later milestones slot their nodes between Classify and Synthesize without changing the API.

### M0 · Contract and Azure foundation (before any agent code)

| Module | What it does | Techniques / libraries | Azure |
| --- | --- | --- | --- |
| `schemas/` | Request, Recipe, Error models with `schema_version` | Pydantic v2; export JSON Schema for your teammate | — |
| Mock endpoint | Returns the example JSON so the backend can integrate today | FastAPI with fixed responses | — |
| Foundation | Resource group, Foundry project, one chat model deployment, Key Vault, App Insights | `az` CLI or `azd`, role assignments | Foundry, Key Vault, App Insights |

**Done when:** the backend calls the mock and parses it; a 10-line script calls your model with `web_search` and prints a cited answer.

### M1 · Dish name → web search → recipe

| Module | What it does | Techniques / libraries | Azure |
| --- | --- | --- | --- |
| `api/` | `/v1/recipes:generate`, `/healthz`, API-key check, `run_id` | FastAPI, uvicorn, SSE for progress | Container Apps, internal ingress |
| `graph/` | Typed state; nodes wired with conditional edges; retry cap of 1 | LangGraph `StateGraph` | — |
| `classify` | Rejects non-dishes; normalizes the name; English aliases for Chinese names | Cheapest model + structured output | Foundry (nano model) |
| `web_research` | Finds 2–3 credible recipes; returns cited notes | Responses API `web_search` tool | Foundry (mini model) |
| `synthesize` | Writes the recipe for 2 servings in US units; marks estimated fields | Structured outputs into the Pydantic schema; scaling rules in the prompt | Foundry (mini model) |
| `validate` | Schema, unit sanity, citations present, allergen match; one repair retry | Pydantic validators; allergen synonym list in code (peanut → groundnut, satay…) | — |
| Observability | One trace per run: tokens, latency, search count, cost | OpenTelemetry → App Insights | App Insights |
| `evals/` | 20 dishes (10 Chinese, 10 Western) with must-have ingredients and step order | pytest + golden files; LLM-as-judge rubric later | Foundry evaluations (optional) |

**Done when:** the backend calls the deployed URL; all 20 dishes return schema-valid JSON; non-food input is rejected without a search; p50 latency, tokens and cost per run are recorded.

**Estimate (measure it):** about $0.05–0.10 per request, about half of it web search (2–4 Bing requests at $14 per 1,000), and 10–25 s end to end. With [Oct 2026 Azure prices](https://benchlm.ai/azure/llm-pricing), gpt-5.4-mini is $0.75 / $4.50 and gpt-5.4-nano $0.20 / $1.25 per 1M input / output tokens.

### M2 · Profile and memory

| Module | What it does | Techniques / libraries | Azure |
| --- | --- | --- | --- |
| Profile (from backend) | Allergies, diet, dislikes, default servings arrive in every request | Hard constraints in the prompt + code post-check | Backend's DB |
| Checkpointer | Saves graph state per run; enables resume and replay for debugging | `langgraph-checkpoint-postgres` (`PostgresSaver`) | PostgreSQL Flexible Server |
| Memory store | Learned preferences per user, e.g. "less oil", "has an air fryer" | LangGraph Store (`PostgresStore` + pgvector), namespace `(user_id, "prefs")`; LangMem for extraction | Same Postgres |
| `load_context` | Reads the profile and top-k preferences before research | Semantic search over the store | — |
| Memory writer | Extracts preferences from `/v1/feedback` (the user's own words only), dedupes, timestamps | Background task; schema-bound extraction | — |
| Memory API | User can list and delete what was learned | CRUD endpoints | — |

**Done when:** a set of dishes that normally contain each declared allergen returns zero recipes with that allergen; a stated preference changes the next recipe; deleting it removes the effect.

Think of the profile as the allergy card stapled to every order ticket, and memory as the waiter's notes about a regular. The card is never optional; the notes are a bonus. If the app's settings screen already captures everything users care about, keep learned memory minimal. M2 needs a stable `user_id` from the backend; an anonymous device ID is enough until accounts exist.

### M3 · Knowledge base (RAG)

| Module | What it does | Techniques / libraries | Azure |
| --- | --- | --- | --- |
| `ingest/` (offline) | Load datasets → clean → dedupe → normalize units → index | pandas, ingredient parsing, `pint` for units, MinHash or embedding dedupe | Container Apps Job or a local script |
| Embeddings | Vectors for title, aliases and ingredients | `text-embedding-3-small` | Foundry |
| Index | One document per recipe: title, aliases (incl. Chinese), cuisine, ingredients, steps, source, license | Index schema; hybrid query + semantic ranker | Azure AI Search |
| `kb_retrieve` | Rewrites the query with aliases; hybrid top-5 | Query rewriting, reciprocal rank fusion | — |
| `grade` | Decides whether the top hit is the same dish; routes to KB or web | LLM grader with a threshold (corrective-RAG pattern) | — |
| Write-back | Validated web recipes saved as candidates with provenance; promoted only after checks | Dedupe; source and license fields; model output is never trusted as a source | Separate AI Search index |
| `evals/retrieval` | Recall@5 and MRR on 50 labeled queries; answer quality vs. M1 | Offline eval script | — |

**Done when:** you set a recall target after the first eval run and meet it; KB hits skip web search; cost and latency per request drop measurably vs. M1.

Candidate sources, each to be checked for license before indexing: TheMealDB, the Wikibooks Cookbook, RecipeNLG, and your own validated M1 outputs. USDA FoodData Central helps with ingredient densities for unit conversion. RAG adds little for brand-new or very obscure dishes; those still fall through to web search.

### M4 · YouTube URL → video-faithful recipe

| Module | What it does | Techniques / libraries | Azure |
| --- | --- | --- | --- |
| `api/jobs` | `POST /v1/jobs` → 202; status polling; idempotent by `request_id` | Job table; queue; worker scales on queue length (KEDA) | Storage Queue, Container Apps |
| `video_evidence` tier 1 | Title, description, chapters, duration | YouTube Data API v3 `videos.list` | API key in Key Vault |
| Tier 2 | Recipe page linked in the description | Fetch with allowlist, size and time limits; schema.org `Recipe` JSON-LD parsing (e.g. `recipe-scrapers`) | — |
| Tier 3 | Transcript when officially available | Skip when unavailable; never scrape around blocks | — |
| Tier 4 | Video understanding when text is thin | Gemini with the public URL (non-Azure exception) or a user-uploaded video → frames → Azure model | Optional |
| Evidence merge | Timestamped evidence; step order and timings follow the video | Evidence IDs and a conflict list, per the repo's W1.1 contract | — |
| Cache | Same `video_id` + prompt version → reuse the result | Postgres table keyed by video ID | Postgres |

**Done when:** a 20-video set (recipe in description, linked page only, talk-only, music-only) yields recipes whose step order matches the video; cost and latency per tier are recorded; a repeat request for the same video returns from cache in under 1 s.

## Security checklist by milestone

The biggest risk here is not hackers breaking in; it's untrusted web and video text steering the model, and one user's data reaching another.

| Milestone | Control | Why |
| --- | --- | --- |
| M1 | Agent ingress internal-only; backend is the single public entry | Nobody can call the paid agent directly |
| M1 | Secrets in Key Vault, read via managed identity; nothing in code, Git or the app | Matches the repo's existing key rule |
| M1 | Rate limits and input limits (length, URL allowlist) at the backend | Caps cost from abuse or bugs |
| M1 | Web content passed as quoted data; the model has no write or send tools | Limits what a prompt injection can do |
| M1 | Every output validated against the schema; citations shown in the app | Catches malformed output; meets Bing's display terms |
| M2 | Every store read and write scoped by `user_id` namespace | Stops cross-user leaks |
| M2 | Memory written only from the user's own feedback, never from web or video text | Prevents memory poisoning |
| M2 | Allergen post-check in code + "check labels" note; no medical advice | Safety net beyond the prompt; matches repo scope |
| M3 | Provenance and license on every KB document; writes only through `ingest/` | Keeps the KB auditable |
| M3 | Screen ingested documents with Azure AI Content Safety Prompt Shields | Catches injected instructions hidden in recipes |
| M4 | Link fetcher blocks private IP ranges, non-HTTPS schemes, large or slow responses | Prevents server-side request forgery |
| M4 | Per-user job quotas; YouTube key server-side only | Video tiers are the expensive path |

## Start here: the first five working days

Goal for the week: a deployed M1 endpoint your teammate can call, plus measured cost and latency. Put the agent code in its own top-level folder (e.g. `agent/`), next to the existing `backend/`.

**Day 1 · Contract and Azure**

- [ ] 30 minutes with your teammate: agree contract v0 (above) and who owns which endpoint
- [ ] Write `schemas.py` plus three example JSONs: success, rejected, error
- [ ] Create a resource group, Foundry project, Key Vault and App Insights in one region
- [ ] Deploy a mini and a nano chat model; pick a region where both and the `web_search` tool are available
- [ ] Smoke script: one Responses API call with `web_search` for "tomato egg stir-fry recipe" prints a cited answer

**Day 2 · Graph on your laptop**

- [ ] LangGraph M1 graph: classify → web\_research → synthesize → validate
- [ ] Run 10 dish names from a CLI; save each input, raw model output and final JSON to files

**Day 3 · Service and tests**

- [ ] FastAPI wrapper with a `MOCK=1` mode that returns the example JSON
- [ ] pytest: schema validity, rejection of non-food input, allergen check, retry cap

**Day 4 · Deploy**

- [ ] Dockerfile; deploy with `az containerapp up`; internal ingress + API key from Key Vault
- [ ] Confirm traces in App Insights; hand the URL and key to your teammate

**Day 5 · Measure**

- [ ] Run the 20-dish eval; record p50 and p95 latency, tokens, search count and cost per run
- [ ] Write results and decisions into PROJECT.md so the repo matches reality

## Open questions for you and your teammate

- [ ] Which plan is current: this one (LangGraph, Azure, dish name, YouTube) or the repo's (OpenAI Agents API, text / image / video, TikTok and Bilibili, laptop server, V1 on Oct 31)?
- [ ] Where does the backend run? In the same Container Apps environment, the agent can stay internal-only.
- [ ] Does the repo's `backend/` pipeline (extract → prepare → analyze) move into the agent service?
- [ ] User identity for M2: anonymous device ID now, accounts later?
- [ ] Output language and units: the repo contract says English, US units and °F. Is that right for your users?
- [ ] Monthly budget cap (the repo still lists it as undecided). It decides model size and how often web search runs.

## Sources

- Project repo: [DishRecipes\_Generator](https://github.com/QVQQQ0722/DishRecipes_Generator) (PROJECT.md, ARCHITECTURE.md, MILESTONES.md, RECIPE\_CONTRACT.md, AGENTS\_API\_ASSESSMENT.md)
- [Host LangGraph agents as Foundry hosted agents](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/langchain-hosted-agents)
- [Foundry Agent Service at Build 2026](https://devblogs.microsoft.com/foundry/agent-service-build2026/)
- [Choosing the right Azure hosting model for AI agents](https://devblogs.microsoft.com/all-things-azure/hostedagent/)
- [Foundry Agent Service pricing](https://azure.microsoft.com/en-us/pricing/details/foundry-agent-service/)
- [Foundry Agent Service limits and regions](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/limits-quotas-regions)
- [Web search with the Responses API](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/web-search)
- [Web grounding overview in Foundry](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/web-overview)
- [Grounding with Bing pricing](https://www.microsoft.com/en-us/bing/apis/grounding-pricing)
- [Memory in Foundry Agent Service](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/what-is-memory) and [memory how-to](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/memory-usage)
- [Azure Container Apps billing](https://learn.microsoft.com/en-us/azure/container-apps/billing)
- [Azure AI Search tiers](https://learn.microsoft.com/en-us/azure/search/search-sku-tier) and [limits](https://learn.microsoft.com/en-us/azure/search/search-limits-quotas-capacity)
- [Azure OpenAI pricing, Oct 2026](https://benchlm.ai/azure/llm-pricing) (third-party summary)
- YouTube Data API: [videos.list](https://developers.google.com/youtube/v3/docs/videos/list), [captions.download](https://developers.google.com/youtube/v3/docs/captions/download)
- [Why transcript tools fail from cloud servers](https://transcriptfetch.com/blog/youtube-transcript-api-not-working-in-production)
- [Gemini API video understanding](https://ai.google.dev/gemini-api/docs/video-understanding)
