# Copyright 2021-present StarRocks, Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


SUPPORTED_CHART_TYPES = {"auto", "line", "bar", "scatter", "pie"}


@dataclass
class EChartsBuildResult:
    option: Dict[str, Any]
    chart_type: str
    x_field: str
    y_fields: List[str]
    series_field: Optional[str]
    row_count: int
    rendered_row_count: int
    truncated: bool

    def to_meta(self) -> Dict[str, Any]:
        return {
            "chart_type": self.chart_type,
            "x_field": self.x_field,
            "y_fields": self.y_fields,
            "series_field": self.series_field,
            "row_count": self.row_count,
            "rendered_row_count": self.rendered_row_count,
            "truncated": self.truncated,
        }


def _to_json_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def _string_list(values: List[Any]) -> List[str]:
    return ["" if value is None else str(value) for value in values]


def _is_numeric(df: pd.DataFrame, column: str) -> bool:
    return pd.api.types.is_numeric_dtype(df[column])


def _parse_y_fields(y_fields: Optional[str]) -> List[str]:
    if not y_fields:
        return []
    return [item.strip() for item in y_fields.split(",") if item.strip()]


def _ensure_columns_exist(df: pd.DataFrame, columns: List[str]) -> None:
    missing = [name for name in columns if name not in df.columns]
    if missing:
        raise ValueError(f"Columns not found in query result: {', '.join(missing)}")


def _dedup_in_order(values: List[Any]) -> List[Any]:
    seen = set()
    output: List[Any] = []
    for value in values:
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def _resolve_fields(
    df: pd.DataFrame,
    chart_type: str,
    x_field: Optional[str],
    y_fields: Optional[str],
) -> Tuple[str, str, List[str]]:
    if chart_type not in SUPPORTED_CHART_TYPES:
        raise ValueError(
            f"Unsupported chart_type '{chart_type}'. Supported values: {', '.join(sorted(SUPPORTED_CHART_TYPES))}"
        )

    columns = list(df.columns)
    if not columns:
        raise ValueError("Query returned no columns")

    numeric_columns = [col for col in columns if _is_numeric(df, col)]
    non_numeric_columns = [col for col in columns if col not in numeric_columns]
    parsed_y_fields = _parse_y_fields(y_fields)

    resolved_type = chart_type
    if chart_type == "auto":
        if non_numeric_columns and numeric_columns:
            resolved_type = "bar"
        elif len(numeric_columns) >= 2:
            resolved_type = "scatter"
        elif numeric_columns:
            resolved_type = "line"
        else:
            raise ValueError("Unable to infer chart type from result set; please specify chart_type explicitly")

    if resolved_type in ("line", "bar"):
        resolved_x = x_field or (non_numeric_columns[0] if non_numeric_columns else columns[0])
        resolved_y = parsed_y_fields or [col for col in numeric_columns if col != resolved_x]
        if not resolved_y:
            fallback_y = [col for col in columns if col != resolved_x]
            if fallback_y:
                resolved_y = [fallback_y[0]]
    elif resolved_type == "scatter":
        if x_field:
            resolved_x = x_field
            resolved_y = parsed_y_fields
            if not resolved_y:
                candidates = [col for col in numeric_columns if col != resolved_x]
                if candidates:
                    resolved_y = [candidates[0]]
        elif parsed_y_fields and len(parsed_y_fields) >= 2:
            resolved_x = parsed_y_fields[0]
            resolved_y = [parsed_y_fields[1]]
        elif len(numeric_columns) >= 2:
            resolved_x = numeric_columns[0]
            resolved_y = [numeric_columns[1]]
        else:
            raise ValueError("Scatter chart requires at least 2 numeric columns or explicit x_field/y_fields")
    else:  # pie
        resolved_x = x_field or (non_numeric_columns[0] if non_numeric_columns else columns[0])
        resolved_y = parsed_y_fields or [col for col in numeric_columns if col != resolved_x]
        if not resolved_y:
            fallback_y = [col for col in columns if col != resolved_x]
            if fallback_y:
                resolved_y = [fallback_y[0]]

    if not resolved_y:
        raise ValueError("Unable to resolve y_fields from query result")

    return resolved_type, resolved_x, resolved_y


def _build_line_or_bar_option(
    df: pd.DataFrame,
    chart_type: str,
    x_field: str,
    y_fields: List[str],
    series_field: Optional[str],
    title: str,
) -> Dict[str, Any]:
    x_values = _dedup_in_order(df[x_field].tolist())
    x_data = _string_list([_to_json_value(value) for value in x_values])
    series: List[Dict[str, Any]] = []

    if series_field:
        if len(y_fields) != 1:
            raise ValueError("series_field mode requires exactly one y field for line/bar chart")
        y_field = y_fields[0]
        series_values = _dedup_in_order(df[series_field].tolist())
        for series_value in series_values:
            subset = df[df[series_field] == series_value]
            value_map = {}
            for _, row in subset.iterrows():
                value_map[str(row[x_field])] = _to_json_value(row[y_field])
            data = [value_map.get(str(x)) for x in x_values]
            series.append(
                {
                    "name": str(series_value),
                    "type": chart_type,
                    "data": data,
                }
            )
    else:
        for y_field in y_fields:
            data = [_to_json_value(value) for value in df[y_field].tolist()]
            series.append(
                {
                    "name": y_field,
                    "type": chart_type,
                    "data": data,
                }
            )
            # Ensure x-axis matches row-wise data for non-dedup mode.
            x_data = _string_list([_to_json_value(value) for value in df[x_field].tolist()])

    return {
        "title": {"text": title},
        "tooltip": {"trigger": "axis"},
        "legend": {"type": "scroll"},
        "xAxis": {"type": "category", "data": x_data},
        "yAxis": {"type": "value"},
        "series": series,
    }


