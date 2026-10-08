import os
import json
import uuid
import threading
from typing import Dict, Optional, List, Any
from app.state.state_models import ConversationState
from app.models.domain import DatasetMetadata, DocumentMetadata, MessageRecord, ToolCallRecord, ChartPayload
from app.utils.exceptions import SessionNotFoundException, FileNotFoundException
from app.utils.logger import logger
from app.storage.repositories.conversation_repository import conversation_repository
from app.storage.repositories.message_repository import message_repository
from app.storage.repositories.file_repository import file_repository
from app.storage.repositories.document_repository import document_repository
from app.storage.repositories.tool_repository import tool_repository
from app.storage.repositories.research_repository import research_repository
from app.storage.repositories.citation_repository import citation_repository


class SessionManager:
    """
    Thread-safe session and conversation manager integrated with central PostgreSQL storage.
    Ensures complete conversation isolation so datasets and documents do not leak across sessions.
    Maintains active datasets, PDF documents, conversation history, and cross-turn context.
    """
    _instance = None
    _lock = threading.RLock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SessionManager, cls).__new__(cls)
                cls._instance._sessions: Dict[str, ConversationState] = {}
                cls._instance._sessions_lock = threading.RLock()
                cls._instance._load_persisted_conversations()
        return cls._instance

    def _hydrate_session_from_db(self, conv_id: str) -> Optional[ConversationState]:
        """
        Loads conversation state from PostgreSQL repositories into memory.
        """
        conv_dict = conversation_repository.get(conv_id)
        if not conv_dict:
            return None

        # Fetch messages
        messages = message_repository.get_messages(conv_id)

        # Fetch files & datasets
        datasets = file_repository.get_datasets_for_conversation(conv_id)

        # Fetch documents
        documents = document_repository.get_documents_for_conversation(conv_id)

        active_file_id = list(datasets.keys())[-1] if datasets else None
        active_doc_id = list(documents.keys())[-1] if documents else None

        state = ConversationState(
            session_id=conv_id,
            conversation_id=conv_id,
            title=conv_dict.get("title", "New Chat"),
            messages=messages,
            files=datasets,
            active_file_id=active_file_id,
            documents=documents,
            active_document_id=active_doc_id
        )
        return state

    def _load_persisted_conversations(self) -> None:
        """
        Pre-loads active conversation list from central PostgreSQL storage on startup.
        Also migrates legacy JSON files if any exist.
        """
        try:
            db_convs = conversation_repository.list_all()
            for c in db_convs:
                cid = c["conversation_id"]
                # Lazy-hydrate or hydrate shallow state
                state = self._hydrate_session_from_db(cid)
                if state:
                    self._sessions[cid] = state
            logger.info(f"Loaded {len(db_convs)} conversations from central database storage.")
        except Exception as e:
            logger.warning(f"Could not load conversations from database: {e}")

    def create_session(self, session_id: Optional[str] = None, title: Optional[str] = None) -> ConversationState:
        with self._sessions_lock:
            sid = session_id or f"conv_{uuid.uuid4().hex[:10]}"
            if sid not in self._sessions:
                chat_title = title or "New Chat"
                # Persist to database
                conversation_repository.create(sid, title=chat_title)

                state = ConversationState(
                    session_id=sid,
                    conversation_id=sid,
                    title=chat_title
                )
                self._sessions[sid] = state
                logger.info(f"Created new conversation in PostgreSQL: {sid}")
            return self._sessions[sid]

    def get_session(self, session_id: str) -> ConversationState:
        with self._sessions_lock:
            if session_id in self._sessions:
                return self._sessions[session_id]

            # Try loading from database
            state = self._hydrate_session_from_db(session_id)
            if state:
                self._sessions[session_id] = state
                return state

            raise SessionNotFoundException(session_id)

    def get_or_create_session(self, session_id: Optional[str] = None, title: Optional[str] = None) -> ConversationState:
        if session_id and self.session_exists(session_id):
            return self.get_session(session_id)
        return self.create_session(session_id, title=title)

    def session_exists(self, session_id: str) -> bool:
        with self._sessions_lock:
            if session_id in self._sessions:
                return True
            return conversation_repository.get(session_id) is not None

    def list_conversations(self) -> List[Dict[str, Any]]:
        with self._sessions_lock:
            return conversation_repository.list_all()

    def rename_conversation(self, session_id: str, new_title: str) -> ConversationState:
        session = self.get_session(session_id)
        cleaned_title = new_title.strip() or "Untitled Chat"
        with self._sessions_lock:
            session.title = cleaned_title
            session.touch()
            # Update in PostgreSQL
            conversation_repository.update_title(session.conversation_id, cleaned_title)
        logger.info(f"Renamed conversation {session_id} to '{cleaned_title}' in PostgreSQL")
        return session

    def delete_conversation(self, session_id: str) -> bool:
        with self._sessions_lock:
            target = self._sessions.get(session_id)
            conv_id = target.conversation_id if target else session_id

            # Remove from memory
            to_delete = [k for k, v in self._sessions.items() if v.conversation_id == conv_id or k == conv_id]
            for k in to_delete:
                del self._sessions[k]

            # Delete from database (cascades to messages, files, citations, etc.)
            conversation_repository.delete(conv_id)
            logger.info(f"Deleted conversation {conv_id} from PostgreSQL")
            return True

    def register_file(self, session_id: str, file_meta: DatasetMetadata, storage_path: str = "") -> None:
        with self._sessions_lock:
            session = self._sessions.get(session_id)
            if not session:
                session = self.create_session(session_id=session_id)

            session.files[file_meta.file_id] = file_meta
            session.active_file_id = file_meta.file_id
            session.touch()

            # Persist dataset metadata to PostgreSQL
            file_repository.save_dataset_metadata(file_meta, session.conversation_id, storage_path=storage_path)
            conversation_repository.touch(session.conversation_id)
            logger.info(f"Registered tabular file {file_meta.file_name} in PostgreSQL for conversation {session_id}")

    def register_document(self, session_id: str, doc_meta: DocumentMetadata, storage_path: str = "") -> None:
        with self._sessions_lock:
            session = self._sessions.get(session_id)
            if not session:
                session = self.create_session(session_id=session_id)

            session.documents[doc_meta.document_id] = doc_meta
            session.active_document_id = doc_meta.document_id
            session.touch()

            # Persist document metadata to PostgreSQL
            document_repository.save_document_metadata(doc_meta, session.conversation_id, storage_path=storage_path)
            conversation_repository.touch(session.conversation_id)
            logger.info(f"Registered document {doc_meta.file_name} in PostgreSQL for conversation {session_id}")

    def get_active_file(self, session_id: str, file_id: Optional[str] = None) -> DatasetMetadata:
        session = self.get_session(session_id)
        target_file_id = file_id or session.active_file_id
        if not target_file_id or target_file_id not in session.files:
            raise FileNotFoundException(target_file_id or "NONE")
        return session.files[target_file_id]

    def get_active_document(self, session_id: str, document_id: Optional[str] = None) -> DocumentMetadata:
        session = self.get_session(session_id)
        target_id = document_id or session.active_document_id
        if not target_id or target_id not in session.documents:
            raise FileNotFoundException(target_id or "NONE")
        return session.documents[target_id]

    def append_message(self, session_id: str, message: MessageRecord) -> None:
        session = self.get_session(session_id)
        with self._sessions_lock:
            session.messages.append(message)

            # Auto-title on first meaningful user query
            if message.role == "user" and session.title in ("New Chat", "Untitled Chat"):
                trimmed = message.content.strip().split("\n")[0][:45]
                if trimmed:
                    session.title = trimmed
                    conversation_repository.update_title(session.conversation_id, trimmed)

            session.touch()

            # Persist message and audit artifacts in PostgreSQL
            msg_id = message_repository.add_message(session.conversation_id, message)

            if message.citations:
                citation_repository.save_citations(session.conversation_id, msg_id, message.citations)

            if message.sources:
                research_repository.save_sources(session.conversation_id, message.sources)

            if message.tool_calls:
                for tc in message.tool_calls:
                    tool_repository.record_tool_call(session.conversation_id, tc)

            conversation_repository.touch(session.conversation_id)

    def update_context(
        self,
        session_id: str,
        query_result: Optional[Any] = None,
        query_summary: Optional[str] = None,
        tool_call: Optional[ToolCallRecord] = None,
        chart: Optional[ChartPayload] = None
    ) -> None:
        session = self.get_session(session_id)
        with self._sessions_lock:
            if query_result is not None:
                session.last_query_result = query_result
            if query_summary is not None:
                session.last_query_summary = query_summary
            if tool_call is not None:
                session.last_tool_call = tool_call
                session.tool_history.append(tool_call)
                tool_repository.record_tool_call(session.conversation_id, tool_call)
            if chart is not None:
                session.last_chart = chart
            session.touch()
            conversation_repository.touch(session.conversation_id)

    def clear_session(self, session_id: str) -> None:
        self.delete_conversation(session_id)


session_manager = SessionManager()
