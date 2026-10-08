from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from app.state.session_manager import session_manager
from app.utils.exceptions import SessionNotFoundException
from app.utils.logger import logger

router = APIRouter(prefix="/conversations", tags=["Conversations"])


class CreateConversationRequest(BaseModel):
    conversation_id: Optional[str] = Field(None, description="Optional custom ID")
    title: Optional[str] = Field("New Chat", description="Initial conversation title")


class RenameConversationRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=100, description="New title for conversation")


@router.post("", status_code=status.HTTP_201_CREATED, summary="Create a new conversation")
def create_conversation(req: Optional[CreateConversationRequest] = None):
    custom_id = req.conversation_id if req else None
    title = req.title if req else "New Chat"
    session = session_manager.create_session(session_id=custom_id, title=title)
    return session.to_detail_dict()


@router.get("", summary="List all saved conversations")
def list_conversations():
    return session_manager.list_conversations()


@router.get("/{conversation_id}", summary="Get conversation messages and context")
def get_conversation(conversation_id: str):
    try:
        session = session_manager.get_session(conversation_id)
        return session.to_detail_dict()
    except SessionNotFoundException as e:
        raise HTTPException(status_code=404, detail=e.message)


@router.patch("/{conversation_id}", summary="Rename a conversation")
def rename_conversation(conversation_id: str, req: RenameConversationRequest):
    try:
        session = session_manager.rename_conversation(conversation_id, req.title)
        return session.to_summary_dict()
    except SessionNotFoundException as e:
        raise HTTPException(status_code=404, detail=e.message)


@router.delete("/{conversation_id}", status_code=status.HTTP_200_OK, summary="Delete a conversation")
def delete_conversation(conversation_id: str):
    success = session_manager.delete_conversation(conversation_id)
    return {"success": success, "conversation_id": conversation_id, "message": "Conversation deleted."}
