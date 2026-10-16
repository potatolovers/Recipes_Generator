"""One knowledge-base recipe, the same shape for every source; one JSON object per line in recipes.jsonl."""

import json
from dataclasses import asdict, dataclass, field


@dataclass
class KBRecipe:
    id: str                  # "<source>:<id in source>", stable across rebuilds
    source: str              # howtocook | themealdb | wikibooks
    title: str               # as the source writes it
    language: str            # zh | en
    url: str                 # page to credit
    license: str
    ingredients: list[str]   # one line each, amounts as written
    steps: list[str]         # in order; "  - " lines are sub-notes of a step, 【…】/[…] entries label a variant
    title_en: str | None = None
    title_zh: str | None = None
    aliases: list[str] = field(default_factory=list)   # filled by a later enrichment step
    description: str | None = None
    cuisine: str | None = None
    category: str | None = None
    servings: str | None = None  # as written, e.g. "按照 1 盘的份量：" or "4"
    notes: list[str] = field(default_factory=list)
    video_url: str | None = None  # TheMealDB links a YouTube video for many meals (useful in M4)

    def problems(self) -> list[str]:
        """Quality gate: a record with problems is not kept."""
        problems = []
        if not self.title.strip():
            problems.append("no title")
        if not self.ingredients:
            problems.append("no ingredients")
        if not self.steps:
            problems.append("no steps")
        return problems

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)
