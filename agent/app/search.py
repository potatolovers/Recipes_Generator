"""Azure AI Search over REST: the recipe knowledge base (M2). Vendor request/response formats stay here.

kb/upload.py creates the index and uploads recipes with the admin key, from a laptop. The deployed agent
only queries, with a read-only query key.
"""

import os
import re

import httpx

API_VERSION = "2024-07-01"  # GA: vector fields, stored=false, hybrid queries
NAME_FIELDS = "title,title_en,title_zh,aliases"  # keyword part of a query looks only at names
VECTOR_FIELDS = ("name_vector", "content_vector")  # names + main method; methods + ingredients + steps
QUERY_OPERATORS = re.compile(r'[+\-|"*()~\\/^:{}\[\]&!]')  # simple-syntax operators, searched as plain text


class SearchFailure(Exception):
    """A safe, caller-visible failure; never include keys."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class AzureSearch:
    def __init__(self, key_setting: str = "AZURE_SEARCH_QUERY_KEY", http: httpx.Client | None = None):
        self.endpoint = os.getenv("AZURE_SEARCH_ENDPOINT", "").strip().rstrip("/")
        self.index = os.getenv("AZURE_SEARCH_INDEX", "").strip() or "recipes-v1"
        key = os.getenv(key_setting, "").strip()
        if not self.endpoint or not key or "<" in self.endpoint:
            raise SearchFailure("SEARCH_CONFIG", f"Set AZURE_SEARCH_ENDPOINT and {key_setting} in agent/.env.")
        self.http = http or httpx.Client(timeout=30)
        self.headers = {"api-key": key}

    def _request(self, method: str, path: str, body: dict | None = None, missing_ok: bool = False) -> dict:
        try:
            response = self.http.request(method, f"{self.endpoint}{path}", params={"api-version": API_VERSION},
                                         headers=self.headers, json=body)
        except httpx.HTTPError as exc:
            raise SearchFailure("SEARCH_UNAVAILABLE", f"Search request failed ({type(exc).__name__}).") from exc
        if missing_ok and response.status_code == 404:
            return {}
        if response.status_code >= 400:
            detail = ""
            if "json" in response.headers.get("content-type", ""):
                detail = response.json().get("error", {}).get("message", "")
            raise SearchFailure("SEARCH_ERROR", f"{method} {path} returned HTTP {response.status_code}. {detail}".strip())
        return response.json() if response.content else {}

    def create_or_update_index(self, schema: dict) -> None:
        self._request("PUT", f"/indexes/{self.index}", {**schema, "name": self.index})

    def delete_index(self) -> None:
        self._request("DELETE", f"/indexes/{self.index}", missing_ok=True)

    def upload(self, documents: list[dict]) -> list[str]:
        """Adds or replaces documents by key; returns one message per document that failed."""
        result = self._request("POST", f"/indexes/{self.index}/docs/index",
                               {"value": [{"@search.action": "upload", **doc} for doc in documents]})
        return [f"{item.get('key')}: {item.get('errorMessage')}" for item in result.get("value", [])
                if not item.get("status")]

    def stats(self) -> dict:
        return self._request("GET", f"/indexes/{self.index}/stats")

    def hybrid(self, text: str | None, vector: list[float], top: int = 3, select: str | None = None,
               filter: str | None = None, vector_fields: tuple[str, ...] = VECTOR_FIELDS) -> list[dict]:
        """Keyword search on the name fields (skipped when text is None) and vector search on each of
        `vector_fields`, fused by reciprocal rank fusion: each list adds 1/(60 + rank) per recipe.
        `filter` is an OData yes/no condition applied before ranking, e.g. "cooking_method eq 'stew'"."""
        if text is None and not vector_fields:
            raise ValueError("search needs text, a vector field, or both")
        body: dict = {"top": top}
        if text is not None:
            body.update(search=" ".join(QUERY_OPERATORS.sub(" ", text).split()) or "*", searchFields=NAME_FIELDS)
        if vector_fields:  # the same query vector is compared with each field
            body["vectorQueries"] = [{"kind": "vector", "vector": vector, "fields": field, "k": 50}
                                     for field in vector_fields]
        if select:
            body["select"] = select
        if filter:
            body["filter"] = filter
        return self._request("POST", f"/indexes/{self.index}/docs/search", body).get("value", [])


def optional_search(timeout: float = 10.0) -> AzureSearch | None:
    """The query-key client when AZURE_SEARCH_ENDPOINT and AZURE_SEARCH_QUERY_KEY are set, else None: the agent
    then skips the knowledge base and uses web search only. A short timeout, since web search is the fallback."""
    try:
        return AzureSearch(http=httpx.Client(timeout=timeout))
    except SearchFailure:
        return None
