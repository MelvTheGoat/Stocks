"""Build the trace viewer page from one or more results files.

    python scripts/build_trace_viewer.py                      # every run, redacted
    python scripts/build_trace_viewer.py --no-redact          # local only
    python scripts/build_trace_viewer.py --out docs/index.html

GitHub Pages serves the `docs/` folder on the default branch, so the default
output lands where Pages will publish it. Redaction is on by default for exactly
that reason: the traces contain licensed prices and the published page must not.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from stockagent.viewer import build

DEFAULT_INPUT = Path("runs/output")
DEFAULT_OUTPUT = Path("docs/index.html")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=DEFAULT_INPUT,
                        help="a results file, or a directory of them")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--no-redact", action="store_true",
                        help="keep raw figures. Never publish the result.")
    parser.add_argument("--max-questions", type=int,
                        help="cap questions per run, to keep the page small")
    args = parser.parse_args(argv)

    if args.results.is_dir():
        files = sorted(args.results.glob("*-results.json"))
    elif args.results.exists():
        files = [args.results]
    else:
        files = []

    if not files:
        print(f"No results files found in {args.results}.")
        print("Run an eval first, or fetch the results branch:")
        print("  git fetch origin results && git checkout results")
        return 1

    redact = not args.no_redact
    path = build(files, args.out, redact=redact, max_questions=args.max_questions)
    size = path.stat().st_size

    print(f"wrote {path} ({size / 1024:.0f} KB) from {len(files)} run(s)")
    if redact:
        print("Raw figures are masked. Safe to publish.")
    else:
        print("WARNING: raw figures are included. Do not commit or publish this file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
