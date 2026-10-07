from fastapi import APIRouter, HTTPException, status
from app.schemas.search import SearchRequest, SearchResponse
from app.schemas.common import ErrorResponse
from app.state.session_manager import session_manager
from app.retrieval.search_engine import search_engine
from app.utils.exceptions import SessionNotFoundException, FileNotFoundException, AppException
from app.utils.logger import logger

router = APIRouter()


@router.post(
    "/search",
    response_model=SearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Search dataset records",
    description="Retrieve ranked Top-K records matching query and filters with full source citations.",
    responses={
        200: {"model": SearchResponse, "description": "Ranked search results with citations."},
        400: {"model": ErrorResponse, "description": "Invalid query or filter parameter."},
        404: {"model": ErrorResponse, "description": "Session or file not found."}
    },
    tags=["Search"]
)
def search_records(request: SearchRequest):
    try:
        session = session_manager.get_session(request.session_id)
        dataset = session_manager.get_active_file(request.session_id, request.file_id)

        results = search_engine.search(
            session_id=request.session_id,
            dataset=dataset,
            query=request.query,
            filters=request.filters,
            top_k=request.top_k
        )

        serialized = [r.model_dump() for r in results]

        return SearchResponse(
            session_id=request.session_id,
            query=request.query,
            count=len(serialized),
            top_k=request.top_k,
            results=serialized
        )

    except SessionNotFoundException as e:
        raise HTTPException(status_code=404, detail=e.message)
    except FileNotFoundException as e:
        raise HTTPException(status_code=404, detail=e.message)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Error in search endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Search failure: {str(e)}")
