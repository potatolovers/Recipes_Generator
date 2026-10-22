"""M0 check, run from agent/: python -m app.smoke — one web_search call, prints a cited answer."""

import sys

from app.llm import AzureModelClient

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
reply = AzureModelClient().search("main", "Answer briefly and cite your sources.", "tomato egg stir-fry recipe")
print(reply.text)
for source in reply.sources:
    print(f"[{source.id}] {source.title} — {source.url}")
print(f"searches={reply.search_requests} input_tokens={reply.input_tokens} output_tokens={reply.output_tokens}")
