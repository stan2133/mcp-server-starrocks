import pandas as pd

from src.mcp_server_starrocks import server
from src.mcp_server_starrocks.db_client import ResultSet


def test_query_and_echarts_chart_truncates_structured_rows(monkeypatch):
    rows = [[i, i * 10] for i in range(5)]
    dataframe = pd.DataFrame(rows, columns=["x", "y"])

    def fake_execute(query, db=None, return_format="raw"):
        assert return_format == "pandas"
        return ResultSet(
            success=True,
            column_names=["x", "y"],
            rows=rows,
            execution_time=0.1,
            pandas=dataframe,
        )

    monkeypatch.setattr(server.db_client, "execute", fake_execute)

    result = server.query_and_echarts_chart("SELECT x, y FROM metrics", max_points=2)

    assert result.structured_content["rows"] == rows[:2]
    assert result.structured_content["echarts_meta"]["row_count"] == 5
    assert result.structured_content["echarts_meta"]["rendered_row_count"] == 2
    assert result.structured_content["echarts_meta"]["truncated"] is True
    assert "Chart data truncated to 2 rows (original 5)." in result.content[0].text
