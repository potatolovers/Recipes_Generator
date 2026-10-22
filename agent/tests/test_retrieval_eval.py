"""Retrieval eval: the cases file, the scoring math and the query each combination sends. No network."""

import json

from evals import run_retrieval_eval as retrieval

SOURCES = ("howtocook:", "themealdb:", "wikibooks:")


def test_cases_file_is_well_formed():
    cases = json.loads(retrieval.CASES.read_text(encoding="utf-8"))
    rows = retrieval.load_queries(cases)
    texts = [row["text"] for row in rows]
    assert len(texts) == len(set(texts)) >= 50  # one row per query text, no repeats
    for case in cases:
        assert case["expect"] and all(recipe_id.startswith(SOURCES) for recipe_id in case["expect"])
        assert set(case["queries"]) <= set(retrieval.GROUPS)


def test_scores_count_the_first_right_recipe():
    assert retrieval.first_right(["a", "b", "c"], ["c", "b"]) == 2
    assert retrieval.first_right(["a"], ["z"]) is None
    summary = retrieval.summarize([1, 3, None, 2])
    assert (summary["hit@1"], summary["hit@3"]) == (0.25, 0.75)
    assert abs(summary["mrr"] - (1 + 1 / 3 + 1 / 2) / 4) < 1e-9


class FakeSearch:
    def __init__(self):
        self.calls = []

    def hybrid(self, text, vector, top, select, vector_fields):
        self.calls.append((text, tuple(vector_fields), top))
        return [{"id": "wikibooks:Other", "title": "Other"}, {"id": "howtocook:x", "title": "X", "title_zh": "某菜"}]


def test_each_combination_sends_its_own_parts():
    rows = retrieval.load_queries([{"dish": "x", "queries": {"name": ["某菜"]}, "expect": ["howtocook:x"]}])
    search = FakeSearch()
    results = retrieval.run(search, rows, [[0.1]], top=10)
    sent = dict(zip(retrieval.COMBINATIONS, search.calls))
    assert sent["keyword"] == ("某菜", (), 10)
    assert sent["content vector"] == (None, ("content_vector",), 10)
    assert sent["keyword + both vectors"] == ("某菜", ("name_vector", "content_vector"), 10)
    row = results["keyword"][0]
    assert (row["rank"], row["top3"]) == (2, ["Other", "某菜"])
    assert retrieval.misses(results["keyword"], 1) == ["  某菜  [name]  first right at 2; got Other / 某菜"]
    assert retrieval.misses(results["keyword"], 3) == []
