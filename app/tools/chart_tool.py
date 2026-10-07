from typing import Dict, Any, Optional
from app.tools.base import BaseTool
from app.models.domain import ChartType
from app.services.visualization_service import visualization_service
from app.state.session_manager import session_manager


class GenerateChartTool(BaseTool):
    name = "generate_chart"
    description = "Generate visualizations (bar, line, pie, scatter, histogram, time_series) from the dataset."

    parameters_schema = {
        "type": "object",
        "properties": {
            "chart_type": {
                "type": "string",
                "enum": ["bar", "line", "pie", "scatter", "histogram", "time_series"],
                "description": "Chart style: bar, line, pie, scatter, histogram, or time_series."
            },
            "x_column": {
                "type": "string",
                "description": "Column name for x-axis or categorical grouping."
            },
            "y_column": {
                "type": "string",
                "description": "Optional column name for y-axis or metric values."
            },
            "aggregation": {
                "type": "string",
                "enum": ["SUM", "AVG", "COUNT", "MIN", "MAX"],
                "description": "Aggregation function if grouping data. Default 'SUM'.",
                "default": "SUM"
            },
            "title": {
                "type": "string",
                "description": "Optional custom title for the chart."
            },
            "top_k": {
                "type": "integer",
                "description": "Maximum number of data categories to include. Default 10.",
                "default": 10
            },
            "file_id": {
                "type": "string",
                "description": "Optional file_id. Defaults to active file."
            }
        },
        "required": ["chart_type", "x_column"]
    }

    output_schema = {
        "type": "object",
        "properties": {
            "chart_type": {"type": "string"},
            "title": {"type": "string"},
            "x_column": {"type": "string"},
            "y_column": {"type": "string"},
            "image_base64": {"type": "string"},
            "spec_json": {"type": "object"},
            "data_points": {"type": "array"}
        }
    }

    usage_example = {
        "call": {
            "tool": "generate_chart",
            "parameters": {
                "chart_type": "bar",
                "x_column": "product",
                "y_column": "revenue",
                "aggregation": "SUM",
                "title": "Revenue by Product"
            }
        },
        "output": {
            "chart_type": "bar",
            "title": "Revenue by Product",
            "x_column": "product",
            "y_column": "revenue",
            "image_base64": "data:image/png;base64,iVBORw0KGgoAAA...",
            "data_points": [{"product": "Laptop", "revenue": 1000}],
            "spec_json": {"type": "bar", "data": []}
        }
    }

    def execute(
        self,
        session_id: str,
        chart_type: str,
        x_column: str,
        y_column: Optional[str] = None,
        aggregation: Optional[str] = "SUM",
        title: Optional[str] = None,
        top_k: int = 10,
        file_id: Optional[str] = None
    ) -> Dict[str, Any]:
        dataset = session_manager.get_active_file(session_id=session_id, file_id=file_id)
        
        # Match case-insensitively
        col_names = {c.name.lower(): c.name for c in dataset.columns}
        actual_x = col_names.get(x_column.lower(), x_column)
        actual_y = col_names.get(y_column.lower(), y_column) if y_column else None

        enum_type = ChartType(chart_type.lower())

        chart_payload = visualization_service.generate_chart(
            session_id=session_id,
            dataset=dataset,
            chart_type=enum_type,
            x_column=actual_x,
            y_column=actual_y,
            aggregation=aggregation,
            title=title,
            top_k=top_k
        )

        return chart_payload.model_dump()
