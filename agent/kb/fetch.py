"""Downloads recipe sources into kb/data/raw/, then builds kb/data/recipes.jsonl.

Run from agent/:
  python -m kb.fetch                  all sources
  python -m kb.fetch themealdb        only the named sources
  python -m kb.fetch --refresh        download again even if files are already there
Downloads resume: files already present are skipped, so re-running after an error is cheap.
"""

import argparse
import sys

from kb import RAW
from kb.build import SOURCES, build


def main(argv: list[str] | None = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="python -m kb.fetch", description=__doc__.splitlines()[0])
    parser.add_argument("sources", nargs="*", metavar="source", help=f"any of: {', '.join(SOURCES)} (default: all)")
    parser.add_argument("--refresh", action="store_true", help="download again even if files are already there")
    args = parser.parse_args(argv)
    unknown = sorted(set(args.sources) - set(SOURCES))
    if unknown:
        parser.error(f"unknown source: {', '.join(unknown)}; choose from {', '.join(SOURCES)}")
    for name in args.sources or SOURCES:
        raw = RAW / name
        raw.mkdir(parents=True, exist_ok=True)
        print(f"{name}: downloading...")
        try:
            print(f"{name}: {SOURCES[name].fetch(raw, args.refresh)}")
        except Exception as exc:  # a blocked or failing source should not stop the others
            print(f"{name}: FAILED, {type(exc).__name__}: {exc}")
    build()


if __name__ == "__main__":
    main()
