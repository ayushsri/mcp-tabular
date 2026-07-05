"""MCP server exposing read-only SQL over CSV/Excel files via DuckDB.

Tools: load_file, list_tables, describe_table, query, sample_rows.
Safety: SELECT/WITH-only statements, optional path allow-listing via
MCP_TABULAR_ROOT, and bounded result sets.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import duckdb
from mcp.server.fastmcp import FastMCP

MAX_ROWS = int(os.environ.get("MCP_TABULAR_MAX_ROWS", "200"))
ROOT = os.environ.get("MCP_TABULAR_ROOT")

mcp = FastMCP("mcp-tabular")
_conn = duckdb.connect(":memory:")
_tables: dict[str, str] = {}  # table name -> source path

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_READONLY_RE = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)


def _check_path(path: str) -> Path:
    p = Path(path).expanduser().resolve()
    if ROOT and not str(p).startswith(str(Path(ROOT).resolve())):
        raise ValueError(f"path outside MCP_TABULAR_ROOT: {p}")
    if not p.exists():
        raise FileNotFoundError(f"no such file: {p}")
    return p


def _to_markdown(cols: list[str], rows: list[tuple]) -> str:
    head = "| " + " | ".join(cols) + " |"
    sep = "|" + "|".join(["---"] * len(cols)) + "|"
    body = ["| " + " | ".join("" if v is None else str(v) for v in row) + " |"
            for row in rows]
    return "\n".join([head, sep, *body])


@mcp.tool()
def load_file(path: str, table_name: str = "") -> str:
    """Load a CSV or Excel file into an in-memory table for SQL querying.

    Args:
        path: path to a .csv, .tsv, .xlsx, or .xls file.
        table_name: optional; defaults to the file stem.
    """
    p = _check_path(path)
    name = table_name or re.sub(r"\W+", "_", p.stem).strip("_").lower()
    if not _IDENT_RE.match(name):
        raise ValueError(f"invalid table name: {name!r}")
    suffix = p.suffix.lower()
    if suffix in (".csv", ".tsv"):
        _conn.execute(
            f'CREATE OR REPLACE TABLE "{name}" AS '
            f"SELECT * FROM read_csv_auto(?, sample_size=-1)", [str(p)])
    elif suffix in (".xlsx", ".xls"):
        import pandas as pd  # optional extra
        frame = pd.read_excel(p)
        _conn.register("_tmp_xlsx", frame)
        _conn.execute(f'CREATE OR REPLACE TABLE "{name}" AS SELECT * FROM _tmp_xlsx')
        _conn.unregister("_tmp_xlsx")
    else:
        raise ValueError(f"unsupported file type: {suffix}")
    _tables[name] = str(p)
    n = _conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
    schema = _conn.execute(f'DESCRIBE "{name}"').fetchall()
    cols = ", ".join(f"{c[0]} {c[1]}" for c in schema)
    return f"loaded table '{name}' ({n:,} rows). Columns: {cols}"


@mcp.tool()
def list_tables() -> str:
    """List tables currently loaded and their source files."""
    if not _tables:
        return "no tables loaded — call load_file first"
    return "\n".join(f"{name}  <-  {src}" for name, src in _tables.items())


@mcp.tool()
def describe_table(table: str) -> str:
    """Column names, types, null counts, and min/max — enough to write correct SQL."""
    if not _IDENT_RE.match(table):
        raise ValueError("invalid table name")
    schema = _conn.execute(f'DESCRIBE "{table}"').fetchall()
    lines = []
    for col, dtype, *_ in schema:
        stats = _conn.execute(
            f'SELECT COUNT(*) - COUNT("{col}"), MIN("{col}"), MAX("{col}") '
            f'FROM "{table}"').fetchone()
        lines.append(f'{col} ({dtype}): nulls={stats[0]}, '
                     f'min={stats[1]!r}, max={stats[2]!r}')
    return "\n".join(lines)


@mcp.tool()
def query(sql: str) -> str:
    """Run a read-only SELECT/WITH query. Results are capped at MAX_ROWS."""
    if not _READONLY_RE.match(sql):
        raise ValueError("only SELECT/WITH statements are allowed")
    if ";" in sql.rstrip().rstrip(";"):
        raise ValueError("multiple statements are not allowed")
    cur = _conn.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchmany(MAX_ROWS + 1)
    truncated = len(rows) > MAX_ROWS
    table = _to_markdown(cols, rows[:MAX_ROWS])
    return table + (f"\n\n(truncated to {MAX_ROWS} rows)" if truncated else "")


@mcp.tool()
def sample_rows(table: str, n: int = 5) -> str:
    """Return n representative rows from a loaded table."""
    if not _IDENT_RE.match(table):
        raise ValueError("invalid table name")
    n = max(1, min(int(n), 50))
    cur = _conn.execute(f'SELECT * FROM "{table}" USING SAMPLE {n} ROWS')
    rows = cur.fetchall()
    if not rows:  # small tables: SAMPLE can return empty
        cur = _conn.execute(f'SELECT * FROM "{table}" LIMIT {n}')
        rows = cur.fetchall()
    return _to_markdown([d[0] for d in cur.description], rows)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
