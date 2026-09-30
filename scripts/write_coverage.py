"""Regenerate COVERAGE.md from the database.

Run after any collection: `python scripts/write_coverage.py`
"""

from __future__ import annotations

import sys
from pathlib import Path

from stockagent.data.coverage_report import build_coverage_markdown
from stockagent.data.store import MarketStore
from stockagent.data.universe import NGX_UNIVERSE, US_UNIVERSE, load_universe

DATABASE = Path("data/db")
OUTPUT = Path("COVERAGE.md")

UNIVERSE_FILES = {"US": US_UNIVERSE, "NGX": NGX_UNIVERSE}


def main() -> int:
    # A market with no universe file yet is listed as empty rather than left
    # out. "We hold nothing for the NGX" is the single most important fact
    # about this project's coverage right now, and it has to be visible.
    universes = {
        market: load_universe(path) if Path(path).exists() else []
        for market, path in UNIVERSE_FILES.items()
    }

    store = MarketStore(DATABASE)
    OUTPUT.write_text(build_coverage_markdown(store, universes))

    for market, entries in universes.items():
        print(f"{market}: {len(entries)} securities in the universe")
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
