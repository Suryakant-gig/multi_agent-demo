import pytest
from app.services.visualization_service import visualization_service
from app.models.domain import ChartType
from app.utils.exceptions import ChartGenerationException


def test_bar_chart_generation(populated_session):
    session_id, meta = populated_session
    payload = visualization_service.generate_chart(
        session_id=session_id,
        dataset=meta,
        chart_type=ChartType.BAR,
        x_column="category",
        y_column="revenue",
        aggregation="SUM"
    )
    assert payload.chart_type == ChartType.BAR
    assert payload.image_base64.startswith("data:image/png;base64,")
    assert payload.spec_json["type"] == "bar"
    assert len(payload.data_points) > 0


def test_pie_chart_generation(populated_session):
    session_id, meta = populated_session
    payload = visualization_service.generate_chart(
        session_id=session_id,
        dataset=meta,
        chart_type=ChartType.PIE,
        x_column="category",
        y_column="revenue"
    )
    assert payload.chart_type == ChartType.PIE
    assert payload.image_base64.startswith("data:image/png;base64,")


def test_scatter_chart_generation(populated_session):
    session_id, meta = populated_session
    payload = visualization_service.generate_chart(
        session_id=session_id,
        dataset=meta,
        chart_type=ChartType.SCATTER,
        x_column="quantity",
        y_column="revenue"
    )
    assert payload.chart_type == ChartType.SCATTER
    assert payload.image_base64.startswith("data:image/png;base64,")


def test_histogram_generation(populated_session):
    session_id, meta = populated_session
    payload = visualization_service.generate_chart(
        session_id=session_id,
        dataset=meta,
        chart_type=ChartType.HISTOGRAM,
        x_column="revenue"
    )
    assert payload.chart_type == ChartType.HISTOGRAM
    assert payload.image_base64.startswith("data:image/png;base64,")


def test_invalid_column_chart(populated_session):
    session_id, meta = populated_session
    with pytest.raises(ChartGenerationException) as exc:
        visualization_service.generate_chart(
            session_id=session_id,
            dataset=meta,
            chart_type=ChartType.BAR,
            x_column="non_existent_column",
            y_column="revenue"
        )
    assert "does not exist in dataset" in str(exc.value)