def _build_scatter_option(
    df: pd.DataFrame,
    x_field: str,
    y_field: str,
    series_field: Optional[str],
    title: str,
) -> Dict[str, Any]:
    x_is_numeric = _is_numeric(df, x_field)
    x_axis_type = "value" if x_is_numeric else "category"
    series: List[Dict[str, Any]] = []

    if series_field:
        series_values = _dedup_in_order(df[series_field].tolist())
        for series_value in series_values:
            subset = df[df[series_field] == series_value]
            if x_axis_type == "value":
                data = [
                    [_to_json_value(row[x_field]), _to_json_value(row[y_field])]
                    for _, row in subset.iterrows()
                ]
            else:
                data = [
                    [str(_to_json_value(row[x_field])), _to_json_value(row[y_field])]
                    for _, row in subset.iterrows()
                ]
            series.append(
                {
                    "name": str(series_value),
                    "type": "scatter",
                    "data": data,
                }
            )
    else:
        if x_axis_type == "value":
            data = [
                [_to_json_value(row[x_field]), _to_json_value(row[y_field])]
                for _, row in df.iterrows()
            ]
        else:
            data = [
                [str(_to_json_value(row[x_field])), _to_json_value(row[y_field])]
                for _, row in df.iterrows()
            ]
        series.append({"name": y_field, "type": "scatter", "data": data})

    option: Dict[str, Any] = {
        "title": {"text": title},
        "tooltip": {"trigger": "item"},
        "legend": {"type": "scroll"},
        "xAxis": {"type": x_axis_type},
        "yAxis": {"type": "value"},
        "series": series,
    }

    if x_axis_type == "category":
        x_data = _string_list([_to_json_value(value) for value in _dedup_in_order(df[x_field].tolist())])
        option["xAxis"]["data"] = x_data

    return option


def _build_pie_option(df: pd.DataFrame, x_field: str, y_field: str, title: str) -> Dict[str, Any]:
    pie_data = []
    for _, row in df.iterrows():
        pie_data.append(
            {
                "name": str(_to_json_value(row[x_field])),
                "value": _to_json_value(row[y_field]),
            }
        )

    return {
        "title": {"text": title},
        "tooltip": {"trigger": "item"},
        "legend": {"type": "scroll"},
        "series": [
            {
                "name": y_field,
                "type": "pie",
                "radius": "55%",
                "data": pie_data,
            }
        ],
    }


def build_echarts_option(
    df: pd.DataFrame,
    chart_type: str = "auto",
    x_field: Optional[str] = None,
    y_fields: Optional[str] = None,
    series_field: Optional[str] = None,
    title: Optional[str] = None,
    max_points: int = 2000,
) -> EChartsBuildResult:
    if max_points <= 0:
        raise ValueError("max_points must be greater than 0")
    if df is None or df.empty:
        raise ValueError("Query returned no data to plot")

    original_row_count = len(df)
    render_df = df.head(max_points) if original_row_count > max_points else df
    truncated = len(render_df) < original_row_count

    resolved_type, resolved_x_field, resolved_y_fields = _resolve_fields(
        render_df,
        chart_type=chart_type,
        x_field=x_field,
        y_fields=y_fields,
    )

    required_columns = [resolved_x_field] + resolved_y_fields
    if series_field:
        required_columns.append(series_field)
    _ensure_columns_exist(render_df, required_columns)

    resolved_title = title or f"{resolved_type.capitalize()} Chart"

    if resolved_type in ("line", "bar"):
        option = _build_line_or_bar_option(
            render_df,
            chart_type=resolved_type,
            x_field=resolved_x_field,
            y_fields=resolved_y_fields,
            series_field=series_field,
            title=resolved_title,
        )
    elif resolved_type == "scatter":
        option = _build_scatter_option(
            render_df,
            x_field=resolved_x_field,
            y_field=resolved_y_fields[0],
            series_field=series_field,
            title=resolved_title,
        )
    else:
        option = _build_pie_option(
            render_df,
            x_field=resolved_x_field,
            y_field=resolved_y_fields[0],
            title=resolved_title,
        )

    return EChartsBuildResult(
        option=option,
        chart_type=resolved_type,
        x_field=resolved_x_field,
        y_fields=resolved_y_fields,
        series_field=series_field,
        row_count=original_row_count,
        rendered_row_count=len(render_df),
        truncated=truncated,
    )

