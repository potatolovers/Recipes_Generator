"""Recipe index upload and hybrid query against a fake Azure AI Search service. No network, no cost."""

import base64
import json
import re

import httpx
import pytest

from app.llm import EMBED_DIMENSIONS, AzureModelClient
from app.search import API_VERSION, AzureSearch, SearchFailure
from kb import upload

KEY_CHARS = re.compile(r"^[A-Za-z0-9=-][A-Za-z0-9_=-]*$")  # Azure document-key rule


def recipe(n: int) -> dict:
    return {"id": f"howtocook:vegetable_dish/西红柿炒鸡蛋{n}", "source": "howtocook", "language": "zh",
            "title": "西红柿炒鸡蛋", "title_en": "Tomato and egg stir-fry", "title_zh": "西红柿炒鸡蛋",
            "aliases": ["番茄炒蛋"], "ingredients": ["西红柿 = 1 个（约 180g） * 份数", "必须配料：鸡蛋 = 1.5 个"],
            "steps": ["西红柿洗净", "鸡蛋  打散"], "notes": [], "url": "https://github.com/x", "license": "Unlicense",
            "cuisine": "Chinese", "category": "vegetable_dish", "servings": None, "description": None,
            "video_url": None, "cooking_method": "stir_fry", "cooking_methods": ["stir_fry"], "cooking_family": "fry"}


class FakeService:
    """Records requests and answers like Azure AI Search; `fail_key` makes one document fail."""

    def __init__(self, fail_key: str | None = None):
        self.requests, self.fail_key = [], fail_key

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.requests.append((request.method, request.url.path, request.url.params.get("api-version"), body))
        path = request.url.path
        if request.method == "DELETE":
            return httpx.Response(404)
        if path.endswith("/docs/index"):
            return httpx.Response(200, json={"value": [
                {"key": doc["key"], "status": doc["key"] != self.fail_key,
                 "errorMessage": "Document is too large" if doc["key"] == self.fail_key else None}
                for doc in body["value"]]})
        if path.endswith("/docs/search"):
            return httpx.Response(200, json={"value": [{"title": "西红柿炒鸡蛋", "source": "howtocook", "@search.score": 0.03}]})
        if path.endswith("/stats"):
            return httpx.Response(200, json={"documentCount": 250, "storageSize": 21_000_000, "vectorIndexSize": 11_000_000})
        return httpx.Response(201, json=body)


def service(monkeypatch, fake: FakeService) -> AzureSearch:
    monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", "https://shiwei-search.search.windows.net")
    monkeypatch.setenv("AZURE_SEARCH_ADMIN_KEY", "admin-key")
    monkeypatch.delenv("AZURE_SEARCH_INDEX", raising=False)
    return AzureSearch("AZURE_SEARCH_ADMIN_KEY", http=httpx.Client(transport=httpx.MockTransport(fake)))


def fake_embed(calls: list):
    """Vector i is [i, i, ...], so a test can tell which text a stored vector came from."""
    def embed(texts):
        calls.append(texts)
        return [[float(i)] * EMBED_DIMENSIONS for i in range(len(texts))]
    return embed


def test_schema_matches_documents_and_embeddings():
    fields = {spec["name"]: spec for spec in upload.INDEX["fields"]}
    for name in ("name_vector", "content_vector"):
        assert fields[name]["dimensions"] == EMBED_DIMENSIONS == upload.EMBED_DIMENSIONS
        assert fields[name]["stored"] is False and fields[name]["retrievable"] is False
    doc = upload.document(recipe(1), [0.0] * EMBED_DIMENSIONS, [1.0] * EMBED_DIMENSIONS)
    assert set(doc) <= set(fields)  # uploading a field the index lacks is rejected by Azure
    assert doc["notes"] == [] and doc["aliases"] == ["番茄炒蛋"]
    assert (doc["name_vector"][0], doc["content_vector"][0]) == (0.0, 1.0)


def test_name_text_is_every_name_then_the_main_method():
    assert upload.name_text(recipe(1)) == "西红柿炒鸡蛋 | Tomato and egg stir-fry | 番茄炒蛋 | 炒 Stir-fry"
    unlabeled = {**recipe(1), "cooking_method": None, "cooking_methods": []}  # before kb.methods has run
    assert upload.name_text(unlabeled) == "西红柿炒鸡蛋 | Tomato and egg stir-fry | 番茄炒蛋"


def test_content_text_keeps_whole_ingredient_lines_and_trims_long_steps():
    pork = {**recipe(1), "cooking_methods": ["blanch", "red_braise"],
            "ingredients": ["五花肉：1000g", "冰糖：15g"], "steps": ["五花肉切块。", "x" * 3000, "收汁出锅。"]}
    text = upload.content_text(pork)
    assert text.startswith("焯 Blanch, 红烧 Red-braise | 五花肉：1000g; 冰糖：15g | 五花肉切块。")  # nothing stripped
    assert text.endswith("x 收汁出锅。") and " … " in text
    steps = text.split(" | ", 2)[2]
    assert len(steps) == upload.STEPS_CHARS + len(" … ")
    assert upload.content_text(recipe(1)) == ("炒 Stir-fry | 西红柿 = 1 个（约 180g） * 份数; 必须配料：鸡蛋 = 1.5 个 | "
                                              "西红柿洗净 鸡蛋 打散")
    huge = {**pork, "ingredients": ["盐 " * 3000]}
    assert len(upload.content_text(huge)) == upload.CONTENT_CHARS


