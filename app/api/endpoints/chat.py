from fastapi import APIRouter, HTTPException, status
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.common import ErrorResponse
from app.agents.orchestrator import agent_orchestrator
from app.state.session_manager import session_manager
from app.utils.exceptions import SessionNotFoundException, FileNotFoundException, AppException
from app.utils.logger import logger

router = APIRouter()


@router.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Chat and analyze dataset",
    description="Ask natural language questions, request aggregations, search items, or generate charts with stateful context.",
    responses={
        200: {"model": ChatResponse, "description": "Successful agent response with answer, sources, and charts."},
        400: {"model": ErrorResponse, "description": "Invalid query parameters."},
        404: {"model": ErrorResponse, "description": "Session or file not found."}
    },
    tags=["Chat & Agent"]
)
def chat_with_data(request: ChatRequest):
    try:
        session = session_manager.get_or_create_session(request.session_id)
        if request.file_id:
            # Validate file exists
            session_manager.get_active_file(session.session_id, request.file_id)

        response_dict = agent_orchestrator.process_query(
            session_id=session.session_id,
            query=request.query
        )

        return ChatResponse(**response_dict)

    except SessionNotFoundException as e:
        raise HTTPException(status_code=404, detail=e.message)
    except FileNotFoundException as e:
        raise HTTPException(status_code=404, detail=e.message)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")
