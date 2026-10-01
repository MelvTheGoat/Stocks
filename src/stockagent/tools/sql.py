"""A read-only SQL tool, with a row limit and a real timeout.

This is the other arm of Experiment B: instead of purpose-built tools, let the
model write queries. It needs three guards, and the reasons differ.

**Read-only** is about the database surviving the experiment. A model that
writes `DELETE FROM bars` during a run would corrupt the very thing the eval
measures against, and the corruption would not be obvious until scores moved.
Guarding by statement kind rather than by file permissions means a single
rejected query costs nothing.

**A row limit** is about tokens. `SELECT * FROM bars` is a hundred thousand rows;
sent to the model it would fill the context and cost more than the whole rest of
the run.

**A timeout** is about a run finishing. A careless join across bars twice over is
easy to write by accident, and a Kaggle session has a wall clock.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass

from stockagent.data.store import MarketStore
from stockagent.tools.base import ToolResult, ToolSpec, require

DEFAULT_ROW_LIMIT = 50
DEFAULT_TIMEOUT_S = 10.0

# Anything that could change the database or reach outside it. Checked as whole
# words so a column called "update_count" is not mistaken for an UPDATE.
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|create|alter|truncate|replace|attach|detach"
    r"|copy|export|import|install|load|pragma|set|call|vacuum|checkpoint)\b",
    re.IGNORECASE,
)

_STARTS_READ_ONLY = re.compile(r"^\s*(select|with|explain|describe|summarize)\b", re.IGNORECASE)

# Functions that read the filesystem. DuckDB exposes these to any query, so a
# read-only statement can still be a file read without them being blocked.
_FILE_FUNCTIONS = re.compile(
    r"\b(read_csv|read_csv_auto|read_parquet|read_json|read_json_auto|read_text"
    r"|read_blob|glob|parquet_scan|csv_scan)\s*\(",
    re.IGNORECASE,
)

SCHEMA_NOTE = """\
Tables available, all read-only:

  bars(ticker, market, day, open, high, low, close, adjusted_close, volume, currency, source)
  dividends(ticker, market, ex_date, amount, currency, source, declared_on, record_date, paid_on)
  actions(ticker, market, effective_date, factor, kind, source)   kind is 'split' or 'bonus'
  securities(ticker, market, name, currency)
  aliases(ticker, market, text, kind, until)                      former names and tickers

Notes that matter:
  adjusted_close is usually NULL; prices are as quoted, so apply actions.factor yourself.
  A price before a split must be divided by the factor to compare it with a later one.
  market is 'US' or 'NGX', and currencies must never be mixed across markets.
"""


def strip_comments(sql: str) -> str:
    """Remove SQL comments before checking, so nothing hides inside one."""
    without_block = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", " ", without_block)


def check_read_only(sql: str) -> str | None:
    """The reason a query is refused, or None if it is acceptable."""
    bare = strip_comments(sql).strip().rstrip(";").strip()
    if not bare:
        return "the query is empty"
    # Several statements in one string is how a guard on the first one gets
    # bypassed, so anything after a semicolon is refused outright.
    if ";" in bare:
        return "only one statement is allowed; remove the semicolon"
    if not _STARTS_READ_ONLY.match(bare):
        return "only SELECT, WITH, EXPLAIN, DESCRIBE and SUMMARIZE queries are allowed"
    found = _FORBIDDEN.search(bare)
    if found:
        return f"the keyword {found.group(0).upper()} is not allowed in a read-only query"
    reader = _FILE_FUNCTIONS.search(bare)
    if reader:
        return f"{reader.group(1)} reads files and is not allowed"
    return None


def add_limit(sql: str, limit: int) -> str:
    """Bound the result even when the query forgot to."""
    bare = strip_comments(sql).strip().rstrip(";").strip()
    if re.search(r"\blimit\s+\d+\s*$", bare, re.IGNORECASE):
        return bare
    # A subquery's own LIMIT does not bound the outer result, so wrapping is the
    # only reliable way to cap what comes back.
    return f"SELECT * FROM ({bare}) AS bounded LIMIT {limit}"


@dataclass
class SqlTool:
    store: MarketStore
    row_limit: int = DEFAULT_ROW_LIMIT
    timeout_s: float = DEFAULT_TIMEOUT_S

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="run_sql",
            description=(
                "Run one read-only SQL query against the market database and get the rows "
                f"back. At most {self.row_limit} rows are returned. Only SELECT and WITH "
                "queries are allowed.\n\n" + SCHEMA_NOTE
            ),
            parameters={"sql": {"type": "string", "description": "a single SELECT query"}},
            required=("sql",),
        )

    def run(self, **arguments) -> ToolResult:
        (sql,) = require(arguments, "sql")
        sql = str(sql)

        refusal = check_read_only(sql)
        if refusal:
            return ToolResult.failure(f"refused: {refusal}")

        bounded = add_limit(sql, self.row_limit)
        connection = self.store.connect()

        # DuckDB has no statement timeout setting, so the query is interrupted
        # from another thread. Without this a runaway join ends the whole run
        # rather than one tool call.
        timer = threading.Timer(self.timeout_s, connection.interrupt)
        timer.start()
        try:
            cursor = connection.execute(bounded)
            columns = [description[0] for description in cursor.description or []]
            rows = cursor.fetchall()
        except Exception as error:  # noqa: BLE001 - any failure becomes a tool result
            detail = str(error).strip()
            message = detail.splitlines()[0] if detail else type(error).__name__
            return ToolResult.failure(f"the query failed: {message}")
        finally:
            timer.cancel()
            connection.close()

        if not rows:
            return ToolResult.success(
                "the query returned no rows, which means the database holds nothing "
                "matching those conditions",
                sources=("sql",),
                rows=0,
            )

        header = " | ".join(columns)
        body = "\n".join(" | ".join("NULL" if v is None else str(v) for v in row) for row in rows)
        note = (
            f"\n({len(rows)} rows, capped at {self.row_limit}; narrow the query to see more)"
            if len(rows) >= self.row_limit
            else f"\n({len(rows)} rows)"
        )
        return ToolResult.success(f"{header}\n{body}{note}", sources=("sql",), rows=len(rows))