def test_embedding_calls_stay_under_the_byte_limit_in_order():
    texts = ["a" * 9, "鸡" * 3, "b" * 5, "c" * 30, "d"]  # 鸡 is 3 bytes in UTF-8
    assert upload.call_groups(texts, limit=20) == [["a" * 9, "鸡" * 3], ["b" * 5], ["c" * 30], ["d"]]
    assert upload.call_groups([], limit=20) == []
    calls = []
    vectors = upload.embed_all(fake_embed(calls), texts, Exception)
    assert len(vectors) == len(texts) and sum(map(len, calls)) == len(texts)


def test_document_keys_follow_azure_rules_and_round_trip():
    for recipe_id in ("howtocook:meat_dish/宫保鸡丁/宫保鸡丁", "wikibooks:Macaroni and Cheese (Vegan)", "themealdb:52772"):
        key = upload.doc_key(recipe_id)
        assert KEY_CHARS.match(key)
        assert base64.urlsafe_b64decode(key).decode("utf-8") == recipe_id


def test_upload_batches_and_reports_failures(monkeypatch):
    recipes = [recipe(n) for n in range(250)]
    fake = FakeService(fail_key=upload.doc_key(recipes[7]["id"]))
    calls = []
    result = upload.upload(service(monkeypatch, fake), fake_embed(calls), recipes, recreate=True)
    methods = [(method, path) for method, path, _, _ in fake.requests]
    assert methods[:2] == [("DELETE", "/indexes/recipes-v1"), ("PUT", "/indexes/recipes-v1")]
    assert [len(texts) for texts in calls] == [100] * 5  # one call per 50 recipes: 50 name texts, then 50 content texts
    assert calls[0][0] == upload.name_text(recipes[0]) and calls[0][50] == upload.content_text(recipes[0])
    assert methods.count(("POST", "/indexes/recipes-v1/docs/index")) == 5
    first = fake.requests[2][3]["value"][1]
    assert (first["name_vector"][0], first["content_vector"][0]) == (1.0, 51.0)  # each vector from its own text
    assert {version for _, _, version, _ in fake.requests} == {API_VERSION}
    assert fake.requests[1][3]["name"] == "recipes-v1"
    assert result == {"sent": 250, "failed": [f"{upload.doc_key(recipes[7]['id'])}: Document is too large"]}


def test_hybrid_query_searches_names_and_both_vectors(monkeypatch):
    fake = FakeService()
    hits = service(monkeypatch, fake).hybrid('mac & "cheese" -vegan', [0.2] * EMBED_DIMENSIONS, top=3, select="title")
    body = fake.requests[-1][3]
    assert body["search"] == "mac cheese vegan"  # operators searched as plain text
    assert body["searchFields"] == "title,title_en,title_zh,aliases" and body["top"] == 3
    assert [query["fields"] for query in body["vectorQueries"]] == ["name_vector", "content_vector"]
    assert all(len(query["vector"]) == 512 for query in body["vectorQueries"])
    assert hits[0]["title"] == "西红柿炒鸡蛋"


def test_hybrid_query_can_leave_out_keyword_or_vector_parts(monkeypatch):
    fake = FakeService()
    search = service(monkeypatch, fake)
    search.hybrid(None, [0.2] * EMBED_DIMENSIONS, vector_fields=("content_vector",))
    vector_only = fake.requests[-1][3]
    assert "search" not in vector_only and [q["fields"] for q in vector_only["vectorQueries"]] == ["content_vector"]
    search.hybrid("红烧肉", [0.2] * EMBED_DIMENSIONS, vector_fields=())
    keyword_only = fake.requests[-1][3]
    assert keyword_only["search"] == "红烧肉" and "vectorQueries" not in keyword_only
    with pytest.raises(ValueError):
        search.hybrid(None, [0.2] * EMBED_DIMENSIONS, vector_fields=())


def test_missing_settings_fail_clearly(monkeypatch):
    monkeypatch.delenv("AZURE_SEARCH_ENDPOINT", raising=False)
    with pytest.raises(SearchFailure, match="AZURE_SEARCH_ENDPOINT"):
        AzureSearch()


def test_model_endpoint_is_used_exactly_as_written(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://agent-learn-resource.openai.azure.com/openai/v1")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "dummy")
    monkeypatch.setenv("AGENT_MODEL_CLASSIFY", "gpt-4o")
    monkeypatch.setenv("AGENT_MODEL_MAIN", "gpt-4o")
    # The OpenAI SDK only adds the trailing slash it needs.
    assert str(AzureModelClient().client.base_url) == "https://agent-learn-resource.openai.azure.com/openai/v1/"
