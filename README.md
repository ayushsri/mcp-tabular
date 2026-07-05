# mcp-tabular

**An MCP server that gives any LLM agent SQL over CSV and Excel files.** DuckDB-powered, read-only, zero configuration.

## Why

Embedding spreadsheets into a vector store gives agents mushy answers; tables chunk badly. The pattern that works in production is **SQL-over-file**: load the table into an analytical engine and let the agent query it. `mcp-tabular` packages that pattern as a standard [MCP](https://modelcontextprotocol.io) server, so it works with Claude Desktop, Claude Code, or any MCP client.

```
Agent ──MCP──▶ mcp-tabular ──▶ DuckDB (in-memory, read-only)
                  tools: load_file · list_tables · describe_table · query · sample_rows
```

## Install & run

```bash
pip install -e .
mcp-tabular            # stdio transport
```

Claude Desktop config:

```json
{
  "mcpServers": {
    "tabular": { "command": "mcp-tabular" }
  }
}
```

## Tools

| Tool | Description |
|---|---|
| `load_file(path, table_name?)` | Load a CSV/XLSX file into an in-memory table. Returns schema + row count. |
| `list_tables()` | Tables currently loaded. |
| `describe_table(table)` | Columns, types, null counts, min/max — enough for the agent to write correct SQL. |
| `query(sql)` | Read-only SELECT. Results capped and returned as markdown. |
| `sample_rows(table, n)` | Quick peek at representative rows. |

## Safety

- **Read-only**: statements other than `SELECT`/`WITH` are rejected before execution.
- **Path allow-listing**: set `MCP_TABULAR_ROOT` to restrict which directory files may be loaded from.
- **Bounded output**: result sets are truncated (default 200 rows) so a bad query can't blow up the agent's context window.

## Example session

```
> load_file("sales_q3.csv")
loaded table 'sales_q3' (8,412 rows). Columns: region VARCHAR, sku VARCHAR, units BIGINT, revenue DOUBLE

> query("SELECT region, SUM(revenue) r FROM sales_q3 GROUP BY 1 ORDER BY r DESC LIMIT 3")
| region | r        |
|--------|----------|
| South  | 412,050  |
| West   | 371,200  |
| East   | 298,700  |
```

## Design notes

Built after shipping enterprise agents where tabular Q&A over uploaded files was the highest-volume use case. Schema + sample injection (via `describe_table`/`sample_rows`) is what makes agents write correct SQL on the first try.

## License

MIT
