"""Wikibooks Cookbook (en.wikibooks.org): English recipes written by volunteers. CC BY-SA 4.0.

Recipe pages carry the {{Recipe summary}} template. Their wikitext is downloaded 50 pages per request
and cached as returned, then cleaned here: links become their text, {{convert}} and {{frac}} become
plain amounts, other templates, files, references and categories are dropped.
"""

import html
import json
import re
import time
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote

from kb.sources.net import get_json
from kb.sources.record import KBRecipe

NAME = "wikibooks"
API = "https://en.wikibooks.org/w/api.php"
LICENSE = "CC BY-SA 4.0 (Wikibooks Cookbook): credit the page; adaptations must share alike"
BATCH = 50

HEADING = re.compile(r"^(={2,6})\s*(.+?)\s*\1\s*$", re.M)
TEMPLATE = re.compile(r"\{\{([^{}]*)\}\}")
SPECIAL_LINK = re.compile(r"\[\[\s*(?:File|Image|Category)\s*:(?:[^\[\]]|\[\[[^\[\]]*\]\])*\]\]", re.I)
STEP_WORDS = ("procedure", "direction", "method", "preparation", "instruction", "step")
NOTE_WORDS = ("note", "tip", "variation", "warning", "serving suggestion")
EXACT_KINDS = {"ingredients": "ingredients", "ingredient": "ingredients", "procedure": "steps",
               "procedures": "steps", "directions": "steps", "method": "steps", "instructions": "steps",
               "steps": "steps", "preparation": "steps", "notes": "notes", "tips": "notes",
               "variations": "notes", "warnings": "notes", "notes, tips, and variations": "notes"}
FILE_LINE = re.compile(r"^(File|Image):", re.I)  # gallery lines that escaped their tag


def api(params: dict) -> dict:
    for _ in range(5):
        data = get_json(API, {"action": "query", "format": "json", "formatversion": "2", "maxlag": "5", **params})
        error = data.get("error")
        if error and error.get("code") == "maxlag":
            time.sleep(5)
            continue
        if error:
            raise RuntimeError(f"Wikibooks API error: {error.get('info', error)}")
        return data
    raise RuntimeError("Wikibooks stayed busy (maxlag); try again later")


def list_all(params: dict, key: str) -> Iterator[dict]:
    cont: dict = {}
    while True:
        data = api({**params, **cont})
        yield from data.get("query", {}).get(key, [])
        if "continue" not in data:
            return
        cont = data["continue"]


def list_titles() -> list[str]:
    titles = {page["title"] for page in list_all(
        {"list": "embeddedin", "eititle": "Template:Recipe summary", "eilimit": "500"}, "embeddedin")}
    if not titles:  # fallback if the template is ever renamed
        titles = {page["title"] for page in list_all(
            {"list": "categorymembers", "cmtitle": "Category:Recipes", "cmlimit": "500", "cmtype": "page"},
            "categorymembers")}
    return sorted(title for title in titles if title.startswith("Cookbook:"))


def fetch(raw_dir: Path, refresh: bool = False) -> str:
    titles_path = raw_dir / "_titles.json"
    if refresh or not titles_path.exists():
        print("  listing recipe pages...")
        titles_path.write_text(json.dumps(list_titles(), ensure_ascii=False, indent=0), encoding="utf-8")
    titles = json.loads(titles_path.read_text("utf-8"))
    batches = range(0, len(titles), BATCH)
    downloaded = 0
    for number, start in enumerate(batches):
        target = raw_dir / f"pages_{number:03d}.json"
        if target.exists() and not refresh:
            continue
        pages: dict[str, str] = {}
        cont: dict = {}
        while True:
            data = api({"prop": "revisions", "rvprop": "content", "rvslots": "main",
                        "titles": "|".join(titles[start:start + BATCH]), **cont})
            for page in data["query"]["pages"]:
                if page.get("revisions"):
                    pages[page["title"]] = page["revisions"][0]["slots"]["main"]["content"]
            if "continue" not in data:
                break
            cont = data["continue"]
        target.write_text(json.dumps([{"title": t, "wikitext": w} for t, w in pages.items()], ensure_ascii=False),
                          encoding="utf-8")
        downloaded += 1
        if downloaded % 10 == 0:
            print(f"  {downloaded}/{len(batches)} batches downloaded")
    return f"{len(titles)} recipe pages in {len(batches)} batches, {downloaded} newly downloaded"


