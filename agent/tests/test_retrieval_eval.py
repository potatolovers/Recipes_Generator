"""Retrieval eval: the cases file, the scoring math and the query each combination sends. No network."""

import json
import re

from evals import run_retrieval_eval as retrieval

SOURCES = ("howtocook:", "themealdb:", "wikibooks:")
CJK = re.compile(r"[　-鿿]")


def test_cases_file_is_well_formed_and_english():
    cases = json.loads(retrieval.CASES.read_text(encoding="utf-8"))
    rows = retrieval.load_queries(cases)
    texts = [row["text"] for row in rows]
    assert len(texts) == len(set(texts)) >= 50  # one row per query text, no repeats
    assert not [text for text in texts if CJK.search(text)]  # written as English-speaking users type
    for case in cases:
        assert set(case["queries"]) <= set(retrieval.GROUPS)
        assert all(recipe_id.startswith(SOURCES) for recipe_id in case["expect"])
        assert bool(case["expect"]) != ("absent" in case["queries"])  # absent dishes have no right recipe


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
        return [{"id": "wikibooks:Other", "title": "Other", "@search.score": 0.7},
                {"id": "howtocook:x", "title": "西红柿炒鸡蛋", "title_en": "Tomato and egg stir-fry"}]


def test_each_combination_sends_its_own_parts():
    cases = [{"dish": "x", "queries": {"name": ["Tomato egg"]}, "expect": ["howtocook:x"]},
             {"dish": "y", "queries": {"absent": ["Cobb salad"]}, "expect": []}]
    search = FakeSearch()
    results = retrieval.run(search, retrieval.load_queries(cases), [[0.1], [0.2]], top=10)
    sent = dict(zip(retrieval.COMBINATIONS, search.calls[::2]))
    assert sent["keyword"] == ("Tomato egg", (), 10)
    assert sent["content vector"] == (None, ("content_vector",), 10)
    assert sent["keyword + both vectors"] == ("Tomato egg", ("name_vector", "content_vector"), 10)
    rows = results["keyword"]
    assert (rows[0]["rank"], rows[0]["top3"]) == (2, ["Other", "Tomato and egg stir-fry"])  # English titles shown
    assert retrieval.scored(rows) == [2]  # absent dishes are not scored
    assert retrieval.misses(rows, 1) == ["  Tomato egg  [name]  first right at 2; got Other / Tomato and egg stir-fry"]
    assert retrieval.absent(rows) == ["  Cobb salad: Other / Tomato and egg stir-fry"]
    assert rows[1]["top_score"] == 0.7
    rows[0]["rank"] = 1
    assert retrieval.score_gap(rows) == ("  right first result: lowest 0.700, median 0.700 (1 queries)\n"
                                         "  absent dishes:      highest 0.700, median 0.700 (1 queries)")
