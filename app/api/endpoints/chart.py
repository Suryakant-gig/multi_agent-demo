from fastapi import APIRouter, HTTPException, status
from app.schemas.chart import ChartRequest, ChartResponse
from app.schemas.common import ErrorResponse
from app.state.session_manager import session_manager
from app.services.visualization_service import visualization_service
from app.utils.exceptions import SessionNotFoundException, FileNotFoundException, ChartGenerationException
from app.utils.logger import logger

router = APIRouter()


@router.post(
    "/chart",
    response_model=ChartResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate data visualization",
    description="Generates Bar, Line, Pie, Scatter, Histogram, or Time-Series charts with Base64 image and JSON specification.",
    responses={
        200: {"model": ChartResponse, "description": "Chart generated successfully."},
        400: {"model": ErrorResponse, "description": "Invalid column names or unsupported chart configuration."},
        404: {"model": ErrorResponse, "description": "Session or file not found."}
    },
    tags=["Visualization"]
)
def create_chart(request: ChartRequest):
    try:
        session = session_manager.get_session(request.session_id)
        dataset = session_manager.get_active_file(request.session_id, request.file_id)

        chart_payload = visualization_service.generate_chart(
            session_id=request.session_id,
            dataset=dataset,
            chart_type=request.chart_type,
            x_column=request.x_column,
            y_column=request.y_column,
            aggregation=request.aggregation or "SUM",
            title=request.title,
            top_k=request.top_k
        )

        return ChartResponse(**chart_payload.model_dump())

    except SessionNotFoundException as e:
        raise HTTPException(status_code=404, detail=e.message)
    except FileNotFoundException as e:
        raise HTTPException(status_code=404, detail=e.message)
    except ChartGenerationException as e:
        raise HTTPException(status_code=400, detail=e.message)
    except Exception as e:
        logger.error(f"Error in chart endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chart generation error: {str(e)}")
