import io
import base64
from typing import Dict, Any, List, Optional
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import pandas as pd
from app.models.domain import ChartType, ChartPayload, DatasetMetadata
from app.services.storage_engine import storage_engine
from app.utils.exceptions import ChartGenerationException
from app.utils.logger import logger


class VisualizationService:
    """
    Renders high-quality charts as Base64 images and returns declarative JSON specs.
    Validates column existence and prepares data safely.
    """

    @staticmethod
    def _validate_columns(dataset: DatasetMetadata, columns: List[str]) -> None:
        dataset_col_names = {c.name for c in dataset.columns}
        for col in columns:
            if col and col not in dataset_col_names:
                raise ChartGenerationException(
                    f"Column '{col}' does not exist in dataset '{dataset.file_name}'. "
                    f"Available columns are: {', '.join(sorted(dataset_col_names))}"
                )

    def generate_chart(
        self,
        session_id: str,
        dataset: DatasetMetadata,
        chart_type: ChartType,
        x_column: str,
        y_column: Optional[str] = None,
        aggregation: Optional[str] = "SUM",
        title: Optional[str] = None,
        top_k: int = 10
    ) -> ChartPayload:
        self._validate_columns(dataset, [x_column] + ([y_column] if y_column else []))
        
        table_name = dataset.db_table_name
        chart_title = title or f"{chart_type.value.upper()} of {y_column or x_column} by {x_column}"

        # Fetch and prepare data
        df = self._prepare_data(
            session_id=session_id,
            table_name=table_name,
            chart_type=chart_type,
            x_col=x_column,
            y_col=y_column,
            aggregation=aggregation or "SUM",
            top_k=top_k
        )

        if df.empty:
            raise ChartGenerationException("No valid data available to generate chart.")

        # Render image
        base64_img = self._render_matplotlib(
            df=df,
            chart_type=chart_type,
            x_col=x_column,
            y_col=y_column,
            title=chart_title
        )

        # Generate JSON specification
        spec_json = self._build_spec_json(
            df=df,
            chart_type=chart_type,
            x_col=x_column,
            y_col=y_column,
            title=chart_title
        )

        data_points = df.to_dict(orient="records")

        return ChartPayload(
            chart_type=chart_type,
            title=chart_title,
            x_column=x_column,
            y_column=y_column,
            aggregation=aggregation,
            data_points=data_points,
            image_base64=base64_img,
            spec_json=spec_json,
            metadata={
                "dataset_id": dataset.file_id,
                "dataset_name": dataset.file_name,
                "points_rendered": len(data_points),
                "generated_at": pd.Timestamp.now().isoformat()
            }
        )

    def _prepare_data(
        self,
        session_id: str,
        table_name: str,
        chart_type: ChartType,
        x_col: str,
        y_col: Optional[str],
        aggregation: str,
        top_k: int
    ) -> pd.DataFrame:
        if chart_type in (ChartType.BAR, ChartType.PIE):
            if y_col:
                records = storage_engine.execute_aggregation(
                    session_id=session_id,
                    table_name=table_name,
                    group_by_col=x_col,
                    agg_col=y_col,
                    agg_func=aggregation,
                    top_k=top_k
                )
                df = pd.DataFrame(records)
                if not df.empty:
                    df = df.rename(columns={"category": x_col, "metric": y_col})
                    return df[[x_col, y_col]]
            else:
                # Count frequencies of x_col
                sql = f'''
                    SELECT "{x_col}", COUNT(*) as count
                    FROM "{table_name}"
                    WHERE "{x_col}" IS NOT NULL
                    GROUP BY "{x_col}"
                    ORDER BY count DESC
                    LIMIT ?
                '''
                records = storage_engine.execute_read_query(session_id, sql, (top_k,))
                return pd.DataFrame(records)

        elif chart_type == ChartType.TIME_SERIES:
            metric_col = y_col or "rowid"
            sql = f'''
                SELECT "{x_col}", {"SUM(" + y_col + ")" if y_col else "COUNT(*)"} as metric
                FROM "{table_name}"
                WHERE "{x_col}" IS NOT NULL
                GROUP BY "{x_col}"
                ORDER BY "{x_col}" ASC
                LIMIT ?
            '''
            records = storage_engine.execute_read_query(session_id, sql, (top_k * 5,))
            df = pd.DataFrame(records)
            if not df.empty and y_col:
                df = df.rename(columns={"metric": y_col})
            return df

        elif chart_type == ChartType.HISTOGRAM:
            target_col = y_col or x_col
            sql = f'SELECT "{target_col}" FROM "{table_name}" WHERE "{target_col}" IS NOT NULL LIMIT 2000'
            records = storage_engine.execute_read_query(session_id, sql)
            return pd.DataFrame(records)

        elif chart_type == ChartType.SCATTER:
            if not y_col:
                raise ChartGenerationException("Scatter plots require both x_column and y_column.")
            sql = f'SELECT "{x_col}", "{y_col}" FROM "{table_name}" WHERE "{x_col}" IS NOT NULL AND "{y_col}" IS NOT NULL LIMIT 500'
            records = storage_engine.execute_read_query(session_id, sql)
            return pd.DataFrame(records)

        # Default fallback
        sql = f'SELECT * FROM "{table_name}" LIMIT ?'
        records = storage_engine.execute_read_query(session_id, sql, (top_k,))
        return pd.DataFrame(records)

    def _render_matplotlib(
        self,
        df: pd.DataFrame,
        chart_type: ChartType,
        x_col: str,
        y_col: Optional[str],
        title: str
    ) -> str:
        fig, ax = plt.subplots(figsize=(8, 5), dpi=100)
        
        # Styling
        ax.set_facecolor("#f8f9fa")
        fig.patch.set_facecolor("#ffffff")
        ax.grid(True, linestyle="--", alpha=0.5, color="#cbd5e1")
        plt.title(title, fontsize=13, fontweight="bold", pad=12, color="#1e293b")

        colors = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4"]

        try:
            if chart_type == ChartType.BAR:
                metric_col = y_col or ("count" if "count" in df.columns else df.columns[1])
                x_vals = df[x_col].astype(str)
                y_vals = pd.to_numeric(df[metric_col], errors="coerce").fillna(0)
                bars = ax.bar(x_vals, y_vals, color="#3b82f6", edgecolor="#1d4ed8", alpha=0.85)
                ax.set_xlabel(x_col, fontsize=10, labelpad=8)
                ax.set_ylabel(metric_col, fontsize=10, labelpad=8)
                plt.xticks(rotation=30, ha="right")

            elif chart_type == ChartType.LINE or chart_type == ChartType.TIME_SERIES:
                metric_col = y_col or ("metric" if "metric" in df.columns else df.columns[1])
                x_vals = df[x_col].astype(str)
                y_vals = pd.to_numeric(df[metric_col], errors="coerce").fillna(0)
                ax.plot(x_vals, y_vals, marker="o", color="#2563eb", linewidth=2.5, markersize=5)
                ax.set_xlabel(x_col, fontsize=10, labelpad=8)
                ax.set_ylabel(metric_col, fontsize=10, labelpad=8)
                plt.xticks(rotation=30, ha="right")

            elif chart_type == ChartType.PIE:
                metric_col = y_col or ("count" if "count" in df.columns else df.columns[1])
                labels = df[x_col].astype(str)
                values = pd.to_numeric(df[metric_col], errors="coerce").fillna(0)
                ax.pie(values, labels=labels, autopct="%1.1f%%", startangle=140, colors=colors[:len(values)])

            elif chart_type == ChartType.SCATTER:
                ax.scatter(pd.to_numeric(df[x_col], errors="coerce"), pd.to_numeric(df[y_col], errors="coerce"), color="#6366f1", alpha=0.7, edgecolors="none")
                ax.set_xlabel(x_col, fontsize=10, labelpad=8)
                ax.set_ylabel(y_col, fontsize=10, labelpad=8)

            elif chart_type == ChartType.HISTOGRAM:
                target_col = y_col or x_col
                vals = pd.to_numeric(df[target_col], errors="coerce").dropna()
                ax.hist(vals, bins=15, color="#10b981", edgecolor="#047857", alpha=0.8)
                ax.set_xlabel(target_col, fontsize=10, labelpad=8)
                ax.set_ylabel("Frequency", fontsize=10, labelpad=8)

            plt.tight_layout()
            buf = io.BytesIO()
            plt.savefig(buf, format="png", bbox_inches="tight")
            buf.seek(0)
            img_b64 = base64.b64encode(buf.read()).decode("utf-8")
            return f"data:image/png;base64,{img_b64}"
        finally:
            plt.close(fig)

    def _build_spec_json(
        self,
        df: pd.DataFrame,
        chart_type: ChartType,
        x_col: str,
        y_col: Optional[str],
        title: str
    ) -> Dict[str, Any]:
        """
        Creates declarative Plotly / Vega-Lite compatible spec for frontend consumption.
        """
        return {
            "title": title,
            "type": chart_type.value,
            "encoding": {
                "x": {"field": x_col, "type": "nominal" if chart_type in (ChartType.BAR, ChartType.PIE) else "quantitative"},
                "y": {"field": y_col or "count", "type": "quantitative"}
            },
            "data": df.to_dict(orient="records")
        }


visualization_service = VisualizationService()
