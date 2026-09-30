"""One database for both markets.

Parquet files on disk, DuckDB for reading them. That split is deliberate:
Parquet files are plain, portable and easy to push to Hugging Face, while
DuckDB gives real SQL over them with no server to run. The agent's SQL tool in
Phase 7 needs the second, and the Kaggle runner needs the first.

Writes are merges, not appends. The daily collector will re-run over days it
has already seen, a Kaggle session will be killed halfway and started again,
and a backfill will overlap whatever is already there. Every write deduplicates
on the record's natural key, so running the same collection twice leaves the
database exactly as running it once did.

Aliases live in their own table rather than nested inside securities, because
the thing that needs them -- resolving "Guaranty Trust Bank" to GTCO -- is a
lookup, and a lookup wants a flat table.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from stockagent.data.models import Bar, CorporateAction, Dividend, Security

_DATE = pa.date32()
_STR = pa.string()
_F64 = pa.float64()

BAR_SCHEMA = pa.schema(
    [
        ("ticker", _STR),
        ("market", _STR),
        ("day", _DATE),
        ("open", _F64),
        ("high", _F64),
        ("low", _F64),
        ("close", _F64),
        ("adjusted_close", _F64),
        ("volume", pa.int64()),
        ("currency", _STR),
        ("source", _STR),
    ]
)

DIVIDEND_SCHEMA = pa.schema(
    [
        ("ticker", _STR),
        ("market", _STR),
        ("ex_date", _DATE),
        ("amount", _F64),
        ("currency", _STR),
        ("source", _STR),
        ("declared_on", _DATE),
        ("record_date", _DATE),
        ("paid_on", _DATE),
    ]
)

ACTION_SCHEMA = pa.schema(
    [
        ("ticker", _STR),
        ("market", _STR),
        ("effective_date", _DATE),
        ("factor", _F64),
        ("kind", _STR),
        ("source", _STR),
    ]
)

SECURITY_SCHEMA = pa.schema(
    [("ticker", _STR), ("market", _STR), ("name", _STR), ("currency", _STR)]
)

ALIAS_SCHEMA = pa.schema(
    [("ticker", _STR), ("market", _STR), ("text", _STR), ("kind", _STR), ("until", _DATE)]
)


@dataclass(frozen=True)
class TableSpec:
    name: str
    schema: pa.Schema
    # The columns that make a row unique. A second write of the same key
    # replaces the first rather than adding a duplicate.
    key: tuple[str, ...]


TABLES: dict[str, TableSpec] = {
    "bars": TableSpec("bars", BAR_SCHEMA, ("market", "ticker", "day", "source")),
    "dividends": TableSpec(
        "dividends", DIVIDEND_SCHEMA, ("market", "ticker", "ex_date", "source")
    ),
    "actions": TableSpec(
        "actions", ACTION_SCHEMA, ("market", "ticker", "effective_date", "kind", "source")
    ),
    "securities": TableSpec("securities", SECURITY_SCHEMA, ("market", "ticker")),
    "aliases": TableSpec("aliases", ALIAS_SCHEMA, ("market", "ticker", "text", "kind")),
}


@dataclass(frozen=True)
class Coverage:
    """What the database actually holds for one security.

    This is what COVERAGE.md is generated from. Writing that file by hand
    would mean writing down what we believe we collected; generating it means
    writing down what is there.
    """

    market: str
    ticker: str
    first_day: date
    last_day: date
    trading_days: int
    sources: tuple[str, ...]


def _rows(records: Iterable[Any], columns: Sequence[str]) -> dict[str, list]:
    materialised = list(records)
    return {
        column: [getattr(record, column, None) for record in materialised] for column in columns
    }


class MarketStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._cached: duckdb.DuckDBPyConnection | None = None

    def path_for(self, table: str) -> Path:
        return self.root / f"{table}.parquet"

    # --- writing ------------------------------------------------------------

    def write(self, table: str, records: Iterable[Any]) -> int:
        """Merge records into a table. Returns the row count afterwards."""
        spec = TABLES[table]
        incoming = pa.table(_rows(records, spec.schema.names), schema=spec.schema)
        path = self.path_for(table)

        with duckdb.connect() as connection:
            connection.register("incoming", incoming)
            if path.exists():
                connection.execute(
                    f"CREATE VIEW existing AS SELECT * FROM read_parquet('{path}')"  # noqa: S608
                )
                union = "SELECT * FROM existing UNION ALL BY NAME SELECT * FROM incoming"
            else:
                union = "SELECT * FROM incoming"

            keys = ", ".join(spec.key)
            # Later rows win, so a re-collected day replaces the stored one.
            # Without the tiebreak on rowid the choice between two rows with
            # the same key would depend on scan order, and a re-run could
            # quietly change a stored price.
            merged = connection.sql(
                f"""
                WITH combined AS (SELECT *, row_number() OVER () AS _seq FROM ({union}))
                SELECT * EXCLUDE (_seq) FROM combined
                QUALIFY row_number() OVER (PARTITION BY {keys} ORDER BY _seq DESC) = 1
                """
            ).to_arrow_table()

        # Written through a temporary file so an interrupted write cannot
        # leave a truncated parquet behind.
        temporary = path.with_suffix(".parquet.tmp")
        pq.write_table(merged.cast(spec.schema), temporary)
        temporary.replace(path)
        # The shared read connection holds views over the old files, and a
        # table written for the first time is not in it at all.
        self.close()
        return merged.num_rows

    def write_bars(self, bars: Iterable[Bar]) -> int:
        return self.write("bars", bars)

    def write_dividends(self, dividends: Iterable[Dividend]) -> int:
        return self.write("dividends", dividends)

    def write_actions(self, actions: Iterable[CorporateAction]) -> int:
        return self.write("actions", actions)

    def write_securities(self, securities: Iterable[Security]) -> int:
        securities = list(securities)
        count = self.write("securities", securities)
        aliases = [
            _AliasRow(
                ticker=security.ticker,
                market=security.market,
                text=alias.text,
                kind=alias.kind,
                until=alias.until,
            )
            for security in securities
            for alias in security.aliases
        ]
        if aliases:
            self.write("aliases", aliases)
        return count

    # --- reading ------------------------------------------------------------

    def connect(self) -> duckdb.DuckDBPyConnection:
        """A connection with a view over every table that exists on disk.

        Tables with no file yet are created as empty views with the right
        columns, so a query written against the full schema works before the
        first collection has run.
        """
        connection = duckdb.connect()
        for name, spec in TABLES.items():
            path = self.path_for(name)
            if path.exists():
                connection.execute(
                    f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{path}')"  # noqa: S608
                )
            else:
                empty = pa.table({field.name: [] for field in spec.schema}, schema=spec.schema)
                connection.register(f"_empty_{name}", empty)
                connection.execute(f"CREATE VIEW {name} AS SELECT * FROM _empty_{name}")
        return connection

    def _shared(self) -> duckdb.DuckDBPyConnection:
        """A connection kept open across queries.

        Opening a connection and re-declaring every view costs more than most of
        the queries in this project put together. Generating the eval set runs
        thousands of small reads, and with a fresh connection each time it took
        minutes rather than seconds. The connection is dropped after any write so
        the next read sees the new parquet files.
        """
        if self._cached is None:
            self._cached = self.connect()
        return self._cached

    def query(self, sql: str, parameters: Sequence[Any] | None = None) -> list[tuple]:
        return self._shared().execute(sql, parameters or []).fetchall()

    def close(self) -> None:
        if self._cached is not None:
            self._cached.close()
            self._cached = None

    def coverage(self) -> list[Coverage]:
        rows = self.query(
            """
            SELECT market, ticker, min(day), max(day), count(DISTINCT day),
                   list_sort(list(DISTINCT source))
            FROM bars
            GROUP BY market, ticker
            ORDER BY market, ticker
            """
        )
        return [
            Coverage(
                market=market,
                ticker=ticker,
                first_day=first,
                last_day=last,
                trading_days=days,
                sources=tuple(sources),
            )
            for market, ticker, first, last, days, sources in rows
        ]


@dataclass(frozen=True)
class _AliasRow:
    ticker: str
    market: str
    text: str
    kind: str
    until: date | None
