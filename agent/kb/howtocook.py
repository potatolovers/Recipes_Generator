"""HowToCook (github.com/Anduin2017/HowToCook): Chinese home recipes, one Markdown file per dish.

Unlicense (public domain). Every file has the same four sections: 必备原料和工具 (what to buy),
计算 (amounts), 操作 (steps) and 附加内容 (notes). Downloads are pinned to one commit.
"""

import hashlib
import json
import re
from collections.abc import Iterator
from datetime import date
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from kb.net import get_json, get_text
from kb.record import KBRecipe

NAME = "howtocook"
REPO = "Anduin2017/HowToCook"
LICENSE = "Unlicense (public domain)"

SECTION = re.compile(r"^##\s+(.+?)\s*$", re.M)
BULLET = re.compile(r"^(\s*)[*+-]\s+(.*)$")
NUMBERED = re.compile(r"^(\s*)\d+[.、)](?!\d)\s*(.*)$")
NUMERAL = re.compile(r"[0-9一二两三四五六七八九十]")
BOILERPLATE = ("如果您遵循本指南", "Pull request")


def fetch(raw_dir: Path, refresh: bool = False) -> str:
    commit = get_json(f"https://api.github.com/repos/{REPO}/commits/master")["sha"]
    tree = get_json(f"https://api.github.com/repos/{REPO}/git/trees/{commit}", {"recursive": "1"})
    blobs = {item["path"]: item["sha"] for item in tree["tree"]
             if item["type"] == "blob" and item["path"].startswith("dishes/")
             and item["path"].endswith(".md") and not item["path"].startswith("dishes/template/")}
    downloaded = 0
    for path, sha in sorted(blobs.items()):
        target = raw_dir / path
        if not refresh and target.exists() and git_blob_sha(target.read_bytes()) == sha:
            continue  # already have this exact version
        target.parent.mkdir(parents=True, exist_ok=True)
        text = get_text(f"https://raw.githubusercontent.com/{REPO}/{commit}/{quote(path)}")
        target.write_text(text, encoding="utf-8", newline="")
        downloaded += 1
        if downloaded % 100 == 0:
            print(f"  {downloaded} files downloaded")
    (raw_dir / "_meta.json").write_text(json.dumps({"commit": commit, "fetched": date.today().isoformat(), "blobs": blobs},
                                    ensure_ascii=False, indent=1), encoding="utf-8")
    return f"{len(blobs)} recipe files at commit {commit[:7]}, {downloaded} newly downloaded"


def git_blob_sha(content: bytes) -> str:
    """The id Git gives a file's content; equal ids mean the local copy matches the commit."""
    return hashlib.sha1(b"blob %d\0" % len(content) + content).hexdigest()


def items(raw_dir: Path) -> Iterator[tuple[str, str, str]]:
    """Only files in the current commit's list, so dishes removed upstream drop out."""
    meta = json.loads((raw_dir / "_meta.json").read_text("utf-8"))
    for path in sorted(meta["blobs"]):
        yield (raw_dir / path).read_text("utf-8"), path, meta["commit"]


def to_recipe(item: tuple[str, str, str]) -> KBRecipe:
    return parse_markdown(*item)


def parse_markdown(text: str, path: str, commit: str) -> KBRecipe:
    parts = SECTION.split(text)
    head = parts[0]
    sections = {parts[i].strip(): parts[i + 1] for i in range(1, len(parts) - 1, 2)}
    heading = re.search(r"^#\s+(.+?)\s*$", head, re.M)
    title = re.sub(r"的做法$", "", heading.group(1)).strip() if heading else PurePosixPath(path).stem
    amounts = sections.get("计算", "")
    steps, step_notes = parse_steps(sections.get("操作", ""))
    extra = [line for line in plain_lines(sections.get("附加内容", ""))
             if not any(phrase in line for phrase in BOILERPLATE)]
    servings = next((clean(line) for line in amounts.splitlines()
                     if line.strip() and not BULLET.match(line)
                     and ("份" in line or "人" in line) and NUMERAL.search(line)), None)
    return KBRecipe(
        id=f"{NAME}:{path.removeprefix('dishes/').removesuffix('.md')}",
        source=NAME, title=title, language="zh", title_zh=title,
        url=f"https://github.com/{REPO}/blob/{commit}/{quote(path)}", license=LICENSE,
        ingredients=ingredients(amounts, sections.get("必备原料和工具", "")),
        steps=steps, description=description(head), cuisine="Chinese", category=path.split("/")[1],
        servings=servings, notes=step_notes + extra,
    )


def clean(text: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)       # images
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)   # links → their text
    text = text.replace("\\*", "*").replace("**", "").replace("`", "")
    return re.sub(r"\s+", " ", text).strip()


def description(head: str) -> str | None:
    for paragraph in re.split(r"\n\s*\n", head):
        text = clean(paragraph)
        if text and not text.startswith(("#", "预估")):
            return text
    return None


def ingredients(amounts: str, shopping: str) -> list[str]:
    """Amounts from 计算; when it names fewer than two items, add the rest of the shopping list."""
    items = leaf_bullets(amounts)
    if len(items) < 2:
        items += [f"{group}：{item}" if group else item for group, item in shopping_list(shopping)
                  if not any(item in known for known in items)]
    return items


def shopping_list(body: str) -> list[tuple[str, str]]:
    """(### group, item) pairs from 必备原料和工具, leaving out tool groups such as 必备工具."""
    group, out = "", []
    for line in body.splitlines():
        if line.startswith("###"):
            group = clean(line.lstrip("#"))
        elif (match := BULLET.match(line)) and "工具" not in group and clean(match.group(2)):
            out.append((group, clean(match.group(2))))
    return out


def leaf_bullets(body: str) -> list[str]:
    """Bullet items; a bullet with indented children is a group label ("可选配料") put in front of them."""
    entries = [(len(m.group(1).expandtabs(4)), clean(m.group(2)))
               for m in map(BULLET.match, body.splitlines()) if m]
    out, groups = [], {}
    for i, (indent, text) in enumerate(entries):
        if i + 1 < len(entries) and entries[i + 1][0] > indent:
            groups = {depth: label for depth, label in groups.items() if depth < indent}
            groups[indent] = text.rstrip("：:")
            continue
        labels = [label for depth, label in sorted(groups.items()) if depth < indent]
        if text:
            out.append(f"{labels[-1]}：{text}" if labels else text)
    return out


def parse_steps(body: str) -> tuple[list[str], list[str]]:
    """Numbered lines are steps; indented bullets are notes on the step above; ### headings label variants."""
    lines = [line.rstrip() for line in body.splitlines() if line.strip()]
    numbered = any((m := NUMBERED.match(line)) and not m.group(1) for line in lines)
    steps, notes = [], []
    for line in lines:
        if line.startswith("###"):
            steps.append(f"【{clean(line.lstrip('#'))}】")
            continue
        number, bullet = NUMBERED.match(line), BULLET.match(line)
        match = number or bullet
        text = clean(match.group(2) if match else line)
        if not text:
            continue
        if match and not match.group(1) and (number or not numbered):
            steps.append(text)
        elif match and steps:
            steps[-1] += f"\n  - {text}"
        else:
            notes.append(text)
    return steps, notes


def plain_lines(body: str) -> list[str]:
    out = []
    for line in body.splitlines():
        match = BULLET.match(line) or NUMBERED.match(line)
        text = clean(match.group(2) if match else line)
        if text:
            out.append(text)
    return out
