import pytest

duckdb = pytest.importorskip("duckdb")
pytest.importorskip("mcp")

from mcp_tabular import server


def test_load_query_and_safety(tmp_path):
    csv = tmp_path / "sales.csv"
    csv.write_text("region,revenue\nSouth,10\nWest,20\n")

    out = server.load_file(str(csv))
    assert "loaded table 'sales'" in out and "2 rows" in out

    result = server.query("SELECT SUM(revenue) AS total FROM sales")
    assert "30" in result

    with pytest.raises(ValueError):
        server.query("DROP TABLE sales")
    with pytest.raises(ValueError):
        server.query("SELECT 1; SELECT 2")

    assert "sales" in server.list_tables()
    assert "revenue" in server.describe_table("sales")
    assert "South" in server.sample_rows("sales", 5) or "West" in server.sample_rows("sales", 5)