def items(raw_dir: Path) -> Iterator[tuple[str, str]]:
    titles = json.loads((raw_dir / "_titles.json").read_text("utf-8"))
    for number in range((len(titles) + BATCH - 1) // BATCH):
        path = raw_dir / f"pages_{number:03d}.json"
        if path.exists():
            for page in json.loads(path.read_text("utf-8")):
                yield page["title"], page["wikitext"]


def to_recipe(item: tuple[str, str]) -> KBRecipe:
    return from_wikitext(*item)


def from_wikitext(title: str, wikitext: str) -> KBRecipe:
    text = re.sub(r"<!--.*?-->", "", wikitext, flags=re.S)
    text = re.sub(r"<ref[^>/]*/>|<ref[^>]*>.*?</ref>|<gallery[^>]*>.*?</gallery>", "", text, flags=re.S | re.I)
    summary = template_params(text, "recipe summary")
    head, parts = blocks(text)
    ingredients, steps, notes = [], [], []
    for kind, label, body in parts:
        if kind == "ingredients":
            ingredients += list_items(body, label)
        elif kind == "steps":
            steps += step_items(body, label)
        else:
            notes += list_items(body, label, prose=True)
    if summary.get("time"):
        notes.insert(0, f"Time: {summary['time']}")
    name = title.removeprefix("Cookbook:")
    category = re.sub(r"\s*recipes?$", "", summary.get("category", ""), flags=re.I) or None
    return KBRecipe(
        id=f"{NAME}:{name}", source=NAME, title=name, language="en", title_en=name,
        url="https://en.wikibooks.org/wiki/" + quote(title.replace(" ", "_"), safe=":/"), license=LICENSE,
        ingredients=ingredients, steps=steps, description=lead(head), cuisine=summary.get("cuisine"),
        category=category, servings=summary.get("servings") or summary.get("yield"), notes=notes,
    )


def section_kind(name: str, top_level: bool) -> str | None:
    """Top-level headings match loosely ("Notes, tips, and variations"); sub-headings only by exact name, so
    "=== Sauce preparation ===" under Ingredients stays an ingredient group."""
    name = name.strip().lower()
    if not top_level:
        return EXACT_KINDS.get(name)
    if "ingredient" in name:
        return "ingredients"
    if any(word in name for word in STEP_WORDS):
        return "steps"
    if any(word in name for word in NOTE_WORDS):
        return "notes"
    return None


def blocks(text: str) -> tuple[str, list[tuple[str, str, str]]]:
    """(kind, label, body) for each stretch between headings, plus the text before the first heading.

    A heading that names a kind starts it at any level: some pages nest "=== Procedure ===" under
    Ingredients. Other sub-headings ("=== Dressing ===") label the items of the current kind; other
    top-level headings ("External links") end it.
    """
    headings = list(HEADING.finditer(text))
    if not headings:
        return text, []
    top = min(len(m.group(1)) for m in headings)
    out, kind, label = [], None, ""
    for i, m in enumerate(headings):
        found = section_kind(m.group(2), len(m.group(1)) == top)
        if found:
            kind, label = found, ""
        elif len(m.group(1)) == top:
            kind, label = None, ""
        else:
            label = clean(m.group(2))
        if kind:
            out.append((kind, label, text[m.end():headings[i + 1].start() if i + 1 < len(headings) else len(text)]))
    return text[:headings[0].start()], out


def list_items(body: str, label: str = "", prose: bool = False) -> list[str]:
    """List lines (* # : ;) and table rows, each prefixed with the block's label ("Dressing: ...")."""
    items, row = [], []

    def add(text: str):
        if text and not FILE_LINE.match(text):
            items.append(f"{label}: {text}" if label else text)

    def flush_row():
        add(" ".join(cell for cell in (clean(table_cell(cell)) for cell in row) if cell))
        row.clear()

    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(("{|", "|}", "|-", "|+")):
            flush_row()
        elif line.startswith("!"):
            continue  # table header row
        elif line.startswith("|"):
            row.extend(line[1:].split("||"))
        elif line[0] in "*#:;":
            add(clean(line.lstrip("*#:;")))
        elif prose:
            add(clean(line))
    flush_row()
    return items


def table_cell(cell: str) -> str:
    """Drops cell formatting: in 'colspan="5" style="…" | Dough' only the part after the last | is shown."""
    cell = strip_links(expand_templates(cell))
    return cell.rsplit("|", 1)[1] if "|" in cell else cell


def step_items(body: str, label: str = "") -> list[str]:
    """# lines are steps (* lines when there are none); deeper levels are notes on the step above."""
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    numbered = any(line.startswith("#") for line in lines)
    bulleted = any(line.startswith("*") for line in lines)
    steps: list[str] = []
    for line in lines:
        marker = re.match(r"^[*#:;]+", line)
        depth = len(marker.group(0)) if marker else 0
        text = clean(line[depth:])
        if not text or FILE_LINE.match(text):
            continue
        if (depth == 1 and (line[0] == "#" or not numbered)) or (depth == 0 and not numbered and not bulleted):
            steps.append(text)
        elif depth and steps:
            steps[-1] += f"\n  - {text}"
    return [f"[{label}]", *steps] if label and steps else steps


def lead(head: str) -> str | None:
    """First real paragraph before the first heading, skipping the navigation line."""
    for paragraph in re.split(r"\n\s*\n", head):
        text = clean(paragraph)
        if len(text) >= 20 and "|" not in text:
            return text[:600]
    return None


def find_template(text: str, name: str) -> str | None:
    match = re.search(r"\{\{\s*" + re.escape(name) + r"\s*(\||\}\})", text, re.I)
    if not match:
        return None
    depth, i = 0, match.start()
    while i < len(text):
        if text.startswith("{{", i):
            depth, i = depth + 1, i + 2
        elif text.startswith("}}", i):
            depth, i = depth - 1, i + 2
            if depth == 0:
                return text[match.start() + 2:i - 2]
        else:
            i += 1
    return None


def template_params(text: str, name: str) -> dict[str, str]:
    inner = find_template(text, name)
    if inner is None:
        return {}
    params = {}
    for part in strip_links(inner).split("|")[1:]:
        key, sep, value = part.partition("=")
        if sep and clean(value):
            params[key.strip().lower()] = clean(value)
    return params


def strip_links(text: str) -> str:
    text = SPECIAL_LINK.sub("", text)
    text = re.sub(r"\[\[([^\[\]|]*)\|([^\[\]]*)\]\]", r"\2", text)
    return re.sub(r"\[\[([^\[\]|]*)\]\]", lambda m: m.group(1).split("#")[0].split(":")[-1], text)


def expand_template(match: re.Match) -> str:
    name, *args = [part.strip() for part in strip_links(match.group(1)).split("|")]
    args = [arg for arg in args if "=" not in arg]  # positional arguments only
    name = name.lower()
    if name in ("convert", "cvt") and len(args) >= 2:
        if len(args) >= 4 and args[1] in ("-", "–", "to", "and", "or"):
            return f"{args[0]}–{args[2]} {args[3]}"
        return f"{args[0]} {args[1]}"
    if name == "frac" and args:  # {{frac|2}} = 1/2, {{frac|1|2}} = 1/2, {{frac|1|1|2}} = 1 1/2
        if len(args) == 1:
            return f"1/{args[0]}"
        return f"{args[0]} {args[1]}/{args[2]}" if len(args) >= 3 else f"{args[0]}/{args[1]}"
    if name in ("nowrap", "nobr", "small", "w", "nw", "lang") and args:
        return args[-1]
    return ""


def expand_templates(text: str) -> str:
    for _ in range(5):  # innermost templates first, so nested ones resolve
        expanded = TEMPLATE.sub(expand_template, text)
        if expanded == text:
            break
        text = expanded
    return text


def clean(text: str) -> str:
    text = strip_links(expand_templates(text))
    text = re.sub(r"\[https?://[^\s\]]+\s+([^\]]+)\]", r"\1", text)
    text = re.sub(r"\[https?://[^\]]+\]", "", text)
    text = text.replace("'''", "").replace("''", "")
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return re.sub(r"\s+", " ", text).strip()
