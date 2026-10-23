"""Looks the dish up in the recipe knowledge base (M2): its English name against name_vector, top 3.

Name-vector search alone did best in the retrieval eval (evals/run_retrieval_eval.py): a right recipe
in the top 3 for all 41 English dish names; adding keyword search or content_vector made it worse.
When the knowledge base isn't configured, or the embedding or search call fails, there are no
candidates and the request continues with web search: the knowledge base never fails a request.
"""

import json
import logging

from langchain_core.runnables import RunnableConfig

from app.graph.state import State, kb_of, llm_of, record
from app.llm import ModelFailure
from app.search import SearchFailure

TOP = 3
FIELDS = "id,source,title,title_en,url,servings,description,cooking_method,ingredients,steps,notes"
log = logging.getLogger(__name__)


def kb_retrieve(state: State, config: RunnableConfig):
    kb = kb_of(config)
    if kb is None:
        return {"candidates": []}
    name = state["classification"].normalized_name
    try:
        vector = llm_of(config).embed([name])[0]
        hits = kb.hybrid(None, vector, TOP, FIELDS, vector_fields=("name_vector",))
    except (ModelFailure, SearchFailure) as exc:
        log.warning("knowledge-base search skipped, using web search: %s", exc.message)
        record(config, "03_kb_retrieve.json", json.dumps({"query": name, "error": exc.message}, indent=2))
        return {"candidates": []}
    record(config, "03_kb_retrieve.json", json.dumps(
        {"query": name, "hits": [{"id": hit["id"], "score": hit.get("@search.score")} for hit in hits]},
        ensure_ascii=False, indent=2))
    return {"candidates": hits}
