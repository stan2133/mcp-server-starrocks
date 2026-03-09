import pandas as pd
import pytest

from src.mcp_server_starrocks.echarts_builder import build_echarts_option


class TestEChartsBuilder:
    def test_auto_infers_bar_for_category_numeric(self):
        df = pd.DataFrame(
            {
                "region": ["east", "west", "north"],
                "sales": [10, 20, 30],
            }
        )

        result = build_echarts_option(df, chart_type="auto")
        assert result.chart_type == "bar"
        assert result.x_field == "region"
        assert result.y_fields == ["sales"]
        assert result.option["series"][0]["type"] == "bar"

    def test_line_with_series_field(self):
        df = pd.DataFrame(
            {
                "day": ["Mon", "Mon", "Tue", "Tue"],
                "category": ["A", "B", "A", "B"],
                "value": [10, 12, 13, 11],
            }
        )

        result = build_echarts_option(
            df,
            chart_type="line",
            x_field="day",
            y_fields="value",
            series_field="category",
        )
        assert result.chart_type == "line"
        assert len(result.option["series"]) == 2
        assert result.option["series"][0]["type"] == "line"

    def test_auto_infers_scatter_for_numeric_pair(self):
        df = pd.DataFrame(
            {
                "x": [1, 2, 3],
                "y": [5, 6, 7],
            }
        )

        result = build_echarts_option(df, chart_type="auto")
        assert result.chart_type == "scatter"
        assert result.x_field == "x"
        assert result.y_fields == ["y"]
        assert result.option["series"][0]["type"] == "scatter"

    def test_pie_chart(self):
        df = pd.DataFrame(
            {
                "name": ["A", "B"],
                "amount": [40, 60],
            }
        )

        result = build_echarts_option(
            df,
            chart_type="pie",
            x_field="name",
            y_fields="amount",
            title="Distribution",
        )
        assert result.chart_type == "pie"
        assert result.option["title"]["text"] == "Distribution"
        assert result.option["series"][0]["type"] == "pie"
        assert result.option["series"][0]["data"][0]["name"] == "A"
        assert result.option["series"][0]["data"][0]["value"] == 40

    def test_max_points_truncation(self):
        df = pd.DataFrame(
            {
                "x": list(range(10)),
                "y": list(range(10)),
            }
        )

        result = build_echarts_option(
            df,
            chart_type="scatter",
            x_field="x",
            y_fields="y",
            max_points=5,
        )
        assert result.truncated is True
        assert result.row_count == 10
        assert result.rendered_row_count == 5
        assert len(result.option["series"][0]["data"]) == 5

    def test_invalid_column_raises(self):
        df = pd.DataFrame({"a": [1, 2, 3]})
        with pytest.raises(ValueError, match="Columns not found"):
            build_echarts_option(df, chart_type="line", x_field="a", y_fields="missing")

